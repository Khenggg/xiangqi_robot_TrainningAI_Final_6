"""Build an app-local Windows release, never a copied virtualenv."""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.capsule.launcher import sha256, contained

PYTHON_URL = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
PYTHON_SHA256 = '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
SOURCE_ROOTS = {'src', 'assets', 'calibration', 'shared', 'moonfish', 'robot-3d-viewer'}
MODEL_FILES = ('best.pt', 'cchess/pose_4_v6.onnx', 'cchess/layout_nano_v3.onnx')
OPTIONAL_MODELS = ('board_pose.pt', 'hand_best_egohands.pt')
START_BAT = r'''@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0runtime\python.exe" (
  echo [ERROR] Capsule incomplete. Extract the complete ZIP before opening START.bat.
  pause
  exit /b 1
)
"%~dp0runtime\python.exe" -I "%~dp0launcher.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%
'''


def run(command, **kwargs):
    print('>', ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True, **kwargs)


def download(url, target, expected):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and sha256(target) == expected:
        print(f'[CACHE] {target.name}', flush=True)
        return target
    temporary = target.with_suffix(target.suffix + '.part')
    print(f'[DOWNLOAD] {target.name}', flush=True)
    with urllib.request.urlopen(url, timeout=90) as response, temporary.open('wb') as stream:
        shutil.copyfileobj(response, stream)
    if sha256(temporary) != expected:
        raise RuntimeError(f'Download checksum mismatch: {target.name}')
    temporary.replace(target)
    return target


def extract_zip(archive, destination):
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            contained(destination, entry.filename)
            if entry.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError('Archive symlinks are not permitted')
        bundle.extractall(destination)


def tracked_source(root):
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode('utf-8').split('\0')
    return sorted(name for name in tracked if name and (
        Path(name).parts[0] in SOURCE_ROOTS or name in {'main.py', 'config.py'}))


def copy_source(root, app):
    files = tracked_source(root)
    if not files:
        raise RuntimeError('Cannot build without tracked runtime source')
    for relative in files:
        src = contained(root, relative)
        if src.is_symlink() or not src.is_file():
            raise RuntimeError(f'Unsafe or missing tracked runtime asset: {relative}')
        dst = contained(app, relative)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return files


def prepare_dependencies(cache):
    requirements = ROOT / 'tools/capsule/requirements.txt'
    fingerprint = sha256(requirements)
    site = cache / 'site'
    stamp = cache / 'site-ready.json'
    if stamp.exists() and json.loads(stamp.read_text()).get('requirements_sha256') == fingerprint:
        if site.is_dir():
            print('[CACHE] validated dependency installation', flush=True)
            return site
    if site.exists():
        # Never install over an interrupted target: pip --target can leave stale code.
        raise RuntimeError(f'Incomplete dependency cache: {site}. Move it aside and rebuild.')
    wheels = cache / 'wheels'
    wheels.mkdir(exist_ok=True)
    run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--wheel-dir', wheels, 'pybullet==3.2.7'])
    run([sys.executable, '-m', 'pip', 'install', '--target', site, '--no-compile',
         '--only-binary=:all:', '--find-links', wheels, '-r', requirements,
         '--report', cache / 'dependency-install.json'])
    stamp.write_text(json.dumps({'requirements_sha256': fingerprint}), encoding='utf-8')
    return site


def install_three(cache, app):
    package = json.loads((ROOT / 'package-lock.json').read_text())['packages']['node_modules/three']
    archive = cache / f'three-{package["version"]}.tgz'
    algorithm, expected = package['integrity'].split('-', 1)
    if algorithm != 'sha512':
        raise ValueError('Expected SHA512 lock integrity for Three.js')
    if not archive.exists():
        with urllib.request.urlopen(package['resolved'], timeout=90) as response:
            archive.write_bytes(response.read())
    if base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode() != expected:
        raise RuntimeError('Three.js lock integrity mismatch')
    destination = app / 'node_modules/three'
    with tarfile.open(archive, 'r:gz') as bundle:
        for member in bundle.getmembers():
            parts = Path(member.name).parts
            if not parts or parts[0] != 'package':
                raise ValueError('Unexpected npm archive prefix')
            target = contained(destination, str(Path(*parts[1:])))
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.extractfile(member) as src, target.open('wb') as dst:
                    shutil.copyfileobj(src, dst)
            else:
                raise ValueError('Npm archive links are not allowed')


def resource_assets(cache, app):
    resources = json.loads((ROOT / 'tools/capsule/resources.json').read_text())
    for item in resources:
        source = download(item['url'], cache / item['name'], item['sha256'])
        target = contained(app, item['destination'])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def install_vc_runtime(runtime):
    """Ship the native imports which a developer PC can silently supply globally."""
    names = ('msvcp140.dll', 'msvcp140_1.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')
    system = Path(os.environ['SystemRoot']) / 'System32'
    paths = [system / name for name in names]
    for path in paths:
        if not path.is_file():
            raise RuntimeError(f'Builder missing Microsoft C++ runtime: {path}')
    literals = ','.join("'" + str(path).replace("'", "''") + "'" for path in paths)
    command = ("$ErrorActionPreference='Stop'; Import-Module Microsoft.PowerShell.Security -ErrorAction Stop; "
               "$result=foreach($file in @(" + literals + ")) { "
               "$s=Get-AuthenticodeSignature -LiteralPath $file; "
               "if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch '^CN=Microsoft (Windows(?: Software Compatibility Publisher)?|Corporation),') "
               "{ throw ('Untrusted VC runtime: '+$file) }; "
               "[PSCustomObject]@{File=$file;Signer=$s.SignerCertificate.Subject} }; "
               "ConvertTo-Json -InputObject @($result) -Compress")
    environment = dict(os.environ)
    environment.pop('PSModulePath', None)  # pwsh's module path can break Windows PowerShell 5 autoload.
    powershell = shutil.which('pwsh.exe') or system / 'WindowsPowerShell/v1.0/powershell.exe'
    provenance = subprocess.check_output(
        [str(powershell), '-NoProfile', '-NonInteractive', '-Command', command],
        text=True, env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
    for path in paths:
        shutil.copy2(path, runtime / path.name)
    (runtime / 'vc-runtime-provenance.json').write_text(provenance, encoding='utf-8')


def write_manifest(destination, source_files):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    source_dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '-uno'], cwd=ROOT))
    packages = sorted(({'name': item.metadata['Name'], 'version': item.version}
                       for item in importlib.metadata.distributions(path=[str(destination / 'runtime/Lib/site-packages')])),
                      key=lambda item: item['name'].lower())
    candidates = [file for file in sorted(destination.rglob('*')) if file.is_file()
                  and file.relative_to(destination).as_posix() not in {'settings.json', 'manifest.json'}
                  and not file.relative_to(destination).as_posix().startswith('state/')]
    print(f'[MANIFEST] Hashing {len(candidates)} release files', flush=True)
    def fingerprint(file):
        return file.relative_to(destination).as_posix(), {'size': file.stat().st_size, 'sha256': sha256(file)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        files = dict(pool.map(fingerprint, candidates))
    manifest = {'schema_version': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
                'platform': 'Windows 10/11 x64', 'python': '3.12.10', 'vision': 'CPU',
                'source': {'head': head, 'tracked_changes': source_dirty,
                           'files': {name: files['app/' + name]['sha256'] for name in source_files}},
                'packages': packages, 'files': files}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def build(args):
    if os.name != 'nt' or sys.version_info[:2] != (3, 12):
        raise RuntimeError('Build using Windows x64 Python 3.12')
    cache = (ROOT / 'build/capsule-cache').resolve()
    cache.mkdir(parents=True, exist_ok=True)
    destination = Path(args.output).resolve()
    if destination.exists():
        raise RuntimeError(f'Output already exists; choose a new output path: {destination}')
    if destination.with_suffix('.zip').exists():
        raise RuntimeError('Archive already exists; choose a new output path')
    build_temp = cache / 'temp'
    build_temp.mkdir(exist_ok=True)
    # Large wheels must unpack on the build drive, not a nearly-full system drive.
    os.environ['TEMP'] = os.environ['TMP'] = str(build_temp)
    tempfile.tempdir = str(build_temp)
    models = Path(args.models).resolve()
    for name in MODEL_FILES:
        if not (models / name).is_file():
            raise RuntimeError(f'Required model missing: {models / name}')
    site = prepare_dependencies(cache)
    python_archive = download(PYTHON_URL, cache / 'python-3.12.10-embed-amd64.zip', PYTHON_SHA256)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Staging is within the explicit output parent; TemporaryDirectory cleans only its own resolved folder.
    with tempfile.TemporaryDirectory(prefix='.capsule-', dir=destination.parent) as temporary:
        stage = Path(temporary).resolve()
        assert stage.is_relative_to(destination.parent)
        runtime = stage / 'runtime'
        runtime.mkdir()
        extract_zip(python_archive, runtime)
        print('[PACKAGE] Copying runtime dependencies (no development headers/tests/static libraries)', flush=True)
        shutil.copytree(site, runtime / 'Lib/site-packages', ignore=shutil.ignore_patterns(
            '__pycache__', '*.pyc', 'bin', 'include', 'tests', '*.lib', '*.h', '*.hpp', '*.pyi',
            'pybullet_data'))  # Stock demo datasets; this app ships its own checked FR3/board assets.
        install_vc_runtime(runtime)
        (runtime / 'python312._pth').write_text(
            'python312.zip\n.\nLib/site-packages\n../app/moonfish\n../app\nimport site\n', encoding='ascii')
        app = stage / 'app'
        app.mkdir()
        source_files = copy_source(ROOT, app)
        for name in MODEL_FILES + OPTIONAL_MODELS:
            if (models / name).is_file():
                target = app / 'models' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(models / name, target)
        install_three(cache, app)
        resource_assets(cache, app)
        shutil.copy2(ROOT / 'tools/capsule/launcher.py', stage / 'launcher.py')
        shutil.copy2(ROOT / 'docs/CAPSULE_OPERATOR.md', stage / 'READ_ME_FIRST.md')
        (stage / 'START.bat').write_text(START_BAT, encoding='ascii')
        (stage / 'settings.json').write_text(json.dumps(
            {'mode': 'SIMULATION', 'camera_index': 2, 'robot_ip': '192.168.58.2'}, indent=2), encoding='utf-8')
        (stage / 'state').mkdir()
        licenses = stage / 'LICENSES'
        licenses.mkdir()
        (licenses / 'README.txt').write_text(
            'CPython license: runtime/LICENSE.txt\nPython dependency licenses: runtime/Lib/site-packages/*dist-info/\n'
            'Three.js MIT: app/node_modules/three/LICENSE\nCAD loader: app/robot-3d-viewer/vendor/occt-import-js/LICENSE.md\n'
            'Noto font OFL: app/assets/fonts/OFL.txt\nMoonfish: app/moonfish/\n'
            'Project-specific weights are supplied by the team; verify redistribution rights before public distribution.\n',
            encoding='utf-8')
        write_manifest(stage, source_files)
        # Run portable interpreter itself, with no external tools on PATH.
        environment = dict(os.environ, PATH=os.path.join(os.environ['SystemRoot'], 'System32'))
        environment.pop('PYTHONPATH', None)
        environment.pop('PYTHONHOME', None)
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        run([runtime / 'python.exe', '-B', '-I', stage / 'launcher.py', '--smoke'], env=environment, cwd=stage)
        # Logs/model caches from self-check are build evidence, not an operator session.
        # Keep smoke evidence in state, which is explicitly mutable/non-manifest.
        stage.rename(destination)
    archive = destination.with_suffix('.zip')
    if archive.exists():
        raise RuntimeError(f'Archive already exists: {archive}')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as output:
        for file in sorted(destination.rglob('*')):
            if file.is_file():
                output.write(file, f'{destination.name}/{file.relative_to(destination).as_posix()}')
    checksum = sha256(archive)
    archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n', encoding='ascii')
    print(f'CAPSULE BUILT: {destination}\nZIP: {archive}\nSHA256: {checksum}', flush=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', required=True, help='Team-supplied models directory (best.pt and cchess/*.onnx)')
    parser.add_argument('--output', default=str(ROOT / 'dist/Xiangqi-Capsule-Windows-x64'))
    build(parser.parse_args())


if __name__ == '__main__':
    main()
