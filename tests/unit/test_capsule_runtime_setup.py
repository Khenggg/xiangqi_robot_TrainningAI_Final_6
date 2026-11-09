import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize('nvidia,cuda_ready', [(True, True), (False, False), (True, False)])
def test_first_run_installs_only_local_ml_packages_and_requires_usable_cuda(tmp_path, monkeypatch, nvidia, cuda_ready):
    source = Path(__file__).resolve().parents[2] / 'tools/capsule/setup_runtime.py'
    spec = importlib.util.spec_from_file_location('runtime_setup_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, '__file__', str(tmp_path/'setup_runtime.py'))
    monkeypatch.setattr(sys, 'executable', str(tmp_path/'runtime/python.exe'))
    (tmp_path/'gpu-requirements.txt').write_text(
        'torch @ https://test.invalid/torch.whl#sha256=abc\n'
        'torchvision @ https://test.invalid/vision.whl#sha256=def\nonnxruntime-gpu==1.20.1\n')
    monkeypatch.delenv('XIANGQI_WHEELHOUSE', raising=False)
    monkeypatch.setattr(module.shutil, 'which', lambda name: 'nvidia-smi' if nvidia else None)
    run = Mock(return_value=SimpleNamespace(returncode=0, stdout='GPU 0: NVIDIA'))
    monkeypatch.setattr(module.subprocess, 'run', run)
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(__version__='2.5.1',
        cuda=SimpleNamespace(is_available=lambda: cuda_ready), version=SimpleNamespace(cuda='12.4' if cuda_ready else None)))
    monkeypatch.setitem(sys.modules, 'onnxruntime', SimpleNamespace(__version__='1.20.1',
        get_available_providers=lambda: ['CUDAExecutionProvider', 'CPUExecutionProvider']))
    if nvidia and not cuda_ready:
        with pytest.raises(RuntimeError, match='CUDA is not ready'):
            module.main()
        assert not (tmp_path/'state/runtime-install.json').exists()
    else:
        module.main()
        result = json.loads((tmp_path/'state/runtime-install.json').read_text())
        assert result['device'] == ('cuda' if nvidia else 'cpu')
    command = run.call_args.args[0]
    assert command[:6] == [sys.executable, '-I', '-X', 'utf8', '-m', 'pip']
    assert command[command.index('--target')+1] == str(tmp_path/'runtime/Lib/site-packages')
    assert '--no-deps' in command
    selected = (tmp_path/'state/selected-ml-requirements.txt').read_text()
    assert ('onnxruntime-gpu==1.20.1' in selected) == nvidia
