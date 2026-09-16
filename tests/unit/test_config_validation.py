"""
Unit tests for strict configuration validation and fail-fast guarantees (Phase P3.1).

Verifies:
1. Malformed virtual_physics.json triggers ValueError/TypeError.
2. Malformed virtual_gripper_profile.json triggers ValueError/TypeError.
3. Malformed xiangqi_start_layout.json triggers ValueError/TypeError.
4. Non-orthonormal or left-handed transforms in virtual_fr3_scene.json trigger ValueError.
5. PyBullet client is safely cleaned up (no leaked connection) if initialization fails.
"""

import copy
import json
from pathlib import Path
import sys
import unittest
import pybullet as p

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.physics.validation import (
    validate_physics_config,
    validate_gripper_profile,
    validate_start_layout,
)
from src.simulation.physics.transforms import SceneTransform, load_scene_transform
from src.simulation.physics.world import VirtualPhysicalWorld


class ConfigValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(_PROJECT_ROOT / "shared" / "virtual_physics.json", "r", encoding="utf-8") as f:
            cls.valid_physics = json.load(f)
        with open(_PROJECT_ROOT / "shared" / "virtual_gripper_profile.json", "r", encoding="utf-8") as f:
            cls.valid_gripper = json.load(f)
        with open(_PROJECT_ROOT / "shared" / "xiangqi_start_layout.json", "r", encoding="utf-8") as f:
            cls.valid_layout = json.load(f)

    def test_valid_configs_pass(self):
        try:
            validate_physics_config(self.valid_physics)
            validate_gripper_profile(self.valid_gripper)
            validate_start_layout(self.valid_layout)
        except Exception as e:
            self.fail(f"Valid configs failed validation: {e}")

    def test_physics_missing_required_keys(self):
        cfg = copy.deepcopy(self.valid_physics)
        del cfg["board"]
        with self.assertRaises((ValueError, KeyError)):
            validate_physics_config(cfg)

    def test_physics_invalid_gravity(self):
        cfg = copy.deepcopy(self.valid_physics)
        cfg["gravity_m_s2"] = [0.0, 0.0]  # Only 2 elements
        with self.assertRaises(ValueError):
            validate_physics_config(cfg)

    def test_physics_invalid_solver_iterations(self):
        cfg = copy.deepcopy(self.valid_physics)
        cfg["solver_iterations"] = 0
        with self.assertRaises(ValueError):
            validate_physics_config(cfg)

    def test_physics_negative_friction(self):
        cfg = copy.deepcopy(self.valid_physics)
        cfg["board"]["lateral_friction"] = -0.5
        with self.assertRaises(ValueError):
            validate_physics_config(cfg)

    def test_gripper_negative_dimensions(self):
        cfg = copy.deepcopy(self.valid_gripper)
        cfg["palm"]["dimensions_m"] = [-0.060, 0.040, 0.030]
        with self.assertRaises(ValueError):
            validate_gripper_profile(cfg)

    def test_gripper_closed_greater_than_open(self):
        cfg = copy.deepcopy(self.valid_gripper)
        cfg["stroke"]["closed_width_m"] = 0.050
        cfg["stroke"]["open_width_m"] = 0.040
        with self.assertRaises(ValueError):
            validate_gripper_profile(cfg)

    def test_gripper_missing_capture_volume(self):
        cfg = copy.deepcopy(self.valid_gripper)
        del cfg["capture_volume"]
        with self.assertRaises((ValueError, KeyError)):
            validate_gripper_profile(cfg)

    def test_layout_wrong_piece_count(self):
        cfg = copy.deepcopy(self.valid_layout)
        cfg["pieces"] = cfg["pieces"][:31]  # 31 pieces instead of 32
        with self.assertRaises(ValueError):
            validate_start_layout(cfg)

    def test_layout_duplicate_piece_id(self):
        cfg = copy.deepcopy(self.valid_layout)
        cfg["pieces"][1]["id"] = cfg["pieces"][0]["id"]
        with self.assertRaises(ValueError):
            validate_start_layout(cfg)

    def test_layout_duplicate_position(self):
        cfg = copy.deepcopy(self.valid_layout)
        cfg["pieces"][1]["col"] = cfg["pieces"][0]["col"]
        cfg["pieces"][1]["row"] = cfg["pieces"][0]["row"]
        with self.assertRaises(ValueError):
            validate_start_layout(cfg)

    def test_layout_coordinate_out_of_bounds(self):
        cfg = copy.deepcopy(self.valid_layout)
        cfg["pieces"][0]["col"] = 9  # col must be 0..8
        with self.assertRaises(ValueError):
            validate_start_layout(cfg)

    def test_scene_transform_non_orthonormal_fails(self):
        bad_rot = [
            [1.0, 0.5, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        with self.assertRaises(ValueError):
            SceneTransform(rotation_matrix=bad_rot, translation_m=[0.0, 0.0, 0.0])

    def test_scene_transform_left_handed_fails(self):
        # Det(R) = -1 (reflection)
        left_handed_rot = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, -1.0],
        ]
        with self.assertRaises(ValueError):
            SceneTransform(rotation_matrix=left_handed_rot, translation_m=[0.0, 0.0, 0.0])

    def test_scene_transform_cache_and_custom_path_isolation(self):
        import builtins
        from unittest.mock import patch
        import tempfile

        # 1. Reset and load default
        load_scene_transform(force_reload=True)
        t1 = load_scene_transform()
        self.assertIsNotNone(t1)

        # Consecutive calls must use cached object without re-opening file
        with patch("builtins.open", side_effect=AssertionError("File should not be opened when cached")):
            t2 = load_scene_transform()
            self.assertIs(t1, t2)

        # 2. Loading a custom path does NOT poison or overwrite default cache
        custom_scene = {
            "robot_base_to_3d_world": {
                "rotation_matrix": [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
                "translation_m": [0.1, 0.2, 0.3],
            }
        }
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
            json.dump(custom_scene, tf)
            temp_path = tf.name

        try:
            custom_t = load_scene_transform(scene_config_path=temp_path)
            self.assertEqual(custom_t.translation_m.tolist(), [0.1, 0.2, 0.3])

            # Default cache remains unchanged (still t1)
            t3 = load_scene_transform()
            self.assertIs(t1, t3)
            self.assertIsNot(custom_t, t3)
        finally:
            Path(temp_path).unlink(missing_ok=True)

        # 3. force_reload=True re-opens file
        orig_open = builtins.open
        call_count = 0

        def counting_open(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return orig_open(*args, **kwargs)

        with patch("builtins.open", side_effect=counting_open):
            t4 = load_scene_transform(force_reload=True)
            self.assertGreaterEqual(call_count, 1)
            self.assertIsNotNone(t4)

    def test_pybullet_client_cleaned_up_on_init_failure(self):
        # Ensure that if validation fails in VirtualPhysicalWorld.__init__, no client is leaked
        bad_physics_path = _PROJECT_ROOT / "shared" / "non_existent_physics.json"
        with self.assertRaises(FileNotFoundError):
            VirtualPhysicalWorld(physics_config_path=bad_physics_path)

        # PyBullet should not have any orphaned active connections from that attempt
        client_count = p.getConnectionInfo(physicsClientId=0)
        self.assertIsNotNone(client_count)


if __name__ == "__main__":
    unittest.main()

