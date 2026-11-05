"""Client controls must match the active session capabilities."""

import pygame

from src.ui.board_renderer import BoardRenderer


def _keys(state):
    return {key for _rect, key, _labels, _color in BoardRenderer.client_action_controls(state)}


def test_game_only_has_only_rollback():
    assert _keys({
        "camera_enabled": False,
        "simulation_enabled": False,
        "robot_moves_enabled": True,
        "can_rollback": True,
    }) == {pygame.K_z}


def test_virtual_simulation_has_viewer_sync_and_robot_tests():
    assert _keys({
        "camera_enabled": False,
        "simulation_enabled": True,
        "robot_moves_enabled": True,
        "can_rollback": True,
    }) == {pygame.K_v, pygame.K_t, pygame.K_h, pygame.K_z}


def test_physical_session_has_camera_controls_and_robot_tests():
    assert _keys({
        "camera_enabled": True,
        "simulation_enabled": True,
        "robot_moves_enabled": True,
        "can_rollback": True,
    }) == {pygame.K_v, pygame.K_SPACE, pygame.K_m, pygame.K_t, pygame.K_h, pygame.K_z}


def test_two_human_session_has_no_camera_or_robot_controls():
    assert _keys({
        "camera_enabled": False,
        "simulation_enabled": True,
        "robot_moves_enabled": False,
        "can_rollback": True,
    }) == {pygame.K_v, pygame.K_z}


def test_failed_physical_session_has_clear_error_control():
    keys = _keys({
        "camera_enabled": True,
        "simulation_enabled": True,
        "robot_moves_enabled": True,
        "can_rollback": True,
        "move_sync_error": "HOMECHESS frame mismatch",
        "physical_sync_fault": True,
    })
    assert pygame.K_F12 in keys


def test_clear_error_control_is_hidden_without_recovery():
    assert pygame.K_F12 not in _keys({
        "camera_enabled": True,
        "simulation_enabled": True,
        "robot_moves_enabled": True,
        "can_rollback": True,
    })


def test_no_history_hides_rollback():
    assert pygame.K_z not in _keys({
        "camera_enabled": False,
        "simulation_enabled": False,
        "robot_moves_enabled": True,
        "can_rollback": False,
    })


def test_hidden_emergency_control_does_not_activate_in_virtual_mode():
    from types import SimpleNamespace
    from src.core.game_state import GameState
    from src.core.session_profile import make_profile
    from src.ui.input_handler import InputHandler
    from src.ui.board_renderer import BTN_EMERGENCY_RECT

    state = GameState()
    state.session_profile = make_profile("HUMAN_VS_ROBOT", "VIRTUAL")
    handler = InputHandler(state, SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND="VIRTUAL"),
                                                   dry_run=True, cam_monitor=None, yolo_detector=None))
    handler.handle_mouse_down(*BTN_EMERGENCY_RECT.center)
    assert state.emergency_mode is False


def test_simulation_without_viewer_hides_viewer_sync_control():
    assert pygame.K_v not in _keys({
        "camera_enabled": False,
        "simulation_enabled": True,
        "viewer_enabled": False,
        "robot_moves_enabled": True,
        "can_rollback": True,
    })


def test_board_grid_is_drawn_without_client_controls(monkeypatch):
    import os
    from src.core.game_state import GameState
    from src.core.session_profile import make_profile
    from src.ui.board_renderer import BoardRenderer, SCREEN_HEIGHT, SCREEN_WIDTH

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    try:
        renderer = BoardRenderer(pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)))
        calls = []
        monkeypatch.setattr(renderer, "_draw_board_grid", lambda: calls.append(True))
        state = GameState()
        state.allow_mouse_move = True
        state.session_profile = make_profile(
            "HUMAN_VS_ROBOT", "VIRTUAL", simulation_enabled=False)
        renderer.draw_ui(state.get_render_state())
        assert calls == [True]
    finally:
        pygame.quit()
