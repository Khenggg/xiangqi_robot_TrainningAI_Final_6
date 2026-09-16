"""Integration test for Three.js viewer schema binding.

Verifies that:
1. shared/robot_profiles/fr3.json has exact fields expected by robot-3d-viewer/main.mjs
   (origin_xyz_m, origin_rpy_rad, 6 joints, all finite floats).
2. shared/virtual_fr3_scene.json has exact fields expected by robot-3d-viewer/board.mjs
   and main.mjs (robot_base_to_3d_world.rotation_matrix, board_center_in_3d_world_m).
3. Running node tests/unit/test_viewer_profile_binding.mjs succeeds without error.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class ViewerProfileBindingTests(unittest.TestCase):
    def setUp(self):
        self.fr3_path = _PROJECT_ROOT / "shared" / "robot_profiles" / "fr3.json"
        self.scene_path = _PROJECT_ROOT / "shared" / "virtual_fr3_scene.json"

    def test_fr3_json_schema_matches_viewer_requirements(self):
        self.assertTrue(self.fr3_path.exists())
        with open(self.fr3_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data.get("robot_model"), "FR3")
        joints = data.get("joints")
        self.assertIsInstance(joints, list)
        self.assertEqual(len(joints), 6)

        for idx, j in enumerate(joints):
            # Must have origin_xyz_m and origin_rpy_rad
            self.assertIn("origin_xyz_m", j, f"Joint {idx} must have origin_xyz_m")
            self.assertIn("origin_rpy_rad", j, f"Joint {idx} must have origin_rpy_rad")

            xyz = j["origin_xyz_m"]
            rpy = j["origin_rpy_rad"]

            self.assertEqual(len(xyz), 3, f"Joint {idx} origin_xyz_m must be length 3")
            self.assertEqual(len(rpy), 3, f"Joint {idx} origin_rpy_rad must be length 3")

            for val in xyz:
                self.assertIsInstance(val, (int, float))
            for val in rpy:
                self.assertIsInstance(val, (int, float))

    def test_virtual_scene_json_matches_viewer_requirements(self):
        self.assertTrue(self.scene_path.exists())
        with open(self.scene_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Coordinate frame check
        base_to_world = data.get("robot_base_to_3d_world", {})
        rot = base_to_world.get("rotation_matrix")
        trans = base_to_world.get("translation_m")

        self.assertIsInstance(rot, list)
        self.assertEqual(len(rot), 3)
        for row in rot:
            self.assertEqual(len(row), 3)

        self.assertIsInstance(trans, list)
        self.assertEqual(len(trans), 3)

        # Board placement check
        placement = data.get("virtual_board_placement", {})
        center_world = placement.get("board_center_in_3d_world_m")
        self.assertIsInstance(center_world, list)
        self.assertEqual(len(center_world), 3)
        self.assertEqual(center_world, [0.0, 0.05, 0.36])

        grid_robot = placement.get("grid_origin_in_robot_base_m")
        self.assertIsInstance(grid_robot, list)
        self.assertEqual(len(grid_robot), 3)
        self.assertEqual(grid_robot, [-0.18, -0.16, 0.05])

        grid_world = placement.get("grid_origin_in_3d_world_m")
        self.assertIsInstance(grid_world, list)
        self.assertEqual(len(grid_world), 3)
        self.assertEqual(grid_world, [0.16, 0.05, 0.18])

        # Mathematical transformation consistency: R * p_robot_origin + t == p_world_origin
        import numpy as np
        R = np.array(rot, dtype=float)
        t = np.array(trans, dtype=float)
        p_robot_origin = np.array(grid_robot, dtype=float)
        p_world_calc = R @ p_robot_origin + t
        np.testing.assert_allclose(
            p_world_calc,
            np.array(grid_world, dtype=float),
            atol=1e-6,
            err_msg="R @ grid_origin_in_robot_base_m + t must equal grid_origin_in_3d_world_m",
        )

    def test_four_corners_and_all_cells_robot_to_world_parity(self):
        """Verify mathematical parity between robot base and 3D viewer board points.

        For all 4 corners and all 90 cells:
        R @ p_robot(col, row) + t == p_viewer(col, row)
        Error must be strictly < 1e-6 m (zero column mirroring).
        """
        import numpy as np

        with open(self.scene_path, "r", encoding="utf-8") as f:
            scene_data = json.load(f)

        phys_path = _PROJECT_ROOT / "shared" / "physical_geometry.json"
        with open(phys_path, "r", encoding="utf-8") as f:
            phys_data = json.load(f)

        rot = scene_data["robot_base_to_3d_world"]["rotation_matrix"]
        trans = scene_data["robot_base_to_3d_world"]["translation_m"]
        R = np.array(rot, dtype=float)
        t = np.array(trans, dtype=float)

        placement = scene_data["virtual_board_placement"]
        grid_robot = np.array(placement["grid_origin_in_robot_base_m"], dtype=float)
        center_world = np.array(placement["board_center_in_3d_world_m"], dtype=float)

        col_spacing_m = phys_data["board"]["column_spacing"] / 1000.0  # 0.04m
        row_spacing_m = phys_data["board"]["row_spacing"] / 1000.0     # 0.04m
        cols = phys_data["board"]["columns"]                          # 9
        rows = phys_data["board"]["rows"]                             # 10

        playable_width_m = (cols - 1) * col_spacing_m                 # 0.32m
        playable_depth_m = (rows - 1) * row_spacing_m                 # 0.36m

        def robot_point(c: int, r: int) -> np.ndarray:
            return np.array([
                grid_robot[0] - r * row_spacing_m,
                grid_robot[1] + c * col_spacing_m,
                grid_robot[2],
            ], dtype=float)

        def viewer_point(c: int, r: int) -> np.ndarray:
            origin_x = center_world[0] + playable_width_m / 2.0
            origin_y = center_world[1]
            origin_z = center_world[2] - playable_depth_m / 2.0
            return np.array([
                origin_x - c * col_spacing_m,
                origin_y,
                origin_z + r * row_spacing_m,
            ], dtype=float)

        corners = [
            ("Top-Left (Col 0, Row 0 - Black Left Rook)", 0, 0),
            ("Top-Right (Col 8, Row 0 - Black Right Rook)", 8, 0),
            ("Bottom-Left (Col 0, Row 9 - Red Left Rook)", 0, 9),
            ("Bottom-Right (Col 8, Row 9 - Red Right Rook)", 8, 9),
        ]

        for name, c, r in corners:
            p_robot = robot_point(c, r)
            p_world_from_robot = R @ p_robot + t
            p_viewer = viewer_point(c, r)
            err = np.linalg.norm(p_world_from_robot - p_viewer)
            self.assertLess(
                err,
                1e-6,
                f"Corner {name} mismatch: robot_transformed={p_world_from_robot}, viewer={p_viewer}, err={err}",
            )

        # Check all 90 cells
        for r in range(rows):
            for c in range(cols):
                p_robot = robot_point(c, r)
                p_world_from_robot = R @ p_robot + t
                p_viewer = viewer_point(c, r)
                err = np.linalg.norm(p_world_from_robot - p_viewer)
                self.assertLess(
                    err,
                    1e-6,
                    f"Cell ({c}, {r}) mismatch: robot_transformed={p_world_from_robot}, viewer={p_viewer}, err={err}",
                )

    def test_node_js_binding_script_executes_successfully(self):
        js_test = _PROJECT_ROOT / "tests" / "unit" / "test_viewer_profile_binding.mjs"
        self.assertTrue(js_test.exists())

        node_bin = shutil.which("node")
        if not node_bin:
            raise unittest.SkipTest("Node.js runtime not found in PATH; skipping 3D viewer profile binding test")

        try:
            res = subprocess.run(
                [node_bin, str(js_test)],
                cwd=str(_PROJECT_ROOT),
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, OSError) as e:
            raise unittest.SkipTest(f"Failed to execute Node.js ({e}); skipping 3D viewer profile binding test")

        self.assertEqual(
            res.returncode,
            0,
            f"Node viewer test failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}",
        )
        self.assertIn("ALL VIEWER INTEGRATION CHECKS PASSED", res.stdout)

    def test_node_js_gripper_and_telemetry_script_executes_successfully(self):
        js_test = _PROJECT_ROOT / "tests" / "unit" / "test_viewer_gripper_and_telemetry.mjs"
        self.assertTrue(js_test.exists())

        node_bin = shutil.which("node")
        if not node_bin:
            raise unittest.SkipTest("Node.js runtime not found in PATH; skipping 3D viewer gripper test")

        try:
            res = subprocess.run(
                [node_bin, str(js_test)],
                cwd=str(_PROJECT_ROOT),
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, OSError) as e:
            raise unittest.SkipTest(f"Failed to execute Node.js ({e}); skipping 3D viewer gripper test")

        self.assertEqual(
            res.returncode,
            0,
            f"Node viewer gripper test failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}",
        )
        self.assertIn("ALL VIEWER GRIPPER & TELEMETRY TESTS PASSED", res.stdout)


if __name__ == "__main__":
    unittest.main()

