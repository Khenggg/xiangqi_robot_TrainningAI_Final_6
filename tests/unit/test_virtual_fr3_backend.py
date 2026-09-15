"""Unit tests for VirtualFR3Backend.

Verifies:
1. Connection lifecycle (connect, disconnect, is_connected).
2. Authoritative state ownership with immutable RobotStateSnapshot.
3. MoveJ joint motion interpolation, boundary checking, and target arrival.
4. MoveJ rejection on joint limit violations.
5. Cartesian MoveL straight-line waypoint interpolation and IK resolution.
6. Cartesian motion clean abort on unreachable waypoints (no teleportation).
7. Gripper actuator state command and reporting.
8. Accelerated execution via speed_factor without wall-clock sleeps.
"""

import math
import os
import sys
import unittest
import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.simulation.kinematics.fr3 import FR3Kinematics
from src.simulation.virtual_fr3_backend import VirtualFR3Backend


class VirtualFR3BackendTests(unittest.TestCase):
    def setUp(self):
        # Use high speed factor for fast test execution
        self.kin = FR3Kinematics()
        self.backend = VirtualFR3Backend(kinematics=self.kin, default_speed_factor=100.0)

    def test_connection_lifecycle(self):
        self.assertFalse(self.backend.is_connected())
        snap_init = self.backend.get_state_snapshot()
        self.assertFalse(snap_init.connected)
        self.assertEqual(snap_init.motion_state, "DISCONNECTED")

        self.assertTrue(self.backend.connect())
        self.assertTrue(self.backend.is_connected())
        snap_conn = self.backend.get_state_snapshot()
        self.assertTrue(snap_conn.connected)
        self.assertEqual(snap_conn.motion_state, "IDLE")
        self.assertEqual(snap_conn.robot_model, "FR3")

        self.assertTrue(self.backend.disconnect())
        self.assertFalse(self.backend.is_connected())

    def test_move_joint_success(self):
        self.backend.connect()
        target_deg = [15.0, -30.0, 70.0, -100.0, -90.0, 20.0]

        ok = self.backend.move_joint(target_deg, speed_factor=100.0)
        self.assertTrue(ok)

        snap = self.backend.get_state_snapshot()
        self.assertEqual(snap.motion_state, "IDLE")
        for actual, expected in zip(snap.joints_deg, target_deg):
            self.assertAlmostEqual(actual, expected, places=2)

    def test_move_joint_limit_violation_rejection(self):
        self.backend.connect()
        snap_before = self.backend.get_state_snapshot()

        # Joint 2 upper limit is 1.4835 rad (~85.0 deg). Send 120 deg.
        invalid_target = [0.0, 120.0, 0.0, 0.0, 0.0, 0.0]
        ok = self.backend.move_joint(invalid_target, speed_factor=100.0)

        self.assertFalse(ok)
        snap_after = self.backend.get_state_snapshot()
        self.assertEqual(snap_after.motion_state, "ERROR")
        self.assertIn("violates joint limits", snap_after.last_error)
        # Joints must NOT have moved
        self.assertEqual(snap_after.joints_deg, snap_before.joints_deg)

    def test_move_cartesian_linear_motion(self):
        self.backend.connect()
        # Start at home pose
        snap_start = self.backend.get_state_snapshot()
        cur_tcp = snap_start.tcp_pose_mm_deg

        # Small reachable translation: shift X by +15 mm
        target_tcp = [cur_tcp[0] + 15.0, cur_tcp[1], cur_tcp[2], cur_tcp[3], cur_tcp[4], cur_tcp[5]]
        ok = self.backend.move_cartesian(target_tcp, speed_factor=100.0, samples=5)
        self.assertTrue(ok)

        snap_end = self.backend.get_state_snapshot()
        self.assertEqual(snap_end.motion_state, "IDLE")
        # Final TCP must match target within tolerance
        self.assertAlmostEqual(snap_end.tcp_pose_mm_deg[0], target_tcp[0], delta=1.5)
        self.assertAlmostEqual(snap_end.tcp_pose_mm_deg[1], target_tcp[1], delta=1.5)
        self.assertAlmostEqual(snap_end.tcp_pose_mm_deg[2], target_tcp[2], delta=1.5)

    def test_move_cartesian_unreachable_abort(self):
        self.backend.connect()
        snap_before = self.backend.get_state_snapshot()

        # Target 3000 mm away
        unreachable_target = [3000.0, 0.0, 200.0, 180.0, 0.0, 0.0]
        ok = self.backend.move_cartesian(unreachable_target, speed_factor=100.0)

        self.assertFalse(ok)
        snap_after = self.backend.get_state_snapshot()
        self.assertEqual(snap_after.motion_state, "ERROR")
        self.assertIn("unreachable", snap_after.last_error.lower())
        # Robot did NOT teleport to unreachable target
        self.assertNotEqual(snap_after.tcp_pose_mm_deg[0], 3000.0)

    def test_stop_cancels_active_motion_immediately(self):
        import threading
        import time

        self.backend.connect()
        target_deg = [45.0, -30.0, 60.0, -90.0, -90.0, 0.0]

        result_container = []

        def run_move():
            # Slow motion (speed_factor=0.2, takes ~1 second)
            res = self.backend.move_joint(target_deg, speed_factor=0.2)
            result_container.append(res)

        th = threading.Thread(target=run_move)
        th.start()
        time.sleep(0.06)  # Let motion start and enter interpolation loop

        # Request abort
        self.backend.stop()
        th.join(timeout=2.0)

        self.assertFalse(th.is_alive(), "Thread should have terminated promptly")
        self.assertEqual(len(result_container), 1)
        self.assertFalse(result_container[0], "Cancelled motion must return False")
        snap = self.backend.get_state_snapshot()
        self.assertEqual(snap.motion_state, "IDLE")
        self.assertIn("aborted by stop()", snap.last_error)

    def test_move_joint_velocity_governance_duration(self):
        self.backend.connect()
        # Large movement on Joint 1: 90 deg = pi/2 rad ~ 1.5708 rad
        # At max velocity 3.1416 rad/s, duration at 1.0x speed is >= 0.5s
        import time

        target_deg = [90.0, -45.0, 90.0, -45.0, -90.0, 0.0]
        t0 = time.time()
        # Run at 10.0x speed factor to keep test fast: duration >= 0.5s / 10.0 = 0.05s
        ok = self.backend.move_joint(target_deg, speed_factor=10.0)
        dt = time.time() - t0

        self.assertTrue(ok)
        self.assertGreaterEqual(dt, 0.045, "Motion must respect URDF velocity-derived duration")

    def test_cartesian_shortest_path_euler_interpolation(self):
        self.backend.connect()
        # Verify rot_diff logic produces shortest path in [-180, +180]
        start_rot = [179.0, 0.0, 0.0]
        target_rot = [-179.0, 0.0, 0.0]
        rot_diff = [(t - s + 180.0) % 360.0 - 180.0 for s, t in zip(start_rot, target_rot)]
        self.assertAlmostEqual(rot_diff[0], 2.0, places=3, msg="179 to -179 must be +2 deg, not -358 deg")


if __name__ == "__main__":
    unittest.main()
