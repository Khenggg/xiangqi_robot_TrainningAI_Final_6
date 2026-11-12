"""Build Xiangqi-FR3.zip: the project plus its installer/launcher, ready to unzip and start.

The archive holds a ``Xiangqi-FR3/`` folder with the project files from git
(tracked and new, not ignored), the vision models from ``--models`` and the
locked Three.js modules. Development-only folders are left out. Nothing in the
project is changed; the result is written to ``--output`` (default
``<repo>/Xiangqi-FR3.zip``, which ``*.zip`` in .gitignore keeps out of git).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
NAME = 'Xiangqi-FR3'
# Development and review material that a player does not need.
EXCLUDED_ROOTS = {'.agents', '.codex', '.vscode', 'reports', 'plans', 'tests'}
REQUIRED_MODELS = ('best.pt', 'cchess/pose_4_v6.onnx', 'cchess/layout_nano_v3.onnx')


def project_files(root):
    listing = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=root)
    names = sorted({name for name in listing.decode('utf-8').split('\0') if name})
    return [name for name in names
            if PurePosixPath(name).parts[0] not in EXCLUDED_ROOTS and (root / name).is_file()]


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def three_archive(root, cache):
    package = json.loads((root / 'package-lock.json').read_text(encoding='utf-8'))['packages']['node_modules/three']
    algorithm, expected = package['integrity'].split('-', 1)
    archive = cache / f'three-{package["version"]}.tgz'
    if not archive.is_file():
        print(f'[DOWNLOAD] three {package["version"]}', flush=True)
        with urllib.request.urlopen(package['resolved'], timeout=90) as response:
            archive.write_bytes(response.read())
    if algorithm != 'sha512' or base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode() != expected:
        archive.unlink()
        raise RuntimeError('Three.js archive failed the package-lock integrity check')
    return archive


def build(models, output, force):
    models = Path(models).resolve()
    missing = [name for name in REQUIRED_MODELS if not (models / name).is_file()]
    if missing:
        raise SystemExit(f'Required models missing in {models}: {", ".join(missing)}')
    output = Path(output).resolve()
    if output.exists() and not force:
        raise SystemExit(f'{output} already exists; pass --force to replace it.')
    cache = ROOT / 'build' / 'installer'
    cache.mkdir(parents=True, exist_ok=True)
    files = project_files(ROOT)
    model_files = sorted(p for p in models.rglob('*') if p.is_file())
    three = three_archive(ROOT, cache)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT))
    partial = output.with_name(output.name + '.part')
    with zipfile.ZipFile(partial, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as bundle:
        # Launcher first, so it is the first thing seen after unzipping.
        bundle.write(ROOT / f'{NAME}.bat', f'{NAME}/{NAME}.bat')
        bundle.write(ROOT / 'tools/installer/README_FIRST.txt', f'{NAME}/README_FIRST.txt')
        for name in files:
            if name not in (f'{NAME}.bat',):
                bundle.write(ROOT / name, f'{NAME}/{name}')
        for path in model_files:
            relative = path.relative_to(models).as_posix()
            if f'models/{relative}' in files:
                continue  # already added from git (models/cchess/README.md)
            bundle.write(path, f'{NAME}/models/{relative}', compress_type=zipfile.ZIP_STORED)
        with tarfile.open(three, 'r:gz') as package:
            for member in package.getmembers():
                parts = PurePosixPath(member.name).parts
                if member.isfile() and len(parts) > 1 and parts[0] == 'package' and '..' not in parts:
                    data = package.extractfile(member).read()
                    bundle.writestr(f'{NAME}/node_modules/three/{"/".join(parts[1:])}', data)
        manifest = {'name': NAME, 'built_utc': datetime.now(timezone.utc).isoformat(),
                    'source_head': head, 'source_has_local_changes': dirty, 'project_files': len(files),
                    'models': {p.relative_to(models).as_posix(): sha256(p) for p in model_files}}
        bundle.writestr(f'{NAME}/build/installer/capsule-manifest.json', json.dumps(manifest, indent=2))
    os.replace(partial, output)
    print(f'CAPSULE: {output}\nSIZE: {output.stat().st_size / 1e6:.1f} MB\nSHA256: {sha256(output)}\n'
          f'FILES: {len(files)} project + {len(model_files)} model files; source {head[:12]}'
          f'{" (with local changes)" if dirty else ""}', flush=True)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--models', required=True, help='folder holding best.pt and cchess/*.onnx')
    parser.add_argument('--output', default=str(ROOT / f'{NAME}.zip'))
    parser.add_argument('--force', action='store_true', help='replace an existing output archive')
    args = parser.parse_args(argv)
    build(args.models, args.output, args.force)


if __name__ == '__main__':
    sys.exit(main())
