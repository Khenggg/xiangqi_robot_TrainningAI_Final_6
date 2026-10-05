import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from src.hardware.hardware_manager import HardwareManager
from src.vision.visual_pick_estimator import GridTarget, VisualPickEstimator


class CenterPickFallbackTests(unittest.TestCase):
    def hardware(self, values):
        hw = HardwareManager.__new__(HardwareManager)
        hw.config = SimpleNamespace(VISUAL_CENTER_PICK_ATTEMPTS=3,
                                    VISUAL_PICK_MIN_STABLE_SAMPLES=2,
                                    VISUAL_CENTER_PICK_MAX_JITTER_CELLS=0.12)
        hw.cam_monitor = Mock()
        hw.cam_monitor.get_fresh_snapshot.return_value = (object(), [])
        hw.center_pick_estimator = Mock()
        hw.center_pick_estimator.estimate_pick_target.side_effect = values
        hw.center_pick_estimator.aggregate_targets = VisualPickEstimator.aggregate_targets
        hw.get_visual_pick_targets = Mock(return_value={"moving": "fallback-target"})
        return hw

    def test_missing_center_uses_foot_fallback(self):
        hw = self.hardware([None] * 3)
        result = hw.get_robot_center_pick_targets({'moving': (2, 3)})
        self.assertEqual(result, {"moving": "fallback-target"})
        hw.get_visual_pick_targets.assert_called_once_with({'moving': (2, 3)})

    def test_unstable_centers_use_foot_fallback(self):
        hw = self.hardware([GridTarget(2, 3 + offset, 0.9, abs(offset)) for offset in (-0.2, 0, 0.2)])
        result = hw.get_robot_center_pick_targets({'moving': (2, 3)})
        self.assertEqual(result, {"moving": "fallback-target"})
        hw.get_visual_pick_targets.assert_called_once_with({'moving': (2, 3)})

    def test_stable_center_is_returned_without_foot_fallback(self):
        target = GridTarget(2.1, 3.05, 0.9, 0.112)
        hw = self.hardware([target] * 3)
        result = hw.get_robot_center_pick_targets({'moving': (2, 3)})
        self.assertEqual(result['moving'], target)
        hw.get_visual_pick_targets.assert_not_called()

    def test_unavailable_camera_uses_foot_fallback(self):
        hw = self.hardware([])
        hw.cam_monitor = None
        result = hw.get_robot_center_pick_targets({'moving': (2, 3)})
        self.assertEqual(result, {"moving": "fallback-target"})
        hw.get_visual_pick_targets.assert_called_once_with({'moving': (2, 3)})


if __name__ == '__main__':
    unittest.main()
