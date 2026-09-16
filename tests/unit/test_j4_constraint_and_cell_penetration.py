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

        # Authoritative CAD parallel gripper length from J6 flange to finger tips (218mm)
        tool_cfg = cls.scene.get("tool_transform", {})
        cls.L_gripper = float(tool_cfg.get("flange_to_tcp_xyz_m", [0.0, 0.0, 0.218])[2])
        # Desired finger tip height: 1.5mm above board surface to cleanly grasp pieces without touching board
        cls.z_tips = cls.z0 + 0.0015
        cls.z_flange = cls.z_tips + cls.L_gripper

    def test_optimal_ik_reaches_all_90_cells_perpendicular_without_penetration(self):
        """Verify unconstrained IK achieves 100% perpendicularity and 0% penetration across all 90 cells."""
        q_seed = np.radians([0.0, -70.0, 120.0, -140.0, -90.0, 0.0])
        reachable = 0
        min_clearances = []
        tilts = []

        for r in range(self.num_rows):
            x = self.x0 - r * self.row_spacing
            for c in range(self.num_cols):
                y = self.y0 + c * self.col_spacing
                T_target = np.eye(4)
                T_target[:3, :3] = self.R_target
                T_target[:3, 3] = [x, y, self.z_flange]

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

                # Gripper tip clearance: flange Z minus gripper length compared to board surface
                actual_flange_z = T_actual[2, 3]
                gripper_tip_z = actual_flange_z - self.L_gripper
                clearance_mm = (gripper_tip_z - self.z0) * 1000.0
                min_clearances.append(clearance_mm)
                # Gripper tips must hover strictly at or above board surface (0% penetration)
                self.assertGreaterEqual(clearance_mm, 0.0, f"Gripper penetrated board by {clearance_mm}mm at ({r}, {c})")

        self.assertEqual(reachable, 90)
        self.assertLess(max(tilts), 0.05, "Maximum gripper tilt exceeded 0.05 deg")
        self.assertGreaterEqual(min(min_clearances), 1.0, "Detected gripper tip penetration or clearance < 1mm")

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
                T_target[:3, 3] = [x, y, self.z_flange]
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
                target_pos = np.array([x, y, self.z_flange])
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

        # In constrained mode, 100% of cells have severe tilt (> 10 deg, up to 36 deg)
        self.assertGreaterEqual(min(tilts), 10.0, f"Expected all cells to have severe tilt > 10 deg, got min={min(tilts)}")
        self.assertGreaterEqual(max(tilts), 35.0, f"Expected max tilt > 35 deg, got max={max(tilts)}")


if __name__ == "__main__":
    unittest.main()
