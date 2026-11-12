"""Xiangqi-FR3 environment check: install only what is missing, replace nothing without consent.

Runs inside the project's own ``.venv312`` (created by ``install.ps1``). It never
modifies project source, configuration or calibration; it only adds missing
Python packages, missing Three.js files and missing model files.

Exit codes: 0 ready (warnings allowed), 1 install failed, 2 cancelled by the user.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata as metadata
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.utils import canonicalize_name

# Same GPU/CPU runtime choices as scripts/windows/SETUP_GPU.bat and SETUP_WINDOWS.bat.
GPU_TORCH = ('torch==2.14.1', 'torchvision==0.29.1')
GPU_TORCH_INDEX = 'https://download.pytorch.org/whl/cu126'
ORT_CPU = 'onnxruntime>=1.16'
ORT_GPU = 'onnxruntime-gpu==1.20.2'
ORT_NAMES = ('onnxruntime', 'onnxruntime-gpu')
REQUIRED_MODELS = ('best.pt', 'cchess/pose_4_v6.onnx', 'cchess/layout_nano_v3.onnx')
# Mirrors the node_modules entries of src/core/launch_options.check_viewer_assets.
THREE_FILES = ('build/three.module.js', 'build/three.core.js',
               'examples/jsm/controls/OrbitControls.js', 'examples/jsm/loaders/STLLoader.js')


def say(tag, message):
    print(f' [{tag}] {message}', flush=True)


def ask(question, mode):
    """mode: 'ask' prompts on a console, 'yes' accepts, 'no' declines."""
    if mode != 'ask':
        say('AUTO', f'{question} -> {mode}')
        return mode == 'yes'
    if not sys.stdin or not sys.stdin.isatty():
        say('AUTO', f'{question} -> no (no console)')
        return False
    try:
        return input(f'  ? {question} [y/N]: ').strip().lower() in ('y', 'yes')
    except EOFError:
        return False


def installed_versions():
    """First distribution on sys.path wins, matching what imports will load."""
    found = {}
    for dist in metadata.distributions():
        name = dist.metadata.get('Name')
        if name:
            found.setdefault(canonicalize_name(name), dist.version)
    return found


def read_requirements(path):
    requirements = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line or line.startswith('-'):
            continue
        requirement = Requirement(line)
        if requirement.marker is None or requirement.marker.evaluate():
            requirements.append(requirement)
    return requirements


def has_nvidia_gpu():
    smi = shutil.which('nvidia-smi')
    if not smi:
        return False
    try:
        return subprocess.run([smi, '-L'], capture_output=True, text=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def plan_packages(requirements, installed, gpu):
    """Return (missing specs, conflicts [(requirement, installed version)])."""
    missing, conflicts = [], []
    names = {canonicalize_name(r.name) for r in requirements}
    for requirement in requirements:
        name = canonicalize_name(requirement.name)
        version = installed.get(name)
        if version is None:
            if name == 'torch' and gpu:
                missing.extend(GPU_TORCH)  # CUDA wheel first, so ultralytics does not pull CPU torch
            else:
                missing.append(str(requirement))
        elif not requirement.specifier.contains(version, prereleases=True):
            conflicts.append((requirement, version))
    if not any(n in installed for n in ORT_NAMES) and not names & set(ORT_NAMES):
        missing.append(ORT_GPU if gpu else ORT_CPU)  # exactly one ORT runtime, never both
    if 'torchvision' in installed:
        missing = [spec for spec in missing if not spec.startswith('torchvision')]
    return missing, conflicts


def pip_install(specs, installed, replace, cache, *, index_url=None):
    """Install specs while pinning every already-installed package to its current version."""
    replace = {canonicalize_name(n) for n in replace}
    constraints = cache / 'keep-installed-constraints.txt'
    constraints.write_text(''.join(f'{name}=={version}\n' for name, version in sorted(installed.items())
                                   if name not in replace), encoding='utf-8')
    command = [sys.executable, '-m', 'pip', 'install', '--disable-pip-version-check',
               '--upgrade-strategy', 'only-if-needed', '-c', str(constraints), *specs]
    if index_url:
        command[4:4] = ['--index-url', index_url]
    say('INSTALL', ' '.join(specs))
    return subprocess.run(command).returncode == 0


def ensure_packages(root, cache, mode, report):
    requirements = read_requirements(root / 'requirements.txt')
    installed = installed_versions()
    gpu = has_nvidia_gpu()
    report['gpu'] = gpu
    missing, conflicts = plan_packages(requirements, installed, gpu)
    replace = []
    for requirement, version in conflicts:
        compatible = str(requirement)
        say('VERSION', f'{requirement.name} {version} is installed; this project needs {compatible}.')
        if ask(f'Install a compatible {compatible} for this project (other programs keep their copy)?', mode):
            replace.append(requirement.name)
            missing.append(compatible)
        else:
            say('WARN', f'Keeping {requirement.name} {version}. The project may not run correctly.')
            report['declined'].append(f'{requirement.name}=={version}')
    if not missing:
        say('OK', f'Python packages present ({len(requirements)} requirements checked).')
        return True
    gpu_torch = [spec for spec in missing if spec in GPU_TORCH]
    others = [spec for spec in missing if spec not in GPU_TORCH]
    say('INFO', f'Missing or replacement packages: {", ".join(missing)}')
    if gpu_torch and not pip_install(gpu_torch, installed, replace, cache, index_url=GPU_TORCH_INDEX):
        return False
    installed = installed_versions()
    if others and not pip_install(others, installed, replace, cache):
        say('ERROR', 'pip could not add the packages without changing installed ones. See the pip output above.')
        return False
    report['installed'].extend(missing)
    return True


def ensure_three(root, cache, report):
    target = root / 'node_modules' / 'three'
    if all((target / name).is_file() for name in THREE_FILES):
        say('OK', 'Three.js viewer modules present.')
        return True
    package = json.loads((root / 'package-lock.json').read_text(encoding='utf-8'))['packages']['node_modules/three']
    algorithm, expected = package['integrity'].split('-', 1)
    archive = cache / f'three-{package["version"]}.tgz'
    if not archive.is_file():
        say('DOWNLOAD', f'three {package["version"]}')
        with urllib.request.urlopen(package['resolved'], timeout=90) as response:
            archive.write_bytes(response.read())
    if algorithm != 'sha512' or base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode() != expected:
        archive.unlink(missing_ok=True)
        say('ERROR', 'Three.js archive failed the package-lock integrity check.')
        return False
    added = 0
    with tarfile.open(archive, 'r:gz') as bundle:
        for member in bundle.getmembers():
            parts = PurePosixPath(member.name).parts
            if not member.isfile() or len(parts) < 2 or parts[0] != 'package' or '..' in parts:
                continue
            destination = target.joinpath(*parts[1:])
            if destination.exists():
                continue  # never overwrite an existing file
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source, destination.open('wb') as stream:
                shutil.copyfileobj(source, stream)
            added += 1
    say('INSTALL', f'Three.js {package["version"]}: added {added} missing files.')
    report['installed'].append(f'three@{package["version"]}')
    return all((target / name).is_file() for name in THREE_FILES)


def ensure_models(root, report):
    models = root / 'models'
    missing = [name for name in REQUIRED_MODELS if not (models / name).is_file()]
    if any(name.endswith('.onnx') for name in missing):
        say('DOWNLOAD', 'Chinese-chess ONNX models')
        subprocess.run([sys.executable, str(root / 'scripts/models/download_cchess_models.py')], cwd=root)
        missing = [name for name in REQUIRED_MODELS if not (models / name).is_file()]
    if missing:
        report['warnings'].append('missing models: ' + ', '.join(missing))
        say('WARN', f'Missing models: {", ".join("models/" + m for m in missing)}. Camera recognition will not work; '
                    'the 2D board and simulation still run.')
    else:
        say('OK', 'Vision models present.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument('--yes', action='store_const', const='yes', dest='mode', help='accept compatible replacements')
    choice.add_argument('--no-input', action='store_const', const='no', dest='mode', help='decline replacements')
    parser.set_defaults(mode='ask')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if sys.version_info[:2] != (3, 12):
        say('ERROR', f'Python 3.12 required, found {sys.version.split()[0]}.')
        return 1
    cache = root / 'build' / 'installer'
    cache.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(cache)
    report = {'checked_utc': datetime.now(timezone.utc).isoformat(), 'python': sys.executable,
              'installed': [], 'declined': [], 'warnings': []}
    ok = ensure_packages(root, cache, args.mode, report) and ensure_three(root, cache, report)
    if ok:
        ensure_models(root, report)
    report['ready'] = ok
    (cache / 'last-check.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
