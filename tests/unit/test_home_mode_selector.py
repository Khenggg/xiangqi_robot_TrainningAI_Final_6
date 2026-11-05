"""The launcher exposes the three customer modes without changing game cards."""

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from src.ui.board_renderer import (
    HOME_MODE_BOARD_RECT,
    HOME_MODE_PHYSICAL_RECT,
    HOME_MODE_SIM_RECT,
    HOME_PHYSICAL_CAMERA_RECT,
    HOME_VS_ROBOT_RECT,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    BoardRenderer,
)


@pytest.fixture
def renderer():
    pygame.init()
    surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    yield BoardRenderer(surface)
    pygame.quit()


def test_home_exposes_three_distinct_environment_cards():
    assert BoardRenderer.home_mode_from_pixel(*HOME_MODE_BOARD_RECT.center) == "BOARD_ONLY"
    assert BoardRenderer.home_mode_from_pixel(*HOME_MODE_SIM_RECT.center) == "SIMULATION"
    assert BoardRenderer.home_mode_from_pixel(*HOME_MODE_PHYSICAL_RECT.center) == "PHYSICAL"
    assert BoardRenderer.home_mode_from_pixel(0, 0) is None


def test_environment_cards_do_not_steal_game_mode_clicks():
    assert BoardRenderer.home_action_from_pixel(*HOME_VS_ROBOT_RECT.center) == "vs_robot"
    assert BoardRenderer.home_mode_from_pixel(*HOME_VS_ROBOT_RECT.center) is None


@pytest.mark.parametrize("mode", ["BOARD_ONLY", "SIMULATION", "PHYSICAL"])
def test_home_screen_renders_each_selected_mode(renderer, mode):
    renderer.home_mode = mode
    renderer.physical_camera_recalibration_requested = mode == "PHYSICAL"
    renderer.draw_home_screen("")
    assert renderer.home_mode == mode


def test_physical_camera_calibration_has_its_own_hit_target():
    assert BoardRenderer.home_physical_camera_calibration_from_pixel(
        *HOME_PHYSICAL_CAMERA_RECT.center)
    assert not BoardRenderer.home_physical_camera_calibration_from_pixel(
        *HOME_MODE_PHYSICAL_RECT.center)
    assert not BoardRenderer.home_physical_camera_calibration_from_pixel(0, 0)


def test_main_passes_selected_environment_into_session_startup(tmp_path, monkeypatch):
    import atexit
    import runpy
    import sys
    import time

    import config
    from src.api.simulation_client import TuongKyDaiSuClient
    from src.ui.board_renderer import (
        HOME_MODE_PHYSICAL_RECT,
        HOME_PHYSICAL_CAMERA_RECT,
    )

    for name in ("DRY_RUN", "ROBOT_BACKEND", "GAME_ONLY", "TELEMETRY_PORT", "GAME_MODE"):
        monkeypatch.setattr(config, name, getattr(config, name, None), raising=False)
    monkeypatch.setattr(sys, "argv", ["main.py", "--log-dir", str(tmp_path / "logs")])
    monkeypatch.setattr(sys, "path", list(sys.path))
    callbacks = []
    monkeypatch.setattr(atexit, "register", lambda f, *a, **kw: callbacks.append(f))
    monkeypatch.setattr(TuongKyDaiSuClient, "end_match", lambda *a, **kw: None)

    captured = []
    from src.core import session_profile

    def capture_mode(cfg, options, mode=None):
        captured.append((mode, cfg.RECALIBRATE_CAMERA, cfg.CAMERA_CALIBRATION_MANUAL_ONLY))
        raise RuntimeError("stop after mode capture")

    monkeypatch.setattr(session_profile, "configure_session", capture_mode)

    from src.ui.game_window import fitted_rect

    phase = [0]
    deadline = time.monotonic() + 10

    def click(canvas_position):
        surface = pygame.display.get_surface()
        rect = fitted_rect((SCREEN_WIDTH, SCREEN_HEIGHT), surface.get_size())
        x, y = canvas_position
        pixel = (round(rect.x + x * rect.width / SCREEN_WIDTH),
                 round(rect.y + y * rect.height / SCREEN_HEIGHT))
        return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pixel, button=1)

    def events():
        assert time.monotonic() < deadline, "GUI did not route the selected mode"
        if phase[0] == 0:
            phase[0] = 1
            return [click(HOME_MODE_PHYSICAL_RECT.center)]
        if phase[0] == 1:
            phase[0] = 2
            return [click(HOME_PHYSICAL_CAMERA_RECT.center)]
        if phase[0] == 2:
            phase[0] = 3
            return [click(HOME_VS_ROBOT_RECT.center)]
        if phase[0] == 3 and captured:
            phase[0] = 4
            return [pygame.event.Event(pygame.QUIT)]
        if phase[0] == 3:
            return []
    monkeypatch.setattr(pygame.event, "get", events)
    try:
        runpy.run_path(str(Path(__file__).resolve().parents[2] / "main.py"), run_name="__main__")
    finally:
        for callback in reversed(callbacks):
            callback()
        pygame.quit()

    assert captured == [("PHYSICAL", True, True)]
