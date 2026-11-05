"""Camera perspective startup: saved matrix by default, explicit recalibration."""
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from src.core.launch_options import configure_runtime, parse_options
from src.hardware import hardware_manager
from src.hardware.hardware_manager import HardwareManager


def _manager(tmp_path, saved=None, *, recalibrate=False):
    manager = HardwareManager.__new__(HardwareManager)
    manager.perspective_path = tmp_path / "perspective.npy"
    if saved is not None:
        np.save(manager.perspective_path, np.asarray(saved, dtype=float))
    manager.config = SimpleNamespace(RECALIBRATE_CAMERA=recalibrate, VIDEO_SOURCE=2)
    manager.cap = object()
    manager.cchess_recognizer = None
    manager.startup_cancelled = None
    manager.camera_calibration_ready = False
    manager.camera_calibration_source = "UNAVAILABLE"
    return manager


def _flow_writing(matrix, calls):
    def flow(cap, path, **kwargs):
        calls.append(dict(cap=cap, path=path, kwargs=kwargs))
        np.save(path, matrix)
        return matrix
    return flow


def test_saved_perspective_skips_interactive_calibration(tmp_path, monkeypatch, caplog):
    manager = _manager(tmp_path, np.eye(3))
    flow = Mock(side_effect=AssertionError("interactive calibration must not open"))
    monkeypatch.setattr(hardware_manager, "run_calibration_flow", flow)

    with caplog.at_level("INFO", logger="xiangqi"):
        manager._prepare_perspective_calibration(2)

    flow.assert_not_called()
    assert manager.camera_calibration_ready is True
    assert manager.camera_calibration_source == "SAVED_CALIBRATION"
    events = [record.event for record in caplog.records if getattr(record, "event", None)]
    assert "camera.calibration_loaded" in events


def test_missing_perspective_runs_interactive_calibration(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    matrix = np.array([[1.0, 0.0, 0.1], [0.0, 1.0, 0.2], [0.0, 0.0, 1.0]])
    calls = []
    monkeypatch.setattr(hardware_manager, "run_calibration_flow", _flow_writing(matrix, calls))

    manager._prepare_perspective_calibration(2)

    assert len(calls) == 1
    assert manager.camera_calibration_ready is True
    assert manager.camera_calibration_source == "FRESH_CALIBRATION"


def test_invalid_saved_perspective_fails_with_clear_action(tmp_path, monkeypatch):
    manager = _manager(tmp_path, np.zeros((3, 3)))
    flow = Mock(side_effect=AssertionError("must not open calibration without the flag"))
    monkeypatch.setattr(hardware_manager, "run_calibration_flow", flow)

    with pytest.raises(RuntimeError, match="--recalibrate-camera"):
        manager._prepare_perspective_calibration(2)

    flow.assert_not_called()
    assert manager.camera_calibration_ready is False


def test_manual_camera_checkbox_passes_manual_only_to_flow(tmp_path, monkeypatch):
    manager = _manager(tmp_path, np.eye(3), recalibrate=True)
    manager.config.CAMERA_CALIBRATION_MANUAL_ONLY = True
    matrix = np.array([[1.0, 0.0, 0.25], [0.0, 1.0, 0.5], [0.0, 0.0, 1.0]])
    calls = []
    monkeypatch.setattr(hardware_manager, "run_calibration_flow", _flow_writing(matrix, calls))

    manager._prepare_perspective_calibration(2)

    assert calls[0]["kwargs"]["manual_only"] is True


def test_recalibrate_flag_runs_interactive_calibration(tmp_path, monkeypatch):
    manager = _manager(tmp_path, np.eye(3), recalibrate=True)
    matrix = np.array([[1.0, 0.0, 0.25], [0.0, 1.0, 0.5], [0.0, 0.0, 1.0]])
    calls = []
    monkeypatch.setattr(hardware_manager, "run_calibration_flow", _flow_writing(matrix, calls))

    manager._prepare_perspective_calibration(2)

    assert len(calls) == 1
    assert manager.camera_calibration_source == "FRESH_CALIBRATION"
    assert np.allclose(np.load(manager.perspective_path), matrix)


def test_recalibrate_camera_requires_physical_mode():
    with pytest.raises(SystemExit):
        parse_options(["--recalibrate-camera"])
    options = parse_options(["--physical", "--recalibrate-camera"])
    assert options.recalibrate_camera is True
    config = SimpleNamespace()
    configure_runtime(config, options)
    assert config.RECALIBRATE_CAMERA is True


