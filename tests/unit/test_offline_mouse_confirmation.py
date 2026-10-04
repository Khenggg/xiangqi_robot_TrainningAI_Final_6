from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import pygame
import config
from src.core.game_state import GameState
from src.ui.board_renderer import BoardRenderer, BTN_CONFIRM_MOVE_RECT
from src.ui.input_handler import InputHandler


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(config, "GAME_MODE", "HUMAN_VS_ROBOT")
    state = GameState(allow_mouse_move=True)
    state.api_client.send_move_update_board = Mock()
    observer = Mock(return_value=True)
    state.set_board_observer(observer)
    hw = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND="VIRTUAL"),
                         dry_run=True, cam_monitor=None, yolo_detector=None)
    return state, InputHandler(state, hw), observer


def move_mouse(handler, src, dst):
    handler.handle_mouse_down(*BoardRenderer.grid_to_pixel(*src))
    handler.handle_mouse_down(*BoardRenderer.grid_to_pixel(*dst))


def test_mouse_then_space_and_button_commit_once_without_camera(offline):
    state, handler, observer = offline
    move_mouse(handler, (4, 6), (4, 5))
    assert state.board[5][4] == "r_P" and state.board[6][4] == "."
    assert state.turn == "b" and state.human_commit_generation == 1
    handler.handle_keyboard(pygame.K_SPACE)
    handler.handle_mouse_down(*BTN_CONFIRM_MOVE_RECT.center)
    assert "không cần SPACE" in state.status_message
    assert len(state.move_log) == 1 and state.human_commit_generation == 1
    observer.assert_called_once_with(state.piece_ids)


def test_offline_human_vs_human_can_confirm_both_colors_without_camera(offline, monkeypatch):
    monkeypatch.setattr(config, "GAME_MODE", "HUMAN_VS_HUMAN")
    state, handler, observer = offline
    move_mouse(handler, (4, 6), (4, 5))
    handler.handle_keyboard(pygame.K_SPACE)
    move_mouse(handler, (0, 3), (0, 4))
    handler.handle_keyboard(pygame.K_SPACE)
    assert state.board[4][0] == "b_P" and state.turn == "r"
    assert len(state.move_log) == 2 and observer.call_count == 2


def test_space_preserves_sync_fault(offline):
    state, handler, _ = offline
    state.physical_sync_fault = True
    state.set_status("Motion failed; recovery required")
    handler.handle_keyboard(pygame.K_SPACE)
    assert state.status_message == "Motion failed; recovery required"
    assert state.physical_sync_fault


def test_real_camera_mode_still_requires_recognition(offline):
    state, handler, observer = offline
    handler.hw.dry_run = False
    handler.hw.config.ROBOT_BACKEND = "FAIRINO"
    handler.handle_keyboard(pygame.K_SPACE)
    assert "nhận diện chưa khởi tạo" in state.status_message
    assert not state.move_log
    observer.assert_not_called()


def test_renderer_shows_offline_instructions_and_robot_turn(offline, monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    pygame.display.init()
    pygame.font.init()
    try:
        renderer = BoardRenderer.__new__(BoardRenderer)
        renderer.screen = pygame.Surface((1440, 1080))
        font = pygame.font.Font(None, 22)
        recorded = []
        class RecordingFont:
            def render(self, text, *args):
                recorded.append(text)
                return font.render(text, *args)
            def size(self, text):
                return font.size(text)
        renderer.ui_font = renderer.button_font = renderer.log_font = RecordingFont()
        state, handler, _ = offline
        renderer._draw_client_actions(state.get_render_state())
        assert "TỰ XÁC NHẬN" in recorded and "NƯỚC ĐỎ" not in recorded
        move_mouse(handler, (4, 6), (4, 5))
        state.status_expiry = 0
        renderer._draw_ai_status(state.get_render_state())
        assert any("Lượt robot" in text for text in recorded)
        assert not any("then confirm with SPACE" in text for text in recorded)
        recorded.clear()
        state.move_sync_error = "retained motion error"
        state.status_expiry = 0
        renderer._draw_ai_status(state.get_render_state())
        assert any("retained motion error" in text for text in recorded)
        assert not any("Lượt robot" in text for text in recorded)
    finally:
        pygame.display.quit()
