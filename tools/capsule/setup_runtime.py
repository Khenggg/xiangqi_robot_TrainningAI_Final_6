"""Install ML wheels once into this capsule; never alter system Python."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    runtime = root / 'runtime'
    if Path(sys.executable).resolve() != runtime / 'python.exe':
        raise RuntimeError('Run INSTALL.bat or start.bat')
    state = root / 'state'
    state.mkdir(exist_ok=True)
    environment = dict(os.environ)
    for key, folder in [('TEMP', 'temp'), ('TMP', 'temp'), ('PIP_CACHE_DIR', 'pip-cache')]:
        path = state / folder
        path.mkdir(exist_ok=True)
        environment[key] = str(path)
    gpu = False
    smi = shutil.which('nvidia-smi')
    if smi:
        result = subprocess.run([smi, '-L'], capture_output=True, text=True, timeout=15)
        gpu = result.returncode == 0 and 'GPU ' in result.stdout
    print('[SETUP] ' + ('NVIDIA found: installing CUDA runtime (large download).' if gpu
                       else 'No NVIDIA GPU found: installing CPU runtime.'), flush=True)
    selected = [line for line in (root / 'gpu-requirements.txt').read_text(encoding='utf-8').splitlines()
                if line.startswith(('torch @ ', 'torchvision @ ', 'onnxruntime-gpu=='))]
    if len(selected) != 3:
        raise RuntimeError('ML dependency lock incomplete')
    if not gpu:
        selected = [
            'torch @ https://download.pytorch.org/whl/cpu/torch-2.5.1%2Bcpu-cp312-cp312-win_amd64.whl#sha256=a6b720410350765d3d77c01a5ce098a6c45af446284e45e87a98b8a16e7d564d',
            'torchvision @ https://download.pytorch.org/whl/cpu/torchvision-0.20.1%2Bcpu-cp312-cp312-win_amd64.whl#sha256=64832095b9b8b8185f24788f1a531ae96c937bf797cd3474a2ea7511852e5cd7',
            'onnxruntime==1.20.2',
        ]
    # Optional, verified local wheel cache for team installations/acceptance.
    wheelhouse = os.environ.get('XIANGQI_WHEELHOUSE')
    if wheelhouse:
        from urllib.parse import unquote, urlsplit
        for index, line in enumerate(selected):
            if ' @ ' not in line:
                continue
            name, reference = line.split(' @ ', 1)
            url, digest = reference.split('#sha256=', 1)
            wheel = Path(wheelhouse) / unquote(Path(urlsplit(url).path).name)
            if wheel.is_file():
                with wheel.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                        raise RuntimeError('Local wheel checksum mismatch: ' + wheel.name)
                selected[index] = f'{name} @ {wheel.resolve().as_uri()}#sha256={digest}'
    lock = state / 'selected-ml-requirements.txt'
    lock.write_text('\n'.join(selected) + '\n', encoding='utf-8')
    command = [sys.executable, '-I', '-X', 'utf8', '-m', 'pip', 'install', '--no-deps', '--upgrade',
               '--only-binary=:all:', '--target', str(runtime / 'Lib/site-packages'), '-r', str(lock),
               '--report', str(state / 'ml-install-report.json')]
    if wheelhouse:
        command += ['--find-links', wheelhouse]
    subprocess.run(command, env=environment, check=True)
    import torch
    import onnxruntime as ort
    if gpu and (not torch.cuda.is_available() or 'CUDAExecutionProvider' not in ort.get_available_providers()):
        raise RuntimeError('CUDA is not ready. Check/update NVIDIA driver, then rerun INSTALL.bat.')
    (state / 'runtime-install.json').write_text(json.dumps({
        'device': 'cuda' if gpu else 'cpu', 'torch': torch.__version__,
        'cuda': torch.version.cuda, 'onnxruntime': ort.__version__,
    }, indent=2), encoding='utf-8')
    print('[SETUP] ML runtime ready: ' + ('GPU' if gpu else 'CPU'), flush=True)


if __name__ == '__main__':
    main()
