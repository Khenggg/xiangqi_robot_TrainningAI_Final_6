"""
Unit tests for grasp attachment and relative transform invariance (Phase P3).

Verifies:
1. T_gripper_piece relative transform invariant is computed on grasp.
2. T_gripper_piece remains invariant across arbitrary gripper 3D translations and rotations:
   || T_gripper^-1 * T_piece - T_gripper_piece || < 1e-5.
3. Kinematic slaving ensures zero drift (no gravity drop or collision drift while attached).
4. Snapshot piece status shows is_grasped = True and ATTACHED_TO_GRIPPER.
"""

from pathlib import Path
import sys
import time
import unittest
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.physics.transforms import (
    quat_to_rot_matrix,
    rpy_deg_to_quat,
)
from src.simulation.physics.state import PiecePhysicalState
from src.simulation.physics.world import VirtualPhysicalWorld


class GraspAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.world = VirtualPhysicalWorld()
        self.gripper = self.world.gripper
        self.world.step_until_settled(max_steps=60)

    def tearDown(self):
        self.world.close()

    def test_relative_transform_invariance_under_translation_and_rotation(self):
        piece = self.world.pieces["black_rook_0"]
        p_init, _ = piece.get_pose_robot_base()

        # Position gripper at piece grasp center
        tcp_pos = p_init - self.gripper.tcp_to_grasp_center
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp_pos, [0, 0, 0, 1], time.time())

        # Grasp piece
        res = self.world.try_grasp()
        self.assertTrue(res.success)
        self.assertIsNotNone(self.gripper.T_gripper_piece)
        T_expected = self.gripper.T_gripper_piece.copy()

        # Apply several translation and rotation steps
        test_waypoints = [
            # (dx, dy, dz, [rx_deg, ry_deg, rz_deg])
            (0.0, 0.0, 0.08, [0.0, 0.0, 0.0]),
            (0.05, -0.04, 0.10, [10.0, -15.0, 30.0]),
            (-0.10, 0.08, 0.12, [0.0, 45.0, -60.0]),
            (0.02, 0.02, 0.05, [-20.0, 0.0, 90.0]),
        ]

        t_sim = time.time()
        for dx, dy, dz, rpy_deg in test_waypoints:
            t_sim += 0.02
            pos_wp = tcp_pos + np.array([dx, dy, dz], dtype=float)
            quat_wp = rpy_deg_to_quat(rpy_deg)

            self.gripper.set_tcp_pose(pos_wp, quat_wp, t_sim)
            self.world.step(1)

            # Compute current T_gripper^-1 * T_piece
            T_gripper = np.eye(4, dtype=float)
            T_gripper[:3, :3] = quat_to_rot_matrix(self.gripper.grasp_quat)
            T_gripper[:3, 3] = self.gripper.grasp_pos

            pos_curr, quat_curr = piece.get_pose_robot_base()
            T_piece = np.eye(4, dtype=float)
            T_piece[:3, :3] = quat_to_rot_matrix(quat_curr)
            T_piece[:3, 3] = pos_curr

            T_inv_gripper = np.linalg.inv(T_gripper)
            T_actual = T_inv_gripper @ T_piece

            diff = np.max(np.abs(T_actual - T_expected))
            self.assertLess(
                diff,
                1e-5,
                f"Relative transform drifted by {diff} at waypoint ({dx}, {dy}, {dz})",
            )

    def test_piece_state_and_snapshot_while_attached(self):
        piece = self.world.pieces["black_rook_0"]
        p_init, _ = piece.get_pose_robot_base()

        tcp_pos = p_init - self.gripper.tcp_to_grasp_center
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp_pos, [0, 0, 0, 1], time.time())

        self.world.try_grasp()
        # Lift 50mm
        self.gripper.set_tcp_pose(tcp_pos + [0, 0, 0.05], [0, 0, 0, 1], time.time() + 0.05)
        self.world.step(5)

        snap = self.world.get_snapshot()
        p_snap = [p for p in snap.pieces if p.id == "black_rook_0"][0]

        self.assertTrue(p_snap.is_grasped)
        self.assertEqual(p_snap.status, PiecePhysicalState.ATTACHED_TO_GRIPPER.value)
        self.assertEqual(snap.gripper["attached_piece_id"], "black_rook_0")


if __name__ == "__main__":
    unittest.main()

