"""
Unit tests for PyBullet gripper collision proxies and attached piece filtering (Phase P3.1).

Verifies:
1. Gripper spawns exactly 3 kinematic collision proxies: palm, left jaw, right jaw.
2. Jaw proxies translate symmetrically along travel_axis (X) on open/close.
3. Attached piece has collision filtering disabled against all 3 proxy bodies.
4. Detaching or dropping the piece re-enables collision filtering with proxies.
5. get_gripper_piece_contacts() accurately reports contact pairs.
"""

from pathlib import Path
import sys
import unittest
import numpy as np
import pybullet as p

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.physics.world import VirtualPhysicalWorld


class GripperCollisionProxiesTests(unittest.TestCase):
    def setUp(self):
        self.world = VirtualPhysicalWorld()
        self.gripper = self.world.gripper
        self.world.step_until_settled(max_steps=60)

    def tearDown(self):
        self.world.close()

    def test_gripper_proxy_bodies_exist(self):
        proxies = self.gripper.proxy_body_ids
        self.assertEqual(len(proxies), 3, "Must have exactly 3 proxy bodies: palm, left jaw, right jaw")
        self.assertGreaterEqual(self.gripper.palm_body_id, 0)
        self.assertGreaterEqual(self.gripper.left_jaw_body_id, 0)
        self.assertGreaterEqual(self.gripper.right_jaw_body_id, 0)

        # Bodies must be registered in PyBullet
        for bid in proxies:
            info = p.getBodyInfo(bid, physicsClientId=self.world.client_id)
            self.assertIsNotNone(info)

    def test_jaw_motion_along_travel_axis(self):
        tcp = [0.0, 0.0, 0.10]
        quat = [0.0, 0.0, 0.0, 1.0]

        # 1. Fully open
        self.gripper.set_gripper_state(False)
        self.gripper.set_tcp_pose(tcp, quat)

        pos_l_open, _ = p.getBasePositionAndOrientation(
            self.gripper.left_jaw_body_id, physicsClientId=self.world.client_id
        )
        pos_r_open, _ = p.getBasePositionAndOrientation(
            self.gripper.right_jaw_body_id, physicsClientId=self.world.client_id
        )
        dist_open = abs(pos_r_open[0] - pos_l_open[0])
        self.assertAlmostEqual(dist_open, self.gripper.open_width_m, places=3)

        # 2. Fully closed
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp, quat)

        pos_l_closed, _ = p.getBasePositionAndOrientation(
            self.gripper.left_jaw_body_id, physicsClientId=self.world.client_id
        )
        pos_r_closed, _ = p.getBasePositionAndOrientation(
            self.gripper.right_jaw_body_id, physicsClientId=self.world.client_id
        )
        dist_closed = abs(pos_r_closed[0] - pos_l_closed[0])
        self.assertAlmostEqual(dist_closed, self.gripper.closed_width_m, places=3)

        # Traveled along X axis (Y and Z relative offsets remain equal)
        self.assertAlmostEqual(pos_l_open[1], pos_l_closed[1], places=4)
        self.assertAlmostEqual(pos_l_open[2], pos_l_closed[2], places=4)

    def test_jaw_motion_along_travel_axis_y_and_z(self):
        tcp = [0.0, 0.0, 0.10]
        quat = [0.0, 0.0, 0.0, 1.0]
        orig_axis = self.gripper.travel_axis

        try:
            # 1. Test Y axis travel
            self.gripper.travel_axis = "Y"
            self.gripper.set_gripper_state(False)
            self.gripper.set_tcp_pose(tcp, quat)

            pos_l_open, _ = p.getBasePositionAndOrientation(
                self.gripper.left_jaw_body_id, physicsClientId=self.world.client_id
            )
            pos_r_open, _ = p.getBasePositionAndOrientation(
                self.gripper.right_jaw_body_id, physicsClientId=self.world.client_id
            )
            dist_y_open = abs(pos_r_open[1] - pos_l_open[1])
            self.assertAlmostEqual(dist_y_open, self.gripper.open_width_m, places=3)

            self.gripper.set_gripper_state(True)
            self.gripper.set_tcp_pose(tcp, quat)
            pos_l_closed, _ = p.getBasePositionAndOrientation(
                self.gripper.left_jaw_body_id, physicsClientId=self.world.client_id
            )
            pos_r_closed, _ = p.getBasePositionAndOrientation(
                self.gripper.right_jaw_body_id, physicsClientId=self.world.client_id
            )
            dist_y_closed = abs(pos_r_closed[1] - pos_l_closed[1])
            self.assertAlmostEqual(dist_y_closed, self.gripper.closed_width_m, places=3)
            # X and Z coordinates remain constant across open/closed
            self.assertAlmostEqual(pos_l_open[0], pos_l_closed[0], places=4)
            self.assertAlmostEqual(pos_l_open[2], pos_l_closed[2], places=4)

            # 2. Test Z axis travel (Phase P3.2.1 parity)
            self.gripper.travel_axis = "Z"
            self.gripper.set_gripper_state(False)
            self.gripper.set_tcp_pose(tcp, quat)

            pos_l_z_open, _ = p.getBasePositionAndOrientation(
                self.gripper.left_jaw_body_id, physicsClientId=self.world.client_id
            )
            pos_r_z_open, _ = p.getBasePositionAndOrientation(
                self.gripper.right_jaw_body_id, physicsClientId=self.world.client_id
            )
            dist_z_open = abs(pos_r_z_open[2] - pos_l_z_open[2])
            self.assertAlmostEqual(dist_z_open, self.gripper.open_width_m, places=3)

            self.gripper.set_gripper_state(True)
            self.gripper.set_tcp_pose(tcp, quat)
            pos_l_z_closed, _ = p.getBasePositionAndOrientation(
                self.gripper.left_jaw_body_id, physicsClientId=self.world.client_id
            )
            pos_r_z_closed, _ = p.getBasePositionAndOrientation(
                self.gripper.right_jaw_body_id, physicsClientId=self.world.client_id
            )
            dist_z_closed = abs(pos_r_z_closed[2] - pos_l_z_closed[2])
            self.assertAlmostEqual(dist_z_closed, self.gripper.closed_width_m, places=3)
            # X and Y coordinates remain constant across open/closed
            self.assertAlmostEqual(pos_l_z_open[0], pos_l_z_closed[0], places=4)
            self.assertAlmostEqual(pos_l_z_open[1], pos_l_z_closed[1], places=4)
        finally:
            self.gripper.travel_axis = orig_axis
            self.gripper.set_gripper_state(False)

    def test_attached_piece_collision_filter_toggle(self):
        piece = self.world.pieces["black_rook_0"]
        pos_init, _ = piece.get_pose_robot_base()

        tcp = pos_init - self.gripper.tcp_to_grasp_center
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp, [0, 0, 0, 1])

        # Grasp and attach
        res = self.world.try_grasp()
        self.assertTrue(res.success)
        self.assertTrue(self.gripper.is_attached)

        # While attached, step world: contacts between attached piece and gripper proxies must be filtered
        self.world.step(5)
        for proxy_id in self.gripper.proxy_body_ids:
            cps = p.getContactPoints(
                piece.body_id, proxy_id, physicsClientId=self.world.client_id
            )
            self.assertEqual(len(cps), 0, f"Attached piece must not collide with proxy body {proxy_id}")

        # Detach piece
        self.world.release_attached_piece()
        self.assertFalse(self.gripper.is_attached)

        # When detached, collision filtering is re-enabled
        # Close gripper and move jaw to intersect piece directly to confirm collision detection is active
        piece_pos, _ = piece.get_pose_robot_base()
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(piece_pos, [0, 0, 0, 1])
        self.world.step(1)
        contacts = self.world.get_gripper_piece_contacts()
        self.assertGreater(len(contacts), 0, "Re-enabled collision proxies should register contacts with piece")


if __name__ == "__main__":
    unittest.main()
