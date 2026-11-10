"""Durable transitions between actual user actions; no camera or FR3 access."""
import pytest
import config
from src.core.game_state import GameState
from src.domain.game_move import MoveActor
from src.core import xiangqi
from src.core.session_journal import dumps, decode
import json
import numpy as np
import threading
from types import SimpleNamespace
from unittest.mock import Mock
from src.motion.result import MotionExecutionResult
from src.core.motion_worker import MotionWorker
from src.ui.input_handler import InputHandler
from src.hardware.hardware_manager import HardwareManager
from src.hardware.telemetry_publisher import TelemetryPublisher
import time


def test_execution_binding_numeric_scalars_survive_durable_roundtrip():
    binding = {'origin': (np.float64(.42), np.float32(-.02)), 'revision': np.int64(3)}
    restored = decode(json.loads(dumps(binding)))
    assert restored == binding
    assert all(type(value) is float for value in restored['origin'])
    assert type(restored['revision']) is int


def test_nonfinite_binding_remains_rejected():
    with pytest.raises(ValueError):
        dumps({'offset': np.float64(float('nan'))})


def test_virtual_ui_operation_uses_worker_instead_of_blocking_event_loop():
    handler = InputHandler.__new__(InputHandler)
    handler.state = SimpleNamespace(set_status=Mock())
    handler.hw = SimpleNamespace(motion_worker=MotionWorker(), simulation_runtime=object(), dry_run=True)
    entered, release = threading.Event(), threading.Event()
    def operation():
        entered.set()
        release.wait(1)
    before = time.monotonic()
    try:
        handler._queue_or_run(operation)
        assert time.monotonic() - before < .25
        assert entered.wait(1) and handler.hw.motion_worker.busy
    finally:
        release.set()
        handler.hw.motion_worker.close(2)
        handler.hw.motion_worker.poll()


def test_busy_virtual_readiness_does_not_wait_on_backend_state_lock():
    manager = HardwareManager.__new__(HardwareManager)
    manager.config = SimpleNamespace(GAME_ONLY=False)
    manager.simulation_runtime = object()
    manager._piece_move_lock = threading.Lock()
    manager._piece_move_lock.acquire()
    manager.backend = SimpleNamespace(is_connected=Mock(side_effect=AssertionError('UI waited on active physics')))
    assert manager.is_robot_ready is False
    manager.backend.is_connected.assert_not_called()


def test_optional_command_metadata_failure_keeps_readonly_arm_packet():
    telemetry = TelemetryPublisher(port=0)
    telemetry.connected = telemetry.joints_valid = True
    telemetry.current_joints = [1, 2, 3, 4, 5, 6]
    telemetry.command_context_provider = Mock(side_effect=RuntimeError('game context unavailable'))
    packet = json.loads(telemetry._make_packet_json())
    assert packet['joints'] == [1, 2, 3, 4, 5, 6] and packet['connected']
    assert packet['command_context'] is None


@pytest.fixture
def session(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'SIMULATION_TOKEN', '')
    monkeypatch.setattr(config, 'GAME_MODE', 'HUMAN_VS_ROBOT')
    state = GameState()
    state.attach_journal(tmp_path, 'VIRTUAL', 'HUMAN_VS_ROBOT')
    yield state, tmp_path
    state.api_client.close()
    state.close_journal()


def reopen(root, mode):
    state = GameState()
    state.attach_journal(root, 'VIRTUAL', mode)
    return state


def test_home_then_other_mode_starts_new_game_and_keeps_retired_outbox(session):
    state, root = session
    old_session = state._journal.session_id
    assert state.process_human_move((4, 6), (4, 5), 'r_P')
    state.publish_match_end(reason='OTHER')
    state.close_journal(clean=True)
    new = reopen(root, 'HUMAN_VS_HUMAN_ROBOT')
    try:
        assert new._journal.session_id != old_session
        assert not new.recovery_required and not new.mode_change_pending
        assert new.board == xiangqi.get_board() and new.move_history == []
        assert new.board_revision == 0 and new.turn == 'r'
        assert old_session in {entry[0] for entry in new._journal.pending_projections(include_retired=True)}
    finally:
        new.close_journal(); new.api_client.close()


def test_clean_close_without_retirement_preserves_saved_game(session):
    state, root = session
    assert state.process_human_move((4, 6), (4, 5), 'r_P')
    old_session = state._journal.session_id
    state.close_journal(clean=True)
    new = reopen(root, 'HUMAN_VS_HUMAN_ROBOT')
    try:
        assert new._journal.session_id == old_session
        assert new.recovery_required and new.mode_change_pending
        assert new.board[5][4] == 'r_P' and len(new.move_history) == 1
    finally:
        new.close_journal(); new.api_client.close()


def test_clean_close_with_recovery_latch_cannot_retire_uncertain_game(session):
    state, root = session
    state.recovery_required = True
    state.publish_match_end(reason='OTHER')
    old_session = state._journal.session_id
    state.close_journal(clean=True)
    new = reopen(root, 'HUMAN_VS_HUMAN_ROBOT')
    try:
        assert new._journal.session_id == old_session
        assert new.recovery_required and new.mode_change_pending
    finally:
        new.close_journal(); new.api_client.close()


def test_retirement_intent_never_discards_dispatched_robot_move(session):
    state, root = session
    assert state.process_human_move((4, 6), (4, 5), 'r_P')
    move = ((4, 3), (4, 4))
    context = state.create_move_context(*move, MoveActor.ROBOT)
    state.mark_move_pending(context)
    expected, _ = xiangqi.make_temp_move(state.board, move)
    state.set_pending_physical_move(move, expected, '.', 'b')
    state.record_motion_dispatch(context, 'pre_pick')
    state.publish_match_end(reason='OTHER')
    old_session = state._journal.session_id
    state.close_journal(clean=True)
    new = reopen(root, 'HUMAN_VS_HUMAN_ROBOT')
    try:
        assert new.recovery_required and new.mode_change_pending
        assert new._journal.session_id == old_session
        assert new.pending_move.move_id == context.move_id
        assert new.pending_execution_binding['move_id'] == context.move_id
        assert len(new.move_history) == 1 and new.board[3][4] == 'b_P'
    finally:
        new.close_journal(); new.api_client.close()


def test_emergency_replacement_does_not_inherit_robot_execution_binding(session, monkeypatch):
    state, root = session
    monkeypatch.setattr(config, 'GAME_MODE', 'HUMAN_VS_ROBOT')
    assert state.process_human_move((4, 6), (4, 5), 'r_P')
    context = state.create_move_context((4, 3), (4, 4), MoveActor.ROBOT)
    state.mark_move_pending(context)
    assert state.process_emergency_move((0, 3), (0, 4), 'b_P')
    assert state.last_committed_move.actor is MoveActor.HUMAN
    assert state.last_committed_move.move_id != context.move_id
    assert state.last_execution_binding is None
    assert state.pending_move is None and state.pending_execution_binding is None
    state.close_journal()
    new = reopen(root, 'HUMAN_VS_HUMAN_ROBOT')
    try:
        assert new.last_execution_binding is None
        assert new.last_committed_move.move_id == state.last_committed_move.move_id
    finally:
        new.close_journal(); new.api_client.close()
