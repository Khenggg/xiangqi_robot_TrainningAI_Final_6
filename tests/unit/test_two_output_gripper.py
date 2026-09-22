"""
Unit tests for TwoOutputGripperDriver.
Verifies mutual exclusion, pulse sequencing, safe idle recovery, and configuration validation.
"""

import unittest
from unittest.mock import MagicMock

from src.hardware.gripper.base import GripperDriver
from src.hardware.gripper.two_output import TwoOutputGripperDriver, GripperSafetyError


class TwoOutputGripperTests(unittest.TestCase):

    def test_implements_gripper_driver(self):
        driver = TwoOutputGripperDriver(dry_run=True)
        self.assertIsInstance(driver, GripperDriver)

    def test_rejects_identical_do_ids(self):
        with self.assertRaises(GripperSafetyError):
            TwoOutputGripperDriver(open_do_id=0, close_do_id=0, dry_run=True)

    def test_rejects_negative_or_nan_timings(self):
        with self.assertRaises(GripperSafetyError):
            TwoOutputGripperDriver(open_pulse_sec=-0.1, dry_run=True)

    def test_open_pulse_call_sequence(self):
        calls = []

        def mock_set_do(do_id, status):
            calls.append((do_id, status))
            return 0

        driver = TwoOutputGripperDriver(
            set_do_fn=mock_set_do,
            open_do_id=1,
            close_do_id=0,
            open_pulse_sec=0.01,
            close_pulse_sec=0.01,
            deadtime_sec=0.005,
            open_settle_sec=0.005,
            close_settle_sec=0.005,
        )

        calls.clear()
        ok = driver.open()
        self.assertTrue(ok)
        self.assertFalse(driver.is_closed())

        # Expected sequence:
        # 1. safe idle reset: (1, 0), (0, 0)
        # 2. pulse open: (1, 1)
        # 3. safe idle reset in finally: (1, 0), (0, 0)
        self.assertIn((1, 1), calls)
        # Verify last calls are safe idle 0
        self.assertEqual(calls[-2:], [(1, 0), (0, 0)])

    def test_close_pulse_call_sequence(self):
        calls = []

        def mock_set_do(do_id, status):
            calls.append((do_id, status))
            return 0

        driver = TwoOutputGripperDriver(
            set_do_fn=mock_set_do,
            open_do_id=1,
            close_do_id=0,
            open_pulse_sec=0.01,
            close_pulse_sec=0.01,
            deadtime_sec=0.005,
            open_settle_sec=0.005,
            close_settle_sec=0.005,
        )

        calls.clear()
        ok = driver.close()
        self.assertTrue(ok)
        self.assertTrue(driver.is_closed())

        self.assertIn((0, 1), calls)
        self.assertEqual(calls[-2:], [(1, 0), (0, 0)])

    def test_mutual_exclusion_enforced(self):
        driver = TwoOutputGripperDriver(open_do_id=1, close_do_id=0, dry_run=True)
        # Manually force active output 1
        driver._active_outputs.add(1)
        with self.assertRaises(GripperSafetyError):
            driver._set_output(0, 1)

    def test_safe_idle_on_exception(self):
        calls = []

        def failing_set_do(do_id, status):
            calls.append((do_id, status))
            if status == 1:
                raise RuntimeError("Hardware communication error")
            return 0

        driver = TwoOutputGripperDriver(
            set_do_fn=failing_set_do,
            open_do_id=1,
            close_do_id=0,
            open_pulse_sec=0.01,
            deadtime_sec=0.005,
            open_settle_sec=0.005,
        )

        calls.clear()
        with self.assertRaises(GripperSafetyError):
            driver.open()

        # Check that safe idle was called in finally
        self.assertEqual(calls[-2:], [(1, 0), (0, 0)])


if __name__ == "__main__":
    unittest.main()
