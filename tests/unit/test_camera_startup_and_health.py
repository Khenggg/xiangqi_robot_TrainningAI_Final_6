from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import time
import numpy as np
import pytest
from src.vision.camera_startup import open_validated_camera, validate_perspective
from src.vision.camera_monitor import CameraMonitor


def test_partial_startup_failure_cleans_resources_before_reraising():
    from src.hardware.hardware_manager import HardwareManager
    manager = HardwareManager.__new__(HardwareManager)
    events = []
    manager._init_ai = lambda: events.append("engine")
    manager._init_robot = lambda: events.append("simulation")
    def camera_failure():
        raise RuntimeError("fresh camera unavailable")
    manager._init_camera = camera_failure
    manager.cleanup = lambda: events.append("cleanup")
    with pytest.raises(RuntimeError, match="fresh camera unavailable"):
        manager.initialize_all()
    assert events == ["engine", "simulation", "cleanup"]


class Capture:
    def __init__(self, frame=None):
        self.frame = frame
        self.released = False
    def isOpened(self): return True
    def set(self, *args): pass
    def read(self): return self.frame is not None, self.frame
    def release(self): self.released = True
    def grab(self): return True


def test_explicit_camera_no_substitution_and_invalid_frame_released():
    cap = Capture()
    selected = []
    def factory(index, backend):
        selected.append(index)
        return cap
    with pytest.raises(RuntimeError, match="VIDEO_INDEX=7"):
        open_validated_camera(7, attempts=1, capture_factory=factory)
    assert selected == [7]
    assert cap.released


def test_camera_requires_valid_bgr_frame():
    frame = np.zeros((4, 5, 3), dtype=np.uint8)
    cap = Capture(frame)
    assert open_validated_camera(2, attempts=1, capture_factory=lambda *args: cap) is cap
    assert not cap.released
    assert validate_perspective(np.eye(3))
    assert not validate_perspective(np.zeros((3, 3)))
    assert not validate_perspective(np.full((3, 3), np.nan))


@pytest.mark.parametrize("working, expected", [(1, [1]), (0, [1, 0]), (2, [1, 0, 2]), (None, [1, 0, 2])])
def test_manager_camera_fallback_tracks_actual_device(tmp_path, monkeypatch, working, expected):
    import src.hardware.hardware_manager as hw
    import src.vision.camera_startup as startup
    manager = hw.HardwareManager.__new__(hw.HardwareManager)
    manager.config = SimpleNamespace(CCHESS_RECOGNITION_ENABLED=False, VIDEO_SOURCE=1)
    manager.project_dir = tmp_path
    manager.dry_run = False
    manager.profile = None
    manager.cap = None
    manager.model = manager.cchess_recognizer = None
    cap = Capture(np.zeros((3, 3, 3), dtype=np.uint8))
    attempted, calibrated = [], []

    def open_device(index):
        attempted.append(index)
        if index != working:
            raise RuntimeError("device unavailable")
        return cap

    def calibrate(index):
        calibrated.append(index)
        # Stop before model setup; a calibration failure must not try another camera.
        raise RuntimeError("calibration rejected")

    monkeypatch.delenv("VIDEO_INDEX", raising=False)
    monkeypatch.setattr(hw, "YOLO", None)
    monkeypatch.setattr(startup, "open_validated_camera", open_device)
    manager._prepare_perspective_calibration = calibrate
    reason = "any camera" if working is None else "calibration rejected"
    with pytest.raises(RuntimeError, match=reason):
        manager._init_camera()
    assert attempted == expected
    assert calibrated == ([] if working is None else [working])
    assert manager.cap is None
    if working is not None:
        assert manager.camera_selected_index == manager.actual_camera_index == working
        assert cap.released


class Model:
    def __init__(self): self.fail = False; self.frame = None
    def predict(self, frame, **kwargs):
        if self.fail: raise RuntimeError("model unavailable")
        self.frame = frame.copy()
        return [SimpleNamespace(boxes=[])]


class Recognizer:
    fail = False
    def extract_rectified_board(self, frame, points): return frame, None
    def recognize_layout(self, frame):
        if self.fail: raise RuntimeError("layout failed")
        board = [["."] * 9 for _ in range(10)]
        return board, board, np.ones((10, 9))


def monitor(tmp_path, model=None, recognizer=None):
    path = tmp_path / "matrix.npy"
    np.save(path, np.eye(3))
    return CameraMonitor(Capture(), model=model, cchess_recognizer=recognizer, perspective_path=path)


def test_yolo_keeps_bgr_and_failed_empty_result_cannot_mean_clear(tmp_path):
    model = Model()
    camera = monitor(tmp_path, model)
    frame = np.full((4, 5, 3), [11, 22, 99], dtype=np.uint8)
    assert camera._infer_frame(frame) == []
    np.testing.assert_array_equal(model.frame, frame)
    assert camera.get_health()["ready"]
    model.fail = True
    camera.cap = Capture(frame)
    assert camera.get_fresh_snapshot() == (None, [])
    assert not camera.get_health()["ready"]
    assert "model unavailable" in camera.get_health()["error"]


def test_cchess_success_invalidated_on_failure_and_age(tmp_path):
    recognizer = Recognizer()
    camera = monitor(tmp_path, recognizer=recognizer)
    frame = np.zeros((4, 5, 3), dtype=np.uint8)
    camera._infer_frame(frame)
    assert camera.get_latest_cchess_result()["success"]
    camera._last_inference_at = time.monotonic() - 3
    assert camera.get_latest_cchess_result() is None
    camera._infer_frame(frame)
    recognizer.fail = True
    assert camera._infer_frame(frame) is None
    assert camera.get_latest_cchess_result() is None
    assert camera.get_latest_frame_and_detections() == (None, [])


def test_cchess_only_does_not_fabricate_measured_pick_boxes(tmp_path):
    camera = monitor(tmp_path, recognizer=Recognizer())
    assert camera._infer_frame(np.zeros((4, 5, 3), dtype=np.uint8)) == []
    assert camera.get_latest_cchess_result()["success"]


def test_failed_fresh_calibration_rejects_existing_saved_matrix(tmp_path, monkeypatch):
    import src.hardware.hardware_manager as hw
    import src.vision.camera_startup as startup
    cap = Capture(np.zeros((3, 3, 3), dtype=np.uint8))
    path = tmp_path / "perspective.npy"
    np.save(path, np.eye(3))
    manager = hw.HardwareManager.__new__(hw.HardwareManager)
    manager.config = SimpleNamespace(CCHESS_RECOGNITION_ENABLED=False, VIDEO_SOURCE=7,
                                     RECALIBRATE_CAMERA=True)
    manager.project_dir = tmp_path
    manager.dry_run = False
    manager.profile = None
    manager.cap = None
    manager.model = None
    manager.cchess_recognizer = None
    manager.perspective_path = path
    monkeypatch.setattr(hw, "YOLO", None)
    monkeypatch.setattr(startup, "open_validated_camera", lambda index: cap)
    monkeypatch.setattr(hw, "run_calibration_flow", lambda *args, **kwargs: None)
    with pytest.raises(RuntimeError, match="Fresh camera calibration failed/cancelled"):
        manager._init_camera()
    assert not manager.camera_calibration_ready
    assert manager.cap is None
    assert cap.released
    np.testing.assert_array_equal(np.load(path), np.eye(3))


def test_restore_drops_only_pre_dispatch_homechess_ai_failure():
    from src.core.game_state import GameState
    state = GameState()
    state.pending_ai_move = {"move": ((0, 3), (0, 4))}
    state.pending_move = object()
    state.pending_execution_binding = {"move_id": "stale"}
    state.move_sync_error = "HOMECHESS: tool/user frame differs from R1-R4 or metadata is missing"
    state.move_execution_error = state.move_sync_error
    state.move_execution_status = "FAILED"
    assert state._discard_pre_dispatch_ai_failure("RECOVERY_REQUIRED")
    assert state.pending_ai_move is None and state.pending_move is None
    assert state.pending_execution_binding is None
    assert state.move_sync_error is None and state.move_execution_error is None
    assert state.move_execution_status == "IDLE"


def test_restore_keeps_other_failed_ai_transactions_locked():
    from src.core.game_state import GameState
    state = GameState()
    state.pending_ai_move = {"move": ((0, 3), (0, 4))}
    state.move_sync_error = "robot command failed after dispatch"
    assert not state._discard_pre_dispatch_ai_failure("RECOVERY_REQUIRED")
    assert state.pending_ai_move is not None
    assert state.move_sync_error


def test_clear_failed_session_verifies_board_then_unlocks_without_restart():
    from src.ui.input_handler import InputHandler
    state = SimpleNamespace(
        move_sync_error="HOMECHESS frame mismatch",
        physical_sync_fault=True,
        pending_ai_move={"move": ((0, 3), (0, 4))},
        board=[["."] * 9 for _ in range(10)],
        snapshot_continue_required=True,
        snapshot_continue_can_commit_pending=True,
        manual_override_active=True,
        emergency_mode=True,
        turn_confirmation_required=False,
        board_revision=7,
        clear_pending_ai_move=Mock(),
        clear_move_sync_error=Mock(),
        sync_current_board=Mock(),
        persist_checkpoint=Mock(),
        approve_recovery_after_verification=Mock(return_value=True),
        set_status=Mock(),
    )
    hw = SimpleNamespace(
        config=SimpleNamespace(ROBOT_BACKEND="PHYSICAL", DRY_RUN=False),
        dry_run=False,
        verify_physical_board=Mock(return_value=True),
        motion_worker=None,
    )
    handler = InputHandler(state, hw)
    handler.resume_automatic_scanning = Mock(return_value=True)

    assert handler._clear_failed_session()
    state.clear_pending_ai_move.assert_called_once()
    state.clear_move_sync_error.assert_called_once()
    state.sync_current_board.assert_called_once()
    assert not state.physical_sync_fault
    assert not state.manual_override_active
    assert not state.snapshot_continue_required


def test_clear_failed_session_refuses_when_board_does_not_match_fen():
    from src.ui.input_handler import InputHandler
    state = SimpleNamespace(
        move_sync_error="HOMECHESS frame mismatch",
        physical_sync_fault=True,
        pending_ai_move={"move": ((0, 3), (0, 4))},
        board=[["."] * 9 for _ in range(10)],
        snapshot_continue_required=True,
        manual_override_active=True,
        clear_pending_ai_move=Mock(),
        clear_move_sync_error=Mock(),
        approve_recovery_after_verification=Mock(return_value=True),
        set_status=Mock(),
    )
    hw = SimpleNamespace(
        config=SimpleNamespace(ROBOT_BACKEND="PHYSICAL", DRY_RUN=False),
        dry_run=False,
        verify_physical_board=Mock(return_value=False),
        motion_worker=None,
    )
    handler = InputHandler(state, hw)
    handler.resume_automatic_scanning = Mock(return_value=True)

    assert not handler._clear_failed_session()
    state.clear_pending_ai_move.assert_not_called()
    state.clear_move_sync_error.assert_not_called()
    assert state.physical_sync_fault
    assert state.manual_override_active


def test_old_background_sample_cannot_replace_new_snapshot(tmp_path):
    model = Model()
    camera = monitor(tmp_path, model=model)
    frame = np.zeros((4, 5, 3), dtype=np.uint8)
    old_time = time.monotonic() - 0.3
    assert camera._infer_frame(frame) == []
    newer_time = camera._last_inference_at
    assert camera._infer_frame(frame, old_time) is None
    assert camera._last_inference_at == newer_time
    assert camera.get_health()["ready"]


def test_continue_cannot_commit_unverified_pending_robot_move():
    from src.ui.input_handler import InputHandler
    from unittest.mock import Mock
    pending = {"move": ((0, 3), (0, 4)), "captured_piece": ".", "expected_board": [["."] * 9 for _ in range(10)]}
    state = SimpleNamespace(physical_sync_fault=True, snapshot_continue_can_commit_pending=True,
                            pending_ai_move=pending, board=[["r_K"] * 9 for _ in range(10)],
                            commit_pending_ai_move=Mock(), set_status=Mock())
    hw = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND="PHYSICAL", DRY_RUN=False), dry_run=False,
                         verify_physical_board=Mock(return_value=False))
    InputHandler(state, hw)._continue_after_snapshot_pause()
    state.commit_pending_ai_move.assert_not_called()
    assert state.physical_sync_fault
    assert state.pending_ai_move is pending


def test_old_board_confirmation_does_not_automatically_retry_physical_robot():
    from src.ui.input_handler import InputHandler
    from unittest.mock import Mock
    state = SimpleNamespace(physical_sync_fault=True, snapshot_continue_required=True,
                            pending_ai_move={"move": ((0, 3), (0, 4))}, board=[["."] * 9 for _ in range(10)],
                            clear_pending_ai_move=Mock(), prepare_ai_retry_after_physical_miss=Mock(), set_status=Mock())
    hw = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND="PHYSICAL", DRY_RUN=False), dry_run=False,
                         verify_physical_board=Mock(return_value=True))
    InputHandler(state, hw)._reconcile_physical_sync_fault()
    state.prepare_ai_retry_after_physical_miss.assert_not_called()
    assert state.manual_override_active
    assert state.physical_sync_fault
