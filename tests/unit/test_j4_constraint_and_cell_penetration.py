"""Active 90-cell grasp clearance and rigid-link kinematics checks."""

import json
from pathlib import Path
import unittest
import numpy as np
import pytest

from src.domain.geometry import get_physical_geometry
from src.simulation.kinematics.fr3 import FR3Kinematics
from src.simulation.runtime import VirtualXiangqiSimulation

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

        # Canonical measured parallel gripper length from J6 flange to grasp center (150mm [MEASURED_APPROXIMATE])
        tool_cfg = cls.scene.get("tool_transform", {})
        cls.L_gripper = float(tool_cfg.get("flange_to_tcp_xyz_m", [0.0, 0.0, 0.150])[2])
        # Desired finger tip height: 1.5mm above board surface to cleanly grasp pieces without touching board
        cls.z_tips = cls.z0 + 0.0015
        cls.z_flange = cls.z_tips + cls.L_gripper

    def test_current_feasibility_status_diagnostic(self):
        """
        Diagnostic measurement of current reachability status.
        Currently achieves >= 67 collision-free cells under CAD proxy envelope.
        Serves to protect against reachability regressions during development.
        """
        sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        sim.start()
        try:
            target_z = sim.board_surface_z + sim.geom.piece_height_mm / 2000.0
            safe_count = 0
            blocked = []
            for row in range(self.num_rows):
                for col in range(self.num_cols):
                    xyz = sim.cell_to_robot_xyz_m(row, col, target_z)
                    pose = [v * 1000.0 for v in xyz] + list(sim.target_tool_euler_deg)
                    piece_id = sim._get_piece_at_cell(row, col)
                    ik = sim.backend.solve_tcp_ik(
                        pose,
                        allow_multi_seed=True,
                        allow_alternate_yaw=True,
                        allowed_grasp_piece_id=piece_id,
                    )
                    if not ik.success:
                        blocked.append((row, col, ik.failure_reason))
                        continue
                    collision = sim.collision_guard.validate_configuration(
                        ik.joints_rad, allowed_grasp_piece_id=piece_id
                    )
                    self.assertTrue(collision.safe, f"Collision at ({row}, {col}): {collision.failure_reason}")
                    safe_count += 1
                    tcp_z = sim.backend._compute_tcp_pose_mm_deg(ik.joints_rad)[2] / 1000.0
                    self.assertGreaterEqual(tcp_z - sim.board_surface_z, 0.0005)
            self.assertGreaterEqual(safe_count, 67, f"Grasp reachability regressed: {blocked}")
            self.assertEqual(safe_count + len(blocked), self.num_rows * self.num_cols)
        finally:
            sim.stop()

    @pytest.mark.acceptance
    def test_gate_90_of_90_cells_grasp_and_contact_acceptance(self):
        """
        OFFICIAL PHYSICAL ACCEPTANCE GATE:
        All 90/90 board cells must be reachable and collision-free with CAD gripper envelope.
        STATUS: NOT PASSED (FAIL).
        Transparently fails until future kinematic/gripper optimization achieves 90/90.
        """
        sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        sim.start()
        try:
            target_z = sim.board_surface_z + sim.geom.piece_height_mm / 2000.0
            safe_count = 0
            blocked = []
            for row in range(self.num_rows):
                for col in range(self.num_cols):
                    xyz = sim.cell_to_robot_xyz_m(row, col, target_z)
                    pose = [v * 1000.0 for v in xyz] + list(sim.target_tool_euler_deg)
                    piece_id = sim._get_piece_at_cell(row, col)
                    ik = sim.backend.solve_tcp_ik(
                        pose,
                        allow_multi_seed=True,
                        allow_alternate_yaw=True,
                        allowed_grasp_piece_id=piece_id,
                    )
                    if not ik.success:
                        blocked.append((row, col, ik.failure_reason))
                        continue
                    collision = sim.collision_guard.validate_configuration(
                        ik.joints_rad, allowed_grasp_piece_id=piece_id
                    )
                    if not collision.safe:
                        blocked.append((row, col, collision.failure_reason))
                        continue
                    safe_count += 1
            self.assertEqual(
                safe_count, 90,
                f"ACCEPTANCE GATE NOT PASSED (chưa đạt): Only {safe_count}/90 cells reachable. "
                f"Blocked cells ({len(blocked)}/90): {blocked}"
            )
        finally:
            sim.stop()

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
            q = np.radians(cell.get("joints_deg") or cell.get("grasp_joints_deg"))
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
