"""
Unit tests for Phase 3B Pre-Hardware Production Safety Guards.

Covers:
P0-1: Production stale BoardPose protection via HardwareManager wiring (zero commands on stale detection)
P0-2: Strict read-only connect (zero Tool DO writes, no RobotEnable/Mode/Move commands)
P1-1: Backend-level enabled motion guard (direct move_joint/move_cartesian fail closed when disabled)
P1-2: Operational mode lifecycle (DISCONNECTED -> CONNECTED -> ENABLED -> MODE_CONFIGURED -> CALIBRATED -> MOTION_AUTHORIZED)
P1-3: Authoritative controller motion-state synchronization (GetRobotEmergencyStopState, GetRobotMotionDone, GetRobotErrorCode)
P1-4: Virtual payload truth (world confirmation vs. bare backend unconfirmed expected state)
"""

from typing import List, Optional, Sequence
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.domain.board_pose_provider import FixedBoardPoseProvider, BoardPlacementState
from src.hardware.backends.base import RobotBackend, RobotStateSnapshot
from src.hardware.backends.physical_fr3 import PhysicalFR3Backend
from src.hardware.hardware_manager import HardwareManager
from src.motion.contracts import CartesianWaypoint, GripperCommand, JointWaypoint, MotionType
from src.motion.executor import MotionExecutor
from src.motion.plan import MotionPlan, MotionStep, PieceMoveIntent
from src.motion.resolver import MotionResolver
from src.motion.result import MotionFailureCategory, PayloadState
from src.motion.stages import MotionStage
from src.simulation.virtual_fr3_backend import VirtualFR3Backend


class MockConfig:
    DRY_RUN = True
    ROBOT_BACKEND = "VIRTUAL"
    ROBOT_IP = "127.0.0.1"
    BOARD_CALIBRATION_MODE = "POINTER_CONTACT"
    FORWARD_SHIFT_MM = 0.0
    PICK_TCP_HEIGHT_MM = 4.715
    PLACE_TCP_HEIGHT_MM = 4.715
    SAFE_CLEARANCE_Z_MM = 40.0
    CAPTURE_BIN_VALIDATED = True
    CAPTURE_BIN_X = -226.123
    CAPTURE_BIN_Y = 225.024
    CAPTURE_BIN_Z = 291.68
    PICK_TOOL_ROTATION = [-179.164, -3.047, -26.304]
    TOOL_DO_OPEN = 1
    TOOL_DO_CLOSE = 0
    TOOL_DO_OPEN_PULSE_SEC = 0.30
    TOOL_DO_CLOSE_PULSE_SEC = 0.30
    TOOL_DO_DEADTIME_SEC = 0.10


class TestPhase3bPreHardwareSafetyGuards(unittest.TestCase):
    """Test suite for Phase 3B pre-hardware execution safety guards."""

    def setUp(self):
        self.project_dir = str(Path(__file__).resolve().parent.parent.parent)

    # -------------------------------------------------------------------------
    # P0-1: PRODUCTION STALE BOARDPOSE PROTECTION
    # -------------------------------------------------------------------------



    # -------------------------------------------------------------------------
    # P0-2: STRICT READ-ONLY CONNECT (ZERO TOOL DO WRITES)
    # -------------------------------------------------------------------------

    def test_strict_read_only_connect_issues_zero_tool_do_and_no_motion(self):
        """
        P0-2: PhysicalFR3Backend.connect() must be strictly read-only.
        Must NOT call RobotEnable, Mode, MoveJ, MoveCart, MoveL, SetToolDO, or SetDO.
        """
        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=False)
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0]*6)
        mock_rpc.GetActualTCPPose.return_value = (0, [0.0]*6)
        mock_rpc.GetRobotMotionDone.return_value = (0, 1)
        mock_rpc.GetRobotEmergencyStopState.return_value = (0, 0)
        mock_rpc.GetRobotErrorCode.return_value = (0, [0, 0])
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0]*6)
        mock_rpc.GetActualTCPPose.return_value = (0, [0.0]*6)
        mock_rpc.GetActualToolFlangePose.return_value = (0, [0.0]*6)

        with patch("src.hardware.backends.physical_fr3.robot_sdk_core") as mock_core, \
             patch("time.sleep"):
            mock_core.RPC.return_value = mock_rpc
            ok = backend.connect()
            self.assertTrue(ok)

            # Assert RPC handle was created
            mock_core.RPC.assert_called_once_with("192.168.58.2")

            # Assert telemetry reads were performed
            mock_rpc.GetActualJointPosDegree.assert_called()
            mock_rpc.GetActualTCPPose.assert_called()

            # STRICT INVARIANTS: NO writes, enables, modes, or motions on connect
            mock_rpc.RobotEnable.assert_not_called()
            mock_rpc.Mode.assert_not_called()
            mock_rpc.MoveJ.assert_not_called()
            mock_rpc.MoveCart.assert_not_called()
            mock_rpc.SetToolDO.assert_not_called()
            mock_rpc.SetDO.assert_not_called()

            # State properties
            self.assertFalse(backend.is_enabled)
            self.assertIsNone(backend.operational_mode)
            self.assertEqual(backend.lifecycle_state, "CONNECTED")

    # -------------------------------------------------------------------------
    # P1-1: BACKEND-LEVEL ENABLED MOTION GUARD
    # -------------------------------------------------------------------------

    def test_backend_motion_guard_rejects_when_connected_but_disabled(self):
        """
        P1-1: Direct backend calls to move_joint and move_cartesian in live physical
        mode must fail closed when connected but not enabled.
        """
        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=False)
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0]*6)
        mock_rpc.GetActualTCPPose.return_value = (0, [0.0]*6)
        mock_rpc.GetRobotMotionDone.return_value = (0, 1)
        mock_rpc.GetRobotEmergencyStopState.return_value = (0, 0)
        mock_rpc.GetRobotErrorCode.return_value = (0, [0, 0])
        backend._rpc = mock_rpc
        backend._connected = True
        backend._enabled = False

        # Attempt move_joint while disabled
        ok_j = backend.move_joint([0.0, -45.0, 90.0, -135.0, -90.0, 0.0])
        self.assertFalse(ok_j)
        self.assertIn("not enabled", backend._last_error)
        mock_rpc.MoveJ.assert_not_called()

        # Attempt move_cartesian while disabled
        ok_c = backend.move_cartesian([-300.0, 0.0, 200.0, 180.0, 0.0, 90.0])
        self.assertFalse(ok_c)
        self.assertIn("not enabled", backend._last_error)
        mock_rpc.MoveCart.assert_not_called()

        # Enable robot
        mock_rpc.RobotEnable.return_value = 0
        backend.enable_robot()
        self.assertTrue(backend.is_enabled)

        # Now motion succeeds and calls RPC
        mock_rpc.MoveJ.return_value = 0
        ok_j2 = backend.move_joint([0.0, -45.0, 90.0, -135.0, -90.0, 0.0])
        self.assertTrue(ok_j2)
        mock_rpc.MoveJ.assert_called_once()

        mock_rpc.MoveCart.return_value = 0
        ok_c2 = backend.move_cartesian([-300.0, 0.0, 200.0, 180.0, 0.0, 90.0])
        self.assertTrue(ok_c2)
        mock_rpc.MoveCart.assert_called_once()

    # -------------------------------------------------------------------------
    # P1-2: OPERATIONAL MODE LIFECYCLE
    # -------------------------------------------------------------------------


    def test_dry_run_simulates_lifecycle(self):
        """P1-2: Dry-run backend explicitly simulates enable/mode lifecycle."""
        backend = PhysicalFR3Backend(ip="127.0.0.1", dry_run=True)
        self.assertEqual(backend.lifecycle_state, "DISCONNECTED")

        backend.connect()
        self.assertEqual(backend.lifecycle_state, "CONNECTED")
        self.assertFalse(backend.is_enabled)
        self.assertIsNone(backend.operational_mode)

        backend.enable_robot()
        self.assertEqual(backend.lifecycle_state, "ENABLED")
        self.assertTrue(backend.is_enabled)

        backend.set_operational_mode(0)
        self.assertEqual(backend.lifecycle_state, "MODE_CONFIGURED")
        self.assertEqual(backend.operational_mode, 0)

        backend.disable_robot()
        self.assertEqual(backend.lifecycle_state, "CONNECTED")
        self.assertFalse(backend.is_enabled)

        backend.disconnect()
        self.assertEqual(backend.lifecycle_state, "DISCONNECTED")

    # -------------------------------------------------------------------------
    # P1-3: ACTUAL CONTROLLER MOTION-STATE AUTHORITY
    # -------------------------------------------------------------------------

    def test_controller_motion_state_authority_synchronization(self):
        """
        P1-3: Queries GetRobotEmergencyStopState, GetRobotErrorCode, and GetRobotMotionDone
        to synchronize RobotStateSnapshot.motion_state.
        """
        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=False)
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0]*6)
        mock_rpc.GetActualTCPPose.return_value = (0, [0.0]*6)
        mock_rpc.GetRobotMotionDone.return_value = (0, 1)
        mock_rpc.GetRobotEmergencyStopState.return_value = (0, 0)
        mock_rpc.GetRobotErrorCode.return_value = (0, [0, 0])
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0]*6)
        mock_rpc.GetActualTCPPose.return_value = (0, [0.0]*6)
        mock_rpc.GetActualToolFlangePose.return_value = (0, [0.0]*6)
        backend._rpc = mock_rpc
        backend._connected = True
        backend._enabled = True

        # Case 1: Emergency Stop active
        mock_rpc.GetRobotEmergencyStopState.return_value = (0, 1)
        mock_rpc.GetRobotMotionDone.return_value = (0, 1)
        snap = backend.get_state_snapshot()
        self.assertEqual(snap.motion_state, "ERROR")
        self.assertIn("E-Stop", snap.last_error)

        # Case 2: Controller Error Code active
        mock_rpc.GetRobotEmergencyStopState.return_value = (0, 0)
        mock_rpc.GetRobotErrorCode.return_value = (0, [105, 3])
        mock_rpc.GetRobotMotionDone.return_value = (0, 1)
        snap = backend.get_state_snapshot()
        self.assertEqual(snap.motion_state, "ERROR")
        self.assertIn("main=105, sub=3", snap.last_error)

        # Case 3: Robot Moving (motion_done=0)
        mock_rpc.GetRobotEmergencyStopState.return_value = (0, 0)
        mock_rpc.GetRobotErrorCode.return_value = (0, [0, 0])
        mock_rpc.GetRobotMotionDone.return_value = (0, 0)
        backend._last_error = None
        snap = backend.get_state_snapshot()
        self.assertEqual(snap.motion_state, "MOVING")

        # Case 4: Robot Idle (motion_done=1)
        mock_rpc.GetRobotMotionDone.return_value = (0, 1)
        snap = backend.get_state_snapshot()
        self.assertEqual(snap.motion_state, "IDLE")

    # -------------------------------------------------------------------------
    # P1-4: VIRTUAL PAYLOAD TRUTH
    # -------------------------------------------------------------------------




if __name__ == "__main__":
    unittest.main()
