"""
Direct PyBullet Contact & Clearance Validation Suite (Phase P3 / Collision Verification).

This suite independently reads raw PyBullet contacts and closest points (getClosestPoints)
to prove that collision detection is physically grounded and not mocked or hallucinated:
1. All 19 CAD fixed collider boxes + 2 moving finger hulls (total 21 shapes across 4 bodies)
   exist in PyBullet, explicitly verifying the 19th component (viewer_adapter_collar).
2. Direct PyBullet clearance & penetration reading for gripper vs board.
3. Direct PyBullet contact/penetration reading for gripper vs board outer rim.
4. Direct PyBullet contact/penetration reading for gripper vs floor.
5. Direct PyBullet contact/penetration reading for gripper vs robot arm (non-adjacent links).
6. Direct PyBullet carried/attached payload collision filtering, board contact, and piece-piece collision.
7. Direct PyBullet jaw closing travel (5.2mm each finger along X) and jaw-to-jaw / obstacle contact.
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
from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.physics.transforms import rpy_deg_to_quat


class DirectPyBulletContactClearanceTests(unittest.TestCase):
    def setUp(self):
        self.world = VirtualPhysicalWorld()
        self.gripper = self.world.gripper
        self.guard = FR3CollisionGuard(self.world)
        self.tool_down_quat = rpy_deg_to_quat([180.0, 0.0, 90.0])
        self.world.step_until_settled(max_steps=60)

    def tearDown(self):
        self.world.close()

    def test_final_collider_body_and_all_19_components_exist(self):
        """
        Verify that PyBullet spawns exactly 4 kinematic multi-bodies for the gripper:
        - 2 fixed chunk multi-bodies (split to prevent PyBullet's 16-shape compound truncation)
        - 2 finger multi-bodies (left jaw, right jaw)
        And verify that all 19 fixed component boxes plus 2 finger hulls exist in PyBullet,
        explicitly verifying the 19th fixed component: 'viewer_adapter_collar'.
        """
        proxies = self.gripper.proxy_body_ids
        self.assertEqual(len(proxies), 4, "Must have exactly 4 proxy multi-bodies: 2 fixed chunks + 2 jaws")
        self.assertEqual(len(self.gripper.fixed_body_ids), 2, "Fixed boxes must be split into 2 multi-bodies")

        # 1. Inspect chunk 0: first 12 fixed component boxes
        shape_data_0 = p.getCollisionShapeData(self.gripper.fixed_body_ids[0], -1, physicsClientId=self.world.client_id)
        self.assertEqual(len(shape_data_0), 12, "Chunk 0 must contain exactly 12 compound collision shapes")

        # 2. Inspect chunk 1: remaining 7 fixed component boxes (12 + 7 = 19)
        shape_data_1 = p.getCollisionShapeData(self.gripper.fixed_body_ids[1], -1, physicsClientId=self.world.client_id)
        self.assertEqual(len(shape_data_1), 7, "Chunk 1 must contain exactly 7 compound collision shapes")

        total_fixed_shapes = len(shape_data_0) + len(shape_data_1)
        self.assertEqual(total_fixed_shapes, 19, "Total fixed collider boxes in PyBullet must equal 19")

        # 3. Explicitly verify the 19th component: 'viewer_adapter_collar'
        # In collision asset, index 18 (19th item) is viewer_adapter_collar.
        # In chunk 1, it is the 7th shape (child shape index 6).
        collar_asset = self.gripper.collision_asset["fixed_boxes"][18]
        self.assertEqual(collar_asset["name"], "viewer_adapter_collar")

        collar_shape = shape_data_1[6]
        # PyBullet shape data: (body_id, link_index, geometry_type, dimensions, filename, frame_pos, frame_orn)
        self.assertEqual(collar_shape[2], p.GEOM_BOX, "Collar collider must be a GEOM_BOX")
        # dimensions in PyBullet shapeData are full extents (2 * half_extents)
        expected_extents = np.array(collar_asset["half_extents_m"]) * 2.0
        np.testing.assert_allclose(
            collar_shape[3],
            expected_extents,
            atol=1e-4,
            err_msg="PyBullet 19th collar collider extents must match CAD asset (2 * half_extents)",
        )
        np.testing.assert_allclose(
            collar_shape[5],
            collar_asset["center_m"],
            atol=1e-4,
            err_msg="PyBullet 19th collar collider center offset must match CAD asset",
        )

        # 4. Moving finger hulls
        shape_left = p.getCollisionShapeData(self.gripper.left_jaw_body_id, -1, physicsClientId=self.world.client_id)
        shape_right = p.getCollisionShapeData(self.gripper.right_jaw_body_id, -1, physicsClientId=self.world.client_id)
        self.assertEqual(len(shape_left), 1, "Left jaw multi-body must contain 1 mesh shape")
        self.assertEqual(len(shape_right), 1, "Right jaw multi-body must contain 1 mesh shape")
        self.assertEqual(shape_left[0][2], p.GEOM_MESH)
        self.assertEqual(shape_right[0][2], p.GEOM_MESH)

        total_shapes = total_fixed_shapes + len(shape_left) + len(shape_right)
        self.assertEqual(total_shapes, 21, "Total gripper collision shapes in PyBullet must equal 21")

    def test_direct_pybullet_gripper_board_clearance_and_penetration(self):
        """
        Directly query PyBullet closest points between gripper proxy bodies and board:
        - At nominal hover (TCP Z = board_surface_z + 80mm): distance > 0 for all proxies.
        - Penetrating into board (TCP Z = 0.0m): at least one proxy body exhibits negative distance (< 0).
        """
        # Nominal hover at center
        hover_tcp = [0.0, 0.360, self.world.board_surface_z + 0.080]
        self.gripper.set_tcp_pose(hover_tcp, self.tool_down_quat)

        # Query direct PyBullet closest points for hover
        for proxy_id in self.gripper.proxy_body_ids:
            pts = p.getClosestPoints(
                proxy_id,
                self.world.board_body_id,
                distance=0.1,
                physicsClientId=self.world.client_id,
            )
            for pt in pts:
                # pt[8] is contactDistance. Greater than 0 means separation.
                self.assertGreater(
                    pt[8], 0.005,
                    f"Proxy {proxy_id} must have positive separation from board when hovering",
                )

        # Move gripper to penetrate board surface (Z = 0.0m)
        penetrate_tcp = [0.0, 0.360, 0.0]
        self.gripper.set_tcp_pose(penetrate_tcp, self.tool_down_quat)

        penetration_found = False
        min_distance = 1.0
        for proxy_id in self.gripper.proxy_body_ids:
            pts = p.getClosestPoints(
                proxy_id,
                self.world.board_body_id,
                distance=0.05,
                physicsClientId=self.world.client_id,
            )
            for pt in pts:
                dist = pt[8]
                if dist < min_distance:
                    min_distance = dist
                if dist < 0.0:
                    penetration_found = True

        self.assertTrue(penetration_found, f"PyBullet must directly report negative distance (penetration), min_dist={min_distance}")
        self.assertLess(min_distance, -0.01, "Deep penetration into board must yield < -10mm distance")

    def test_direct_pybullet_gripper_rim_contact(self):
        """
        Directly verify PyBullet contact/penetration when gripper proxy collides with board outer rim.
        Board outer boundary is in Y in [0.1765, 0.5435], X in [-0.2245, 0.2245].
        """
        # Position TCP at board rim edge and lower Z so collar overlaps board border
        rim_tcp = [0.2245, 0.360, self.world.board_surface_z - 0.010]
        self.gripper.set_tcp_pose(rim_tcp, self.tool_down_quat)

        pts = []
        for proxy_id in self.gripper.proxy_body_ids:
            contacts = p.getClosestPoints(
                proxy_id,
                self.world.board_body_id,
                distance=0.01,
                physicsClientId=self.world.client_id,
            )
            for pt in contacts:
                if pt[8] < 0.0:
                    pts.append(pt)

        self.assertGreater(len(pts), 0, "PyBullet must detect direct penetration between gripper proxy and board rim")

    def test_direct_pybullet_gripper_floor_contact(self):
        """
        Directly query PyBullet closest points between gripper proxy bodies and floor plane.
        When TCP is lowered below ground (Z = -0.05m), PyBullet must report contactDistance < 0.
        """
        floor_tcp = [0.200, 0.0, -0.050]
        self.gripper.set_tcp_pose(floor_tcp, self.tool_down_quat)

        penetration_found = False
        min_dist = 1.0
        for proxy_id in self.gripper.proxy_body_ids:
            pts = p.getClosestPoints(
                proxy_id,
                self.world.floor_body_id,
                distance=0.05,
                physicsClientId=self.world.client_id,
            )
            for pt in pts:
                if pt[8] < min_dist:
                    min_dist = pt[8]
                if pt[8] < 0.0:
                    penetration_found = True

        self.assertTrue(penetration_found, f"PyBullet must report negative distance when gripper penetrates floor, min_dist={min_dist}")
        self.assertLess(min_dist, -0.03, "Floor penetration must be < -30mm")

    def test_direct_pybullet_gripper_arm_contact(self):
        """
        Directly verify PyBullet contact between gripper proxy and non-adjacent robot arm links
        in a folded configuration (q = [0, -45, -160, -260, -160, 0] deg).
        """
        q_folded = np.deg2rad([0.0, -45.0, -160.0, -260.0, -160.0, 0.0])
        self.world.sync_robot_collision_configuration(q_folded)

        arm_penetrations = []
        for proxy_id in self.gripper.proxy_body_ids:
            pts = p.getClosestPoints(
                proxy_id,
                self.world.robot_body_id,
                distance=0.01,
                physicsClientId=self.world.client_id,
            )
            for pt in pts:
                # pt[4] is robot link index. Link 5 is flange (mounting link).
                # Contact with Link 2, 3, or 1 represents physical collision!
                if int(pt[4]) != 5 and pt[8] < 0.0:
                    arm_penetrations.append((int(pt[4]), pt[8]))

        self.assertGreater(len(arm_penetrations), 0, "PyBullet must directly detect gripper-to-arm penetration in folded pose")
        colliding_links = {link for link, _ in arm_penetrations}
        self.assertIn(2, colliding_links, "Gripper must directly collide with Link 2 in this pose")

    def test_direct_pybullet_carried_piece_filtering_and_collision(self):
        """
        Directly verify physical contact behavior of carried/attached piece:
        1. When attached, contact points between piece and gripper proxies are 0 (filtered).
        2. When lowered into board, PyBullet directly detects piece-to-board penetration (distance < 0).
        3. When moved to intersect another resting piece, PyBullet directly detects piece-to-piece penetration.
        """
        piece = self.world.pieces["black_rook_0"]
        pos_init, _ = piece.get_pose_robot_base()

        # Position gripper at grasp pose and attach piece
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(pos_init, self.tool_down_quat)

        # Exercise carried-body collision filtering directly. Grasp eligibility
        # is separately tested against both CAD jaw hulls.
        self.assertTrue(self.gripper.attach_piece(piece))
        self.assertTrue(self.gripper.is_attached)

        # 1. Verify filtering: stepping world yields 0 contacts between attached piece and all 4 proxies
        self.world.step(5)
        for proxy_id in self.gripper.proxy_body_ids:
            cps = p.getContactPoints(piece.body_id, proxy_id, physicsClientId=self.world.client_id)
            self.assertEqual(len(cps), 0, f"Attached piece must have 0 contacts with proxy {proxy_id}")

        # 2. Lower gripper so attached piece penetrates into board surface (Z = 0.0)
        self.gripper.set_tcp_pose([pos_init[0], pos_init[1], 0.0], self.tool_down_quat)

        pts_board = p.getClosestPoints(
            piece.body_id,
            self.world.board_body_id,
            distance=0.01,
            physicsClientId=self.world.client_id,
        )
        piece_board_penetrations = [pt for pt in pts_board if pt[8] < 0.0]
        self.assertGreater(len(piece_board_penetrations), 0, "PyBullet must detect direct penetration between carried piece and board")
        self.assertLess(min(pt[8] for pt in piece_board_penetrations), -0.003)

        # 3. Move carried piece to penetrate another piece (black_knight_0)
        other_piece = self.world.pieces["black_knight_0"]
        other_pos, _ = other_piece.get_pose_robot_base()

        # Place carried piece directly at other piece position
        self.gripper.set_tcp_pose(other_pos, self.tool_down_quat)

        pts_pieces = p.getClosestPoints(
            piece.body_id,
            other_piece.body_id,
            distance=0.01,
            physicsClientId=self.world.client_id,
        )
        piece_clash_penetrations = [pt for pt in pts_pieces if pt[8] < 0.0]
        self.assertGreater(len(piece_clash_penetrations), 0, "PyBullet must detect direct penetration between carried piece and obstacle piece")
        self.assertLess(min(pt[8] for pt in piece_clash_penetrations), -0.005)

        # Cleanup
        self.world.release_attached_piece()
        self.assertFalse(self.gripper.is_attached)

    def test_direct_pybullet_jaw_closure_and_obstacle_contact(self):
        """
        Verify PyBullet kinematic jaw motion and closest points distance between the two closing jaws:
        - Open jaw-to-jaw distance: ~37.2 mm.
        - Closed jaw-to-jaw distance: ~27.0 mm.
        - Difference reflects 2 * finger_travel_m (2 * 5.2mm = 10.4mm).
        - Clamping contact on an obstacle body of width 30mm:
          When open (gap > 30mm), obstacle clearance is positive (> 0).
          When closed (gap < 30mm), jaws press/penetrate obstacle (distance <= 0).
        """
        tcp = [0.0, 0.360, 0.150]

        # 1. Verify open positions and jaw-to-jaw distance
        self.gripper.set_gripper_state(False)
        self.gripper.set_tcp_pose(tcp, self.tool_down_quat)
        pos_l_open, _ = p.getBasePositionAndOrientation(self.gripper.left_jaw_body_id, physicsClientId=self.world.client_id)
        pos_r_open, _ = p.getBasePositionAndOrientation(self.gripper.right_jaw_body_id, physicsClientId=self.world.client_id)

        pts_open = p.getClosestPoints(
            self.gripper.left_jaw_body_id,
            self.gripper.right_jaw_body_id,
            distance=0.1,
            physicsClientId=self.world.client_id,
        )
        self.assertGreater(len(pts_open), 0)
        dist_open = pts_open[0][8]
        self.assertAlmostEqual(dist_open, 0.0372, places=3, msg="Open jaw-to-jaw distance should be ~37.2mm")

        # 2. Verify closed positions and jaw-to-jaw distance
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp, self.tool_down_quat)
        pos_l_closed, _ = p.getBasePositionAndOrientation(self.gripper.left_jaw_body_id, physicsClientId=self.world.client_id)
        pos_r_closed, _ = p.getBasePositionAndOrientation(self.gripper.right_jaw_body_id, physicsClientId=self.world.client_id)

        pts_closed = p.getClosestPoints(
            self.gripper.left_jaw_body_id,
            self.gripper.right_jaw_body_id,
            distance=0.1,
            physicsClientId=self.world.client_id,
        )
        self.assertGreater(len(pts_closed), 0)
        dist_closed = pts_closed[0][8]
        self.assertAlmostEqual(dist_closed, 0.0270, places=3, msg="Closed jaw-to-jaw distance should be ~27.0mm")

        # Distance difference matches finger travel stroke
        stroke_closure = dist_open - dist_closed
        self.assertAlmostEqual(stroke_closure, 2.0 * self.gripper.collision_asset["finger_travel_m"], places=3)

        # 3. Clamping contact on a 30mm obstacle block spawned between the jaws
        obs_shape = p.createCollisionShape(
            p.GEOM_BOX, halfExtents=[0.015, 0.015, 0.010], physicsClientId=self.world.client_id
        )
        obs_body = p.createMultiBody(
            baseMass=0.0,
            baseCollisionShapeIndex=obs_shape,
            basePosition=tcp,
            physicsClientId=self.world.client_id,
        )
        try:
            # Jaws open: 37.2mm gap clears 30mm obstacle (clearance > 0)
            self.gripper.set_gripper_state(False)
            self.gripper.set_tcp_pose(tcp, self.tool_down_quat)
            pts_l = p.getClosestPoints(self.gripper.left_jaw_body_id, obs_body, distance=0.05, physicsClientId=self.world.client_id)
            pts_r = p.getClosestPoints(self.gripper.right_jaw_body_id, obs_body, distance=0.05, physicsClientId=self.world.client_id)
            min_dist_open = min(min([pt[8] for pt in pts_l], default=1.0), min([pt[8] for pt in pts_r], default=1.0))
            self.assertGreater(min_dist_open, 0.001, f"Open jaws must clear 30mm obstacle, got {min_dist_open}")

            # Jaws closed: 27.0mm gap collides with 30mm obstacle (clearance <= 0)
            self.gripper.set_gripper_state(True)
            self.gripper.set_tcp_pose(tcp, self.tool_down_quat)
            pts_l = p.getClosestPoints(self.gripper.left_jaw_body_id, obs_body, distance=0.05, physicsClientId=self.world.client_id)
            pts_r = p.getClosestPoints(self.gripper.right_jaw_body_id, obs_body, distance=0.05, physicsClientId=self.world.client_id)
            min_dist_closed = min(min([pt[8] for pt in pts_l], default=1.0), min([pt[8] for pt in pts_r], default=1.0))
            self.assertLessEqual(min_dist_closed, 0.0, f"Closed jaws must physically clamp/penetrate 30mm obstacle, got {min_dist_closed}")
        finally:
            p.removeBody(obs_body, physicsClientId=self.world.client_id)


if __name__ == "__main__":
    unittest.main()
