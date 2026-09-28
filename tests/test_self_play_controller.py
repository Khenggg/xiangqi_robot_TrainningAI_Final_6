# =============================================================================
# === FILE: tests/test_self_play_controller.py ===
# =============================================================================
import time
from unittest.mock import MagicMock
import pytest

from src.core.game_state import GameState
from src.core.self_play_controller import SelfPlayController, SelfPlayStatus
from src.hardware.robot_VIP import MotionResult, MotionStage


class DummyAIController:
    def __init__(self, moves=None):
        self.moves = moves or [((1, 7), (4, 7))]
        self._idx = 0

    def pick_move(self, board, color="b", difficulty=None):
        if self._idx < len(self.moves):
            mv = self.moves[self._idx]
            self._idx += 1
            return mv
        return ((1, 7), (4, 7))


class DummyHardwareManager:
    def __init__(self):
        self.dry_run = True
        self.is_robot_ready = True
        self.config = MagicMock()
        self.config.ROBOT_BACKEND = "VIRTUAL"
        self.ai_ctrl = DummyAIController()
        self.robot = MagicMock()
        self.robot.connected = True
        self.execute_piece_move = MagicMock(return_value=MotionResult(True, MotionStage.COMPLETED))
        self.reconcile_human_move = MagicMock()


def test_self_play_lifecycle_step_mode():
    state = GameState(allow_mouse_move=True)
    hw = DummyHardwareManager()
    # Canonical initial opening move for Red cannon: (1, 7) -> (4, 7) [Pháo 2 bình 5]
    hw.ai_ctrl = DummyAIController(moves=[((1, 7), (4, 7))])

    ctrl = SelfPlayController(state, hw)
    assert ctrl.status == SelfPlayStatus.IDLE

    # 1. Start self-play
    ok = ctrl.start(red_difficulty="medium", black_difficulty="medium", run_mode="step")
    assert ok is True
    assert ctrl.status == SelfPlayStatus.READY
    assert ctrl.accepts_next is True
    assert ctrl.human_input_disabled is True

    # 2. Request next move
    req = ctrl.request_next_move()
    assert req is True
    assert ctrl.status == SelfPlayStatus.THINKING

    # Wait for thinking thread to complete
    for _ in range(50):
        if ctrl._thread is None or not ctrl._thread.is_alive():
            break
        time.sleep(0.02)

    # 3. Tick: processes thinking -> sets pending move -> starts moving thread
    ctrl.tick()
    assert ctrl.status == SelfPlayStatus.MOVING
    assert state.pending_move is not None

    # Wait for moving thread to complete
    for _ in range(50):
        if ctrl._thread is None or not ctrl._thread.is_alive():
            break
        time.sleep(0.02)

    # 4. Tick: processes moving -> commits pending move -> status READY
    ctrl.tick()
    assert ctrl.status == SelfPlayStatus.READY
    assert state.pending_move is None
    assert state.turn == "b"  # Turn flipped to black
    assert hw.execute_piece_move.called


def test_self_play_end_match():
    state = GameState(allow_mouse_move=True)
    hw = DummyHardwareManager()
    ctrl = SelfPlayController(state, hw)

    ctrl.start(run_mode="step")
    assert ctrl.active is True

    ended = ctrl.end_match()
    assert ended is True
    assert ctrl.status == SelfPlayStatus.ENDED
    assert ctrl.active is False


def test_self_play_motion_failure_transitions_to_fault():
    state = GameState(allow_mouse_move=True)
    hw = DummyHardwareManager()
    hw.execute_piece_move = MagicMock(return_value=MotionResult(False, MotionStage.PICK_MOVING))
    hw.ai_ctrl = DummyAIController(moves=[((1, 7), (4, 7))])

    ctrl = SelfPlayController(state, hw)
    ctrl.start(run_mode="step")
    ctrl.request_next_move()

    for _ in range(50):
        if ctrl._thread is None or not ctrl._thread.is_alive():
            break
        time.sleep(0.02)

    ctrl.tick()  # Transition to MOVING

    for _ in range(50):
        if ctrl._thread is None or not ctrl._thread.is_alive():
            break
        time.sleep(0.02)

    ctrl.tick()  # Motion failed -> FAULTED
    assert ctrl.status == SelfPlayStatus.FAULTED
    assert state.physical_sync_fault is True
