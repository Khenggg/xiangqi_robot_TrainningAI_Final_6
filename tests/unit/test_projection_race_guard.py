"""A board projection must not overwrite an in-flight semantic move."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock

from src.hardware.hardware_manager import HardwareManager


def _manager(state):
    bridge = Mock()
    bridge.reconcile_to_board_cells = Mock(return_value=True)
    return SimpleNamespace(
        twin_bridge=bridge,
        _piece_move_lock=threading.Lock(),
        game_state=state,
        simulation_runtime=None,
        viewer_command_context=lambda: {},
    ), bridge


def test_sync_committed_board_rejects_while_a_move_is_pending():
    state = SimpleNamespace(
        pending_move=object(),
        pending_ai_move=None,
        pending_test_motion=None,
        _transition_lock=threading.RLock(),
        pick_test_resume_required=False,
        piece_ids={},
        board_revision=1,
        _journal=None,
        _local_session_id="test",
        pick_test_mode=False,
    )
    manager, bridge = _manager(state)
    assert HardwareManager.sync_committed_board(manager, {}) is False
    bridge.reconcile_to_board_cells.assert_not_called()


def test_sync_committed_board_allows_a_committed_board():
    state = SimpleNamespace(
        pending_move=None,
        pending_ai_move=None,
        pending_test_motion=None,
        _transition_lock=threading.RLock(),
        pick_test_resume_required=False,
        piece_ids={},
        board_revision=1,
        _journal=None,
        _local_session_id="test",
        pick_test_mode=False,
    )
    manager, bridge = _manager(state)
    assert HardwareManager.sync_committed_board(manager, {}) is True
    bridge.reconcile_to_board_cells.assert_called_once()
