import unittest

from src.vision.turn_completion_monitor import TurnCompletionMonitor


class TurnCompletionMonitorTests(unittest.TestCase):
    def test_emits_once_after_hand_leaves_board(self):
        monitor = TurnCompletionMonitor(absence_seconds=0.8, min_hand_seconds=0.25)
        self.assertFalse(monitor.observe(True, now=0.0))
        self.assertFalse(monitor.observe(True, now=0.3))
        self.assertFalse(monitor.observe(False, now=0.4))
        self.assertFalse(monitor.observe(False, now=1.19))
        self.assertTrue(monitor.observe(False, now=1.21))
        self.assertFalse(monitor.observe(False, now=2.0))

    def test_ignores_a_brief_hand_flash(self):
        monitor = TurnCompletionMonitor(absence_seconds=0.5, min_hand_seconds=0.25)
        monitor.observe(True, now=0.0)
        monitor.observe(False, now=0.1)
        self.assertFalse(monitor.observe(False, now=0.7))

    def test_reset_allows_the_next_human_turn(self):
        monitor = TurnCompletionMonitor(absence_seconds=0.2, min_hand_seconds=0.1)
        monitor.observe(True, now=0.0)
        monitor.observe(False, now=0.2)
        self.assertTrue(monitor.observe(False, now=0.5))
        monitor.reset()
        monitor.observe(True, now=1.0)
        monitor.observe(False, now=1.2)
        self.assertTrue(monitor.observe(False, now=1.5))
