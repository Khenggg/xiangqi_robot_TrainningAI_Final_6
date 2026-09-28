"""Current virtual flange, fingertip, board, and seed provenance contract."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
from types import SimpleNamespace

import numpy as np
import pybullet as p

from src.domain.geometry import (
    ProvenanceStatus,
    get_canonical_tool_geometry,
    load_canonical_tool_geometry,
)
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.physics.transforms import quat_to_rot_matrix
from src.simulation.runtime import VirtualXiangqiSimulation
from src.simulation.virtual_fr3_backend import VirtualFR3Backend


ROOT = Path(__file__).resolve().parents[2]


class ToolBoardGeometryContractTests(unittest.TestCase):
    def test_adapter_collar_and_visible_board_rim_exist_in_pybullet(self):
        sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        sim.start()
        try:
            gripper = sim.world.gripper
            client = sim.world.client_id
            actual = sum(len(p.getCollisionShapeData(body, -1, physicsClientId=client))
                         for body in gripper.fixed_body_ids)
            self.assertEqual(actual, len(gripper.collision_asset["fixed_boxes"]))
            collar = gripper.collision_asset["fixed_boxes"][-1]
            self.assertEqual(collar["name"], "viewer_adapter_collar")
            tip_pos = gripper.tcp_pos + quat_to_rot_matrix(gripper.tcp_quat) @ collar["center_m"]
            sphere_shape = p.createCollisionShape(p.GEOM_SPHERE, radius=0.002, physicsClientId=client)
            probe = p.createMultiBody(baseMass=0.0, baseCollisionShapeIndex=sphere_shape,
                                      basePosition=tip_pos, physicsClientId=client)
            self.assertTrue(any(
                p.getClosestPoints(body, probe, distance=0.0, physicsClientId=client)
                for body in gripper.fixed_body_ids
            ))
            p.removeBody(probe, physicsClientId=client)

            board = sim.world.board_placement_state
            half_u = sim.geom.outer_width_mm / 2000.0
            half_z = sim.geom.thickness_mm / 2000.0
            frame_local = np.array([half_u + 0.005, 0.0, half_z - 0.001])
            frame_world = np.asarray(board.board_center_robot_m) + (
                quat_to_rot_matrix(board.quat_robot_from_board) @ frame_local
            )
            rim_probe = p.createMultiBody(baseMass=0.0, baseCollisionShapeIndex=sphere_shape,
                                          basePosition=frame_world, physicsClientId=client)
            self.assertTrue(p.getClosestPoints(rim_probe, sim.world.board_body_id,
                                               distance=0.0, physicsClientId=client))
        finally:
            sim.stop()

    def test_jaw_closure_rejects_obstacle_and_keeps_open_state(self):
        sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        sim.start()
        try:
            self.assertTrue(sim.runtime_go_service_safe()["success"])
            gripper = sim.world.gripper
            left = gripper.collision_asset["finger_boxes"][0]
            local = np.array(left["center_m"], dtype=float)
            local[0] += left["half_extents_m"][0] + gripper.collision_asset["finger_travel_m"] / 2.0
            world_pos = gripper.tcp_pos + quat_to_rot_matrix(gripper.tcp_quat) @ local
            client = sim.world.client_id
            shape = p.createCollisionShape(p.GEOM_SPHERE, radius=0.001, physicsClientId=client)
            body = p.createMultiBody(baseMass=0.0, baseCollisionShapeIndex=shape,
                                     basePosition=world_pos, physicsClientId=client)
            sim.world.pieces["probe_obstacle"] = SimpleNamespace(body_id=body, attached_to_gripper=False)
            self.assertFalse(sim.backend.set_gripper(True))
            self.assertFalse(sim.backend.is_gripper_closed())
            self.assertIn("Gripper command rejected", sim.backend._last_error)
            sim.backend.set_allowed_grasp_piece_id("probe_obstacle")
            self.assertFalse(sim.backend.set_gripper(True))
            self.assertIn("crushing target piece", sim.backend._last_error)
        finally:
            sim.world.pieces.pop("probe_obstacle", None)
            sim.stop()

    def test_measured_tip_transform_is_shared_by_backend_and_world(self):
        tool = get_canonical_tool_geometry(reload=True)
        self.assertEqual(tool.status, ProvenanceStatus.MEASURED_PHYSICAL)
        self.assertAlmostEqual(tool.flange_to_tcp_distance_m, 0.1683)
        backend = VirtualFR3Backend()
        world = VirtualPhysicalWorld()
        try:
            visual = json.loads((ROOT / "shared/gripper_visual_asset.json").read_text(encoding="utf-8"))
            link_to_flange = np.asarray(visual["profiles"]["fr3"]["robot_flange_origin_m"])
            np.testing.assert_allclose(backend._T_flange_tcp[:3, 3], tool.canonical_tcp_offset_m)
            np.testing.assert_allclose(backend._T_link_flange[:3, 3], link_to_flange)
            np.testing.assert_allclose(backend._T_link_tcp[:3, 3], world._tool_offset)
            np.testing.assert_allclose(world._tool_offset, link_to_flange + tool.canonical_tcp_offset_m)
            self.assertEqual(len(world.gripper.collision_asset["fixed_boxes"]), 19)
            visual_tip_z = max(
                box["center_m"][2] + box["half_extents_m"][2]
                for box in world.gripper.collision_asset["finger_boxes"]
            )
            self.assertLess(abs(visual_tip_z), 0.0005)
        finally:
            world.close()

    def test_direct_pybullet_board_and_arm_penetrations_are_rejected(self):
        sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        sim.start()
        try:
            xyz = sim.cell_to_robot_xyz_m(4, 4, sim.board_surface_z - 0.008)
            pose = [v * 1000 for v in xyz] + list(sim.target_tool_euler_deg)
            ik = sim.backend.solve_tcp_ik(pose, allow_multi_seed=True)
            self.assertFalse(ik.success)
            self.assertIn("collision", ik.failure_reason.lower())
            # Diagnostic-only raw IK supplies a known penetrating q; no motion is sent.
            sim.backend.collision_guard = None
            try:
                raw_ik = sim.backend.solve_tcp_ik(pose, allow_multi_seed=True)
            finally:
                sim.backend.collision_guard = sim.collision_guard
            self.assertTrue(raw_ik.success)
            board_result = sim.collision_guard.validate_configuration(raw_ik.joints_rad)
            sim.world.sync_robot_collision_configuration(raw_ik.joints_rad)
            board_distances = [
                pt[8] for body in sim.world.gripper.proxy_body_ids
                for pt in p.getClosestPoints(body, sim.world.board_body_id, distance=0.5,
                                             physicsClientId=sim.world.client_id)
            ]
            self.assertLess(min(board_distances), -0.005)
            self.assertFalse(board_result.safe)
            self.assertEqual(board_result.obstacle, "board")

            arm_q = np.deg2rad([161.509, -139.051, -45.877, -244.745, 135.818, -65.748])
            arm_result = sim.collision_guard.validate_configuration(arm_q)
            sim.world.sync_robot_collision_configuration(arm_q)
            arm_distances = [
                pt[8] for body in sim.world.gripper.proxy_body_ids
                for pt in p.getClosestPoints(body, sim.world.robot_body_id, distance=0.0,
                                             physicsClientId=sim.world.client_id)
                if pt[4] != 5
            ]
            self.assertLess(min(arm_distances), -0.015)
            self.assertFalse(arm_result.safe)
            self.assertTrue(arm_result.obstacle.startswith("robot_link_"))

            floor_q = np.deg2rad([-7.805, -133.751, -128.525, -47.54, 4.115, 41.582])
            floor_result = sim.collision_guard.validate_configuration(floor_q)
            sim.world.sync_robot_collision_configuration(floor_q)
            floor_distances = [
                pt[8] for body in sim.world.gripper.proxy_body_ids
                for pt in p.getClosestPoints(body, sim.world.floor_body_id, distance=0.0,
                                             physicsClientId=sim.world.client_id)
            ]
            self.assertLess(min(floor_distances), 0.0)
            self.assertEqual(floor_result.obstacle, "floor")
            self.assertEqual(floor_result.colliding_body, "gripper")
        finally:
            sim.stop()

    def test_invalid_profile_fails_instead_of_using_shorter_tool(self):
        profile = json.loads((ROOT / "shared/robot_profiles/fr3.json").read_text(encoding="utf-8"))
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "fr3.json"
            profile["tool"]["canonical_tcp"]["provenance"] = "UNKNOWN"
            path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_canonical_tool_geometry(path)

            profile["tool"]["canonical_tcp"]["provenance"] = "MEASURED_PHYSICAL"
            profile["tool"]["canonical_tcp"]["length_mm"] = 168.3
            profile["tool"]["canonical_tcp"]["flange_to_tcp_rpy_deg"] = [0.0, 5.0, 0.0]
            path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_canonical_tool_geometry(path)

            profile["tool"]["canonical_tcp"]["flange_to_tcp_rpy_deg"] = [0.0, 0.0, 0.0]
            profile["tool"]["canonical_tcp"]["length_mm"] = 150.0
            path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_canonical_tool_geometry(path)

    def test_scene_profile_disagreement_fails_closed(self):
        scene = json.loads((ROOT / "shared/virtual_fr3_scene.json").read_text(encoding="utf-8"))
        scene["tool_transform"]["flange_to_tcp_xyz_m"] = [0.0, 0.0, 0.150]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "scene.json"
            path.write_text(json.dumps(scene), encoding="utf-8")
            with self.assertRaises(ValueError):
                VirtualFR3Backend(scene_config_path=path)
            with self.assertRaises(ValueError):
                VirtualPhysicalWorld(scene_config_path=path)

            scene["tool_transform"]["flange_to_tcp_xyz_m"] = [0.0, 0.0, 0.1683]
            scene["tool_transform"]["flange_to_tcp_rpy_deg"] = [0.0, 5.0, 0.0]
            path.write_text(json.dumps(scene), encoding="utf-8")
            with self.assertRaises(ValueError):
                VirtualFR3Backend(scene_config_path=path)
            with self.assertRaises(ValueError):
                VirtualPhysicalWorld(scene_config_path=path)

    def test_stale_seeds_are_ignored_and_fingertips_clear_board(self):
        sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        sim.start()
        try:
            self.assertEqual(sim.reachability_dataset, {})
            self.assertIsNotNone(sim._get_piece_at_cell(0, 0))
            xyz = sim.cell_to_robot_xyz_m(
                4, 4, sim.board_surface_z + sim.geom.piece_height_mm / 2000.0
            )
            pose = [v * 1000.0 for v in xyz] + list(sim.target_tool_euler_deg)
            ik = sim.backend.solve_tcp_ik(pose, allow_multi_seed=True)
            self.assertTrue(ik.success)
            self.assertTrue(sim.collision_guard.validate_configuration(ik.joints_rad).safe)
            sim.world.sync_robot_collision_configuration(ik.joints_rad)
            clearance_m, _ = sim.world.get_board_to_robot_clearance()
            self.assertGreaterEqual(clearance_m, sim.collision_guard.gripper_board_margin_m)
        finally:
            sim.stop()

    def test_repeated_placement_updates_do_not_compound_board_height(self):
        sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        sim.start()
        try:
            self.assertTrue(sim.runtime_go_service_safe()["success"])
            self.assertTrue(sim.set_board_placement(board_height_offset_mm=10.0, internal_reset=True)["success"])
            self.assertTrue(sim.set_board_placement(forward_shift_mm=10.0, internal_reset=True)["success"])
            expected_z = sim.nominal_board_surface_z + 0.010
            self.assertAlmostEqual(sim.board_surface_z, expected_z)
            self.assertAlmostEqual(sim.placement_state.board_surface_z_robot_m, expected_z)
            self.assertAlmostEqual(sim.world.board_surface_z, expected_z)
            np.testing.assert_allclose(
                sim.world.get_board_pose()[0], sim.placement_state.board_center_robot_m, atol=1e-6
            )
            rook_pos, _ = sim.world.pieces["black_rook_0"].get_pose_robot_base()
            np.testing.assert_allclose(
                rook_pos[:2], sim.cell_to_robot_xyz_m(0, 0)[:2], atol=0.001
            )
        finally:
            sim.stop()

    def test_attached_piece_is_checked_and_candidate_pose_is_restored(self):
        sim = VirtualXiangqiSimulation(auto_sync_telemetry=False)
        sim.start()
        try:
            self.assertTrue(sim.runtime_go_service_safe()["success"])
            piece_id = next(iter(sim.world.pieces))
            piece = sim.world.pieces[piece_id]
            row, col, _ = piece.get_nearest_intersection()
            grasp_z = sim.board_surface_z + sim.geom.piece_height_mm / 2000.0
            xyz = sim.cell_to_robot_xyz_m(row, col, grasp_z)
            grasp_pose = [v * 1000.0 for v in xyz] + list(sim.target_tool_euler_deg)
            grasp_ik = sim.backend.solve_tcp_ik(
                grasp_pose, allow_multi_seed=True, allow_alternate_yaw=True,
                allowed_grasp_piece_id=piece_id,
            )
            self.assertTrue(grasp_ik.success)
            # This test targets carried-payload collision and pose restoration.
            # Supply bilateral contact synthetically; actual CAD grip is covered separately.
            with mock.patch.object(sim.world.gripper, "_jaw_gap_to_piece_m", return_value=0.0):
                self.assertTrue(sim.pick_piece(piece_id).success)
            before_pos, before_quat = piece.get_pose_robot_base()
            result = sim.collision_guard.validate_configuration(
                grasp_ik.joints_rad, restore_state=True
            )
            self.assertFalse(result.safe)
            self.assertEqual(result.colliding_body, "payload")
            self.assertEqual(result.obstacle, "board")
            after_pos, after_quat = piece.get_pose_robot_base()
            np.testing.assert_allclose(after_pos, before_pos, atol=1e-9)
            np.testing.assert_allclose(after_quat, before_quat, atol=1e-9)

            obstacle = next(p for pid, p in sim.world.pieces.items() if pid != piece_id)
            obstacle.set_pose_robot_base(
                [before_pos[0], before_pos[1], before_pos[2] - 0.008], before_quat
            )
            safe_q = np.deg2rad(sim.backend.get_state_snapshot().joints_deg)
            q_before = sim.world.get_robot_joint_positions()
            result = sim.collision_guard.validate_configuration(safe_q)
            self.assertFalse(result.safe)
            self.assertEqual(result.colliding_body, "payload")
            self.assertEqual(result.obstacle, f"piece:{obstacle.piece_id}")
            self.assertFalse(sim.collision_guard.validate_configuration(grasp_ik.joints_rad).safe)
            np.testing.assert_allclose(sim.world.get_robot_joint_positions(), q_before, atol=1e-9)
        finally:
            sim.stop()
