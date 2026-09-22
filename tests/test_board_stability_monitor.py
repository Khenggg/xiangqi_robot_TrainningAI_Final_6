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
