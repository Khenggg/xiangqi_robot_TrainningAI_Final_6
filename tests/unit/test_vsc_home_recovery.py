"""HOMECHESS recovery keeps one unfinished move behind manual-reset approval."""
from copy import deepcopy
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest

from src.modes.vsc_v3.core import game_state as donor
from src.modes.vsc_v3.core import xiangqi
from src.modes.vsc_v3.ui import input_handler as ui
from src.modes.vsc_v3.ui.board_renderer import BTN_NEW_GAME_RECT, BTN_CONTINUE_RECT


@pytest.fixture
def recovery(monkeypatch):
    monkeypatch.setattr(donor, 'TuongKyDaiSuClient', lambda *args: Mock(room_id=None))
    state = donor.GameState()
    state.process_human_move((0, 6), (0, 5), 'r_P')
    move = ((0, 3), (0, 4))
    expected, captured = xiangqi.make_temp_move(state.board, move)
    state.set_pending_ai_move(move, expected, captured)
    state.api_client.reset_mock()
    config = SimpleNamespace(VISUAL_MOTION_ASYNC_ENABLED=False,
                             GRIPPER_ACTION_OPEN_MAX='open_max')
    hw = SimpleNamespace(config=config, robot=SimpleNamespace(gripper_ctrl=Mock(return_value=0)),
                         verify_physical_board=Mock(return_value=True),
                         capture_baseline_if_needed=Mock(return_value=True))
    handler = ui.InputHandler.__new__(ui.InputHandler)
    handler.state, handler.hw, handler._motion_thread = state, hw, None
    home = Mock(return_value=SimpleNamespace(at_home=True, reason='Verified HOMECHESS'))
    check = Mock(return_value=SimpleNamespace(at_home=True, reason='Fresh HOMECHESS'))
    execute = Mock()
    monkeypatch.setattr('src.hardware.home_chess_recovery.return_to_home_chess', home)
    monkeypatch.setattr('src.hardware.home_chess_recovery.check_home_chess', check)
    monkeypatch.setattr(ui, 'execute_pending_ai_motion', execute)
    return SimpleNamespace(state=state, hw=hw, handler=handler, home=home,
                           check=check, execute=execute, monkeypatch=monkeypatch)


def begin(recovery):
    error = RuntimeError('Lift interrupted')
    recovery.handler.begin_home_recovery(error)
    return error


def test_failed_motion_parks_once_and_keeps_gripper_pending_fen_and_history(recovery):
    r = recovery
    pending, board, fen, history = (r.state.pending_ai_move, deepcopy(r.state.board),
                                    r.state.current_fen, deepcopy(r.state.move_history))
    error = begin(r)
    r.home.assert_called_once()
    assert r.home.call_args.args == (r.hw.robot,)
    assert r.home.call_args.kwargs['failure'] is error
    assert r.home.call_args.kwargs['is_current']()
    r.hw.robot.gripper_ctrl.assert_not_called()
    r.execute.assert_not_called()
    assert r.state.pending_ai_move is pending
    assert r.state.board == board and r.state.current_fen == fen
    assert r.state.move_history == history and r.state.turn == 'b'
    assert r.state.home_recovery.status == 'waiting_manual'
    assert r.state.physical_sync_fault and r.state.snapshot_continue_required
    assert not r.state.can_start_ai_turn()


def test_initial_motion_exception_enters_home_recovery(recovery):
    r = recovery
    r.execute.side_effect = RuntimeError('Controller rejected move')
    r.handler.start_pending_ai_motion()
    r.home.assert_called_once()
    assert r.state.home_recovery.status == 'waiting_manual'
    assert r.state.pending_ai_move is not None and len(r.state.move_history) == 1


def test_manual_approval_retries_the_same_pending_move_and_commits_once(recovery):
    r = recovery
    pending = r.state.pending_ai_move
    old_board = deepcopy(r.state.board)
    begin(r)
    observed = []
    r.hw.verify_physical_board.side_effect = lambda board: observed.append(('board', board)) or True
    r.hw.robot.gripper_ctrl.side_effect = lambda action: observed.append(('gripper', action)) or 0

    def execute(state, hw, config):
        assert state.pending_ai_move is pending
        assert state.current_fen == original_fen
        assert len(state.move_history) == 1
        observed.append(('motion', state.pending_ai_move['move']))

    original_fen = r.state.current_fen
    r.execute.side_effect = execute
    r.handler.handle_keyboard(pygame.K_r)
    assert [item[0] for item in observed] == ['board', 'gripper', 'motion']
    assert observed[0][1] == old_board
    assert observed[1][1] == 'open_max'
    r.execute.assert_called_once_with(r.state, r.hw, r.hw.config)
    assert r.state.pending_ai_move is None and r.state.home_recovery is None
    assert r.state.turn == 'r' and r.state.board == pending['expected_board']
    assert r.state.current_fen != original_fen and len(r.state.move_history) == 2
    assert not r.state.physical_sync_fault and not r.state.manual_override_active
    r.handler.handle_keyboard(pygame.K_r)
    r.execute.assert_called_once()
    assert len(r.state.move_history) == 2


def test_full_old_board_must_match_before_opening_or_replaying_a_capture(recovery):
    r = recovery
    move = ((0, 3), (0, 5))
    expected, captured = xiangqi.make_temp_move(r.state.board, move)
    r.state.set_pending_ai_move(move, expected, captured)
    checkpoint = r.state.visual_capture_checkpoint = {'capture_removed': True}
    old_board = deepcopy(r.state.board)
    begin(r)
    r.hw.verify_physical_board.return_value = False
    r.handler.handle_keyboard(pygame.K_r)
    r.hw.verify_physical_board.assert_called_once_with(old_board)
    assert r.state.visual_capture_checkpoint is checkpoint
    r.hw.robot.gripper_ctrl.assert_not_called()
    r.execute.assert_not_called()
    assert r.state.home_recovery.status == 'waiting_manual'

    def execute(state, hw, config):
        assert state.visual_capture_checkpoint is None
        assert state.pending_ai_move['captured_piece'] == 'r_P'

    r.hw.verify_physical_board.return_value = True
    r.execute.side_effect = execute
    r.handler.handle_keyboard(pygame.K_r)
    r.execute.assert_called_once()
    assert r.state.board == expected and r.state.r_captured == ['r_P']


@pytest.mark.parametrize('key', [pygame.K_v, pygame.K_SPACE, pygame.K_m,
                                 pygame.K_z, pygame.K_t, pygame.K_x])
def test_ordinary_keys_cannot_bypass_manual_recovery(recovery, key):
    r = recovery
    pending = r.state.pending_ai_move
    begin(r)
    r.handler.handle_keyboard(key)
    r.execute.assert_not_called()
    r.check.assert_not_called()
    r.hw.robot.gripper_ctrl.assert_not_called()
    assert r.state.pending_ai_move is pending and r.state.physical_sync_fault


def test_new_game_click_cannot_discard_the_unfinished_move(recovery):
    r = recovery
    begin(r)
    pending = r.state.pending_ai_move
    reset = Mock()
    r.state.reset_game = reset
    r.handler.handle_mouse_down(*BTN_NEW_GAME_RECT.center)
    reset.assert_not_called()
    assert r.state.pending_ai_move is pending
    r.execute.assert_not_called()


def test_continue_button_is_the_manual_retry_action(recovery):
    r = recovery
    begin(r)
    r.handler.handle_mouse_down(*BTN_CONTINUE_RECT.center)
    r.execute.assert_called_once()
    assert r.state.turn == 'r'


@pytest.mark.parametrize('change', ['epoch', 'pending_identity', 'pending_contents', 'board', 'game_over'])
def test_stale_recovery_cannot_open_gripper_or_execute_move(recovery, change):
    r = recovery
    begin(r)
    if change == 'epoch':
        r.state.ai_epoch += 1
    elif change == 'pending_identity':
        r.state.pending_ai_move = deepcopy(r.state.pending_ai_move)
    elif change == 'pending_contents':
        r.state.pending_ai_move['move'] = ((2, 3), (2, 4))
    elif change == 'board':
        r.state.board[3][2] = '.'
    else:
        r.state.game_over = True
    r.handler.handle_keyboard(pygame.K_r)
    r.check.assert_not_called()
    r.hw.robot.gripper_ctrl.assert_not_called()
    r.execute.assert_not_called()
    r.home.assert_called_once()
    assert r.state.physical_sync_fault


def test_home_failure_waits_for_deliberate_h_and_never_repeats_automatically(recovery):
    r = recovery
    r.home.side_effect = [SimpleNamespace(at_home=False, reason='Controller fault'),
                          SimpleNamespace(at_home=True, reason='Verified HOMECHESS')]
    error = begin(r)
    assert r.state.home_recovery.status == 'home_failed'
    r.handler.handle_keyboard(pygame.K_r)
    r.handler.handle_keyboard(pygame.K_v)
    r.home.assert_called_once()
    assert r.home.call_args.kwargs['failure'] is error
    assert r.home.call_args.kwargs['is_current']()
    r.execute.assert_not_called()
    r.handler.handle_keyboard(pygame.K_h)
    assert r.home.call_count == 2 and r.home.call_args.kwargs['failure'] is None
    assert r.home.call_args.kwargs['is_current']()
    assert r.state.home_recovery.status == 'waiting_manual'
    r.handler.handle_keyboard(pygame.K_h)
    assert r.home.call_count == 2
    r.hw.robot.gripper_ctrl.assert_not_called()


def test_changed_home_measurement_blocks_manual_retry(recovery):
    r = recovery
    begin(r)
    r.check.return_value = SimpleNamespace(at_home=False, reason='TCP no longer at HOME')
    r.handler.handle_keyboard(pygame.K_r)
    assert r.state.home_recovery.status == 'home_failed'
    r.hw.verify_physical_board.assert_not_called()
    r.hw.robot.gripper_ctrl.assert_not_called()
    r.execute.assert_not_called()


def test_home_must_still_be_verified_after_the_camera_reset_check(recovery):
    r = recovery
    begin(r)
    at_home = [True]
    r.check.side_effect = lambda robot, **kwargs: SimpleNamespace(
        at_home=at_home[0], reason='HOME changed during camera verification')

    def verify_board(board):
        # Camera verification can take seconds; the earlier pose proof expires.
        at_home[0] = False
        return True

    r.hw.verify_physical_board.side_effect = verify_board
    r.handler.handle_keyboard(pygame.K_r)
    r.hw.robot.gripper_ctrl.assert_not_called()
    r.execute.assert_not_called()
    assert r.state.pending_ai_move is not None and r.state.physical_sync_fault


def test_retry_failure_parks_again_and_preserves_the_original_pending_move(recovery):
    r = recovery
    pending = r.state.pending_ai_move
    begin(r)
    r.execute.side_effect = RuntimeError('Lift failed again')
    r.handler.handle_keyboard(pygame.K_r)
    assert r.home.call_count == 2
    assert r.state.pending_ai_move is pending and r.state.home_recovery.status == 'waiting_manual'
    assert len(r.state.move_history) == 1 and r.state.turn == 'b'
    r.execute.assert_called_once()


def test_post_commit_api_failure_never_parks_or_replays_an_already_committed_move(recovery):
    r = recovery
    begin(r)
    r.state.api_client.send_move_update_board.side_effect = RuntimeError('API offline')
    r.handler.handle_keyboard(pygame.K_r)
    r.home.assert_called_once()
    r.execute.assert_called_once()
    assert r.state.pending_ai_move is None and r.state.home_recovery is None
    assert len(r.state.move_history) == 2 and r.state.turn == 'r'
    assert r.state.manual_override_active


@pytest.mark.parametrize('code', [False, 17])
def test_gripper_open_failure_prevents_replay(recovery, code):
    r = recovery
    begin(r)
    r.hw.robot.gripper_ctrl.return_value = code
    r.handler.handle_keyboard(pygame.K_r)
    r.execute.assert_not_called()
    assert r.state.pending_ai_move is not None and r.state.physical_sync_fault


def test_async_home_job_retains_worker_ownership_and_blocks_input(recovery):
    r = recovery
    r.hw.config.VISUAL_MOTION_ASYNC_ENABLED = True
    entered, release = threading.Event(), threading.Event()
    owner = []

    def park(robot, *, failure, is_current):
        assert is_current()
        owner.append(threading.current_thread())
        entered.set()
        assert release.wait(3)
        return SimpleNamespace(at_home=True, reason='Verified HOMECHESS')

    r.home.side_effect = park
    try:
        begin(r)
        assert entered.wait(2)
        assert r.state.physical_motion_busy
        r.handler.handle_keyboard(pygame.K_r)
        r.handler.handle_keyboard(pygame.K_h)
        r.handler.handle_mouse_down(*BTN_CONTINUE_RECT.center)
        r.execute.assert_not_called()
        r.check.assert_not_called()
        assert owner == [r.handler._motion_thread]
    finally:
        release.set()
        worker = r.handler._motion_thread
        if worker is not None:
            worker.join(3)
    assert not r.state.physical_motion_busy
    assert r.state.home_recovery.status == 'waiting_manual'


def prepare_manual_test(recovery):
    r = recovery
    r.state.pending_ai_move = None
    r.state.pick_test_mode = True
    r.state.pick_test_board = deepcopy(r.state.board)
    r.hw.execute_pick_place_test = Mock(side_effect=RuntimeError('Test lift interrupted'))
    return (0, 3), (0, 4)


def test_manual_pick_failure_returns_home_without_modifying_test_board_or_fen(recovery):
    r = recovery
    source, destination = prepare_manual_test(r)
    board, test_board, fen, history = (deepcopy(r.state.board), deepcopy(r.state.pick_test_board),
                                      r.state.current_fen, deepcopy(r.state.move_history))
    r.handler._run_pick_test(source, destination)
    r.home.assert_called_once()
    r.hw.robot.gripper_ctrl.assert_not_called()
    assert r.state.home_recovery.owner == 'test'
    assert r.state.home_recovery.status == 'waiting_manual'
    assert r.state.home_recovery.test_move == (source, destination)
    assert r.state.board == board and r.state.pick_test_board == test_board
    assert r.state.current_fen == fen and r.state.move_history == history
    assert r.state.pick_test_resume_required and r.state.manual_override_active


def test_manual_test_r_retries_same_move_with_live_ownership_validation(recovery):
    r = recovery
    source, destination = prepare_manual_test(r)
    r.handler._run_pick_test(source, destination)
    original_fen, original_board = r.state.current_fen, deepcopy(r.state.board)
    before_test = deepcopy(r.state.pick_test_board)
    r.hw.execute_pick_place_test.reset_mock()

    def execute(sc, dc, *, validate_request):
        assert (sc, dc) == (source, destination)
        validate_request()
        assert r.state.pick_test_board == before_test
        return SimpleNamespace(col=dc[0], row=dc[1])

    r.hw.execute_pick_place_test.side_effect = execute
    r.handler.handle_keyboard(pygame.K_r)
    r.hw.execute_pick_place_test.assert_called_once()
    r.execute.assert_not_called()  # No AI motion or recomputation for a test.
    assert r.state.home_recovery is None
    assert r.state.pick_test_board[4][0] == before_test[3][0]
    assert r.state.pick_test_board[3][0] == '.'
    assert r.state.board == original_board and r.state.current_fen == original_fen
    assert r.state.pick_test_resume_required


def test_manual_test_retry_failure_parks_and_keeps_its_unmodified_board(recovery):
    r = recovery
    source, destination = prepare_manual_test(r)
    before = deepcopy(r.state.pick_test_board)
    r.handler._run_pick_test(source, destination)
    r.handler.handle_keyboard(pygame.K_r)
    assert r.hw.execute_pick_place_test.call_count == 2
    assert r.home.call_count == 2
    assert r.state.home_recovery.owner == 'test'
    assert r.state.home_recovery.status == 'waiting_manual'
    assert r.state.pick_test_board == before
    assert r.state.pick_test_resume_required and r.state.manual_override_active


def test_manual_test_board_change_invalidates_recovery_before_open_or_replay(recovery):
    r = recovery
    source, destination = prepare_manual_test(r)
    r.handler._run_pick_test(source, destination)
    r.state.pick_test_board[3][0] = '.'
    r.handler.handle_keyboard(pygame.K_r)
    r.hw.execute_pick_place_test.assert_called_once()
    r.hw.robot.gripper_ctrl.assert_not_called()
    r.hw.verify_physical_board.assert_not_called()


def change_ai_owner(state, change):
    if change == 'epoch':
        state.ai_epoch += 1
    elif change == 'pending':
        state.pending_ai_move = deepcopy(state.pending_ai_move)
    else:
        state.board[3][2] = '.'


@pytest.mark.parametrize('change', ['epoch', 'pending', 'board'])
def test_initial_motion_error_cannot_park_after_operation_ownership_changes(recovery, change):
    r = recovery
    original_pending = r.state.pending_ai_move

    def fail(state, hw, config):
        change_ai_owner(state, change)
        raise RuntimeError('Old operation failed after ownership changed')

    r.execute.side_effect = fail
    r.handler.start_pending_ai_motion()
    r.home.assert_not_called()
    r.hw.robot.gripper_ctrl.assert_not_called()
    assert r.state.home_recovery.pending is original_pending
    assert not r.state.home_recovery.is_current(r.state)
    assert r.state.physical_sync_fault and r.state.manual_override_active


@pytest.mark.parametrize('change', ['epoch', 'pending', 'board'])
def test_sync_session_motion_error_uses_its_original_operation_snapshot(recovery, change):
    from src.modes.vsc_v3_session import VscV3Session

    r = recovery
    session = VscV3Session.__new__(VscV3Session)
    session.state, session.hw, session.input = r.state, r.hw, r.handler
    session.config = SimpleNamespace(DRY_RUN=False, VISUAL_MOTION_ASYNC_ENABLED=False)
    r.hw.robot.connected = True
    token = (r.state.game_epoch, r.state.ai_epoch, r.state.human_commit_generation)
    r.state.ai_thinking = True
    r.state.ai_thread = SimpleNamespace(is_alive=lambda: False)
    r.state.ai_job_token = token
    r.state.ai_results[token] = ((0, 3), (0, 4))
    original_pending = []

    def fail(state, hw, config):
        original_pending.append(state.pending_ai_move)
        change_ai_owner(state, change)
        raise RuntimeError('Old synchronous operation failed')

    r.monkeypatch.setattr('src.modes.vsc_v3.core.visual_move_coordinator.execute_pending_ai_motion', fail)
    session._tick_ai()
    assert len(original_pending) == 1
    r.home.assert_not_called()
    r.hw.robot.gripper_ctrl.assert_not_called()
    assert r.state.home_recovery.pending is original_pending[0]
    assert not r.state.home_recovery.is_current(r.state)
    assert len(r.state.move_history) == 1 and r.state.physical_sync_fault


@pytest.mark.parametrize('change', ['epoch', 'test_board', 'test_owner'])
def test_initial_manual_test_error_cannot_park_a_superseded_operation(recovery, change):
    r = recovery
    source, destination = prepare_manual_test(r)

    def fail(*args, **kwargs):
        if change == 'epoch':
            r.state.ai_epoch += 1
        elif change == 'test_board':
            r.state.pick_test_board[3][2] = '.'
        else:
            r.state.pick_test_mode = False
        raise RuntimeError('Test operation changed while faulting')

    r.hw.execute_pick_place_test.side_effect = fail
    r.handler._run_pick_test(source, destination)
    r.home.assert_not_called()
    r.hw.robot.gripper_ctrl.assert_not_called()
    assert r.state.home_recovery.owner == 'test'
    assert not r.state.home_recovery.is_current(r.state)
    assert r.state.pick_test_resume_required and r.state.manual_override_active

@pytest.mark.parametrize('parked', [True, False])
def test_surrender_during_home_recovery_requires_verified_parking(recovery, parked):
    r = recovery
    r.home.return_value = SimpleNamespace(at_home=parked, reason='test')
    begin(r)
    fen = r.state.current_fen
    r.handler.handle_mouse_down(*ui.BTN_SURRENDER_RECT.center)
    assert r.state.current_fen == fen
    assert r.state.game_over is parked
    assert (r.state.home_recovery is None) is parked
    assert (r.state.pending_ai_move is None) is parked
    if parked:
        r.state.api_client.end_match.assert_called_once_with(winner="BLACK", reason="RESIGN")
    else:
        r.state.api_client.end_match.assert_not_called()
    r.execute.assert_not_called()
    r.hw.robot.gripper_ctrl.assert_not_called()

@pytest.mark.parametrize('use_mouse', [False, True])
@pytest.mark.parametrize('parked', [False, True])
def test_failed_pick_test_exit_requires_home(recovery, use_mouse, parked):
    r = recovery
    source, destination = prepare_manual_test(r)
    r.home.return_value = SimpleNamespace(at_home=parked, reason='test')
    r.handler._run_pick_test(source, destination)
    r.hw.execute_pick_place_test.reset_mock()
    if use_mouse:
        r.handler.handle_mouse_down(*ui.BTN_PICK_TEST_RECT.center)
    else:
        r.handler.handle_keyboard(pygame.K_t)
    assert (r.state.home_recovery is None) is parked
    assert r.state.pick_test_mode is (not parked)
    assert r.state.pick_test_resume_required
    r.hw.execute_pick_place_test.assert_not_called()
    r.hw.robot.gripper_ctrl.assert_not_called()
