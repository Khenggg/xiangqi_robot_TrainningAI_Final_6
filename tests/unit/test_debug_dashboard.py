"""
Unit tests for DebugDashboard.
Verifies telemetry extraction from RobotBackend and legacy robot without blocking.
"""

import unittest
from unittest.mock import MagicMock

from src.hardware.backends.base import RobotBackend, RobotStateSnapshot
from src.ui.debug_dashboard import DebugDashboard


class DebugDashboardTests(unittest.TestCase):

    def test_snapshot_with_backend(self):
        mock_backend = MagicMock(spec=RobotBackend)
        mock_backend.get_state_snapshot.return_value = RobotStateSnapshot(
            robot_model="FR3",
            connected=True,
            motion_state="IDLE",
            joints_deg=[0, -45, 90, -135, -90, 0],
            flange_pose_mm_deg=[-360, 0, 418, 180, 0, 90],
            tcp_pose_mm_deg=[-360.0, 0.0, 200.0, 180.0, 0.0, 90.0],
            gripper_closed=False,
            timestamp=100.0,
            last_error=None,
        )

        dashboard = DebugDashboard(dry_run=True, backend=mock_backend, spawn_process=False)
        snap = dashboard.snapshot()

        self.assertEqual(snap["mode"], "DRY RUN")
        self.assertEqual(snap["connection"], "Connected")
        self.assertEqual(snap["motion"], "IDLE")
        self.assertIn("-360.00 mm", snap["live"])
        dashboard.close()

    def test_snapshot_disconnected(self):
        dashboard = DebugDashboard(dry_run=False, backend=None, robot=None, spawn_process=False)
        snap = dashboard.snapshot()

        self.assertEqual(snap["mode"], "REAL RUN")
        self.assertEqual(snap["connection"], "Not connected")
        self.assertEqual(snap["live"], "Unavailable")
        dashboard.close()


if __name__ == "__main__":
    unittest.main()
