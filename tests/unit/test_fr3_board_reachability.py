"""Unit regression tests for Virtual FR3 Xiangqi board reachability.

Verifies:
1. shared/virtual_fr3_scene.json exists and defines explicit extrinsics.
2. All 90 board intersections are kinematically reachable at board surface height.
3. Maximum position residual across all 90 cells <= 1.0 mm.
4. Maximum orientation residual across all 90 cells <= 1.0 deg.
5. Minimum joint margin is strictly positive (no joint out of bounds).
"""

import json
import os
from pathlib import Path
import sys
import unittest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.simulation.check_fr3_board_reachability import evaluate_board_reachability


class FR3BoardReachabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene_path = _PROJECT_ROOT / "shared" / "virtual_fr3_scene.json"

    def test_scene_config_exists_and_labelled(self):
        self.assertTrue(self.scene_path.is_file(), f"Scene config missing: {self.scene_path}")
        with open(self.scene_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("schema_version"), 1)
        self.assertEqual(data.get("status"), "SIMULATION_ONLY_PROVISIONAL")
        self.assertEqual(data.get("robot_model"), "FR3")
        self.assertIn("robot_base_to_3d_world", data)
        self.assertIn("virtual_board_placement", data)

    def test_90_intersections_reachable_at_board_surface(self):
        summary = evaluate_board_reachability(scene_config_path=self.scene_path, height_offset_m=0.0)

        self.assertEqual(
            summary["reachable_count"],
            90,
            f"Expected 90/90 reachable, got {summary['reachable_count']}/90. "
            f"Unreachable cells: {summary['unreachable_cells']}",
        )
        self.assertEqual(summary["unreachable_count"], 0)
        self.assertLessEqual(
            summary["worst_pos_err_mm"],
            1.0,
            f"Worst position residual exceeded 1.0mm: {summary['worst_pos_err_mm']:.4f}mm",
        )
        self.assertLessEqual(
            summary["worst_rot_err_deg"],
            1.0,
            f"Worst orientation residual exceeded 1.0deg: {summary['worst_rot_err_deg']:.4f}deg",
        )
        self.assertGreater(
            summary["min_joint_margin_deg"],
            0.0,
            "A joint was on or past its physical kinematic limit",
        )


if __name__ == "__main__":
    unittest.main()
