"""
Unit tests for VirtualGripper and deterministic grasp criteria (Phase P3).

Verifies:
1. Capture volume radius and height boundaries.
2. Rejection when gripper is open (INVALID_GRIPPER_STATE).
3. Ambiguity rejection when multiple pieces occupy capture volume (AMBIGUOUS).
4. Rejection when already holding a piece (ALREADY_ATTACHED).
5. Velocity estimation from trajectory history.
"""

from pathlib import Path
import sys
import time
import unittest
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.physics.gripper import VirtualGripper
from src.simulation.physics.piece import XiangqiPieceBody
from src.simulation.physics.state import GraspStatus
from src.simulation.physics.world import VirtualPhysicalWorld


class VirtualGripperTests(unittest.TestCase):
    def setUp(self):
        self.world = VirtualPhysicalWorld()
        self.gripper = self.world.gripper
        self.world.step_until_settled(max_steps=60)

    def tearDown(self):
        self.world.close()

    def test_grasp_fails_when_gripper_open(self):
        # Position gripper directly at black_rook_0
        piece = self.world.pieces["black_rook_0"]
        pos, _ = piece.get_pose_robot_base()

        # Set TCP so grasp center aligns with piece center
        # grasp_center = tcp_pos + R * tcp_to_grasp_center
        # With R = I: tcp_pos = pos - tcp_to_grasp_center
        tcp_pos = pos - self.gripper.tcp_to_grasp_center
        self.gripper.set_gripper_state(False)
        self.gripper.set_tcp_pose(tcp_pos, [0, 0, 0, 1], time.time())

        result = self.gripper.evaluate_grasp_eligibility(list(self.world.pieces.values()))
        self.assertFalse(result.success)
        self.assertEqual(result.status, GraspStatus.INVALID_GRIPPER_STATE)

    def test_grasp_fails_when_out_of_capture_volume(self):
        # Position far from any piece
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose([0.0, 0.0, 0.5], [0, 0, 0, 1], time.time())

        result = self.gripper.evaluate_grasp_eligibility(list(self.world.pieces.values()))
        self.assertFalse(result.success)
        self.assertEqual(result.status, GraspStatus.NO_CANDIDATE)

    def test_grasp_succeeds_for_single_candidate_in_volume(self):
        piece = self.world.pieces["black_rook_0"]
        pos, _ = piece.get_pose_robot_base()

        tcp_pos = pos - self.gripper.tcp_to_grasp_center
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp_pos, [0, 0, 0, 1], time.time())

        result = self.gripper.evaluate_grasp_eligibility(list(self.world.pieces.values()))
        self.assertTrue(result.success)
        self.assertEqual(result.status, GraspStatus.SUCCESS)
        self.assertEqual(result.piece_id, "black_rook_0")

    def test_ambiguity_rejection_for_multiple_candidates(self):
        # Move two pieces into overlapping proximity inside capture volume
        p1 = self.world.pieces["black_rook_0"]
        p2 = self.world.pieces["black_knight_0"]

        shared_pos = [-0.25, 0.0, 0.06]
        p1.set_pose_robot_base(shared_pos, [0, 0, 0, 1])
        p2.set_pose_robot_base([shared_pos[0] + 0.005, shared_pos[1], shared_pos[2]], [0, 0, 0, 1])

        tcp_pos = np.array(shared_pos) - self.gripper.tcp_to_grasp_center
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp_pos, [0, 0, 0, 1], time.time())

        result = self.gripper.evaluate_grasp_eligibility(list(self.world.pieces.values()))
        self.assertFalse(result.success)
        self.assertEqual(result.status, GraspStatus.AMBIGUOUS)

    def test_already_attached_rejection(self):
        piece = self.world.pieces["black_rook_0"]
        pos, _ = piece.get_pose_robot_base()

        tcp_pos = pos - self.gripper.tcp_to_grasp_center
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp_pos, [0, 0, 0, 1], time.time())

        res1 = self.world.try_grasp()
        self.assertTrue(res1.success)

        # Attempt to grasp again while holding
        res2 = self.world.try_grasp()
        self.assertFalse(res2.success)
        self.assertEqual(res2.status, GraspStatus.ALREADY_ATTACHED)

    def test_velocity_estimation(self):
        t0 = 100.0
        self.gripper.set_tcp_pose([0.0, 0.0, 0.1], [0, 0, 0, 1], t0)
        t1 = 100.1  # dt = 0.1s
        self.gripper.set_tcp_pose([0.02, 0.0, 0.1], [0, 0, 0, 1], t1)

        lin_vel, ang_vel = self.gripper.estimate_velocity()
        # dx = 0.02, dt = 0.1 -> vx = 0.2 m/s
        self.assertAlmostEqual(lin_vel[0], 0.2, places=3)
        self.assertAlmostEqual(lin_vel[1], 0.0, places=3)
        self.assertAlmostEqual(lin_vel[2], 0.0, places=3)


if __name__ == "__main__":
    unittest.main()

