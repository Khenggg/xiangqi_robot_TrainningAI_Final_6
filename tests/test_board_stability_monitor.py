import unittest

from src.core import xiangqi
from src.ui.input_handler import InputHandler
from src.vision.board_stability_monitor import BoardStabilityMonitor


class BoardStabilityMonitorTests(unittest.TestCase):
    def setUp(self):
        self.move = ((0, 6), (0, 5), "r_P")

    def test_confirms_after_three_matching_samples_over_window(self):
        monitor = BoardStabilityMonitor(stability_seconds=1.2, min_samples=3)
        self.assertIsNone(monitor.observe(self.move, now=0.0))
        self.assertIsNone(monitor.observe(self.move, now=0.6))
        self.assertEqual(self.move, monitor.observe(self.move, now=1.2))
        self.assertIsNone(monitor.observe(self.move, now=1.4))

    def test_does_not_confirm_before_window_or_sample_count(self):
        monitor = BoardStabilityMonitor(stability_seconds=1.2, min_samples=3)
        monitor.observe(self.move, now=0.0)
        self.assertIsNone(monitor.observe(self.move, now=1.2))

    def test_candidate_change_or_missing_sample_restarts_window(self):
        monitor = BoardStabilityMonitor(stability_seconds=1.2, min_samples=3)
        other_move = ((1, 7), (1, 6), "r_C")
        monitor.observe(self.move, now=0.0)
        monitor.observe(self.move, now=0.6)
        self.assertIsNone(monitor.observe(other_move, now=0.8))
        self.assertIsNone(monitor.observe(other_move, now=1.5))
        self.assertIsNone(monitor.observe(None, now=1.6))
        self.assertIsNone(monitor.observe(other_move, now=2.0))
        self.assertIsNone(monitor.observe(other_move, now=2.6))
        self.assertEqual(other_move, monitor.observe(other_move, now=3.2))

    def test_rejects_a_stability_window_outside_configured_bounds(self):
        with self.assertRaises(ValueError):
            BoardStabilityMonitor(stability_seconds=0.9, min_samples=3)
        with self.assertRaises(ValueError):
            BoardStabilityMonitor(stability_seconds=1.6, min_samples=3)

    def test_replaced_baseline_discards_partial_candidate(self):
        candidate = ((0, 6), (0, 5), "r_P")

        class Detector:
            _baseline_occ = [[False for _ in range(9)] for _ in range(10)]
            _baseline_time = 2.0

            def has_baseline(self):
                return True

            def detect_move(self, *args, **kwargs):
                return candidate

        class Camera:
            def get_fresh_snapshot(self):
                return object(), []

        class State:
            turn = "r"
            game_over = False
            board = xiangqi.get_board()
            committed = False

            def process_human_move(self, *args):
                self.committed = True

        class Hardware:
            yolo_detector = Detector()
            cam_monitor = Camera()
            cchess_recognizer = None

        state = State()
        handler = InputHandler(state, Hardware())
        handler._board_stability_monitor.observe(candidate, now=0.0)
        handler._board_stability_monitor.observe(candidate, now=0.6)
        handler._observed_baseline_time = 1.0

        self.assertFalse(handler.poll_board_stability())
        self.assertFalse(state.committed)
        self.assertEqual(1, handler._board_stability_monitor._sample_count)

    def test_full_board_desync_shows_a_warning_without_committing_a_move(self):
        class State:
            board = xiangqi.get_board()
            game_epoch = 0
            human_commit_generation = 0

            def __init__(self):
                self.statuses = []

            def set_status(self, message, **kwargs):
                self.statuses.append(message)

        class Config:
            BOARD_WARNING_CHECK_INTERVAL_SECONDS = 0.0
            BOARD_WARNING_MIN_STABLE_SAMPLES = 2

        class Hardware:
            config = Config()

        state = State()
        handler = InputHandler(state, Hardware())
        observed = xiangqi.get_board()
        observed[4][8] = "r_R"  # Extra Red Rook at i4 is not a legal successor.

        handler._check_board_warning({"success": True, "board": observed}, now=1.0)
        handler._check_board_warning({"success": True, "board": observed}, now=1.1)

        self.assertEqual(
            "⚠️ Board does not match the expected position.", state.statuses[-1]
        )

    def test_legal_successor_does_not_show_a_desync_warning(self):
        class State:
            board = xiangqi.get_board()
            game_epoch = 0
            human_commit_generation = 0

            def __init__(self):
                self.statuses = []

            def set_status(self, message, **kwargs):
                self.statuses.append(message)

        class Config:
            BOARD_WARNING_CHECK_INTERVAL_SECONDS = 0.0
            BOARD_WARNING_MIN_STABLE_SAMPLES = 2

        class Hardware:
            config = Config()

        state = State()
        handler = InputHandler(state, Hardware())
        observed, _ = xiangqi.make_temp_move(state.board, ((0, 6), (0, 5)))

        handler._check_board_warning({"success": True, "board": observed}, now=1.0)

        self.assertEqual([], state.statuses)

    def test_stable_illegal_red_move_shows_its_coordinate_warning(self):
        class State:
            board = xiangqi.get_board()
            game_epoch = 0
            human_commit_generation = 0

            def __init__(self):
                self.statuses = []

            def set_status(self, message, **kwargs):
                self.statuses.append(message)

        class Config:
            BOARD_WARNING_CHECK_INTERVAL_SECONDS = 0.0
            BOARD_WARNING_MIN_STABLE_SAMPLES = 2

        class Hardware:
            config = Config()

        state = State()
        handler = InputHandler(state, Hardware())
        observed, _ = xiangqi.make_temp_move(state.board, ((0, 6), (1, 5)))

        handler._check_board_warning({"success": True, "board": observed}, now=1.0)
        handler._check_board_warning({"success": True, "board": observed}, now=1.1)

        self.assertEqual(
            "❌ Illegal move: a6 -> b5 — move not accepted.", state.statuses[-1]
        )

    def test_stable_same_square_piece_flip_shows_unstable_fen_warning(self):
        class State:
            board = xiangqi.get_board()
            game_epoch = 0
            human_commit_generation = 0

            def __init__(self):
                self.statuses = []

            def set_status(self, message, **kwargs):
                self.statuses.append(message)

        class Config:
            BOARD_WARNING_CHECK_INTERVAL_SECONDS = 0.0
            BOARD_WARNING_MIN_STABLE_SAMPLES = 2

        class Hardware:
            config = Config()

        state = State()
        state.board[4][2] = "r_P"
        observed = xiangqi.get_board()
        observed[4][2] = "r_C"
        handler = InputHandler(state, Hardware())

        handler._check_board_warning({"success": True, "board": observed}, now=1.0)
        handler._check_board_warning({"success": True, "board": observed}, now=1.1)

        self.assertEqual("⚠️ Unstable FEN detection at c4", state.statuses[-1])

    def test_legal_layout_clears_only_the_checker_warning(self):
        class State:
            board = xiangqi.get_board()
            game_epoch = 0
            human_commit_generation = 0

            def __init__(self):
                self.status_message = ""

            def set_status(self, message, **kwargs):
                self.status_message = message

        class Config:
            BOARD_WARNING_CHECK_INTERVAL_SECONDS = 0.0
            BOARD_WARNING_MIN_STABLE_SAMPLES = 1

        class Hardware:
            config = Config()

        state = State()
        handler = InputHandler(state, Hardware())
        mismatched = xiangqi.get_board()
        mismatched[4][8] = "r_R"
        handler._check_board_warning({"success": True, "board": mismatched}, now=1.0)
        handler._check_board_warning({"success": True, "board": mismatched}, now=1.1)
        self.assertIn("Board does not match", state.status_message)

        handler._check_board_warning({"success": True, "board": state.board}, now=1.3)
        self.assertEqual("", state.status_message)
