"""
Comprehensive Master Unit Tests for Phase 3 Final Corrective Pass:
1.  test_try_grasp_target_matching: try_grasp filters strictly by target_piece_id.
2.  test_try_grasp_target_mismatch_rejection: try_grasp rejects candidates not matching target_piece_id.
3.  test_pick_result_fail_fast_contract: PickResult dataclass/dict contract and fail-fast invariants.
4.  test_pybullet_fr3_tracking_interpolated: PyBullet FR3 arm links follow backend trajectory in real-time.
5.  test_runtime_operation_state_transitions: RuntimeOperationState transitions cleanly to/from IDLE.
6.  test_runtime_operation_state_mutual_exclusion: Validations, motions, and adjustments reject with BUSY if not IDLE.
7.  test_collision_guard_explicit_candidate_no_wildcard: Wildcard '*' disallowed; only explicit piece ID or None allowed.
8.  test_is_service_safe_predicate: is_service_safe() returns True only at SERVICE_SAFE_JOINTS_DEG.
9.  test_go_service_safe_motion: runtime_go_service_safe() drives arm safely to service safe pose.
10. test_prepare_board_adjustment_flow: prepare_board_adjustment() clears grasp and elevates arm to service safe pose.
11. test_swept_volume_collision_arm_obstruction: set_board_placement() rejects if arm obstructs swept path.
12. test_swept_volume_collision_clear_path: Swept-volume check passes and relocates cleanly when arm is at service safe pose.
13. test_runtime_jog_tcp: Cartesian jog along TCP axes with collision protection.
14. test_runtime_jog_joint: Manual joint jog within soft limits.
15. test_granular_recovery_actions: Granular reset and clear_error operations succeed independently.
16. test_ruler_single_authoritative_update: ruler.mjs has exactly one authoritative updateBoardPlacement method.
17. test_full_system_reset_in_process: full_reset() restores complete system state without restarting Python process.
"""

import json
from pathlib import Path
import sys
import unittest
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.physics.state import GraspStatus, GraspResult, PickResult, PlaceResult, PiecePhysicalState
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.runtime import VirtualXiangqiSimulation, RuntimeOperationState
from src.simulation.virtual_fr3_backend import VirtualFR3Backend, SERVICE_SAFE_JOINTS_DEG


class Phase3FinalMasterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        cls.sim.start()

    @classmethod
    def tearDownClass(cls):
        cls.sim.stop()

    def setUp(self):
        self.sim.clear_error()

    def tearDown(self):
        self.sim.clear_error()
        self.sim.world.step_until_settled(max_steps=20)

    def test_01_try_grasp_target_matching(self):
        """1. try_grasp filters strictly by target_piece_id."""
        world = self.sim.world
        # Identify an existing piece on board
        first_piece_id = list(world.pieces.keys())[0]
        piece = world.pieces[first_piece_id]
        pos, quat = piece.get_pose_robot_base()

        # Place gripper directly at piece position and close it
        world.gripper.grasp_pos = np.array(pos, dtype=float)
        world.gripper.grasp_quat = np.array(quat, dtype=float)
        world.gripper.set_gripper_state(True)

        res = world.try_grasp(target_piece_id=first_piece_id)
        self.assertTrue(res.success, f"Should grasp target piece {first_piece_id}")
        self.assertEqual(res.piece_id, first_piece_id)
        self.assertEqual(res.status, GraspStatus.SUCCESS)

        # Release for clean state
        world.release_attached_piece()
        world.gripper.set_gripper_state(False)

    def test_02_try_grasp_target_mismatch_rejection(self):
        """2. try_grasp rejects candidate that does not match target_piece_id."""
        world = self.sim.world
        p_ids = list(world.pieces.keys())
        first_piece_id = p_ids[0]
        other_piece_id = p_ids[1]

        piece = world.pieces[first_piece_id]
        pos, quat = piece.get_pose_robot_base()

        # Gripper is at first_piece_id, but we target other_piece_id
        world.gripper.grasp_pos = np.array(pos, dtype=float)
        world.gripper.grasp_quat = np.array(quat, dtype=float)
        world.gripper.set_gripper_state(True)

        res = world.try_grasp(target_piece_id=other_piece_id)
        self.assertFalse(res.success, "Should reject grasp when piece under gripper does not match target_piece_id")
        self.assertIn(res.status, (GraspStatus.AMBIGUOUS, GraspStatus.NO_CANDIDATE))
        self.assertIsNone(world.get_attached_piece())
        world.gripper.set_gripper_state(False)

    def test_03_pick_result_fail_fast_contract(self):
        """3. PickResult dataclass/dict contract and fail-fast invariants."""
        # Check fail result attributes
        fail_res = PickResult(
            success=False,
            status="HOVER_UNREACHABLE",
            error="IK failed",
            piece_id="r_c_1",
            reason="IK failed",
        )
        self.assertFalse(bool(fail_res))
        self.assertEqual(fail_res.success, False)
        self.assertEqual(fail_res["status"], "HOVER_UNREACHABLE")
        self.assertEqual(fail_res.status, "HOVER_UNREACHABLE")
        self.assertEqual(fail_res.piece_id, "r_c_1")

        # Check success result
        ok_res = PickResult(
            success=True,
            status="SUCCESS",
            piece_id="r_c_1",
        )
        self.assertTrue(bool(ok_res))
        self.assertEqual(ok_res.success, True)
        self.assertEqual(ok_res.status, "SUCCESS")

        # Verify runtime.pick_piece returns PickResult on non-existent piece
        res = self.sim.pick_piece("non_existent_piece_id_12345")
        self.assertIsInstance(res, PickResult)
        self.assertFalse(res.success)
        self.assertEqual(res.status, "PIECE_NOT_FOUND")

    def test_04_pybullet_fr3_tracking_interpolated(self):
        """4. PyBullet FR3 arm links follow backend trajectory in real-time."""
        self.sim.runtime_go_service_safe()
        q_backend = self.sim.backend.get_state_snapshot().joints_rad
        q_bullet = self.sim.world.get_robot_joint_positions()

        # Verify pybullet robot joints strictly mirror backend joints within 1e-3 rad
        np.testing.assert_allclose(q_bullet, q_backend, atol=1e-3)

    def test_05_runtime_operation_state_transitions(self):
        """5. RuntimeOperationState transitions cleanly to/from IDLE."""
        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

        with self.sim.acquire_operation_state(RuntimeOperationState.MOTION):
            self.assertEqual(self.sim.operation_state, RuntimeOperationState.MOTION)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

        with self.sim.acquire_operation_state(RuntimeOperationState.VALIDATING_LOCAL):
            self.assertEqual(self.sim.operation_state, RuntimeOperationState.VALIDATING_LOCAL)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

        with self.sim.acquire_operation_state(RuntimeOperationState.BOARD_ADJUSTMENT):
            self.assertEqual(self.sim.operation_state, RuntimeOperationState.BOARD_ADJUSTMENT)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

        with self.sim.acquire_operation_state(RuntimeOperationState.SERVICE_MOVE):
            self.assertEqual(self.sim.operation_state, RuntimeOperationState.SERVICE_MOVE)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_06_runtime_operation_state_mutual_exclusion(self):
        """6. Validations, motions, and adjustments reject with BUSY if not IDLE."""
        with self.sim.acquire_operation_state(RuntimeOperationState.MOTION):
            # Attempt validation while MOTION is active
            res_val = self.sim.validate_board_placement()
            self.assertFalse(res_val["success"])
            self.assertEqual(res_val["status"], "VALIDATION_REJECTED_BUSY")

            # Attempt full route validation while MOTION is active
            res_routes = self.sim.validate_full_board_routes(sample_limit=5)
            self.assertFalse(res_routes["success"])
            self.assertEqual(res_routes["status"], "VALIDATION_REJECTED_BUSY")

            # Attempt board relocation while MOTION is active
            res_reloc = self.sim.set_board_placement(forward_shift_mm=10.0)
            self.assertFalse(res_reloc["success"])
            self.assertEqual(res_reloc["status"], "BOARD_RELOCATION_REJECTED_BUSY")

            # Attempt trajectory execution while MOTION is active
            res_traj = self.sim.execute_3stage_trajectory((0, 0), (0, 1))
            self.assertFalse(res_traj["success"])
            self.assertEqual(res_traj["status"], "MOTION_REJECTED_BUSY")

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_07_collision_guard_explicit_candidate_no_wildcard(self):
        """7. Wildcard '*' disallowed; only explicit piece ID or None allowed."""
        self.sim.backend.set_allowed_grasp_piece_id("*")
        # Wildcard '*' must NOT be accepted or allowed
        self.assertIsNone(self.sim.backend.allowed_grasp_piece_id)

        # Setting explicit ID must succeed
        self.sim.backend.set_allowed_grasp_piece_id("r_c_1")
        self.assertEqual(self.sim.backend.allowed_grasp_piece_id, "r_c_1")
        self.sim.backend.set_allowed_grasp_piece_id(None)
        self.assertIsNone(self.sim.backend.allowed_grasp_piece_id)

    def test_08_is_service_safe_predicate(self):
        """8. is_service_safe() returns True only at SERVICE_SAFE_JOINTS_DEG."""
        self.sim.backend.move_joint([0.0, -90.0, 90.0, -45.0, -90.0, 0.0])
        self.assertFalse(self.sim.backend.is_service_safe())

        self.sim.backend.move_joint(SERVICE_SAFE_JOINTS_DEG)
        self.assertTrue(self.sim.backend.is_service_safe())

    def test_09_go_service_safe_motion(self):
        """9. runtime_go_service_safe() drives arm safely to service safe pose."""
        res = self.sim.runtime_go_service_safe()
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "SERVICE_SAFE_REACHED")
        self.assertTrue(self.sim.backend.is_service_safe())
        snap_deg = self.sim.backend.get_state_snapshot().joints_deg
        np.testing.assert_allclose(snap_deg, SERVICE_SAFE_JOINTS_DEG, atol=1.0)

    def test_10_prepare_board_adjustment_flow(self):
        """10. prepare_board_adjustment() clears grasp and elevates arm to service safe pose."""
        res = self.sim.prepare_board_adjustment()
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "READY_FOR_BOARD_ADJUSTMENT")
        self.assertIsNone(self.sim.world.get_attached_piece())
        self.assertFalse(self.sim.backend.is_gripper_closed())
        self.assertTrue(self.sim.backend.is_service_safe())

    def test_11_swept_volume_collision_arm_obstruction(self):
        """11. set_board_placement() rejects if arm obstructs swept path."""
        # Drive robot to a cell grasp pose near the board
        r, c = 0, 4
        z_grasp = self.sim.board_surface_z
        grasp_m = self.sim.cell_to_robot_xyz_m(r, c, z_grasp)
        grasp_pose_mm = [grasp_m[0] * 1000.0, grasp_m[1] * 1000.0, grasp_m[2] * 1000.0, 180.0, 0.0, 90.0]
        ik = self.sim.backend.solve_tcp_ik(grasp_pose_mm, allow_multi_seed=True)
        if ik.success:
            self.sim.backend.move_joint(np.degrees(ik.joints_rad).tolist())
            self.sim.world.sync_robot_runtime_configuration(ik.joints_rad)

        # Attempt to relocate board while arm is low on board
        is_safe, reason = self.sim.world.check_board_swept_volume_collision(
            new_forward_shift_m=0.04,
            new_height_offset_m=0.0,
        )
        self.assertFalse(is_safe, f"Expected swept volume collision with robot arm, but got safe: {reason}")

        # set_board_placement must reject with BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR
        res = self.sim.set_board_placement(forward_shift_mm=40.0)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR")

        # Restore robot to service safe pose after obstruction test
        self.sim.reset_robot()
        self.sim.runtime_go_service_safe()

    def test_12_swept_volume_collision_clear_path(self):
        """12. Swept-volume check passes and relocates cleanly when arm is at service safe pose."""
        self.sim.runtime_go_service_safe()
        self.assertTrue(self.sim.backend.is_service_safe())

        # When at service safe pose, relocating board by 10mm should be completely clear
        is_safe, reason = self.sim.world.check_board_swept_volume_collision(
            new_forward_shift_m=0.01,
            new_height_offset_m=0.0,
        )
        self.assertTrue(is_safe, f"Expected clear swept volume at service safe pose, but got: {reason}")

        res = self.sim.set_board_placement(forward_shift_mm=10.0)
        self.assertTrue(res["success"])
        self.assertEqual(self.sim.placement_state.forward_shift_mm, 10.0)

    def test_13_runtime_jog_tcp(self):
        """13. Cartesian jog along TCP axes with collision protection."""
        self.sim.runtime_go_service_safe()
        snap_before = self.sim.backend.get_state_snapshot()
        z_before = snap_before.tcp_pose_mm_deg[2]

        res = self.sim.runtime_jog_tcp(axis="+Z", step_mm=5.0)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "JOG_COMPLETE")

        snap_after = self.sim.backend.get_state_snapshot()
        z_after = snap_after.tcp_pose_mm_deg[2]
        self.assertAlmostEqual(z_after - z_before, 5.0, delta=1.0)

    def test_14_runtime_jog_joint(self):
        """14. Manual joint jog within soft limits."""
        self.sim.runtime_go_service_safe()
        snap_before = self.sim.backend.get_state_snapshot()
        j0_before = snap_before.joints_deg[0]

        res = self.sim.runtime_jog_joint(joint_idx=0, delta_deg=2.0)
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "JOG_COMPLETE")

        snap_after = self.sim.backend.get_state_snapshot()
        j0_after = snap_after.joints_deg[0]
        self.assertAlmostEqual(j0_after - j0_before, 2.0, delta=0.5)

    def test_15_granular_recovery_actions(self):
        """15. Granular reset and clear_error operations succeed independently."""
        # 1. clear_error
        self.sim.backend._last_error = "Test error"
        self.sim.clear_error()
        self.assertIsNone(self.sim.backend._last_error)

        # 2. reset_board
        self.sim.runtime_go_service_safe()
        self.sim.set_board_placement(forward_shift_mm=15.0)
        self.assertEqual(self.sim.placement_state.forward_shift_mm, 15.0)
        res_b = self.sim.reset_board()
        self.assertTrue(res_b["success"])
        self.assertEqual(self.sim.placement_state.forward_shift_mm, 0.0)

        # 3. reset_robot
        res_r = self.sim.reset_robot()
        self.assertTrue(res_r["success"])
        snap = self.sim.backend.get_state_snapshot()
        np.testing.assert_allclose(snap.joints_deg, self.sim.backend.home_joints_deg, atol=1.0)

        # 4. reset_pieces
        res_p = self.sim.reset_pieces()
        self.assertTrue(res_p["success"])
        self.assertIn(res_p["status"], ("PIECES_RESET", "PIECES_RESET_COMPLETE"))

    def test_16_ruler_single_authoritative_update(self):
        """16. ruler.mjs has exactly one authoritative updateBoardPlacement method."""
        ruler_path = _PROJECT_ROOT / "robot-3d-viewer" / "ruler.mjs"
        with open(ruler_path, "r", encoding="utf-8") as f:
            content = f.read()

        occurrences = content.count("group.updateBoardPlacement = ")
        self.assertEqual(
            occurrences,
            1,
            f"Expected exactly 1 definition of group.updateBoardPlacement in ruler.mjs, found {occurrences}",
        )

    def test_17_full_system_reset_in_process(self):
        """17. full_reset() restores complete system state without restarting Python process."""
        # Mutate system state: go service safe, change board placement, inject error
        self.sim.runtime_go_service_safe()
        self.sim.set_board_placement(forward_shift_mm=20.0)
        self.sim.backend._last_error = "Injected failure"

        res = self.sim.full_reset()
        self.assertTrue(res["success"])
        self.assertIn(res["status"], ("RESET_COMPLETE", "FULL_RESET_COMPLETE"))

        # Verify state is completely restored
        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)
        self.assertIsNone(self.sim.backend._last_error)
        self.assertEqual(self.sim.placement_state.forward_shift_mm, 0.0)
        self.assertEqual(self.sim.placement_state.board_height_offset_mm, 0.0)
        self.assertIsNone(self.sim.world.get_attached_piece())
        self.assertFalse(self.sim.backend.is_gripper_closed())

        snap = self.sim.backend.get_state_snapshot()
        np.testing.assert_allclose(snap.joints_deg, self.sim.backend.home_joints_deg, atol=1.0)


if __name__ == "__main__":
    unittest.main()
