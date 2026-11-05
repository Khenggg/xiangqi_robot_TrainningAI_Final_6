"""BRD A-01/A-06/A-07: verify actual expected board, independent model results."""
import time
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import config
from src.core import xiangqi
from src.hardware.hardware_manager import HardwareManager
from src.vision.camera_monitor import CameraMonitor


@pytest.mark.parametrize("kind", ["wrong_board", "bad_quality", "malformed"])
def test_physical_verification_never_accepts_camera_health_as_board_truth(kind):
    board = xiangqi.get_board()
    seen = [row[:] for row in board]
    quality = True
    if kind == "wrong_board":
        seen[5][0], seen[6][0] = seen[6][0], "."
    elif kind == "bad_quality":
        quality = False
    else:
        seen = [["."] for _ in range(10)]
    cfg = SimpleNamespace(VISUAL_BOARD_SYNC_REQUIRED=False,
                          VISUAL_PICK_SAMPLE_COUNT=3, VISUAL_PICK_MIN_STABLE_SAMPLES=2)
    hw = SimpleNamespace(config=cfg, camera_calibration_ready=True,
        cam_monitor=SimpleNamespace(get_fresh_snapshot=Mock(return_value=(object(), []))),
        recognize_board_state=Mock(return_value={"success": True, "quality_ok": quality, "board": seen}))
    assert not HardwareManager.verify_physical_board(hw, board)


def model_camera(tmp_path, *, yolo_fails=False, cchess_fails=False):
    matrix = tmp_path / "perspective.npy"
    np.save(matrix, np.eye(3))
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    capture = SimpleNamespace(isOpened=lambda: True, grab=lambda: True, read=lambda: (True, frame.copy()))
    board = xiangqi.get_board()
    layout = Mock(return_value=(board, board, np.full((10, 9), .99)))
    if cchess_fails:
        layout.side_effect = RuntimeError("CChess unavailable")
    recognizer = SimpleNamespace(extract_rectified_board=lambda f, k: (f, None), recognize_layout=layout)
    predict = Mock(return_value=[SimpleNamespace(boxes=[])])
    if yolo_fails:
        predict.side_effect = RuntimeError("YOLO unavailable")
    monitor = CameraMonitor(capture, model=SimpleNamespace(predict=predict),
        perspective_path=matrix, cchess_recognizer=recognizer, device_preference="cpu")
    return monitor, layout


def test_yolo_failure_keeps_successful_cchess_for_board_verification(tmp_path):
    monitor, layout = model_camera(tmp_path, yolo_fails=True)
    frame, _ = monitor.get_fresh_snapshot()
    assert frame is not None
    assert monitor.get_latest_cchess_result()["board"] == xiangqi.get_board()
    assert monitor.get_health()["cchess_ready"]
    assert not monitor.get_health()["yolo_ready"]
    with pytest.raises(Exception, match="best.pt inference failed"):
        monitor.get_fresh_pick_snapshot()  # Board evidence must not masquerade as a grip target.


def test_cchess_failure_preserves_successful_yolo_capability(tmp_path):
    monitor, _ = model_camera(tmp_path, cchess_fails=True)
    frame, boxes = monitor.get_fresh_snapshot()
    assert frame is not None and boxes == []
    assert monitor.get_latest_cchess_result() is None
    assert monitor.get_health()["yolo_ready"]
    assert not monitor.get_health()["cchess_ready"]


def test_actual_camera_verifier_reuses_layout_from_each_fresh_frame(tmp_path):
    monitor, layout = model_camera(tmp_path)
    cfg = SimpleNamespace(VISUAL_BOARD_SYNC_REQUIRED=False, VISUAL_PICK_SAMPLE_COUNT=3,
                          VISUAL_PICK_MIN_STABLE_SAMPLES=2)
    hw = SimpleNamespace(config=cfg, camera_calibration_ready=True, cam_monitor=monitor,
                         recognize_board_state=Mock(side_effect=AssertionError("Repeated CChess inference")))
    assert HardwareManager.verify_physical_board(hw, xiangqi.get_board())
    assert layout.call_count == 2
    hw.recognize_board_state.assert_not_called()


def test_same_observation_cannot_count_twice_for_physical_commit():
    board = xiangqi.get_board()
    observation = (time.monotonic(), object(), [], {"success": True, "quality_ok": True, "board": board})
    camera = SimpleNamespace(get_fresh_observation=lambda: observation,
                             get_fresh_snapshot=Mock(return_value=(object(), [])))
    hw = SimpleNamespace(camera_calibration_ready=True, cam_monitor=camera,
        config=SimpleNamespace(VISUAL_BOARD_SYNC_REQUIRED=True, VISUAL_PICK_SAMPLE_COUNT=3),
        recognize_board_state=Mock(return_value=observation[3]))
    assert not HardwareManager.verify_physical_board(hw, board)
