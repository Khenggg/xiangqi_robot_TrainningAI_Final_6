"""Run the actual launcher/event loop with mock motion and real room sockets."""
import atexit
import inspect
import os
from pathlib import Path
import queue
import runpy
import signal
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.serial
@pytest.mark.parametrize('ending',['quit','cancel_quit','cancel_interrupt','surrender_reset'])
def test_menu_host_red_and_network_black_complete_two_gui_turns(monkeypatch, tmp_path, ending):
    monkeypatch.setenv('SDL_VIDEODRIVER','dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER','dummy')
    import pygame
    import config
    from src.core import session_startup
    from src.core.session_profile import configure_session
    from src.core.pvp_room import LocalRoomClient
    from src.hardware.hardware_manager import HardwareManager
    from src.motion.result import MotionExecutionResult
    from src.ui.pvp_client import ClientBoard
    from src.ui.board_renderer import HOME_ROBOT_PVP_RECT, SCREEN_WIDTH, SCREEN_HEIGHT, START_X, START_Y, SQUARE_SIZE, BTN_SURRENDER_RECT, BTN_NEW_GAME_RECT
    from src.ui.game_window import fitted_rect

    # Restore config mutations performed by the actual launcher.
    for name,value in vars(config).copy().items():
        if name.isupper(): monkeypatch.setattr(config,name,value)
    monkeypatch.setattr(sys,'argv',['main.py','--simulation','--no-viewer','--log-dir',str(tmp_path/'logs')])
    monkeypatch.setattr(sys,'path',list(sys.path))
    monkeypatch.setattr('src.core.game_state.TuongKyDaiSuClient',lambda *a: Mock(token=None,room_id=None))
    # The real application exits the OS process after this one confirmation.
    decisions = iter([False, True] if ending.startswith('cancel_') else [True])
    monkeypatch.setattr('src.ui.exit_confirmation.confirm_exit', lambda: next(decisions))
    monkeypatch.setattr('src.ui.exit_confirmation.exit_application', lambda: None)
    callbacks, motions = [], []
    monkeypatch.setattr(atexit,'register',lambda f,*a,**kw: callbacks.append(f))
    manager = [None]
    def build(cfg,options,root,state,cancelled=None,mode=None):
        profile = configure_session(cfg,options,mode=mode)
        assert profile.game_mode == 'HUMAN_VS_HUMAN_ROBOT' and not profile.ai_enabled
        state.session_profile = profile
        state.allow_mouse_move = False
        state.attach_journal(tmp_path,'VIRTUAL',profile.game_mode,fresh_start=True)
        hw = manager[0] = HardwareManager(cfg,root)
        hw.game_state = state
        hw.simulation_runtime = SimpleNamespace()
        hw.backend = SimpleNamespace(is_connected=lambda:True)
        def execute(**kwargs):
            motions.append(kwargs['move_context'])
            return MotionExecutionResult.ok()
        hw.execute_piece_move = execute
        def cleanup():
            hw.motion_worker.close()
            if getattr(hw,'pvp_controller',None): hw.pvp_controller.close()
        hw.cleanup = cleanup
        return hw,None,None,None
    monkeypatch.setattr(session_startup,'build_session',build)
    phase, client, model = [0], [None], ClientBoard()
    deadline = time.monotonic()+20
    def click(canvas_pos):
        surface = pygame.display.get_surface()
        rect = fitted_rect((SCREEN_WIDTH,SCREEN_HEIGHT),surface.get_size())
        return pygame.event.Event(pygame.MOUSEBUTTONDOWN,button=1,pos=(
            round(rect.x+canvas_pos[0]*rect.width/SCREEN_WIDTH),
            round(rect.y+canvas_pos[1]*rect.height/SCREEN_HEIGHT)))
    def cell(col,row):
        return click((START_X+col*SQUARE_SIZE,START_Y+row*SQUARE_SIZE))
    def events():
        assert time.monotonic() < deadline, 'Actual GUI did not finish mock two-player game'
        scope = inspect.currentframe().f_back.f_globals
        if client[0]:
            while True:
                try: model.receive(client[0].events.get_nowait())
                except queue.Empty: break
        hw = scope.get('hw')
        if phase[0] == 0:
            phase[0] = 1
            return [click(HOME_ROBOT_PVP_RECT.center)]
        if phase[0] == 1 and hw is not None and not hw.motion_worker.busy:
            assert not scope['difficulty_menu_active']
            client[0] = LocalRoomClient(hw.pvp_controller.room.code)
            phase[0] = 2
        elif phase[0] == 2 and model.snapshot and hw.pvp_controller.room.connected:
            phase[0] = 3
            return [cell(0,6)]
        elif phase[0] == 3:
            phase[0] = 4
            return [cell(0,5)]
        elif phase[0] == 4 and model.can_move(client[0].connected):
            assert model.snapshot['revision'] == 1
            assert client[0].send_move((0,3),(0,4),model.snapshot['revision'],model.snapshot['epoch'])
            phase[0] = 5
        elif phase[0] == 5 and scope['state'].board_revision == 2 and not hw.motion_worker.busy:
            state = scope['state']
            assert state.turn == 'r' and len(motions) == 2
            assert state.board[5][0] == 'r_P' and state.board[4][0] == 'b_P'
            output = os.environ.get('PVP_UI_EVIDENCE_DIR')
            if output:
                path = Path(output); path.mkdir(parents=True,exist_ok=True)
                pygame.image.save(scope['screen'],str(path/'host-after-two-turns.png'))
            phase[0] = 6
            if ending == 'cancel_interrupt':
                signal.raise_signal(signal.SIGINT)
                return []
            return [click(BTN_SURRENDER_RECT.center)] if ending=='surrender_reset' else [pygame.event.Event(pygame.QUIT)]
        elif phase[0] == 6 and ending=='surrender_reset' and scope['state'].game_over:
            assert scope['state'].winner=='b'
            phase[0]=7
            return [click(BTN_NEW_GAME_RECT.center)]
        elif phase[0] == 6 and ending.startswith('cancel_'):
            assert not scope['quit_requested']
            assert scope['session_control'].action is None
            phase[0]=7
            return [pygame.event.Event(pygame.QUIT)]
        elif phase[0] == 7 and scope['state'].game_epoch>0 and not hw.motion_worker.busy:
            assert scope['state'].turn=='r' and not scope['state'].game_over
            phase[0]=8
            return [pygame.event.Event(pygame.QUIT)]
        return []
    monkeypatch.setattr(pygame.event,'get',events)
    try:
        result = runpy.run_path(str(Path(__file__).resolve().parents[2]/'main.py'),run_name='__main__')
        assert phase[0] == (8 if ending=='surrender_reset' else 7 if ending.startswith('cancel_') else 6)
        assert result['state'].board_revision == (0 if ending=='surrender_reset' else 2)
        assert all(context.actor.value == 'ROBOT' for context in motions)
        assert not manager[0].pvp_controller.room.path.exists()
    finally:
        if client[0]: client[0].close()
        for callback in reversed(callbacks): callback()
        pygame.quit()
