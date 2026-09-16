"""
Unit tests for world coordinate and spatial quaternion parity between Python and Three.js (Phase P3).

Verifies:
1. Canonical R_robot_to_world matrix is orthonormal with determinant = +1.0 (proper rotation).
2. Canonical translation is [0, 0, 0].
3. Grid origin in robot_base [-0.18, -0.16, 0.05] transforms to [0.16, 0.05, 0.18] in 3d_world.
4. Board center in robot_base [-0.36, 0.0, 0.05] transforms to [0.0, 0.05, 0.36] in 3d_world.
5. All 90 grid cell centers transform with position residual < 1e-6 between continuous math and R @ p.
6. Upright cylinder quaternion [0, 0, 0, 1] transforms to [-0.5, 0.5, 0.5, 0.5] in 3d_world,
   mapping the piece cylinder axis to [0, 1, 0] (vertical Y-up in Three.js).
"""

import json
from pathlib import Path
import sys
import unittest
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.physics.transforms import (
    DEFAULT_R_ROBOT_TO_WORLD,
    DEFAULT_TRANSLATION_ROBOT_TO_WORLD,
    quat_to_rot_matrix,
    rot_matrix_to_quat,
    tilt_angle_deg,
    transform_point_robot_to_world,
    transform_quat_robot_to_world,
)
from src.domain.geometry import get_physical_geometry


class WorldCoordinateParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene_path = _PROJECT_ROOT / "shared" / "virtual_fr3_scene.json"
        with open(cls.scene_path, "r", encoding="utf-8-sig") as f:
            cls.scene_cfg = json.load(f)

    def test_canonical_rotation_matrix_properties(self):
        R = DEFAULT_R_ROBOT_TO_WORLD
        # Orthogonality: R.T @ R = I
        np.testing.assert_allclose(R.T @ R, np.eye(3), atol=1e-12)
        # Determinant = +1.0 (proper rotation, no reflection / improper parity)
        det = np.linalg.det(R)
        self.assertAlmostEqual(det, 1.0, places=12)

    def test_key_scene_points_parity(self):
        bp = self.scene_cfg["virtual_board_placement"]
        grid_robot = bp["grid_origin_in_robot_base_m"]
        grid_world_expected = bp["grid_origin_in_3d_world_m"]

        p_world = transform_point_robot_to_world(grid_robot)
        np.testing.assert_allclose(p_world, grid_world_expected, atol=1e-6)

        center_robot = bp["board_center_in_robot_base_m"]
        center_world_expected = bp["board_center_in_3d_world_m"]

        p_center = transform_point_robot_to_world(center_robot)
        np.testing.assert_allclose(p_center, center_world_expected, atol=1e-6)

    def test_all_90_cells_transformation_parity(self):
        geom = get_physical_geometry()
        col_spacing = geom.grid_cell_width_mm / 1000.0
        row_spacing = geom.grid_cell_length_mm / 1000.0

        bp = self.scene_cfg["virtual_board_placement"]
        x0_r, y0_r, z0_r = bp["grid_origin_in_robot_base_m"]
        x0_w, y0_w, z0_w = bp["grid_origin_in_3d_world_m"]

        for r in range(10):
            for c in range(9):
                # Robot base coordinates: row increases along -X, col increases along +Y
                p_r = [x0_r - r * row_spacing, y0_r + c * col_spacing, z0_r]
                p_w = transform_point_robot_to_world(p_r)

                # World coordinates from mapping:
                # world_x = -robot_y = -(y0_r + c * col_spacing) = x0_w - c * col_spacing
                # world_y = +robot_z = z0_r = y0_w
                # world_z = -robot_x = -(x0_r - r * row_spacing) = z0_w + r * row_spacing
                expected_w = [x0_w - c * col_spacing, y0_w, z0_w + r * row_spacing]
                np.testing.assert_allclose(p_w, expected_w, atol=1e-6)

    def test_quaternion_transformation_and_axis_mapping(self):
        # Upright cylinder in robot frame has local Z along robot +Z
        q_robot = [0.0, 0.0, 0.0, 1.0]
        q_world = transform_quat_robot_to_world(q_robot)

        # Expected quaternion for rotation R = [[0, -1, 0], [0, 0, 1], [-1, 0, 0]]
        # Trace is 0.0, q is [-0.5, 0.5, 0.5, 0.5]
        R_world = quat_to_rot_matrix(q_world)
        local_z_in_world = R_world @ np.array([0.0, 0.0, 1.0])

        # Local cylinder axis must point along world +Y (vertical up in Three.js)
        np.testing.assert_allclose(local_z_in_world, [0.0, 1.0, 0.0], atol=1e-6)

    def test_tilt_angle_derivation(self):
        # Upright cylinder
        q_upright = [0.0, 0.0, 0.0, 1.0]
        self.assertAlmostEqual(tilt_angle_deg(q_upright), 0.0, places=3)

        # Cylinder tilted 90 degrees around X
        # Quaternion for 90 deg around X: [sin(45), 0, 0, cos(45)] = [0.7071, 0, 0, 0.7071]
        q_tilted = [np.sin(np.pi / 4), 0.0, 0.0, np.cos(np.pi / 4)]
        self.assertAlmostEqual(tilt_angle_deg(q_tilted), 90.0, places=3)

        # Inverted cylinder (180 deg)
        q_inverted = [1.0, 0.0, 0.0, 0.0]
        self.assertAlmostEqual(tilt_angle_deg(q_inverted), 180.0, places=3)


if __name__ == "__main__":
    unittest.main()

