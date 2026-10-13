"""Independent lifecycle edge probes; hardware and all external HTTP are mocked."""
import atexit
from copy import deepcopy
import inspect
import os
from pathlib import Path
import runpy
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import config
from src.core import xiangqi
from src.core.game_state import GameState
from src.core.human_move_commit_coordinator import HumanMoveCommitCoordinator
from src.domain.game_move import piece_symbol_for_identity


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr(config,'GAME_MODE','HUMAN_VS_HUMAN')
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient',lambda *a:Mock(room_id=None))
    return GameState(allow_mouse_move=True)


def install_mate_board(state, color='r', capture=False):
    board=[['.']*9 for _ in range(10)]
    board[0][4]='b_K'; board[9][4]='r_K';board[6][4]='r_P'
    board[2][4 if capture else 0]='r_R'
    board[1][3]='r_R';board[2][6]='r_N'
    if color=='b':
        board=[[p.replace('r_','x_').replace('b_','r_').replace('x_','b_') for p in row]
               for row in reversed(board)]
    pools={}
    for piece_id in state.piece_ids.values():
        pools.setdefault(piece_symbol_for_identity(piece_id),[]).append(piece_id)
    state.board=board
    state.piece_ids={(r,c):pools[p].pop() for r,row in enumerate(board) for c,p in enumerate(row) if p!='.'}
    state.turn=color
    state.update_fen_from_board()
    if color=='r':
        return ((4,2),(4,0)) if capture else ((0,2),(4,2))
    return ((4,7),(4,9)) if capture else ((0,7),(4,7))


@pytest.mark.parametrize('color',['r','b'])
@pytest.mark.parametrize('capture',[False,True])
def test_human_terminal_move_finishes_and_publishes_after_fen(state,color,capture):
    move=install_mate_board(state,color,capture)
    assert xiangqi.is_valid_move(*move,state.board,color)
    expected,_=xiangqi.make_temp_move(state.board,move)
    other='b' if color=='r' else 'r'
    assert xiangqi.get_king_pos(other,expected) is None or not xiangqi.find_all_valid_moves(other,expected)
    request=SimpleNamespace(turn_token=(state.game_epoch,state.human_commit_generation),move=move)
    coordinator=HumanMoveCommitCoordinator(state)
    assert coordinator.try_commit(request)=='ACCEPTED'
    assert state.game_over and state.winner==color
    assert [c[0] for c in state.api_client.method_calls]==['send_move_update_board','end_match']
    state.api_client.end_match.assert_called_once_with(winner='RED' if color=='r' else 'BLACK',reason='CHECKMATE')
    assert coordinator.try_commit(request)=='DUPLICATE'
    assert len(state.move_history)==1


def test_rollback_then_undo_cannot_restore_a_cancelled_future(state):
    hw=SimpleNamespace(config=SimpleNamespace(GAME_ONLY=True,ROBOT_BACKEND='VIRTUAL'),dry_run=True,
                       simulation_runtime=None)
    assert state.process_human_move((4,6),(4,5),'r_P')
    before=deepcopy(state.history_snapshots)
    state.save_rollback_state()
    assert state.process_human_move((0,3),(0,4),'b_P')
    state.handle_rollback(hw)
    assert state.history_snapshots==before
    assert state.undo_round(hw)
    assert state.board==xiangqi.get_board() and state.turn=='r'
    assert not state.move_history and not state.history_snapshots


@pytest.mark.parametrize('operation',['human','emergency'])
def test_finished_state_rejects_direct_move_without_mutation(state,operation):
    state.game_over=True
    before=(deepcopy(state.board),dict(state.piece_ids),state.current_fen)
    method=state.process_human_move if operation=='human' else state.process_emergency_move
    assert method((4,6),(4,5),'r_P') is False
    assert (state.board,state.piece_ids,state.current_fen)==before
    assert not state.history_snapshots and not state.api_client.method_calls


def test_illegal_emergency_black_move_preserves_pending_recovery(state):
    state.turn='b'
    pending={'move':((0,3),(0,4))}
    state.pending_ai_move=pending
    before=deepcopy(state.board)
    assert state.process_emergency_move((0,3),(0,5),'b_P') is False
    assert state.board==before and state.pending_ai_move is pending
    assert not state.api_client.method_calls


def test_unconfirmed_turn_rejects_human_commit(state):
    state.turn_confirmation_required=True
    before=deepcopy(state.board)
    assert state.process_human_move((4,6),(4,5),'r_P') is False
    assert state.board==before and not state.move_history


def test_rejected_red_emergency_does_not_discard_pending_recovery(state):
    state.physical_sync_fault=True
    pending={'move':((0,3),(0,4))}
    state.pending_ai_move=pending
    assert state.process_emergency_move((4,6),(4,5),'r_P') is False
    assert state.pending_ai_move is pending
    assert state.board==xiangqi.get_board()


@pytest.mark.parametrize('capture',[False,True])
def test_emergency_black_terminal_move_publishes_once(state,capture):
    move=install_mate_board(state,'b',capture)
    assert state.process_emergency_move(*move,'b_R') is True
    assert state.game_over and state.winner=='b'
    state.api_client.end_match.assert_called_once_with(winner='BLACK',reason='CHECKMATE')
    assert [c[0] for c in state.api_client.method_calls]==['send_move_update_board','end_match']


def test_emergency_scene_rejection_keeps_new_fen_and_error_without_publishing(state):
    state.turn='b'
    state.set_board_observer(Mock(return_value=False))
    assert state.process_emergency_move((0,3),(0,4),'b_P') is False
    assert state.board[4][0]=='b_P' and state.current_fen.split()[1]=='w'
    assert state.physical_sync_fault and state.move_sync_error and state.snapshot_continue_required
    assert not state.api_client.method_calls


def test_mouse_emergency_rejection_does_not_install_camera_baseline(state,monkeypatch):
    from src.ui.input_handler import InputHandler
    from src.ui.board_renderer import BoardRenderer
    monkeypatch.setattr(config,'PLAYER_TURN_MODE','LEGACY',raising=False)
    state.turn='b';state.emergency_mode=True;state.manual_override_active=True
    state.process_emergency_move=Mock(return_value=False)
    hw=SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND='VIRTUAL'),dry_run=True,
                       cam_monitor=object(),yolo_detector=None,capture_baseline_if_needed=Mock())
    handler=InputHandler(state,hw)
    monkeypatch.setattr(BoardRenderer,'pixel_to_grid',Mock(side_effect=[(0,3),(0,4)]))
    handler.handle_mouse_down(0,0);handler.handle_mouse_down(0,0)
    state.process_emergency_move.assert_called_once_with((0,3),(0,4),'b_P')
    hw.capture_baseline_if_needed.assert_not_called()


def test_camera_quit_cannot_dispatch_ready_ai_move_in_same_frame(tmp_path,monkeypatch):
    os.environ.setdefault('SDL_VIDEODRIVER','dummy');os.environ.setdefault('SDL_AUDIODRIVER','dummy')
    import pygame
    from src.core.motion_worker import MotionWorker
    from src.ui.board_renderer import BoardRenderer
    for name in ('DRY_RUN','ROBOT_BACKEND','GAME_ONLY','GAME_MODE','TELEMETRY_PORT'):
        monkeypatch.setattr(config,name,getattr(config,name,None),raising=False)
    monkeypatch.setattr(config,'AUTO_MOVE_CONFIRM_ENABLED',False)
    monkeypatch.setattr(sys,'argv',['main.py','--virtual','--log-dir',str(tmp_path/'logs')])
    monkeypatch.setattr(sys,'path',list(sys.path))
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient',lambda *a:Mock(room_id=None))
    execute=Mock(return_value=False)
    monkeypatch.setattr('src.core.ai_execution.execute_ai_move',execute)
    callbacks=[]
    monkeypatch.setattr(atexit,'register',lambda f,*a,**kw:callbacks.append(f))
    selected=[False]
    def camera_key():
        g=inspect.currentframe().f_back.f_globals
        ready=(g.get('hw') is not None and not g['hw'].motion_worker.busy
               and not g.get('difficulty_menu_active'))
        return ord('q') if selected[0] and ready else -1
    def build(cfg,options,root,game,*args):
        assert game.process_human_move((4,6),(4,5),'r_P')
        game.ai_thinking=True
        game.ai_thread=SimpleNamespace(is_alive=lambda:False)
        game.ai_started_for_human_commit_generation=game.human_commit_generation
        token=(game.game_epoch,game.ai_epoch,game.human_commit_generation)
        game.ai_job_token=token;game.ai_results[token]=((0,3),(0,4))
        def choose(*a):
            selected[0]=True
            return True,'Mock engine'
        hw=SimpleNamespace(config=cfg,dry_run=True,is_robot_ready=True,simulation_runtime=None,
            motion_worker=MotionWorker(),cam_monitor=SimpleNamespace(update_display=camera_key),
            capture_baseline_if_needed=Mock(return_value=True),cleanup=Mock(),
            select_difficulty=choose,difficulty_availability=lambda:dict.fromkeys(['easy','medium','hard','impossible'],True))
        return hw,None,None,None
    monkeypatch.setattr('src.core.session_startup.build_session',build)
    phase=[0];deadline=time.monotonic()+10
    def events():
        assert time.monotonic()<deadline,'mock GUI stalled'
        g=inspect.currentframe().f_back.f_globals
        if phase[0]==0:
            phase[0]=1
            return [pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN)]
        if phase[0]==1 and g.get('difficulty_menu_active'):
            phase[0]=2
            return [pygame.event.Event(pygame.KEYDOWN,key=pygame.K_1)]
        return []
    monkeypatch.setattr(pygame.event,'get',events)
    try:
        app=runpy.run_path(str(Path(__file__).resolve().parents[2]/'main.py'),run_name='__main__')
        execute.assert_not_called()
        assert app['state'].last_move==((4,6),(4,5))
    finally:
        for cb in reversed(callbacks):cb()
        pygame.quit()
