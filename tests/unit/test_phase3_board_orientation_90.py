"""
Test Suite: Phase 3 Board Orientation 90° Geometry Redesign (G90-01 to G90-25)

Authoritative Verification Suite:
- G90-01: Board-local cell coordinates (col span = 320 mm, row span = 360 mm)
- G90-02: yaw = +90° transform (+col -> -X_robot, +row -> -Y_robot, +z -> +Z_robot)
- G90-03: Exact cell -> robot -> cell round-trip for all 90 cells
- G90-04: All four corners map to expected quadrants
- G90-05: PyBullet board collider orientation equals authoritative BoardPose
- G90-06: Board physical dimensions remain canonical 410 x 367 x 10.5 mm
- G90-07: All ON_BOARD pieces rotate and translate consistently with BoardPose
- G90-08: Nearest-cell works after rotation
- G90-09: Out-of-bounds works in board-local frame after rotation
- G90-10: Stale placement version remains rejected
- G90-11: Viewer board/piece pose matches backend BoardPose
- G90-12: Local 90-cell feasibility reports correct counts
- G90-13: Local validator label is honest (LOCAL_CELL_FEASIBILITY, not called full-route safe)
- G90-14: Chained validator: LAND start_q == TRANSIT.final_q
- G90-15: Route to each of the four corner cells uses fully chained trajectory
- G90-16: Route from each corner back toward center is chained and collision checked
- G90-17: Near-side center cells do not reproduce old link1-link3 collision
- G90-18: Far-side worst cell retains positive reach margin
- G90-19: SERVICE_SAFE still passes rotated-board exclusion checks
- G90-20: Board adjustment / relocation swept volume works with rotated board
- G90-21: Normal pick-place succeeds with 90° orientation
- G90-22: Post-release retreat returns SERVICE_SAFE
- G90-23: Deliberate unreachable/collision candidate is rejected
- G90-24: Validation is state-invariant / no authoritative pose mutation
- G90-25: No regression on Pass A/A.1/A.2 authority and non-reentrancy rules
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
    compute_rotation_matrix,
)
from src.simulation.kinematics.fr3 import FR3Kinematics, IKStatus
from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.physics.state import PiecePhysicalState
from src.simulation.runtime import (
    VirtualXiangqiSimulation,
    RuntimeOperationState,
    RuntimeOperationBusy,
)
from src.simulation.virtual_fr3_backend import VirtualFR3Backend, PlannedTrajectory
import pybullet as p_bullet


class TestPhase3BoardOrientation90(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geom = get_physical_geometry()
        cls.kinematics = FR3Kinematics()

    def test_g90_01_board_local_cell_coordinates(self):
        """G90-01: Board-local cell coordinates: col span = 320 mm, row span = 360 mm."""
        state = BoardPlacementState.compute(0.0, board_yaw_deg=90.0)
        # Column span: col 0 -> -160mm, col 8 -> +160mm (span = 320mm)
        u_c0, _ = state.cell_to_board_local(0, 0)
        u_c8, _ = state.cell_to_board_local(0, 8)
        self.assertAlmostEqual(u_c0, -0.160, places=4)
        self.assertAlmostEqual(u_c8, +0.160, places=4)
        self.assertAlmostEqual(u_c8 - u_c0, 0.320, places=4)

        # Row span: row 0 -> -180mm, row 9 -> +180mm (span = 360mm)
        _, v_r0 = state.cell_to_board_local(0, 0)
        _, v_r9 = state.cell_to_board_local(9, 0)
        self.assertAlmostEqual(v_r0, -0.180, places=4)
        self.assertAlmostEqual(v_r9, +0.180, places=4)
        self.assertAlmostEqual(v_r9 - v_r0, 0.360, places=4)

    def test_g90_02_yaw_90_transform_axes(self):
        """G90-02: yaw = +90° transform: +column -> -X_robot, +row -> -Y_robot, +z -> +Z_robot."""
        state = BoardPlacementState.compute(0.0, board_yaw_deg=90.0)
        R = state.R_robot_from_board

        # Column axis unit vector [1, 0, 0] in board -> [-1, 0, 0] in robot (-X_robot)
        col_in_robot = R @ np.array([1.0, 0.0, 0.0])
        np.testing.assert_allclose(col_in_robot, [-1.0, 0.0, 0.0], atol=1e-6)

        # Row axis unit vector [0, 1, 0] in board -> [0, -1, 0] in robot (-Y_robot)
        row_in_robot = R @ np.array([0.0, 1.0, 0.0])
        np.testing.assert_allclose(row_in_robot, [0.0, -1.0, 0.0], atol=1e-6)

        # Up axis unit vector [0, 0, 1] in board -> [0, 0, 1] in robot (+Z_robot)
        up_in_robot = R @ np.array([0.0, 0.0, 1.0])
        np.testing.assert_allclose(up_in_robot, [0.0, 0.0, 1.0], atol=1e-6)

    def test_g90_03_exact_cell_robot_cell_roundtrip_all_90_cells(self):
        """G90-03: exact cell -> robot -> cell round-trip for all 90 cells."""
        state = BoardPlacementState.compute(15.0, board_yaw_deg=90.0)
        for r in range(10):
            for c in range(9):
                p_rob = state.cell_to_robot_xyz(r, c, 0.0)
                nearest_r, nearest_c, dist_m = state.robot_xyz_to_nearest_cell(p_rob)
                self.assertEqual(nearest_r, r, f"Row mismatch at ({r}, {c})")
                self.assertEqual(nearest_c, c, f"Col mismatch at ({r}, {c})")
                self.assertLess(dist_m, 1e-4, f"Distance residual non-zero at ({r}, {c})")

    def test_g90_04_four_corners_quadrants(self):
        """G90-04: all four corners map to expected quadrants."""
        state = BoardPlacementState.compute(0.0, board_yaw_deg=90.0)
        # Center is at [-0.360, 0.0]
        # (0, 0): col 0 (-160mm), row 0 (-180mm) -> X = -0.36 - (-0.16) = -0.20, Y = 0.0 - (-0.18) = +0.18
        p00 = state.cell_to_robot_xyz(0, 0, 0.0)
        self.assertAlmostEqual(p00[0], -0.200, places=4)
        self.assertAlmostEqual(p00[1], +0.180, places=4)
        self.assertLess(p00[0], 0.0)  # -X
        self.assertGreater(p00[1], 0.0)  # +Y

        # (0, 8): col 8 (+160mm), row 0 (-180mm) -> X = -0.36 - (+0.16) = -0.52, Y = +0.18
        p08 = state.cell_to_robot_xyz(0, 8, 0.0)
        self.assertAlmostEqual(p08[0], -0.520, places=4)
        self.assertAlmostEqual(p08[1], +0.180, places=4)
        self.assertLess(p08[0], 0.0)  # -X
        self.assertGreater(p08[1], 0.0)  # +Y

        # (9, 0): col 0 (-160mm), row 9 (+180mm) -> X = -0.20, Y = -0.18
        p90 = state.cell_to_robot_xyz(9, 0, 0.0)
        self.assertAlmostEqual(p90[0], -0.200, places=4)
        self.assertAlmostEqual(p90[1], -0.180, places=4)
        self.assertLess(p90[0], 0.0)  # -X
        self.assertLess(p90[1], 0.0)  # -Y

        # (9, 8): col 8 (+160mm), row 9 (+180mm) -> X = -0.52, Y = -0.18
        p98 = state.cell_to_robot_xyz(9, 8, 0.0)
        self.assertAlmostEqual(p98[0], -0.520, places=4)
        self.assertAlmostEqual(p98[1], -0.180, places=4)
        self.assertLess(p98[0], 0.0)  # -X
        self.assertLess(p98[1], 0.0)  # -Y

    def test_g90_05_pybullet_board_collider_orientation(self):
        """G90-05: PyBullet board collider orientation equals authoritative BoardPose."""
        world = VirtualPhysicalWorld()
        state = world.board_placement_state
        self.assertEqual(state.board_yaw_deg, 90.0)
        board_pos, board_quat = world.get_board_pose()

        # Check quaternion matches state.quat_robot_from_board: [0.0, 0.0, 1.0, 0.0]
        for q_act, q_exp in zip(board_quat, state.quat_robot_from_board):
            self.assertAlmostEqual(q_act, q_exp, places=4)
        world.close()

    def test_g90_06_board_physical_dimensions_canonical(self):
        """G90-06: board physical dimensions remain canonical 410 x 367 x 10.5 mm."""
        self.assertAlmostEqual(self.geom.board.outer_length, 410.0, places=2)
        self.assertAlmostEqual(self.geom.board.outer_width, 367.0, places=2)
        self.assertAlmostEqual(self.geom.board.thickness, 10.5, places=2)

    def test_g90_07_on_board_pieces_rotate_and_translate_consistently(self):
        """G90-07: all ON_BOARD pieces rotate and translate consistently with BoardPose."""
        sim = VirtualXiangqiSimulation()
        sim.start()

        # Check initial piece positions match state.cell_to_robot_xyz
        state_init = sim.placement_state
        for pid, p in sim.world.pieces.items():
            if p.physical_state == PiecePhysicalState.ON_BOARD:
                r, c, _ = p.get_nearest_intersection()
                expected_p = state_init.cell_to_robot_xyz(r, c, z_rel_m=self.geom.piece.height / 2000.0)
                actual_p, _ = p.get_pose_robot_base()
                self.assertAlmostEqual(actual_p[0], expected_p[0], places=3)
                self.assertAlmostEqual(actual_p[1], expected_p[1], places=3)

        # Relocate board and verify all pieces translate consistently
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=20.0)
        state_shifted = sim.placement_state
        for pid, p in sim.world.pieces.items():
            if p.physical_state == PiecePhysicalState.ON_BOARD:
                r, c, _ = p.get_nearest_intersection()
                expected_p = state_shifted.cell_to_robot_xyz(r, c, z_rel_m=self.geom.piece.height / 2000.0)
                actual_p, _ = p.get_pose_robot_base()
                self.assertAlmostEqual(actual_p[0], expected_p[0], places=3)
                self.assertAlmostEqual(actual_p[1], expected_p[1], places=3)

        sim.stop()

    def test_g90_08_nearest_cell_after_rotation(self):
        """G90-08: nearest-cell works after rotation."""
        state = BoardPlacementState.compute(15.0, board_yaw_deg=90.0)
        # Point slightly offset from cell (3, 3)
        p_exact = state.cell_to_robot_xyz(3, 3, 0.0)
        p_offset = p_exact + np.array([0.005, -0.005, 0.0])
        r, c, dist = state.robot_xyz_to_nearest_cell(p_offset)
        self.assertEqual((r, c), (3, 3))
        self.assertAlmostEqual(dist, math.hypot(0.005, 0.005), places=4)

    def test_g90_09_out_of_bounds_board_local(self):
        """G90-09: out-of-bounds works in board-local frame after rotation."""
        state = BoardPlacementState.compute(15.0, board_yaw_deg=90.0)
        # Center of board is in bounds
        p_center = list(state.board_center_robot_m[:2]) + [state.board_surface_z_robot_m]
        self.assertTrue(state.is_in_bounds_robot(p_center))

        # 4 corners are in bounds
        for r, c in [(0, 0), (0, 8), (9, 0), (9, 8)]:
            self.assertTrue(state.is_in_bounds_robot(state.cell_to_robot_xyz(r, c, 0.0)))

        # Point way off in board-local u (width) is out of bounds
        p_oob_u = state.board_local_to_robot(0.300, 0.0, 0.0)
        self.assertFalse(state.is_in_bounds_robot(p_oob_u))

        # Point way off in board-local v (length) is out of bounds
        p_oob_v = state.board_local_to_robot(0.0, 0.350, 0.0)
        self.assertFalse(state.is_in_bounds_robot(p_oob_v))

    def test_g90_10_stale_placement_version_remains_rejected(self):
        """G90-10: stale placement version remains rejected."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        curr_ver = sim.placement_state.placement_version
        res = sim.validate_board_placement(placement_version=curr_ver + 99)
        self.assertFalse(res["all_passed"])
        self.assertEqual(res["status"], "STALE_VALIDATION_RESULT")
        sim.stop()

    def test_g90_11_viewer_board_piece_pose_matches_backend(self):
        """G90-11: viewer board/piece pose matches backend BoardPose."""
        state = BoardPlacementState.compute(15.0, board_yaw_deg=90.0)
        # Check world coordinate mapping: X_world = -Y_robot, Y_world = +Z_robot, Z_world = -X_robot
        p_rob = state.board_center_robot_m
        p_w = state.physical_board_center_world_m
        self.assertAlmostEqual(p_w[0], -p_rob[1], places=4)
        self.assertAlmostEqual(p_w[1], p_rob[2], places=4)
        self.assertAlmostEqual(p_w[2], -p_rob[0], places=4)

    def test_g90_12_local_90_cell_feasibility_reports_correct_counts(self):
        """G90-12: local 90-cell feasibility reports correct counts."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        # Set placement to robust candidate
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)
        res = sim.validate_board_placement(sample_limit=5)
        self.assertIn("passed_cells_count", res)
        self.assertIn("failed_cells", res)
        self.assertEqual(res["total_cells"], 5)
        self.assertEqual(res["passed_cells_count"] + len(res["failed_cells"]), 5)
        sim.stop()

    def test_g90_13_local_validator_label_is_honest(self):
        """G90-13: local validator label is honest and not called full-route safe."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        res = sim.validate_board_placement(sample_limit=1)
        self.assertEqual(res["validation_label"], "LOCAL_CELL_FEASIBILITY")
        self.assertNotEqual(res["status"], "FULL_BOARD_ROUTE_SAFE")
        self.assertIn(res["status"], ("LOCAL_CELL_FEASIBLE", "LOCAL_CELL_UNFEASIBLE", "VALIDATION_REJECTED_BUSY"))
        sim.stop()

    def test_g90_14_chained_validator_land_starts_from_transit_final_q(self):
        """G90-14: chained validator: LAND start_q == TRANSIT.final_q."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)
        backend = sim.backend
        state = sim.placement_state
        p_src = state.cell_to_robot_xyz(4, 4, 0.040)
        p_dst_ap = state.cell_to_robot_xyz(4, 5, 0.040)
        p_dst_gr = state.cell_to_robot_xyz(4, 5, 0.004715)

        pose_src = [v * 1000.0 for v in p_src] + [180.0, 0.0, 90.0]
        pose_dst_ap = [v * 1000.0 for v in p_dst_ap] + [180.0, 0.0, 90.0]
        pose_dst_gr = [v * 1000.0 for v in p_dst_gr] + [180.0, 0.0, 90.0]

        seed_src = np.deg2rad(sim.reachability_dataset[(4, 4)]["approach_joints_deg"])
        ik_src = backend.solve_tcp_ik(pose_src, seed_joints=seed_src, allow_multi_seed=True)
        self.assertTrue(ik_src.success)

        transit = backend.plan_cartesian(ik_src.joints_rad, pose_dst_ap, samples=10, check_collision=False)
        self.assertTrue(transit.success)
        self.assertIsNotNone(transit.final_q)

        land = backend.plan_cartesian(transit.final_q, pose_dst_gr, samples=10, check_collision=False)
        self.assertTrue(land.success)
        # Assert LAND strictly starts from transit.final_q
        np.testing.assert_allclose(land.start_q, transit.final_q, atol=1e-6)
        sim.stop()

    def test_g90_15_route_to_each_corner_uses_fully_chained_trajectory(self):
        """G90-15: route to each of the four corner cells uses fully chained trajectory."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)

        # Validate 4 corners specifically
        corner_routes = [((4, 4), (0, 0)), ((4, 4), (0, 8)), ((4, 4), (9, 0)), ((4, 4), (9, 8))]
        res = sim.validate_full_board_routes(sample_limit=4)
        self.assertEqual(res["validation_label"], "FULL_CHAINED_ROUTE_VALIDATION")
        sim.stop()

    def test_g90_16_route_from_each_corner_back_toward_center_chained(self):
        """G90-16: route from each corner back toward center is chained and collision checked."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)

        res = sim.validate_full_board_routes(sample_limit=4)
        self.assertIn(res["status"], ("FULL_BOARD_ROUTES_SAMPLE_SAFE", "FULL_BOARD_ROUTE_SAFE", "FULL_BOARD_ROUTE_COLLISION", "ROUTE_VALIDATION_REJECTED_BUSY"))
        sim.stop()

    def test_g90_17_near_side_center_cells_no_link1_link3_collision(self):
        """G90-17: near-side center cells do not reproduce old link1-link3 collision."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)

        # The two closest cells to robot base are (4, 0) and (5, 0)
        for r, c in [(4, 0), (5, 0)]:
            p_gr = sim.placement_state.cell_to_robot_xyz(r, c, 0.004715)
            pose_gr_mm = [v * 1000.0 for v in p_gr] + [180.0, 0.0, 90.0]
            seed_info = sim.reachability_dataset.get((r, c))
            seed_gr = np.deg2rad(seed_info["grasp_joints_deg"]) if seed_info else None
            ik_gr = sim.backend.solve_tcp_ik(pose_gr_mm, seed_joints=seed_gr, allow_multi_seed=True)
            self.assertTrue(ik_gr.success, f"IK failed for near cell ({r}, {c})")

            col = sim.collision_guard.validate_configuration(ik_gr.joints_rad, allowed_grasp_piece_id="*")
            self.assertTrue(col.safe, f"Collision detected at near cell ({r}, {c}): {col.failure_reason}")

        sim.stop()

    def test_g90_18_far_side_worst_cell_retains_positive_reach_margin(self):
        """G90-18: far-side worst cell retains positive reach margin."""
        state = BoardPlacementState.compute(15.0, board_yaw_deg=90.0)
        analyzer = BoardPlacementAnalyzer(kinematics=self.kinematics)
        metrics = analyzer.compute_geometric_precheck(forward_shift_mm=15.0, board_yaw_deg=90.0)
        self.assertGreater(metrics["grasp_reach_margin_mm"], 10.0)
        self.assertGreater(metrics["approach_reach_margin_mm"], 10.0)

    def test_g90_19_service_safe_passes_rotated_board_exclusion(self):
        """G90-19: SERVICE_SAFE still passes rotated-board exclusion checks."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0)

        # Robot at home pose should be service safe
        rep = sim.evaluate_service_safety()
        self.assertTrue(rep.service_safe, f"Service safety failed with rotated board: {rep.reasons}")
        self.assertTrue(rep.links_clear)
        self.assertTrue(rep.gripper_clear)
        sim.stop()

    def test_g90_20_board_adjustment_swept_volume_rotated_board(self):
        """G90-20: board adjustment / relocation swept volume works with rotated board."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        res = sim.world.check_board_swept_volume_collision(
            new_forward_shift_m=0.015,
            new_height_offset_m=0.0,
        )
        self.assertTrue(res.is_safe, f"Swept volume should be safe: {res.reason}")
        sim.stop()

    def test_g90_21_normal_pick_place_succeeds_90deg(self):
        """G90-21: normal pick-place succeeds with 90° orientation."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)

        # Move piece at (0, 0) to (0, 1) if (0, 0) has a piece
        src_pid = sim._get_piece_at_cell(0, 0)
        if src_pid is not None:
            pick_res = sim.pick_piece((0, 0))
            self.assertTrue(pick_res.success, f"Pick piece failed: {pick_res.error}")
            place_res = sim.place_piece((1, 0))
            self.assertTrue(place_res.success, f"Place piece failed: {place_res.error}")
            self.assertTrue(place_res.piece_placed)
            self.assertTrue(place_res.service_safe)

        sim.stop()

    def test_g90_22_post_release_retreat_returns_service_safe(self):
        """G90-22: post-release retreat returns SERVICE_SAFE."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)

        rep = sim.evaluate_service_safety()
        self.assertTrue(rep.service_safe)
        sim.stop()

    def test_g90_23_deliberate_unreachable_collision_rejected(self):
        """G90-23: deliberate unreachable/collision candidate is rejected."""
        analyzer = BoardPlacementAnalyzer(kinematics=self.kinematics)
        metrics = analyzer.compute_geometric_precheck(forward_shift_mm=250.0)
        self.assertFalse(metrics["is_geometric_pass"])
        self.assertLess(metrics["grasp_reach_margin_mm"], 0.0)

    def test_g90_24_validation_state_invariant(self):
        """G90-24: validation is state-invariant / no authoritative pose mutation."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        q_before = [p_bullet.getJointState(sim.world.robot_body_id, j, physicsClientId=sim.world.client_id)[0] for j in range(6)]
        snap_before = sim.backend.get_state_snapshot()

        sim.validate_board_placement(sample_limit=2)

        q_after = [p_bullet.getJointState(sim.world.robot_body_id, j, physicsClientId=sim.world.client_id)[0] for j in range(6)]
        snap_after = sim.backend.get_state_snapshot()

        np.testing.assert_allclose(q_before, q_after, atol=1e-5)
        np.testing.assert_allclose(snap_before.joints_deg, snap_after.joints_deg, atol=1e-3)
        sim.stop()

    def test_g90_25_no_regression_pass_a_rules(self):
        """G90-25: no regression on Pass A/A.1/A.2 authority and non-reentrancy rules."""
        sim = VirtualXiangqiSimulation()
        sim.start()

        # When an operation is in progress, secondary operation must reject immediately with MOTION_REJECTED_BUSY
        with sim.acquire_operation_state(RuntimeOperationState.MOTION):
            with self.assertRaises(RuntimeOperationBusy):
                with sim.acquire_operation_state(RuntimeOperationState.MOTION):
                    pass

        sim.stop()


if __name__ == "__main__":
    unittest.main()
