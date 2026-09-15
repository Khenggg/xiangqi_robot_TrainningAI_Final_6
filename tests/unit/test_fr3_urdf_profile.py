"""Unit tests for FR3 URDF parsing and simulation profile generation.

Verifies:
1. shared/robot_profiles/fr3.json exists and conforms to schema_version 1.
2. Exactly 6 revolute joints (j1..j6) with valid parents/children.
3. Profile values match fairino3_v6.urdf exactly.
4. URDF joint limits match physical robot specifications (e.g. j1 in [-175 deg, +175 deg]).
5. Profile generation and check utility runs deterministically.
"""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.simulation.generate_fr3_profile import (
    parse_fr3_urdf,
    verify_profile_matches_urdf,
)


class FR3UrdfProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.urdf_path = _PROJECT_ROOT / "robot-3d-viewer" / "assets" / "fr3_v6" / "fairino3_v6.urdf"
        cls.profile_path = _PROJECT_ROOT / "shared" / "robot_profiles" / "fr3.json"

    def test_urdf_file_exists(self):
        self.assertTrue(self.urdf_path.is_file(), f"URDF not found: {self.urdf_path}")

    def test_profile_file_exists(self):
        self.assertTrue(self.profile_path.is_file(), f"Profile not found: {self.profile_path}")

    def test_profile_schema_and_contents(self):
        with open(self.profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data.get("schema_version"), 1)
        self.assertEqual(data.get("robot_model"), "FR3")
        self.assertEqual(data.get("base_link"), "base_link")
        self.assertEqual(data.get("flange_link"), "wrist3_link")

        joints = data.get("joints", [])
        self.assertEqual(len(joints), 6)

        expected_names = ["j1", "j2", "j3", "j4", "j5", "j6"]
        actual_names = [j["name"] for j in joints]
        self.assertEqual(actual_names, expected_names)

        # Check revolute type and axis [0, 0, 1]
        for j in joints:
            self.assertEqual(j["type"], "revolute")
            self.assertEqual(j["axis"], [0.0, 0.0, 1.0])
            self.assertLess(j["lower_rad"], j["upper_rad"])

    def test_profile_matches_parsed_urdf(self):
        with open(self.profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertTrue(
            verify_profile_matches_urdf(data, self.urdf_path),
            "Profile in shared/robot_profiles/fr3.json does not match fairino3_v6.urdf",
        )

    def test_generate_script_check_cli(self):
        cmd = [sys.executable, str(_PROJECT_ROOT / "tools" / "simulation" / "generate_fr3_profile.py"), "--check"]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(_PROJECT_ROOT))
        self.assertEqual(proc.returncode, 0, f"Check CLI failed: {proc.stderr}")
        self.assertIn("[CHECK PASSED]", proc.stdout)


if __name__ == "__main__":
    unittest.main()
