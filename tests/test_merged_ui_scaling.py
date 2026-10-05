"""Exercise merged event handling without launching the app or hardware."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pytest

from src.core.self_play_controller import SelfPlayStatus
from src.ui import board_renderer as ui


def event_context(monkeypatch, rect, *, home=False, status=SelfPlayStatus.READY):
    tree = ast.parse((Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8"))
    convert = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "canvas_position")
    events = next(node for node in ast.walk(tree) if isinstance(node, ast.For)
                  and ast.unparse(node.iter) == "pygame.event.get()")
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=tuple(round(value * 0.9) for value in rect.center))
    monkeypatch.setattr(pygame.event, "get", lambda: [event])
    controller = Mock(status=status, human_input_disabled=True, accepts_next=True, run_mode="step")
    hardware = Mock()
    context = {
        "pygame": pygame, "SCREEN_WIDTH": ui.SCREEN_WIDTH, "SCREEN_HEIGHT": ui.SCREEN_HEIGHT,
        "WINDOW_WIDTH": round(ui.SCREEN_WIDTH * 0.9), "WINDOW_HEIGHT": round(ui.SCREEN_HEIGHT * 0.9),
        "BTN_NEW_GAME_RECT": ui.BTN_NEW_GAME_RECT,
        "SELF_PLAY_NEXT_RECT": ui.SELF_PLAY_NEXT_RECT,
        "SELF_PLAY_MODE_RECT": ui.SELF_PLAY_MODE_RECT,
        "SELF_PLAY_END_RECT": ui.SELF_PLAY_END_RECT,
        "home_screen_active": home, "settings_menu_active": False, "difficulty_menu_active": False,
        "self_play_controller": controller, "SelfPlayStatus": SelfPlayStatus,
        "renderer": ui.BoardRenderer, "state": Mock(), "input_mgr": Mock(),
        "HardwareManager": Mock(return_value=hardware), "InputHandler": Mock(),
        "config": SimpleNamespace(), "_BASE_DIR": ".", "debug_dashboard": None,
    }
    exec(compile(ast.Module(body=[convert, events], type_ignores=[]), "main.py", "exec"), context)
    return context, controller


def test_scaled_click_launches_robot_vs_robot(monkeypatch):
    context, _ = event_context(monkeypatch, ui.HOME_ROBOT_VS_ROBOT_RECT, home=True)
    assert context["home_screen_active"] is False
    assert context["difficulty_menu_active"] is True
    assert context["self_play_setup_stage"] == "red"
    context["HardwareManager"].return_value.initialize_all.assert_called_once()


@pytest.mark.parametrize("rect,method,args", [
    (ui.SELF_PLAY_NEXT_RECT, "request_next_move", ()),
    (ui.SELF_PLAY_MODE_RECT, "set_run_mode", ("continuous",)),
    (ui.SELF_PLAY_END_RECT, "end_match", ()),
])
def test_scaled_click_dispatches_self_play_control(monkeypatch, rect, method, args):
    context, controller = event_context(monkeypatch, rect)
    getattr(controller, method).assert_called_once_with(*args)
    context["input_mgr"].handle_mouse_down.assert_not_called()


@pytest.mark.parametrize("status", [SelfPlayStatus.ENDED, SelfPlayStatus.FINISHED])
def test_scaled_new_game_returns_self_play_to_launcher(monkeypatch, status):
    context, _ = event_context(monkeypatch, ui.BTN_NEW_GAME_RECT, status=status)
    context["state"].reset_game.assert_called_once_with(create_api_match=False)
    assert context["state"].physical_sync_fault is True
    assert context["self_play_controller"] is None
    assert context["home_screen_active"] is True


def test_merged_controls_fit_canvas_without_overlapping():
    canvas = pygame.Rect(0, 0, ui.SCREEN_WIDTH, ui.SCREEN_HEIGHT)
    rectangles = [ui.HOME_VS_ROBOT_RECT.inflate(48, 68), ui.HOME_ROBOT_VS_ROBOT_RECT]
    controls = [ui.SELF_PLAY_NEXT_RECT, ui.SELF_PLAY_MODE_RECT, ui.SELF_PLAY_END_RECT]
    assert not rectangles[0].colliderect(rectangles[1])
    for rect in rectangles + controls:
        assert canvas.contains(rect)
    for index, rect in enumerate(controls):
        assert not rect.colliderect(ui.BTN_NEW_GAME_RECT)
        assert not any(rect.colliderect(other) for other in controls[index + 1:])
