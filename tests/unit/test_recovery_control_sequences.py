"""Ending/recovery sequence regressions; all hardware endpoints are fakes."""
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest
import config
from src.core.game_state import GameState
from src.core.session_profile import make_profile
from src.core.session_control import SessionControl
from src.core.motion_worker import MotionWorker
from src.core import xiangqi
from src.hardware.hardware_manager import HardwareManager
from src.hardware.controlled_stop import ControlledStopCoordinator
from src.ui.input_handler import InputHandler
from src.domain.game_move import MoveActor
from src.core.visual_move_coordinator import pause_visual_pick
from src.vision.pick_consensus import PickTargetUnavailable

@pytest.fixture
def pending_session(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'GAME_MODE', 'HUMAN_VS_ROBOT')
    monkeypatch.setattr(config, 'SIMULATION_TOKEN', '')
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(token=None, room_id=None))
    s = GameState()
    s.session_profile = make_profile('HUMAN_VS_ROBOT', 'PHYSICAL')
    s.attach_journal(tmp_path, 'PHYSICAL', 'HUMAN_VS_ROBOT', fresh_start=True)
    # A legal black turn with an exact pre-pick retry, without any dispatch.
    s.turn = 'b'
    s.update_fen_from_board()
    move = ((0,3),(0,4))
    context = s.create_move_context(*move, MoveActor.ROBOT)
    s.mark_move_pending(context)
    expected, captured = xiangqi.make_temp_move(s.board, move)
    s.set_pending_physical_move(move, expected, '.', 'b')
    pause_visual_pick(s, PickTargetUnavailable('test: no stable centre', 'pre_pick'))
    hw = HardwareManager.__new__(HardwareManager)
    hw.profile = s.session_profile
    hw.config = SimpleNamespace(ROBOT_BACKEND='PHYSICAL', GAME_ONLY=False)
    hw.dry_run = False
    hw.simulation_runtime = None
    hw.game_state = s
    hw._piece_move_lock = threading.Lock()
    hw.motion_worker = MotionWorker()
    hw.robot = SimpleNamespace(connected=True, physical_motion_authorized=True,
        _activation_owned=False, _gripper_pulse_active=False,
        latch_motion_stop=Mock(), send_controlled_stop=Mock(return_value=0))
    hw.backend = SimpleNamespace(get_state_snapshot=lambda: SimpleNamespace(
        connected=True, joints_valid=True, measurement_timestamp=time.time(), motion_state='IDLE', last_error=None))
    hw.stop_coordinator = ControlledStopCoordinator(hw)
    hw.physical_telemetry_ready = lambda **kw: True
    hw.capture_baseline_if_needed = Mock(return_value=True)
    hw.cam_monitor = SimpleNamespace()
    hw.yolo_detector = None
    hw.verify_physical_board = Mock(return_value=True)
    hw.execute_piece_move = Mock(side_effect=AssertionError('No physical motion permitted in this audit'))
    ctl = SessionControl(s,hw,None)
    handler = InputHandler(s,hw)
    handler.session_control = ctl
    yield s,hw,ctl,handler
    hw.motion_worker.close()
    if hw.stop_coordinator.request is not None and hw.stop_coordinator.request.thread is not None:
        hw.stop_coordinator.request.thread.join(2)
    s.close_journal()


def settle(hw):
    end = time.monotonic()+3
    while hw.motion_worker.busy and time.monotonic()<end:
        hw.motion_worker.poll()
        time.sleep(.005)
    assert not hw.motion_worker.busy

@pytest.mark.parametrize('action',['reset','surrender','home'])
def test_v_after_end_request_reconciles_the_pre_pick_transaction(pending_session, action):
    s,hw,ctl,handler = pending_session
    if action=='surrender':
        ctl.request_surrender('b')
        ctl.poll()
    else:
        ctl.request(action)
    assert ctl.stop.done.wait(2) and ctl.stop.result.safe
    handler.handle_keyboard(pygame.K_v)
    settle(hw)
    hw.execute_piece_move.assert_not_called()
    assert s.pending_move is None, f'{action}: V retained the transaction: {s.status_message}'
    assert s.pending_ai_move is None
    if action == 'home':
        assert ctl.poll() == 'home'


@pytest.mark.parametrize('action',['home','reset','surrender'])
def test_y_during_ending_must_not_enter_move_retry(pending_session, action, monkeypatch):
    s,hw,ctl,handler = pending_session
    retry=Mock()
    monkeypatch.setattr(handler,'_retry_visual_pick',retry)
    if action=='surrender':
        ctl.request_surrender('b');ctl.poll()
    else: ctl.request(action)
    assert ctl.stop.done.wait(2)
    handler.handle_keyboard(pygame.K_y)
    retry.assert_not_called()


def test_board_only_pause_can_resume_using_continue(pending_session):
    s,hw,ctl,handler = pending_session
    s.clear_pending_ai_move()
    s.session_profile=hw.profile=make_profile('HUMAN_VS_ROBOT','VIRTUAL',simulation_enabled=False,viewer_enabled=False)
    hw.config=SimpleNamespace(ROBOT_BACKEND='VIRTUAL',GAME_ONLY=True)
    hw.dry_run=True
    ctl.request('pause')
    assert ctl.stop.done.wait(2)
    ctl.poll()
    assert s.snapshot_continue_required
    from src.ui.board_renderer import BoardRenderer
    rect=BoardRenderer.client_continue_rect(s.get_render_state())
    handler.handle_mouse_down(*rect.center)
    settle(hw)
    assert not s.snapshot_continue_required and not s.manual_override_active

@pytest.mark.parametrize('key',[pygame.K_m,pygame.K_t,pygame.K_h,pygame.K_SPACE,pygame.K_z,pygame.K_F4,pygame.K_v,pygame.K_F12])
def test_busy_input_handler_has_no_side_effect(pending_session,key,monkeypatch):
    s,hw,ctl,handler=pending_session
    release=threading.Event()
    hw.motion_worker.start(lambda: release.wait(2), lambda *a:None)
    before=(s.current_fen,s.pending_move,s.visual_pick_retry,s.emergency_mode,s.pick_test_mode)
    try:
        for _ in range(3):handler.handle_keyboard(key)
        assert (s.current_fen,s.pending_move,s.visual_pick_retry,s.emergency_mode,s.pick_test_mode)==before
        hw.execute_piece_move.assert_not_called()
    finally:
        release.set();settle(hw)


@pytest.mark.parametrize('action', ['home','reset','surrender'])
def test_v_during_end_request_routes_pending_test_to_test_reconciliation(pending_session, monkeypatch, action):
    s,hw,ctl,handler = pending_session
    s.clear_pending_ai_move()
    s.pending_test_motion = {'context': object()}
    test_reconcile = Mock()
    game_reconcile = Mock(side_effect=AssertionError('Wrong recovery path for a manual-test transaction'))
    monkeypatch.setattr(handler, '_reconcile_pick_test', test_reconcile)
    monkeypatch.setattr(handler, '_reconcile_physical_sync_fault', game_reconcile)
    if action == 'surrender':
        ctl.request_surrender('b'); ctl.poll()
    else:
        ctl.request(action)
    assert ctl.stop.done.wait(2) and ctl.stop.result.safe
    handler.handle_keyboard(pygame.K_v)
    settle(hw)
    test_reconcile.assert_called_once()
    game_reconcile.assert_not_called()
    hw.execute_piece_move.assert_not_called()


def test_home_reconciliation_waits_for_stop_proof(pending_session):
    s,hw,ctl,handler = pending_session
    hw.backend = SimpleNamespace(get_state_snapshot=lambda: SimpleNamespace(
        connected=True, joints_valid=True, measurement_timestamp=time.time()-5, motion_state='IDLE', last_error=None))
    # A completed stop request alone must not replace fresh idle measurements.
    from src.hardware.controlled_stop import StopRequest, StopResult
    ctl.action = 'home'
    request = StopRequest('home'); request.requires_measurements = True
    request.finish(StopResult(True, True, 'Historical stop ACK'))
    hw.stop_coordinator.request = request
    pending = s.pending_move
    handler.handle_keyboard(pygame.K_v)
    assert s.pending_move is pending
    hw.verify_physical_board.assert_not_called()
    hw.execute_piece_move.assert_not_called()


@pytest.mark.parametrize('fault', ['physical_sync_fault', 'move_sync_error'])
def test_visible_clear_error_click_passes_retained_retry_guard(pending_session, monkeypatch, fault):
    s,hw,ctl,handler = pending_session
    setattr(s, fault, True if fault == 'physical_sync_fault' else 'Retry failed after stop')
    clear = Mock()
    monkeypatch.setattr(handler, '_clear_failed_session', clear)
    from src.ui.board_renderer import BoardRenderer
    rect = next(rect for rect, key, *_ in BoardRenderer.client_action_controls(s.get_render_state())
                if key == pygame.K_F12)
    handler.handle_mouse_down(*rect.center)
    settle(hw)
    clear.assert_called_once()
    hw.execute_piece_move.assert_not_called()


def test_clear_error_click_retains_controller_fault_gate(pending_session):
    s,hw,ctl,handler = pending_session
    s.physical_sync_fault = True
    hw.physical_telemetry_ready = lambda **kw: False
    hw.physical_recovery_block_reason = lambda: 'injected controller error'
    pending = s.pending_move
    from src.ui.board_renderer import BoardRenderer
    rect = next(rect for rect, key, *_ in BoardRenderer.client_action_controls(s.get_render_state())
                if key == pygame.K_F12)
    handler.handle_mouse_down(*rect.center)
    settle(hw)
    assert s.pending_move is pending and s.physical_sync_fault
    assert 'injected controller error' in s.status_message
    hw.execute_piece_move.assert_not_called()
