"""Trajectory checks against the active board, tool, and collision scene."""

import json
from pathlib import Path
import unittest

import numpy as np

from src.simulation.runtime import VirtualXiangqiSimulation


ROOT = Path(__file__).resolve().parents[2]


class TrajectoryWaypointsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        cls.sim.start()

    @classmethod
    def tearDownClass(cls):
        cls.sim.stop()

    def _pose(self, row, col, height_m, orientation=None):
        xyz = self.sim.cell_to_robot_xyz_m(row, col, height_m)
        return [v * 1000.0 for v in xyz] + list(
            self.sim.target_tool_euler_deg if orientation is None else orientation
        )

    def test_stale_dataset_is_not_used_as_current_waypoints(self):
        dataset = json.loads((ROOT / "shared/cell_reachability_dataset.json").read_text(encoding="utf-8"))
        self.assertEqual(dataset["metadata"]["status"], "STALE/UNVALIDATED")
        self.assertEqual(self.sim.reachability_dataset, {})

    def test_current_grasp_and_approach_endpoints_clear_board(self):
        board_z = self.sim.board_surface_z
        grasp_z = board_z + self.sim.geom.piece_height_mm / 2000.0
        approach_z = board_z + self.sim.placement_state.safe_transit_height_mm / 1000.0
        for row, col in ((0, 0), (4, 4), (9, 0)):
            for name, height in (("grasp", grasp_z), ("approach", approach_z)):
                piece_id = self.sim._get_piece_at_cell(row, col) if name == "grasp" else None
                ik = self.sim.backend.solve_tcp_ik(
                    self._pose(row, col, height),
                    allow_multi_seed=True,
                    allow_alternate_yaw=True,
                    allowed_grasp_piece_id=piece_id,
                )
                self.assertTrue(ik.success, f"{name} IK failed at ({row}, {col})")
                result = self.sim.collision_guard.validate_configuration(
                    ik.joints_rad, allowed_grasp_piece_id=piece_id
                )
                self.assertTrue(result.safe, f"{name} collision at ({row}, {col}): {result.failure_reason}")
                tcp = self.sim.backend._compute_tcp_pose_mm_deg(ik.joints_rad)
                self.assertGreaterEqual(tcp[2] / 1000.0 - board_z, 0.0005)

    def test_cartesian_transit_maintains_safe_height(self):
        board_z = self.sim.board_surface_z
        safe_z = board_z + self.sim.placement_state.safe_transit_height_mm / 1000.0
        start = self.sim.backend.solve_tcp_ik(
            self._pose(0, 0, safe_z), allow_multi_seed=True, allow_alternate_yaw=True
        )
        self.assertTrue(start.success)
        orientation = self.sim.backend._compute_tcp_pose_mm_deg(start.joints_rad)[3:]
        plan = self.sim.backend.plan_cartesian(
            start.joints_rad, self._pose(9, 0, safe_z, orientation), samples=20
        )
        self.assertTrue(plan.success, plan.failure_reason)
        self.assertTrue(plan.collision_safe)
        for q in plan.q_samples:
            tcp_z = self.sim.backend._compute_tcp_pose_mm_deg(q)[2] / 1000.0
            self.assertGreaterEqual(tcp_z, safe_z - 0.001)

    def test_cartesian_lift_stays_over_cell(self):
        row, col = 4, 4
        board_z = self.sim.board_surface_z
        grasp_z = board_z + self.sim.geom.piece_height_mm / 2000.0
        safe_z = board_z + self.sim.placement_state.safe_transit_height_mm / 1000.0
        start = self.sim.backend.solve_tcp_ik(
            self._pose(row, col, grasp_z), allow_multi_seed=True, allow_alternate_yaw=True
        )
        self.assertTrue(start.success)
        start_tcp = self.sim.backend._compute_tcp_pose_mm_deg(start.joints_rad)
        plan = self.sim.backend.plan_cartesian(
            start.joints_rad, self._pose(row, col, safe_z, start_tcp[3:]), samples=20
        )
        self.assertTrue(plan.success, plan.failure_reason)
        self.assertTrue(plan.collision_safe)
        for q in plan.q_samples:
            tcp = self.sim.backend._compute_tcp_pose_mm_deg(q)
            self.assertLess(np.hypot(tcp[0] - start_tcp[0], tcp[1] - start_tcp[1]), 1.0)
            self.assertGreaterEqual(tcp[2] / 1000.0 - board_z, 0.0005)


if __name__ == "__main__":
    unittest.main()
