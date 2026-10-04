import os
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest
import config

from src.ui.game_window import GameWindow, fitted_rect, initial_window_size
from src.core.game_state import GameState
from src.ui.input_handler import InputHandler
from src.ui.board_renderer import (BoardRenderer, START_X, START_Y, SQUARE_SIZE,
                                   HOME_VS_ROBOT_RECT, BTN_NEW_GAME_RECT,
                                   BTN_CONFIRM_MOVE_RECT)


@pytest.fixture
def window():
    pygame.init()
    result = GameWindow((1440, 1080))
    yield result
    pygame.quit()


@pytest.mark.parametrize("desktop", [(1920, 1080), (1536, 864), (1366, 768), (800, 600)])
def test_initial_window_fits_desktop(desktop):
    size = initial_window_size((1440, 1080), desktop)
    assert size[0] <= desktop[0] * .8 and size[1] <= desktop[1] * .8
    assert abs(size[0] / size[1] - 4 / 3) < .005


@pytest.mark.parametrize("size", [(960, 720), (1280, 720), (700, 900), (1920, 1080)])
def test_all_90_cells_and_controls_map_after_resize(window, size):
    window.display = pygame.display.set_mode(size, pygame.RESIZABLE)
    rect = fitted_rect(window.canvas_size, size)
    points = [(START_X + col * SQUARE_SIZE, START_Y + row * SQUARE_SIZE)
              for row in range(10) for col in range(9)]
    points += [r.center for r in (HOME_VS_ROBOT_RECT, BTN_NEW_GAME_RECT, BTN_CONFIRM_MOVE_RECT)]
    for x, y in points:
        pixel = (round(rect.x + x * rect.width / 1440),
                 round(rect.y + y * rect.height / 1080))
        event = window.map_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                                  pos=pixel, button=1))
        assert abs(event.pos[0] - x) <= 2 and abs(event.pos[1] - y) <= 2
    for row in range(10):
        for col in range(9):
            x, y = points[row * 9 + col]
            pixel = (round(rect.x + x * rect.width / 1440),
                     round(rect.y + y * rect.height / 1080))
            assert BoardRenderer.pixel_to_grid(*window.canvas_position(pixel)) == (col, row)
    window.canvas.fill((120, 70, 30))
    window.present()
    # SIMD smoothscale can round constant channels down by up to two levels.
    assert all(abs(actual - expected) <= 2 for actual, expected in
               zip(window.display.get_at(rect.center)[:3], (120, 70, 30)))


def test_letterbox_click_is_ignored(window):
    window.display = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
    assert window.map_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                             pos=(10, 360), button=1)) is None


@pytest.mark.parametrize("size", [(960, 720), (1280, 720)])
def test_resized_mouse_move_commits_once(window, size, monkeypatch):
    monkeypatch.setattr(config, "GAME_MODE", "HUMAN_VS_ROBOT")
    state = GameState(allow_mouse_move=True)
    observer = Mock(return_value=True)
    state.set_board_observer(observer)
    hw = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND="VIRTUAL"),
                         dry_run=True, cam_monitor=None, yolo_detector=None)
    handler = InputHandler(state, hw)
    window.display = pygame.display.set_mode(size, pygame.RESIZABLE)
    rect = fitted_rect(window.canvas_size, size)
    for cell in ((4, 6), (4, 5)):
        x, y = BoardRenderer.grid_to_pixel(*cell)
        pixel = (round(rect.x + x * rect.width / 1440),
                 round(rect.y + y * rect.height / 1080))
        event = window.map_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                                  pos=pixel, button=1))
        handler.handle_mouse_down(*event.pos)
    assert state.board[5][4] == "r_P" and state.board[6][4] == "."
    assert state.turn == "b" and state.human_commit_generation == 1
    observer.assert_called_once_with(state.piece_ids)


def test_fullscreen_restores_resized_window_and_preserves_canvas(window, monkeypatch):
    # SDL's dummy driver cannot restore a window after entering fullscreen.
    # Assert the requested modes here; exercise the real Windows driver in GUI.
    calls = []
    def set_mode(size, flags):
        calls.append((size, flags))
        return pygame.Surface((1920, 1080) if flags == pygame.FULLSCREEN else size)
    monkeypatch.setattr(pygame.display, "set_mode", set_mode)
    window.display = pygame.Surface((800, 600))
    window.canvas.set_at((700, 500), (10, 20, 30))
    assert window.map_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11)) is None
    assert window.fullscreen
    assert window.map_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)) is None
    assert not window.fullscreen and window.display.get_size() == (800, 600)
    assert calls == [((0, 0), pygame.FULLSCREEN), ((800, 600), pygame.RESIZABLE)]
    assert window.canvas.get_at((700, 500))[:3] == (10, 20, 30)
    # Escape outside fullscreen remains available to the existing menu.
    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
    assert window.map_event(event) is event
