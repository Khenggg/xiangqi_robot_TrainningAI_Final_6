"""
Phase 3B-Wiring: Comprehensive Integration and Safety Invariant Tests.

Tests:
1. Physical backend connection is strictly READ-ONLY (no RobotEnable(1), no Mode(0)).
2. Explicit enable / disable API lifecycle.
3. Legacy double connection eliminated in HardwareManager.
4. Physical readiness requires enabled backend when not dry-run.
5. Capture bin provenance check rejects physical capture when CAPTURE_BIN_VALIDATED=False.
6. Virtual capture succeeds regardless of physical bin validation.
7. Continuous visual pick offsets in production pipeline.
8. AI move execution gates GameState commit strictly on motion success (no dry-run bypass).
9. Stale placement version rejected through production path.
10. Backend MOVING state rejected through production path.
11. WAIT dwell belief state semantics (unverified physical vs verified virtual).
"""

import dataclasses
import unittest
from unittest.mock import MagicMock, patch, call
from pathlib import Path

from src.hardware.backends.physical_fr3 import PhysicalFR3Backend
from src.hardware.backends.base import RobotStateSnapshot
from src.hardware.hardware_manager import HardwareManager
from src.domain.board_pose_provider import BoardCalibrationProfile, FixedBoardPoseProvider
from src.motion.contracts import (
    MotionStage,
    MotionType,
    GripperCommand,
)
from src.motion.plan import PieceMoveIntent, CaptureIntent, ResolvedMotionPlan
from src.motion.result import (
    PayloadState,
    MotionFailureCategory,
    ExecutionFailureCategory,
    MotionExecutionResult,
)
from src.motion.resolver import MotionResolver
from src.motion.executor import MotionExecutor
from src.motion.coordinator import MotionProfile
from src.core.ai_execution import execute_ai_move
from src.core import xiangqi


class MockWiringConfig:
    DRY_RUN = True
    ROBOT_BACKEND = "PHYSICAL"
    ROBOT_IP = "192.168.58.2"
    BOARD_CALIBRATION_MODE = "POINTER_CONTACT"
    BOARD_ORIGIN_X = 200.0
    BOARD_ORIGIN_Y = -100.0
    ROTATION = [-179.164, -3.047, -26.304]
    PICK_TOOL_ROTATION = [-179.164, -3.047, -26.304]
    SAFE_CLEARANCE_Z_MM = 40.0
    PICK_DEPTH_OFFSET_MM = 0.0
    CAPTURE_BIN_X = -226.123
    CAPTURE_BIN_Y = 225.024
    CAPTURE_BIN_Z = 291.68
    CAPTURE_BIN_POSE_MM_DEG = [-226.123, 225.024, 291.68, -179.164, -3.047, -26.304]
    CAPTURE_BIN_PROVENANCE = "LEGACY_UNVERIFIED"
    CAPTURE_BIN_VALIDATED = False
    ENGINE_TYPE = "LOCAL"
    MOONFISH_EXE = "dummy_moonfish"
    MOONFISH_NNUE = None
    MOONFISH_THINK_MS = 100
    VISUAL_PICK_ENABLED = False


class TestPhase3BWiring(unittest.TestCase):

    def setUp(self):
        self.config = MockWiringConfig()
        self.project_dir = str(Path(__file__).resolve().parent.parent.parent)

    # -------------------------------------------------------------------------
    # 1. READ-ONLY PHYSICAL CONNECT & EXPLICIT ENABLE/DISABLE API
    # -------------------------------------------------------------------------

    @patch("src.hardware.backends.physical_fr3.robot_sdk_core")
    def test_physical_connect_is_strictly_read_only(self, mock_sdk_core):
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        mock_rpc.GetActualTCPPose.return_value = (0, [200.0, -100.0, 100.0, 180.0, 0.0, 0.0])
        mock_rpc.SetToolDO.return_value = 0
        mock_sdk_core.RPC.return_value = mock_rpc

        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=False)
        ok = backend.connect()

        self.assertTrue(ok)
        self.assertTrue(backend.get_state_snapshot().connected)
        self.assertFalse(backend.is_enabled)

        # Invariant: connect() must NEVER call RobotEnable(1) or Mode(0)
        mock_rpc.RobotEnable.assert_not_called()
        mock_rpc.Mode.assert_not_called()

        backend.disconnect()

    @patch("src.hardware.backends.physical_fr3.robot_sdk_core")
    def test_explicit_enable_disable_lifecycle(self, mock_sdk_core):
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        mock_rpc.GetActualTCPPose.return_value = (0, [200.0, -100.0, 100.0, 180.0, 0.0, 0.0])
        mock_rpc.RobotEnable.return_value = 0
        mock_rpc.Mode.return_value = 0
        mock_rpc.SetToolDO.return_value = 0
        mock_sdk_core.RPC.return_value = mock_rpc

        backend = PhysicalFR3Backend(ip="192.168.58.2", dry_run=False)
        backend.connect()
        self.assertFalse(backend.is_enabled)

        # Explicit enable
        ok_en = backend.enable_robot()
        self.assertTrue(ok_en)
        self.assertTrue(backend.is_enabled)
        mock_rpc.RobotEnable.assert_called_with(1)

        # Explicit mode
        ok_mode = backend.set_operational_mode(0)
        self.assertTrue(ok_mode)
        mock_rpc.Mode.assert_called_with(0)

        # Explicit disable
        ok_dis = backend.disable_robot()
        self.assertTrue(ok_dis)
        self.assertFalse(backend.is_enabled)
        mock_rpc.RobotEnable.assert_called_with(0)

        # Enable again, then disconnect -> must safely disable
        backend.enable_robot()
        self.assertTrue(backend.is_enabled)
        backend.disconnect()
        self.assertFalse(backend.is_enabled)

    # -------------------------------------------------------------------------
    # 2. LEGACY DOUBLE CONNECTION ELIMINATED
    # -------------------------------------------------------------------------

    @patch("src.hardware.backends.physical_fr3.robot_sdk_core")
    @patch("src.hardware.hardware_manager.FR5Robot")
    @patch("src.hardware.hardware_manager.PhysicalTeachingPointBoardPoseProvider")
    def test_legacy_double_connection_eliminated(self, mock_cal_provider, mock_fr5_class, mock_sdk_core):
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        mock_rpc.GetActualTCPPose.return_value = (0, [200.0, -100.0, 100.0, 180.0, 0.0, 0.0])
        mock_rpc.SetToolDO.return_value = 0
        mock_sdk_core.RPC.return_value = mock_rpc

        mock_fr5 = MagicMock()
        mock_fr5.connected = False
        mock_fr5_class.return_value = mock_fr5

        # Mock successful calibration
        mock_provider_inst = MagicMock()
        mock_provider_inst.is_calibrated = True
        mock_provider_inst.calibration_result.success = True
        mock_provider_inst.calibration_result.warnings = []
        mock_provider_inst.calibration_result.calibration_log = "OK"
        mock_provider_inst.get_board_placement_state.return_value.cell_to_robot_xyz.return_value = [0.2, -0.1, 0.0]
        mock_cal_provider.from_controller.return_value = mock_provider_inst

        cfg = MockWiringConfig()
        cfg.DRY_RUN = False
        hw = HardwareManager(cfg, self.project_dir)
        hw._init_robot()

        # Invariant: hw.robot.connect() was NEVER called!
        mock_fr5.connect.assert_not_called()
        self.assertFalse(hw.robot.connected)

        # hw.backend was connected (read-only)
        self.assertIsNotNone(hw.backend)
        self.assertTrue(hw.backend.get_state_snapshot().connected)
        self.assertFalse(hw.backend.is_enabled)

        hw.cleanup()

    # -------------------------------------------------------------------------
    # 3. PHYSICAL READINESS GATED ON ENABLED STATE
    # -------------------------------------------------------------------------

    @patch("src.hardware.backends.physical_fr3.robot_sdk_core")
    @patch("src.hardware.hardware_manager.PhysicalTeachingPointBoardPoseProvider")
    def test_physical_readiness_requires_enabled_backend(self, mock_cal_provider, mock_sdk_core):
        mock_rpc = MagicMock()
        mock_rpc.SDK_state = True
        mock_rpc.GetActualJointPosDegree.return_value = (0, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
        mock_rpc.GetActualTCPPose.return_value = (0, [200.0, -100.0, 100.0, 180.0, 0.0, 0.0])
        mock_rpc.RobotEnable.return_value = 0
        mock_rpc.Mode.return_value = 0
        mock_rpc.SetToolDO.return_value = 0
        mock_sdk_core.RPC.return_value = mock_rpc

        mock_provider_inst = MagicMock()
        mock_provider_inst.is_calibrated = True
        mock_provider_inst.calibration_result.success = True
        mock_provider_inst.calibration_result.warnings = []
        mock_provider_inst.calibration_result.calibration_log = "OK"
        mock_provider_inst.get_board_placement_state.return_value.cell_to_robot_xyz.return_value = [0.2, -0.1, 0.0]
        mock_cal_provider.from_controller.return_value = mock_provider_inst

        cfg = MockWiringConfig()
        cfg.DRY_RUN = False
        hw = HardwareManager(cfg, self.project_dir)
        hw._init_robot()

        # Calibrated and connected, but NOT enabled
        self.assertFalse(hw.backend.is_enabled)
        self.assertFalse(hw.is_robot_ready)
        self.assertEqual(hw.lifecycle_state, "CONNECTED")

        # Explicitly enable robot: enabled but operational mode still unconfigured (None)
        hw.enable_robot()
        self.assertTrue(hw.backend.is_enabled)
        self.assertFalse(hw.is_robot_ready)
        self.assertEqual(hw.lifecycle_state, "ENABLED")

        # Explicitly configure operational mode to 0 -> ready becomes True
        hw.set_operational_mode(0)
        self.assertEqual(hw.backend.operational_mode, 0)
        self.assertTrue(hw.is_robot_ready)
        self.assertEqual(hw.lifecycle_state, "MOTION_AUTHORIZED")

        # Explicitly disable robot -> ready turns False again
        hw.disable_robot()
        self.assertFalse(hw.backend.is_enabled)
        self.assertFalse(hw.is_robot_ready)
        self.assertEqual(hw.lifecycle_state, "CONNECTED")

        hw.cleanup()

    # -------------------------------------------------------------------------
    # 4. CAPTURE BIN PROVENANCE SAFETY INTERLOCK
    # -------------------------------------------------------------------------

    def test_physical_capture_rejected_when_capture_bin_unvalidated(self):
        cfg = MockWiringConfig()
        cfg.DRY_RUN = True
        cfg.ROBOT_BACKEND = "PHYSICAL"
        cfg.CAPTURE_BIN_VALIDATED = False

        hw = HardwareManager(cfg, self.project_dir)
        hw.backend = PhysicalFR3Backend(ip="127.0.0.1", dry_run=True)
        hw.backend.connect()
        provider = FixedBoardPoseProvider.from_forward_shift(0.0)
        provider.is_calibrated = True
        hw.board_pose_provider = provider
        hw.motion_profile = MotionProfile(
            pick_tcp_height_above_board_mm=4.715,
            place_tcp_height_above_board_mm=4.715,
            safe_clearance_above_board_mm=40.0,
            provenance="MOCK_TEST",
        )
        hw.motion_resolver = MotionResolver(
            board_pose_provider=hw.board_pose_provider,
            motion_profile=hw.motion_profile,
            tool_rotation_deg=[-179.164, -3.047, -26.304],
        )
        hw.motion_executor = MotionExecutor(backend=hw.backend)
        hw.physical_motion_authorized = True

        self.assertTrue(hw.is_robot_ready)

        # Invariant: Physical capture with CAPTURE_BIN_VALIDATED=False must fail closed
        res_cap = hw.execute_piece_move(s_col=0, s_row=0, d_col=0, d_row=1, is_capture=True)
        self.assertFalse(res_cap.success)
        self.assertEqual(res_cap.failure_category, ExecutionFailureCategory.SAFETY_INTERLOCK)
        self.assertIn("not validated", res_cap.message)

        # Normal move without capture succeeds
        res_move = hw.execute_piece_move(s_col=0, s_row=0, d_col=0, d_row=1, is_capture=False)
        self.assertTrue(res_move.success)

        # If CAPTURE_BIN_VALIDATED is True, physical capture is permitted
        cfg.CAPTURE_BIN_VALIDATED = True
        res_cap_validated = hw.execute_piece_move(s_col=0, s_row=0, d_col=0, d_row=1, is_capture=True)
        self.assertTrue(res_cap_validated.success)

        hw.cleanup()

    def test_virtual_capture_succeeds_independent_of_physical_validation(self):
        cfg = MockWiringConfig()
        cfg.DRY_RUN = True
        cfg.ROBOT_BACKEND = "VIRTUAL"
        cfg.CAPTURE_BIN_VALIDATED = False  # Physical flag is False

        hw = HardwareManager(cfg, self.project_dir)
        hw._init_robot()

        self.assertTrue(hw.is_robot_ready)
        res_cap = hw.execute_piece_move(s_col=0, s_row=0, d_col=0, d_row=1, is_capture=True)
        self.assertTrue(res_cap.success)

        hw.cleanup()

    # -------------------------------------------------------------------------
    # 5. CONTINUOUS VISUAL PICK OFFSETS WITHOUT CORRUPTING LOGICAL TARGETS
    # -------------------------------------------------------------------------

    def test_continuous_visual_pick_offsets_in_production_pipeline(self):
        cfg = MockWiringConfig()
        cfg.DRY_RUN = True
        cfg.ROBOT_BACKEND = "PHYSICAL"

        hw = HardwareManager(cfg, self.project_dir)
        hw.backend = PhysicalFR3Backend(ip="127.0.0.1", dry_run=True)
        hw.backend.connect()
        provider = FixedBoardPoseProvider.from_forward_shift(0.0)
        provider.is_calibrated = True
        hw.board_pose_provider = provider
        hw.motion_profile = MotionProfile(
            pick_tcp_height_above_board_mm=4.715,
            place_tcp_height_above_board_mm=4.715,
            safe_clearance_above_board_mm=40.0,
            provenance="MOCK_TEST",
        )
        hw.motion_resolver = MotionResolver(
            board_pose_provider=hw.board_pose_provider,
            motion_profile=hw.motion_profile,
            tool_rotation_deg=[-179.164, -3.047, -26.304],
        )
        hw.motion_executor = MotionExecutor(backend=hw.backend)
        hw.physical_motion_authorized = True

        # Section 48: Continuous visual pick offset
        # Logical source: row=6, col=4 -> Logical destination: row=2, col=4
        # Visual source: row=6.08, col=3.94
        class MockVisualTarget:
            row = 6.08
            col = 3.94

        moving_target = MockVisualTarget()

        # Capture executed plan by mocking executor.execute_plan
        executed_plans = []
        original_exec = hw.motion_executor.execute_plan

        def capture_plan(plan):
            executed_plans.append(plan)
            return original_exec(plan)

        hw.motion_executor.execute_plan = capture_plan

        # HardwareManager.execute_piece_move(s_col, s_row, d_col, d_row, ...)
        res = hw.execute_piece_move(
            s_col=4, s_row=6, d_col=4, d_row=2, is_capture=False,
            moving_visual_target=moving_target,
        )
        self.assertTrue(res.success)
        self.assertEqual(len(executed_plans), 1)
        plan = executed_plans[0]

        # Calculate nominal pick and place poses
        state = hw.board_pose_provider.get_board_placement_state()
        p_refined_pick = state.cell_to_robot_xyz(6.08, 3.94, height_above_board_mm=4.715)
        p_nominal_place = state.cell_to_robot_xyz(2, 4, height_above_board_mm=4.715)

        # LAND waypoint (descent to grasp surface) must have continuous visual pick applied
        land_step = next(s for s in plan.steps if s.stage == MotionStage.LAND and s.waypoint is not None)
        self.assertAlmostEqual(land_step.waypoint.position_mm[0], p_refined_pick[0] * 1000.0, places=2)
        self.assertAlmostEqual(land_step.waypoint.position_mm[1], p_refined_pick[1] * 1000.0, places=2)

        # PLACE_LAND waypoint must NOT have visual offset: exact canonical cell center!
        place_step = next(s for s in plan.steps if s.stage == MotionStage.PLACE_LAND and s.waypoint is not None)
        self.assertAlmostEqual(place_step.waypoint.position_mm[0], p_nominal_place[0] * 1000.0, places=2)
        self.assertAlmostEqual(place_step.waypoint.position_mm[1], p_nominal_place[1] * 1000.0, places=2)

        hw.cleanup()

    # -------------------------------------------------------------------------
    # 6. AI EXECUTION: NO DRY-RUN COMMIT BYPASS
    # -------------------------------------------------------------------------

    def test_ai_execution_dry_run_no_bypass_on_failure(self):
        class MockGameState:
            def __init__(self):
                self.board = xiangqi.get_board()
                self.move_history = []
                self.turn = "b"
                self.last_move = None
            def set_status(self, *args, **kwargs):
                pass
            def update_fen_from_board(self):
                pass

        state = MockGameState()
        initial_board = [row[:] for row in state.board]
        test_move = ((1, 2), (4, 2))

        # 1. hw not ready -> rejected commit even in dry_run
        mock_hw = MagicMock()
        mock_hw.is_robot_ready = False

        res = execute_ai_move(state=state, hw=mock_hw, best_move=test_move, dry_run=True)
        self.assertFalse(res)
        self.assertEqual(state.turn, "b")
        self.assertEqual(state.board, initial_board)

        # 2. hw ready, but execute_piece_move returns failure -> rejected commit
        mock_hw.is_robot_ready = True
        mock_hw.execute_piece_move.return_value = MotionExecutionResult.fail(
            failed_stage=MotionStage.LAND,
            category=ExecutionFailureCategory.IK_FAILED,
            message="IK unreachable",
        )

        res_fail = execute_ai_move(state=state, hw=mock_hw, best_move=test_move, dry_run=True)
        self.assertFalse(res_fail)
        self.assertEqual(state.turn, "b")
        self.assertEqual(state.board, initial_board)

        # 3. hw ready and execute_piece_move succeeds -> committed
        mock_hw.execute_piece_move.return_value = MotionExecutionResult.ok()

        res_ok = execute_ai_move(state=state, hw=mock_hw, best_move=test_move, dry_run=True)
        self.assertTrue(res_ok)
        self.assertEqual(state.turn, "r")
        self.assertEqual(state.board[2][4], "b_C")
        self.assertEqual(state.board[2][1], ".")

    # -------------------------------------------------------------------------
    # 7. WAIT DWELL BELIEF STATE SEMANTICS
    # -------------------------------------------------------------------------

    def test_wait_dwell_belief_state_semantics(self):
        cfg = MockWiringConfig()
        cfg.DRY_RUN = True
        cfg.ROBOT_BACKEND = "PHYSICAL"

        hw = HardwareManager(cfg, self.project_dir)
        hw.backend = PhysicalFR3Backend(ip="127.0.0.1", dry_run=True)
        hw.backend.connect()
        provider = FixedBoardPoseProvider.from_forward_shift(0.0)
        provider.is_calibrated = True
        hw.board_pose_provider = provider
        hw.motion_profile = MotionProfile(
            pick_tcp_height_above_board_mm=4.715,
            place_tcp_height_above_board_mm=4.715,
            safe_clearance_above_board_mm=40.0,
            provenance="MOCK_TEST",
        )
        hw.motion_resolver = MotionResolver(
            board_pose_provider=hw.board_pose_provider,
            motion_profile=hw.motion_profile,
            tool_rotation_deg=[-179.164, -3.047, -26.304],
        )

        # Case A: Unverified physical mode (payload_verifier=None)
        # Settle dwell does NOT fabricate sensor certainty -> EXPECTED_RELEASED
        executor_unverified = MotionExecutor(backend=hw.backend, payload_verifier=None)
        plan = hw.motion_resolver.resolve_move(
            intent=PieceMoveIntent(src_row=0, src_col=0, dst_row=1, dst_col=0)
        )
        res_unverified = executor_unverified.execute_plan(plan)
        self.assertTrue(res_unverified.success)
        self.assertEqual(res_unverified.payload_state, PayloadState.EXPECTED_RELEASED)

        # Case B: Verified mode where verifier callback confirms piece released
        verified_called = []
        def verifier(state: PayloadState) -> bool:
            verified_called.append(state)
            return True

        executor_verified = MotionExecutor(backend=hw.backend, payload_verifier=verifier)
        res_verified = executor_verified.execute_plan(plan)
        self.assertTrue(res_verified.success)
        self.assertIn(PayloadState.EXPECTED_RELEASED, verified_called)
        self.assertEqual(res_verified.payload_state, PayloadState.RELEASED)

        hw.cleanup()

    # -------------------------------------------------------------------------
    # 8. STALE PLACEMENT & BACKEND MOVING GUARDS
    # -------------------------------------------------------------------------

    def test_capture_continuous_visual_pick_offsets(self):
        # Section 49: Capture visual test
        # captured_visual_target -> captured-piece pick refined
        # moving_visual_target -> attacker pick refined
        # attacker place -> logical destination unchanged
        cfg = MockWiringConfig()
        cfg.DRY_RUN = True
        cfg.ROBOT_BACKEND = "VIRTUAL"

        hw = HardwareManager(cfg, self.project_dir)
        hw.backend = PhysicalFR3Backend(ip="127.0.0.1", dry_run=True)
        hw.backend.connect()
        provider = FixedBoardPoseProvider.from_forward_shift(0.0)
        provider.is_calibrated = True
        hw.board_pose_provider = provider
        hw.motion_profile = MotionProfile(
            pick_tcp_height_above_board_mm=4.715,
            place_tcp_height_above_board_mm=4.715,
            safe_clearance_above_board_mm=40.0,
            provenance="MOCK_TEST",
        )
        hw.motion_resolver = MotionResolver(
            board_pose_provider=hw.board_pose_provider,
            motion_profile=hw.motion_profile,
            tool_rotation_deg=[-179.164, -3.047, -26.304],
        )
        hw.motion_executor = MotionExecutor(backend=hw.backend)
        hw.physical_motion_authorized = True

        class MockVisualTarget:
            def __init__(self, r, c):
                self.row = r
                self.col = c

        moving_target = MockVisualTarget(6.08, 3.94)  # Attacker at (6, 4) refined
        captured_target = MockVisualTarget(2.04, 3.96)  # Target at (2, 4) refined

        executed_plans = []
        original_exec = hw.motion_executor.execute_plan

        def capture_plan(plan):
            executed_plans.append(plan)
            return original_exec(plan)

        hw.motion_executor.execute_plan = capture_plan

        # Attacker: s_row=6, s_col=4 -> Captured at: d_row=2, d_col=4
        res = hw.execute_piece_move(
            s_col=4, s_row=6, d_col=4, d_row=2, is_capture=True,
            moving_visual_target=moving_target,
            captured_visual_target=captured_target,
        )
        self.assertTrue(res.success)
        self.assertEqual(len(executed_plans), 1)
        plan = executed_plans[0]

        state = hw.board_pose_provider.get_board_placement_state()
        p_cap_pick = state.cell_to_robot_xyz(2.04, 3.96, height_above_board_mm=4.715)
        p_atk_pick = state.cell_to_robot_xyz(6.08, 3.94, height_above_board_mm=4.715)
        p_dst_place = state.cell_to_robot_xyz(2, 4, height_above_board_mm=4.715)

        # Pick steps: first LAND is captured piece descent, second LAND is attacker descent
        land_steps = [s for s in plan.steps if s.stage == MotionStage.LAND and s.waypoint is not None]
        self.assertEqual(len(land_steps), 2)
        cap_land_step = land_steps[0]
        atk_land_step = land_steps[1]

        # Refined captured pick
        self.assertAlmostEqual(cap_land_step.waypoint.position_mm[0], p_cap_pick[0] * 1000.0, places=2)
        self.assertAlmostEqual(cap_land_step.waypoint.position_mm[1], p_cap_pick[1] * 1000.0, places=2)

        # Refined attacker pick
        self.assertAlmostEqual(atk_land_step.waypoint.position_mm[0], p_atk_pick[0] * 1000.0, places=2)
        self.assertAlmostEqual(atk_land_step.waypoint.position_mm[1], p_atk_pick[1] * 1000.0, places=2)

        # Place steps: first PLACE_LAND is bin, second PLACE_LAND is destination
        place_land_steps = [s for s in plan.steps if s.stage == MotionStage.PLACE_LAND and s.waypoint is not None]
        self.assertEqual(len(place_land_steps), 2)
        dst_place_step = place_land_steps[1]
        self.assertAlmostEqual(dst_place_step.waypoint.position_mm[0], p_dst_place[0] * 1000.0, places=2)
        self.assertAlmostEqual(dst_place_step.waypoint.position_mm[1], p_dst_place[1] * 1000.0, places=2)

        hw.cleanup()

    def test_stale_placement_version_rejected(self):
        backend = PhysicalFR3Backend(ip="127.0.0.1", dry_run=True)
        backend.connect()
        provider = FixedBoardPoseProvider.from_forward_shift(0.0)
        profile = MotionProfile(pick_tcp_height_above_board_mm=4.715, place_tcp_height_above_board_mm=4.715, safe_clearance_above_board_mm=40.0)
        resolver = MotionResolver(board_pose_provider=provider, motion_profile=profile)
        executor = MotionExecutor(backend=backend, board_pose_provider=provider)

        plan = resolver.resolve_move(PieceMoveIntent(src_row=0, src_col=0, dst_row=1, dst_col=0))

        # Mutate plan placement version to simulate stale cache
        stale_plan = dataclasses.replace(
            plan,
            placement_version=(plan.placement_version or 0) + 99,
        )

        res = executor.execute_plan(stale_plan)
        self.assertFalse(res.success)
        self.assertEqual(res.failure_category, MotionFailureCategory.STALE_PLACEMENT_VERSION)
        backend.disconnect()

    def test_backend_moving_rejected(self):
        backend = PhysicalFR3Backend(ip="127.0.0.1", dry_run=True)
        backend.connect()
        provider = FixedBoardPoseProvider.from_forward_shift(0.0)
        profile = MotionProfile(pick_tcp_height_above_board_mm=4.715, place_tcp_height_above_board_mm=4.715, safe_clearance_above_board_mm=40.0)
        resolver = MotionResolver(board_pose_provider=provider, motion_profile=profile)
        executor = MotionExecutor(backend=backend)

        plan = resolver.resolve_move(PieceMoveIntent(src_row=0, src_col=0, dst_row=1, dst_col=0))

        # Put backend into MOVING state
        backend._motion_state = "MOVING"

        res = executor.execute_plan(plan)
        self.assertFalse(res.success)
        self.assertEqual(res.failure_category, MotionFailureCategory.BACKEND_NOT_READY)
        self.assertTrue("not ready" in res.message.lower() or "moving" in res.message.lower())
        backend.disconnect()


if __name__ == "__main__":
    unittest.main()
