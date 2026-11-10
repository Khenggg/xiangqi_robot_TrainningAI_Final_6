from types import SimpleNamespace
from unittest.mock import Mock
import threading

import numpy as np
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


def test_camera_display_closes_on_ui_before_worker_stop(monkeypatch):
    from src.modes.vsc_v3.vision import camera_monitor as module
    camera = module.CameraMonitor.__new__(module.CameraMonitor)
    camera.window_name = 'Camera Monitor'
    camera._display_thread_id = threading.get_ident()
    camera._stop_event = threading.Event()
    camera._thread = camera._detect_thread = None
    capture = camera.cap = Mock()
    destroy_window = Mock()
    monkeypatch.setattr(module.cv2, 'destroyWindow', destroy_window)

    camera.close_display()
    worker = threading.Thread(target=camera.stop)
    worker.start()
    worker.join(2)

    assert not worker.is_alive()
    destroy_window.assert_called_once_with(camera.window_name)
    capture.release.assert_called_once()


def test_unavailable_camera_raises_normal_startup_error(tmp_path, monkeypatch):
    import src.modes.vsc_v3.hardware.hardware_manager as module
    hw = module.HardwareManager.__new__(module.HardwareManager)
    hw.config = SimpleNamespace(CCHESS_RECOGNITION_ENABLED=False, VIDEO_SOURCE=1)
    hw.project_dir = tmp_path
    hw.dry_run = False
    hw.cap = None
    monkeypatch.delenv('VIDEO_INDEX', raising=False)
    monkeypatch.setattr(hw, '_load_vision_models', Mock())
    monkeypatch.setattr(module, 'open_validated_camera', Mock(side_effect=RuntimeError('unavailable')))
    with pytest.raises(RuntimeError, match='camera'):
        hw._init_camera()
    assert [call.args[0] for call in module.open_validated_camera.call_args_list] == [1, 0, 2]


def test_missing_vision_weights_block_physical_startup_before_robot(tmp_path, monkeypatch):
    import src.modes.vsc_v3.hardware.hardware_manager as module
    hw = manager()
    hw.project_dir = tmp_path
    hw._init_ai = Mock()
    hw._init_robot = Mock()
    open_camera = Mock()
    monkeypatch.setattr(module, 'open_validated_camera', open_camera)

    with pytest.raises(RuntimeError, match=r'Missing model files: .*best\.pt.*pose_4_v6\.onnx.*layout_nano_v3\.onnx'):
        hw.initialize_all()

    open_camera.assert_not_called()
    hw._init_robot.assert_not_called()


@pytest.mark.parametrize('manual_only, camera_index', [(False, 1), (True, 1), (False, 0)])
def test_physical_camera_starts_monitor_after_required_calibration(
        tmp_path, monkeypatch, manual_only, camera_index):
    import src.modes.vsc_v3.hardware.hardware_manager as module
    hw = module.HardwareManager(
        SimpleNamespace(DRY_RUN=False, VIDEO_SOURCE=1, CAMERA_CALIBRATION_MANUAL_ONLY=manual_only,
                        VISUAL_BOARD_SYNC_REQUIRED=False),
        tmp_path)
    saved_matrix = np.eye(3)
    np.save(hw.perspective_path, saved_matrix)
    hw.model, hw.cchess_recognizer = Mock(), Mock()
    monkeypatch.setattr(hw, '_load_vision_models', Mock())
    monkeypatch.delenv('VIDEO_INDEX', raising=False)
    cap, monitor = Mock(), Mock()

    def open_camera(index, **kwargs):
        if index != camera_index:
            raise RuntimeError('unavailable')
        return cap

    monkeypatch.setattr(module, 'open_validated_camera', open_camera)
    flow = Mock(return_value=saved_matrix)
    monkeypatch.setattr(module, 'run_calibration_flow', flow)
    camera_monitor = Mock(return_value=monitor)
    monkeypatch.setattr(module, 'CameraMonitor', camera_monitor)

    hw._init_camera()

    flow.assert_called_once_with(cap, str(hw.perspective_path), cchess_recognizer=hw.cchess_recognizer,
                                 cancel_event=None, capture_owner=hw, manual_only=manual_only, dry_run=False)
    assert hw.actual_camera_index == camera_index
    camera_monitor.assert_called_once_with(cap, model=hw.model, perspective_path=hw.perspective_path,
                                           cchess_recognizer=hw.cchess_recognizer)
    monitor.start.assert_called_once()


def test_cancelled_recalibration_does_not_accept_saved_matrix(tmp_path, monkeypatch):
    import src.modes.vsc_v3.hardware.hardware_manager as module
    hw = manager()
    hw.config = SimpleNamespace()
    hw.perspective_path = tmp_path / 'perspective.npy'
    hw.cchess_recognizer = Mock()
    np.save(hw.perspective_path, np.eye(3))
    monkeypatch.setattr(module, 'run_calibration_flow', Mock(return_value=None))

    with pytest.raises(RuntimeError, match='Fresh camera calibration'):
        hw._prepare_perspective_calibration()

    np.testing.assert_array_equal(np.load(hw.perspective_path), np.eye(3))
