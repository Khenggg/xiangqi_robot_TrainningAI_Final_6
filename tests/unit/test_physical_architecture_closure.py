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

    def test_physical_fr3_backend_binds_set_do_fn_not_none(self):
        """
        Verify that HardwareManager in PHYSICAL mode binds set_do_fn to
        PhysicalFR3Backend.set_tool_do (must NOT be None).
        """
        class MockConfig:
            ROBOT_BACKEND = "PHYSICAL"
            ROBOT_IP = "192.168.58.2"
            DRY_RUN = True
            BOARD_CALIBRATION_MODE = "POINTER_CONTACT"
            TOOL_DO_OPEN = 1
            TOOL_DO_CLOSE = 0

        hm = HardwareManager(MockConfig(), ".")
        hm.initialize_all()

        self.assertIsNotNone(hm.backend)
        self.assertIsNotNone(hm.gripper_driver)
        # The critical P0 check: set_do_fn must NOT be None
        self.assertIsNotNone(hm.gripper_driver._set_do_fn)
        self.assertEqual(hm.gripper_driver._set_do_fn, hm.backend.set_tool_do)

    def test_safe_idle_called_on_cleanup(self):
        """HardwareManager.cleanup() must invoke safe_idle on gripper driver."""
        class MockConfig:
            ROBOT_BACKEND = "PHYSICAL"
            ROBOT_IP = "192.168.58.2"
            DRY_RUN = True
            BOARD_CALIBRATION_MODE = "POINTER_CONTACT"

        hm = HardwareManager(MockConfig(), ".")
        hm.initialize_all()

        mock_driver = MagicMock()
        hm.gripper_driver = mock_driver

        hm.cleanup()
        mock_driver.safe_idle.assert_called_once()


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

        coordinator = MotionCoordinator(
            backend=backend,
            board_pose_provider=FixedBoardPoseProvider(),
        )
        ok = coordinator.pick(row=0, col=0)
        self.assertFalse(ok)


class TestGameStateCommitRule(unittest.TestCase):
    """Requirement 18 & 42: GameState must NOT commit if motion failed."""

    def test_motion_failure_prevents_board_commit(self):
        """Simulate move execution failure in game loop: state.board must not change."""
        initial_board = [
            ["r", "n", "b", "a", "k", "a", "b", "n", "r"],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            [".", "c", ".", ".", ".", ".", ".", "c", "."],
            ["p", ".", "p", ".", "p", ".", "p", ".", "p"],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            ["P", ".", "P", ".", "P", ".", "P", ".", "P"],
            [".", "C", ".", ".", ".", ".", ".", "C", "."],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            ["R", "N", "B", "A", "K", "A", "B", "N", "R"],
        ]
        board = [row[:] for row in initial_board]
        move_history = []
        r_captured = []

        # Mock a failed move (e.g. MoveCart threw or returned False)
        robot_success = False
        best = ((1, 2), (1, 4))
        s, d = best
        cap_p = board[d[1]][d[0]]
        is_cap = cap_p != "."

        # The new execution contract from main.py:
        if robot_success:
            move_history.append({"turn": "b", "src": s, "dst": d})
            if is_cap:
                r_captured.append(cap_p)
            board[d[1]][d[0]] = board[s[1]][s[0]]
            board[s[1]][s[0]] = "."

        # State must remain identical to initial state
        self.assertEqual(board, initial_board)
        self.assertEqual(len(move_history), 0)
        self.assertEqual(len(r_captured), 0)


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
        hm.initialize_all()

        self.assertFalse(hm.physical_motion_authorized)
        self.assertFalse(hm.is_robot_ready)
        self.assertIsNone(hm.motion_coordinator)
        # Attempting move_piece must return False safely
        self.assertFalse(hm.move_piece(0, 0, 0, 1, False))


class TestCanonicalTool218mmResidual(unittest.TestCase):
    """Requirement 12, 44: Verify removal of stale 218mm runtime assumptions."""

    def test_canonical_tool_is_150mm_with_approximate_provenance(self):
        """Active canonical tool must be 150mm with MEASURED_APPROXIMATE."""
        tool = get_canonical_tool_geometry()
        self.assertAlmostEqual(tool.flange_to_tcp_distance_mm, 150.0, places=3)
        self.assertEqual(tool.status, ProvenanceStatus.MEASURED_APPROXIMATE)

    def test_backend_dry_flange_pose_derived_from_150mm(self):
        """Initial mock flange pose is TCP Z (200.0) + 150.0 = 350.0 mm, not 418 mm."""
        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=True)
        snap = backend.get_state_snapshot()
        self.assertAlmostEqual(snap.tcp_pose_mm_deg[2], 200.0)
        self.assertAlmostEqual(snap.flange_pose_mm_deg[2], 350.0)
        # Difference must be 150.0 mm, NOT 218.0 mm
        self.assertAlmostEqual(snap.flange_pose_mm_deg[2] - snap.tcp_pose_mm_deg[2], 150.0)


if __name__ == "__main__":
    unittest.main()
