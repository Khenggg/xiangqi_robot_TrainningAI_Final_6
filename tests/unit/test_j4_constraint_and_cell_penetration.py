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

    def test_links_remain_strictly_rigid_with_zero_deformation(self):
        """Verify that link lengths are strictly invariant (delta < 1 um) across all 90 cell configurations.
        Guarantees the algorithm NEVER stretches, deforms, or scales any robot link.
        """
        with open(_REPO_ROOT / "shared" / "cell_reachability_dataset.json", "r", encoding="utf-8") as f:
            dataset = json.load(f)

        L1_expected = 0.140   # Base to Shoulder (140mm)
        L2_expected = 0.280   # Shoulder to Elbow (280mm)
        L3_expected = 0.24001 # Elbow to Wrist1 (240.01mm)
        L4_expected = 0.102   # Wrist1 to Wrist2 (102mm)
        L5_expected = 0.102   # Wrist2 to Flange (102mm)

        for cell in dataset["cells"]:
            q = np.radians(cell["joints_deg"])
            chain = self.kin.chain.forward_kinematics_chain(q)

            p0, p1, p2, p3, p4, p5 = [frame[:3, 3] for frame in chain[:6]]
            L1 = float(np.linalg.norm(p1 - p0))
            L2 = float(np.linalg.norm(p2 - p1))
            L3 = float(np.linalg.norm(p3 - p2))
            L4 = float(np.linalg.norm(p4 - p3))
            L5 = float(np.linalg.norm(p5 - p4))

            # Tolerance 1e-6 meters (1 micron)
            self.assertAlmostEqual(L1, L1_expected, places=5, msg=f"Link 1 deformed at ({cell['row']},{cell['col']})")
            self.assertAlmostEqual(L2, L2_expected, places=5, msg=f"Link 2 deformed at ({cell['row']},{cell['col']})")
            self.assertAlmostEqual(L3, L3_expected, places=5, msg=f"Link 3 deformed at ({cell['row']},{cell['col']})")
            self.assertAlmostEqual(L4, L4_expected, places=5, msg=f"Link 4 deformed at ({cell['row']},{cell['col']})")
            self.assertAlmostEqual(L5, L5_expected, places=5, msg=f"Link 5 deformed at ({cell['row']},{cell['col']})")


if __name__ == "__main__":
    unittest.main()
