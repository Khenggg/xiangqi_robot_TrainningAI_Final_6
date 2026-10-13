"""Adversarial scheduling and retry probes; all hardware/HTTP mocked."""
import atexit
import inspect
import os
from pathlib import Path
import runpy
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import config
from src.core import xiangqi
from src.core.ai_execution import execute_ai_move
from src.core.game_state import GameState
from src.core.motion_worker import MotionWorker
from src.core.self_play_controller import SelfPlayController, SelfPlayStatus
from src.motion.result import MotionExecutionResult
from src.ui.input_handler import InputHandler
from src.vision.pick_consensus import PickTargetUnavailable
from src.vision.visual_pick_estimator import GridTarget


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a: Mock(room_id=None))
    return GameState()


def hardware(physical=False):
    return SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL' if physical else 'VIRTUAL',
        VISUAL_PICK_ENABLED=physical, GAME_ONLY=False), dry_run=not physical,
        simulation_runtime=None if physical else object(), is_robot_ready=True,
        cam_monitor=object(), yolo_detector=None,
        ai_ctrl=SimpleNamespace(pick_move=Mock(return_value=((4,6),(4,5)))),
        verify_physical_board=Mock(return_value=True), is_cell_visually_clear=Mock(return_value=True),
        execute_piece_move=Mock(return_value=MotionExecutionResult.ok()),
        get_robot_center_pick_targets=Mock(side_effect=lambda cells: {k: GridTarget(*v,.99,0) for k,v in cells.items()}),
        capture_baseline_if_needed=Mock(return_value=True))


@pytest.mark.parametrize('phase',['thinking','moving'])
def test_f6_cannot_discard_a_completed_unpolled_worker(state,phase):
    hw=hardware(); ctrl=SelfPlayController(state,hw)
    assert ctrl.start() and ctrl.request_next_move()
    ctrl._thread.join(2); assert not ctrl._thread.is_alive()
    if phase=='moving':
        ctrl.tick(); assert ctrl.status is SelfPlayStatus.MOVING
        ctrl._thread.join(2); assert not ctrl._thread.is_alive()
    before=(ctrl.status,ctrl._epoch,ctrl._result,state.pending_ai_move,state.pending_move)
    assert not ctrl.start(), 'F6 reset a worker result before tick consumed it'
    assert (ctrl.status,ctrl._epoch,ctrl._result,state.pending_ai_move,state.pending_move)==before
    if phase=='thinking':
        ctrl.tick(); ctrl._thread.join(2)
    ctrl.tick()
    assert state.last_move==((4,6),(4,5)) and len(state.move_history)==1
    hw.execute_piece_move.assert_called_once()


@pytest.mark.parametrize('stage',['pre_pick','capture_removed'])
def test_f6_preserves_a_paused_pick_checkpoint(state,stage):
    hw=hardware(); ctrl=SelfPlayController(state,hw); assert ctrl.start()
    if stage=='capture_removed':
        state.board[3][4]='.';state.board[5][4]='b_P'
        state.piece_ids[(5,4)]=state.piece_ids.pop((3,4))
        state.update_fen_from_board()
    context=state.create_move_context((4,6),(4,5),'ROBOT')
    state.mark_move_pending(context)
    expected,_=xiangqi.make_temp_move(state.board,((4,6),(4,5)))
    state.set_pending_physical_move(((4,6),(4,5)),expected,'b_P' if stage=='capture_removed' else '.','r')
    from src.core.visual_move_coordinator import pause_visual_pick,signature
    if stage=='capture_removed':
        state.visual_capture_checkpoint=dict(pending=state.pending_ai_move,signature=signature(state))
    pause_visual_pick(state,PickTargetUnavailable('unstable source',stage))
    ctrl.status=SelfPlayStatus.PICK_PAUSED
    request=state.visual_pick_retry; checkpoint=state.visual_capture_checkpoint
    assert not ctrl.start()
    assert ctrl.status is SelfPlayStatus.PICK_PAUSED and state.visual_pick_retry is request
    assert state.visual_capture_checkpoint is checkpoint
    hw.execute_piece_move.assert_not_called()


def test_new_selfplay_controller_does_not_replace_another_pending_move(state):
    hw=hardware()
    state.mark_move_pending(state.create_move_context((4,6),(4,5),'ROBOT'))
    expected,_=xiangqi.make_temp_move(state.board,((4,6),(4,5)))
    state.set_pending_physical_move(((4,6),(4,5)),expected,'.','r')
    ctrl=SelfPlayController(state,hw);context=state.pending_move;pending=state.pending_ai_move
    assert not ctrl.start() and ctrl.status is SelfPlayStatus.IDLE
    assert state.pending_move is context and state.pending_ai_move is pending
    hw.verify_physical_board.assert_not_called()
    hw.execute_piece_move.assert_not_called()


@pytest.mark.parametrize('phase',['ready_step','ready_continuous','thinking_done'])
def test_selfplay_defers_dispatch_while_ui_worker_owns_a_job(state,phase):
    hw=hardware(); ctrl=SelfPlayController(state,hw)
    assert ctrl.start(run_mode='continuous' if phase=='ready_continuous' else 'step')
    if phase=='thinking_done':
        assert ctrl.request_next_move(); ctrl._thread.join(2)
        assert not ctrl._thread.is_alive()
    worker=hw.motion_worker=MotionWorker();release=threading.Event()
    assert worker.start(lambda:release.wait(2),lambda *args:None)
    before=(ctrl.status,ctrl._result,ctrl._epoch,state.pending_ai_move)
    try:
        assert not ctrl.request_next_move()
        ctrl.tick()
        assert (ctrl.status,ctrl._result,ctrl._epoch,state.pending_ai_move)==before
        hw.execute_piece_move.assert_not_called()
    finally:
        release.set();worker.close()
        assert worker.poll() and not worker.busy
    if phase=='thinking_done':
        ctrl.tick()
    else:
        assert ctrl.request_next_move();ctrl._thread.join(2);ctrl.tick()
    ctrl._thread.join(2);ctrl.tick()
    hw.execute_piece_move.assert_called_once()
    assert len(state.move_history)==1


def paused_retry(state,hw,move):
    hw.get_robot_center_pick_targets.side_effect=PickTargetUnavailable('unstable center')
    assert not execute_ai_move(state,hw,move,visual_pick_enabled=True)
    assert state.visual_pick_retry and not state.physical_sync_fault
    hw.get_robot_center_pick_targets.side_effect=lambda cells:{k:GridTarget(*v,.99,0) for k,v in cells.items()}
    return InputHandler(state,hw)


@pytest.mark.parametrize('failure',['false','exception'])
def test_retry_baseline_failure_pauses_game_after_preserving_commit(state,failure):
    state.turn='b'; state.update_fen_from_board(); hw=hardware(True)
    handler=paused_retry(state,hw,((4,3),(4,4)))
    if failure=='false': hw.capture_baseline_if_needed.return_value=False
    else: hw.capture_baseline_if_needed.side_effect=RuntimeError('camera disconnected')
    handler._retry_visual_pick()
    assert len(state.move_history)==1 and state.turn=='r' and state.pending_ai_move is None
    assert state.manual_override_active and state.snapshot_continue_required
    assert not state.snapshot_continue_can_commit_pending
    assert not state.physical_sync_fault, 'A confirmed move is retained; pause for baseline repair'
    hw.execute_piece_move.assert_called_once()
    hw.capture_baseline_if_needed.assert_called_once()
    assert not InputHandler(state,hw).poll_board_stability()


def test_retry_mirror_failure_does_not_refresh_baseline_or_replay_motion(state):
    state.turn='b'; state.update_fen_from_board(); hw=hardware(True)
    handler=paused_retry(state,hw,((4,3),(4,4)))
    state.set_board_observer(lambda *a:False)
    handler._retry_visual_pick()
    assert len(state.move_history)==1 and state.physical_sync_fault and state.move_sync_error
    hw.capture_baseline_if_needed.assert_not_called()
    handler._retry_visual_pick()
    hw.execute_piece_move.assert_called_once()


@pytest.mark.parametrize('color',['r','b'])
def test_terminal_retry_publishes_fen_then_end_once(state,color):
    board=[['.']*9 for _ in range(10)]
    board[0][4]='b_K';board[9][4]='r_K';board[6][4]='r_P'
    board[2][0]='r_R';board[1][3]='r_R';board[2][6]='r_N'
    if color=='b':
        board=[[p.replace('r_','x_').replace('b_','r_').replace('x_','b_') for p in row] for row in reversed(board)]
    from src.domain.game_move import piece_symbol_for_identity
    pools={}
    for identity in state.piece_ids.values(): pools.setdefault(piece_symbol_for_identity(identity),[]).append(identity)
    state.board=board;state.turn=color
    state.piece_ids={(r,c):pools[p].pop() for r,row in enumerate(board) for c,p in enumerate(row) if p!='.'}
    state.update_fen_from_board()
    move=((0,2),(4,2)) if color=='r' else ((0,7),(4,7))
    hw=hardware(True);handler=paused_retry(state,hw,move)
    handler._retry_visual_pick()
    assert state.game_over and state.winner==color and state.game_over_reason=='CHECKMATE'
    assert [c[0] for c in state.api_client.method_calls]==['send_move_update_board','end_match']
    state.api_client.end_match.assert_called_once_with(winner='RED' if color=='r' else 'BLACK',reason='CHECKMATE')
    handler._retry_visual_pick()
    hw.execute_piece_move.assert_called_once()
    hw.capture_baseline_if_needed.assert_not_called()


@pytest.mark.parametrize('trailing_key',['next','start'])
def test_window_quit_stops_dispatching_remaining_events(state,tmp_path,monkeypatch,trailing_key):
    os.environ.setdefault('SDL_VIDEODRIVER','dummy'); os.environ.setdefault('SDL_AUDIODRIVER','dummy')
    import pygame
    from src.ui.board_renderer import BoardRenderer
    for name in ('DRY_RUN','ROBOT_BACKEND','GAME_ONLY','GAME_MODE','TELEMETRY_PORT'):
        monkeypatch.setattr(config,name,getattr(config,name,None),raising=False)
    monkeypatch.setattr(config,'AUTO_MOVE_CONFIRM_ENABLED',False)
    monkeypatch.setattr(sys,'argv',['main.py','--virtual','--log-dir',str(tmp_path/'logs')])
    monkeypatch.setattr(sys,'path',list(sys.path))
    callbacks=[];monkeypatch.setattr(atexit,'register',lambda f,*a,**kw:callbacks.append(f))
    after_quit=[]; closing=[False]
    original_start=SelfPlayController.start; original_next=SelfPlayController.request_next_move
    def start(ctrl,*args,**kw):
        if closing[0]: after_quit.append('start')
        return original_start(ctrl,*args,**kw)
    def next_move(ctrl,*args,**kw):
        if closing[0]: after_quit.append('next')
        return original_next(ctrl,*args,**kw)
    monkeypatch.setattr(SelfPlayController,'start',start)
    monkeypatch.setattr(SelfPlayController,'request_next_move',next_move)
    def build(cfg,options,root,game,*args):
        hw=hardware(); hw.config=cfg;hw.simulation_runtime=None;hw.motion_worker=MotionWorker()
        hw.cam_monitor=None;hw.cleanup=Mock();hw.select_difficulty=lambda *a:(True,'Mock engine')
        hw.difficulty_availability=lambda:dict.fromkeys(['easy','medium','hard','impossible'],True)
        return hw,None,None,None
    monkeypatch.setattr('src.core.session_startup.build_session',build)
    monkeypatch.setattr(BoardRenderer,'home_action_from_pixel',lambda *a:'self_play')
    phase=[0];deadline=time.monotonic()+10
    def events():
        assert time.monotonic()<deadline,'Headless GUI stalled'
        g=inspect.currentframe().f_back.f_globals
        if phase[0]==0:
            phase[0]=1;return [pygame.event.Event(pygame.MOUSEBUTTONDOWN,pos=(0,0),button=1)]
        if phase[0]==1 and g.get('difficulty_menu_active'):
            phase[0]=2;return [pygame.event.Event(pygame.KEYDOWN,key=pygame.K_1)]
        ctrl=g.get('self_play');hw=g.get('hw')
        if phase[0]==2 and ctrl and ctrl.status is SelfPlayStatus.READY and not hw.motion_worker.busy:
            closing[0]=True;phase[0]=3
            return [pygame.event.Event(pygame.QUIT),pygame.event.Event(pygame.KEYDOWN,
                key=pygame.K_F7 if trailing_key=='next' else pygame.K_F6)]
        return []
    monkeypatch.setattr(pygame.event,'get',events)
    try:
        app=runpy.run_path(str(Path(__file__).resolve().parents[2]/'main.py'),run_name='__main__')
        assert not after_quit, 'Commands were dispatched after receiving window QUIT'
        app['hw'].execute_piece_move.assert_not_called()
    finally:
        for cb in reversed(callbacks): cb()
        pygame.quit()
