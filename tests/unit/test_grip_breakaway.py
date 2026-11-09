"""Breakaway grip: a held piece slips when contact force exceeds the limit.

The grip is still a kinematic weld while the payload is free, but it is no longer
unconditional: contact force above the configured limit releases the piece so it
falls under gravity, and 0 keeps the old rigid behaviour.
"""
from pathlib import Path
import sys
import time
import unittest

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.physics.world import VirtualPhysicalWorld


class GripBreakawayTests(unittest.TestCase):
    def setUp(self):
        self.world = VirtualPhysicalWorld()
        self.world.step_until_settled(max_steps=60)

    def tearDown(self):
        self.world.close()

    def _grasp(self):
        gripper = self.world.gripper
        piece = self.world.pieces["black_rook_0"]
        position, _ = piece.get_pose_robot_base()
        tcp = position - gripper.tcp_to_grasp_center
        gripper.set_gripper_state(True)
        gripper.set_tcp_pose(tcp, [0, 0, 0, 1], time.time())
        self.assertTrue(self.world.try_grasp().success, "test setup must grasp the piece")
        return gripper, tcp

    def test_contact_above_the_limit_releases_the_payload(self):
        self.world.grip_break_force_n = 0.01  # deliberately fragile grip
        gripper, tcp = self._grasp()
        gripper.set_tcp_pose(tcp - np.array([0.0, 0.0, 0.02]), [0, 0, 0, 1], time.time())
        self.world.step(8)

        self.assertIsNone(self.world.get_attached_piece(), "payload must slip out")
        self.assertIsNotNone(self.world.last_grip_break)
        self.assertGreater(self.world.last_grip_break["contact_force_n"], 0.01)
        self.assertEqual(self.world.last_grip_break["piece_id"], "black_rook_0")

    def test_payload_without_contact_stays_attached(self):
        self.world.grip_break_force_n = 0.01  # fragile, but the piece touches nothing
        gripper, tcp = self._grasp()
        gripper.set_tcp_pose(tcp + np.array([0.0, 0.0, 0.05]), [0, 0, 0, 1], time.time())
        self.world.step(8)

        self.assertIsNotNone(self.world.get_attached_piece())
        self.assertIsNone(self.world.last_grip_break)

    def test_high_limit_keeps_the_payload_under_contact(self):
        self.world.grip_break_force_n = 1e6
        gripper, tcp = self._grasp()
        gripper.set_tcp_pose(tcp - np.array([0.0, 0.0, 0.02]), [0, 0, 0, 1], time.time())
        self.world.step(8)

        self.assertIsNotNone(self.world.get_attached_piece())
        self.assertIsNone(self.world.last_grip_break)

    def test_zero_limit_disables_breakaway(self):
        self.world.grip_break_force_n = 0.0
        gripper, tcp = self._grasp()
        gripper.set_tcp_pose(tcp - np.array([0.0, 0.0, 0.02]), [0, 0, 0, 1], time.time())
        self.world.step(8)

        self.assertIsNotNone(self.world.get_attached_piece())
        self.assertIsNone(self.world.last_grip_break)


if __name__ == "__main__":
    unittest.main()
