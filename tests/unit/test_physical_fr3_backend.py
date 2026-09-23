"""
Unit tests for PhysicalFR3Backend.
Verifies interface compliance, dry-run state transitions, and mock RPC call contracts.
"""

import unittest
from unittest.mock import MagicMock

from src.hardware.backends.base import RobotBackend, RobotStateSnapshot
from src.hardware.backends.physical_fr3 import PhysicalFR3Backend


class PhysicalFR3BackendTests(unittest.TestCase):

    def test_implements_robot_backend_interface(self):
        backend = PhysicalFR3Backend(dry_run=True)
        self.assertIsInstance(backend, RobotBackend)

    def test_dry_run_connection_and_state_snapshot(self):
        backend = PhysicalFR3Backend(dry_run=True)
        self.assertFalse(backend.is_connected())
        
        # Connect in dry run
        ok = backend.connect()
        self.assertTrue(ok)
        self.assertTrue(backend.is_connected())

        snap = backend.get_state_snapshot()
        self.assertIsInstance(snap, RobotStateSnapshot)
        self.assertEqual(snap.robot_model, "FR3")
        self.assertTrue(snap.connected)
        self.assertEqual(snap.motion_state, "IDLE")
        self.assertEqual(len(snap.joints_deg), 6)
        self.assertEqual(len(snap.tcp_pose_mm_deg), 6)

        # Disconnect
        backend.disconnect()
        self.assertFalse(backend.is_connected())

    def test_dry_run_motion_and_gripper(self):
        backend = PhysicalFR3Backend(dry_run=True)
        backend.connect()

        # Move joint
        target_q = [10.0, -30.0, 60.0, -120.0, -90.0, 15.0]
        ok = backend.move_joint(target_q)
        self.assertTrue(ok)
        snap = backend.get_state_snapshot()
        self.assertEqual(snap.joints_deg, target_q)

        # Invalid joint length raises ValueError
        with self.assertRaises(ValueError):
            backend.move_joint([1.0, 2.0, 3.0])

        # Move cartesian
        target_tcp = [-350.0, 50.0, 180.0, 180.0, 0.0, 90.0]
        ok = backend.move_cartesian(target_tcp)
        self.assertTrue(ok)
        snap = backend.get_state_snapshot()
        self.assertEqual(snap.tcp_pose_mm_deg, target_tcp)

        with self.assertRaises(ValueError):
            backend.move_cartesian([1.0, 2.0])

        # Gripper
        self.assertTrue(backend.set_gripper(closed=True))
        self.assertTrue(backend.get_state_snapshot().gripper_closed)
        self.assertTrue(backend.set_gripper(closed=False))
        self.assertFalse(backend.get_state_snapshot().gripper_closed)

        # Stop
        self.assertTrue(backend.stop())

    def test_mock_rpc_controller_calls(self):
        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=False)
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.RobotEnable.return_value = 0
        mock_rpc.Mode.return_value = 0
        mock_rpc.MoveJ.return_value = 0
        mock_rpc.MoveCart.return_value = 0
        mock_rpc.SetToolDO.return_value = 0
        mock_rpc.StopMotion.return_value = 0
        mock_rpc.GetActualJointPosDegree.return_value = (0, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        mock_rpc.GetActualTCPPose.return_value = (0, [100.0, 200.0, 300.0, 180.0, 0.0, 90.0])

        backend._rpc = mock_rpc
        backend._connected = True
        backend._enabled = True
        backend._motion_state = "IDLE"

        # MoveJ invokes mock RPC
        backend.move_joint([0.0, -45.0, 90.0, -135.0, -90.0, 0.0], speed_factor=0.4)
        mock_rpc.MoveJ.assert_called_once()
        self.assertEqual(mock_rpc.MoveJ.call_args[1]["vel"], 40.0)

        # MoveCart invokes mock RPC
        backend.move_cartesian([-300.0, 0.0, 200.0, 180.0, 0.0, 90.0])
        mock_rpc.MoveCart.assert_called_once()

        # Gripper calls SetToolDO
        backend.set_gripper(closed=True)
        self.assertTrue(mock_rpc.SetToolDO.called)

        # Stop calls StopMotion
        backend.stop()
        mock_rpc.StopMotion.assert_called_once()

    def test_direct_backend_motion_rejected_when_connected_but_disabled(self):
        """P1-1: Live backend must reject move_joint and move_cartesian when enabled=False."""
        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=False)
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        backend._rpc = mock_rpc
        backend._connected = True
        backend._enabled = False

        # Attempt move_joint while connected-but-disabled
        ok_j = backend.move_joint([0.0, -45.0, 90.0, -135.0, -90.0, 0.0])
        self.assertFalse(ok_j)
        self.assertIn("not enabled", backend._last_error)
        mock_rpc.MoveJ.assert_not_called()

        # Attempt move_cartesian while connected-but-disabled
        ok_c = backend.move_cartesian([-300.0, 0.0, 200.0, 180.0, 0.0, 90.0])
        self.assertFalse(ok_c)
        self.assertIn("not enabled", backend._last_error)
        mock_rpc.MoveCart.assert_not_called()

    def test_read_only_connect_issues_zero_tool_do_and_no_motion(self):
        """P0-2: Live physical connect must be strictly read-only."""
        from unittest.mock import patch
        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=False)
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0]*6)
        mock_rpc.GetActualTCPPose.return_value = (0, [0.0]*6)
        mock_rpc.GetActualToolFlangePose.return_value = (0, [0.0]*6)

        with patch("src.hardware.backends.physical_fr3.robot_sdk_core") as mock_core, \
             patch("time.sleep"):
            mock_core.RPC.return_value = mock_rpc
            ok = backend.connect()
            self.assertTrue(ok)

            # RPC constructed and telemetry queries allowed
            mock_core.RPC.assert_called_once_with("192.168.58.2")
            mock_rpc.GetActualJointPosDegree.assert_called()
            mock_rpc.GetActualTCPPose.assert_called()

            # Zero commands allowed during read-only connect
            mock_rpc.RobotEnable.assert_not_called()
            mock_rpc.Mode.assert_not_called()
            mock_rpc.MoveJ.assert_not_called()
            mock_rpc.MoveCart.assert_not_called()
            mock_rpc.SetToolDO.assert_not_called()

    def test_controller_motion_state_authority_synchronization(self):
        """P1-3: FAIRINO SDK controller queries synchronize RobotStateSnapshot.motion_state."""
        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=False)
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0]*6)
        mock_rpc.GetActualTCPPose.return_value = (0, [0.0]*6)
        mock_rpc.GetActualToolFlangePose.return_value = (0, [0.0]*6)
        backend._rpc = mock_rpc
        backend._connected = True
        backend._enabled = True

        # 1. E-Stop Active -> motion_state must become ERROR
        mock_rpc.GetRobotEmergencyStopState.return_value = (0, 1)
        mock_rpc.GetRobotMotionDone.return_value = (0, 1)
        snap = backend.get_state_snapshot()
        self.assertEqual(snap.motion_state, "ERROR")
        self.assertIn("E-Stop", snap.last_error)

        # 2. Normal (No E-stop), Motion in progress (motion_done=0) -> MOVING
        mock_rpc.GetRobotEmergencyStopState.return_value = (0, 0)
        mock_rpc.GetRobotErrorCode.return_value = (0, [0, 0])
        mock_rpc.GetRobotMotionDone.return_value = (0, 0)
        backend._last_error = None
        snap = backend.get_state_snapshot()
        self.assertEqual(snap.motion_state, "MOVING")

        # 3. Motion completed (motion_done=1) -> IDLE
        mock_rpc.GetRobotMotionDone.return_value = (0, 1)
        snap = backend.get_state_snapshot()
        self.assertEqual(snap.motion_state, "IDLE")


if __name__ == "__main__":
    unittest.main()
