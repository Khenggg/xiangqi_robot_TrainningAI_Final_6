import numpy as np
import pytest

from src.core import xiangqi
from src.vision.cchess_recognizer import CChessRecognizer, check_recognition_quality
from src.vision.move_observation import derive_move_observation


def successor():
    before = xiangqi.get_board()
    after, _ = xiangqi.make_temp_move(before, ((0, 6), (0, 5)))
    return before, after


def test_camera_rejects_legal_move_with_unrelated_opponent_change():
    before, after = successor()
    after[0][0] = "."
    observation = derive_move_observation(before, after)
    assert not observation.success
    assert observation.status == "BOARD_MISMATCH"


def test_camera_rejects_changed_piece_identity():
    before, after = successor()
    after[5][0] = "r_C"
    assert not derive_move_observation(before, after).success


@pytest.mark.parametrize("confidence", [np.full((10, 9), np.nan), np.ones((9, 9)), np.full((10, 9), 1.1)])
def test_invalid_confidence_cannot_confirm_move(confidence):
    before, after = successor()
    observation = derive_move_observation(before, after, confidence_grid=confidence)
    assert not observation.success
    assert observation.status == "INVALID_CONFIDENCE"


def test_full_recognizer_blocks_nonfinite_corner_before_publication():
    recognizer = CChessRecognizer.__new__(CChessRecognizer)
    corners = np.array([[50., 50.], [550., 50.], [50., 550.], [550., 550.]])
    corners[0, 0] = np.nan
    recognizer.detect_board_corners = lambda frame: (corners, np.ones(4))
    recognizer.extract_rectified_board = lambda frame, points: (frame, None)
    recognizer.recognize_layout = lambda frame: (xiangqi.get_board(), [], np.ones((10, 9)))
    result = recognizer.full_recognize(np.zeros((600, 600, 3), dtype=np.uint8))
    assert not result["success"]


def test_quality_rejects_nonfinite_layout_confidence():
    result = {"success": True, "board": xiangqi.get_board(),
              "corners": [[50., 50.], [550., 50.], [50., 550.], [550., 550.]],
              "corner_scores": np.ones(4), "confidence": np.full((10, 9), np.nan)}
    assert not check_recognition_quality(result, img_shape=(600, 600)).is_valid


def test_physical_confirmation_cannot_fall_back_to_an_occupancy_guess():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from src.core.game_state import GameState
    from src.ui.input_handler import InputHandler
    state = GameState()
    before = [row[:] for row in state.board]
    detector = Mock(_baseline_occ=[[False] * 9 for _ in range(10)], _baseline_time=0.)
    detector.has_baseline.return_value = True
    detector.detect_move.return_value = ((0, 6), (0, 5), "r_P")
    detector.has_new_human_move.return_value = True
    hardware = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND="PHYSICAL"), dry_run=False,
                               yolo_detector=detector, cchess_recognizer=object(),
                               recognize_board_state=lambda frame: {"success": False, "error": "occluded"},
                               clear_yolo_baseline=Mock(),
                               cam_monitor=SimpleNamespace(get_fresh_snapshot=lambda: (np.zeros((600, 600, 3), dtype=np.uint8), [])))
    assert not InputHandler(state, hardware)._handle_space_key()
    assert state.board == before
    assert state.manual_override_active
