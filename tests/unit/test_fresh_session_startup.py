"""A new launch owns a new board; old commands remain durable audit evidence."""
import ast
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import config
from src.core import xiangqi
from src.core.fen_utils import INITIAL_FEN
from src.core.game_state import GameState
from src.core.session_journal import JournalError, decode
from src.domain.game_move import MoveActor


@pytest.fixture
def states(monkeypatch):
    monkeypatch.setattr(config, "SIMULATION_TOKEN", "")
    monkeypatch.setattr(config, "GAME_MODE", "HUMAN_VS_HUMAN")
    opened = []

    def create():
        state = GameState()
        opened.append(state)
        return state

    yield create
    for state in opened:
        state.close_projection_worker()
        state.api_client.close()
        state.close_journal()


@pytest.mark.parametrize("environment", ["VIRTUAL", "PHYSICAL"])
def test_new_launch_starts_initial_fen_and_archives_previous_board(states, tmp_path, environment):
    old = states()
    old.attach_journal(tmp_path, environment, "HUMAN_VS_HUMAN")
    assert old.process_human_move((6, 6), (6, 5), "r_P")
    old_id, old_fen = old._journal.session_id, old.current_fen
    old.close_journal(clean=True)

    new = states()
    new.attach_journal(tmp_path, environment, "HUMAN_VS_ROBOT", fresh_start=True)
    assert new._journal.session_id != old_id
    assert new.board == xiangqi.get_board() and new.current_fen == INITIAL_FEN
    assert new.turn == "r" and new.board_revision == 0 and new.move_number == 1
    assert not new.move_history and new.pending_move is None and new.pending_ai_move is None
    assert not new.mode_change_pending and not new.recovery_required
    archived = new._journal._db.execute(
        "SELECT state FROM session_archive WHERE session_id=?", (old_id,)).fetchone()
    assert decode(json.loads(archived[0]))["current_fen"] == old_fen
    assert new._journal._db.execute(
        "SELECT count(*) FROM committed_moves WHERE session_id=?", (old_id,)).fetchone()[0] == 1


def test_interrupted_physical_command_is_archived_without_replay_or_old_fen(states, tmp_path):
    old = states()
    old.attach_journal(tmp_path, "PHYSICAL", "HUMAN_VS_ROBOT")
    assert old.process_human_move((6, 6), (6, 5), "r_P")
    move = ((0, 3), (0, 4))
    context = old.create_move_context(*move, MoveActor.ROBOT)
    old.mark_move_pending(context)
    expected, _ = xiangqi.make_temp_move(old.board, move)
    old.set_pending_physical_move(move, expected, ".", "b")
    old.record_motion_dispatch(context, "pre_pick")
    old_id = old._journal.session_id
    old.close_journal()

    new = states()
    new.attach_journal(tmp_path, "PHYSICAL", "HUMAN_VS_ROBOT", fresh_start=True)
    assert new.current_fen == INITIAL_FEN and new.board == xiangqi.get_board()
    assert new.pending_move is None and new.pending_execution_binding is None
    assert new.pending_ai_move is None and new.visual_capture_checkpoint is None
    assert new.recovery_required and new.physical_sync_fault
    assert not new.can_start_ai_turn()
    archived = decode(json.loads(new._journal._db.execute(
        "SELECT state FROM session_archive WHERE session_id=?", (old_id,)).fetchone()[0]))
    assert archived["pending_move"].move_id == context.move_id
    assert new._journal._db.execute(
        "SELECT stage FROM command_receipts WHERE session_id=? AND move_id=?",
        (old_id, context.move_id)).fetchone() == ("pre_pick",)
    new.close_journal()
    again = states()
    again.attach_journal(tmp_path, "PHYSICAL", "HUMAN_VS_ROBOT", fresh_start=True)
    assert again.recovery_required and again.current_fen == INITIAL_FEN


def test_failed_fresh_start_keeps_previous_session_and_archive_atomic(states, tmp_path):
    old = states()
    old.attach_journal(tmp_path, "VIRTUAL", "HUMAN_VS_HUMAN")
    assert old.process_human_move((6, 6), (6, 5), "r_P")
    old_id, old_fen = old._journal.session_id, old.current_fen
    old._journal._db.execute("""CREATE TRIGGER reject_new_session BEFORE INSERT ON current_session
        WHEN NEW.session_id != (SELECT session_id FROM current_session WHERE id=1)
        BEGIN SELECT RAISE(ABORT, 'injected write failure'); END""")
    old.close_journal()
    new = states()
    with pytest.raises(JournalError, match="injected write failure"):
        new.attach_journal(tmp_path, "VIRTUAL", "HUMAN_VS_HUMAN", fresh_start=True)
    assert new._journal is None
    restored = states()
    restored.attach_journal(tmp_path, "VIRTUAL", "HUMAN_VS_HUMAN")
    assert restored._journal.session_id == old_id and restored.current_fen == old_fen
    assert restored._journal._db.execute("SELECT count(*) FROM session_archive").fetchone()[0] == 0


def test_fresh_start_cannot_replace_an_open_session_lease(states, tmp_path):
    old = states()
    old.attach_journal(tmp_path, "VIRTUAL", "HUMAN_VS_HUMAN")
    old_id = old._journal.session_id
    with pytest.raises(JournalError):
        states().attach_journal(tmp_path, "VIRTUAL", "HUMAN_VS_HUMAN", fresh_start=True)
    assert old._journal.session_id == old_id


def test_launcher_requests_fresh_journal_before_opening_devices(states, tmp_path, monkeypatch):
    from src.core import session_startup
    from src.core.launch_options import parse_options
    old = states()
    old.attach_journal(tmp_path, "VIRTUAL", "HUMAN_VS_HUMAN")
    assert old.process_human_move((6, 6), (6, 5), "r_P")
    old_id = old._journal.session_id
    old.close_journal(clean=True)
    state = states()
    state.attach_journal = Mock(wraps=state.attach_journal)
    state.start_projection_worker = Mock()
    manager = SimpleNamespace(initialize_all=Mock(), setup_digital_twin=Mock(return_value=None),
                              viewer_command_context=Mock(), simulation_error=None)
    manager.initialize_all.return_value = manager
    def construct(*args):
        state.attach_journal.assert_called_once_with(
            tmp_path, "VIRTUAL", "HUMAN_VS_HUMAN", fresh_start=True)
        return manager
    monkeypatch.setattr(session_startup, "HardwareManager", construct)
    monkeypatch.setattr(session_startup, "TelemetryPublisher", Mock())
    cfg = SimpleNamespace(GAME_MODE="HUMAN_VS_HUMAN", GAME_ONLY=False,
                          ROBOT_BACKEND="VIRTUAL", DRY_RUN=True,
                          TELEMETRY_HOST="127.0.0.1", TELEMETRY_PORT=8765)
    session_startup.build_session(cfg, parse_options(["--board-only"]), tmp_path, state)
    assert state.current_fen == INITIAL_FEN
    assert state._journal.session_id != old_id


@pytest.mark.parametrize("measurement", ["unavailable", "stale", "moving", "idle"])
def test_fresh_physical_recovery_needs_measured_stop_even_without_pending_move(states, measurement):
    from src.hardware.controlled_stop import ControlledStopCoordinator
    state = states()
    state.recovery_required = state.physical_sync_fault = True
    assert state.pending_move is None and state.pending_ai_move is None
    robot = SimpleNamespace(latch_motion_stop=Mock(), send_controlled_stop=Mock())
    def snapshot():
        if measurement == "unavailable":
            raise RuntimeError("No telemetry")
        return SimpleNamespace(connected=True, joints_valid=True,
            measurement_timestamp=0 if measurement == "stale" else time.time(),
            motion_state="MOVING" if measurement == "moving" else "IDLE")
    backend = SimpleNamespace(get_state_snapshot=Mock(side_effect=snapshot))
    hardware = SimpleNamespace(game_state=state, robot=robot, backend=backend,
        simulation_runtime=None, dry_run=False, _piece_move_lock=threading.Lock())
    coordinator = ControlledStopCoordinator(hardware)
    request = coordinator.begin("Fresh session requires inspection", timeout=.2)
    assert request.done.wait(2)
    request.thread.join(2)
    assert request.requires_measurements
    assert request.result.safe is (measurement == "idle")
    assert coordinator.safe_for_release() is (measurement == "idle")
    assert backend.get_state_snapshot.called
    robot.send_controlled_stop.assert_not_called()  # Startup never owns actuation.


def test_selected_physical_game_captures_a_fresh_initial_board(states):
    # Execute the actual startup callback without importing main.py's GUI/devices.
    tree = ast.parse(Path("main.py").read_text(encoding="utf-8-sig"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_start_selected_game")
    state = states()
    hardware = SimpleNamespace(profile=SimpleNamespace(camera_enabled=True, mouse_input="NONE"),
        capture_baseline_if_needed=Mock(return_value=True), is_robot_ready=False)
    scope = dict(state=state, hw=hardware, self_play=None,
                 config=SimpleNamespace(DRY_RUN=False, ROBOT_BACKEND="PHYSICAL", GAME_MODE="HUMAN_VS_ROBOT"))
    exec(compile(ast.Module(body=[node], type_ignores=[]), "main.py", "exec"), scope)
    scope["_start_selected_game"]()
    hardware.capture_baseline_if_needed.assert_called_once_with(force_delay=0.0, expected_board=xiangqi.get_board())
    assert state.current_fen == INITIAL_FEN
