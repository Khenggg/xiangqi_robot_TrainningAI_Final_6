"""Unit tests for FR3 Forward Kinematics (FK).

Verifies:
1. Zero-joint state produces exact expected flange transform.
2. Multiple non-zero configurations produce deterministic, orthonormal rotation matrices.
3. Rotation matrix determinant is +1.0 (proper rotation, no reflection).
4. Changing J1 rotates downstream chain correctly in the XY plane.
5. Changing J6 rotates flange orientation without moving upstream link positions.
6. Near-limit configurations evaluate safely without numerical divergence.
"""

import math
import os
import sys
import unittest
import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.simulation.kinematics.fr3 import FR3Kinematics
from src.simulation.kinematics.urdf_chain import Pose3D


class FR3ForwardKinematicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kin = FR3Kinematics()

    def test_zero_joint_pose(self):
        """Zero pose produces deterministic flange position matching URDF chain."""
        pose = self.kin.forward_kinematics(np.zeros(6))
        # Known URDF zero pose: x = -0.52001, y = -0.102, z = 0.038 m
        self.assertAlmostEqual(float(pose.translation_m[0]), -0.52001, places=4)
        self.assertAlmostEqual(float(pose.translation_m[1]), -0.102, places=4)
        self.assertAlmostEqual(float(pose.translation_m[2]), 0.038, places=4)

    def test_orthonormality_and_determinant(self):
        """Verify rotation matrices across diverse configurations are proper orthonormal."""
        test_configs = [
            np.zeros(6),
            np.array([0.5, -0.8, 1.2, -0.6, 1.0, -0.4]),
            np.array([-1.2, 0.4, -0.9, 0.8, -1.5, 2.0]),
            np.array([2.5, -2.0, 1.5, -3.0, 2.0, -1.0]),
        ]
        for q in test_configs:
            pose = self.kin.forward_kinematics(q)
            R = pose.rotation_matrix
            # R @ R.T should be Identity
            eye_diff = np.max(np.abs(R @ R.T - np.eye(3)))
            self.assertLess(eye_diff, 1e-6, f"Matrix not orthogonal for q={q}")
            det = np.linalg.det(R)
            self.assertAlmostEqual(det, 1.0, places=5, msg=f"Determinant not +1 for q={q}")

    def test_j1_rotates_downstream_chain_in_xy(self):
        """Changing J1 by angle theta rotates end-effector position about base Z by theta."""
        base_q = np.array([0.0, -0.5, 1.0, -0.5, -1.0, 0.0])
        pose_base = self.kin.forward_kinematics(base_q)
        p0 = pose_base.translation_m

        for angle_deg in [30.0, 45.0, 90.0, -60.0]:
            theta = math.radians(angle_deg)
            q = base_q.copy()
            q[0] = theta
            pose = self.kin.forward_kinematics(q)
            p = pose.translation_m

            # Z coordinate must be invariant under J1 base rotation
            self.assertAlmostEqual(float(p[2]), float(p0[2]), places=4)

            # Radius from base in XY must remain invariant
            r0 = math.sqrt(p0[0] ** 2 + p0[1] ** 2)
            r = math.sqrt(p[0] ** 2 + p[1] ** 2)
            self.assertAlmostEqual(r, r0, places=4)

            # Rotated (x, y) must match 2D rotation matrix
            expected_x = p0[0] * math.cos(theta) - p0[1] * math.sin(theta)
            expected_y = p0[0] * math.sin(theta) + p0[1] * math.cos(theta)
            self.assertAlmostEqual(float(p[0]), expected_x, places=4)
            self.assertAlmostEqual(float(p[1]), expected_y, places=4)

    def test_j6_does_not_move_upstream_links(self):
        """Changing J6 modifies end orientation but leaves upstream link positions unchanged."""
        base_q = np.array([0.2, -0.4, 0.8, -1.2, 0.5, 0.0])
        chain_base = self.kin.chain.forward_kinematics_chain(base_q)

        for j6_val in [-1.5, -0.5, 0.5, 1.5, 2.5]:
            q = base_q.copy()
            q[5] = j6_val
            chain = self.kin.chain.forward_kinematics_chain(q)

            # Upstream links 0 through 4 (base to wrist2) must have identical origins
            for link_idx in range(5):
                diff = np.max(np.abs(chain[link_idx][:3, 3] - chain_base[link_idx][:3, 3]))
                self.assertLess(diff, 1e-7, f"Upstream link {link_idx} moved when J6 changed")

            # Flange origin (link 5) must also have identical translation (rotation only at flange center)
            flange_pos_diff = np.max(np.abs(chain[5][:3, 3] - chain_base[5][:3, 3]))
            self.assertLess(flange_pos_diff, 1e-7, "Flange position moved when J6 rotated")

    def test_near_limit_configurations(self):
        """Verify FK computes cleanly near joint lower and upper limits."""
        lower = self.kin.lower_limits + 0.01
        upper = self.kin.upper_limits - 0.01

        pose_lower = self.kin.forward_kinematics(lower)
        pose_upper = self.kin.forward_kinematics(upper)

        self.assertTrue(np.all(np.isfinite(pose_lower.translation_m)))
        self.assertTrue(np.all(np.isfinite(pose_upper.translation_m)))


if __name__ == "__main__":
    unittest.main()
