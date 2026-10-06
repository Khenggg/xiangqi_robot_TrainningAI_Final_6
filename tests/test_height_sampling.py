"""Selection and UI ownership tests; no real camera/robot."""
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from src.vision.visual_pick_estimator import GridTarget
from src.vision.height_pick_geometry import aggregate_height_targets
from src.ui.input_handler import InputHandler


def point(col, confidence=.9):
    return GridTarget(col, 6., confidence, abs(col-6))


class HeightSamplingTests(unittest.TestCase):
    def test_pick_scan_pauses_capture_and_restores_on_failure(self):
        from src.vision.camera_monitor import CameraMonitor
        monitor = CameraMonitor.__new__(CameraMonitor)
        monitor._pick_scan_active = threading.Event()
        monitor._pick_scan_lock = threading.Lock()
        monitor._stop_event = threading.Event()
        monitor.cap = Mock()
        with self.assertRaises(ValueError):
            with monitor.pick_scan_session():
                self.assertTrue(monitor._pick_scan_active.is_set())
                with unittest.mock.patch.object(monitor._stop_event, 'wait',
                                                side_effect=lambda _: monitor._stop_event.set()):
                    monitor._capture_loop()
                monitor.cap.read.assert_not_called()
                raise ValueError('failure')
        self.assertFalse(monitor._pick_scan_active.is_set())
    def test_missing_frames_mean_all_available_coherent_points(self):
        target, method = aggregate_height_targets([None, point(6.01), point(6.03), None, point(6.08)], (6, 6))
        self.assertEqual(method, 'mean')
        self.assertAlmostEqual(target.col, 6.04)
        self.assertIsNone(aggregate_height_targets([None, point(6)], (6, 6))[0])

    def test_unstable_selects_top_three_confidence_then_median(self):
        samples = [point(5.8, .5), point(6.01, .97), point(6.02, .93), point(6.05, .91), point(6.2, .6)]
        target, method = aggregate_height_targets(samples, (6, 6))
        self.assertEqual(method, 'top3-median')
        self.assertAlmostEqual(target.col, 6.02)

    def test_confident_but_disagreeing_points_remain_blocked(self):
        result, reason = aggregate_height_targets([point(5.8, .99), point(6., .98), point(6.2, .97)], (6, 6))
        self.assertIsNone(result)
        self.assertIn('dispersed', reason)

    def test_worker_keeps_input_and_player_poll_out_of_physical_job(self):
        handler = InputHandler.__new__(InputHandler)
        handler.state = SimpleNamespace(physical_motion_busy=False)
        handler.hw = SimpleNamespace(config=SimpleNamespace(VISUAL_MOTION_ASYNC_ENABLED=True))
        handler._motion_thread = None
        handler._board_stability_monitor = Mock()
        entered, release = threading.Event(), threading.Event()
        calls = []
        def operation():
            entered.set()
            release.wait(2)
            calls.append('done')
        try:
            self.assertTrue(handler._defer_motion(operation))
            self.assertTrue(entered.wait(1))
            self.assertTrue(handler.state.physical_motion_busy)
            handler.handle_keyboard(0)
            handler.handle_mouse_down(0, 0)
            self.assertFalse(handler.poll_board_stability())
            self.assertTrue(handler._defer_motion(lambda: calls.append('duplicate')))
        finally:
            release.set()
            handler._motion_thread.join(2)
        self.assertEqual(calls, ['done'])
        self.assertFalse(handler.state.physical_motion_busy)


if __name__ == '__main__':
    unittest.main()
