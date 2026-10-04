from types import SimpleNamespace
from unittest.mock import Mock
from src.core.game_state import GameState
from src.core.ai_execution import execute_ai_move
from src.motion.result import MotionExecutionResult, MotionFailureCategory
from src.motion.stages import MotionStage


def hardware(result, verifier=True, virtual=False):
    return SimpleNamespace(is_robot_ready=True, simulation_runtime=object() if virtual else None,
                           execute_piece_move=Mock(return_value=result),
                           verify_physical_board=Mock(return_value=verifier))


def test_successful_camera_verified_move_keeps_twin_ids_and_visual_move_log():
    state = GameState(); state.turn = "b"
    observer = Mock(return_value=True); state.set_board_observer(observer)
    hw = hardware(MotionExecutionResult.ok())
    assert execute_ai_move(state, hw, ((0, 3), (0, 4)))
    assert state.board[4][0] == "b_P"
    assert state.piece_ids[(4, 0)] == "black_pawn_0"
    assert (3, 0) not in state.piece_ids
    assert state.move_log[-1]["turn"] == "b"
    observer.assert_called_once_with(state.piece_ids)


def test_failed_motion_does_not_commit_or_sync():
    state = GameState(); state.turn = "b"
    before = [row[:] for row in state.board]
    observer = Mock(return_value=True); state.set_board_observer(observer)
    hw = hardware(MotionExecutionResult.fail(MotionStage.LAND, MotionFailureCategory.MOTION_COMMAND_FAILED, "112"))
    assert not execute_ai_move(state, hw, ((0, 3), (0, 4)))
    assert state.board == before and state.turn == "b"
    observer.assert_not_called(); hw.verify_physical_board.assert_called_once_with(before)


def test_reset_during_camera_verification_cannot_commit_old_move():
    state = GameState(); state.turn = "b"
    hw = hardware(MotionExecutionResult.ok())
    def reset(_):
        state.game_epoch += 1
        return True
    hw.verify_physical_board.side_effect = reset
    before = [row[:] for row in state.board]
    assert not execute_ai_move(state, hw, ((0, 3), (0, 4)))
    assert state.board == before and state.physical_sync_fault


def test_human_move_syncs_actual_committed_piece_not_robot_command():
    state = GameState(); state.api_client.send_move_update_board = Mock()
    observer = Mock(return_value=True); state.set_board_observer(observer)
    state.process_human_move((0, 6), (0, 5), "r_P")
    assert state.piece_ids[(5, 0)] == "red_pawn_0"
    observer.assert_called_once_with(state.piece_ids)
