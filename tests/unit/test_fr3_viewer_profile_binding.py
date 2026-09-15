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

    def test_node_js_binding_script_executes_successfully(self):
        js_test = _PROJECT_ROOT / "tests" / "unit" / "test_viewer_profile_binding.mjs"
        self.assertTrue(js_test.exists())

        res = subprocess.run(
            ["node", str(js_test)],
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            res.returncode,
            0,
            f"Node viewer test failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}",
        )
        self.assertIn("ALL VIEWER INTEGRATION CHECKS PASSED", res.stdout)


if __name__ == "__main__":
    unittest.main()
