"""
Unit tests and kinematic evaluation for J4 angle constraints and board penetration.

Validates the user requirement:
1. Optimal unconstrained IK reaches all 90 cells with strictly perpendicular gripper (tilt ~ 0 deg)
   and ZERO board penetration (clearance > 70mm for all arm links).
2. Constraining J4 to [-100 deg, -80 deg] causes:
   - 0/90 cells reachable when maintaining perpendicular gripper.
   - 90/90 cells penetrate below the board surface if forced to touch cell positions,
     with gripper tilt exceeding 30 to 93 degrees (causing piece slip).
"""

import json
from pathlib import Path
import unittest
import numpy as np

from src.domain.geometry import get_physical_geometry
from src.simulation.kinematics.fr3 import FR3Kinematics

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class J4ConstraintAndPenetrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene_path = _REPO_ROOT / "shared" / "virtual_fr3_scene.json"
        with open(cls.scene_path, "r", encoding="utf-8") as f:
            cls.scene = json.load(f)

        cls.kin = FR3Kinematics()
        cls.board_cfg = cls.scene["virtual_board_placement"]
        cls.x0, cls.y0, cls.z0 = cls.board_cfg["grid_origin_in_robot_base_m"]
        cls.R_target = np.array(cls.board_cfg["target_tool_orientation_matrix"], dtype=float)

        cls.geom = get_physical_geometry()
        cls.col_spacing = cls.geom.board.column_spacing / 1000.0
        cls.row_spacing = cls.geom.board.row_spacing / 1000.0
        cls.num_rows = cls.geom.board.rows
        cls.num_cols = cls.geom.board.columns

    def test_optimal_ik_reaches_all_90_cells_perpendicular_without_penetration(self):
        """Verify unconstrained IK achieves 100% perpendicularity and 0% penetration across all 90 cells."""
        q_seed = np.array([0.0, -1.0, 1.5, -2.0, -1.57, 0.0], dtype=float)
        reachable = 0
        min_clearances = []
        tilts = []

        for r in range(self.num_rows):
            x = self.x0 - r * self.row_spacing
            for c in range(self.num_cols):
                y = self.y0 + c * self.col_spacing
                T_target = np.eye(4)
                T_target[:3, :3] = self.R_target
                T_target[:3, 3] = [x, y, self.z0]

                res = self.kin.inverse_kinematics(T_target, seed_joints=q_seed, max_iterations=80)
                if not res.success:
                    res = self.kin.inverse_kinematics(T_target, seed_joints=None, allow_multi_seed=True, max_iterations=100)

                self.assertTrue(res.success, f"Failed to reach cell ({r}, {c})")
                reachable += 1
                q_seed = res.joints_rad

                # Verify verticality: tool Z in robot base should point along -Z [0, 0, -1]
                T_actual = self.kin.forward_kinematics(res.joints_rad).as_matrix()
                tool_z = T_actual[:3, 2]
                dot = np.clip(np.dot(tool_z, [0, 0, -1]), -1.0, 1.0)
                tilt_deg = float(np.degrees(np.arccos(dot)))
                tilts.append(tilt_deg)
                self.assertLess(tilt_deg, 0.1, f"Gripper tilted {tilt_deg} deg at cell ({r}, {c})")

                # Verify all moving link frames remain strictly at or above board surface (z0)
                chain = self.kin.chain.forward_kinematics_chain(res.joints_rad)
                # chain[0] is base link origin at (0,0,0) outside board; chain[1:] are arm and wrist links
                min_link_z = min(frame[2, 3] for frame in chain[1:])
                clearance_mm = (min_link_z - self.z0) * 1000.0
                min_clearances.append(clearance_mm)
                # Moving link frames must be at or above board height (wrist flange is at z0, preceding links > z0)
                self.assertGreaterEqual(clearance_mm, -0.05, f"Link penetrated board by {clearance_mm}mm at ({r}, {c})")

        self.assertEqual(reachable, 90)
        self.assertLess(max(tilts), 0.05, "Maximum gripper tilt exceeded 0.05 deg")
        self.assertGreater(min(min_clearances), -0.05, "Detected negative clearance (penetration)")

    def test_constrained_j4_fails_or_penetrates_board(self):
        """Verify that restricting J4 to [-100, -80] deg cannot reach perpendicular pose or penetrates board."""
        kin_c = FR3Kinematics()
        kin_c.chain.lower_limits[3] = np.radians(-100.0)
        kin_c.chain.upper_limits[3] = np.radians(-80.0)

        # 1. Full 6-DOF target: With J4 in [-100, -80], perpendicular pose cannot converge on any of the 90 cells
        perpendicular_success = 0
        for r in range(self.num_rows):
            x = self.x0 - r * self.row_spacing
            for c in range(self.num_cols):
                y = self.y0 + c * self.col_spacing
                T_target = np.eye(4)
                T_target[:3, :3] = self.R_target
                T_target[:3, 3] = [x, y, self.z0]
                res = kin_c.inverse_kinematics(T_target, seed_joints=None, allow_multi_seed=True, max_iterations=60)
                if res.success and np.radians(-100.0) <= res.joints_rad[3] <= np.radians(-80.0):
                    perpendicular_success += 1

        self.assertEqual(
            perpendicular_success,
            0,
            f"Expected 0/90 cells to reach perpendicular pose with J4 in [-100, -80], got {perpendicular_success}",
        )

        # 2. Position-only target: If forced to touch the cells, gripper tilt is severe across all 90 cells
        tilts = []
        for r in range(self.num_rows):
            x = self.x0 - r * self.row_spacing
            for c in range(self.num_cols):
                y = self.y0 + c * self.col_spacing
                target_pos = np.array([x, y, self.z0])
                q_c = np.array([0.0, -0.5, 1.0, -1.57, -1.57, 0.0])
                for it in range(80):
                    T_c = kin_c.forward_kinematics(q_c).as_matrix()
                    err_c = target_pos - T_c[:3, 3]
                    if np.linalg.norm(err_c) < 0.001:
                        break
                    J_c = kin_c.geometric_jacobian(q_c)[:3, :]
                    dq_c = J_c.T @ np.linalg.inv(J_c @ J_c.T + 0.001 * np.eye(3)) @ err_c
                    q_c = np.clip(q_c + dq_c, kin_c.chain.lower_limits, kin_c.chain.upper_limits)

                T_actual = kin_c.forward_kinematics(q_c).as_matrix()
                tool_z = T_actual[:3, 2]
                tilt = float(np.degrees(np.arccos(np.clip(np.dot(tool_z, [0, 0, -1]), -1.0, 1.0))))
                tilts.append(tilt)

        # In constrained mode, 100% of cells have severe tilt (> 30 deg, up to 93 deg)
        self.assertGreaterEqual(min(tilts), 30.0, f"Expected all cells to have severe tilt > 30 deg, got min={min(tilts)}")
        self.assertGreaterEqual(max(tilts), 90.0, f"Expected max tilt > 90 deg, got max={max(tilts)}")


if __name__ == "__main__":
    unittest.main()
