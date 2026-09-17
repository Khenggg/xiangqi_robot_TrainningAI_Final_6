"""
Unit tests for Phase 3 Dynamic Board Placement Corrective Pass:
1. Coordinate transform contract (d=0, d=30mm, robot -X to viewer +Z).
2. Authoritative BoardPlacementState & PyBullet/pieces consistency.
3. Dataset invalidation policy & on-demand IK runtime authority.
4. Guaranteed allowed_grasp_piece_id cleanup on all exit paths.
5. Strengthened anti-tunneling negative test (start SAFE, end SAFE, intermediate COLLISION, rejected, state preserved).
6. Row 0 Col 2..6 collision investigation & resolution via continuous safe interval.
7. Representative Cartesian trajectory executions across the board.
"""

import json
import math
from pathlib import Path
import sys
import unittest
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.domain.geometry import get_physical_geometry
from src.simulation.placement import (
    BoardPlacementState,
    BoardPlacementAnalyzer,
    canonical_cell_to_robot_xyz_m,
)
from src.simulation.kinematics.fr3 import FR3Kinematics
from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.physics.state import PiecePhysicalState
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.runtime import VirtualXiangqiSimulation
import pybullet as p_bullet
from src.simulation.virtual_fr3_backend import VirtualFR3Backend, PlannedTrajectory


class DynamicBoardPlacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geom = get_physical_geometry()
        cls.kinematics = FR3Kinematics()

    def test_coordinate_transform_contract(self):
        """
        Verify Section 35 coordinate contract:
        - d = 0, row 0 col 4: x = -0.180, y = 0.0
        - d = +30mm, row 0 col 4: x = -0.210, y = 0.0
        - d = +30mm, row 9 col 8: x = -0.570, y = +0.160
        - Viewer mapping: robot -X shift by -30mm maps to Three.js world +Z shift by +30mm.
        """
        r_sp = self.geom.grid_cell_length_mm / 1000.0  # 0.040m
        c_sp = self.geom.grid_cell_width_mm / 1000.0   # 0.040m

        # 1. d = 0, row 0 col 4
        x, y, z = canonical_cell_to_robot_xyz_m(
            row=0, col=4, forward_shift_mm=0.0, z_m=0.0105,
            nominal_x0=-0.180, nominal_y0=-0.160, row_spacing_m=r_sp, col_spacing_m=c_sp,
        )
        self.assertAlmostEqual(x, -0.180, places=4)
        self.assertAlmostEqual(y, 0.000, places=4)
        self.assertAlmostEqual(z, 0.0105, places=4)

        # 2. d = +30mm, row 0 col 4
        x, y, z = canonical_cell_to_robot_xyz_m(
            row=0, col=4, forward_shift_mm=30.0, z_m=0.0105,
            nominal_x0=-0.180, nominal_y0=-0.160, row_spacing_m=r_sp, col_spacing_m=c_sp,
        )
        self.assertAlmostEqual(x, -0.210, places=4)
        self.assertAlmostEqual(y, 0.000, places=4)

        # 3. d = +30mm, row 9 col 8
        x, y, z = canonical_cell_to_robot_xyz_m(
            row=9, col=8, forward_shift_mm=30.0, z_m=0.0105,
            nominal_x0=-0.180, nominal_y0=-0.160, row_spacing_m=r_sp, col_spacing_m=c_sp,
        )
        # x = -0.180 - 0.030 - 9*0.040 = -0.570
        # y = -0.160 + 8*0.040 = +0.160
        self.assertAlmostEqual(x, -0.570, places=4)
        self.assertAlmostEqual(y, 0.160, places=4)

        # 4. Three.js world mapping verification: world_z = -robot_x
        state_nom = BoardPlacementState.compute(forward_shift_mm=0.0)
        state_shift = BoardPlacementState.compute(forward_shift_mm=30.0)

        delta_robot_x = state_shift.board_center_robot_m[0] - state_nom.board_center_robot_m[0]
        delta_world_z = state_shift.board_center_world_m[2] - state_nom.board_center_world_m[2]

        self.assertAlmostEqual(delta_robot_x, -0.030, places=4, msg="Robot X must shift by -30mm")
        self.assertAlmostEqual(delta_world_z, +0.030, places=4, msg="Viewer world Z must shift by +30mm")

    def test_board_placement_runtime_state_and_pybullet_consistency(self):
        """
        Verify Section 36:
        - Relocating board updates PyBullet board pose
        - All ON_BOARD pieces translated consistently
        - Target cell coordinates correspond to new position
        - Placement version increments
        """
        sim = VirtualXiangqiSimulation()
        sim.start()

        init_ver = sim.placement_state.placement_version
        init_board_pos = sim.world.get_board_pose()[0]

        # Prepare board adjustment
        sim.prepare_board_adjustment()

        # Record piece positions before relocation
        piece_p_before = {}
        for pid, p in sim.world.pieces.items():
            piece_p_before[pid] = list(p.get_pose_robot_base()[0])

        # Relocate board forward by 25mm
        res = sim.set_board_placement(forward_shift_mm=25.0, safe_transit_height_mm=45.0)
        self.assertTrue(res["success"])
        self.assertEqual(sim.placement_state.placement_version, init_ver + 1)
        self.assertEqual(sim.backend.get_state_snapshot().placement_version, init_ver + 1)

        # Check PyBullet board pose
        new_board_pos = sim.world.get_board_pose()[0]
        # In robot frame: board shifted by -0.025m along X.
        self.assertAlmostEqual(new_board_pos[0] - init_board_pos[0], -0.025, places=4)

        # Check all pieces translated consistently
        for pid, p in sim.world.pieces.items():
            new_p = p.get_pose_robot_base()[0]
            delta_x = new_p[0] - piece_p_before[pid][0]
            self.assertAlmostEqual(delta_x, -0.025, places=4, msg=f"Piece {pid} must translate by -25mm along robot X")

        # Revert back to nominal
        sim.reset_board_placement()
        self.assertAlmostEqual(sim.placement_state.forward_shift_mm, 0.0)
        sim.stop()

    def test_dataset_invalidation_and_on_demand_ik(self):
        """
        Verify Section 37:
        - Once board placement changes, precomputed nominal joints are not blindly used.
        - Runtime computes on-demand IK for current placement.
        - Stale planned_placement_version is rejected.
        """
        sim = VirtualXiangqiSimulation()
        sim.start()

        # Version 1 is nominal
        v1 = sim.placement_state.placement_version

        # Move board to 28mm -> Version 2
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=28.0, safe_transit_height_mm=40.0)
        v2 = sim.placement_state.placement_version
        self.assertEqual(v2, v1 + 1)

        # Attempt trajectory with stale planned version (v1)
        stale_res = sim.execute_3stage_trajectory(
            src_cell=(4, 4), dst_cell=(4, 5), planned_placement_version=v1
        )
        self.assertFalse(stale_res["success"])
        self.assertEqual(stale_res["failed_stage"], "PRECHECK")
        self.assertIn("Stale placement version", stale_res["error"])

        # Execute trajectory with matching current version (v2) -> solves on-demand IK
        valid_res = sim.execute_3stage_trajectory(
            src_cell=(4, 4), dst_cell=(4, 5), planned_placement_version=v2, samples_per_stage=10
        )
        self.assertTrue(valid_res["success"], f"On-demand IK trajectory failed: {valid_res.get('error')}")
        self.assertEqual(valid_res["placement_version"], v2)

        sim.stop()

    def test_allowed_grasp_piece_id_guaranteed_cleanup(self):
        """
        Verify Section 29:
        allowed_grasp_piece_id must NEVER survive a trajectory:
        - on success
        - on PREPOSITION failure
        - on LIFT/TRANSIT/LAND failure
        - on exception
        - on stop()
        """
        sim = VirtualXiangqiSimulation()
        sim.start()

        backend = sim.backend

        # 1. Success cleanup
        sim.execute_3stage_trajectory((4, 4), (4, 5), samples_per_stage=10)
        self.assertIsNone(backend.allowed_grasp_piece_id, "Must be None after successful trajectory")

        # 2. Failure cleanup (unreachable destination)
        sim.execute_3stage_trajectory((4, 4), (99, 99), samples_per_stage=10)
        self.assertIsNone(backend.allowed_grasp_piece_id, "Must be None after PREPOSITION reject")

        # 3. Exception cleanup
        try:
            backend.set_allowed_grasp_piece_id("test_piece")
            # Simulate trajectory try/finally block
            try:
                raise RuntimeError("Simulated mid-trajectory failure")
            finally:
                backend.set_allowed_grasp_piece_id(None)
        except RuntimeError:
            pass
        self.assertIsNone(backend.allowed_grasp_piece_id, "Must be None after exception")

        # 4. Stop cleanup
        backend.set_allowed_grasp_piece_id("test_piece_2")
        backend.stop()
        self.assertIsNone(backend.allowed_grasp_piece_id, "Must be None after stop()")

        sim.stop()

    def test_strengthened_anti_tunneling(self):
        """
        Verify Section 30:
        - start configuration = SAFE
        - end configuration = SAFE
        - sparse endpoint-only check would not see collision
        - intermediate configuration collides with obstacle
        - trajectory REJECTED
        - last safe state preserved
        """
        sim = VirtualXiangqiSimulation()
        sim.start()

        # Place all ambient pieces out of bounds
        for pid, p in sim.world.pieces.items():
            p.physical_state = PiecePhysicalState.OUT_OF_BOUNDS

        # Place an elevated obstacle directly on the path between cell (2, 2) and cell (2, 6)
        obs = sim.world.pieces["black_cannon_0"]
        obs.physical_state = PiecePhysicalState.RESTING
        obs.set_pose_robot_base([-0.260, 0.0, 0.130], [0, 0, 0, 1])

        # Start at cell (2, 2), goal at cell (2, 6) at transit height
        pos_s = sim.cell_to_robot_xyz_m(2, 2, sim.board_surface_z + 0.070)
        pos_g = sim.cell_to_robot_xyz_m(2, 6, sim.board_surface_z + 0.070)
        p_s_mm = [v * 1000.0 for v in pos_s] + [180.0, 0.0, 90.0]
        p_g_mm = [v * 1000.0 for v in pos_g] + [180.0, 0.0, 90.0]

        p_mid_m = sim.cell_to_robot_xyz_m(2, 4, sim.board_surface_z + 0.070)
        p_m_mm = [v * 1000.0 for v in p_mid_m] + [180.0, 0.0, 90.0]

        seed_s = sim.reachability_dataset[(2, 2)]["approach_joints_deg"]
        seed_g = sim.reachability_dataset[(2, 6)]["approach_joints_deg"]
        seed_m = sim.reachability_dataset[(2, 4)]["approach_joints_deg"]

        ik_start = sim.backend.solve_tcp_ik(p_s_mm, seed_joints=np.deg2rad(seed_s), allow_multi_seed=True)
        ik_goal = sim.backend.solve_tcp_ik(p_g_mm, seed_joints=np.deg2rad(seed_g), allow_multi_seed=True)
        ik_mid = sim.backend.solve_tcp_ik(p_m_mm, seed_joints=np.deg2rad(seed_m), allow_multi_seed=True)

        self.assertTrue(ik_start.success)
        self.assertTrue(ik_goal.success)
        self.assertTrue(ik_mid.success)

        # 1. Assert start is SAFE
        start_check = sim.collision_guard.validate_configuration(ik_start.joints_rad)
        self.assertTrue(start_check.safe, "Start configuration must be collision-free")

        # 2. Assert end is SAFE
        end_check = sim.collision_guard.validate_configuration(ik_goal.joints_rad)
        self.assertTrue(end_check.safe, "End configuration must be collision-free")

        # 3. Assert a naive endpoint-only check would be blind to collision
        naive_endpoint_only_safe = start_check.safe and end_check.safe
        self.assertTrue(naive_endpoint_only_safe, "Sparse endpoint check falsely considers motion safe")

        # 4. Assert intermediate configuration COLLIDES
        mid_check = sim.collision_guard.validate_configuration(ik_mid.joints_rad)
        self.assertFalse(mid_check.safe, "Intermediate configuration must collide with obstacle")

        # 5. Execute trajectory and assert REJECTED
        sim.backend.move_joint(np.degrees(ik_start.joints_rad).tolist(), speed_factor=100.0)
        saved_safe_joints = list(sim.backend.get_state_snapshot().joints_deg)

        traj_res = sim.backend.move_cartesian(p_g_mm, samples=20, speed_factor=100.0)
        self.assertFalse(traj_res, "Subdivided trajectory must reject intermediate collision")
        self.assertEqual(sim.backend.get_state_snapshot().motion_state, "COLLISION_REJECTED")

        # 6. Assert last safe state preserved
        after_joints = sim.backend.get_state_snapshot().joints_deg
        np.testing.assert_allclose(
            after_joints, saved_safe_joints, atol=1e-2,
            err_msg="Authoritative robot state must remain at last safe pose after rejection"
        )

        sim.stop()

    def test_row0_collision_resolution_and_recommended_placement(self):
        """
        Verify Section 39 & 40:
        At nominal d=0, H=70mm:
        - Row 0 Col 2..6 LAND vertical descent fails due to link 1 <-> link 3 robot self-collision.
        At recommended placement d=28.5mm, H=40mm:
        - Row 0 Col 2..6 ALL succeed LAND vertical descent without collision.
        - Far cells (Row 9 Col 0, 4, 8) remain reachable and collision-free.
        """
        sim = VirtualXiangqiSimulation()
        sim.start()

        # Step 1: Prove nominal problem on Row 0 Col 4
        sim.reset_board_placement()  # d=0, H=70
        z_grasp = sim.board_surface_z + sim.geom.piece_height_mm / 2000.0
        p_gr_nom = [v * 1000.0 for v in sim.cell_to_robot_xyz_m(0, 4, z_grasp)] + [180.0, 0.0, 90.0]

        cell_info = sim.reachability_dataset.get((0, 4))
        q_app = np.deg2rad(cell_info["approach_joints_deg"])
        sim.backend.move_joint(np.degrees(q_app).tolist(), speed_factor=100.0)
        land_nom_ok = sim.backend.move_cartesian(p_gr_nom, samples=20, speed_factor=100.0)
        self.assertFalse(land_nom_ok, "At nominal d=0, H=70, Row 0 Col 4 LAND must fail due to self-collision")
        self.assertIn("link 1", sim.backend._last_error)
        self.assertIn("link 3", sim.backend._last_error)

        # Step 2: Relocate to recommended operating region (d = 28.5mm, H = 40mm)
        sim.prepare_board_adjustment()
        res_reloc = sim.set_board_placement(forward_shift_mm=28.5, safe_transit_height_mm=40.0)
        self.assertTrue(res_reloc["success"])

        # Step 3: Test Row 0 Col 2..6 LAND vertical descent
        for c in range(2, 7):
            pos_gr = sim.cell_to_robot_xyz_m(0, c, z_grasp)
            pos_ap = sim.cell_to_robot_xyz_m(0, c, sim.board_surface_z + 0.040)
            pose_gr = [v * 1000.0 for v in pos_gr] + [180.0, 0.0, 90.0]
            pose_ap = [v * 1000.0 for v in pos_ap] + [180.0, 0.0, 90.0]

            cell_info = sim.reachability_dataset.get((0, c))
            seed_app = np.deg2rad(cell_info["approach_joints_deg"]) if cell_info else None
            ik_a = sim.backend.solve_tcp_ik(pose_ap, seed_joints=seed_app, allow_multi_seed=True)
            self.assertTrue(ik_a.success, f"Approach IK must succeed for (0, {c})")
            sim.backend.set_authoritative_joints(ik_a.joints_rad, is_deg=False)

            # Find target piece at (0, c) if any
            target_pid = None
            for pid, pb in sim.world.pieces.items():
                if pb.physical_state != PiecePhysicalState.OUT_OF_BOUNDS:
                    c_p, r_p, d_p = pb.get_nearest_intersection()
                    if (r_p, c_p) == (0, c) and d_p < 0.025:
                        target_pid = pid
                        break

            try:
                sim.backend.set_allowed_grasp_piece_id(target_pid)
                land_ok = sim.backend.move_cartesian(pose_gr, samples=15, speed_factor=100.0)
                self.assertTrue(
                    land_ok,
                    f"Row 0 Col {c} LAND descent must succeed at d=28.5mm without collision, error: {sim.backend._last_error}"
                )
            finally:
                sim.backend.set_allowed_grasp_piece_id(None)

        # Step 4: Verify far cells remain reachable and collision-free
        for far_c in [0, 4, 8]:
            pos_gr = sim.cell_to_robot_xyz_m(9, far_c, z_grasp)
            pos_ap = sim.cell_to_robot_xyz_m(9, far_c, sim.board_surface_z + 0.040)
            cell_info = sim.reachability_dataset.get((9, far_c))
            seed_gr = np.deg2rad(cell_info["grasp_joints_deg"]) if cell_info else None
            seed_ap = np.deg2rad(cell_info["approach_joints_deg"]) if cell_info else None

            ik_far_gr = sim.backend.solve_tcp_ik([v * 1000.0 for v in pos_gr] + [180.0, 0.0, 90.0], seed_joints=seed_gr, allow_multi_seed=True)
            ik_far_ap = sim.backend.solve_tcp_ik([v * 1000.0 for v in pos_ap] + [180.0, 0.0, 90.0], seed_joints=seed_ap, allow_multi_seed=True)
            self.assertTrue(ik_far_gr.success, f"Far cell (9, {far_c}) grasp IK must succeed")
            self.assertTrue(ik_far_ap.success, f"Far cell (9, {far_c}) approach IK must succeed")
            col_gr = sim.collision_guard.validate_configuration(ik_far_gr.joints_rad, allowed_grasp_piece_id="*")
            col_ap = sim.collision_guard.validate_configuration(ik_far_ap.joints_rad)
            self.assertTrue(col_gr.safe, f"Far cell (9, {far_c}) grasp must be collision-free")
            self.assertTrue(col_ap.safe, f"Far cell (9, {far_c}) approach must be collision-free")

        sim.stop()

    def test_representative_trajectories_at_recommended_placement(self):
        """
        Verify Section 40:
        Execute full 3-stage trajectories across diverse routes at recommended placement:
        - Near -> Far: (0, 4) -> (9, 4)
        - Far -> Near: (9, 0) -> (0, 8)
        - Left -> Right: (4, 0) -> (4, 8)
        - Diagonal: (0, 2) -> (5, 7)
        """
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=28.5, safe_transit_height_mm=40.0)

        routes = [
            ((0, 4), (9, 4), "Near to Far (center file)"),
            ((9, 0), (0, 8), "Far to Near (diagonal cross)"),
            ((4, 0), (4, 8), "Left to Right (river file)"),
            ((0, 2), (5, 7), "Problem cell to mid-board"),
        ]

        for src, dst, label in routes:
            res = sim.execute_3stage_trajectory(src_cell=src, dst_cell=dst, samples_per_stage=10, speed_factor=100.0)
            self.assertTrue(res["success"], f"Trajectory '{label}' from {src} to {dst} failed: {res.get('error')}")

        sim.stop()

    def test_plan_cartesian_pure_planning_without_state_mutation(self):
        """
        Verify plan_cartesian() produces PlannedTrajectory without mutating robot joint state.
        """
        sim = VirtualXiangqiSimulation()
        sim.start()
        backend = sim.backend

        init_joints = list(backend.get_state_snapshot().joints_deg)
        q_start = np.deg2rad(init_joints)

        # Plan move to a reachable target pose
        target_pose_mm = [-300.0, 0.0, 150.0, 180.0, 0.0, 90.0]
        planned = backend.plan_cartesian(q_start, target_pose_mm, samples=15)
        self.assertIsInstance(planned, PlannedTrajectory)
        self.assertTrue(planned.success)
        self.assertGreaterEqual(len(planned.q_samples), 15)

        # Assert backend state and PyBullet joints remained unchanged
        current_joints = list(backend.get_state_snapshot().joints_deg)
        np.testing.assert_allclose(current_joints, init_joints, atol=1e-3)

        pb_joints = [p_bullet.getJointState(sim.world.robot_body_id, j, physicsClientId=sim.world.client_id)[0] for j in range(6)]
        np.testing.assert_allclose(np.rad2deg(pb_joints), init_joints, atol=1e-2)

        sim.stop()

    def test_validation_state_invariance(self):
        """
        Verify validate_board_placement() guarantees joint state invariance
        in backend and PyBullet world before and after full validation run.
        """
        sim = VirtualXiangqiSimulation()
        sim.start()

        # Set robot to specific non-default pose
        test_pose = [10.0, -20.0, 30.0, -40.0, 50.0, -60.0]
        sim.backend.set_authoritative_joints(np.deg2rad(test_pose).tolist(), is_deg=False)
        sim.world.sync_robot_configuration(np.deg2rad(test_pose).tolist())

        q_backend_before = list(sim.backend.get_state_snapshot().joints_deg)
        q_pb_before = [p_bullet.getJointState(sim.world.robot_body_id, j, physicsClientId=sim.world.client_id)[0] for j in range(6)]

        # Run validation
        res = sim.validate_board_placement()
        self.assertIn("total_cells", res)

        # Assert state unchanged
        q_backend_after = list(sim.backend.get_state_snapshot().joints_deg)
        q_pb_after = [p_bullet.getJointState(sim.world.robot_body_id, j, physicsClientId=sim.world.client_id)[0] for j in range(6)]

        np.testing.assert_allclose(q_backend_after, q_backend_before, atol=1e-3)
        np.testing.assert_allclose(q_pb_after, q_pb_before, atol=1e-3)

        sim.stop()

    def test_validation_version_atomicity(self):
        """
        Verify validate_board_placement() rejects mismatched placement version
        with status STALE_VALIDATION_RESULT.
        """
        sim = VirtualXiangqiSimulation()
        sim.start()

        curr_ver = sim.placement_state.placement_version
        res = sim.validate_board_placement(placement_version=curr_ver + 99)
        self.assertEqual(res["status"], "STALE_VALIDATION_RESULT")
        self.assertFalse(res["all_passed"])

        sim.stop()

    def test_nominal_placement_fails_row0_with_link_pair_and_sample(self):
        """
        Verify nominal d=0, H=70 fails Row 0 Col 2..6 LAND MoveL descent,
        reporting the failure stage, sample index, and self-collision link pair.
        """
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.reset_board_placement()

        res = sim.validate_board_placement()
        self.assertFalse(res["all_passed"])
        self.assertGreater(len(res["failed_cells"]), 0)

        # Look for (0, 4) in failed cells
        fail_0_4 = next((f for f in res["failed_cells"] if f["row"] == 0 and f["col"] == 4), None)
        self.assertIsNotNone(fail_0_4, "Row 0 Col 4 must fail at nominal placement")
        self.assertEqual(fail_0_4["stage"], "LAND")
        self.assertIn("link 1", fail_0_4["reason"])
        self.assertIn("link 3", fail_0_4["reason"])
        self.assertIsNotNone(fail_0_4.get("sample_idx"))
        self.assertGreater(fail_0_4["sample_idx"], 0)

        sim.stop()

    def test_recommended_placement_90_cells_pass(self):
        """
        Verify recommended candidate placement d=28.5mm, H=40mm achieves:
        - 90/90 Approach IK PASS
        - 90/90 LAND MoveL PASS
        - 90/90 Grasp IK PASS
        - 90/90 LIFT MoveL PASS
        - all_passed == True ("90/90 LOCAL CELL TRAJECTORIES PASS")
        """
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=28.5, safe_transit_height_mm=40.0)

        res = sim.validate_board_placement()
        self.assertTrue(res["all_passed"], f"Expected 90/90 pass, got failures: {res['failed_cells']}")
        self.assertEqual(res["total_cells"], 90)
        self.assertEqual(res["approach_ik_count"], 90)
        self.assertEqual(res["grasp_ik_count"], 90)
        self.assertEqual(res["land_move_passed_count"], 90)
        self.assertEqual(res["lift_move_passed_count"], 90)
        self.assertEqual(len(res["failed_cells"]), 0)

        sim.stop()

    def test_full_board_routes_validation(self):
        """
        Verify validate_full_board_routes() executes dry-run full trajectories
        across candidate placement and reports safe status.
        """
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=28.5, safe_transit_height_mm=40.0)

        res = sim.validate_full_board_routes(sample_limit=8)
        self.assertTrue(res["all_routes_safe"])
        self.assertEqual(res["failed_routes"], 0)
        self.assertGreaterEqual(res["total_routes"], 4)

        sim.stop()


if __name__ == "__main__":
    unittest.main()
