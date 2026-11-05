"""Physical startup must not silently accept a camera without recognition models."""
from types import SimpleNamespace

import numpy as np
import pytest

import config
from src.hardware import hardware_manager as module


class _Capture:
    def __init__(self):
        self.released = False

    def isOpened(self):
        return not self.released

    def release(self):
        self.released = True


def test_missing_models_fail_physical_camera_startup(monkeypatch, tmp_path):
    cfg = SimpleNamespace(**{key: getattr(config, key) for key in dir(config) if key.isupper()})
    cfg.ROBOT_BACKEND = "PHYSICAL"
    cfg.DRY_RUN = False
    cfg.CCHESS_RECOGNITION_ENABLED = True
    cfg.VIDEO_SOURCE = 0
    cfg.RECALIBRATE_CAMERA = False
    np.save(tmp_path / "perspective.npy", np.eye(3))
    cap = _Capture()
    monkeypatch.setattr(module, "YOLO", None)
    monkeypatch.setattr("src.vision.camera_startup.open_validated_camera", lambda index: cap)

    manager = module.HardwareManager(cfg, str(tmp_path))
    with pytest.raises(RuntimeError, match="Physical camera recognition unavailable"):
        manager._init_camera()

    assert manager.camera_recognition_ready is False
    assert manager.cam_monitor is None
    assert manager.camera_startup_error
    assert "CChess" in manager.camera_startup_error
    assert "YOLO" in manager.camera_startup_error
    assert cap.released
