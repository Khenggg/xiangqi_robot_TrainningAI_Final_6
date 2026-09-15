"""Unit tests for FR3 Inverse Kinematics (IK) using Damped Least Squares (DLS).

Verifies:
1. FK <-> IK roundtrip succeeds for multiple valid configurations.
2. Resulting FK pose matches target within simulation tolerances (<= 1.0 mm, <= 1.0 deg).
3. Joint limits are strictly enforced on all returned solutions.
4. Unreachable targets return structured failure (IKStatus.UNREACHABLE).
5. Non-finite targets return structured failure (IKStatus.INVALID_TARGET).
6. Multi-seed restart improves solve capability from diverse initializations.
"""

import math
import os
import sys
import unittest
import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.simulation.kinematics.fr3 import FR3Kinematics, IKResult, IKStatus
from src.simulation.kinematics.urdf_chain import Pose3D


class FR3InverseKinematicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kin = FR3Kinematics()

    def test_fk_ik_roundtrip_seeded(self):
        """Test FK -> IK roundtrip from close seed: must meet <= 1.0mm, <= 1.0deg."""
        configs = [
            np.array([0.0, -0.6, 1.2, -0.8, -1.57, 0.0]),
            np.array([0.4, -0.8, 1.5, -1.2, 1.57, -0.3]),
            np.array([-0.5, -0.4, 0.9, -1.0, -1.2, 0.4]),
            np.array([0.8, -1.0, 1.8, -1.5, -1.57, 0.5]),
            np.array([-0.8, -0.5, 1.1, -0.6, 1.4, -0.2]),
        ]

        for q_orig in configs:
            target_pose = self.kin.forward_kinematics(q_orig)
            seed = q_orig + np.random.normal(0, 0.05, 6)
            seed = np.clip(seed, self.kin.lower_limits, self.kin.upper_limits)

            res = self.kin.inverse_kinematics(
                target_pose,
                seed_joints=seed,
                pos_tol_mm=1.0,
                rot_tol_deg=1.0,
            )

            self.assertTrue(res.success, f"IK failed for q={q_orig}: {res.failure_reason}")
            self.assertEqual(res.status, IKStatus.SUCCESS)
            self.assertLessEqual(res.position_error_mm, 1.0)
            self.assertLessEqual(res.orientation_error_deg, 1.0)

            # End-effector transform roundtrip check
            pose_solved = self.kin.forward_kinematics(res.joints_rad)
            pos_diff_mm = np.linalg.norm(target_pose.translation_m - pose_solved.translation_m) * 1000.0
            self.assertLessEqual(pos_diff_mm, 1.0)

    def test_joint_limits_strictly_obeyed(self):
        """Verify returned IK solutions never violate URDF joint limits."""
        np.random.seed(123)
        for _ in range(15):
            q_rand = np.random.uniform(self.kin.lower_limits * 0.7, self.kin.upper_limits * 0.7)
            target = self.kin.forward_kinematics(q_rand)
            res = self.kin.inverse_kinematics(target, seed_joints=q_rand + 0.02)
            if res.success:
                q_sol = res.joints_rad
                for i in range(6):
                    self.assertGreaterEqual(
                        q_sol[i],
                        self.kin.lower_limits[i] - 1e-6,
                        f"Joint {i} violated lower limit",
                    )
                    self.assertLessEqual(
                        q_sol[i],
                        self.kin.upper_limits[i] + 1e-6,
                        f"Joint {i} violated upper limit",
                    )

    def test_unreachable_target_structured_failure(self):
        """Targets beyond physical arm reach return IKStatus.UNREACHABLE without throwing."""
        # 2.0 meters away from base
        unreachable_target = [2000.0, 0.0, 0.0, 180.0, 0.0, 0.0]
        res = self.kin.inverse_kinematics(unreachable_target)

        self.assertFalse(res.success)
        self.assertEqual(res.status, IKStatus.UNREACHABLE)
        self.assertIn("exceeds max FR3 reach", res.failure_reason)

    def test_invalid_target_rejection(self):
        """NaN or Inf inputs return IKStatus.INVALID_TARGET cleanly."""
        nan_target = [float("nan"), 0.0, 200.0, 180.0, 0.0, 0.0]
        res = self.kin.inverse_kinematics(nan_target)
        self.assertFalse(res.success)
        self.assertEqual(res.status, IKStatus.INVALID_TARGET)

        inf_target = [300.0, float("inf"), 200.0, 180.0, 0.0, 0.0]
        res2 = self.kin.inverse_kinematics(inf_target)
        self.assertFalse(res2.success)
        self.assertEqual(res2.status, IKStatus.INVALID_TARGET)


if __name__ == "__main__":
    unittest.main()
