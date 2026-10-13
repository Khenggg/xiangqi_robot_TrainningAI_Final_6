"""Merged visual application uses retained simulator and commissioned visual hardware."""
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
from types import SimpleNamespace
from src.hardware.hardware_manager import HardwareManager
from src.hardware.robot_VIP import MotionResult
from src.motion.result import MotionExecutionResult, MotionFailureCategory

class HardwareManagerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.project_dir=str(Path(__file__).resolve().parents[2])
        self.config=SimpleNamespace(DRY_RUN=True,ROBOT_BACKEND="VIRTUAL")

    def test_virtual_runtime_owns_world_and_rejects_invalid_identity_without_motion(self):
        hw=HardwareManager(self.config,self.project_dir)
        try:
            with patch("src.hardware.robot_VIP.robot_sdk_core.RPC") as rpc:
                hw._init_robot()
                rpc.assert_not_called()
            self.assertIsNotNone(hw.simulation_runtime)
            self.assertIs(hw.backend,hw.simulation_runtime.backend)
            self.assertTrue(hw.is_robot_ready)
            twin=hw.setup_digital_twin(start=False)
            self.assertIs(twin.world,hw.simulation_runtime.world)
            self.assertIs(hw.backend.collision_guard.world,twin.world)
            before=hw.backend.get_state_snapshot().joints_deg
            result=hw.execute_piece_move(0,0,0,1,False,piece_id="missing_piece")
            self.assertIsInstance(result,MotionExecutionResult)
            self.assertFalse(result.success)
            self.assertEqual(before,hw.backend.get_state_snapshot().joints_deg)
            self.assertIsNone(hw.robot.robot)
        finally:
            hw.cleanup()

    def test_physical_dry_run_never_connects_or_claims_hardware_success(self):
        self.config.ROBOT_BACKEND="PHYSICAL"
        hw=HardwareManager(self.config,self.project_dir)
        with patch.object(hw.robot,"connect") as connect,patch.object(hw.robot,"move_piece") as move:
            hw._init_robot()
            self.assertIsNone(hw.backend)
            self.assertFalse(hw.is_robot_ready)
            result=hw.execute_piece_move(1,2,1,3,False)
            self.assertFalse(result.success)
            connect.assert_not_called();move.assert_not_called()
        self.assertIsNone(hw.setup_digital_twin(start=False))
        hw.cleanup()

    def test_physical_dispatch_requires_authorization_and_fresh_telemetry_not_mirror(self):
        self.config.ROBOT_BACKEND="PHYSICAL";self.config.DRY_RUN=False
        hw=HardwareManager(self.config,self.project_dir)
        hw.robot=MagicMock(connected=True,physical_motion_authorized=False)
        result=hw.execute_piece_move(0,0,0,1,False)
        self.assertFalse(result.success);hw.robot.move_piece.assert_not_called()
        hw.robot.physical_motion_authorized=True
        hw.physical_telemetry_ready = MagicMock(return_value=False)
        result=hw.execute_piece_move(0,0,0,1,False)
        self.assertFalse(result.success);hw.robot.move_piece.assert_not_called()
        self.assertIsNone(hw.board_pose_provider)
        hw.physical_telemetry_ready.return_value = True
        hw.robot.move_piece.return_value=MotionResult.ok()
        context=object()
        result=hw.execute_piece_move(0,0,0,1,False,piece_id="red_rook_0",move_context=context)
        self.assertTrue(result.success)
        hw.robot.move_piece.assert_called_once_with(0,0,0,1,False)

    def test_move_lock_rejects_parallel_command_without_controller_call(self):
        self.config.ROBOT_BACKEND="PHYSICAL"
        hw=HardwareManager(self.config,self.project_dir)
        with patch.object(hw.robot,"move_piece") as move:
            hw._piece_move_lock.acquire()
            try:result=hw.execute_piece_move(0,0,0,1,False)
            finally:hw._piece_move_lock.release()
        self.assertEqual(result.failure_category,MotionFailureCategory.ROBOT_BUSY)
        move.assert_not_called()
