"""
Targeted regression tests for conservative full-tool collision envelope (tool_bridge)
and simulator board-penetration defect resolution.

Verifies:
1. Tool coverage invariant: bridge spans continuously from TCP region back toward flange.
2. Critical regression test: TCP-only arithmetic (Z_tcp > Z_board) appears acceptable,
   but actual PyBullet collision geometry detects tool_bridge board penetration.
3. State preservation test: colliding candidate motion is rejected and preserves old authoritative state.
4. Trajectory tunnel test: safe start and safe end with intermediate board penetration is caught
   by subdivision (anti-tunneling) and returns sample_index.
5. Safe control case: safe valid configurations sufficiently above board pass cleanly.
"""

import math
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
from src.simulation.virtual_fr3_backend import VirtualFR3Backend
from src.simulation.kinematics.fr3 import FR3Kinematics


class SimulatorToolCollisionEnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kinematics = FR3Kinematics()

    def setUp(self):
        self.world = VirtualPhysicalWorld()
        self.guard = FR3CollisionGuard(self.world)
        self.backend = VirtualFR3Backend(kinematics=self.kinematics)
        self.backend.connect()
        self.backend.collision_guard = self.guard

    def tearDown(self):
        self.backend.disconnect()
        self.world.close()

    def test_tool_coverage_invariant(self):
        """
        Verify the simulation-only conservative tool collision coverage spans
        continuously from the TCP region toward the flange region.
        """
        gripper = self.world.gripper
        self.assertTrue(
            getattr(gripper, "SIMULATION_CONSERVATIVE_COLLISION_ENVELOPE", False),
            "Gripper must have SIMULATION_CONSERVATIVE_COLLISION_ENVELOPE marker enabled",
        )
        self.assertGreaterEqual(
            gripper.tool_bridge_body_id,
            0,
            "tool_bridge_body_id must be a valid registered PyBullet body ID",
        )
        self.assertIn(
            gripper.tool_bridge_body_id,
            gripper.collision_tool_body_ids,
            "tool_bridge must be present in collision_tool_body_ids collection",
        )

        flange_to_tcp_dist = float(np.linalg.norm(gripper.flange_to_tcp_xyz_m))
        self.assertGreater(flange_to_tcp_dist, 0.0)
        self.assertGreaterEqual(
            gripper.tool_bridge_length_m,
            flange_to_tcp_dist - 1e-6,
            "Tool bridge length must cover at least the simulation flange-to-TCP distance",
        )

        # Check full axial extent of box collision shape (2 * halfExtent >= flange_to_tcp_dist)
        bridge_axial_span = float(gripper.tool_bridge_half_extents_m[2] * 2.0)
        self.assertGreaterEqual(
            bridge_axial_span,
            flange_to_tcp_dist - 1e-6,
            "Collision shape axial span must fully cover flange-to-TCP distance",
        )

        # PyBullet body registration check
        info = p.getBodyInfo(gripper.tool_bridge_body_id, physicsClientId=self.world.client_id)
        self.assertIsNotNone(info)

    def test_critical_regression_tool_board_penetration(self):
        """
        Critical regression test reproducing the board penetration defect:
        TCP-based height check alone appears acceptable (tcp_z > board_z),
        palm and jaws proxies do not touch the board, but the tool body
        (tool_bridge) intersects the board in actual PyBullet collision geometry.
        """
        # q_bad tilts the wrist such that TCP is above the board surface,
        # but the tool bridge behind the TCP penetrates into the board collider.
        q_bad_deg = [0.0, -60.0, 110.0, -105.0, -120.0, 0.0]
        q_bad_rad = np.deg2rad(q_bad_deg)

        # 1. Forward kinematics check: TCP height is strictly above board surface
        pose = self.kinematics.forward_kinematics(q_bad_rad)
        T_tcp = pose.as_matrix() @ self.backend._T_flange_tcp
        tcp_z = float(T_tcp[2, 3])
        board_z = float(self.world.board_surface_z)
        self.assertGreater(
            tcp_z,
            board_z,
            f"TCP must be strictly above board surface ({tcp_z*1000:.2f}mm > {board_z*1000:.2f}mm)",
        )

        # 2. Verify that palm and jaw proxies alone do not register collision with board
        client = self.world.client_id
        self.world.sync_robot_collision_configuration(q_bad_rad)
        p.performCollisionDetection(physicsClientId=client)

        palm_pts = p.getClosestPoints(
            self.world.gripper.palm_body_id,
            self.world.board_body_id,
            distance=0.0005,
            physicsClientId=client,
        )
        jaw_l_pts = p.getClosestPoints(
            self.world.gripper.left_jaw_body_id,
            self.world.board_body_id,
            distance=0.0005,
            physicsClientId=client,
        )
        jaw_r_pts = p.getClosestPoints(
            self.world.gripper.right_jaw_body_id,
            self.world.board_body_id,
            distance=0.0005,
            physicsClientId=client,
        )
        self.assertEqual(len(palm_pts), 0, "Palm proxy alone does not touch board in this pose")
        self.assertEqual(len(jaw_l_pts), 0, "Left jaw alone does not touch board in this pose")
        self.assertEqual(len(jaw_r_pts), 0, "Right jaw alone does not touch board in this pose")

        # 3. CollisionGuard authoritative validation must reject this configuration
        result = self.guard.validate_configuration(q_bad_rad)
        self.assertFalse(result.safe, "CollisionGuard must reject tool-penetrating configuration")
        self.assertEqual(result.obstacle, "board", "Obstacle must be identified as 'board'")
        self.assertEqual(
            result.colliding_body,
            "tool_bridge",
            "Colliding component must explicitly identify 'tool_bridge'",
        )
        self.assertIsNotNone(result.penetration_m)
        self.assertGreater(
            result.penetration_m,
            0.0,
            "Actual geometric penetration into board must be positive",
        )

    def test_state_preservation_on_rejected_candidate(self):
        """
        Verify transactional motion semantics:
        A colliding motion command is rejected, and authoritative state
        (joints, TCP pose, motion_state) strictly preserves the pre-command state.
        """
        before = self.backend.get_state_snapshot()
        q_bad_deg = [0.0, -60.0, 110.0, -105.0, -120.0, 0.0]

        ok = self.backend.move_joint(q_bad_deg)
        after = self.backend.get_state_snapshot()

        self.assertFalse(ok, "Backend move_joint must return False for colliding target")
        self.assertEqual(
            after.joints_deg,
            before.joints_deg,
            "Joint angles must not change on collision rejection",
        )
        self.assertEqual(
            after.tcp_pose_mm_deg,
            before.tcp_pose_mm_deg,
            "TCP pose must not change on collision rejection",
        )
        self.assertEqual(
            after.motion_state,
            "COLLISION_REJECTED",
            "Motion state must be set to COLLISION_REJECTED",
        )
        self.assertIn(
            "MoveJ rejected by collision guard",
            after.last_error or "",
            "last_error must record collision guard rejection reason",
        )

    def test_trajectory_tunnel_anti_tunneling(self):
        """
        Verify anti-tunneling subdivision:
        q_start is safe, q_end is safe, but linear joint interpolation intersects
        the board via tool_bridge -> validate_trajectory returns unsafe with sample_index.
        """
        q_start_deg = [25.0, -60.0, 100.0, -110.0, -110.0, 0.0]
        q_end_deg = [45.0, -60.0, 120.0, -110.0, -110.0, 0.0]

        q_start_rad = np.deg2rad(q_start_deg)
        q_end_rad = np.deg2rad(q_end_deg)

        res_start = self.guard.validate_configuration(q_start_rad)
        self.assertTrue(res_start.safe, "Trajectory start waypoint must be safe")

        res_end = self.guard.validate_configuration(q_end_rad)
        self.assertTrue(res_end.safe, "Trajectory end waypoint must be safe")

        # Validate trajectory with default subdivision (<= 1.0 deg steps)
        res_traj = self.guard.validate_trajectory([q_start_rad, q_end_rad])
        self.assertFalse(
            res_traj.safe,
            "Trajectory with intermediate board penetration must be rejected",
        )
        self.assertIsNotNone(
            res_traj.sample_index,
            "sample_index must be recorded for failing intermediate step",
        )
        self.assertEqual(
            res_traj.obstacle,
            "board",
            "Colliding obstacle must be identified as 'board'",
        )
        self.assertEqual(
            res_traj.colliding_body,
            "tool_bridge",
            "Colliding body must be identified as 'tool_bridge'",
        )

    def test_safe_control_pose_passes(self):
        """
        Verify that normal valid configurations sufficiently above the board
        are accepted and not falsely rejected.
        """
        # Canonical home pose
        home_deg = [0.0, -45.0, 90.0, -45.0, -90.0, 0.0]
        home_rad = np.deg2rad(home_deg)
        res_home = self.guard.validate_configuration(home_rad)
        self.assertTrue(res_home.safe, "Canonical home pose must be collision-free")

        # Service safe pose
        service_deg = [0.0, -70.0, 60.0, -80.0, -90.0, 0.0]
        service_rad = np.deg2rad(service_deg)
        res_service = self.guard.validate_configuration(service_rad)
        self.assertTrue(res_service.safe, "Service safe pose must be collision-free")


if __name__ == "__main__":
    unittest.main()
