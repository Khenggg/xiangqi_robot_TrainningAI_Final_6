"""Game identity and motion/twin contracts, using no real hardware or RPC."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.core.ai_execution import execute_ai_move
from src.core.game_state import GameState
from src.domain.game_move import MoveActor, MoveContext, initial_piece_identities
from src.motion.builder import build_capture_plan, build_move_plan
from src.motion.contracts import GripperCommand, MotionType
from src.motion.executor import MotionExecutor
from src.motion.plan import MotionPlan, MotionStep
from src.motion.result import MotionExecutionResult, PayloadState
from src.motion.stages import MotionStage


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr("src.core.game_state.TuongKyDaiSuClient", lambda *args: MagicMock(room_id=None))
    return GameState()


class FakeBackend:
    """Only in-memory operations: importing/instantiating a controller is unnecessary."""
    def __init__(self, events):
        self.events = events
        self.connected = True
        self.motion_state = "IDLE"
        self.joints = [1, 2, 3, 4, 5, 6]
        self.fail_close = False
        self.fail_open = False

    def is_connected(self):
        return self.connected

    def get_state_snapshot(self):
        return SimpleNamespace(connected=self.connected, motion_state=self.motion_state,
                               last_error=None, joints_valid=True, joints_deg=list(self.joints))

    def move_cartesian(self, pose, speed_factor=None):
        self.events.append(("move", tuple(pose)))
        return True

    def set_gripper(self, closed):
        self.events.append(("command", closed))
        return not (self.fail_close if closed else self.fail_open)


class FakeTwin:
    def __init__(self, events):
        self.events = events
        self.reject_attach = False

    def set_expected_payload(self, piece_id):
        self.events.append(("expected", piece_id))
        return True

    def on_gripper_closed(self, piece_id):
        self.events.append(("attach", piece_id))
        return not self.reject_attach

    def on_gripper_opened(self):
        self.events.append(("release",))
        return True


def move_plan(piece_id="black_cannon_0"):
    return build_move_plan(
        [-300, 0, 100, 180, 0, 0], [-300, 0, 10, 180, 0, 0],
        [-350, 0, 100, 180, 0, 0], [-350, 0, 10, 180, 0, 0],
        metadata={"piece_id": piece_id} if piece_id else {}, settle_time_s=0,
    )


def test_initial_game_ids_match_canonical_layout(state):
    assert state.piece_ids == initial_piece_identities()
    assert len(state.piece_ids) == 32
    context = state.create_move_context((1, 2), (4, 2), MoveActor.ROBOT)
    assert context.piece_id == "black_cannon_0"
    assert context.src == (2, 1)
    assert context.dst == (2, 4)


def test_human_commit_notifies_after_board_and_identity_commit(state):
    commands = []
    backend = FakeBackend(commands)
    received = []

    def observe(context):
        assert state.board[5][0] == "r_P"
        assert state.piece_ids[(5, 0)] == context.piece_id
        assert context.actor is MoveActor.HUMAN
        received.append(context)
        return True

    state.set_move_observer(observe)
    state.process_human_move((0, 6), (0, 5), "r_P")
    assert received[0].piece_id == "red_pawn_0"
    assert received[0].captured_piece_id is None
    assert commands == []
    assert backend.joints == [1, 2, 3, 4, 5, 6]


def test_human_capture_preserves_both_ids_without_motion(state):
    # The observer receives semantics for two bodies; only the world bridge
    # decides their physical poses. This test deliberately has no robot method.
    received = []
    state.set_move_observer(lambda context: received.append(context) or True)
    state.process_human_move((1, 7), (1, 0), "r_C")
    context = received[0]
    assert context.piece_id == "red_cannon_0"
    assert context.captured_piece_id == "black_knight_0"
    assert state.piece_ids[(0, 1)] == "red_cannon_0"
    assert "black_knight_0" not in state.piece_ids.values()
    assert "black_knight_1" in state.piece_ids.values()
    assert state.board[0][1] == "r_C"


def test_human_sync_failure_is_latched_and_blocks_robot(state):
    state.set_move_observer(lambda context: False)
    state.process_human_move((0, 6), (0, 5), "r_P")
    hardware = MagicMock(is_robot_ready=True)
    assert not execute_ai_move(state, hardware, ((1, 2), (4, 2)))
    hardware.execute_piece_move.assert_not_called()
    assert state.board[5][0] == "r_P"  # Human already moved; do not undo reality.
    assert state.move_sync_error


def test_robot_move_passes_pending_identity_then_commits(state):
    state.turn = "b"
    received = []

    def execute_piece_move(*, s_col, s_row, d_col, d_row, is_capture,
                           moving_visual_target, captured_visual_target,
                           piece_id, captured_piece_id, move_context):
        assert state.move_execution_status == "PENDING"
        assert state.board[s_row][s_col] == "b_C"
        assert piece_id == "black_cannon_0"
        assert captured_piece_id is None
        assert move_context.actor is MoveActor.ROBOT
        received.append(move_context)
        return MotionExecutionResult.ok()

    hardware = SimpleNamespace(is_robot_ready=True, execute_piece_move=execute_piece_move)
    assert execute_ai_move(state, hardware, ((1, 2), (4, 2)))
    assert state.piece_ids[(2, 4)] == "black_cannon_0"
    assert (2, 1) not in state.piece_ids
    assert state.last_committed_move == received[0]
    assert state.move_execution_status == "COMMITTED"
    assert state.pending_move is None


def test_robot_failure_preserves_game_and_identity(state):
    state.turn = "b"
    before_board = [row[:] for row in state.board]
    before_ids = dict(state.piece_ids)
    hardware = SimpleNamespace(is_robot_ready=True, execute_piece_move=lambda **kwargs: False)
    assert not execute_ai_move(state, hardware, ((1, 2), (4, 2)))
    assert state.board == before_board
    assert state.piece_ids == before_ids
    assert state.turn == "b"
    assert state.move_execution_status == "FAILED"
    assert state.pending_move.piece_id == "black_cannon_0"


def test_legacy_hardware_signature_still_supported(state):
    state.turn = "b"

    def legacy(s_col, s_row, d_col, d_row, is_capture,
               moving_visual_target=None, captured_visual_target=None):
        return True

    hardware = SimpleNamespace(is_robot_ready=True, move_piece=legacy)
    assert execute_ai_move(state, hardware, ((1, 2), (4, 2)))


def test_undo_restores_identity_and_requires_twin_reconciliation(state):
    received = []
    state.set_move_observer(lambda context: received.append(context) or True)
    state.process_human_move((0, 6), (0, 5), "r_P")
    assert state.undo_round()
    assert state.piece_ids[(6, 0)] == "red_pawn_0"
    assert (5, 0) not in state.piece_ids
    assert state.move_sync_error
    assert len(received) == 1  # Undo must not teleport physical manipulations.


def test_rollback_restores_stable_identity(state):
    state.save_rollback_state()
    state.process_human_move((0, 6), (0, 5), "r_P")
    state.handle_rollback()
    assert state.piece_ids == initial_piece_identities()


def test_close_expected_id_precedes_command_and_attaches_exactly(state):
    events = []
    backend = FakeBackend(events)
    result = MotionExecutor(backend, twin_bridge=FakeTwin(events)).execute_plan(move_plan())
    assert result.success
    index = events.index(("command", True))
    assert events[index - 1] == ("expected", "black_cannon_0")
    assert events[index + 1] == ("attach", "black_cannon_0")
    assert events[events.index(("command", False)) + 1] == ("release",)
    assert result.payload_state == PayloadState.EXPECTED_RELEASED


def test_capture_removes_red_before_grasping_black():
    events = []
    plan = build_capture_plan(
        [10, 0, 100, 180, 0, 0], [10, 0, 10, 180, 0, 0],
        [90, 0, 100, 180, 0, 0], [90, 0, 10, 180, 0, 0],
        [20, 0, 100, 180, 0, 0], [20, 0, 10, 180, 0, 0],
        [10, 0, 100, 180, 0, 0], [10, 0, 10, 180, 0, 0],
        metadata={"captured_piece_id": "red_pawn_0", "attacker_piece_id": "black_rook_0"},
        settle_time_s=0,
    )
    result = MotionExecutor(FakeBackend(events), twin_bridge=FakeTwin(events)).execute_plan(plan)
    assert result.success
    grasp_events = [event for event in events if event[0] in ("expected", "attach", "release")]
    assert grasp_events == [("expected", "red_pawn_0"), ("attach", "red_pawn_0"), ("release",),
                            ("expected", "black_rook_0"), ("attach", "black_rook_0"), ("release",)]
    assert events.index(("move", (90, 0, 10, 180, 0, 0))) < events.index(("expected", "black_rook_0"))


def test_missing_payload_id_rejects_before_any_command():
    events = []
    result = MotionExecutor(FakeBackend(events), twin_bridge=FakeTwin(events)).execute_plan(move_plan(None))
    assert not result.success
    assert events == []


def test_failed_close_cannot_attach_or_continue():
    events = []
    backend = FakeBackend(events)
    backend.fail_close = True
    result = MotionExecutor(backend, twin_bridge=FakeTwin(events)).execute_plan(move_plan())
    assert not result.success
    assert events[-1] == ("command", True)
    assert not any(event[0] == "attach" for event in events)


def test_failed_twin_attachment_prevents_transport():
    events = []
    twin = FakeTwin(events)
    twin.reject_attach = True
    result = MotionExecutor(FakeBackend(events), twin_bridge=twin).execute_plan(move_plan())
    assert not result.success
    assert result.payload_state == PayloadState.EXPECTED_ATTACHED
    assert events[-1] == ("attach", "black_cannon_0")


def test_failed_open_preserves_attachment_semantics():
    events = []
    backend = FakeBackend(events)
    backend.fail_open = True
    result = MotionExecutor(backend, twin_bridge=FakeTwin(events)).execute_plan(move_plan())
    assert not result.success
    assert ("release",) not in events


def test_estop_between_steps_preserves_latest_actual_joints():
    events = []
    backend = FakeBackend(events)

    def interrupt(_seconds):
        backend.joints = [17, 27, 37, 47, 57, 67]
        backend.motion_state = "ERROR"

    plan = MotionPlan("interrupted", "PLACE", (
        MotionStep(1, MotionStage.SETTLE, MotionType.WAIT, wait_duration_s=0.01),
        MotionStep(2, MotionStage.RELEASE, MotionType.GRIPPER, gripper_command=GripperCommand.OPEN),
    ))
    result = MotionExecutor(backend, sleep_fn=interrupt, twin_bridge=FakeTwin(events)).execute_plan(plan)
    assert not result.success
    assert backend.joints == [17, 27, 37, 47, 57, 67]
    assert events == []


def test_move_context_rejects_swapped_or_invalid_cells():
    with pytest.raises(ValueError):
        MoveContext("red_pawn_0", (0, 9), (0, 8), MoveActor.HUMAN)
