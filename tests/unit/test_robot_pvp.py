"""Two GUI players share the existing durable execution path; fake hardware only."""
import queue
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import config
from src.core import xiangqi
from src.core.game_state import GameState
from src.core.motion_worker import MotionWorker
from src.core.robot_pvp import RobotPvPController, ROBOT_PVP_MODE
from src.core.session_profile import make_profile
from src.motion.result import MotionExecutionResult
from src.domain.game_move import MoveActor


class Room:
    code, session, generation, connected = 'ABC234', 'session', 'peer', True
    def __init__(self):
        self.events = queue.Queue()
        self.sent = []
    def send(self, packet):
        self.sent.append(packet)
    def publish(self, packet):
        self.latest = packet
    def close(self):
        self.connected = False


def settle(hw):
    limit = time.monotonic()+3
    while hw.motion_worker.busy and time.monotonic() < limit:
        hw.motion_worker.poll()
        time.sleep(.005)
    assert not hw.motion_worker.busy


@pytest.fixture
def game(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'GAME_MODE', ROBOT_PVP_MODE)
    monkeypatch.setattr(config, 'SIMULATION_TOKEN', '')
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(token=None, room_id=None))
    s = GameState()
    s.session_profile = make_profile(ROBOT_PVP_MODE, 'PHYSICAL')
    s.attach_journal(tmp_path, 'PHYSICAL', ROBOT_PVP_MODE, fresh_start=True)
    hw = SimpleNamespace(profile=s.session_profile, dry_run=False, simulation_runtime=None,
        is_robot_ready=True, config=SimpleNamespace(VISUAL_PICK_ENABLED=False, ROBOT_BACKEND='PHYSICAL'),
        motion_worker=MotionWorker(), stop_coordinator=SimpleNamespace(blocked=False, generation=0),
        capture_baseline_if_needed=Mock(return_value=True))
    physical = {'board': [row[:] for row in s.board]}
    def verify(board, **kw):
        matched = board == physical['board']
        if matched:
            s.note_verified_pending_board(board)  # Same journal notification as HardwareManager.
        return matched
    hw.verify_physical_board = Mock(side_effect=verify)
    hw.is_cell_visually_clear = lambda cell: physical['board'][cell[1]][cell[0]] == '.'
    def execute(**kw):
        assert s.board_revision == len(s.move_history)
        assert s.board == physical['board']  # No logical commit before physical execution.
        if kw['is_capture']:
            physical['board'][kw['d_row']][kw['d_col']] = '.'
            assert kw['verify_capture_cleared']()
        physical['board'] = [row[:] for row in s.pending_ai_move['expected_board']]
        return MotionExecutionResult.ok()
    hw.execute_piece_move = Mock(side_effect=execute)
    room = Room()
    ctrl = RobotPvPController(s, hw, room)
    hw.pvp_controller = ctrl
    yield s, hw, ctrl, physical
    hw.motion_worker.close()
    ctrl.close()
    s.close_journal()


def submit(ctrl, side, move, **kwargs):
    s = ctrl.state
    return ctrl.submit(side, *move, revision=s.board_revision, epoch=s.game_epoch,
                       generation=ctrl.room.generation if side == 'b' else None, **kwargs)


def test_both_gui_players_execute_and_commit_capture_through_same_journal(game):
    s, hw, ctrl, _ = game
    for side, move in [('r',((0,6),(0,5))), ('b',((0,3),(0,4))), ('r',((0,5),(0,4)))]:
        assert submit(ctrl, side, move), (ctrl._blocked(), s.status_message, s.pending_move, s.turn)
        settle(hw)
        assert s.turn != side, (s.status_message, s.move_sync_error, s.visual_pick_retry, hw.execute_piece_move.call_count)
    assert s.turn == 'b' and s.board_revision == 3 and len(s.move_history) == 3
    assert s.board[4][0] == 'r_P' and s.b_captured == ['b_P']
    assert hw.execute_piece_move.call_count == 3
    contexts = [call.kwargs['move_context'] for call in hw.execute_piece_move.call_args_list]
    assert all(c.actor.value == 'ROBOT' for c in contexts)
    assert contexts[-1].captured_piece_id
    assert s._journal._db.execute('SELECT count(*) FROM committed_moves').fetchone()[0] == 3
    assert s.pending_move is None and not s.is_human_turn  # Camera never admits a GUI player's move.


def test_board_and_turn_stay_unchanged_while_robot_is_running(game):
    s, hw, ctrl, _ = game
    entered, release = threading.Event(), threading.Event()
    original = hw.execute_piece_move.side_effect
    def execute(**kw):
        entered.set()
        assert release.wait(2)
        return original(**kw)
    hw.execute_piece_move.side_effect = execute
    before = [row[:] for row in s.board]
    try:
        assert submit(ctrl,'r',((0,6),(0,5)),request_id='once')
        assert entered.wait(2)
        assert s.board == before and s.turn == 'r' and s.board_revision == 0
        assert not submit(ctrl,'r',((0,6),(0,5)),request_id='once')
        assert not submit(ctrl,'r',((2,6),(2,5)))
    finally:
        release.set()
    settle(hw)
    assert hw.execute_piece_move.call_count == 1 and s.board_revision == 1


@pytest.mark.parametrize('gate', ['recovery_required','physical_sync_fault','snapshot_continue_required',
                                  'manual_override_active','mode_change_pending','turn_confirmation_required'])
def test_recovery_flags_block_new_gui_move_without_pending_transaction(game, gate):
    s, hw, ctrl, _ = game
    setattr(s,gate,True)
    assert not submit(ctrl,'r',((0,6),(0,5)))
    assert s.pending_move is None and s.board_revision == 0
    hw.execute_piece_move.assert_not_called()


def test_stale_duplicate_wrong_role_and_invalid_cell_requests_do_not_dispatch(game):
    s, hw, ctrl, _ = game
    assert not submit(ctrl,'b',((0,3),(0,4)))
    assert not ctrl.submit('r',(0,6),(0,5),revision=-1,epoch=s.game_epoch)
    assert not ctrl.submit('r',(0,6),(0,5),revision=0,epoch=s.game_epoch-1)
    assert not submit(ctrl,'r',((True,6),(0,5)))
    assert not submit(ctrl,'r',((9,6),(0,5)))
    assert not submit(ctrl,'r',((0,6),(0,8)))
    hw.execute_piece_move.assert_not_called()


@pytest.mark.parametrize('change', ['disconnect', 'generation', 'stop', 'epoch'])
def test_queued_move_revalidates_before_any_robot_dispatch(game, change):
    s, hw, ctrl, _ = game
    queued = {}
    hw.motion_worker.start = lambda op, done: queued.update(op=op, done=done) or True
    assert submit(ctrl,'r',((0,6),(0,5)))
    if change == 'disconnect': ctrl.room.connected = False
    if change == 'generation': ctrl.room.generation = 'new-peer'
    if change == 'stop': hw.stop_coordinator.generation += 1
    if change == 'epoch': s.game_epoch += 1
    result = queued['op']()
    queued['done'](result, None)
    assert not result and s.pending_move is None and s.board_revision == 0
    hw.execute_piece_move.assert_not_called()


def test_post_motion_camera_failure_does_not_commit_or_replay_on_reconnect(game):
    s, hw, ctrl, _ = game
    hw.verify_physical_board.side_effect = [True, False]
    assert submit(ctrl,'r',((0,6),(0,5)))
    settle(hw)
    assert s.board_revision == 0 and s.turn == 'r' and s.pending_move is not None
    assert s.physical_sync_fault and s.move_sync_error
    ctrl.room.generation = 'reconnected'
    ctrl.tick()
    assert not submit(ctrl,'r',((0,6),(0,5)))
    assert hw.execute_piece_move.call_count == 1


def test_pre_motion_camera_failure_preserves_same_move_for_host_v_retry(game):
    s, hw, ctrl, _ = game
    hw.verify_physical_board.side_effect = [False]
    assert submit(ctrl,'r',((0,6),(0,5)))
    settle(hw)
    assert s.visual_pick_retry and not s.physical_sync_fault
    assert s.pending_ai_move['move'] == ((0,6),(0,5))
    assert not submit(ctrl,'r',((2,6),(2,5)))
    hw.execute_piece_move.assert_not_called()


@pytest.mark.parametrize('environment', ['VIRTUAL','PHYSICAL'])
def test_dedicated_profile_keeps_robot_execution_and_disables_ai(environment):
    p = make_profile(ROBOT_PVP_MODE, environment)
    assert p.robot_moves_enabled and p.mouse_input == 'ROBOT_COMMANDS'
    assert not p.ai_enabled and not p.self_play_enabled
    assert p.physical_robot_enabled is (environment == 'PHYSICAL')
    assert p.match_names == ('Người chơi Đỏ','Người chơi Đen')
    old = make_profile('HUMAN_VS_HUMAN','PHYSICAL')
    assert old.dry_run and not old.robot_moves_enabled
    with pytest.raises(ValueError):
        make_profile(ROBOT_PVP_MODE, environment, simulation_enabled=False)


@pytest.mark.parametrize('turn',['r','b'])
def test_host_surrender_belongs_to_red_even_during_black_turn(game, turn):
    from src.ui.input_handler import InputHandler
    from src.ui.board_renderer import BTN_SURRENDER_RECT
    s, hw, ctrl, _ = game
    s.turn = turn
    InputHandler(s,hw).handle_mouse_down(*BTN_SURRENDER_RECT.center)
    assert s.game_over and s.winner == 'b'
    hw.execute_piece_move.assert_not_called()


def test_host_selection_cannot_cross_a_board_revision(game):
    s, hw, ctrl, _ = game
    assert ctrl.handle_click(0,6)
    s.board_revision += 1
    assert not ctrl.handle_click(0,5)
    assert s.selected_pos is None
    hw.execute_piece_move.assert_not_called()


def test_post_commit_camera_baseline_stays_on_motion_worker(game):
    s, hw, ctrl, _ = game
    threads = []
    hw.capture_baseline_if_needed.side_effect = lambda **kw: threads.append(threading.current_thread().name) or True
    assert submit(ctrl,'r',((0,6),(0,5)))
    settle(hw)
    assert s.board_revision == 1 and threads == ['xiangqi-motion']


@pytest.mark.parametrize('exception', [False, True])
def test_baseline_failure_keeps_committed_move_and_pauses_next_gui_turn(game, exception):
    s, hw, ctrl, _ = game
    if exception:
        hw.capture_baseline_if_needed.side_effect = RuntimeError('camera unavailable')
    else:
        hw.capture_baseline_if_needed.return_value = False
    assert submit(ctrl,'r',((0,6),(0,5)))
    settle(hw)
    assert s.board_revision == 1 and s.turn == 'b' and s.pending_move is None
    assert s.manual_override_active and s.snapshot_continue_required
    assert not submit(ctrl,'b',((0,3),(0,4)))
    assert hw.execute_piece_move.call_count == 1


@pytest.mark.parametrize('route', ['V','CONTINUE'])
def test_verified_camera_resume_clears_startup_pause_and_persists_without_motion(game, route):
    from src.ui.input_handler import InputHandler
    s, hw, ctrl, _ = game
    hw.cam_monitor = object()
    hw.yolo_detector = object()
    s.snapshot_continue_required = s.manual_override_active = True
    assert ctrl._blocked()
    handler = InputHandler(s,hw)
    if route == 'V':
        assert handler.resume_automatic_scanning()
    else:
        assert handler._continue_after_snapshot_pause()
    assert not s.snapshot_continue_required and not s.manual_override_active
    assert ctrl._blocked() is None
    phase = s._journal._db.execute('SELECT phase FROM current_session WHERE id=1').fetchone()[0]
    assert phase == 'OPERATOR_RESUMED_ROBOT_PVP_CAMERA'
    assert s.board_revision == 0 and s.pending_move is None
    hw.execute_piece_move.assert_not_called()


@pytest.mark.parametrize('failure', ['mismatch','baseline','controller','pending','storage','new_stop'])
def test_camera_resume_keeps_pause_when_unresolved_conditions_remain(game, failure):
    from src.ui.input_handler import InputHandler
    s, hw, ctrl, _ = game
    hw.cam_monitor = hw.yolo_detector = object()
    s.snapshot_continue_required = s.manual_override_active = True
    if failure == 'mismatch':
        hw.verify_physical_board.side_effect = None
        hw.verify_physical_board.return_value = False
    elif failure == 'baseline':
        hw.capture_baseline_if_needed.return_value = False
    elif failure == 'controller':
        s.recovery_required = s.physical_sync_fault = True
        hw.physical_telemetry_ready = Mock(return_value=False)
        hw.physical_recovery_block_reason = lambda: 'Controller error: main=1, sub=29'
    elif failure == 'pending':
        move = ((0,6),(0,5))
        s.mark_move_pending(s.create_move_context(*move,MoveActor.ROBOT))
    elif failure == 'new_stop':
        def stopped(**kw):
            hw.stop_coordinator.generation += 1
            return True
        hw.capture_baseline_if_needed.side_effect = stopped
    else:
        s.persist_checkpoint = Mock(side_effect=RuntimeError('storage unavailable'))
    assert not InputHandler(s,hw).resume_automatic_scanning()
    assert s.snapshot_continue_required and s.manual_override_active
    assert ctrl._blocked() and s.board_revision == 0
    hw.execute_piece_move.assert_not_called()
