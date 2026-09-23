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

    def test_production_stale_board_pose_protection_virtual_composition(self):
        """
        P0-1: In production Virtual HardwareManager wiring, when BoardPoseProvider
        placement_version increments from N to N+1, MotionExecutor must abort with
        STALE_PLACEMENT_VERSION and issue ZERO motion or gripper commands.
        """
        cfg = MockConfig()
        cfg.ROBOT_BACKEND = "VIRTUAL"
        cfg.DRY_RUN = True

        hw = HardwareManager(cfg, self.project_dir)
        hw._init_robot()

        self.assertIsNotNone(hw.board_pose_provider)
        self.assertIsNotNone(hw.motion_executor)
        self.assertIsNotNone(hw.motion_resolver)
        self.assertIs(hw.motion_executor.board_pose_provider, hw.board_pose_provider)

        # 1. Resolve a plan using current BoardPose version (version 1)
        intent = PieceMoveIntent(src_row=2, src_col=1, dst_row=3, dst_col=1)
        plan = hw.motion_resolver.resolve_move(intent)
        self.assertEqual(plan.placement_version, 1)

        # 2. Simulate authoritative BoardPose update to version 2
        new_state = BoardPlacementState(
            placement_version=2,
            forward_shift_mm=10.0,
        )
        hw.board_pose_provider.set_board_placement_state(new_state)
        self.assertEqual(hw.board_pose_provider.get_board_placement_state().placement_version, 2)

        # 3. Intercept backend motion commands to verify ZERO execution
        move_cart_calls = []
        move_joint_calls = []
        set_gripper_calls = []

        orig_mc = hw.backend.move_cartesian
        orig_mj = hw.backend.move_joint
        orig_sg = hw.backend.set_gripper

        def spy_move_cart(*args, **kwargs):
            move_cart_calls.append(args)
            return orig_mc(*args, **kwargs)

        def spy_move_joint(*args, **kwargs):
            move_joint_calls.append(args)
            return orig_mj(*args, **kwargs)

        def spy_set_gripper(*args, **kwargs):
            set_gripper_calls.append(args)
            return orig_sg(*args, **kwargs)

        hw.backend.move_cartesian = spy_move_cart
        hw.backend.move_joint = spy_move_joint
        hw.backend.set_gripper = spy_set_gripper

        # 4. Attempt to execute the stale plan through the production motion_executor
        result = hw.motion_executor.execute_plan(plan)

        # 5. Assert STALE_PLACEMENT_VERSION failure and ZERO issued commands
        self.assertFalse(result.success)
        self.assertEqual(result.failure_category, MotionFailureCategory.STALE_PLACEMENT_VERSION)
        self.assertIn("does not match current BoardPlacement version=2", result.message)

        self.assertEqual(len(move_cart_calls), 0, "MoveCart must NOT be called on stale placement!")
        self.assertEqual(len(move_joint_calls), 0, "MoveJ must NOT be called on stale placement!")
        self.assertEqual(len(set_gripper_calls), 0, "Gripper commands must NOT be called on stale placement!")

        hw.cleanup()

    def test_production_stale_board_pose_protection_physical_composition(self):
        """
        P0-1: In production Physical HardwareManager wiring, when BoardPoseProvider
        placement_version increments from N to N+1, MotionExecutor must abort with
        STALE_PLACEMENT_VERSION and issue ZERO MoveCart, MoveJ, or SetToolDO calls.
        """
        cfg = MockConfig()
        cfg.ROBOT_BACKEND = "PHYSICAL"
        cfg.DRY_RUN = True

        hw = HardwareManager(cfg, self.project_dir)
        hw._init_robot()

        self.assertIsNotNone(hw.board_pose_provider)
        self.assertIsNotNone(hw.motion_executor)
        self.assertIsNotNone(hw.motion_resolver)
        self.assertIs(hw.motion_executor.board_pose_provider, hw.board_pose_provider)

        # 1. Resolve a plan using current version
        initial_version = hw.board_pose_provider.get_board_placement_state().placement_version
        intent = PieceMoveIntent(src_row=0, src_col=0, dst_row=1, dst_col=0)
        plan = hw.motion_resolver.resolve_move(intent)
        self.assertEqual(plan.placement_version, initial_version)

        # 2. Bump placement version to N+1
        new_state = BoardPlacementState(
            placement_version=initial_version + 1,
            forward_shift_mm=10.0,
        )
        hw.board_pose_provider.set_board_placement_state(new_state)

        # 3. Intercept backend calls
        move_cart_calls = []
        move_joint_calls = []
        set_gripper_calls = []

        orig_mc = hw.backend.move_cartesian
        orig_mj = hw.backend.move_joint
        orig_sg = hw.backend.set_gripper

        def spy_move_cart(*args, **kwargs):
            move_cart_calls.append(args)
            return orig_mc(*args, **kwargs)

        def spy_move_joint(*args, **kwargs):
            move_joint_calls.append(args)
            return orig_mj(*args, **kwargs)

        def spy_set_gripper(*args, **kwargs):
            set_gripper_calls.append(args)
            return orig_sg(*args, **kwargs)

        hw.backend.move_cartesian = spy_move_cart
        hw.backend.move_joint = spy_move_joint
        hw.backend.set_gripper = spy_set_gripper

        # 4. Execute stale plan
        result = hw.motion_executor.execute_plan(plan)

        # 5. Assert STALE_PLACEMENT_VERSION failure and ZERO issued commands
        self.assertFalse(result.success)
        self.assertEqual(result.failure_category, MotionFailureCategory.STALE_PLACEMENT_VERSION)
        self.assertEqual(len(move_cart_calls), 0)
        self.assertEqual(len(move_joint_calls), 0)
        self.assertEqual(len(set_gripper_calls), 0)

        hw.cleanup()

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

    def test_operational_mode_lifecycle_physical_mode(self):
        """
        P1-2: In live PHYSICAL mode, is_robot_ready requires explicit operational mode.
        Lifecycle:
          DISCONNECTED -> CONNECTED -> ENABLED -> MODE_CONFIGURED -> CALIBRATED -> MOTION_AUTHORIZED
        """
        cfg = MockConfig()
        cfg.DRY_RUN = False
        cfg.ROBOT_BACKEND = "PHYSICAL"

        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.RobotEnable.return_value = 0
        mock_rpc.Mode.return_value = 0
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0]*6)
        mock_rpc.GetActualTCPPose.return_value = (0, [0.0]*6)
        mock_rpc.GetActualToolFlangePose.return_value = (0, [0.0]*6)

        with patch("src.hardware.backends.physical_fr3.robot_sdk_core") as mock_core, \
             patch("src.hardware.hardware_manager.PhysicalTeachingPointBoardPoseProvider") as mock_cal_provider, \
             patch("time.sleep"):

            mock_core.RPC.return_value = mock_rpc

            mock_provider_inst = MagicMock()
            mock_provider_inst.is_calibrated = True
            mock_provider_inst.calibration_result.success = True
            mock_provider_inst.calibration_result.warnings = []
            mock_provider_inst.calibration_result.calibration_log = "OK"
            mock_provider_inst.get_board_placement_state.return_value.cell_to_robot_xyz.return_value = [0.2, -0.1, 0.0]
            mock_cal_provider.from_controller.return_value = mock_provider_inst

            hw = HardwareManager(cfg, self.project_dir)
            self.assertEqual(hw.lifecycle_state, "DISCONNECTED")
            self.assertFalse(hw.is_robot_ready)

            hw._init_robot()

            # Connected and calibrated, but NOT enabled
            self.assertTrue(hw.backend.is_connected())
            self.assertFalse(hw.backend.is_enabled)
            self.assertEqual(hw.lifecycle_state, "CONNECTED")
            self.assertFalse(hw.is_robot_ready)

            # Explicitly enable robot: enabled=True, but mode unknown (None)
            hw.enable_robot()
            self.assertTrue(hw.backend.is_enabled)
            self.assertIsNone(hw.backend.operational_mode)
            self.assertEqual(hw.lifecycle_state, "ENABLED")
            self.assertFalse(hw.is_robot_ready)

            # Explicitly configure operational mode: mode=0
            hw.set_operational_mode(0)
            self.assertEqual(hw.backend.operational_mode, 0)
            self.assertEqual(hw.lifecycle_state, "MOTION_AUTHORIZED")
            self.assertTrue(hw.is_robot_ready)

            # Disable robot -> readiness turns False again
            hw.disable_robot()
            self.assertFalse(hw.backend.is_enabled)
            self.assertEqual(hw.lifecycle_state, "CONNECTED")
            self.assertFalse(hw.is_robot_ready)

            hw.cleanup()

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

    def test_virtual_payload_verifier_with_world_confirms_attachment(self):
        """
        P1-4: When VirtualXiangqiSimulation.world is available, piece presence
        independently verifies ATTACHED and RELEASED.
        """
        cfg = MockConfig()
        cfg.ROBOT_BACKEND = "VIRTUAL"

        hw = HardwareManager(cfg, self.project_dir)

        # Mock simulation runtime with world
        mock_world = MagicMock()
        mock_sim = MagicMock()
        mock_sim.world = mock_world
        hw.simulation_runtime = mock_sim
        hw._init_robot()

        self.assertIsNotNone(hw.motion_executor.payload_verifier)

        # Simulate gripper CLOSE step with piece present in world
        mock_world.get_attached_piece.return_value = "P"  # Piece is attached
        step_close = MotionStep(
            step_id=3,
            stage=MotionStage.GRIP,
            motion_type=MotionType.GRIPPER,
            gripper_command=GripperCommand.CLOSE,
        )
        res = hw.motion_executor._execute_step(step_close, last_completed_stage=MotionStage.LAND)
        self.assertTrue(res.success)
        self.assertEqual(hw.motion_executor.payload_state, PayloadState.ATTACHED)

        # Simulate gripper OPEN step with piece released in world
        mock_world.get_attached_piece.return_value = None  # Piece released
        step_open = MotionStep(
            step_id=6,
            stage=MotionStage.RELEASE,
            motion_type=MotionType.GRIPPER,
            gripper_command=GripperCommand.OPEN,
        )
        res_open = hw.motion_executor._execute_step(step_open, last_completed_stage=MotionStage.PLACE_LAND)
        self.assertTrue(res_open.success)
        self.assertEqual(hw.motion_executor.payload_state, PayloadState.RELEASED)

        hw.cleanup()

    def test_bare_virtual_backend_retains_unconfirmed_expected_payload_state(self):
        """
        P1-4: When using bare VirtualFR3Backend with NO world, gripper closed is NOT
        proof that a piece is attached. Payload state remains EXPECTED_ATTACHED / EXPECTED_RELEASED.
        """
        cfg = MockConfig()
        cfg.ROBOT_BACKEND = "VIRTUAL"

        hw = HardwareManager(cfg, self.project_dir)
        hw.simulation_runtime = None  # Bare backend (no world)
        hw._init_robot()

        # In bare backend, payload_verifier must be None
        self.assertIsNone(hw.motion_executor.payload_verifier)

        # Execute gripper CLOSE step
        step_close = MotionStep(
            step_id=3,
            stage=MotionStage.GRIP,
            motion_type=MotionType.GRIPPER,
            gripper_command=GripperCommand.CLOSE,
        )
        res = hw.motion_executor._execute_step(step_close, last_completed_stage=MotionStage.LAND)
        self.assertTrue(res.success)
        # CRITICAL P1-4 CHECK: Must be EXPECTED_ATTACHED, NOT ATTACHED
        self.assertEqual(hw.motion_executor.payload_state, PayloadState.EXPECTED_ATTACHED)

        # Execute gripper OPEN step
        step_open = MotionStep(
            step_id=6,
            stage=MotionStage.RELEASE,
            motion_type=MotionType.GRIPPER,
            gripper_command=GripperCommand.OPEN,
        )
        res_open = hw.motion_executor._execute_step(step_open, last_completed_stage=MotionStage.PLACE_LAND)
        self.assertTrue(res_open.success)
        # CRITICAL P1-4 CHECK: Must be EXPECTED_RELEASED, NOT RELEASED
        self.assertEqual(hw.motion_executor.payload_state, PayloadState.EXPECTED_RELEASED)

        hw.cleanup()


if __name__ == "__main__":
    unittest.main()
