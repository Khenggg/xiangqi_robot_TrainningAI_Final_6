"""A-04/A-05: committed game truth survives optional projection failures."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import config
from src.core.game_state import GameState
from src.core import xiangqi
from src.domain.game_move import MoveActor
from src.motion.result import MotionExecutionResult


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(room_id=None))
    monkeypatch.setattr(config, 'GAME_MODE', 'HUMAN_VS_ROBOT')
    return GameState()


@pytest.mark.parametrize('failure', [False, RuntimeError('viewer unavailable')])
def test_human_commit_retains_turn_and_success_when_viewer_fails(state, failure):
    observer = Mock(return_value=failure if failure is False else True,
                    side_effect=failure if isinstance(failure, Exception) else None)
    state.set_board_observer(observer)
    assert state.process_human_move((0,6),(0,5),'r_P')
    assert state.turn == 'b' and state.board[5][0] == 'r_P'
    assert len(state.move_history) == 1
    assert not state.physical_sync_fault and state.move_sync_error is None
    assert state.projection_error
    assert state.last_commit_result.committed and state.last_commit_result.projection_pending
    state.api_client.send_move_update_board.assert_called_once()


def test_robot_commit_exposes_projection_pending_without_physical_fault(state):
    state.turn = 'b'
    move = ((0,3),(0,4))
    context = state.create_move_context(*move, MoveActor.ROBOT)
    state.mark_move_pending(context)
    after, _ = xiangqi.make_temp_move(state.board, move)
    state.set_pending_physical_move(move, after, '.', 'b')
    state.set_board_observer(Mock(return_value=False))
    assert state.commit_pending_physical_move()
    assert state.last_commit_result.move_id == context.move_id
    assert state.last_commit_result.committed and state.last_commit_result.projection_pending
    assert not state.physical_sync_fault and not state.move_sync_error
    assert not state.commit_pending_physical_move()
    assert len(state.move_history) == 1


def king_capture(state):
    board = [['.']*9 for _ in range(10)]
    board[0][4], board[9][4], board[1][4] = 'b_K', 'r_K', 'r_R'
    state.board, state.turn = board, 'r'
    state.piece_ids = {(0,4):'black_king_0',(9,4):'red_king_0',(1,4):'red_rook_0'}
    state.set_board_observer(Mock(return_value=False))
    return ((4,1),(4,0))


def test_terminal_human_commit_is_processed_despite_mirror_failure(state):
    move = king_capture(state)
    assert state.process_human_move(*move,'r_R')
    assert state.game_over and state.winner == 'r'
    state.api_client.end_match.assert_called_once_with(winner='RED',reason='CHECKMATE')

