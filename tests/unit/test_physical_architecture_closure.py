"""
Unit tests for Phase 1 Physical Architecture Closure.

Covers:
1. Gripper RPC Binding & Timing/Invariants (P0)
2. Safe Idle on Connect, Error, and Cleanup
3. MoveCart Return Codes & Elimination of 112 / 'MoveCart' error workaround (P0)
4. GameState Non-Commit on Motion Failure
5. Fail-Closed Board Calibration Mode
6. 218 mm Stale Residual Regression Test
"""

import unittest
from unittest.mock import MagicMock, patch, call
import time
import pytest

from src.hardware.gripper.two_output import TwoOutputGripperDriver, GripperSafetyError
from src.hardware.backends.physical_fr3 import PhysicalFR3Backend, is_motion_success_code
from src.hardware.hardware_manager import HardwareManager
from src.motion.coordinator import MotionCoordinator, MotionProfile
from src.domain.board_pose_provider import FixedBoardPoseProvider
from src.domain.geometry import get_canonical_tool_geometry, ProvenanceStatus


class TestGripperRPCBindingAndInvariants(unittest.TestCase):
    """Requirement 41: Gripper RPC binding, mutual exclusion, deadtime, and safe idle."""

    def test_gripper_open_and_close_sequence(self):
        """
        Verify OPEN: DO0 LOW, DO1 LOW, deadtime, DO1 HIGH, pulse, DO1 LOW, DO0 LOW.
        Verify CLOSE: DO0 LOW, DO1 LOW, deadtime, DO0 HIGH, pulse, DO0 LOW, DO1 LOW.
        """
        do_events = []

        def mock_set_do(do_id: int, status: int) -> int:
            do_events.append((do_id, status))
            return 0

        driver = TwoOutputGripperDriver(
            set_do_fn=mock_set_do,
            open_do_id=1,
            close_do_id=0,
            open_pulse_sec=0.01,
            close_pulse_sec=0.01,
            open_settle_sec=0.01,
            close_settle_sec=0.01,
            deadtime_sec=0.01,
            dry_run=False,
        )
        # Init sets safe idle: DO1=0, DO0=0
        self.assertEqual(do_events[:2], [(1, 0), (0, 0)])
        do_events.clear()

        # Execute OPEN
        driver.open()
        # Expected OPEN sequence: safe_idle (1=0, 0=0) -> DO1=1 -> safe_idle (1=0, 0=0)
        expected_open = [(1, 0), (0, 0), (1, 1), (1, 0), (0, 0)]
        self.assertEqual(do_events, expected_open)
        do_events.clear()

        # Execute CLOSE
        driver.close()
        # Expected CLOSE sequence: safe_idle (1=0, 0=0) -> DO0=1 -> safe_idle (1=0, 0=0)
        expected_close = [(1, 0), (0, 0), (0, 1), (1, 0), (0, 0)]
        self.assertEqual(do_events, expected_close)

    def test_mutual_exclusion_invariant(self):
        """DO0 and DO1 must never be active simultaneously."""
        driver = TwoOutputGripperDriver(
            set_do_fn=lambda do_id, st: 0,
            open_do_id=1,
            close_do_id=0,
            dry_run=False,
        )
        # Manually force DO0 active in tracking set
        driver._active_outputs.add(0)
        # Attempting to activate DO1 must raise GripperSafetyError
        with self.assertRaises(GripperSafetyError) as ctx:
            driver._set_output(1, 1)
        self.assertIn("already active", str(ctx.exception))

    def test_exception_in_set_do_triggers_safe_idle(self):
        """SetToolDO exception triggers safe idle and failure propagation."""
        call_count = 0

        def failing_set_do(do_id: int, status: int) -> int:
            nonlocal call_count
            call_count += 1
            if status == 1:
                raise RuntimeError("Hardware communication fault on SetToolDO")
            return 0

        driver = TwoOutputGripperDriver(
            set_do_fn=failing_set_do,
            open_pulse_sec=0.01,
            deadtime_sec=0.01,
            dry_run=False,
        )
        with self.assertRaises(GripperSafetyError):
            driver.open()

        # Verify driver is in safe idle (no active outputs)
        self.assertEqual(len(driver._active_outputs), 0)

    def test_physical_application_dry_run_keeps_sdk_unbound(self):
        from types import SimpleNamespace
        cfg=SimpleNamespace(ROBOT_BACKEND="PHYSICAL",DRY_RUN=True)
        hm=HardwareManager(cfg,".")
        with patch.object(hm.robot,"connect") as connect:
            hm._init_robot()
        connect.assert_not_called()
        self.assertIsNone(hm.backend)
        self.assertIsNone(hm.robot.robot)
        self.assertFalse(hm.is_robot_ready)

    def test_cleanup_read_only_connection_never_commands_gripper_or_enable(self):
        from types import SimpleNamespace
        cfg=SimpleNamespace(ROBOT_BACKEND="PHYSICAL",DRY_RUN=False)
        hm=HardwareManager(cfg,".")
        hm.robot=MagicMock(connected=True,physical_motion_authorized=False)
        hm.cleanup()
        hm.robot._set_gripper_safe_idle.assert_not_called()
        hm.robot.robot.RobotEnable.assert_not_called()

    def test_cleanup_commissioned_connection_forces_outputs_low_and_disables(self):
        from types import SimpleNamespace
        cfg=SimpleNamespace(ROBOT_BACKEND="PHYSICAL",DRY_RUN=False)
        hm=HardwareManager(cfg,".")
        from src.hardware.robot_VIP import FR5Robot
        hm.robot=FR5Robot()
        hm.robot.connected=True
        hm.robot.dry=False
        hm.robot.physical_motion_authorized=True
        hm.robot.robot=MagicMock()
        hm.robot.robot.RobotEnable.return_value=0
        hm.robot._set_gripper_safe_idle=MagicMock()
        hm.cleanup()
        hm.robot._set_gripper_safe_idle.assert_called_once()
        hm.robot.robot.RobotEnable.assert_called_once_with(0)


class TestMoveCartReturnCodesAndSafety(unittest.TestCase):
    """Requirements 16, 17, 42: SDK return codes and removal of MoveCart workaround."""

    def test_is_motion_success_code_contract(self):
        """Only return code 0 indicates success. 112 and other codes must fail."""
        self.assertTrue(is_motion_success_code(0))
        self.assertFalse(is_motion_success_code(112))
        self.assertFalse(is_motion_success_code(-1))
        self.assertFalse(is_motion_success_code(14))
        self.assertFalse(is_motion_success_code(101))

    def test_move_cartesian_fails_on_code_112(self):
        """FAIRINO MoveCart returning 112 (singularity) must return False and not succeed."""
        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=False)
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.RobotEnable.return_value = 0
        mock_rpc.Mode.return_value = 0
        mock_rpc.MoveCart.return_value = 112  # Singularity/error code
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0]*6)
        mock_rpc.GetActualTCPPose.return_value = (0, [0.0]*6)

        backend._rpc = mock_rpc
        backend._connected = True
        backend._enabled = True

        ok = backend.move_cartesian([100.0, 200.0, 300.0, 180.0, 0.0, 90.0])
        self.assertFalse(ok)
        self.assertEqual(backend._motion_state, "ERROR")
        self.assertIn("112", backend._last_error)

    def test_move_piece_failure_propagates_to_motion_coordinator(self):
        """When backend MoveCart fails, MotionCoordinator.pick/execute_move returns False."""
        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=False)
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.RobotEnable.return_value = 0
        mock_rpc.Mode.return_value = 0
        mock_rpc.SetToolDO.return_value = 0
        mock_rpc.MoveCart.return_value = -1  # Kinematic error
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0]*6)
        mock_rpc.GetActualTCPPose.return_value = (0, [0.0]*6)

        backend._rpc = mock_rpc
        backend._connected = True
        backend._enabled = True

        coordinator = MotionCoordinator(
            backend=backend,
            board_pose_provider=FixedBoardPoseProvider(),
        )
        ok = coordinator.pick(row=0, col=0)
        self.assertFalse(ok)


class TestGameStateCommitRule(unittest.TestCase):
    def test_real_execution_entrypoint_failure_does_not_commit(self):
        from types import SimpleNamespace
        from src.core.ai_execution import execute_ai_move
        from src.core.game_state import GameState
        from src.motion.result import MotionExecutionResult,MotionFailureCategory
        from src.motion.stages import MotionStage
        state=GameState()
        state.api_client.send_move_update_board=MagicMock()
        state.process_human_move((0,6),(0,5),"r_P")
        before=[row[:] for row in state.board];before_fen=state.current_fen
        hw=SimpleNamespace(is_robot_ready=True,simulation_runtime=object(),
            execute_piece_move=MagicMock(return_value=MotionExecutionResult.fail(
                MotionStage.LAND,MotionFailureCategory.MOTION_COMMAND_FAILED,"112")))
        self.assertFalse(execute_ai_move(state,hw,((0,3),(0,4))))
        self.assertEqual(before,state.board)
        self.assertEqual(before_fen,state.current_fen)
        self.assertTrue(state.physical_sync_fault)


class TestFailClosedCalibrationMode(unittest.TestCase):
    """Requirement 3: Physical calibration mode must fail-closed."""

    def test_unconfigured_calibration_mode_denies_motion(self):
        """When BOARD_CALIBRATION_MODE is None, physical motion must be denied."""
        class UnconfiguredConfig:
            ROBOT_BACKEND = "PHYSICAL"
            ROBOT_IP = "192.168.58.2"
            DRY_RUN = True
            BOARD_CALIBRATION_MODE = None

        hm = HardwareManager(UnconfiguredConfig(), ".")
        with patch.object(hm.robot,"connect") as connect:
            hm._init_robot()
        self.assertFalse(hm.robot.physical_motion_authorized)
        self.assertFalse(hm.is_robot_ready)
        connect.assert_not_called()
        self.assertFalse(hm.execute_piece_move(0,0,0,1,False).success)


class TestCanonicalTool218mmResidual(unittest.TestCase):
    """Requirement 12, 44: Verify removal of stale 218mm runtime assumptions."""

    def test_canonical_tool_matches_active_1683mm_profile(self):
        """Canonical active profile declares the measured 168.3mm direct-mount tool."""
        tool = get_canonical_tool_geometry()
        self.assertAlmostEqual(tool.flange_to_tcp_distance_mm, 168.3, places=3)
        self.assertEqual(tool.status, ProvenanceStatus.MEASURED_PHYSICAL)

    def test_backend_dry_flange_pose_derived_from_canonical_tool(self):
        """Dry mock flange uses the current canonical tool, never stale 150/218mm offsets."""
        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=True)
        snap = backend.get_state_snapshot()
        self.assertAlmostEqual(snap.tcp_pose_mm_deg[2], 200.0)
        self.assertAlmostEqual(snap.flange_pose_mm_deg[2], 200.0 + get_canonical_tool_geometry().flange_to_tcp_distance_mm)
        # Difference must follow active geometry, not the historical 218mm assumption.
        self.assertAlmostEqual(snap.flange_pose_mm_deg[2] - snap.tcp_pose_mm_deg[2], get_canonical_tool_geometry().flange_to_tcp_distance_mm)


if __name__ == "__main__":
    unittest.main()
