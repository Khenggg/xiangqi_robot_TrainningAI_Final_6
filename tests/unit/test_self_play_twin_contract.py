"""Self-play must issue semantic robot moves for either color and fail closed."""

import time
from types import SimpleNamespace
from unittest.mock import Mock

from src.core.game_state import GameState
from src.core.self_play_controller import SelfPlayController, SelfPlayStatus
from src.domain.game_move import MoveActor
from src.motion.result import MotionExecutionResult


def _tick_until(controller, target):
    for _ in range(100):
        controller.tick()
        if controller.status is target:
            return
        time.sleep(0.01)
    raise AssertionError(f"Self-play did not reach {target}: {controller.status}")


def _system():
    state = GameState()
    state.api_client.send_move_update_board = Mock()
    moves = iter([((0, 6), (0, 5)), ((0, 3), (0, 4))])
    execute = Mock(return_value=MotionExecutionResult.ok())
    home = Mock(side_effect=AssertionError("Self-play issued an unrequested home motion"))
    hw = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND="VIRTUAL"), dry_run=True,
                         is_robot_ready=True, ai_ctrl=SimpleNamespace(pick_move=lambda *a, **k: next(moves)),
                         execute_piece_move=execute, robot=SimpleNamespace(go_to_home_chess=home))
    return state, hw, execute, home


def test_both_robot_colors_use_semantic_context_without_human_reconciliation():
    state, hw, execute, home = _system()
    human_observer = Mock(side_effect=AssertionError("Self-play invoked human reconcile"))
    hw.reconcile_human_move = human_observer
    controller = SelfPlayController(state, hw)
    assert controller.start(run_mode="step")
    for expected_actor, expected_piece in [("r", "red_pawn_0"), ("b", "black_pawn_0")]:
        assert state.turn == expected_actor
        assert controller.request_next_move()
        _tick_until(controller, SelfPlayStatus.MOVING)
        _tick_until(controller, SelfPlayStatus.READY)
        context = execute.call_args.kwargs["move_context"]
        assert context.actor is MoveActor.ROBOT
        assert context.piece_id == expected_piece
        assert execute.call_args.kwargs["piece_id"] == expected_piece
        assert state.last_committed_move == context
    human_observer.assert_not_called()
    home.assert_not_called()


def test_identity_failure_prevents_execution_and_commit():
    state, hw, execute, home = _system()
    state.piece_ids.pop((6, 0))
    controller = SelfPlayController(state, hw)
    assert controller.start(run_mode="step")
    assert controller.request_next_move()
    _tick_until(controller, SelfPlayStatus.FAULTED)
    execute.assert_not_called()
    assert state.board[6][0] == "r_P"
    home.assert_not_called()


def test_ending_match_does_not_park_or_fake_a_move():
    state, hw, execute, home = _system()
    controller = SelfPlayController(state, hw)
    assert controller.start(run_mode="step")
    assert controller.request_next_move()
    assert controller.end_match()
    assert controller.status is SelfPlayStatus.ENDED
    execute.assert_not_called()
    home.assert_not_called()
