"""Second-pass failure probes through real game/recovery and main routing."""
import atexit
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
from src.core.self_play_controller import SelfPlayController, SelfPlayStatus
from src.domain.game_move import MoveActor
from src.ui.input_handler import InputHandler


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient', lambda *a:Mock(room_id=None))
    return GameState()


def test_recovery_commit_keeps_new_mirror_failure_visible(state):
    state.turn = 'b'
    move = ((0,3),(0,4))
    state.mark_move_pending(state.create_move_context(*move, MoveActor.ROBOT))
    expected, _ = xiangqi.make_temp_move(state.board,move)
    state.set_pending_physical_move(move,expected,'.','b')
    state.set_board_observer(Mock(return_value=False))
    hw = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL'),dry_run=False,
        capture_baseline_if_needed=Mock(return_value=True))
    handler = InputHandler(state,hw)
    assert handler._finalize_pending_ai_move('success',(0,120,0))
    assert state.board == expected and len(state.move_history) == 1
    assert state.physical_sync_fault and state.move_sync_error
    assert state.snapshot_continue_required and state.manual_override_active
    hw.capture_baseline_if_needed.assert_not_called()


def test_recovery_commit_clears_old_failure_when_new_mirror_sync_succeeds(state):
    state.turn='b'
    move=((0,3),(0,4))
    state.mark_move_pending(state.create_move_context(*move,MoveActor.ROBOT))
    expected,_=xiangqi.make_temp_move(state.board,move)
    state.set_pending_physical_move(move,expected,'.','b')
    state.move_sync_error='old motion reply lost'
    state.physical_sync_fault=True
    state.set_board_observer(Mock(return_value=True))
    hw=SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL'),dry_run=False,
        capture_baseline_if_needed=Mock(return_value=True))
    assert InputHandler(state,hw)._finalize_pending_ai_move('recovered',(0,120,0))
    assert state.move_sync_error is None and not state.physical_sync_fault
    assert not state.snapshot_continue_required
    hw.capture_baseline_if_needed.assert_called_once()


def test_recovery_commit_finishes_checkmate_without_further_baseline(state,monkeypatch):
    state.turn='b'
    move=((0,3),(0,4))
    expected,_=xiangqi.make_temp_move(state.board,move)
    state.mark_move_pending(state.create_move_context(*move,MoveActor.ROBOT))
    state.set_pending_physical_move(move,expected,'.','b')
    hw=SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL'),dry_run=False,
        capture_baseline_if_needed=Mock(return_value=True))
    monkeypatch.setattr(xiangqi,'find_all_valid_moves',lambda *a:[])
    assert InputHandler(state,hw)._finalize_pending_ai_move('recovered',(0,120,0))
    assert state.game_over and state.winner=='b'
    state.api_client.end_match.assert_called_once_with(winner='BLACK',reason='CHECKMATE')
    hw.capture_baseline_if_needed.assert_not_called()


def test_physical_continue_rejects_low_confidence_legal_successor(state):
    move = ((4,6),(4,5))
    after, _ = xiangqi.make_temp_move(state.board,move)
    camera = SimpleNamespace(get_fresh_snapshot=Mock(return_value=(object(),[])))
    recognizer = Mock(return_value={'success':True,'board':after,'confidence':[[.05]*9 for _ in range(10)]})
    hw = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL'),dry_run=False,
        camera_calibration_ready=True,cam_monitor=camera,recognize_board_state=recognizer,
        capture_baseline_if_needed=Mock(return_value=True))
    handler = InputHandler(state,hw)
    handler._commit_human_move = Mock(return_value=True)
    handler._continue_after_snapshot_pause()
    handler._commit_human_move.assert_not_called()
    hw.capture_baseline_if_needed.assert_not_called()
    assert state.manual_override_active and state.snapshot_continue_required


def test_selfplay_explicit_stop_ends_spectator_once(state):
    hw = SimpleNamespace()
    ctrl = SelfPlayController(state,hw)
    ctrl.status = SelfPlayStatus.READY
    assert ctrl.end_match()
    assert not ctrl.end_match()
    state.api_client.end_match.assert_called_once_with(winner='DRAW',reason='OTHER')
    assert ctrl.status is SelfPlayStatus.ENDED


def test_dormant_selfplay_stop_does_not_end_human_game(state):
    ctrl=SelfPlayController(state,SimpleNamespace())
    assert not ctrl.end_match()
    assert ctrl.status is SelfPlayStatus.IDLE
    state.api_client.end_match.assert_not_called()


@pytest.mark.parametrize('color,move', [('r',((4,6),(4,5))),('b',((4,3),(4,4)))])
def test_physical_continue_accepts_verified_current_color(state,monkeypatch,color,move):
    monkeypatch.setattr(config,'GAME_MODE','HUMAN_VS_HUMAN')
    state.turn=color
    after, _ = xiangqi.make_temp_move(state.board,move)
    hw=SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL'),dry_run=False,
        camera_calibration_ready=True,
        cam_monitor=SimpleNamespace(get_fresh_snapshot=Mock(return_value=(object(),[]))),
        recognize_board_state=Mock(return_value={'success':True,'board':after,'confidence':[[.99]*9 for _ in range(10)]}),
        capture_baseline_if_needed=Mock(return_value=True))
    InputHandler(state,hw)._continue_after_snapshot_pause()
    assert state.board==after and len(state.move_history)==1
    assert not state.snapshot_continue_required and not state.manual_override_active
    assert hw.cam_monitor.get_fresh_snapshot.call_count==2


def test_selfplay_no_legal_move_terminal_ends_spectator(state,monkeypatch):
    ctrl=SelfPlayController(state,SimpleNamespace())
    ctrl.status=SelfPlayStatus.THINKING
    ctrl._token=ctrl._current_token()
    ctrl._thread=SimpleNamespace(is_alive=lambda:False)
    ctrl._result=(ctrl._token,[row[:] for row in state.board],state.turn,None,None)
    monkeypatch.setattr(xiangqi,'find_all_valid_moves',lambda *a:[])
    ctrl.tick()
    assert ctrl.status is SelfPlayStatus.FINISHED and state.game_over
    state.api_client.end_match.assert_called_once_with(winner='BLACK',reason='CHECKMATE')


def test_selfplay_stop_during_motion_and_resign_publish_once(state):
    ctrl=SelfPlayController(state,SimpleNamespace())
    ctrl.status=SelfPlayStatus.MOVING
    ctrl._thread=SimpleNamespace(is_alive=lambda:True)
    assert ctrl.end_match(winner='BLACK',reason='RESIGN')
    assert ctrl.status is SelfPlayStatus.ENDING
    assert not ctrl.end_match()
    state.api_client.end_match.assert_called_once_with(winner='BLACK',reason='RESIGN')


@pytest.mark.parametrize('color', ['r','b'])
def test_known_king_capture_verifies_removal_and_terminal_board_then_commits_winner(state,color):
    from src.hardware.hardware_manager import HardwareManager
    from src.core.visual_move_coordinator import execute_pending_ai_motion
    from src.motion.result import MotionExecutionResult
    from src.vision.cchess_recognizer import validate_board_sanity
    before=[['.']*9 for _ in range(10)]
    before[0][4]='b_K';before[9][4]='r_K'
    source=(4,1) if color=='r' else (4,8)
    destination=(4,0) if color=='r' else (4,9)
    before[source[1]][source[0]]=color+'_R'
    state.board=before;state.turn=color
    state.piece_ids={(0,4):'black_king_0',(9,4):'red_king_0',
        (source[1],source[0]):'red_rook_0' if color=='r' else 'black_rook_0'}
    expected,captured=xiangqi.make_temp_move(before,(source,destination))
    state.mark_move_pending(state.create_move_context(source,destination,MoveActor.ROBOT))
    state.set_pending_physical_move((source,destination),expected,captured,color)
    observed=[before]
    hw=HardwareManager.__new__(HardwareManager)
    hw.config=SimpleNamespace(ROBOT_BACKEND='PHYSICAL',VISUAL_PICK_ENABLED=False)
    hw.dry_run=False;hw.camera_calibration_ready=True
    hw.cam_monitor=SimpleNamespace(get_fresh_snapshot=Mock(side_effect=lambda:(object(),[])))
    hw.recognize_board_state=lambda frame:{'success':True,'board':observed[0],'confidence':[[.99]*9 for _ in range(10)]}
    hw.is_cell_visually_clear=lambda cell:observed[0][cell[1]][cell[0]]=='.'
    calls=[]
    def command(**kwargs):
        calls.append(kwargs)
        removed=[row[:] for row in before]
        removed[destination[1]][destination[0]]='.'
        observed[0]=removed
        assert kwargs['verify_capture_cleared']()
        observed[0]=expected
        return MotionExecutionResult.ok()
    hw.execute_piece_move=command
    hw.capture_baseline_if_needed=Mock()
    assert execute_pending_ai_motion(state,hw).success
    assert len(calls)==1 and hw.cam_monitor.get_fresh_snapshot.call_count==6
    handler=InputHandler(state,hw)
    assert handler._verify_recovery_board(expected)
    assert not hw.verify_physical_board(expected)  # Default recognition still requires both kings.
    assert handler._finalize_pending_ai_move('won',(0,120,0))
    assert state.game_over and state.winner==color and state.board==expected
    state.api_client.end_match.assert_called_once_with(winner='RED' if color=='r' else 'BLACK',reason='CHECKMATE')
    hw.capture_baseline_if_needed.assert_not_called()
    missing='b' if color=='r' else 'r'
    assert validate_board_sanity(expected,missing_king_color=missing)[0]
    assert not validate_board_sanity(expected,missing_king_color=color)[0]
    both_missing=[row[:] for row in expected]
    both_missing[9 if color=='r' else 0][4]='.'
    assert not validate_board_sanity(both_missing,missing_king_color=missing)[0]


def test_main_input_setup_failure_rolls_back_and_retries(tmp_path,monkeypatch):
    os.environ.setdefault('SDL_VIDEODRIVER','dummy')
    os.environ.setdefault('SDL_AUDIODRIVER','dummy')
    import pygame
    from src.core.motion_worker import MotionWorker
    from src.ui.board_renderer import BoardRenderer
    for name in ('DRY_RUN','ROBOT_BACKEND','GAME_ONLY','TELEMETRY_PORT','GAME_MODE'):
        monkeypatch.setattr(config,name,getattr(config,name,None),raising=False)
    monkeypatch.setattr(sys,'argv',['main.py','--no-viewer','--log-dir',str(tmp_path/'logs')])
    monkeypatch.setattr(sys,'path',list(sys.path))
    callbacks=[]
    monkeypatch.setattr(atexit,'register',lambda f,*a,**kw:callbacks.append(f))
    resources=[]
    def build(*args):
        hw=SimpleNamespace(motion_worker=MotionWorker(),cleanup=Mock(),cam_monitor=None)
        telemetry,viewer=Mock(),Mock()
        resources.append((hw,telemetry,viewer))
        return hw,telemetry,viewer,None
    monkeypatch.setattr('src.core.session_startup.build_session',build)
    monkeypatch.setattr('src.ui.input_handler.InputHandler',Mock(side_effect=ValueError('bad UI configuration')))
    messages=[]
    original=BoardRenderer.draw_home_screen
    def draw(self,message=''):
        messages.append(message)
        return original(self,message)
    monkeypatch.setattr(BoardRenderer,'draw_home_screen',draw)
    sent=[0]
    deadline=time.monotonic()+10
    def events():
        assert time.monotonic()<deadline,'UI startup failure stranded the main loop'
        if sent[0]==0 or (sent[0]<2 and messages and 'bad UI configuration' in messages[-1]):
            sent[0]+=1
            return [pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN)]
        if len(resources)==2 and messages and 'bad UI configuration' in messages[-1] and resources[-1][0].cleanup.called:
            return [pygame.event.Event(pygame.QUIT)]
        return []
    monkeypatch.setattr(pygame.event,'get',events)
    try:
        app=runpy.run_path(str(Path(__file__).resolve().parents[2]/'main.py'),run_name='__main__')
        assert app['home_screen_active'] and app['hw'] is None and app['input_mgr'] is None
        assert len(resources)==2
        for hw,telemetry,viewer in resources:
            hw.cleanup.assert_called_once()
            telemetry.stop.assert_called_once()
            viewer.close.assert_called_once()
    finally:
        for callback in reversed(callbacks):callback()
        pygame.quit()
