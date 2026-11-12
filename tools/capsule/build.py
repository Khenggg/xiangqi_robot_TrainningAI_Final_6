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
from urllib.parse import unquote, urlsplit
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
set "XIANGQI_CAPSULE_ROOT=%~dp0"
if /I "%~1"=="-Setup" goto :SETUP
if not exist "%~dp0runtime\python.exe" goto :INSTALL
if not exist "%~dp0runtime\.capsule-ready" goto :INSTALL
goto :RUN
:SETUP
set "XIANGQI_SETUP_ONLY=1"
:INSTALL
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create([IO.File]::ReadAllText((Join-Path $env:XIANGQI_CAPSULE_ROOT 'start.run')))) -Root $env:XIANGQI_CAPSULE_ROOT"
if errorlevel 1 goto :FAILED
if defined XIANGQI_SETUP_ONLY exit /b 0
:RUN
"%~dp0runtime\python.exe" -I "%~dp0launcher.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" pause
exit /b %RC%
:FAILED
echo [ERROR] First-run setup failed. See the message above.
pause
exit /b 1
'''
INSTALL_BAT = r'''@echo off
call "%~dp0start.bat" -Setup
if errorlevel 1 exit /b 1
echo Setup complete. Open start.bat to run Xiangqi.
pause
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
    if not list(wheels.glob('pybullet-3.2.7-cp312-cp312-win_amd64.whl')):
        run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--wheel-dir', wheels, 'pybullet==3.2.7'])
    # Reuse checksum-verified large CUDA wheels instead of restarting pip's download.
    install_lines = []
    for line in requirements.read_text(encoding='utf-8').splitlines():
        if ' @ https://' in line and '#sha256=' in line:
            name, reference = line.split(' @ ', 1)
            url, digest = reference.split('#sha256=', 1)
            wheel = download(url, wheels / unquote(Path(urlsplit(url).path).name), digest)
            line = f'{name} @ {wheel.resolve().as_uri()}#sha256={digest}'
        install_lines.append(line)
    install_requirements = cache / 'install-requirements.txt'
    install_requirements.write_text('\n'.join(install_lines) + '\n', encoding='utf-8')
    run([sys.executable, '-m', 'pip', 'install', '--target', site, '--no-compile',
         '--only-binary=:all:', '--find-links', wheels, '-r', install_requirements,
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
    # A tool-provided pwsh can lack bundled modules; use Windows' own signature
    # verifier and its native module tree rather than inherit developer paths.
    environment['PSModulePath'] = str(system / 'WindowsPowerShell/v1.0/Modules')
    powershell = system / 'WindowsPowerShell/v1.0/powershell.exe'
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
                'platform': 'Windows 10/11 x64', 'python': '3.12.10', 'vision': 'GPU preferred (CUDA 12.4), CPU fallback',
                'source': {'head': head, 'tracked_changes': source_dirty,
                           'files': {name: files['app/' + name]['sha256'] for name in source_files}},
                'packages': packages, 'files': files}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def build(args):
    if os.name != 'nt' or sys.version_info[:2] != (3, 12):
        raise RuntimeError('Build using Windows x64 Python 3.12')
    cache = (ROOT / 'build/capsule-cache-gpu').resolve()
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
    lightweight = getattr(args, 'lightweight', False)
    site = ROOT / 'build/capsule-cache/site' if lightweight else prepare_dependencies(cache)
    if not site.is_dir():
        raise RuntimeError('Base dependency cache unavailable')
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
        omitted = ('torch', 'torchgen', 'functorch', 'torchvision', 'torch-*.dist-info',
                   'torchvision-*.dist-info', 'onnxruntime', 'onnxruntime-*.dist-info') if lightweight else ()
        shutil.copytree(site, runtime / 'Lib/site-packages', ignore=shutil.ignore_patterns(
            '__pycache__', '*.pyc', 'bin', 'include', 'tests', '*.lib', '*.h', '*.hpp', '*.pyi',
            'pybullet_data', *omitted))
        if lightweight:
            import pip
            shutil.copytree(Path(pip.__file__).parent, runtime / 'Lib/site-packages/pip')
            pip_info = Path(importlib.metadata.distribution('pip')._path)
            shutil.copytree(pip_info, runtime / 'Lib/site-packages' / pip_info.name)
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
        shutil.copy2(ROOT / 'docs/guides/CAPSULE_OPERATOR.md', stage / 'READ_ME_FIRST.md')
        (stage / 'start.bat').write_text(START_BAT, encoding='ascii')
        (stage / 'INSTALL.bat').write_text(INSTALL_BAT, encoding='ascii')
        shutil.copy2(ROOT / 'tools/capsule/bootstrap.ps1', stage / 'start.run')
        shutil.copy2(ROOT / 'tools/capsule/setup_runtime.py', stage / 'setup_runtime.py')
        shutil.copy2(ROOT / 'tools/capsule/requirements.txt', stage / 'gpu-requirements.txt')
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
        if not lightweight:
            run([runtime / 'python.exe', '-B', '-I', stage / 'launcher.py', '--smoke'], env=environment, cwd=stage)
        # Logs/model caches from self-check are build evidence, not an operator session.
        # Keep smoke evidence in state, which is explicitly mutable/non-manifest.
        # Ship runtime compressed; the first start expands it locally, offline.
        runtime_archive = stage / 'runtime.zip'
        with zipfile.ZipFile(runtime_archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as packed:
            for file in sorted(runtime.rglob('*')):
                if file.is_file():
                    packed.write(file, file.relative_to(runtime).as_posix())
        manifest_path = stage / 'manifest.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        manifest['first_run_downloads'] = lightweight
        manifest['files']['runtime.zip'] = {'size': runtime_archive.stat().st_size,
                                          'sha256': sha256(runtime_archive)}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        stage.rename(destination)
    archive = destination.with_suffix('.zip')
    if archive.exists():
        raise RuntimeError(f'Archive already exists: {archive}')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as output:
        for file in sorted(destination.rglob('*')):
            relative = file.relative_to(destination)
            if file.is_file() and relative.parts[0] != 'runtime':
                output.write(file, f'{destination.name}/{relative.as_posix()}',
                             compress_type=zipfile.ZIP_STORED if relative.as_posix() == 'runtime.zip' else zipfile.ZIP_DEFLATED)
    checksum = sha256(archive)
    archive.with_suffix('.zip.sha256').write_text(f'{checksum}  {archive.name}\n', encoding='ascii')
    print(f'CAPSULE BUILT: {destination}\nZIP: {archive}\nSHA256: {checksum}', flush=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', required=True, help='Team-supplied models directory (best.pt and cchess/*.onnx)')
    parser.add_argument('--output', default=str(ROOT / 'dist/Xiangqi-Capsule-Windows-x64'))
    parser.add_argument('--lightweight', action='store_true', help='Download CUDA/ML packages on first setup instead of bundling them')
    build(parser.parse_args())


if __name__ == '__main__':
    main()
