import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows patch helper')


def run_patch(root):
    script = Path(__file__).resolve().parents[2] / 'tools/capsule/apply_do_patch.ps1'
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    return subprocess.run([str(powershell), '-NoProfile', '-ExecutionPolicy', 'Bypass',
                           '-File', str(script), '-Root', str(root)], capture_output=True)


def test_real_patch_preserves_local_settings_and_is_idempotent(tmp_path):
    root = tmp_path / 'Máy khác - Xiangqi'
    config = root / 'app/config.py'
    config.parent.mkdir(parents=True)
    before = ('# Cấu hình riêng\r\nROBOT_IP = "192.168.58.9"\r\nVIDEO_SOURCE = 1\r\n'
              'GRIPPER_OPEN_DO_ID = 0  # mở\r\nGRIPPER_CLOSE_DO_ID = 1  # đóng\r\n'
              'GRIPPER_CLOSE_PULSE_SEC = 0.8\r\n')
    config.write_bytes(before.encode('utf-8'))
    result = run_patch(root)
    assert result.returncode == 0, result.stderr
    expected = before.replace('GRIPPER_OPEN_DO_ID = 0', 'GRIPPER_OPEN_DO_ID = 1').replace(
        'GRIPPER_CLOSE_DO_ID = 1', 'GRIPPER_CLOSE_DO_ID = 0')
    assert config.read_bytes() == expected.encode('utf-8')
    backups = list(config.parent.glob('config.py.before-do-swap-*'))
    assert len(backups) == 1 and backups[0].read_bytes() == before.encode('utf-8')
    assert run_patch(root).returncode == 0
    assert len(list(config.parent.glob('config.py.before-do-swap-*'))) == 1


def test_ambiguous_config_is_not_modified(tmp_path):
    config = tmp_path/'app/config.py'
    config.parent.mkdir()
    before = b'GRIPPER_OPEN_DO_ID = 0\nGRIPPER_OPEN_DO_ID = 1\nGRIPPER_CLOSE_DO_ID = 1\n'
    config.write_bytes(before)
    assert run_patch(tmp_path).returncode != 0
    assert config.read_bytes() == before
    assert not list(config.parent.glob('config.py.before-do-swap-*'))
