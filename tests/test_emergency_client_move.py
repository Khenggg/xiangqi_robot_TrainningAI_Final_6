import unittest
from unittest.mock import patch

import pygame

from src.core import xiangqi
from src.core.game_state import GameState
from src.ui.board_renderer import BTN_CONTINUE_RECT, BTN_EMERGENCY_RECT
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

    def test_m_key_is_available_in_dry_run_mode(self):
        class State:
            allow_mouse_move = True
            game_over = False
            turn = "b"
            manual_override_active = False
            physical_sync_fault = False

            def set_status(self, *args, **kwargs):
                pass

        handler = InputHandler(State(), type("Hardware", (), {})())
        handler.handle_keyboard(pygame.K_m)
        self.assertTrue(handler.state.emergency_mode)

    def test_emergency_panel_button_dispatches_m_key(self):
        class State:
            allow_mouse_move = False
            game_over = False
            turn = "r"
            manual_override_active = False
            physical_sync_fault = False

            def set_status(self, *args, **kwargs):
                pass

        state = State()
        handler = InputHandler(state, type("Hardware", (), {})())
        handler.handle_mouse_down(*BTN_EMERGENCY_RECT.center)

        self.assertTrue(state.emergency_mode)
        self.assertTrue(state.manual_override_active)

    def test_disabled_continue_button_does_not_select_a_board_piece(self):
        class State:
            allow_mouse_move = False
            game_over = False
            turn = "r"
            manual_override_active = True
            snapshot_continue_required = False
            physical_sync_fault = False
            selected_pos = None
            board = xiangqi.get_board()

            def set_status(self, *args, **kwargs):
                pass

        state = State()
        InputHandler(state, type("Hardware", (), {})()).handle_mouse_down(*BTN_CONTINUE_RECT.center)
        self.assertIsNone(state.selected_pos)

    def test_v_resume_exits_emergency_mode(self):
        class State:
            allow_mouse_move = False
            game_over = False
            turn = "r"
            manual_override_active = True
            emergency_mode = True
            physical_sync_fault = False
            board = xiangqi.get_board()

            def set_status(self, *args, **kwargs):
                pass

        class Hardware:
            yolo_detector = object()
            cam_monitor = object()
            board_reconciler = None

            def capture_baseline_if_needed(self, force_delay=0.0):
                return True

        state = State()
        InputHandler(state, Hardware()).handle_keyboard(pygame.K_v)
        self.assertFalse(state.manual_override_active)
        self.assertFalse(state.emergency_mode)

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

    def test_continue_restarts_snapshot_scanning_from_current_fen(self):
        class State:
            allow_mouse_move = False
            game_over = False
            turn = "r"
            manual_override_active = True
            snapshot_continue_required = True
            snapshot_continue_can_commit_pending = False
            emergency_mode = False
            physical_sync_fault = False
            selected_pos = (0, 6)
            board = xiangqi.get_board()

            def __init__(self):
                self.statuses = []

            def set_status(self, message, **kwargs):
                self.statuses.append(message)

        class Hardware:
            cchess_recognizer = object()

            def __init__(self):
                self.calls = 0

                class Camera:
                    def get_fresh_snapshot(_,):
                        return object(), []
                self.cam_monitor = Camera()

            def recognize_board_state(self, frame):
                return {"success": True, "board": xiangqi.get_board()}

            def capture_baseline_if_needed(self, force_delay=0.0):
                self.calls += 1
                return True

        state, hardware = State(), Hardware()
        handler = InputHandler(state, hardware)
        handler._continue_after_snapshot_pause()

        self.assertFalse(state.manual_override_active)
        self.assertFalse(state.snapshot_continue_required)
        self.assertEqual(1, hardware.calls)
        self.assertIn("Continue", state.statuses[-1])

    def test_emergency_black_move_updates_fen_and_returns_turn_to_red(self):
        state = GameState(allow_mouse_move=False)
        state.api_client.send_move_update_board = lambda fen: None
        state.turn = "b"
        state.ai_thread = object()
        state.ai_results = {"old": ((0, 0), (0, 1))}
        state.pending_ai_move = {"move": ((0, 3), (0, 4)), "expected_board": xiangqi.get_board(), "captured_piece": "."}
        state.physical_sync_fault = True
        state.snapshot_continue_required = True
        state.process_emergency_move((0, 3), (0, 4), "b_P")

        self.assertEqual("r", state.turn)
        self.assertEqual(".", state.board[3][0])
        self.assertEqual("b_P", state.board[4][0])
        self.assertEqual("w", state.current_fen.split()[1])
        self.assertIsNone(state.ai_thread)
        self.assertEqual({}, state.ai_results)
        self.assertIsNone(state.pending_ai_move)
        self.assertFalse(state.physical_sync_fault)

    def test_verified_missed_pick_reopens_one_fresh_ai_turn(self):
        state = GameState(allow_mouse_move=False)
        state.api_client.send_move_update_board = lambda fen: None
        state.turn = "b"
        state.human_commit_generation = 4
        state.ai_started_for_human_commit_generation = 4
        state.ai_epoch = 7
        state.ai_thread = object()
        state.ai_thinking = True
        state.ai_results = {"stale": "move"}

        self.assertTrue(state.prepare_ai_retry_after_physical_miss())
        self.assertEqual(4, state.ai_started_for_human_commit_generation)
        self.assertEqual(8, state.ai_epoch)
        self.assertTrue(state.ai_retry_requested)
        self.assertIsNone(state.ai_thread)
        self.assertFalse(state.ai_thinking)
        self.assertEqual({}, state.ai_results)

    def test_v_reconciliation_queues_retry_when_board_is_still_old_fen(self):
        class State:
            game_over = False
            board = xiangqi.get_board()
            pending_ai_move = {"expected_board": [["." for _ in range(9)] for _ in range(10)]}
            snapshot_continue_required = True

            def __init__(self):
                self.cleared = False
                self.retry_requested = False
                self.statuses = []

            def clear_pending_ai_move(self):
                self.cleared = True
                self.pending_ai_move = None

            def prepare_ai_retry_after_physical_miss(self):
                self.retry_requested = True
                return True

            def set_status(self, message, **kwargs):
                self.statuses.append(message)

        class Hardware:
            def verify_physical_board(self, board):
                return board == state.board

        state = State()
        handler = InputHandler(state, Hardware())
        handler._reconcile_physical_sync_fault()

        self.assertTrue(state.cleared)
        self.assertTrue(state.retry_requested)
        self.assertIn("AI đang tính lại", state.statuses[-1])

    def test_v_partial_capture_shows_manual_completion_coordinates(self):
        class State:
            game_over = False
            board = xiangqi.get_board()
            pending_ai_move = {
                "move": ((2, 2), (2, 5)),
                "expected_board": [["." for _ in range(9)] for _ in range(10)],
                "captured_piece": "r_P",
            }

            def __init__(self):
                self.statuses = []

            def set_status(self, message, **kwargs):
                self.statuses.append(message)

        class Hardware:
            def verify_physical_board(self, board):
                return False

        state = State()
        InputHandler(state, Hardware())._reconcile_physical_sync_fault()

        self.assertIn("Nước ăn chưa hoàn tất", state.statuses[-1])
        self.assertIn("(2,2)→(2,5)", state.statuses[-1])

    def test_v_after_manual_capture_completion_commits_expected_fen(self):
        state = GameState(allow_mouse_move=False)
        sent_fens = []
        state.api_client.send_move_update_board = sent_fens.append
        expected_board = [row[:] for row in state.board]
        expected_board[3][0] = "."
        expected_board[6][0] = "b_P"
        state.set_pending_ai_move(((0, 3), (0, 6)), expected_board, "r_P")
        state.physical_sync_fault = True

        class Hardware:
            def __init__(self):
                self.baseline_calls = 0

            def verify_physical_board(self, board):
                return board == expected_board

            def capture_baseline_if_needed(self, force_delay=0.0):
                self.baseline_calls += 1
                return True

        hardware = Hardware()
        InputHandler(state, hardware)._reconcile_physical_sync_fault()

        self.assertEqual(expected_board, state.board)
        self.assertEqual("r", state.turn)
        self.assertIn("r_P", state.r_captured)
        self.assertIsNone(state.pending_ai_move)
        self.assertFalse(state.physical_sync_fault)
        self.assertEqual([state.current_fen], sent_fens)
        self.assertEqual(1, hardware.baseline_calls)

    def test_retry_start_authority_is_consumed_exactly_once(self):
        state = GameState(allow_mouse_move=False)
        state.turn = "b"
        state.human_commit_generation = 5
        state.ai_started_for_human_commit_generation = 5
        state.ai_retry_requested = True

        self.assertTrue(state.can_start_ai_turn())
        state.mark_ai_turn_started()
        self.assertFalse(state.ai_retry_requested)
        self.assertFalse(state.can_start_ai_turn())

    def test_retry_refuses_to_replace_a_live_ai_worker(self):
        class Worker:
            def is_alive(self):
                return True

        state = GameState(allow_mouse_move=False)
        state.turn = "b"
        state.ai_thread = Worker()

        self.assertFalse(state.prepare_ai_retry_after_physical_miss())
        self.assertFalse(state.ai_retry_requested)
        self.assertIsInstance(state.ai_thread, Worker)


if __name__ == "__main__":
    unittest.main()
