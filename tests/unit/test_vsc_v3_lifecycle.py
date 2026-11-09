from types import SimpleNamespace
from unittest.mock import Mock
import threading

import pytest


def manager():
    from src.modes.vsc_v3.hardware.hardware_manager import HardwareManager
    hw = HardwareManager.__new__(HardwareManager)
    hw.dry_run = False
    hw.cap = Mock()
    hw.cam_monitor = Mock()
    hw.robot = SimpleNamespace(connected=True, deactivate_physical_control=Mock(), robot=Mock())
    return hw


def test_reader_failure_retains_capture_and_sdk_then_retry_closes_once():
    hw = manager()
    cap, rpc = hw.cap, hw.robot.robot
    hw.cam_monitor.stop.side_effect = RuntimeError('reader alive')
    with pytest.raises(RuntimeError, match='reader alive'):
        hw.cleanup()
    cap.release.assert_not_called()
    rpc.CloseRPC.assert_not_called()
    hw.cam_monitor.stop.side_effect = None
    hw.cleanup()
    hw.cleanup()
    rpc.CloseRPC.assert_called_once()
    assert hw.cap is None and hw.cam_monitor is None and not hw.robot.connected


def test_sdk_close_failure_retains_owner_for_explicit_retry():
    hw = manager()
    hw.robot.robot.CloseRPC.side_effect = RuntimeError('receiver alive')
    with pytest.raises(RuntimeError, match='receiver alive'):
        hw.cleanup()
    assert hw.robot.connected
    hw.robot.robot.CloseRPC.side_effect = None
    hw.cleanup()
    assert not hw.robot.connected


def test_camera_stop_does_not_release_capture_under_active_reader():
    from src.modes.vsc_v3.vision.camera_monitor import CameraMonitor
    camera = CameraMonitor.__new__(CameraMonitor)
    camera._stop_event = threading.Event()
    camera._thread = Mock(is_alive=Mock(return_value=True))
    camera._detect_thread = None
    camera.cap = Mock()
    with pytest.raises(RuntimeError, match='reader still running'):
        camera.stop()
    assert camera._stop_event.is_set()
    camera.cap.release.assert_not_called()


def test_unavailable_camera_raises_normal_startup_error(tmp_path, monkeypatch):
    import src.modes.vsc_v3.hardware.hardware_manager as module
    hw = module.HardwareManager.__new__(module.HardwareManager)
    hw.config = SimpleNamespace(CCHESS_RECOGNITION_ENABLED=False, VIDEO_SOURCE=1)
    hw.project_dir = tmp_path
    hw.dry_run = False
    hw.cap = None
    monkeypatch.delenv('VIDEO_INDEX', raising=False)
    monkeypatch.setattr(module, 'YOLO', None)
    monkeypatch.setattr(module, 'open_camera', Mock(side_effect=RuntimeError('unavailable')))
    with pytest.raises(RuntimeError, match='camera'):
        hw._init_camera()
