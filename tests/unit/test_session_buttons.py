"""Deferred end/reset and late stop acknowledgement; no hardware actuation."""
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import config
from src.core.game_state import GameState
from src.core.motion_worker import MotionWorker
from src.core.session_control import SessionControl
from src.core.session_profile import make_profile
from src.hardware.controlled_stop import ControlledStopCoordinator, StopRequest, StopResult
from src.ui.input_handler import InputHandler
from src.ui.board_renderer import BTN_SURRENDER_RECT
from src.domain.game_move import MoveActor


@pytest.fixture
def session(monkeypatch,tmp_path):
    monkeypatch.setattr(config,'GAME_MODE','HUMAN_VS_HUMAN_ROBOT')
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient',lambda *a:Mock(token=None,room_id=None))
    s=GameState();s.session_profile=make_profile(config.GAME_MODE,'PHYSICAL')
    s.attach_journal(tmp_path,'PHYSICAL',config.GAME_MODE,fresh_start=True)
    robot=SimpleNamespace(physical_motion_authorized=True,_activation_owned=False,
        _gripper_pulse_active=False,latch_motion_stop=Mock(),send_controlled_stop=Mock(return_value=0))
    hw=SimpleNamespace(robot=robot,game_state=s,dry_run=False,simulation_runtime=None,
        profile=s.session_profile,config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL'),
        _piece_move_lock=threading.Lock(),motion_worker=MotionWorker(),capture_baseline_if_needed=Mock(return_value=True))
    hw.backend=SimpleNamespace(get_state_snapshot=Mock(side_effect=lambda:SimpleNamespace(
        connected=True,joints_valid=True,measurement_timestamp=time.time(),motion_state='IDLE')))
    hw.stop_coordinator=ControlledStopCoordinator(hw)
    hw.request_controlled_stop=hw.stop_coordinator.begin
    ctl=SessionControl(s,hw,None)
    yield s,hw,ctl
    hw.motion_worker.close()
    if hw.stop_coordinator.request and hw.stop_coordinator.request.thread:
        hw.stop_coordinator.request.thread.join(2)
    s.close_journal()


def until(ctl,hw,wanted,timeout=3):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        hw.motion_worker.poll()
        if ctl.poll()==wanted:return
        time.sleep(.01)
    raise AssertionError(ctl.state.status_message)


def test_surrender_click_is_accepted_during_busy_worker_then_ends_once(session):
    s,hw,ctl=session
    release=threading.Event()
    hw.motion_worker.start(lambda:release.wait(2),lambda *a:None)
    handler=InputHandler(s,hw);handler.session_control=ctl
    try:
        handler.handle_mouse_down(*BTN_SURRENDER_RECT.center)
        assert ctl.action=='surrender' and not s.game_over
        ctl.poll()
        hw.robot.send_controlled_stop.assert_not_called()  # Let current piece finish first.
    finally:release.set()
    until(ctl,hw,'surrender')
    assert s.game_over and s.winner=='b' and s.game_over_reason=='RESIGN'
    assert s._match_end_intent==dict(winner='BLACK',reason='RESIGN')
    assert not ctl.request_surrender('b')
    hw.robot.send_controlled_stop.assert_called_once()


def test_surrender_is_accepted_at_pick_retry_and_waits_for_reconciliation(session):
    s,hw,ctl=session
    move=((0,6),(0,5));s.mark_move_pending(s.create_move_context(*move,MoveActor.ROBOT))
    s.visual_pick_retry={'stage':'pre_pick'}
    handler=InputHandler(s,hw);handler.session_control=ctl
    handler.handle_mouse_down(*BTN_SURRENDER_RECT.center)
    assert ctl.action=='surrender'
    ctl.poll();assert ctl.stop.done.wait(2)
    ctl.poll()
    assert not s.game_over and s.pending_move is not None
    assert 'đối soát' in s.status_message
    s.clear_pending_ai_move()  # Stands in for the existing verified-old-board recovery.
    until(ctl,hw,'surrender')
    assert s.game_over


def test_new_game_completes_after_worker_outlasts_initial_acknowledged_stop_wait(session):
    s,hw,ctl=session
    release=threading.Event()
    hw.motion_worker.start(lambda:release.wait(2),lambda *a:None)
    hw.request_controlled_stop=lambda reason,workers_finished=None:hw.stop_coordinator.begin(
        reason,workers_finished,timeout=.05)
    ctl.request('reset')
    try:
        assert ctl.stop.done.wait(2)
        assert not ctl.stop.result.safe and ctl.stop.result.acknowledged
    finally:release.set()
    until(ctl,hw,'reset')
    assert not s.game_over and s.turn=='r' and s.board_revision==0
    assert s.physical_sync_fault and s.snapshot_continue_required  # New opening still needs camera.
    hw.robot.send_controlled_stop.assert_called_once()  # No stop replay or power cycle.


@pytest.mark.parametrize('condition',['unacknowledged','error','stale','duplicate','gripper'])
def test_stop_refresh_never_bypasses_missing_safety_evidence(session,condition):
    s,hw,ctl=session
    req=StopRequest('reset');req.requires_measurements=True
    req.finish(StopResult(False,condition!='unacknowledged','original stop uncertainty'))
    hw.stop_coordinator.request=req
    if condition=='error':
        hw.backend.get_state_snapshot.side_effect=lambda:SimpleNamespace(
            connected=True,joints_valid=True,measurement_timestamp=time.time(),motion_state='ERROR')
    elif condition in ('stale','duplicate'):
        stamp=time.time()-2 if condition=='stale' else time.time()
        hw.backend.get_state_snapshot.side_effect=lambda:SimpleNamespace(
            connected=True,joints_valid=True,measurement_timestamp=stamp,motion_state='IDLE')
    elif condition=='gripper':hw.robot._gripper_pulse_active=True
    for _ in range(3):
        hw.stop_coordinator._next_settle_probe=0
        assert not hw.stop_coordinator.refresh_acknowledged_stop()
    assert not req.result.safe
    hw.robot.send_controlled_stop.assert_not_called()


def test_new_game_never_discards_unresolved_physical_transaction(session):
    s,hw,ctl=session
    s.mark_move_pending(s.create_move_context((0,6),(0,5),MoveActor.ROBOT))
    pending=s.pending_move
    ctl.request('reset');assert ctl.stop.done.wait(2)
    ctl.poll()
    assert s.pending_move is pending and not hw.motion_worker.busy
    assert 'V đối soát' in s.status_message


def test_v_during_deferred_surrender_only_reconciles_and_never_retries_motion(session):
    import pygame
    s,hw,ctl=session
    s.mark_move_pending(s.create_move_context((0,6),(0,5),MoveActor.ROBOT))
    s.visual_pick_retry={'stage':'pre_pick'}
    ctl.request_surrender('b');ctl.poll();assert ctl.stop.done.wait(2)
    handler=InputHandler(s,hw);handler.session_control=ctl
    handler._reconcile_physical_sync_fault=Mock()
    handler._retry_visual_pick=Mock(side_effect=AssertionError('unexpected motion retry'))
    handler.handle_keyboard(pygame.K_v)
    deadline=time.monotonic()+2
    while hw.motion_worker.busy and time.monotonic()<deadline:
        hw.motion_worker.poll();time.sleep(.005)
    handler._reconcile_physical_sync_fault.assert_called_once()
    handler._retry_visual_pick.assert_not_called()


def test_y_and_continue_cannot_restart_motion_during_deferred_surrender(session):
    import pygame
    from src.ui.board_renderer import BoardRenderer
    s,hw,ctl=session
    s.mark_move_pending(s.create_move_context((0,6),(0,5),MoveActor.ROBOT))
    s.visual_pick_retry={'stage':'pre_pick'}
    ctl.request_surrender('b');ctl.poll();assert ctl.stop.done.wait(2)
    handler=InputHandler(s,hw);handler.session_control=ctl
    handler._retry_visual_pick=Mock(side_effect=AssertionError('unexpected motion retry'))
    handler._reconcile_physical_sync_fault=Mock()
    handler.handle_keyboard(pygame.K_y)
    assert not handler._retry_visual_pick.called
    rect=BoardRenderer.client_continue_rect(s.get_render_state())
    handler.handle_mouse_down(*rect.center)
    deadline=time.monotonic()+2
    while hw.motion_worker.busy and time.monotonic()<deadline:
        hw.motion_worker.poll();time.sleep(.005)
    handler._reconcile_physical_sync_fault.assert_called_once()


def test_surrender_keeps_terminal_outcome_already_committed_by_current_move(session):
    s,hw,ctl=session
    ctl.request_surrender('b')
    s.handle_game_over('r',reason='CHECKMATE')
    until(ctl,hw,'surrender')
    assert s.winner=='r' and s._match_end_intent==dict(winner='RED',reason='CHECKMATE')
