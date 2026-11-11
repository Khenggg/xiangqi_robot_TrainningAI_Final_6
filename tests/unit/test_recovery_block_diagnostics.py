"""A verified board must not hide controller/stop recovery blockers."""
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.core.game_state import GameState
from src.core import xiangqi
from src.domain.game_move import MoveActor
from src.hardware.hardware_manager import HardwareManager
from src.ui.input_handler import InputHandler
from src.ui.recovery_status import describe_recovery


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(room_id=None))
    value = GameState()
    value.recovery_required = value.physical_sync_fault = True
    value.snapshot_continue_required = value.manual_override_active = True
    yield value
    value.close_journal()


def hardware(*, motion='ERROR', error='Controller error: main=1, sub=29', age=0,
             connected=True, stop_safe=False):
    hw = HardwareManager.__new__(HardwareManager)
    hw.config = SimpleNamespace(ROBOT_BACKEND='PHYSICAL')
    hw.dry_run = False
    hw.simulation_runtime = None
    hw.robot = SimpleNamespace(connected=True, activate_physical_control=Mock())
    hw.backend = SimpleNamespace(get_state_snapshot=Mock(side_effect=lambda: SimpleNamespace(
        connected=connected, joints_valid=True, measurement_timestamp=time.time()-age,
        motion_state=motion, last_error=error)))
    hw.physical_telemetry_ready = Mock(return_value=motion == 'IDLE' and not error and age < .5 and connected)
    hw.stop_coordinator = SimpleNamespace(safe_for_release=Mock(return_value=stop_safe), generation=0)
    hw.verify_physical_board = Mock(return_value=True)
    hw.capture_baseline_if_needed = Mock(return_value=True)
    hw._piece_move_lock = threading.Lock()
    return hw


@pytest.mark.parametrize('operation', ['V', 'F12', 'F4'])
def test_verified_opening_reports_controller_fault_and_preserves_lock(state, operation):
    hw = hardware()
    handler = InputHandler(state, hw)
    before = [row[:] for row in state.board]
    scanned = [row[:] for row in before]
    if operation == 'F4':
        scanned[5][0], scanned[6][0] = scanned[6][0], '.'
    handler._fresh_confirmed_layout = Mock(return_value=scanned)
    handler.resume_automatic_scanning = Mock()
    if operation == 'V':
        handler._reconcile_physical_sync_fault()
    elif operation == 'F12':
        assert not handler._clear_failed_session()
    else:
        assert not handler._rescan_confirmed_board()
    assert 'Camera đã xác nhận bàn' in state.status_message
    assert 'FEN đã khớp' not in state.status_message  # F4 can scan a different layout.
    assert 'main=1, sub=29' in state.status_message
    panel = describe_recovery(state.get_render_state())
    assert 'The camera confirmed the board' in panel['reason'] and 'sub=29' in panel['reason']
    assert 'WebApp' in panel['action']
    assert state.recovery_required and state.physical_sync_fault
    assert state.snapshot_continue_required and state.manual_override_active
    assert state.board == before and state.board_revision == 0
    assert sum(cell != '.' for row in state.board for cell in row) == 32
    handler.resume_automatic_scanning.assert_not_called()
    hw.capture_baseline_if_needed.assert_not_called()
    hw.robot.activate_physical_control.assert_not_called()


@pytest.mark.parametrize('observed', ['before', 'after'])
def test_verified_pending_board_does_not_prompt_piece_correction_or_retire_move(state, observed):
    hw = hardware()
    state.turn = 'b'
    move = ((0, 3), (0, 4))
    state.mark_move_pending(state.create_move_context(*move, MoveActor.ROBOT))
    expected, captured = xiangqi.make_temp_move(state.board, move)
    state.set_pending_physical_move(move, expected, captured, 'b')
    pending = state.pending_move
    hw.verify_physical_board.side_effect = lambda board: board == (state.board if observed == 'before' else expected)
    handler = InputHandler(state, hw)
    handler._finalize_pending_ai_move = Mock()
    handler._reconcile_physical_sync_fault()
    assert 'Camera đã xác nhận bàn' in state.status_message and 'sub=29' in state.status_message
    assert state.pending_move is pending and state.pending_ai_move is not None
    assert state.recovery_required and state.physical_sync_fault
    assert state.board_revision == 0
    handler._finalize_pending_ai_move.assert_not_called()
    hw.robot.activate_physical_control.assert_not_called()


def test_enable_reports_fault_before_generic_pending_board_error(state):
    hw = hardware()
    with pytest.raises(RuntimeError, match='main=1, sub=29'):
        hw.activate_physical_game(state, commissioned=True)
    hw.robot.activate_physical_control.assert_not_called()
    hw.verify_physical_board.assert_not_called()


@pytest.mark.parametrize('kwargs, fragment', [
    ({'age': 2}, 'đã cũ'),
    ({'connected': False}, 'mất kết nối'),
    ({'motion': 'MOVING', 'error': None}, 'MOVING'),
    ({'motion': 'IDLE', 'error': None}, 'V xác nhận'),
])
def test_other_hardware_blockers_are_distinct_from_board_mismatch(state, kwargs, fragment):
    handler = InputHandler(state, hardware(**kwargs))
    handler._reconcile_physical_sync_fault()
    assert 'Camera đã xác nhận bàn' in state.status_message and fragment in state.status_message
    assert state.recovery_required and state.physical_sync_fault


def test_healthy_idle_stop_proof_allows_existing_recovery(state):
    state.hardware_recovery_reason = 'Previous controller fault'
    hw = hardware(motion='IDLE', error=None, stop_safe=True)
    handler = InputHandler(state, hw)
    handler.resume_automatic_scanning = Mock(return_value=True)
    state.sync_current_board = Mock(return_value=True)
    handler._reconcile_physical_sync_fault()
    assert not state.recovery_required and not state.physical_sync_fault
    assert not state.snapshot_continue_required
    assert state.hardware_recovery_reason is None
    handler.resume_automatic_scanning.assert_called_once()
    hw.robot.activate_physical_control.assert_not_called()


def test_board_mismatch_still_reports_camera_failure(state):
    state.hardware_recovery_reason = 'Previous controller fault'
    hw = hardware()
    hw.verify_physical_board.return_value = False
    InputHandler(state, hw)._reconcile_physical_sync_fault()
    assert 'full-board verification failed' in state.status_message
    assert state.recovery_required and state.physical_sync_fault
    assert state.hardware_recovery_reason is None
