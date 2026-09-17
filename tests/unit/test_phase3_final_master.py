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

import dataclasses
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest import mock
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.physics.state import (
    GraspStatus, GraspResult, PickResult, PlaceResult, PiecePhysicalState,
    ServiceSafetyReport, PayloadSafetyReport,
)
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.runtime import VirtualXiangqiSimulation, RuntimeOperationState, RuntimeOperationBusy
from src.simulation.virtual_fr3_backend import VirtualFR3Backend, SERVICE_SAFE_JOINTS_DEG
from src.simulation.placement import BoardPlacementState


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
        self.assertEqual(res["status"], "BOARD_ADJUSTMENT_READY")
        self.assertTrue(self.sim.is_board_adjustment_ready)
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
        self.sim.prepare_board_adjustment()
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
        self.sim.prepare_board_adjustment()
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
        self.sim.prepare_board_adjustment()
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

    def test_a1_move_joint_command_uses_runtime_authority(self):
        """A1: _handle_client_command(MOVE_JOINT) rejected when in VALIDATING_LOCAL, joints unchanged."""
        initial_q = list(self.sim.backend.get_state_snapshot().joints_deg)
        target_q = [val + 10.0 for val in initial_q]

        with self.sim.acquire_operation_state(RuntimeOperationState.VALIDATING_LOCAL):
            # Direct runtime wrapper rejection
            res = self.sim.runtime_move_joint(target_q)
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "MOTION_REJECTED_BUSY")

            # UI WebSocket command dispatch rejection
            self.sim._handle_client_command({"command": "MOVE_JOINT", "joints_deg": target_q})
            # Sleep briefly to ensure async thread ran
            time.sleep(0.05)

            # Joints must be completely unchanged
            current_q = list(self.sim.backend.get_state_snapshot().joints_deg)
            np.testing.assert_allclose(initial_q, current_q, atol=1e-3)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_a2_true_concurrent_acquisition(self):
        """A2: True concurrent acquisition with Barrier(2): exactly one succeeds, one gets RuntimeOperationBusy."""
        barrier = threading.Barrier(2)
        successes = []
        busies = []

        def _worker(thread_name: str):
            barrier.wait()
            try:
                with self.sim.acquire_operation_state(RuntimeOperationState.MOTION):
                    successes.append(thread_name)
                    time.sleep(0.05)
            except RuntimeOperationBusy:
                busies.append(thread_name)

        t1 = threading.Thread(target=_worker, args=("Thread-1",))
        t2 = threading.Thread(target=_worker, args=("Thread-2",))
        t1.start()
        t2.start()
        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        self.assertEqual(len(successes), 1, f"Expected exactly 1 success, got {successes}")
        self.assertEqual(len(busies), 1, f"Expected exactly 1 busy rejection, got {busies}")
        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)
        self.assertIsNone(self.sim.operation_owner)
        self.assertEqual(self.sim.operation_depth, 0)

    def test_a3_validation_vs_move_joint_race(self):
        """A3: Validator paused in VALIDATING_LOCAL rejects runtime_move_joint with MOTION_REJECTED_BUSY, resumes to IDLE."""
        entered_val = threading.Event()
        resume_val = threading.Event()

        def _val_task():
            with self.sim.acquire_operation_state(RuntimeOperationState.VALIDATING_LOCAL):
                entered_val.set()
                resume_val.wait(timeout=2.0)

        t = threading.Thread(target=_val_task)
        t.start()
        self.assertTrue(entered_val.wait(timeout=1.0))

        try:
            # While holding VALIDATING_LOCAL, runtime_move_joint must reject
            res = self.sim.runtime_move_joint(self.sim.backend.home_joints_deg)
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "MOTION_REJECTED_BUSY")
        finally:
            resume_val.set()
            t.join(timeout=2.0)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_a3_1_real_validator_rejects_move_joint_before_release(self):
        """A3.1: Real validate_board_placement() pauses via hook; runtime_move_joint rejects with MOTION_REJECTED_BUSY before release."""
        val_started = threading.Event()
        val_release = threading.Event()
        val_result = {}

        def _hook():
            val_started.set()
            val_release.wait(timeout=5.0)

        self.sim._test_hook_validation_owned = _hook
        try:
            def _run_val():
                val_result["res"] = self.sim.validate_board_placement(sample_limit=1)

            t_val = threading.Thread(target=_run_val)
            t_val.start()

            self.assertTrue(val_started.wait(timeout=2.0), "Validator did not start in time")
            self.assertEqual(self.sim.operation_state, RuntimeOperationState.VALIDATING_LOCAL)
            self.assertFalse(val_release.is_set(), "Release event must not be set yet")

            # Call runtime_move_joint while validator is paused in VALIDATING_LOCAL
            res_move = self.sim.runtime_move_joint(self.sim.backend.home_joints_deg)

            # Assert MoveJ returned BUSY BEFORE validation release
            self.assertFalse(val_release.is_set(), "MoveJ must return BEFORE validation release event is set")
            self.assertFalse(res_move["success"])
            self.assertEqual(res_move["status"], "MOTION_REJECTED_BUSY")
        finally:
            val_release.set()
            t_val.join(timeout=10.0)
            self.sim._test_hook_validation_owned = None

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)
        self.assertIsNone(self.sim.operation_owner)
        self.assertEqual(self.sim.operation_depth, 0)
        self.assertFalse(self.sim._validation_in_progress)

    def test_a3_2_timing_handshake_proof(self):
        """A3.2: Deterministic timing handshake proving MoveJ returns before validation release event is set."""
        val_holding = threading.Event()
        val_release = threading.Event()
        move_j_finished = threading.Event()
        order_log = []

        def _hook():
            order_log.append("validator_holding")
            val_holding.set()
            val_release.wait(timeout=5.0)
            order_log.append("validator_resumed")

        self.sim._test_hook_validation_owned = _hook
        try:
            t_val = threading.Thread(target=self.sim.validate_board_placement, kwargs={"sample_limit": 1})
            t_val.start()

            self.assertTrue(val_holding.wait(timeout=2.0))

            def _run_move():
                res = self.sim.runtime_move_joint(self.sim.backend.home_joints_deg)
                order_log.append(f"move_j_returned_{res['status']}")
                move_j_finished.set()

            t_move = threading.Thread(target=_run_move)
            t_move.start()

            self.assertTrue(move_j_finished.wait(timeout=2.0), "MoveJ thread did not finish")

            # Deterministic handshake assertion: MoveJ returned BEFORE validator was released!
            self.assertFalse(val_release.is_set(), "MoveJ must finish while validator is still holding state")
            order_log.append("releasing_validator")
            val_release.set()

            t_val.join(timeout=10.0)
            t_move.join(timeout=2.0)
        finally:
            val_release.set()
            self.sim._test_hook_validation_owned = None

        self.assertEqual(
            order_log,
            [
                "validator_holding",
                "move_j_returned_MOTION_REJECTED_BUSY",
                "releasing_validator",
                "validator_resumed",
            ],
        )
        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)
        self.assertIsNone(self.sim.operation_owner)
        self.assertEqual(self.sim.operation_depth, 0)

    def test_a3_3_full_route_validator_rejects_move_joint(self):
        """A3.3: Real validate_full_board_routes(sample_limit=1) pauses via hook; runtime_move_joint rejects before release."""
        route_holding = threading.Event()
        route_release = threading.Event()
        move_j_done = threading.Event()
        move_res = {}

        def _hook():
            route_holding.set()
            route_release.wait(timeout=5.0)

        self.sim._test_hook_routes_owned = _hook
        try:
            t_route = threading.Thread(target=self.sim.validate_full_board_routes, kwargs={"sample_limit": 1})
            t_route.start()

            self.assertTrue(route_holding.wait(timeout=2.0), "Route validator did not start")
            self.assertEqual(self.sim.operation_state, RuntimeOperationState.VALIDATING_ROUTES)

            def _run_move():
                move_res["result"] = self.sim.runtime_move_joint(self.sim.backend.home_joints_deg)
                move_j_done.set()

            t_move = threading.Thread(target=_run_move)
            t_move.start()
            self.assertTrue(move_j_done.wait(timeout=2.0), "MoveJ did not complete")

            # Check rejection occurred before route release
            self.assertFalse(route_release.is_set())
            self.assertFalse(move_res["result"]["success"])
            self.assertEqual(move_res["result"]["status"], "MOTION_REJECTED_BUSY")
        finally:
            route_release.set()
            t_route.join(timeout=10.0)
            self.sim._test_hook_routes_owned = None

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)
        self.assertIsNone(self.sim.operation_owner)
        self.assertEqual(self.sim.operation_depth, 0)
        self.assertFalse(self.sim._validation_in_progress)

    def test_lock_not_held_across_yield(self):
        """Verify _operation_lock is released while operation is in progress, allowing instant state inspection."""
        op_holding = threading.Event()
        op_release = threading.Event()

        def _long_op():
            with self.sim.acquire_operation_state(RuntimeOperationState.MOTION):
                op_holding.set()
                op_release.wait(timeout=5.0)

        t_op = threading.Thread(target=_long_op)
        t_op.start()
        self.assertTrue(op_holding.wait(timeout=2.0))

        try:
            # While MOTION is active, competing thread can acquire _operation_lock instantly without blocking
            t0 = time.perf_counter()
            acquired = self.sim._operation_lock.acquire(timeout=0.2)
            self.assertTrue(acquired, "_operation_lock should NOT be held while operation is active!")
            try:
                self.assertEqual(self.sim._operation_state, RuntimeOperationState.MOTION)
                self.assertEqual(self.sim._operation_depth, 1)
            finally:
                self.sim._operation_lock.release()
            elapsed = time.perf_counter() - t0
            self.assertLess(elapsed, 0.1, f"Lock acquisition took too long: {elapsed:.4f}s")
        finally:
            op_release.set()
            t_op.join(timeout=2.0)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)
        self.assertIsNone(self.sim.operation_owner)
        self.assertEqual(self.sim.operation_depth, 0)

    def test_a4_move_joint_owns_first(self):
        """A4: Active motion paused in MOTION rejects validate_board_placement without touching PyBullet q."""
        entered_motion = threading.Event()
        resume_motion = threading.Event()

        def _mock_move(q, speed_factor=None):
            entered_motion.set()
            resume_motion.wait(timeout=2.0)
            return True

        q_bullet_before = self.sim.world.get_robot_joint_positions()

        with mock.patch.object(self.sim.backend, "move_joint", side_effect=_mock_move):
            t = threading.Thread(target=self.sim.runtime_move_joint, args=(self.sim.backend.home_joints_deg,))
            t.start()
            self.assertTrue(entered_motion.wait(timeout=1.0))

            try:
                # Validation must be rejected atomically
                res_val = self.sim.validate_board_placement()
                self.assertFalse(res_val["success"])
                self.assertEqual(res_val["status"], "VALIDATION_REJECTED_BUSY")

                # Verify PyBullet configuration was NOT altered
                q_bullet_after = self.sim.world.get_robot_joint_positions()
                np.testing.assert_allclose(q_bullet_before, q_bullet_after, atol=1e-5)
            finally:
                resume_motion.set()
                t.join(timeout=2.0)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_a5_validation_flag_consistency(self):
        """A5: _validation_in_progress is True during validation states and False when IDLE."""
        self.assertFalse(self.sim._validation_in_progress)
        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

        with self.sim.acquire_operation_state(RuntimeOperationState.VALIDATING_LOCAL):
            self.assertTrue(self.sim._validation_in_progress)
            self.assertEqual(self.sim.operation_state, RuntimeOperationState.VALIDATING_LOCAL)

        self.assertFalse(self.sim._validation_in_progress)
        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

        with self.sim.acquire_operation_state(RuntimeOperationState.VALIDATING_ROUTES):
            self.assertTrue(self.sim._validation_in_progress)
            self.assertEqual(self.sim.operation_state, RuntimeOperationState.VALIDATING_ROUTES)

        self.assertFalse(self.sim._validation_in_progress)
        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_a6_exception_cleanup(self):
        """A6: Exception inside runtime_move_joint cleanly restores state to IDLE and permits subsequent motion."""
        with mock.patch.object(self.sim.backend, "move_joint", side_effect=RuntimeError("Simulated motor fault")):
            res = self.sim.runtime_move_joint([10.0, 10.0, 10.0, 10.0, 10.0, 10.0])
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "MOVE_FAILED")

        # State must be cleanly restored to IDLE
        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

        # Subsequent operation must succeed cleanly
        res_subsequent = self.sim.runtime_move_joint(self.sim.backend.home_joints_deg)
        self.assertTrue(res_subsequent["success"])
        self.assertEqual(res_subsequent["status"], "SUCCESS")
        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_a6_nested_exception_cleanup(self):
        """A6.2: Exception inside nested acquisition cleanly restores state to IDLE, owner=None, depth=0."""
        # Test 1: Exception in nested acquire of same target state
        try:
            with self.sim.acquire_operation_state(RuntimeOperationState.VALIDATING_LOCAL):
                self.assertEqual(self.sim.operation_depth, 1)
                with self.sim.acquire_operation_state(RuntimeOperationState.VALIDATING_LOCAL):
                    self.assertEqual(self.sim.operation_depth, 2)
                    raise RuntimeError("Simulated nested failure")
        except RuntimeError:
            pass

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)
        self.assertIsNone(self.sim.operation_owner)
        self.assertEqual(self.sim.operation_depth, 0)
        self.assertFalse(self.sim._validation_in_progress)

        # Test 2: Exception in nested acquire of RESETTING
        try:
            with self.sim.acquire_operation_state(RuntimeOperationState.RESETTING):
                self.assertEqual(self.sim.operation_depth, 1)
                with self.sim.acquire_operation_state(RuntimeOperationState.BOARD_ADJUSTMENT):
                    self.assertEqual(self.sim.operation_depth, 2)
                    raise ValueError("Simulated nested reset failure")
        except ValueError:
            pass

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)
        self.assertIsNone(self.sim.operation_owner)
        self.assertEqual(self.sim.operation_depth, 0)

    def test_a7_service_jog_vs_validation(self):
        """A7: While in VALIDATING_LOCAL, runtime_jog_tcp and runtime_jog_joint reject with BUSY and mutate nothing."""
        with self.sim.acquire_operation_state(RuntimeOperationState.VALIDATING_LOCAL):
            snap_before = self.sim.backend.get_state_snapshot()
            tcp_before = list(snap_before.tcp_pose_mm_deg)
            joints_before = list(snap_before.joints_deg)

            res_tcp = self.sim.runtime_jog_tcp(axis="+Z", step_mm=10.0)
            self.assertFalse(res_tcp["success"])
            self.assertEqual(res_tcp["status"], "MOTION_REJECTED_BUSY")

            res_joint = self.sim.runtime_jog_joint(joint_idx=0, delta_deg=10.0)
            self.assertFalse(res_joint["success"])
            self.assertEqual(res_joint["status"], "MOTION_REJECTED_BUSY")

            snap_after = self.sim.backend.get_state_snapshot()
            tcp_after = list(snap_after.tcp_pose_mm_deg)
            joints_after = list(snap_after.joints_deg)

            np.testing.assert_allclose(tcp_before, tcp_after, atol=1e-5)
            np.testing.assert_allclose(joints_before, joints_after, atol=1e-5)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_a2_1_move_joint_vs_move_joint_no_queue(self):
        """A2.1: Competing MoveJ returns MOTION_REJECTED_BUSY immediately without waiting on _command_lock."""
        target_a = [10.0, -20.0, 30.0, -40.0, -90.0, 0.0]
        target_b = [-10.0, -10.0, 20.0, -30.0, -90.0, 10.0]

        motion_a_started = threading.Event()
        motion_a_release = threading.Event()

        orig_move_joint = self.sim.backend.move_joint

        def blocking_move_joint(*args, **kwargs):
            motion_a_started.set()
            motion_a_release.wait(timeout=5.0)
            return orig_move_joint(*args, **kwargs)

        with mock.patch.object(self.sim.backend, "move_joint", side_effect=blocking_move_joint):
            t_a = threading.Thread(target=self.sim.runtime_move_joint, args=(target_a,), daemon=True)
            t_a.start()

            self.assertTrue(motion_a_started.wait(timeout=2.0))
            self.assertEqual(self.sim.operation_state, RuntimeOperationState.MOTION)

            # Thread B calls runtime_move_joint while Thread A holds MOTION and _command_lock
            res_b = self.sim.runtime_move_joint(target_b)

            # Thread B must have returned immediately BEFORE motion_a_release was set
            self.assertFalse(res_b["success"])
            self.assertEqual(res_b["status"], "MOTION_REJECTED_BUSY")
            self.assertFalse(motion_a_release.is_set(), "Queueing occurred: Thread B waited for Thread A completion!")

            # Release Thread A
            motion_a_release.set()
            t_a.join(timeout=3.0)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)
        self.assertIsNone(self.sim.operation_owner)
        self.assertEqual(self.sim.operation_depth, 0)

    def test_a2_2_timing_handshake_proof(self):
        """A2.2: Deterministic event handshake proving Thread B returns before Thread A release."""
        motion_a_started = threading.Event()
        motion_a_release = threading.Event()
        motion_b_returned = threading.Event()
        result_b = {}

        orig_move_joint = self.sim.backend.move_joint

        def blocking_move_joint(*args, **kwargs):
            motion_a_started.set()
            motion_a_release.wait(timeout=5.0)
            return orig_move_joint(*args, **kwargs)

        with mock.patch.object(self.sim.backend, "move_joint", side_effect=blocking_move_joint):
            t_a = threading.Thread(target=self.sim.runtime_move_joint, args=([0.0, -10.0, 10.0, -20.0, -90.0, 0.0],), daemon=True)
            t_a.start()

            self.assertTrue(motion_a_started.wait(timeout=2.0))

            def run_b():
                res = self.sim.runtime_move_joint([5.0, 5.0, 5.0, 5.0, -90.0, 0.0])
                result_b.update(res)
                motion_b_returned.set()

            t_b = threading.Thread(target=run_b, daemon=True)
            t_b.start()

            self.assertTrue(motion_b_returned.wait(timeout=2.0), "Thread B timed out waiting to return!")
            self.assertFalse(result_b.get("success", True))
            self.assertEqual(result_b.get("status"), "MOTION_REJECTED_BUSY")
            self.assertFalse(motion_a_release.is_set(), "Thread B returned only after Thread A released!")

            motion_a_release.set()
            t_a.join(timeout=3.0)
            t_b.join(timeout=1.0)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_a2_3_move_joint_vs_jog(self):
        """A2.3: While MoveJ owns MOTION, runtime_jog_joint and runtime_jog_tcp return MOTION_REJECTED_BUSY immediately."""
        motion_started = threading.Event()
        motion_release = threading.Event()

        orig_move_joint = self.sim.backend.move_joint

        def blocking_move_joint(*args, **kwargs):
            motion_started.set()
            motion_release.wait(timeout=5.0)
            return orig_move_joint(*args, **kwargs)

        with mock.patch.object(self.sim.backend, "move_joint", side_effect=blocking_move_joint):
            t = threading.Thread(target=self.sim.runtime_move_joint, args=([10.0, -20.0, 30.0, -40.0, -90.0, 0.0],), daemon=True)
            t.start()

            self.assertTrue(motion_started.wait(timeout=2.0))
            snap_before = self.sim.backend.get_state_snapshot()

            res_jog_j = self.sim.runtime_jog_joint(joint_idx=0, delta_deg=5.0)
            self.assertFalse(res_jog_j["success"])
            self.assertEqual(res_jog_j["status"], "MOTION_REJECTED_BUSY")

            res_jog_tcp = self.sim.runtime_jog_tcp(axis="+Z", step_mm=10.0)
            self.assertFalse(res_jog_tcp["success"])
            self.assertEqual(res_jog_tcp["status"], "MOTION_REJECTED_BUSY")

            self.assertFalse(motion_release.is_set())

            snap_after = self.sim.backend.get_state_snapshot()
            np.testing.assert_allclose(snap_before.joints_deg, snap_after.joints_deg, atol=1e-4)

            motion_release.set()
            t.join(timeout=3.0)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_a2_4_service_move_vs_move_joint(self):
        """A2.4: While SERVICE_MOVE is active, runtime_move_joint returns MOTION_REJECTED_BUSY immediately."""
        jog_started = threading.Event()
        jog_release = threading.Event()

        orig_jog = self.sim.backend.jog_joint

        def blocking_jog(*args, **kwargs):
            jog_started.set()
            jog_release.wait(timeout=5.0)
            return orig_jog(*args, **kwargs)

        with mock.patch.object(self.sim.backend, "jog_joint", side_effect=blocking_jog):
            t = threading.Thread(target=self.sim.runtime_jog_joint, kwargs={"joint_idx": 0, "delta_deg": 2.0}, daemon=True)
            t.start()

            self.assertTrue(jog_started.wait(timeout=2.0))
            self.assertEqual(self.sim.operation_state, RuntimeOperationState.SERVICE_MOVE)

            res_move = self.sim.runtime_move_joint([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            self.assertFalse(res_move["success"])
            self.assertEqual(res_move["status"], "MOTION_REJECTED_BUSY")
            self.assertFalse(jog_release.is_set())

            jog_release.set()
            t.join(timeout=3.0)

        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_a2_5_pick_vs_move_joint(self):
        """A2.5: While pick_piece owns MOTION, runtime_move_joint returns MOTION_REJECTED_BUSY immediately."""
        pick_started = threading.Event()
        pick_release = threading.Event()

        def on_motion_owned():
            pick_started.set()
            pick_release.wait(timeout=5.0)

        self.sim._test_hook_motion_owned = on_motion_owned

        with mock.patch.object(self.sim.backend, "move_joint_with_lift_recovery", return_value=True):
            with mock.patch.object(self.sim.backend, "move_cartesian", return_value=True):
                with mock.patch.object(self.sim.world, "try_grasp", return_value=True):
                    piece_id = next(iter(self.sim.world.pieces.keys()))
                    t = threading.Thread(target=self.sim.pick_piece, args=(piece_id,), daemon=True)
                    t.start()

                    self.assertTrue(pick_started.wait(timeout=2.0))
                    self.assertEqual(self.sim.operation_state, RuntimeOperationState.MOTION)

                    res_move = self.sim.runtime_move_joint([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
                    self.assertFalse(res_move["success"])
                    self.assertEqual(res_move["status"], "MOTION_REJECTED_BUSY")
                    self.assertFalse(pick_release.is_set())

                    pick_release.set()
                    t.join(timeout=3.0)

        self.sim.backend.open_gripper()
        self.sim.world.release_attached_piece()
        self.sim._test_hook_motion_owned = None
        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_a2_6_place_vs_jog(self):
        """A2.6: While place_piece owns MOTION, runtime_jog_tcp returns MOTION_REJECTED_BUSY immediately."""
        place_started = threading.Event()
        place_release = threading.Event()

        def on_motion_owned():
            place_started.set()
            place_release.wait(timeout=5.0)

        self.sim._test_hook_motion_owned = on_motion_owned

        with mock.patch.object(self.sim.backend, "move_joint_with_lift_recovery", return_value=True):
            with mock.patch.object(self.sim.backend, "move_cartesian", return_value=True):
                t = threading.Thread(target=self.sim.place_piece, kwargs={"col": 0, "row": 0}, daemon=True)
                t.start()

                self.assertTrue(place_started.wait(timeout=2.0))
                self.assertEqual(self.sim.operation_state, RuntimeOperationState.MOTION)

                res_jog = self.sim.runtime_jog_tcp(axis="+X", step_mm=5.0)
                self.assertFalse(res_jog["success"])
                self.assertEqual(res_jog["status"], "MOTION_REJECTED_BUSY")
                self.assertFalse(place_release.is_set())

                place_release.set()
                t.join(timeout=3.0)

        self.sim._test_hook_motion_owned = None
        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    def test_a2_7_3stage_trajectory_vs_move_joint(self):
        """A2.7: While execute_3stage_trajectory owns MOTION, runtime_move_joint returns MOTION_REJECTED_BUSY immediately."""
        traj_started = threading.Event()
        traj_release = threading.Event()

        def on_motion_owned():
            traj_started.set()
            traj_release.wait(timeout=5.0)

        self.sim._test_hook_motion_owned = on_motion_owned

        with mock.patch.object(self.sim, "_execute_3stage_trajectory_impl", return_value={"success": True, "status": "SUCCESS"}):
            t = threading.Thread(target=self.sim.execute_3stage_trajectory, args=((0, 0), (0, 1)), daemon=True)
            t.start()

            self.assertTrue(traj_started.wait(timeout=2.0))
            self.assertEqual(self.sim.operation_state, RuntimeOperationState.MOTION)

            res_move = self.sim.runtime_move_joint([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
            self.assertFalse(res_move["success"])
            self.assertEqual(res_move["status"], "MOTION_REJECTED_BUSY")
            self.assertFalse(traj_release.is_set())

            traj_release.set()
            t.join(timeout=3.0)

        self.sim._test_hook_motion_owned = None
        self.assertEqual(self.sim.operation_state, RuntimeOperationState.IDLE)

    # ======================================================================
    # Pass B: SERVICE_SAFE Physical Predicate & Board Adjustment Safety Tests
    # ======================================================================

    def test_b1_service_safe_physical_predicate_clear(self):
        """b1. Full physical predicate passes when arm is safely parked at SERVICE_SAFE."""
        res = self.sim.runtime_go_service_safe()
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "SERVICE_SAFE_REACHED")

        rep = self.sim.evaluate_service_safety()
        self.assertTrue(rep.service_safe)
        self.assertTrue(rep.robot_connected)
        self.assertTrue(rep.robot_idle)
        self.assertTrue(rep.trajectory_idle)
        self.assertTrue(rep.gripper_open)
        self.assertFalse(rep.piece_attached)
        self.assertTrue(rep.links_clear)
        self.assertTrue(rep.gripper_clear)
        self.assertGreaterEqual(rep.min_board_clearance_mm, 50.0)
        self.assertGreaterEqual(rep.min_joint_margin_deg, 5.0)
        self.assertLess(rep.condition_number, 100.0)
        self.assertEqual(len(rep.reasons), 0)
        self.assertTrue(self.sim.is_service_safe())

    def test_b2_service_safe_rejected_gripper_closed(self):
        """b2. Closed gripper (even without piece) rejects service_safe physical predicate."""
        self.sim.runtime_go_service_safe()
        self.sim.backend.set_gripper(True)
        try:
            rep = self.sim.evaluate_service_safety()
            self.assertFalse(rep.service_safe)
            self.assertFalse(rep.gripper_open)
            self.assertTrue(any("gripper" in r.lower() for r in rep.reasons))
            self.assertFalse(self.sim.is_service_safe())
        finally:
            self.sim.backend.set_gripper(False)

    def test_b3_service_safe_rejected_piece_attached(self):
        """b3. Attached piece rejects service_safe and runtime_go_service_safe."""
        self.sim.runtime_go_service_safe()
        # Simulate piece attached to gripper
        piece = next(iter(self.sim.world.pieces.values()))
        self.sim.world.gripper.attached_piece = piece
        self.sim.backend._attached_piece_id = piece.piece_id
        try:
            rep = self.sim.evaluate_service_safety()
            self.assertFalse(rep.service_safe)
            self.assertTrue(rep.piece_attached)
            self.assertTrue(any("piece" in r.lower() for r in rep.reasons))
            self.assertFalse(self.sim.is_service_safe())

            res = self.sim.runtime_go_service_safe()
            self.assertFalse(res["success"])
            self.assertEqual(res["status"], "SERVICE_SAFE_REJECTED_PIECE_ATTACHED")
        finally:
            self.sim.world.gripper.attached_piece = None
            self.sim.backend._attached_piece_id = None

    def test_b4_service_safe_rejected_robot_moving(self):
        """b4. MOVING robot state rejects service_safe physical predicate."""
        self.sim.runtime_go_service_safe()
        orig_motion = self.sim.backend._motion_state
        self.sim.backend._motion_state = "MOVING"
        try:
            rep = self.sim.evaluate_service_safety()
            self.assertFalse(rep.service_safe)
            self.assertFalse(rep.robot_idle)
            self.assertTrue(any("moving" in r.lower() for r in rep.reasons))
            self.assertFalse(self.sim.is_service_safe())
        finally:
            self.sim.backend._motion_state = orig_motion

    def test_b5_home_is_not_service_safe(self):
        """b5. Candidate 2 (HOME pose) is physically distinct and rejected as SERVICE_SAFE."""
        # Move to nominal HOME [0, -45, 90, -45, -90, 0]
        self.sim.runtime_move_joint([0.0, -45.0, 90.0, -45.0, -90.0, 0.0])
        rep = self.sim.evaluate_service_safety()
        self.assertFalse(rep.service_safe)
        self.assertFalse(rep.service_pose_match)
        self.assertFalse(self.sim.is_service_safe())
        # Restore to SERVICE_SAFE
        self.sim.runtime_go_service_safe()

    def test_b6_vertical_board_raise_rejected_when_arm_low(self):
        """b6. Vertical board raise (+25mm) rejected when arm is in low workspace."""
        # Lower arm to grasp level near board
        r, c = 0, 4
        z_grasp = self.sim.board_surface_z
        grasp_m = self.sim.cell_to_robot_xyz_m(r, c, z_grasp)
        grasp_pose_mm = [grasp_m[0] * 1000.0, grasp_m[1] * 1000.0, grasp_m[2] * 1000.0, 180.0, 0.0, 90.0]
        ik = self.sim.backend.solve_tcp_ik(grasp_pose_mm, allow_multi_seed=True)
        if ik.success:
            self.sim.backend.move_joint(np.degrees(ik.joints_rad).tolist())
            self.sim.world.sync_robot_runtime_configuration(ik.joints_rad)

        orig_z_offset = self.sim.placement_state.board_height_offset_mm
        orig_version = self.sim.placement_state.placement_version

        swept_res = self.sim.world.check_board_swept_volume_collision(
            new_forward_shift_m=0.0,
            new_height_offset_m=0.025,
        )
        self.assertFalse(swept_res.is_safe)

        res = self.sim.set_board_placement(board_height_offset_mm=25.0)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR")

        # 100% state invariance check
        self.assertEqual(self.sim.placement_state.board_height_offset_mm, orig_z_offset)
        self.assertEqual(self.sim.placement_state.placement_version, orig_version)
        self.assertEqual(self.sim.backend.placement_version, orig_version)

        # Restore
        self.sim.reset_robot()
        self.sim.runtime_go_service_safe()

    def test_b7_board_lowering_swept_path(self):
        """b7. Board lowering (-10mm) swept path is completely clear from SERVICE_SAFE."""
        self.sim.prepare_board_adjustment()
        swept_res = self.sim.world.check_board_swept_volume_collision(
            new_forward_shift_m=0.0,
            new_height_offset_m=-0.010,
        )
        self.assertTrue(swept_res.is_safe, f"Board lowering swept check failed: {swept_res.reason}")

        res = self.sim.set_board_placement(board_height_offset_mm=-10.0)
        self.assertTrue(res["success"])
        self.assertEqual(self.sim.placement_state.board_height_offset_mm, -10.0)
        self.sim.reset_board_placement()

    def test_b8_forward_and_backward_shift_swept_path(self):
        """b8. Pure forward (+40mm) and backward (-20mm) translations pass cleanly from SERVICE_SAFE."""
        self.sim.prepare_board_adjustment()

        # Forward shift +40mm
        res_fwd = self.sim.set_board_placement(forward_shift_mm=40.0)
        self.assertTrue(res_fwd["success"])
        self.assertEqual(self.sim.placement_state.forward_shift_mm, 40.0)

        # Backward shift -20mm (prepare new one-shot token)
        self.sim.prepare_board_adjustment()
        res_bwd = self.sim.set_board_placement(forward_shift_mm=-20.0)
        self.assertTrue(res_bwd["success"])
        self.assertEqual(self.sim.placement_state.forward_shift_mm, -20.0)

        self.sim.reset_board_placement()

    def test_b9_combined_diagonal_swept_path(self):
        """b9. Combined forward (+30mm) and raise (+20mm) diagonal path passes at SERVICE_SAFE."""
        self.sim.prepare_board_adjustment()
        swept_res = self.sim.world.check_board_swept_volume_collision(
            new_forward_shift_m=0.030,
            new_height_offset_m=0.020,
        )
        self.assertTrue(swept_res.is_safe, f"Combined diagonal swept check failed: {swept_res.reason}")

        res = self.sim.set_board_placement(forward_shift_mm=30.0, board_height_offset_mm=20.0)
        self.assertTrue(res["success"])
        self.assertEqual(self.sim.placement_state.forward_shift_mm, 30.0)
        self.assertEqual(self.sim.placement_state.board_height_offset_mm, 20.0)

        self.sim.reset_board_placement()

    def test_b10_prepare_board_adjustment_strict_flow(self):
        """b10. Strict prepare_board_adjustment flow grants readiness and resets it on relocation."""
        res = self.sim.prepare_board_adjustment()
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "BOARD_ADJUSTMENT_READY")
        self.assertTrue(self.sim.is_board_adjustment_ready)
        self.assertTrue(self.sim.backend.is_service_safe())

        # Perform relocation
        res_reloc = self.sim.set_board_placement(forward_shift_mm=15.0)
        self.assertTrue(res_reloc["success"])

        # Token consumed
        self.assertFalse(self.sim.is_board_adjustment_ready)

        self.sim.reset_board_placement()

    def test_b11_jog_invalidates_service_safe(self):
        """b11. Jogging joint or TCP invalidates board adjustment readiness."""
        self.sim.prepare_board_adjustment()
        self.assertTrue(self.sim.is_board_adjustment_ready)

        # Jog joint 0 slightly
        res_jog = self.sim.runtime_jog_joint(0, 5.0)
        self.assertTrue(res_jog["success"])
        self.assertFalse(self.sim.is_board_adjustment_ready)

        # Restore
        self.sim.runtime_go_service_safe()

    # -------------------------------------------------------------------------
    # PASS B CORRECTIVE TEST MATRIX (B-C1 to B-C12)
    # -------------------------------------------------------------------------

    def test_bc1_disconnected_backend_rejects_service_safe(self):
        """B-C1. Disconnected backend evaluates robot_connected=False and service_safe=False."""
        self.sim.runtime_go_service_safe()
        try:
            self.sim.backend.disconnect()
            self.assertFalse(self.sim.backend.is_connected())
            rep = self.sim.evaluate_service_safety()
            self.assertFalse(rep.robot_connected)
            self.assertFalse(rep.service_safe)
            self.assertIn("SERVICE_UNSAFE_NOT_CONNECTED", rep.reasons)
        finally:
            self.sim.backend.connect()
            self.sim.runtime_go_service_safe()

    def test_bc2_backend_is_service_safe_rejects_disconnected(self):
        """B-C2. VirtualFR3Backend.is_service_safe() properly rejects disconnected state."""
        self.sim.backend.go_service_safe()
        self.assertTrue(self.sim.backend.is_service_safe())
        try:
            self.sim.backend.disconnect()
            self.assertFalse(self.sim.backend.is_connected())
            self.assertFalse(self.sim.backend.is_service_safe())
        finally:
            self.sim.backend.connect()
            self.sim.backend.go_service_safe()

    def test_bc3_settling_invalidates_service_safe(self):
        """B-C3. SETTLING piece physical state invalidates ServiceSafetyReport."""
        self.sim.runtime_go_service_safe()
        rep_before = self.sim.evaluate_service_safety()
        self.assertTrue(rep_before.service_safe)

        piece = next(iter(self.sim.world.pieces.values()))
        orig_state = piece.physical_state
        piece.physical_state = PiecePhysicalState.SETTLING
        try:
            rep_after = self.sim.evaluate_service_safety()
            self.assertFalse(rep_after.service_safe)
            self.assertIn("SERVICE_UNSAFE_WORLD_NOT_SETTLED", rep_after.reasons)
            self.assertFalse(self.sim.is_service_safe())
        finally:
            piece.physical_state = orig_state

    def test_bc4_settling_invalidates_board_readiness(self):
        """B-C4. SETTLING piece invalidates live is_board_adjustment_ready property."""
        res = self.sim.prepare_board_adjustment()
        self.assertTrue(res["success"])
        self.assertTrue(self.sim.is_board_adjustment_ready)

        piece = next(iter(self.sim.world.pieces.values()))
        orig_state = piece.physical_state
        piece.physical_state = PiecePhysicalState.SETTLING
        try:
            self.assertFalse(self.sim.is_board_adjustment_ready)
            self.assertFalse(self.sim.evaluate_service_safety().service_safe)
        finally:
            piece.physical_state = orig_state

    def test_bc5_direct_relocation_without_prepare_rejected(self):
        """B-C5. set_board_placement() directly without PREPARE_BOARD_ADJUSTMENT is rejected."""
        self.sim.runtime_go_service_safe()
        self.sim._board_adjustment_ready = False

        res = self.sim.set_board_placement(forward_shift_mm=10.0)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "BOARD_RELOCATION_REJECTED_NOT_READY")

    def test_bc6_stale_readiness_token_with_unsafe_robot_rejected(self):
        """B-C6. Stale readiness token + unsafe robot state is rejected with 100% state invariance."""
        self.sim.prepare_board_adjustment()
        self.assertTrue(self.sim._board_adjustment_ready)

        # Mutate robot state: close gripper
        self.sim.backend.close_gripper()
        self.assertFalse(self.sim.evaluate_service_safety().service_safe)

        # Record authoritative state before relocation attempt
        orig_pos, orig_orn = self.sim.world.get_board_pose()
        orig_placement_state = self.sim.placement_state
        orig_version = self.sim.placement_state.placement_version
        orig_joints = list(self.sim.backend.get_state_snapshot().joints_deg)

        res = self.sim.set_board_placement(forward_shift_mm=10.0)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "BOARD_RELOCATION_REJECTED_SERVICE_UNSAFE")
        self.assertFalse(self.sim._board_adjustment_ready)  # Token invalidated!

        # Verify 100% state invariance
        new_pos, new_orn = self.sim.world.get_board_pose()
        np.testing.assert_allclose(orig_pos, new_pos, atol=1e-5)
        np.testing.assert_allclose(orig_orn, new_orn, atol=1e-5)
        self.assertEqual(self.sim.placement_state, orig_placement_state)
        self.assertEqual(self.sim.placement_state.placement_version, orig_version)
        self.assertEqual(self.sim.backend.placement_version, orig_version)
        np.testing.assert_allclose(orig_joints, self.sim.backend.get_state_snapshot().joints_deg, atol=1e-5)

        # Restore
        self.sim.backend.open_gripper()
        self.sim.runtime_go_service_safe()

    def test_bc7_negative_board_lowering_into_arm_rejected(self):
        """B-C7. Real PyBullet swept volume collision: initial clearance > 5mm, collides at step k > 0 on lowering."""
        # Drive robot to fixture pose where gripper proxy is initially clear of board by > 5mm,
        # but negative lowering (-10mm) sweeps into the gripper body at step k > 0
        q_fixture = [0.0, -60.0, 125.0, -135.0, -90.0, 0.0]
        self.sim.backend.move_joint(q_fixture)
        self.sim.world.sync_robot_runtime_configuration(np.radians(q_fixture))

        # 1. Verify initial clearance strictly exceeds safety margin (> 5.0 mm)
        init_dist_m, closest_body = self.sim.world.get_board_to_robot_clearance()
        self.assertGreater(init_dist_m, 0.005, f"Expected initial clearance > 5mm, got {init_dist_m * 1000.0:.2f}mm")
        self.assertGreaterEqual(init_dist_m * 1000.0, 7.0)

        # 2. Check swept volume collision: must detect collision during sweep at step > 0
        swept_res = self.sim.world.check_board_swept_volume_collision(
            new_forward_shift_m=0.0,
            new_height_offset_m=-0.010,
        )
        self.assertFalse(swept_res.is_safe, f"Expected swept lowering collision, got safe: {swept_res.reason}")
        self.assertGreater(swept_res.details["first_blocking_step"], 0, f"Collision must occur at step > 0, got {swept_res.details}")
        self.assertLessEqual(swept_res.details["minimum_clearance_mm"], 5.0)

        # 3. set_board_placement must reject with BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR and preserve diagnostics
        res = self.sim.set_board_placement(board_height_offset_mm=-10.0)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR")
        self.assertGreater(res["details"]["first_blocking_step"], 0)

        # Restore
        self.sim.reset_robot()
        self.sim.runtime_go_service_safe()

    def test_bc8_rejected_lowering_preserves_full_authoritative_state(self):
        """B-C8. Rejected lowering (with d_initial > 5mm, k > 0 collision) preserves 100% PyBullet state."""
        q_fixture = [0.0, -60.0, 125.0, -135.0, -90.0, 0.0]
        self.sim.backend.move_joint(q_fixture)
        self.sim.world.sync_robot_runtime_configuration(np.radians(q_fixture))

        # Initial clearance must be clear (> 5mm)
        init_dist_m, _ = self.sim.world.get_board_to_robot_clearance()
        self.assertGreater(init_dist_m, 0.005)

        orig_board_pos, orig_board_orn = self.sim.world.get_board_pose()
        orig_state = self.sim.placement_state
        orig_version = self.sim.placement_state.placement_version
        orig_joints = list(self.sim.backend.get_state_snapshot().joints_deg)
        orig_piece_poses = {pid: p.get_pose_robot_base() for pid, p in self.sim.world.pieces.items()}

        res = self.sim.set_board_placement(board_height_offset_mm=-10.0)
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR")
        self.assertGreater(res["details"]["first_blocking_step"], 0)

        new_board_pos, new_board_orn = self.sim.world.get_board_pose()
        np.testing.assert_allclose(orig_board_pos, new_board_pos, atol=1e-5)
        np.testing.assert_allclose(orig_board_orn, new_board_orn, atol=1e-5)
        self.assertEqual(self.sim.placement_state, orig_state)
        self.assertEqual(self.sim.placement_state.placement_version, orig_version)
        self.assertEqual(self.sim.backend.placement_version, orig_version)
        np.testing.assert_allclose(orig_joints, self.sim.backend.get_state_snapshot().joints_deg, atol=1e-5)
        for pid, p in self.sim.world.pieces.items():
            pos, orn = p.get_pose_robot_base()
            np.testing.assert_allclose(orig_piece_poses[pid][0], pos, atol=1e-4)

        # Restore
        self.sim.reset_robot()
        self.sim.runtime_go_service_safe()

    def test_bc9_service_exclusion_detects_link_inside_region(self):
        """B-C9. Service exclusion volume detects robot link inside even when TCP is outside."""
        # Pose [0, -45, 90, -60, 135, -90] angles wrist upward so TCP is > 100mm high, well above
        # the service exclusion ceiling (70mm), while link 4/5 encroaches the exclusion volume.
        q_link_inside = [0.0, -45.0, 90.0, -60.0, 135.0, -90.0]
        self.sim.runtime_move_joint(q_link_inside)

        snap = self.sim.backend.get_state_snapshot()
        tcp_z_m = snap.tcp_pose_mm_deg[2] / 1000.0
        z_max_excl = self.sim.placement_state.board_surface_z_robot_m + (self.sim.geom.piece.height / 1000.0) + self.sim.DEFAULT_SERVICE_VERTICAL_CLEARANCE_M
        # Assert TCP is explicitly outside (above) the exclusion volume ceiling
        self.assertGreater(tcp_z_m, z_max_excl, f"TCP (z={tcp_z_m:.3f}m) should be above exclusion ceiling (z={z_max_excl:.3f}m)")

        rep = self.sim.evaluate_service_safety()
        self.assertFalse(rep.service_safe)
        self.assertFalse(rep.links_clear)
        self.assertIn("SERVICE_UNSAFE_LINK_OVER_BOARD", rep.reasons)

        self.sim.runtime_go_service_safe()

    def test_bc10_service_exclusion_detects_gripper_proxy(self):
        """B-C10. Service exclusion volume detects gripper proxy occupancy."""
        # Place TCP at low pose where gripper proxy penetrates exclusion volume
        r, c = 0, 4
        z_grasp = self.sim.board_surface_z
        grasp_m = self.sim.cell_to_robot_xyz_m(r, c, z_grasp)
        grasp_pose_mm = [grasp_m[0] * 1000.0, grasp_m[1] * 1000.0, grasp_m[2] * 1000.0, 180.0, 0.0, 90.0]
        ik = self.sim.backend.solve_tcp_ik(grasp_pose_mm, allow_multi_seed=True)
        if ik.success:
            self.sim.backend.move_joint(np.degrees(ik.joints_rad).tolist())
            self.sim.world.sync_robot_runtime_configuration(ik.joints_rad)

        rep = self.sim.evaluate_service_safety()
        self.assertFalse(rep.service_safe)
        self.assertFalse(rep.gripper_clear)
        self.assertIn("SERVICE_UNSAFE_GRIPPER_OVER_BOARD", rep.reasons)

        self.sim.runtime_go_service_safe()

    def test_bc11_authoritative_service_safe_candidate_passes_corrected_predicate(self):
        """B-C11. Authoritative candidate [0, -70, 60, -80, -90, 0] passes corrected predicate with high clearance."""
        self.sim.runtime_go_service_safe()
        rep = self.sim.evaluate_service_safety()

        self.assertTrue(rep.service_safe)
        self.assertEqual(len(rep.reasons), 0)
        self.assertTrue(rep.robot_connected)
        self.assertTrue(rep.robot_idle)
        self.assertTrue(rep.trajectory_idle)
        self.assertTrue(rep.gripper_open)
        self.assertFalse(rep.piece_attached)
        self.assertTrue(rep.links_clear)
        self.assertTrue(rep.gripper_clear)
        self.assertGreaterEqual(rep.min_board_clearance_mm, 50.0)
        self.assertGreaterEqual(rep.min_joint_margin_deg, 10.0)
        self.assertLessEqual(rep.condition_number, 50.0)
        self.assertTrue(rep.service_pose_match)
        self.assertTrue(self.sim.is_service_safe())

    def test_bc12_supported_envelope_boundary_cases_remain_safe(self):
        """B-C12. SERVICE_SAFE pose remains physically safe across all boundary corners of supported envelope."""
        self.sim.runtime_go_service_safe()
        envelope_corners = [
            (-20.0, -10.0),
            (-20.0, 30.0),
            (60.0, -10.0),
            (60.0, 30.0),
        ]
        half_l = (self.sim.geom.board.outer_length / 2.0) / 1000.0
        half_w = (self.sim.geom.board.outer_width / 2.0) / 1000.0
        piece_h = self.sim.geom.piece.height / 1000.0
        thick = self.sim.geom.board.thickness / 1000.0

        for fwd, z_off in envelope_corners:
            st = BoardPlacementState.compute(forward_shift_mm=fwd, board_height_offset_mm=z_off)
            cx, cy = st.physical_board_center_robot_m[:2]
            surf_z = st.board_surface_z_robot_m

            excl = self.sim.world.check_service_exclusion_occupancy(
                board_center_xy=(cx, cy),
                board_surface_z=surf_z,
                half_length_m=half_l,
                half_width_m=half_w,
                board_thickness_m=thick,
                piece_height_m=piece_h,
                xy_margin_m=self.sim.DEFAULT_SERVICE_XY_MARGIN_M,
                vertical_clearance_m=self.sim.DEFAULT_SERVICE_VERTICAL_CLEARANCE_M,
            )
            self.assertFalse(excl["link_inside"], f"Corner ({fwd}, {z_off}) link encroached: {excl}")
            self.assertFalse(excl["gripper_inside"], f"Corner ({fwd}, {z_off}) gripper encroached: {excl}")
            self.assertGreater(excl["min_moving_link_dist_m"], 0.05, f"Corner ({fwd}, {z_off}) link margin < 50mm")
            self.assertGreater(excl["min_gripper_proxy_dist_m"], 0.10, f"Corner ({fwd}, {z_off}) proxy margin < 100mm")

    # =========================================================================
    # PASS C: POST-OPERATION SAFE RETREAT TESTS (test_c1 .. test_c12)
    # =========================================================================

    def test_c1_normal_pick_retreat(self):
        """C1. Normal PICK lifts attached piece away from board to safe transit height and verifies PAYLOAD_CLEAR."""
        self.sim.runtime_go_service_safe()
        self.sim.world.step_until_settled(max_steps=30)
        p_id = list(self.sim.world.pieces.keys())[0]

        res = self.sim.pick_piece(p_id)
        self.assertTrue(res.success, f"Pick should succeed: {res.error}")
        self.assertTrue(res.piece_grasped)
        self.assertTrue(res.payload_clear)
        self.assertFalse(res.requires_recovery)
        self.assertEqual(res.piece_id, p_id)
        self.assertEqual(res.status, GraspStatus.SUCCESS.value)
        self.assertTrue(self.sim.is_payload_clear())

        # Authoritative physical predicate verification
        rep = self.sim.evaluate_payload_clearance(expected_piece_id=p_id)
        self.assertTrue(rep.payload_clear)
        self.assertTrue(rep.piece_attached)
        self.assertTrue(rep.gripper_closed)
        self.assertTrue(rep.robot_idle)
        self.assertTrue(rep.trajectory_idle)
        self.assertTrue(rep.collision_safe)
        self.assertTrue(rep.payload_above_transit_plane)
        self.assertGreaterEqual(rep.board_clearance_mm, 20.0)

        # Standalone PICK does NOT reach SERVICE_SAFE because piece is attached
        self.assertFalse(self.sim.is_service_safe())

        # Clean up
        self.sim.world.release_attached_piece()
        self.sim.backend.open_gripper()
        self.sim.runtime_go_service_safe()
        self.sim.reset_pieces()

    def test_c2_pick_lift_failure(self):
        """C2. Pick post-grasp lift failure reports failure with attached piece and requires recovery."""
        self.sim.runtime_go_service_safe()
        self.sim.world.step_until_settled(max_steps=30)
        p_id = list(self.sim.world.pieces.keys())[0]

        orig_mc = self.sim.backend.move_cartesian
        def mock_mc(pose, **kwargs):
            if self.sim.backend.get_trajectory_stage() == "LIFT":
                self.sim.backend._last_error = "MOCK_LIFT_STALL"
                return False
            return orig_mc(pose, **kwargs)

        with mock.patch.object(self.sim.backend, "move_cartesian", side_effect=mock_mc):
            res = self.sim.pick_piece(p_id)

        self.assertFalse(res.success)
        self.assertEqual(res.status, "PICK_LIFT_FAILED_WITH_ATTACHED_PIECE")
        self.assertTrue(res.piece_grasped)
        self.assertFalse(res.payload_clear)
        self.assertTrue(res.requires_recovery)
        self.assertEqual(self.sim.backend.get_trajectory_stage(), "FAILED")

        # Clean up
        self.sim.world.release_attached_piece()
        self.sim.backend.open_gripper()
        self.sim.clear_error()
        self.sim.runtime_go_service_safe()
        self.sim.reset_pieces()

    def test_c3_attachment_loss_during_retreat(self):
        """C3. Dropping piece during post-grasp lift reports attachment lost and requires recovery."""
        self.sim.runtime_go_service_safe()
        self.sim.world.step_until_settled(max_steps=30)
        p_id = list(self.sim.world.pieces.keys())[0]

        orig_mc = self.sim.backend.move_cartesian
        def mock_mc(pose, **kwargs):
            if self.sim.backend.get_trajectory_stage() == "LIFT":
                # Simulate attachment loss / piece drop during lift
                self.sim.world.release_attached_piece()
                self.sim.backend.set_attached_piece_id(None)
            return orig_mc(pose, **kwargs)

        with mock.patch.object(self.sim.backend, "move_cartesian", side_effect=mock_mc):
            res = self.sim.pick_piece(p_id)

        self.assertFalse(res.success)
        self.assertEqual(res.status, "PICK_ATTACHMENT_LOST_DURING_RETREAT")
        self.assertFalse(res.piece_grasped)
        self.assertFalse(res.payload_clear)
        self.assertTrue(res.requires_recovery)
        self.assertEqual(self.sim.backend.get_trajectory_stage(), "FAILED")

        # Clean up
        self.sim.clear_error()
        self.sim.runtime_go_service_safe()
        self.sim.reset_pieces()

    def test_c4_normal_place_full_retreat(self):
        """C4. Normal PLACE executes complete retreat through LIFT, CLEAR_BOARD, SERVICE_RETREAT to SERVICE_SAFE."""
        self.sim.runtime_go_service_safe()
        self.sim.world.step_until_settled(max_steps=30)
        p_id = list(self.sim.world.pieces.keys())[0]

        pick_res = self.sim.pick_piece(p_id)
        self.assertTrue(pick_res.success)

        res = self.sim.place_piece(target_cell=(4, 4))
        self.assertTrue(res.success)
        self.assertEqual(res.status, "SUCCESS")
        self.assertTrue(res.piece_placed)
        self.assertTrue(res.piece_released)
        self.assertTrue(res.post_release_lift_complete)
        self.assertTrue(res.board_clear)
        self.assertTrue(res.service_safe)
        self.assertFalse(res.requires_recovery)
        self.assertEqual(self.sim.backend.get_trajectory_stage(), "COMPLETE")

        # Authoritative physical predicate verification
        rep = self.sim.evaluate_service_safety()
        self.assertTrue(rep.service_safe)
        self.assertTrue(self.sim.is_service_safe())

        # Clean up
        self.sim.reset_pieces()
        self.sim.runtime_go_service_safe()

    def test_c5_release_succeeds_lift_fails(self):
        """C5. Release succeeds but post-release lift fails: success is False, piece is placed, requires recovery."""
        self.sim.runtime_go_service_safe()
        self.sim.world.step_until_settled(max_steps=30)
        p_id = list(self.sim.world.pieces.keys())[0]
        pick_res = self.sim.pick_piece(p_id)
        self.assertTrue(pick_res.success)

        orig_mc = self.sim.backend.move_cartesian
        def mock_mc(pose, **kwargs):
            if self.sim.backend.get_trajectory_stage() == "POST_RELEASE_LIFT":
                self.sim.backend._last_error = "MOCK_POST_RELEASE_LIFT_FAILED"
                return False
            return orig_mc(pose, **kwargs)

        with mock.patch.object(self.sim.backend, "move_cartesian", side_effect=mock_mc):
            res = self.sim.place_piece(target_cell=(4, 4))

        # CRITICAL BUG FIX INVARIANT: Under NO circumstances return success=True!
        self.assertFalse(res.success)
        self.assertEqual(res.status, "PLACE_LIFT_FAILED_AFTER_RELEASE")
        self.assertTrue(res.piece_placed)
        self.assertTrue(res.piece_released)
        self.assertFalse(res.post_release_lift_complete)
        self.assertFalse(res.board_clear)
        self.assertFalse(res.service_safe)
        self.assertTrue(res.requires_recovery)
        self.assertEqual(self.sim.backend.get_trajectory_stage(), "FAILED")

        # Piece remains physically placed at cell (4, 4)
        p = self.sim.world.pieces[p_id]
        pos, _ = p.get_pose_robot_base()
        tx, ty, _ = self.sim.cell_to_robot_xyz_m(4, 4)
        np.testing.assert_allclose(pos[:2], [tx, ty], atol=0.03)

        # Clean up
        self.sim.clear_error()
        self.sim.runtime_go_service_safe()
        self.sim.reset_pieces()

    def test_c6_clear_board_succeeds_service_retreat_fails(self):
        """C6. Post-release lift succeeds but SERVICE_RETREAT fails: success is False, piece is placed, requires recovery."""
        self.sim.runtime_go_service_safe()
        self.sim.world.step_until_settled(max_steps=30)
        p_id = list(self.sim.world.pieces.keys())[0]
        pick_res = self.sim.pick_piece(p_id)
        self.assertTrue(pick_res.success)

        orig_fn = self.sim.backend.move_joint_with_lift_recovery
        def mock_retreat(target_joints_deg, **kwargs):
            if self.sim.backend.get_trajectory_stage() == "SERVICE_RETREAT":
                self.sim.backend._last_error = "MOCK_SERVICE_RETREAT_INTERRUPTED"
                return False
            return orig_fn(target_joints_deg, **kwargs)

        with mock.patch.object(self.sim.backend, "move_joint_with_lift_recovery", side_effect=mock_retreat):
            res = self.sim.place_piece(target_cell=(4, 4))

        self.assertFalse(res.success)
        self.assertEqual(res.status, "PLACE_SERVICE_RETREAT_FAILED")
        self.assertTrue(res.piece_placed)
        self.assertTrue(res.piece_released)
        self.assertTrue(res.post_release_lift_complete)
        self.assertTrue(res.board_clear)
        self.assertFalse(res.service_safe)
        self.assertTrue(res.requires_recovery)
        self.assertEqual(self.sim.backend.get_trajectory_stage(), "FAILED")

        # Clean up
        self.sim.clear_error()
        self.sim.runtime_go_service_safe()
        self.sim.reset_pieces()

    def test_c7_joint_target_reached_but_physical_service_predicate_fails(self):
        """C7. Reaches SERVICE_SAFE joint target but physical predicate fails: reports COMPLETE_BUT_NOT_SERVICE_SAFE."""
        self.sim.runtime_go_service_safe()
        self.sim.world.step_until_settled(max_steps=30)
        p_id = list(self.sim.world.pieces.keys())[0]
        pick_res = self.sim.pick_piece(p_id)
        self.assertTrue(pick_res.success)

        orig_eval = self.sim.evaluate_service_safety
        def mock_eval():
            rep = orig_eval()
            return dataclasses.replace(
                rep,
                service_safe=False,
                gripper_open=False,
                reasons=["SERVICE_UNSAFE_GRIPPER_NOT_OPEN"],
            )

        with mock.patch.object(self.sim, "evaluate_service_safety", side_effect=mock_eval):
            res = self.sim.place_piece(target_cell=(4, 4))

        self.assertFalse(res.success)
        self.assertEqual(res.status, "COMPLETE_BUT_NOT_SERVICE_SAFE")
        self.assertTrue(res.piece_placed)
        self.assertTrue(res.piece_released)
        self.assertTrue(res.post_release_lift_complete)
        self.assertFalse(res.service_safe)
        self.assertTrue(res.requires_recovery)
        self.assertEqual(self.sim.backend.get_trajectory_stage(), "FAILED")

        # Clean up
        self.sim.clear_error()
        self.sim.runtime_go_service_safe()
        self.sim.reset_pieces()

    def test_c8_dynamic_board_height(self):
        """C8. Place and retreat operates correctly under dynamic board placement and height offset."""
        self.sim.runtime_go_service_safe()
        self.sim.prepare_board_adjustment()
        adj_res = self.sim.set_board_placement(forward_shift_mm=0.0, board_height_offset_mm=15.0)
        self.assertTrue(adj_res.get("success", False))

        p_id = list(self.sim.world.pieces.keys())[0]
        pick_res = self.sim.pick_piece(p_id)
        self.assertTrue(pick_res.success)

        place_res = self.sim.place_piece(target_cell=(4, 4))
        self.assertTrue(place_res.success)
        self.assertTrue(place_res.service_safe)
        self.assertEqual(place_res.status, "SUCCESS")

        # Verify robot reached SERVICE_SAFE pose above elevated board
        rep = self.sim.evaluate_service_safety()
        self.assertTrue(rep.service_safe)

        # Restore default placement
        self.sim.prepare_board_adjustment()
        self.sim.set_board_placement(forward_shift_mm=0.0, board_height_offset_mm=0.0)
        self.sim.reset_pieces()

    def test_c9_retreat_collision(self):
        """C9. Staged retreat halts safely if obstacle is detected, preventing swept collisions."""
        self.sim.runtime_go_service_safe()
        self.sim.world.step_until_settled(max_steps=30)
        p_id = list(self.sim.world.pieces.keys())[0]
        pick_res = self.sim.pick_piece(p_id)
        self.assertTrue(pick_res.success)

        orig_fn = self.sim.backend.move_joint_with_lift_recovery
        def mock_retreat(target_joints_deg, **kwargs):
            if self.sim.backend.get_trajectory_stage() == "SERVICE_RETREAT":
                self.sim.backend._last_error = "COLLISION_DETECTED_IN_RETREAT"
                return False
            return orig_fn(target_joints_deg, **kwargs)

        with mock.patch.object(self.sim.backend, "move_joint_with_lift_recovery", side_effect=mock_retreat):
            res = self.sim.place_piece(target_cell=(4, 4))

        self.assertFalse(res.success)
        self.assertEqual(res.status, "PLACE_SERVICE_RETREAT_FAILED")
        self.assertTrue(res.requires_recovery)
        self.assertFalse(res.service_safe)
        self.assertEqual(self.sim.backend.get_trajectory_stage(), "FAILED")

        # Clean up
        self.sim.clear_error()
        self.sim.runtime_go_service_safe()
        self.sim.reset_pieces()

    def test_c10_board_controls_remain_locked_after_unsafe_partial_place(self):
        """C10. Board controls remain locked after unsafe partial place; relocation is strictly rejected."""
        self.sim.runtime_go_service_safe()
        self.sim.world.step_until_settled(max_steps=30)
        p_id = list(self.sim.world.pieces.keys())[0]
        pick_res = self.sim.pick_piece(p_id)
        self.assertTrue(pick_res.success)

        orig_mc = self.sim.backend.move_cartesian
        def mock_mc(pose, **kwargs):
            if self.sim.backend.get_trajectory_stage() == "POST_RELEASE_LIFT":
                self.sim.backend._last_error = "LIFT_MOTOR_OVERLOAD"
                return False
            return orig_mc(pose, **kwargs)

        with mock.patch.object(self.sim.backend, "move_cartesian", side_effect=mock_mc):
            res = self.sim.place_piece(target_cell=(4, 4))

        self.assertFalse(res.success)
        self.assertEqual(res.status, "PLACE_LIFT_FAILED_AFTER_RELEASE")

        # Pass B invariant: board adjustment readiness MUST be False
        self.assertFalse(self.sim.is_board_adjustment_ready)

        # Attempting board adjustment must be rejected
        reloc = self.sim.set_board_placement(forward_shift_mm=10.0)
        self.assertFalse(reloc.get("success", False))
        self.assertIn("BOARD_RELOCATION_REJECTED", reloc.get("status", ""))

        # Clean up: clear error, prepare board adjustment and restore service safe
        self.sim.clear_error()
        self.sim.runtime_go_service_safe()
        self.sim.reset_pieces()

    def test_c11_no_duplicate_place(self):
        """C11. Partial place failure preserves placed piece without duplicate release or re-grasp retry."""
        self.sim.runtime_go_service_safe()
        self.sim.world.step_until_settled(max_steps=30)
        initial_piece_count = len(self.sim.world.pieces)
        p_id = list(self.sim.world.pieces.keys())[0]

        pick_res = self.sim.pick_piece(p_id)
        self.assertTrue(pick_res.success)

        orig_mc = self.sim.backend.move_cartesian
        def mock_mc(pose, **kwargs):
            if self.sim.backend.get_trajectory_stage() == "POST_RELEASE_LIFT":
                self.sim.backend._last_error = "MOCK_LIFT_STALL"
                return False
            return orig_mc(pose, **kwargs)

        with mock.patch.object(self.sim.backend, "move_cartesian", side_effect=mock_mc):
            res = self.sim.place_piece(target_cell=(4, 4))

        self.assertFalse(res.success)
        self.assertTrue(res.piece_placed)
        self.assertTrue(res.piece_released)

        # Piece count remains strictly invariant
        self.assertEqual(len(self.sim.world.pieces), initial_piece_count)

        # Gripper is empty (no re-grasp attempt)
        self.assertIsNone(self.sim.world.get_attached_piece())
        self.assertIsNone(self.sim.backend.get_attached_piece_id())

        # Piece physically resting at target cell
        p = self.sim.world.pieces[p_id]
        pos, _ = p.get_pose_robot_base()
        tx, ty, _ = self.sim.cell_to_robot_xyz_m(4, 4)
        np.testing.assert_allclose(pos[:2], [tx, ty], atol=0.03)

        # Clean up
        self.sim.clear_error()
        self.sim.runtime_go_service_safe()
        self.sim.reset_pieces()

    def test_c12_trajectory_stage_truthfulness(self):
        """C12. Trajectory stage is never COMPLETE prior to verified retreat and reports FAILED on retreat error."""
        self.sim.runtime_go_service_safe()
        self.sim.world.step_until_settled(max_steps=30)
        p_id = list(self.sim.world.pieces.keys())[0]
        pick_res = self.sim.pick_piece(p_id)
        self.assertTrue(pick_res.success)

        stages_observed = []
        orig_set_stage = self.sim.backend.set_trajectory_stage
        def record_stage(stage):
            stages_observed.append(stage)
            return orig_set_stage(stage)

        with mock.patch.object(self.sim.backend, "set_trajectory_stage", side_effect=record_stage):
            orig_retreat = self.sim.backend.move_joint_with_lift_recovery
            def mock_retreat(target_joints_deg, **kwargs):
                if self.sim.backend.get_trajectory_stage() == "SERVICE_RETREAT":
                    return False
                return orig_retreat(target_joints_deg, **kwargs)

            with mock.patch.object(self.sim.backend, "move_joint_with_lift_recovery", side_effect=mock_retreat):
                res = self.sim.place_piece(target_cell=(4, 4))

        self.assertFalse(res.success)
        self.assertIn("SERVICE_RETREAT", stages_observed)
        self.assertEqual(stages_observed[-1], "FAILED")
        self.assertNotIn("COMPLETE", stages_observed)
        self.assertEqual(self.sim.backend.get_trajectory_stage(), "FAILED")

        # Now test successful place stage progression
        self.sim.clear_error()
        self.sim.runtime_go_service_safe()
        self.sim.reset_pieces()

        p_id = list(self.sim.world.pieces.keys())[0]
        self.sim.pick_piece(p_id)

        stages_success = []
        def record_stage_ok(stage):
            stages_success.append(stage)
            return orig_set_stage(stage)

        with mock.patch.object(self.sim.backend, "set_trajectory_stage", side_effect=record_stage_ok):
            res_ok = self.sim.place_piece(target_cell=(4, 4))

        self.assertTrue(res_ok.success)
        self.assertIn("APPROACH", stages_success)
        self.assertIn("LAND", stages_success)
        self.assertIn("RELEASE", stages_success)
        self.assertIn("SETTLE", stages_success)
        self.assertIn("POST_RELEASE_LIFT", stages_success)
        self.assertIn("CLEAR_BOARD", stages_success)
        self.assertIn("SERVICE_RETREAT", stages_success)
        self.assertEqual(stages_success[-1], "COMPLETE")
        self.assertEqual(self.sim.backend.get_trajectory_stage(), "COMPLETE")

        # Clean up
        self.sim.reset_pieces()
        self.sim.runtime_go_service_safe()


if __name__ == "__main__":
    unittest.main()
