"""
Unit tests for PyBullet gripper collision proxies and attached piece filtering (Phase P3.1).

Verifies:
1. Gripper spawns exactly 4 kinematic collision proxy bodies: 2 fixed chunks, left jaw, right jaw.
2. Jaw proxies translate symmetrically along travel_axis (X) on open/close (5.2 mm each).
3. Attached piece has collision filtering disabled against all proxy bodies.
4. Detaching or dropping the piece re-enables collision filtering with proxies.
5. get_gripper_piece_contacts() accurately reports contact pairs across all proxy bodies.
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
from src.simulation.physics.transforms import rpy_deg_to_quat


class GripperCollisionProxiesTests(unittest.TestCase):
    def setUp(self):
        self.world = VirtualPhysicalWorld()
        self.gripper = self.world.gripper
        self.tool_down_quat = rpy_deg_to_quat([180.0, 0.0, 90.0])
        self.world.step_until_settled(max_steps=60)

    def tearDown(self):
        self.world.close()

    def test_gripper_proxy_bodies_exist(self):
        proxies = self.gripper.proxy_body_ids
        # CAD-derived proxy decomposes fixed components into chunks of <= 12 shapes
        # to avoid PyBullet's 16-shape compound truncation. Thus 2 fixed chunks + 2 jaw bodies = 4 bodies.
        self.assertEqual(len(proxies), 4, "Must have exactly 4 proxy bodies: 2 fixed chunks, left jaw, right jaw")
        self.assertEqual(len(self.gripper.fixed_body_ids), 2)
        self.assertGreaterEqual(self.gripper.palm_body_id, 0)
        self.assertGreaterEqual(self.gripper.left_jaw_body_id, 0)
        self.assertGreaterEqual(self.gripper.right_jaw_body_id, 0)

        # Bodies must be registered in PyBullet
        for bid in proxies:
            info = p.getBodyInfo(bid, physicsClientId=self.world.client_id)
            self.assertIsNotNone(info)

    def test_jaw_motion_along_travel_axis(self):
        """
        Verify jaw motion along canonical X travel axis:
        - In open state, finger mesh frames sit at TCP origin (open spacing is in mesh vertices).
        - In closed state, left finger translates +5.2mm along X, right finger translates -5.2mm along X.
        - Physical gap between jaw meshes narrows from ~37.2mm to ~27.0mm.
        """
        tcp = [0.0, 0.360, 0.150]
        quat = self.tool_down_quat

        # 1. Fully open
        self.gripper.set_gripper_state(False)
        self.gripper.set_tcp_pose(tcp, quat)

        pos_l_open, _ = p.getBasePositionAndOrientation(
            self.gripper.left_jaw_body_id, physicsClientId=self.world.client_id
        )
        pos_r_open, _ = p.getBasePositionAndOrientation(
            self.gripper.right_jaw_body_id, physicsClientId=self.world.client_id
        )

        # 2. Fully closed
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp, quat)

        pos_l_closed, _ = p.getBasePositionAndOrientation(
            self.gripper.left_jaw_body_id, physicsClientId=self.world.client_id
        )
        pos_r_closed, _ = p.getBasePositionAndOrientation(
            self.gripper.right_jaw_body_id, physicsClientId=self.world.client_id
        )

        travel_m = self.gripper.collision_asset["finger_travel_m"]

        # Displacements in TCP frame: left shifts +X, right shifts -X
        # Since tool_down_quat has yaw 90, TCP X is robot Y
        # Compute displacement vectors
        disp_l = np.array(pos_l_closed) - np.array(pos_l_open)
        disp_r = np.array(pos_r_closed) - np.array(pos_r_open)

        self.assertAlmostEqual(float(np.linalg.norm(disp_l)), travel_m, places=4)
        self.assertAlmostEqual(float(np.linalg.norm(disp_r)), travel_m, places=4)

        # Direct PyBullet distance between jaws
        self.gripper.set_gripper_state(False)
        self.gripper.set_tcp_pose(tcp, quat)
        pts_open = p.getClosestPoints(
            self.gripper.left_jaw_body_id, self.gripper.right_jaw_body_id, 0.1, physicsClientId=self.world.client_id
        )
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp, quat)
        pts_closed = p.getClosestPoints(
            self.gripper.left_jaw_body_id, self.gripper.right_jaw_body_id, 0.1, physicsClientId=self.world.client_id
        )
        self.assertAlmostEqual(pts_open[0][8] - pts_closed[0][8], 2.0 * travel_m, places=3)

    def test_attached_piece_collision_filter_toggle(self):
        piece = self.world.pieces["black_rook_0"]
        pos_init, _ = piece.get_pose_robot_base()

        tcp = pos_init - self.gripper.tcp_to_grasp_center
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp, self.tool_down_quat)

        # This test isolates collision-filter lifecycle. The nominal virtual
        # stroke does not contact the 22.5 mm rook, so bypass grasp eligibility.
        self.assertTrue(self.gripper.attach_piece(piece))
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
        # Shift laterally so the jaw mesh deeply penetrates the piece body
        intersect_pos = [piece_pos[0], piece_pos[1] + 0.012, piece_pos[2]]
        self.gripper.set_tcp_pose(intersect_pos, self.tool_down_quat)
        p.performCollisionDetection(physicsClientId=self.world.client_id)
        contacts = self.world.get_gripper_piece_contacts()
        self.assertGreater(len(contacts), 0, "Re-enabled collision proxies should register contacts with piece")
        colliding_pieces = {c["piece_id"] for c in contacts}
        self.assertIn("black_rook_0", colliding_pieces)


if __name__ == "__main__":
    unittest.main()
