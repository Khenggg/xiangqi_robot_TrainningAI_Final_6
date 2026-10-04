"""A successful robot command alone cannot advance the real-board game."""

from types import SimpleNamespace
from unittest.mock import Mock

from src.core.ai_execution import execute_ai_move
from src.core import xiangqi
from src.core.game_state import GameState
from src.hardware.hardware_manager import HardwareManager
from src.motion.result import MotionExecutionResult


def test_live_robot_success_without_camera_confirmation_does_not_commit():
    state = GameState()
    state.turn = "b"
    state.api_client.send_move_update_board = Mock()
    before = [row[:] for row in state.board]
    execute = Mock(return_value=MotionExecutionResult.ok())
    hw = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND="PHYSICAL"), dry_run=False,
                         is_robot_ready=True, execute_piece_move=execute,
                         verify_physical_board=Mock(side_effect=[True, False]))

    assert not execute_ai_move(state, hw, ((0, 3), (0, 4)), dry_run=False)
    assert execute.call_args.kwargs["move_context"].piece_id == "black_pawn_0"
    assert state.board == before
    assert state.turn == "b"
    assert state.physical_sync_fault
    assert state.move_sync_error
    state.api_client.send_move_update_board.assert_not_called()


def test_physical_board_verifier_requires_two_fresh_quality_approved_frames():
    expected = xiangqi.get_board()
    wrong = [row[:] for row in expected]
    wrong[6][0], wrong[5][0] = ".", "r_P"
    snapshots = Mock(side_effect=[(object(), []), (object(), [])])
    observed = iter([{"success": True, "quality_ok": True, "board": expected},
                     {"success": True, "quality_ok": True, "board": wrong}])
    hw = SimpleNamespace(camera_calibration_ready=True, cam_monitor=SimpleNamespace(get_fresh_snapshot=snapshots),
                         cchess_recognizer=object(), recognize_board_state=lambda frame: next(observed))
    assert not HardwareManager.verify_physical_board(hw, expected)
    assert snapshots.call_count == 2


def test_physical_board_verifier_accepts_two_fresh_frames_but_never_stale_calibration():
    expected = xiangqi.get_board()
    snapshots = Mock(return_value=(object(), []))
    recognize = Mock(return_value={"success": True, "quality_ok": True, "board": expected})
    hw = SimpleNamespace(camera_calibration_ready=False, cam_monitor=SimpleNamespace(get_fresh_snapshot=snapshots),
                         recognize_board_state=recognize)
    assert not HardwareManager.verify_physical_board(hw, expected)
    snapshots.assert_not_called()
    hw.camera_calibration_ready = True
    assert HardwareManager.verify_physical_board(hw, expected)
    assert snapshots.call_count == 2
