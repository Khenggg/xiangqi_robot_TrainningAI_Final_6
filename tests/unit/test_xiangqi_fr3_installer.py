"""Xiangqi-FR3 installer: adds only what is missing and never replaces without consent."""
import base64
import hashlib
import io
import json
import tarfile

from pip._vendor.packaging.requirements import Requirement

from tools.installer import build_zip, env_check


def reqs(*lines):
    return [Requirement(line) for line in lines]


def test_present_packages_are_skipped_and_missing_ones_planned():
    missing, conflicts = env_check.plan_packages(
        reqs('numpy>=1.24', 'pygame>=2.5'), {'numpy': '1.26.4', 'onnxruntime': '1.20.0'}, gpu=False)
    assert missing == ['pygame>=2.5'] and conflicts == []


def test_incompatible_version_is_a_conflict_not_an_install():
    missing, conflicts = env_check.plan_packages(reqs('numpy>=1.24'), {'numpy': '1.23.0', 'onnxruntime': '1'}, gpu=False)
    assert missing == [] and [(str(r), v) for r, v in conflicts] == [('numpy>=1.24', '1.23.0')]


def test_existing_gpu_or_cpu_onnxruntime_is_kept():
    for name in env_check.ORT_NAMES:
        missing, _ = env_check.plan_packages([], {name: '1.20.2'}, gpu=True)
        assert missing == []
    assert env_check.plan_packages([], {}, gpu=True)[0] == [env_check.ORT_GPU]
    assert env_check.plan_packages([], {}, gpu=False)[0] == [env_check.ORT_CPU]


def test_missing_torch_uses_cuda_wheels_on_gpu_and_keeps_installed_torchvision():
    missing, _ = env_check.plan_packages(reqs('torch>=2.0'), {'onnxruntime': '1'}, gpu=True)
    assert missing == list(env_check.GPU_TORCH)
    missing, _ = env_check.plan_packages(reqs('torch>=2.0'), {'onnxruntime': '1', 'torchvision': '0.29.1'}, gpu=True)
    assert missing == ['torch==2.14.1']
    assert env_check.plan_packages(reqs('torch>=2.0'), {'onnxruntime': '1'}, gpu=False)[0] == ['torch>=2.0']


def test_pip_constraints_pin_installed_packages_except_accepted_replacements(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(env_check.subprocess, 'run', lambda cmd, **k: calls.append(cmd) or type('R', (), {'returncode': 0})())
    assert env_check.pip_install(['numpy>=1.24'], {'numpy': '1.23.0', 'pillow': '10.0.0'}, ['NumPy'], tmp_path)
    pins = (tmp_path / 'keep-installed-constraints.txt').read_text().split()
    assert pins == ['pillow==10.0.0']
    assert calls[0][-1] == 'numpy>=1.24' and '-c' in calls[0]


def test_declined_replacement_installs_nothing(tmp_path, monkeypatch):
    (tmp_path / 'requirements.txt').write_text('numpy>=1.24\n')
    monkeypatch.setattr(env_check, 'installed_versions', lambda: {'numpy': '1.23.0', 'onnxruntime': '1'})
    monkeypatch.setattr(env_check, 'has_nvidia_gpu', lambda: False)
    monkeypatch.setattr(env_check, 'pip_install', lambda *a, **k: (_ for _ in ()).throw(AssertionError('installed')))
    report = {'installed': [], 'declined': [], 'warnings': []}
    assert env_check.ensure_packages(tmp_path, tmp_path, 'no', report)
    assert report['declined'] == ['numpy==1.23.0'] and report['installed'] == []


def three_fixture(tmp_path):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w:gz') as bundle:
        for name in env_check.THREE_FILES + ('LICENSE',):
            data = f'new {name}'.encode()
            info = tarfile.TarInfo(f'package/{name}')
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
    blob = raw.getvalue()
    integrity = 'sha512-' + base64.b64encode(hashlib.sha512(blob).digest()).decode()
    (tmp_path / 'package-lock.json').write_text(json.dumps({'packages': {'node_modules/three': {
        'version': '0.0.1', 'resolved': 'https://test.invalid/three.tgz', 'integrity': integrity}}}))
    cache = tmp_path / 'cache'
    cache.mkdir()
    (cache / 'three-0.0.1.tgz').write_bytes(blob)
    return cache


def test_three_adds_missing_files_without_overwriting(tmp_path):
    cache = three_fixture(tmp_path)
    kept = tmp_path / 'node_modules/three/build/three.module.js'
    kept.parent.mkdir(parents=True)
    kept.write_text('user copy')
    report = {'installed': []}
    assert env_check.ensure_three(tmp_path, cache, report)
    assert kept.read_text() == 'user copy'
    assert (tmp_path / 'node_modules/three/LICENSE').read_text() == 'new LICENSE'


def test_three_rejects_archive_failing_lock_integrity(tmp_path):
    cache = three_fixture(tmp_path)
    (cache / 'three-0.0.1.tgz').write_bytes(b'tampered')
    assert not env_check.ensure_three(tmp_path, cache, {'installed': []})
    assert not (tmp_path / 'node_modules').exists()


def test_capsule_leaves_out_development_folders(tmp_path, monkeypatch):
    names = ['main.py', 'src/a.py', 'Xiangqi-FR3.bat', 'tests/unit/t.py', 'reports/r.md', '.agents/x.md', 'plans/p.md']
    for name in names:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text('x')
    monkeypatch.setattr(build_zip.subprocess, 'check_output', lambda *a, **k: '\0'.join(names).encode())
    assert build_zip.project_files(tmp_path) == ['Xiangqi-FR3.bat', 'main.py', 'src/a.py']
