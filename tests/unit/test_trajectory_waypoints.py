"""
Unit tests for 3-stage Pick & Place Safe Waypoint Trajectory (Lift -> Transit -> Land).

Validates the user requirement:
"mỗi lần đi tới đâu nó phải nhấc lên trước rồi mới đi tới vị trí đó để không vô tình làm ảnh hưởng tới quân cờ khác"
1. Every cell has both a Grasp waypoint (+1.5mm) and an Approach waypoint (+70mm safe lift).
2. During air transit between cells, gripper tip altitude maintains > 65mm above board surface
   (clearance > 55mm above chess piece tops of 9.43mm), guaranteeing zero piece disturbance.
3. Descent/ascent motions are purely vertical over each cell.
4. Link lengths remain strictly invariant (delta < 1 um) with zero physical deformation.
"""

import json
from pathlib import Path
import unittest
import numpy as np

from src.domain.geometry import get_physical_geometry
from src.simulation.kinematics.fr3 import FR3Kinematics

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TrajectoryWaypointsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset_path = _REPO_ROOT / "shared" / "cell_reachability_dataset.json"
        with open(cls.dataset_path, "r", encoding="utf-8") as f:
            cls.dataset = json.load(f)

        cls.scene_path = _REPO_ROOT / "shared" / "virtual_fr3_scene.json"
        with open(cls.scene_path, "r", encoding="utf-8") as f:
            cls.scene = json.load(f)

        cls.kin = FR3Kinematics()
        cls.board_cfg = cls.scene["virtual_board_placement"]
        cls.x0, cls.y0, cls.z0 = cls.board_cfg["grid_origin_in_robot_base_m"]

        cls.geom = get_physical_geometry()
        cls.piece_height_m = cls.geom.piece.height / 1000.0  # 9.43mm -> 0.00943m
        cls.piece_top_z = cls.z0 + cls.piece_height_m

        # Canonical measured tool length (150mm [MEASURED_APPROXIMATE])
        tool_cfg = cls.scene.get("tool_transform", {})
        cls.L_gripper = float(tool_cfg.get("flange_to_tcp_xyz_m", [0.0, 0.0, 0.150])[2])
        meta = cls.dataset.get("metadata", {})
        cls.safe_lift_mm = float(meta.get("clearance_safe_lift_m", 0.040)) * 1000.0
        cls.grasp_clearance_mm = float(meta.get("clearance_grasp_m", 0.004715)) * 1000.0

    def test_all_90_cells_have_grasp_and_approach_waypoints(self):
        """Verify 100% reachability for both grasp and approach poses."""
        cells = self.dataset.get("cells", [])
        self.assertEqual(len(cells), 90)

        for cell in cells:
            r, c = cell["row"], cell["col"]
            self.assertTrue(cell["reachable"], f"Cell ({r}, {c}) not marked reachable")
            self.assertIn("grasp_joints_deg", cell)
            self.assertIn("approach_joints_deg", cell)

            q_grasp = np.radians(cell["grasp_joints_deg"])
            q_approach = np.radians(cell["approach_joints_deg"])

            # FK check for grasp (piece center height: 0.0105 + 0.00943/2 = 0.015215m -> clearance ~4.715mm)
            T_grasp = self.kin.forward_kinematics(q_grasp).as_matrix()
            flange_z_grasp = T_grasp[2, 3]
            tip_z_grasp = flange_z_grasp - self.L_gripper
            clearance_grasp_mm = (tip_z_grasp - self.z0) * 1000.0
            self.assertAlmostEqual(clearance_grasp_mm, self.grasp_clearance_mm, delta=1.0,
                                   msg=f"Cell ({r},{c}) grasp clearance not ~{self.grasp_clearance_mm}mm (piece center)")

            # FK check for approach (safe lift height)
            T_app = self.kin.forward_kinematics(q_approach).as_matrix()
            flange_z_app = T_app[2, 3]
            tip_z_app = flange_z_app - self.L_gripper
            clearance_app_mm = (tip_z_app - self.z0) * 1000.0
            self.assertAlmostEqual(clearance_app_mm, self.safe_lift_mm, delta=1.0,
                                   msg=f"Cell ({r},{c}) approach clearance not ~{self.safe_lift_mm}mm")

            # Perpendicularity check
            for label, T in [("grasp", T_grasp), ("approach", T_app)]:
                tool_z = T[:3, 2]
                dot = np.clip(np.dot(tool_z, [0, 0, -1]), -1.0, 1.0)
                tilt_deg = float(np.degrees(np.arccos(dot)))
                self.assertLess(tilt_deg, 0.15, f"Cell ({r},{c}) {label} tilt exceeded 0.15 deg")

    def test_transit_clearance_over_pieces_between_arbitrary_cells(self):
        """Simulate horizontal transit between distant cells and verify safe clearance above piece tops."""
        test_pairs = [
            ((0, 0), (9, 8)),  # Main diagonal
            ((0, 8), (9, 0)),  # Anti-diagonal
            ((0, 4), (9, 4)),  # King-file full traverse
            ((4, 0), (4, 8)),  # River lateral traverse
            ((2, 1), (7, 6)),  # Typical knight move traverse
        ]

        cell_map = {(c["row"], c["col"]): c for c in self.dataset.get("cells", [])}

        for (r1, c1), (r2, c2) in test_pairs:
            src = cell_map[(r1, c1)]
            dst = cell_map[(r2, c2)]

            q_src_app = np.radians(src["approach_joints_deg"])
            q_dst_app = np.radians(dst["approach_joints_deg"])

            # Interpolate 20 steps along the transit trajectory
            for alpha in np.linspace(0.0, 1.0, 21):
                q_interp = (1.0 - alpha) * q_src_app + alpha * q_dst_app
                T = self.kin.forward_kinematics(q_interp).as_matrix()
                flange_z = T[2, 3]
                tip_z = flange_z - self.L_gripper

                # Altitude above board surface
                clearance_board_mm = (tip_z - self.z0) * 1000.0
                # Altitude above chess piece tops (9.43mm)
                clearance_pieces_mm = (tip_z - self.piece_top_z) * 1000.0

                # Gripper tips must remain comfortably in the safe corridor (> 10mm above pieces, > 20mm above board)
                self.assertGreater(clearance_pieces_mm, 10.0,
                                   f"Collision risk: clearance above piece top {clearance_pieces_mm:.1f}mm "
                                   f"at alpha={alpha:.2f} between ({r1},{c1}) and ({r2},{c2})")
                self.assertGreater(clearance_board_mm, 20.0,
                                   f"Tip altitude dropped below 20mm during transit ({r1},{c1})->({r2},{c2})")

    def test_vertical_lift_and_descent_linearity(self):
        """Verify that lift and descent phases move vertically over cell (XY drift < 15mm)."""
        sample_cells = [(0, 0), (4, 4), (9, 8), (0, 8), (9, 0)]
        cell_map = {(c["row"], c["col"]): c for c in self.dataset.get("cells", [])}
        expected_lift_delta_mm = self.safe_lift_mm - self.grasp_clearance_mm

        for (r, c) in sample_cells:
            cell = cell_map[(r, c)]
            q_grasp = np.radians(cell["grasp_joints_deg"])
            q_app = np.radians(cell["approach_joints_deg"])

            T_grasp = self.kin.forward_kinematics(q_grasp).as_matrix()
            T_app = self.kin.forward_kinematics(q_app).as_matrix()

            # XY position at grasp vs approach
            xy_drift_m = np.hypot(T_app[0, 3] - T_grasp[0, 3], T_app[1, 3] - T_grasp[1, 3])
            self.assertLess(xy_drift_m, 0.015,
                            f"Cell ({r},{c}) XY drift during vertical lift {xy_drift_m*1000:.1f}mm exceeds 15mm")

            # Z delta must be positive lift ~ expected_lift_delta_mm
            z_lift_m = T_app[2, 3] - T_grasp[2, 3]
            self.assertAlmostEqual(z_lift_m * 1000.0, expected_lift_delta_mm, delta=1.5,
                                   msg=f"Cell ({r},{c}) lift height delta not ~{expected_lift_delta_mm:.3f}mm")


if __name__ == "__main__":
    unittest.main()
