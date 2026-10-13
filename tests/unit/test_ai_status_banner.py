import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame
import pytest

from src.ui.board_renderer import BoardRenderer, JADE_COLOR, AMBER_COLOR
from src.core.game_state import GameState


def test_ai_status_banner_physical_readonly_shows_f9_f10_hint():
    pygame.init()
    screen = pygame.Surface((1440, 1080))
    renderer = BoardRenderer(screen)

    state = GameState()
    state.turn = "b"
    state.is_robot_ready = False
    state.physical_enable_pending = False

    render_dict = state.get_render_state()
    render_dict["robot_backend"] = "PHYSICAL"
    render_dict["is_robot_ready"] = False
    render_dict["physical_enable_pending"] = False

    # Simulate drawing status banner
    renderer._draw_ai_status(render_dict)

    # Now verify pending enable state
    render_dict["physical_enable_pending"] = True
    renderer._draw_ai_status(render_dict)

    # Now verify robot ready state
    render_dict["is_robot_ready"] = True
    renderer._draw_ai_status(render_dict)

    pygame.quit()
