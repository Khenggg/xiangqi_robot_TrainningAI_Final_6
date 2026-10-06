import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import pygame
from src.ui.input_handler import InputHandler
from src.ui.board_renderer import BoardRenderer
from src.hardware.hardware_manager import HardwareManager
from src.core.game_state import GameState


class PickPlaceModeTests(unittest.TestCase):
    def make_handler(self):
        board = [["." for _ in range(9)] for _ in range(10)]
        board[0][0] = "b_R"
        board[9][0] = "r_R"
        state = SimpleNamespace(board=board, game_over=False, selected_pos=None,
                                turn="r", ai_thinking=False, ai_thread=None,
                                set_status=Mock(), pending_ai_move=None)
        target = SimpleNamespace(col=0.1, row=0.1)
        hardware = SimpleNamespace(execute_pick_place_test=Mock(return_value=target))
        return InputHandler(state, hardware)

    def click(self, handler, col, row):
        handler.handle_mouse_down(*BoardRenderer.grid_to_pixel(col, row))

    def test_any_color_moves_without_rules_or_game_board_mutation(self):
        handler = self.make_handler()
        handler.handle_keyboard(pygame.K_t)
        # Rook diagonal would be illegal, and Black is not the side to move.
        self.click(handler, 0, 0)
        self.click(handler, 3, 4)
        handler.hw.execute_pick_place_test.assert_called_once_with((0, 0), (3, 4))
        self.assertEqual(handler.state.pick_test_board[4][3], "b_R")
        self.assertEqual(handler.state.board[0][0], "b_R")
        self.assertEqual(handler.state.turn, "r")

    def test_occupied_destination_reselects_without_arm_motion(self):
        handler = self.make_handler()
        handler.handle_keyboard(pygame.K_t)
        self.click(handler, 0, 0)
        self.click(handler, 0, 9)
        handler.hw.execute_pick_place_test.assert_not_called()
        self.assertEqual(handler.state.selected_pos, (0, 9))

    def test_failure_preserves_test_board(self):
        handler = self.make_handler()
        handler.hw.execute_pick_place_test.side_effect = RuntimeError("No vision")
        handler.handle_keyboard(pygame.K_t)
        self.click(handler, 0, 0)
        self.click(handler, 3, 4)
        self.assertEqual(handler.state.pick_test_board[0][0], "b_R")
        self.assertEqual(handler.state.pick_test_board[4][3], ".")

    def test_exit_and_space_do_not_resume_ai(self):
        handler = self.make_handler()
        handler.handle_keyboard(pygame.K_t)
        handler.handle_keyboard(pygame.K_t)
        self.assertFalse(handler.state.pick_test_mode)
        self.assertTrue(handler.state.pick_test_resume_required)
        state = GameState.__new__(GameState)
        state.pick_test_resume_required = True
        self.assertFalse(state.can_start_ai_turn())
        handler.handle_keyboard(pygame.K_SPACE)
        handler.hw.execute_pick_place_test.assert_not_called()

    def test_entry_blocked_during_ai_job(self):
        handler = self.make_handler()
        handler.state.ai_thinking = True
        handler.handle_keyboard(pygame.K_t)
        self.assertFalse(getattr(handler.state, "pick_test_mode", False))

    def make_hardware(self):
        hardware = HardwareManager.__new__(HardwareManager)
        hardware.robot = Mock(connected=True)
        hardware.center_pick_estimator = object()
        hardware.cam_monitor = object()
        hardware.is_cell_visually_clear = Mock(return_value=True)
        hardware.verify_visual_move = Mock(return_value=True)
        hardware.get_robot_center_pick_targets = Mock(return_value={"moving": SimpleNamespace(col=0.1, row=0.1, confidence=0.9, offset_cells=0.14)})
        return hardware

    def test_hardware_passes_measured_target_to_production_motion(self):
        hardware = self.make_hardware()
        target = hardware.execute_pick_place_test((0, 0), (3, 4))
        hardware.robot.move_piece.assert_called_once_with(0, 0, 3, 4, False,
                                                        moving_visual_target=target,
                                                        require_visual_target=False)
        hardware.verify_visual_move.assert_called_once_with((0, 0), (3, 4))

    def test_missing_target_or_occupied_destination_blocks_motion(self):
        for blocked_vision in (True, False):
            hardware = self.make_hardware()
            hardware.config = SimpleNamespace(VISUAL_TOP_FACE_ENABLED=True)
            if blocked_vision:
                hardware.get_robot_center_pick_targets.return_value = {"moving": None}
            else:
                hardware.is_cell_visually_clear.return_value = False
            with self.assertRaises(RuntimeError):
                hardware.execute_pick_place_test((0, 0), (3, 4))
            hardware.robot.move_piece.assert_not_called()

    def test_legacy_missing_visual_target_uses_logical_cell(self):
        hardware = self.make_hardware()
        hardware.get_robot_center_pick_targets.return_value = {"moving": None}
        target = hardware.execute_pick_place_test((2, 3), (4, 5))
        hardware.robot.move_piece.assert_called_once_with(2, 3, 4, 5, False,
            moving_visual_target=None, require_visual_target=False)
        self.assertEqual((target.col, target.row, target.confidence), (2, 3, 0))
        hardware.verify_visual_move.assert_called_once_with((2, 3), (4, 5))


if __name__ == '__main__':
    unittest.main()
