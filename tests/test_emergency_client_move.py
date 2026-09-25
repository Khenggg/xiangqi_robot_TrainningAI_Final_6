import unittest
from unittest.mock import patch

import pygame

from src.core import xiangqi
from src.ui.input_handler import InputHandler


class EmergencyClientMoveTests(unittest.TestCase):
    def test_resume_scan_only_unpauses_after_a_new_baseline_is_captured(self):
        class State:
            allow_mouse_move = False
            game_over = False
            turn = "r"
            manual_override_active = True

            def __init__(self):
                self.statuses = []

            def set_status(self, message, **kwargs):
                self.statuses.append(message)

        class Hardware:
            yolo_detector = object()
            cam_monitor = object()

            def __init__(self, result):
                self.result = result
                self.calls = 0

            def capture_baseline_if_needed(self, force_delay=0.0):
                self.calls += 1
                self.force_delay = force_delay
                return self.result

        state = State()
        hardware = Hardware(True)
        handler = InputHandler(state, hardware)
        self.assertTrue(handler.resume_automatic_scanning())
        self.assertFalse(state.manual_override_active)
        self.assertEqual(1, hardware.calls)
        self.assertEqual(0.0, hardware.force_delay)

        state.manual_override_active = True
        failed_hardware = Hardware(False)
        failed_handler = InputHandler(state, failed_hardware)
        self.assertFalse(failed_handler.resume_automatic_scanning())
        self.assertTrue(state.manual_override_active)

    def test_resume_scan_refuses_to_baseline_a_board_that_still_differs_from_fen(self):
        class State:
            allow_mouse_move = False
            game_over = False
            turn = "r"
            manual_override_active = True
            board = xiangqi.get_board()

            def set_status(self, *args, **kwargs):
                pass

        class Hardware:
            yolo_detector = object()
            cam_monitor = object()

            def verify_physical_board(self, board):
                return False

            def capture_baseline_if_needed(self, force_delay=0.0):
                raise AssertionError("must not replace baseline for mismatched FEN")

        state = State()
        hardware = Hardware()
        hardware.board_reconciler = object()
        self.assertFalse(InputHandler(state, hardware).resume_automatic_scanning())
        self.assertTrue(state.manual_override_active)

    def test_resume_scan_uses_legacy_baseline_when_reconciler_is_unavailable(self):
        class State:
            allow_mouse_move = False
            game_over = False
            turn = "r"
            manual_override_active = True
            board = xiangqi.get_board()

            def set_status(self, *args, **kwargs):
                pass

        class Hardware:
            yolo_detector = object()
            cam_monitor = object()
            board_reconciler = None

            def verify_physical_board(self, board):
                return False

            def capture_baseline_if_needed(self, force_delay=0.0):
                return True

        state = State()
        self.assertTrue(InputHandler(state, Hardware()).resume_automatic_scanning())
        self.assertFalse(state.manual_override_active)

    def test_m_key_enables_client_move_and_pauses_board_auto_confirm(self):
        class State:
            allow_mouse_move = False
            game_over = False
            turn = "r"
            manual_override_active = False
            physical_sync_fault = False

            def __init__(self):
                self.statuses = []

            def set_status(self, message, **kwargs):
                self.statuses.append(message)

        class Hardware:
            pass

        state = State()
        handler = InputHandler(state, Hardware())
        handler.handle_keyboard(pygame.K_m)

        self.assertTrue(state.manual_override_active)
        self.assertIn("Emergency client mode", state.statuses[-1])
        self.assertFalse(handler.poll_board_stability())

    def test_space_confirmation_exits_emergency_mode(self):
        class Detector:
            _baseline_occ = [[False for _ in range(9)] for _ in range(10)]
            _baseline_time = 1.0

            def has_baseline(self):
                return True

            def detect_move(self, *args, **kwargs):
                return (0, 6), (0, 5), "r_P"

        class Camera:
            def get_fresh_snapshot(self):
                return object(), []

        class State:
            allow_mouse_move = False
            game_over = False
            turn = "r"
            manual_override_active = False
            physical_sync_fault = False
            board = xiangqi.get_board()

            def set_status(self, *args, **kwargs):
                pass

            def save_rollback_state(self, *args):
                pass

            def process_human_move(self, *args):
                self.turn = "b"

        class Hardware:
            yolo_detector = Detector()
            cam_monitor = Camera()
            cchess_recognizer = None

        state = State()
        handler = InputHandler(state, Hardware())
        with patch("builtins.print"):
            handler.handle_keyboard(pygame.K_m)
            self.assertTrue(handler._handle_space_key())
        self.assertFalse(state.manual_override_active)

    def test_emergency_click_move_saves_rollback_state(self):
        class Detector:
            _baseline_occ = [[False for _ in range(9)] for _ in range(10)]
            _baseline_time = 4.0

            def has_baseline(self):
                return True

        class State:
            allow_mouse_move = False
            game_over = False
            turn = "r"
            manual_override_active = True
            physical_sync_fault = False
            selected_pos = None
            board = xiangqi.get_board()

            def __init__(self):
                self.rollback = None

            def save_rollback_state(self, occ, baseline_time):
                self.rollback = (occ, baseline_time)

            def process_human_move(self, *args):
                pass

        class Hardware:
            yolo_detector = Detector()
            cam_monitor = None

        state = State()
        handler = InputHandler(state, Hardware())
        with (patch("builtins.print"),
              patch("src.ui.input_handler.BoardRenderer.pixel_to_grid", side_effect=[(0, 6), (0, 5)])):
            handler.handle_mouse_down(0, 0)
            handler.handle_mouse_down(0, 0)

        self.assertIsNotNone(state.rollback)
        self.assertEqual(4.0, state.rollback[1])


if __name__ == "__main__":
    unittest.main()
