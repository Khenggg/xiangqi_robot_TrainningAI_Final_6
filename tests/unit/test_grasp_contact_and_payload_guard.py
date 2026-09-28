"""Direct PyBullet checks for grasp truth and carried-piece collisions."""

import unittest

import numpy as np
import pybullet as p

from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.physics.state import GraspStatus
from src.simulation.physics.transforms import quat_to_rot_matrix, rpy_deg_to_quat
from src.simulation.physics.world import VirtualPhysicalWorld


class GraspContactAndPayloadGuardTests(unittest.TestCase):
    def setUp(self):
        self.world = VirtualPhysicalWorld()
        self.guard = FR3CollisionGuard(self.world)
        self.world.step_until_settled(max_steps=60)

    def tearDown(self):
        self.world.close()

    def test_nominal_closed_jaws_cannot_claim_rook_without_contact(self):
        piece = self.world.pieces["black_rook_0"]
        center, _ = piece.get_pose_robot_base()
        gripper = self.world.gripper
        gripper.set_gripper_state(True)
        gripper.set_tcp_pose(center, rpy_deg_to_quat([180.0, 0.0, 90.0]))

        gaps = []
        for jaw in (gripper.left_jaw_body_id, gripper.right_jaw_body_id):
            points = p.getClosestPoints(jaw, piece.body_id, distance=0.05,
                                        physicsClientId=self.world.client_id)
            gaps.append(min(float(point[8]) for point in points))
        self.assertTrue(all(gap > gripper.MAX_JAW_CONTACT_GAP_M for gap in gaps), gaps)

        result = self.world.try_grasp(target_piece_id=piece.piece_id)
        self.assertFalse(result.success)
        self.assertEqual(result.status, GraspStatus.NO_JAW_CONTACT)
        self.assertIsNone(self.world.get_attached_piece())

    def _place_attached_piece_for_collision(self, target_xyz):
        piece = self.world.pieces["black_rook_0"]
        self.world.gripper.attach_piece(piece)
        robot = self.world.robot_body_id
        client = self.world.client_id
        flange = p.getLinkState(robot, 5, computeForwardKinematics=True, physicsClientId=client)
        rotation = quat_to_rot_matrix(flange[5])
        grasp_xyz = np.asarray(flange[4]) + rotation @ (
            self.world._tool_offset + self.world.gripper.tcp_to_grasp_center
        )
        grasp_transform = np.eye(4)
        grasp_transform[:3, :3] = rotation
        grasp_transform[:3, 3] = grasp_xyz
        target_transform = np.eye(4)
        target_transform[:3, 3] = target_xyz
        self.world.gripper.T_gripper_piece = np.linalg.inv(grasp_transform) @ target_transform
        piece.set_pose_robot_base(target_xyz, [0, 0, 0, 1])
        q = [p.getJointState(robot, joint, physicsClientId=client)[0] for joint in range(6)]
        return piece, q

    def test_carried_piece_penetrating_floor_is_rejected(self):
        piece, q = self._place_attached_piece_for_collision([0.4, 0.0, 0.0])
        points = p.getClosestPoints(piece.body_id, self.world.floor_body_id, 0.05,
                                    physicsClientId=self.world.client_id)
        self.assertLess(min(point[8] for point in points), 0.0)
        result = self.guard.validate_configuration(q)
        self.assertFalse(result.safe)
        self.assertEqual(result.colliding_body, "payload")
        self.assertEqual(result.obstacle, "floor")

    def test_carried_piece_penetrating_robot_link_is_rejected(self):
        aabb = p.getAABB(self.world.robot_body_id, 2, physicsClientId=self.world.client_id)
        target = np.mean(aabb, axis=0).tolist()
        piece, q = self._place_attached_piece_for_collision(target)
        points = p.getClosestPoints(piece.body_id, self.world.robot_body_id, 0.05,
                                    physicsClientId=self.world.client_id)
        self.assertLess(min(point[8] for point in points), 0.0)
        result = self.guard.validate_configuration(q)
        self.assertFalse(result.safe)
        self.assertEqual(result.colliding_body, "payload")
        self.assertEqual(result.obstacle, "robot_link_2")


if __name__ == "__main__":
    unittest.main()
