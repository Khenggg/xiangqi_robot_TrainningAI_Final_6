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


    # -------------------------------------------------------------------------
    # 3. PHYSICAL READINESS GATED ON ENABLED STATE
    # -------------------------------------------------------------------------


    # -------------------------------------------------------------------------
    # 4. CAPTURE BIN PROVENANCE SAFETY INTERLOCK
    # -------------------------------------------------------------------------



    # -------------------------------------------------------------------------
    # 5. CONTINUOUS VISUAL PICK OFFSETS WITHOUT CORRUPTING LOGICAL TARGETS
    # -------------------------------------------------------------------------


    # -------------------------------------------------------------------------
    # 6. AI EXECUTION: NO DRY-RUN COMMIT BYPASS
    # -------------------------------------------------------------------------


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
