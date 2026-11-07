"""Execute the exact main event loop with real Pygame constants and current layout."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock
import pygame
import pytest
from src.ui import board_renderer as ui

ROOT=Path(__file__).resolve().parents[2]
tree=ast.parse((ROOT/'main.py').read_text())
loop=next(n for n in ast.walk(tree) if isinstance(n,ast.For) and isinstance(n.target,ast.Name)
          and n.target.id=='event' and ast.unparse(n.iter)=='pygame.event.get()')
PROGRAM=compile(ast.fix_missing_locations(ast.Module(body=[loop],type_ignores=[])),str(ROOT/'main.py'),'exec')

def run_event(monkeypatch,event,recovery=True,render_state=None):
    monkeypatch.setattr(pygame.event,'get',lambda:[event])
    handler=NS(handle_keyboard=Mock(),handle_mouse_down=Mock())
    render_state = render_state if render_state is not None else dict(
        camera_enabled=True, robot_moves_enabled=True, simulation_enabled=True, viewer_enabled=True,
        game_mode='ROBOT_VS_ROBOT', client_controls_compact=True, can_rollback=False,
        physical_sync_fault=True, move_sync_error='test fault', snapshot_continue_required=True)
    env=dict(pygame=pygame,game_window=NS(map_event=lambda e:e),
        hw=NS(motion_worker=NS(busy=False)),startup_worker=NS(busy=False),
        self_play=NS(active=False,status=NS(value='faulted' if recovery else 'idle'),
            recovery_input_allowed=recovery,human_input_disabled=recovery),
        state=NS(physical_sync_fault=True,move_sync_error='test fault',game_over=False,
            get_render_state=lambda: dict(render_state)),
        config=NS(ROBOT_BACKEND='PHYSICAL',GAME_MODE='ROBOT_VS_ROBOT'),
        input_mgr=handler,session_control=NS(action=None),home_screen_active=False,
        settings_menu_active=False,difficulty_menu_active=False,mode_switching=False,
        mode_switch_failed=False,quit_requested=False,
        **{n:v for n,v in vars(ui).items() if n.startswith('BTN_')})
    exec(PROGRAM,env)
    return handler

@pytest.mark.parametrize('key',[pygame.K_v,pygame.K_F4,pygame.K_1,pygame.K_2,pygame.K_F12])
def test_selfplay_recovery_forwards_documented_keys(monkeypatch,key):
    handler=run_event(monkeypatch,pygame.event.Event(pygame.KEYDOWN,key=key,mod=0))
    handler.handle_keyboard.assert_called_once_with(key)

@pytest.mark.parametrize('rollback',[False,True])
@pytest.mark.parametrize('action',['scan','clear_error','continue'])
def test_selfplay_recovery_forwards_actual_rendered_button(monkeypatch,rollback,action):
    state=dict(camera_enabled=True,robot_moves_enabled=True,simulation_enabled=True,viewer_enabled=True,
        game_mode='ROBOT_VS_ROBOT',client_controls_compact=True,can_rollback=rollback,
        physical_sync_fault=True,move_sync_error='test fault',snapshot_continue_required=True)
    actions=ui.BoardRenderer.client_action_controls(state)
    if action=='continue':rect=ui.BoardRenderer.client_continue_rect(state,actions)
    else:
        key=pygame.K_v if action=='scan' else pygame.K_F12
        rect=next(r for r,k,*_ in actions if k==key)
    handler=run_event(monkeypatch,pygame.event.Event(pygame.MOUSEBUTTONDOWN,pos=rect.center,button=1),render_state=state)
    handler.handle_mouse_down.assert_called_once_with(*rect.center)

@pytest.mark.parametrize('key',[pygame.K_F12,pygame.K_v])
def test_idle_controller_forwards_recovery_keys(monkeypatch,key):
    handler=run_event(monkeypatch,pygame.event.Event(pygame.KEYDOWN,key=key,mod=0),recovery=False)
    handler.handle_keyboard.assert_called_once_with(key)


@pytest.mark.parametrize('key',[pygame.K_m,pygame.K_t,pygame.K_h,pygame.K_z])
def test_selfplay_recovery_does_not_admit_other_visible_actions(monkeypatch,key):
    state=dict(camera_enabled=True,robot_moves_enabled=True,simulation_enabled=True,viewer_enabled=True,
        game_mode='ROBOT_VS_ROBOT',client_controls_compact=True,can_rollback=True,
        physical_sync_fault=True,move_sync_error='test fault',snapshot_continue_required=True)
    rect=next(r for r,k,*_ in ui.BoardRenderer.client_action_controls(state) if k==key)
    handler=run_event(monkeypatch,pygame.event.Event(pygame.MOUSEBUTTONDOWN,pos=rect.center,button=1),render_state=state)
    handler.handle_mouse_down.assert_not_called()


def test_selfplay_recovery_does_not_admit_hidden_continue(monkeypatch):
    state=dict(camera_enabled=True,robot_moves_enabled=True,simulation_enabled=True,viewer_enabled=True,
        game_mode='ROBOT_VS_ROBOT',client_controls_compact=True,can_rollback=False,
        physical_sync_fault=True,move_sync_error='test fault',snapshot_continue_required=False)
    rect=ui.BoardRenderer.client_continue_rect(state)
    handler=run_event(monkeypatch,pygame.event.Event(pygame.MOUSEBUTTONDOWN,pos=rect.center,button=1),render_state=state)
    handler.handle_mouse_down.assert_not_called()


@pytest.mark.parametrize('action', ['scan', 'clear_error', 'continue'])
def test_game_over_does_not_admit_hidden_client_buttons(monkeypatch, action):
    state=dict(camera_enabled=True,robot_moves_enabled=True,simulation_enabled=True,viewer_enabled=True,
        game_mode='ROBOT_VS_ROBOT',client_controls_compact=True,can_rollback=False,
        physical_sync_fault=True,move_sync_error='test fault',snapshot_continue_required=True,game_over=True)
    if action == 'continue':
        rect=ui.BoardRenderer.client_continue_rect(state)
    else:
        key=pygame.K_v if action == 'scan' else pygame.K_F12
        rect=next(r for r,k,*_ in ui.BoardRenderer.client_action_controls(state) if k==key)
    handler=run_event(monkeypatch,pygame.event.Event(pygame.MOUSEBUTTONDOWN,pos=rect.center,button=1),render_state=state)
    handler.handle_mouse_down.assert_not_called()
