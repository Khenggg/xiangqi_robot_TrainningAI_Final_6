"""Regression coverage for authoritative simulator poses and viewer/physics frames."""

from __future__ import annotations

import json
import math
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

import numpy as np
import pybullet as p

from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.runtime import VirtualXiangqiSimulation
from src.simulation.virtual_fr3_backend import VirtualFR3Backend


ROOT = Path(__file__).resolve().parents[2]
SCENE_PATH = ROOT / "shared" / "virtual_fr3_scene.json"
PROFILE_PATH = ROOT / "shared" / "robot_profiles" / "fr3.json"
URDF_PATH = ROOT / "robot-3d-viewer" / "assets" / "fr3_v6" / "fairino3_v6.urdf"


def _rotation_rpy(rpy):
    roll, pitch, yaw = (float(value) for value in rpy)
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]], dtype=float)
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]], dtype=float)
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]], dtype=float)
    return rz @ ry @ rx


def _rotation_z(angle):
    cosine, sine = math.cos(angle), math.sin(angle)
    return np.array(
        [[cosine, -sine, 0], [sine, cosine, 0], [0, 0, 1]],
        dtype=float,
    )


def _angle_between(first, second):
    cosine = (float(np.trace(first.T @ second)) - 1.0) / 2.0
    return math.acos(max(-1.0, min(1.0, cosine)))


class SimulatorPoseAuthorityParityTests(unittest.TestCase):
    # One micron and one microradian are well below the 0.5 mm collision margin
    # and the visible defect scale, while allowing float/quaternion roundoff.
    LINK_POSITION_TOLERANCE_M = 1e-6
    LINK_ORIENTATION_TOLERANCE_RAD = 1e-6
    # Scene and board dimensions share exact configuration values; 1 nm only
    # accommodates PyBullet's double-precision quaternion reconstruction.
    BOARD_PLANE_TOLERANCE_M = 1e-9
    BOARD_NORMAL_TOLERANCE_RAD = 1e-9

    def setUp(self):
        self.world = VirtualPhysicalWorld()
        self.backend = VirtualFR3Backend()
        self.sim = VirtualXiangqiSimulation(backend=self.backend, world=self.world)
        self.assertTrue(self.sim.connect(), "safe configured startup pose must validate")

    def tearDown(self):
        self.sim.stop()
        self.world.close()

    def test_board_penetrating_pose_is_rejected_and_safe_state_is_preserved(self):
        safe_start_deg = [0, -70, 110, -105, -120, 0]
        penetrating_deg = [0, -60, 110, -105, -120, 0]
        self.assertTrue(self.backend.set_authoritative_joints(safe_start_deg))

        direct = self.sim.collision_guard.validate_configuration(
            np.radians(penetrating_deg), restore_state=True
        )
        self.assertFalse(direct.safe)
        self.assertEqual(direct.obstacle, "board")

        before = self.backend.get_state_snapshot()
        self.assertFalse(self.backend.move_joint(penetrating_deg, speed_factor=100))
        after = self.backend.get_state_snapshot()

        self.assertEqual(after.joints_deg, before.joints_deg)
        self.assertEqual(after.tcp_pose_mm_deg, before.tcp_pose_mm_deg)
        self.assertEqual(after.motion_state, "COLLISION_REJECTED")
        self.assertTrue(after.connected)
        self.assertTrue(after.collision_validated)
        self.assertIn("board", (after.last_error or "").lower())

    def test_safe_endpoints_with_intermediate_collision_are_rejected(self):
        start_deg = [0, -45, 90, -45, -90, 0]
        end_deg = [0, -45, 90, -45, -90, 90]
        start_rad, end_rad = np.radians(start_deg), np.radians(end_deg)
        self.assertTrue(self.sim.collision_guard.validate_configuration(start_rad, restore_state=True).safe)
        self.assertTrue(self.sim.collision_guard.validate_configuration(end_rad, restore_state=True).safe)

        swept = self.sim.collision_guard.validate_trajectory(
            [start_rad, end_rad], restore_state=True
        )
        self.assertFalse(swept.safe)
        self.assertIsNotNone(swept.sample_index)
        self.assertTrue(swept.obstacle == "board" or (swept.obstacle or "").startswith("piece:"))

        before = self.backend.get_state_snapshot()
        self.assertFalse(self.backend.move_joint(end_deg, speed_factor=100))
        after = self.backend.get_state_snapshot()
        self.assertEqual(after.joints_deg, before.joints_deg)
        self.assertEqual(after.tcp_pose_mm_deg, before.tcp_pose_mm_deg)
        self.assertTrue(after.collision_validated)

    def test_nearby_safe_pose_remains_accepted(self):
        target_deg = [0, -46, 90, -45, -90, 0]
        target_rad = np.radians(target_deg)
        self.assertTrue(self.sim.collision_guard.validate_configuration(target_rad, restore_state=True).safe)
        self.assertTrue(self.backend.move_joint(target_deg, speed_factor=100))
        snapshot = self.backend.get_state_snapshot()
        self.assertEqual(snapshot.joints_deg, target_deg)
        self.assertTrue(snapshot.collision_validated)

    def test_unsafe_initial_pose_never_reaches_ready(self):
        bad_world = VirtualPhysicalWorld()
        bad_backend = VirtualFR3Backend()
        bad_pose_deg = [0, -60, 110, -105, -120, 0]
        self.assertTrue(bad_backend.set_authoritative_joints(bad_pose_deg))
        bad_sim = VirtualXiangqiSimulation(backend=bad_backend, world=bad_world)
        try:
            self.assertFalse(bad_sim.connect())
            snapshot = bad_backend.get_state_snapshot()
            self.assertFalse(snapshot.connected)
            self.assertFalse(snapshot.collision_validated)
            self.assertEqual(snapshot.motion_state, "COLLISION_REJECTED")
            self.assertIn("startup", (snapshot.last_error or "").lower())
        finally:
            bad_sim.stop()
            bad_world.close()

    def test_three_link_frames_match_pybullet_urdf_for_representative_joint_vectors(self):
        with PROFILE_PATH.open("r", encoding="utf-8") as stream:
            profile = json.load(stream)
        with SCENE_PATH.open("r", encoding="utf-8") as stream:
            scene = json.load(stream)
        urdf = ET.parse(URDF_PATH).getroot()
        urdf_joints = [joint for joint in urdf.findall("joint") if joint.attrib.get("type") == "revolute"]
        self.assertEqual(len(urdf_joints), 6)
        self.assertEqual(len(profile["joints"]), 6)

        three_origins = []
        for visual_joint, urdf_joint in zip(profile["joints"], urdf_joints):
            origin = urdf_joint.find("origin")
            xyz_urdf = [float(v) for v in origin.attrib.get("xyz", "0 0 0").split()]
            rpy_urdf = [float(v) for v in origin.attrib.get("rpy", "0 0 0").split()]
            axis = [float(v) for v in urdf_joint.find("axis").attrib.get("xyz", "0 0 1").split()]
            np.testing.assert_allclose(visual_joint["origin_xyz_m"], xyz_urdf, atol=1e-12, rtol=0)
            np.testing.assert_allclose(visual_joint["origin_rpy_rad"], rpy_urdf, atol=1e-12, rtol=0)
            np.testing.assert_allclose(axis, [0, 0, 1], atol=1e-12, rtol=0)
            three_origins.append((np.asarray(xyz_urdf), np.asarray(rpy_urdf)))

        root_cfg = scene["robot_base_to_3d_world"]
        root_rotation = np.asarray(root_cfg["rotation_matrix"], dtype=float)
        root_translation = np.asarray(root_cfg["translation_m"], dtype=float)
        representative_q_deg = [
            [0, -45, 90, -45, -90, 0],
            [0, -60, 110, -105, -120, 0],
            [0, -70, 110, -105, -120, 0],
            [37, -32, 78, -118, 64, -29],
        ]
        worst_position = 0.0
        worst_orientation = 0.0
        checked_links = 0
        for joints_deg in representative_q_deg:
            q_rad = np.radians(joints_deg)
            self.world.sync_robot_collision_configuration(q_rad)
            T_three = np.eye(4)
            for index, ((xyz, rpy), angle) in enumerate(zip(three_origins, q_rad)):
                T_origin = np.eye(4)
                T_origin[:3, :3] = _rotation_rpy(rpy)
                T_origin[:3, 3] = xyz
                T_joint = np.eye(4)
                T_joint[:3, :3] = _rotation_z(float(angle))
                T_three = T_three @ T_origin @ T_joint

                state = p.getLinkState(
                    self.world.robot_body_id,
                    index,
                    computeForwardKinematics=True,
                    physicsClientId=self.world.client_id,
                )
                T_bullet = np.eye(4)
                T_bullet[:3, :3] = np.asarray(
                    p.getMatrixFromQuaternion(state[5]), dtype=float
                ).reshape(3, 3)
                T_bullet[:3, 3] = np.asarray(state[4], dtype=float)
                expected_position = root_rotation @ T_three[:3, 3] + root_translation
                actual_position = root_rotation @ T_bullet[:3, 3] + root_translation
                expected_rotation = root_rotation @ T_three[:3, :3]
                actual_rotation = root_rotation @ T_bullet[:3, :3]
                position_error = float(np.linalg.norm(expected_position - actual_position))
                orientation_error = _angle_between(expected_rotation, actual_rotation)
                worst_position = max(worst_position, position_error)
                worst_orientation = max(worst_orientation, orientation_error)
                checked_links += 1

        self.assertEqual(checked_links, 24, "compare all six movable links in four configurations")
        self.assertLessEqual(worst_position, self.LINK_POSITION_TOLERANCE_M)
        self.assertLessEqual(worst_orientation, self.LINK_ORIENTATION_TOLERANCE_RAD)
        print(
            "Three/URDF parity: "
            f"{checked_links} link poses; max position {worst_position:.3e} m, "
            f"max orientation {worst_orientation:.3e} rad"
        )

    def test_three_and_pybullet_board_top_planes_match(self):
        with SCENE_PATH.open("r", encoding="utf-8") as stream:
            scene = json.load(stream)
        visual = scene["virtual_board_placement"]
        visual_point = np.asarray(visual["board_center_in_3d_world_m"], dtype=float)
        visual_normal = np.array([0.0, 1.0, 0.0])

        physics_center, physics_quat = p.getBasePositionAndOrientation(
            self.world.board_body_id, physicsClientId=self.world.client_id
        )
        physics_rotation = np.asarray(
            p.getMatrixFromQuaternion(physics_quat), dtype=float
        ).reshape(3, 3)
        physics_top_robot = np.asarray(physics_center) + physics_rotation @ np.array(
            [0.0, 0.0, self.world._board_half_z]
        )
        root_cfg = scene["robot_base_to_3d_world"]
        root_rotation = np.asarray(root_cfg["rotation_matrix"], dtype=float)
        root_translation = np.asarray(root_cfg["translation_m"], dtype=float)
        physics_point = root_rotation @ physics_top_robot + root_translation
        physics_normal = root_rotation @ physics_rotation[:, 2]
        center_error = float(np.linalg.norm(physics_point - visual_point))
        plane_error = abs(float(np.dot(physics_point - visual_point, visual_normal)))
        normal_error = _angle_between(
            np.column_stack((np.array([1.0, 0.0, 0.0]), visual_normal, np.array([0.0, 0.0, 1.0]))),
            np.column_stack((np.array([1.0, 0.0, 0.0]), physics_normal, np.array([0.0, 0.0, 1.0]))),
        )

        self.assertLessEqual(center_error, self.BOARD_PLANE_TOLERANCE_M)
        self.assertLessEqual(plane_error, self.BOARD_PLANE_TOLERANCE_M)
        self.assertLessEqual(normal_error, self.BOARD_NORMAL_TOLERANCE_RAD)
        print(
            "Board surface parity: "
            f"center offset {center_error:.3e} m, plane offset {plane_error:.3e} m, "
            f"normal angle {normal_error:.3e} rad"
        )


if __name__ == "__main__":
    unittest.main()
