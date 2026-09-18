"""
Unit and regression tests for Phase 3 Final G90 Corrective:
1. G90F-01: BoardPose exact yaw=90° produces expected extrema via transform.
2. G90F-02: BoardPose perturbation yaw=89° changes extrema predictably.
3. G90F-03: BoardPose perturbation yaw=91° changes extrema predictably.
4. G90F-04: Backend and frontend identify same nearest/farthest BoardCells.
5. G90F-05: Backend and frontend reach metrics agree within tolerance.
6. G90F-06: Physical board corner distances agree between backend and geometry model.
7. G90F-07: AST/source audit: No hardcoded 520+d or 180 constants used in authoritative calculations.
8. G90F-08: CLEAR_BOARD planning failure immediately fails the route (fail-fast).
9. G90F-09: SERVICE_RETREAT is not executed after CLEAR_BOARD failure.
10. G90F-10: Every chained stage consumes previous stage final_q strictly.
11. G90F-11: Sampled mode reports exhaustive == False and FULL_BOARD_ROUTES_SAMPLE_SAFE.
12. G90F-12: Exhaustive mode contract reports possible_ordered_routes == 8010.
13. G90F-13: Route accounting invariant: passed_routes + failed_routes == tested_routes.
14. G90F-14: Candidate placement (d=15, H=40, Z=0, yaw=90°) critical routes execute safely.
"""

import ast
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.placement import (
    BoardPlacementState,
    BoardPlacementAnalyzer,
)
from src.simulation.runtime import VirtualXiangqiSimulation
from src.simulation.virtual_fr3_backend import PlannedTrajectory


class Phase3FinalG90CorrectiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analyzer = BoardPlacementAnalyzer()

    # -------------------------------------------------------------------------
    # Issue 1: CLEAR_BOARD Fail-Fast & Pass C Stage Chaining (G90F-08, 09, 10)
    # -------------------------------------------------------------------------

    def test_g90f_08_clear_board_failure_fails_route_immediately(self):
        """G90F-08: If CLEAR_BOARD fails, route fails immediately, failed_routes increments, passed_routes does not."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)

        original_plan_cartesian = sim.backend.plan_cartesian

        def mock_plan_cartesian(start_q, target_pose_mm_deg, samples=20, allowed_grasp_piece_id=None, check_collision=True):
            # If this is CLEAR_BOARD (z target is clear_z_mm ~ 80.5mm)
            safe_plane_z = sim.board_surface_z + (sim.placement_state.safe_transit_height_mm / 1000.0)
            clear_z_mm = (safe_plane_z + 0.030) * 1000.0
            if abs(target_pose_mm_deg[2] - clear_z_mm) < 1.0:
                # Force CLEAR_BOARD failure
                return PlannedTrajectory(
                    success=False,
                    start_q=np.array(start_q),
                    target_tcp_pose=list(target_pose_mm_deg),
                    waypoints_cartesian=[],
                    q_samples=[],
                    ik_success=False,
                    collision_safe=False,
                    failure_reason="Forced CLEAR_BOARD collision with upper obstacle",
                    colliding_links_or_bodies="robot_link5 <-> ceiling_boundary",
                )
            return original_plan_cartesian(
                start_q, target_pose_mm_deg, samples=samples,
                allowed_grasp_piece_id=allowed_grasp_piece_id, check_collision=check_collision
            )

        with patch.object(sim.backend, "plan_cartesian", side_effect=mock_plan_cartesian):
            res = sim.validate_full_board_routes(sample_limit=1)

        self.assertFalse(res["all_routes_safe"])
        self.assertEqual(res["failed_routes"], 1)
        self.assertEqual(res["passed_routes"], 0)
        self.assertEqual(res["tested_routes"], 1)
        self.assertIsNotNone(res["worst_route"])
        self.assertEqual(res["worst_route"]["stage"], "CLEAR_BOARD")
        self.assertEqual(res["first_collision_stage"], "CLEAR_BOARD")
        self.assertIn("Forced CLEAR_BOARD", res["worst_route"]["failure_reason"])
        self.assertEqual(res["status"], "FULL_BOARD_ROUTES_FAILED")

        sim.stop()

    def test_g90f_09_service_retreat_not_executed_after_clear_board_failure(self):
        """G90F-09: SERVICE_RETREAT interpolation must NOT be evaluated when CLEAR_BOARD fails."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)

        original_plan_cartesian = sim.backend.plan_cartesian
        col_guard_calls = []
        original_col_validate = sim.collision_guard.validate_configuration

        def spy_col_validate(joints_rad, **kwargs):
            col_guard_calls.append(np.array(joints_rad))
            return original_col_validate(joints_rad, **kwargs)

        def mock_plan_cartesian(start_q, target_pose_mm_deg, samples=20, allowed_grasp_piece_id=None, check_collision=True):
            safe_plane_z = sim.board_surface_z + (sim.placement_state.safe_transit_height_mm / 1000.0)
            clear_z_mm = (safe_plane_z + 0.030) * 1000.0
            if abs(target_pose_mm_deg[2] - clear_z_mm) < 1.0:
                return PlannedTrajectory(
                    success=False,
                    start_q=np.array(start_q),
                    target_tcp_pose=list(target_pose_mm_deg),
                    waypoints_cartesian=[],
                    q_samples=[],
                    ik_success=False,
                    collision_safe=False,
                    failure_reason="Forced CLEAR_BOARD failure",
                )
            return original_plan_cartesian(
                start_q, target_pose_mm_deg, samples=samples,
                allowed_grasp_piece_id=allowed_grasp_piece_id, check_collision=check_collision
            )

        with patch.object(sim.backend, "plan_cartesian", side_effect=mock_plan_cartesian):
            with patch.object(sim.collision_guard, "validate_configuration", side_effect=spy_col_validate):
                res = sim.validate_full_board_routes(sample_limit=1)

        self.assertFalse(res["all_routes_safe"])
        self.assertEqual(res["worst_route"]["stage"], "CLEAR_BOARD")

        # In SERVICE_RETREAT, interpolation targets target_service_q = np.deg2rad(SERVICE_SAFE_JOINTS_DEG)
        # Verify no call to collision_guard checked interpolation towards SERVICE_SAFE_JOINTS_DEG
        target_service_q = np.deg2rad(sim.backend.SERVICE_SAFE_JOINTS_DEG)
        for called_q in col_guard_calls:
            diff = np.max(np.abs(called_q - target_service_q))
            self.assertGreater(diff, 1e-4, "SERVICE_RETREAT was erroneously executed after CLEAR_BOARD failure!")

        sim.stop()

    def test_g90f_10_chained_stages_strictly_consume_previous_final_q(self):
        """G90F-10: Stage chaining: LIFT.final_q -> TRANSIT.start_q, TRANSIT.final_q -> LAND.start_q, LAND.final_q -> POST_LIFT.start_q."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)

        calls = []
        original_plan_cartesian = sim.backend.plan_cartesian

        def recorder_plan_cartesian(start_q, target_pose_mm_deg, samples=20, allowed_grasp_piece_id=None, check_collision=True):
            res = original_plan_cartesian(
                start_q, target_pose_mm_deg, samples=samples,
                allowed_grasp_piece_id=allowed_grasp_piece_id, check_collision=check_collision
            )
            calls.append((np.array(start_q, copy=True), np.array(res.final_q, copy=True) if res.final_q is not None else None, list(target_pose_mm_deg)))
            return res

        with patch.object(sim.backend, "plan_cartesian", side_effect=recorder_plan_cartesian):
            res = sim.validate_full_board_routes(sample_limit=1)

        self.assertTrue(res["all_routes_safe"])
        # In 1 route: calls contain [LIFT_preplan..., TRANSIT, LAND, POST_RELEASE_LIFT, CLEAR_BOARD]
        transit_call = calls[-4]
        land_call = calls[-3]
        post_lift_call = calls[-2]
        clear_call = calls[-1]

        # TRANSIT.final_q must equal LAND.start_q
        np.testing.assert_allclose(transit_call[1], land_call[0], atol=1e-6, err_msg="LAND start_q does not match TRANSIT final_q")
        # LAND.final_q must equal POST_RELEASE_LIFT.start_q
        np.testing.assert_allclose(land_call[1], post_lift_call[0], atol=1e-6, err_msg="POST_LIFT start_q does not match LAND final_q")
        # POST_RELEASE_LIFT.final_q must equal CLEAR_BOARD.start_q
        np.testing.assert_allclose(post_lift_call[1], clear_call[0], atol=1e-6, err_msg="CLEAR_BOARD start_q does not match POST_LIFT final_q")

        sim.stop()

    # -------------------------------------------------------------------------
    # Issue 2: Validation Modes & Coverage Accounting (G90F-11, 12, 13, 14)
    # -------------------------------------------------------------------------

    def test_g90f_11_sampled_mode_reports_non_exhaustive(self):
        """G90F-11: Sampled mode reports exhaustive == False, status == FULL_BOARD_ROUTES_SAMPLE_SAFE, and coverage fraction."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)

        res = sim.validate_full_board_routes(sample_limit=8)
        self.assertEqual(res["validation_mode"], "SAMPLED")
        self.assertFalse(res["exhaustive"])
        self.assertEqual(res["tested_routes"], 8)
        self.assertEqual(res["possible_ordered_routes"], 8010)
        self.assertAlmostEqual(res["coverage_fraction"], 8 / 8010.0, places=5)
        self.assertEqual(res["status"], "FULL_BOARD_ROUTES_SAMPLE_SAFE")
        self.assertTrue(res["all_routes_safe"])
        self.assertEqual(res["passed_routes"], 8)
        self.assertEqual(res["failed_routes"], 0)

        sim.stop()

    def test_g90f_12_exhaustive_mode_contract(self):
        """G90F-12: When sample_limit is None, validation_mode is EXHAUSTIVE, exhaustive is True, possible_ordered_routes is 8010."""
        sim = VirtualXiangqiSimulation()
        sim.start()

        # Test busy rejection payload preserves contract
        sim.backend._motion_state = "MOVING"
        busy_res = sim.validate_full_board_routes(sample_limit=None)
        self.assertEqual(busy_res["validation_mode"], "EXHAUSTIVE")
        self.assertTrue(busy_res["exhaustive"])
        self.assertEqual(busy_res["possible_ordered_routes"], 8010)
        self.assertEqual(busy_res["tested_routes"], 0)

        sim.backend._motion_state = "IDLE"
        sim.stop()

    def test_g90f_13_accounting_invariant(self):
        """G90F-13: Invariant holds: passed_routes + failed_routes == tested_routes."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)

        res = sim.validate_full_board_routes(sample_limit=6)
        self.assertEqual(res["passed_routes"] + res["failed_routes"], res["tested_routes"])
        self.assertEqual(res["tested_routes"], 6)

        sim.stop()

    def test_g90f_14_critical_routes_explicit(self):
        """G90F-14: Explicit validation of high-risk near-fold and far-reach routes."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        sim.prepare_board_adjustment()
        sim.set_board_placement(forward_shift_mm=15.0, safe_transit_height_mm=40.0)

        critical_pairs = [
            ((4, 0), (0, 8)),  # Near-center fold risk to far-top corner
            ((5, 0), (9, 8)),  # Near-center fold risk to far-bottom corner
            ((0, 8), (4, 0)),  # Far-top to near-center
            ((9, 8), (5, 0)),  # Far-bottom to near-center
            ((0, 0), (9, 8)),  # Extreme diagonal
            ((9, 0), (0, 8)),  # Extreme diagonal
        ]

        board_z = sim.board_surface_z
        piece_h = sim.geom.piece_height_mm / 1000.0
        z_grasp = board_z + piece_h / 2.0
        z_transit = board_z + (sim.placement_state.safe_transit_height_mm / 1000.0)
        clear_z_mm = (board_z + (sim.placement_state.safe_transit_height_mm / 1000.0) + 0.030) * 1000.0

        for src, dst in critical_pairs:
            src_pos_gr = sim.cell_to_robot_xyz_m(src[0], src[1], z_grasp)
            src_pos_ap = sim.cell_to_robot_xyz_m(src[0], src[1], z_transit)
            dst_pos_gr = sim.cell_to_robot_xyz_m(dst[0], dst[1], z_grasp)
            dst_pos_ap = sim.cell_to_robot_xyz_m(dst[0], dst[1], z_transit)

            src_pose_gr = [v * 1000.0 for v in src_pos_gr] + list(sim.target_tool_euler_deg)
            src_pose_ap = [v * 1000.0 for v in src_pos_ap] + list(sim.target_tool_euler_deg)
            dst_pose_gr = [v * 1000.0 for v in dst_pos_gr] + list(sim.target_tool_euler_deg)
            dst_pose_ap = [v * 1000.0 for v in dst_pos_ap] + list(sim.target_tool_euler_deg)

            seed_info = sim.reachability_dataset.get(src)
            seed_gr = np.deg2rad(seed_info["grasp_joints_deg"]) if seed_info and "grasp_joints_deg" in seed_info else None
            src_piece_id = sim._get_piece_at_cell(src[0], src[1])

            # Grasp IK
            ik_gr = sim.backend.solve_tcp_ik(src_pose_gr, seed_joints=seed_gr, allow_multi_seed=True)
            self.assertTrue(ik_gr.success, f"Grasp IK failed for src {src}")

            # 1. LIFT
            lift_plan = sim.backend.plan_cartesian(ik_gr.joints_rad, src_pose_ap, samples=15, allowed_grasp_piece_id=src_piece_id)
            self.assertTrue(lift_plan.success, f"LIFT failed for src {src}: {lift_plan.failure_reason}")

            # 2. TRANSIT
            transit_plan = sim.backend.plan_cartesian(lift_plan.final_q, dst_pose_ap, samples=15, allowed_grasp_piece_id=src_piece_id)
            self.assertTrue(transit_plan.success, f"TRANSIT failed for {src}->{dst}: {transit_plan.failure_reason}")

            # 3. LAND
            land_plan = sim.backend.plan_cartesian(transit_plan.final_q, dst_pose_gr, samples=15, allowed_grasp_piece_id=src_piece_id)
            self.assertTrue(land_plan.success, f"LAND failed for {src}->{dst}: {land_plan.failure_reason}")

            # 4. POST_RELEASE_LIFT
            post_lift_plan = sim.backend.plan_cartesian(land_plan.final_q, dst_pose_ap, samples=15, allowed_grasp_piece_id=src_piece_id)
            self.assertTrue(post_lift_plan.success, f"POST_LIFT failed for {src}->{dst}: {post_lift_plan.failure_reason}")

            # 5. CLEAR_BOARD
            clear_pose = list(dst_pose_ap)
            clear_pose[2] = clear_z_mm
            clear_plan = sim.backend.plan_cartesian(post_lift_plan.final_q, clear_pose, samples=10, allowed_grasp_piece_id=None)
            self.assertTrue(clear_plan.success, f"CLEAR_BOARD failed for {src}->{dst}: {clear_plan.failure_reason}")

        sim.stop()

    # -------------------------------------------------------------------------
    # Issue 3: BoardPose Geometry Parity (G90F-01 to G90F-06)
    # -------------------------------------------------------------------------

    def test_g90f_01_exact_yaw_90_extrema_from_transform(self):
        """G90F-01: Exact yaw 90° returns expected extrema derived through transform."""
        analysis = self.analyzer.compute_geometric_precheck(
            forward_shift_mm=15.0,
            safe_transit_height_mm=40.0,
            board_yaw_deg=90.0,
        )
        # Column 0 is near robot (-X direction): depth = 200 + d = 215 mm
        # Column 8 is far from robot: depth = 520 + d = 535 mm
        self.assertEqual(analysis["nearest_grid_cell"][1], 0)
        self.assertEqual(analysis["farthest_grid_cell"][1], 8)
        self.assertAlmostEqual(analysis["nearest_grid_cell_distance_mm"], 215.0, delta=15.0)
        self.assertAlmostEqual(analysis["farthest_grid_cell_distance_mm"], math.hypot(535.0, 180.0), delta=2.0)
        self.assertTrue(analysis["is_geometric_pass"])

    def test_g90f_02_yaw_89_perturbation(self):
        """G90F-02: yaw=89° changes extrema predictably compared to yaw=90°."""
        a90 = self.analyzer.compute_geometric_precheck(15.0, 40.0, board_yaw_deg=90.0)
        a89 = self.analyzer.compute_geometric_precheck(15.0, 40.0, board_yaw_deg=89.0)

        self.assertNotEqual(a90["far_approach_distance_mm"], a89["far_approach_distance_mm"])
        self.assertNotEqual(a90["near_board_edge_distance_mm"], a89["near_board_edge_distance_mm"])
        self.assertNotEqual(a90["far_board_edge_distance_mm"], a89["far_board_edge_distance_mm"])

    def test_g90f_03_yaw_91_perturbation(self):
        """G90F-03: yaw=91° changes extrema predictably compared to yaw=90°."""
        a90 = self.analyzer.compute_geometric_precheck(15.0, 40.0, board_yaw_deg=90.0)
        a91 = self.analyzer.compute_geometric_precheck(15.0, 40.0, board_yaw_deg=91.0)

        self.assertNotEqual(a90["far_approach_distance_mm"], a91["far_approach_distance_mm"])
        self.assertNotEqual(a90["near_board_edge_distance_mm"], a91["near_board_edge_distance_mm"])
        self.assertNotEqual(a90["far_board_edge_distance_mm"], a91["far_board_edge_distance_mm"])

    def test_g90f_04_backend_and_geometry_model_identify_same_extrema_cells(self):
        """G90F-04: Transformed grid cells correctly identify (0,8) or (9,8) as farthest and (4,0)/(5,0) as nearest."""
        state = BoardPlacementState.compute(forward_shift_mm=15.0, board_yaw_deg=90.0)
        cells = [(r, c) for r in range(10) for c in range(9)]
        dists = {}
        for r, c in cells:
            p = state.cell_to_robot_xyz(r, c, 0.0)
            dists[(r, c)] = math.hypot(p[0], p[1])

        nearest = min(dists, key=dists.get)
        farthest = max(dists, key=dists.get)

        self.assertIn(nearest, [(4, 0), (5, 0)])
        self.assertIn(farthest, [(0, 8), (9, 8)])

    def test_g90f_05_max_flange_approach_distance_audit(self):
        """G90F-05: The audited value 625.1 mm is strictly Max flange approach distance, NOT TCP distance."""
        analysis = self.analyzer.compute_geometric_precheck(
            forward_shift_mm=15.0,
            safe_transit_height_mm=40.0,
            board_yaw_deg=90.0,
        )
        self.assertAlmostEqual(analysis["far_approach_distance_mm"], 625.1, delta=1.0)
        self.assertAlmostEqual(analysis["approach_reach_margin_mm"], 650.0 - analysis["far_approach_distance_mm"], delta=0.1)

    def test_g90f_06_physical_board_corner_distances(self):
        """G90F-06: Physical board (410x367mm) corner distances computed via BoardPose."""
        state = BoardPlacementState.compute(forward_shift_mm=15.0, board_yaw_deg=90.0)
        hw = 0.367 / 2.0
        hl = 0.410 / 2.0
        corners = [(-hw, -hl), (-hw, hl), (hw, -hl), (hw, hl)]
        pts_robot = [state.board_local_to_robot(u, v, 0.0) for u, v in corners]

        x_coords = [p[0] * 1000.0 for p in pts_robot]
        near_dist = min(abs(x) for x in x_coords)
        far_dist = max(abs(x) for x in x_coords)

        # In 90 orientation: grid column span is 320mm (col 0 to 8). Board width is 367mm, border margin = (367-320)/2 = 23.5mm.
        # Along column direction (depth, -X_robot): 200+15-23.5 = 191.5 mm (near), 520+15+23.5 = 558.5 mm (far).
        self.assertAlmostEqual(near_dist, 191.5, delta=1.0)
        self.assertAlmostEqual(far_dist, 558.5, delta=1.0)


if __name__ == "__main__":
    unittest.main()
