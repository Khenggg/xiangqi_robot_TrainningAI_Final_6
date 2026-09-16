"""
Comprehensive unit tests for Phase 3 Final Closure:
1. Single Tool Frame Contract (TCP at fingertips, 0.218m rigid offset, 0 grasp offset).
2. Authoritative Motion & Rigid TCP Invariant (||p_tcp - p_flange|| == 0.218m).
3. Collision Guard Negative Tests (penetration rejection, state preservation).
4. Cartesian 3-Stage Trajectory (Lift XY drift <= 1.0mm, Transit Z deviation <= 1.0mm, Land XY drift <= 1.0mm, tilt <= 0.5 deg).
5. All 90 cells in cell_reachability_dataset.json kinematically valid and collision-free.
"""

import json
import math
from pathlib import Path
import sys
import unittest
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.domain.geometry import get_physical_geometry
from src.simulation.kinematics.fr3 import FR3Kinematics
from src.simulation.kinematics.urdf_chain import Pose3D, matrix_to_rpy, rpy_to_matrix
from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.physics.transforms import quat_to_rot_matrix, rot_matrix_to_quat
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.runtime import VirtualXiangqiSimulation
from src.simulation.virtual_fr3_backend import VirtualFR3Backend


class Phase3FinalClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geom = get_physical_geometry()
        cls.kinematics = FR3Kinematics()

    def test_canonical_geometry_single_source_of_truth(self):
        """Verify board thickness 10.5mm and piece geometry strictly match across contracts."""
        self.assertEqual(self.geom.thickness_mm, 10.5)
        self.assertAlmostEqual(self.geom.board_thickness_m, 0.0105, places=5)
        self.assertEqual(self.geom.outer_length_mm, 410.0)
        self.assertEqual(self.geom.outer_width_mm, 367.0)
        self.assertEqual(self.geom.piece_diameter_mm, 22.5)
        self.assertEqual(self.geom.piece_height_mm, 9.43)

        # Check virtual_physics.json board collision thickness
        physics_path = _PROJECT_ROOT / "shared" / "virtual_physics.json"
        with open(physics_path, "r", encoding="utf-8") as f:
            physics_cfg = json.load(f)
        self.assertEqual(physics_cfg["board"]["collision_thickness_m"], 0.0105)

        # Check virtual_gripper_profile.json grasp center offset is exactly zero
        gripper_path = _PROJECT_ROOT / "shared" / "virtual_gripper_profile.json"
        with open(gripper_path, "r", encoding="utf-8") as f:
            gripper_cfg = json.load(f)
        self.assertEqual(gripper_cfg["tcp_to_grasp_center_m"], [0.0, 0.0, 0.0])

    def test_tool_frame_rigid_invariant(self):
        """Verify ||p_tcp - p_flange|| == 0.218m across diverse joint configurations."""
        backend = VirtualFR3Backend()
        test_configs = [
            [0.0, -45.0, 90.0, -45.0, -90.0, 0.0],
            [15.0, -60.0, 110.0, -50.0, -90.0, 15.0],
            [-30.0, -80.0, 130.0, -90.0, -90.0, -30.0],
            [45.0, -30.0, 60.0, -120.0, -90.0, 45.0],
        ]

        for q_deg in test_configs:
            q_rad = np.radians(q_deg)
            flange_pose = backend._compute_flange_pose_mm_deg(q_rad)
            tcp_pose = backend._compute_tcp_pose_mm_deg(q_rad)

            p_flange = np.array(flange_pose[:3]) / 1000.0
            p_tcp = np.array(tcp_pose[:3]) / 1000.0
            dist = float(np.linalg.norm(p_tcp - p_flange))

            self.assertAlmostEqual(
                dist,
                0.218,
                places=4,
                msg=f"Flange-to-TCP distance must be 0.218m at q={q_deg}, got {dist:.6f}m",
            )

    def test_downward_tool_orientation_contract(self):
        """Verify target tool orientation points tool approach axis (+Z_tool) along -Z_robot."""
        scene_path = _PROJECT_ROOT / "shared" / "virtual_fr3_scene.json"
        with open(scene_path, "r", encoding="utf-8") as f:
            scene_cfg = json.load(f)

        R_target = np.array(
            scene_cfg["virtual_board_placement"]["target_tool_orientation_matrix"],
            dtype=float,
        )
        z_tool = np.array([0.0, 0.0, 1.0])
        tool_approach_in_robot = R_target @ z_tool

        # Must point vertically down along -Z_robot
        np.testing.assert_allclose(tool_approach_in_robot, [0.0, 0.0, -1.0], atol=1e-6)

        # In 3D world: robot -Z maps to -Y_world (downward)
        R_world_robot = np.array(scene_cfg["robot_base_to_3d_world"]["rotation_matrix"], dtype=float)
        approach_in_world = R_world_robot @ tool_approach_in_robot
        np.testing.assert_allclose(approach_in_world, [0.0, -1.0, 0.0], atol=1e-6)

    def test_collision_negative_command_below_board(self):
        """Commanding TCP penetrating board must be rejected by collision guard."""
        world = VirtualPhysicalWorld()
        guard = FR3CollisionGuard(world)
        backend = VirtualFR3Backend()
        backend.connect()
        backend.set_collision_guard(guard)

        # Move to safe hover above board
        backend.move_cartesian([-180.0, 0.0, 80.5, 180.0, 0.0, 90.0], samples=5)
        # Attempt to penetrate through board surface (Z=0.0mm while board surface is 10.5mm)
        target_below = [-180.0, 0.0, 0.0, 180.0, 0.0, 90.0]
        result = backend.move_cartesian(target_below, samples=10)
        self.assertFalse(result, "move_cartesian penetrating board must be rejected")
        self.assertEqual(backend.get_state_snapshot().motion_state, "COLLISION_REJECTED")

        world.close()
        backend.disconnect()

    def test_collision_negative_preserves_last_safe_state(self):
        """When a colliding motion is rejected, authoritative state must remain at last safe pose."""
        world = VirtualPhysicalWorld()
        guard = FR3CollisionGuard(world)
        backend = VirtualFR3Backend()
        backend.connect()
        backend.set_collision_guard(guard)

        # Move to safe hover
        backend.move_cartesian([-180.0, 0.0, 80.5, 180.0, 0.0, 90.0], samples=5)
        safe_snapshot = backend.get_state_snapshot()
        safe_joints = list(safe_snapshot.joints_deg)

        # Reject penetrating command
        target_below = [-180.0, 0.0, 0.0, 180.0, 0.0, 90.0]
        backend.move_cartesian(target_below, samples=10)

        after_snapshot = backend.get_state_snapshot()
        np.testing.assert_allclose(
            after_snapshot.joints_deg,
            safe_joints,
            atol=1e-2,
            err_msg="Robot configuration must remain at last safe pose after rejected move",
        )

        world.close()
        backend.disconnect()

    def test_cartesian_3stage_trajectory_fidelity_and_drift(self):
        """
        Verify authoritative 3-stage trajectory (Lift -> Transit -> Land) via REAL backend state listener:
        - Lift: sample points along Lift have XY drift <= 1.0mm, Z monotonically increasing.
        - Transit: sample points along Transit have Z deviation <= 1.0mm from safe transit plane.
        - Land: sample points along Land have XY drift <= 1.0mm, Z monotonically decreasing.
        - Tool orientation tilt along all waypoints <= 0.5 deg.
        - Sample count >= 10 per stage (true trajectory evidence, NOT synthetic interpolation).
        """
        sim = VirtualXiangqiSimulation()
        sim.start()

        emitted_snaps = []
        sim.backend.add_state_listener(lambda s: emitted_snaps.append(s))

        # Pick and place between (2, 1) and (4, 1)
        src_cell = (2, 1)
        dst_cell = (4, 1)
        res = sim.execute_3stage_trajectory(src_cell=src_cell, dst_cell=dst_cell, samples_per_stage=20)
        self.assertTrue(res["success"], f"3-stage trajectory failed: {res.get('error')}")

        lift_snaps = [s for s in emitted_snaps if s.trajectory_stage == "LIFT"]
        transit_snaps = [s for s in emitted_snaps if s.trajectory_stage == "TRANSIT"]
        land_snaps = [s for s in emitted_snaps if s.trajectory_stage == "LAND"]

        # 1. Assert sample counts >= 10 per stage
        self.assertGreaterEqual(len(lift_snaps), 10, f"Lift stage must have >= 10 real samples, got {len(lift_snaps)}")
        self.assertGreaterEqual(len(transit_snaps), 10, f"Transit stage must have >= 10 real samples, got {len(transit_snaps)}")
        self.assertGreaterEqual(len(land_snaps), 10, f"Land stage must have >= 10 real samples, got {len(land_snaps)}")

        board_z = sim.board_surface_z
        z_grasp = board_z + sim.geom.piece_height_mm / 2000.0  # 0.015215 m
        z_transit = board_z + 0.070                            # 0.0805 m
        p_src_grasp = np.array(sim.cell_to_robot_xyz_m(src_cell[0], src_cell[1], z_grasp))
        p_dst_grasp = np.array(sim.cell_to_robot_xyz_m(dst_cell[0], dst_cell[1], z_grasp))

        def get_tilt_deg(rpy_deg):
            R = rpy_to_matrix(np.radians(rpy_deg))
            z_tool = R @ np.array([0.0, 0.0, 1.0])
            cos_val = np.clip(np.dot(z_tool, [0.0, 0.0, -1.0]), -1.0, 1.0)
            return math.degrees(math.acos(cos_val))

        # 2. Lift stage validation (XY drift <= 1.0mm, Z monotonically increasing, tilt <= 0.5 deg)
        for s in lift_snaps:
            p = np.array(s.tcp_pose_mm_deg[:3]) / 1000.0
            xy_drift_mm = np.linalg.norm(p[:2] - p_src_grasp[:2]) * 1000.0
            self.assertLessEqual(xy_drift_mm, 1.0, f"Lift XY drift {xy_drift_mm:.3f}mm exceeds 1.0mm tolerance")
            tilt = get_tilt_deg(s.tcp_pose_mm_deg[3:])
            self.assertLessEqual(tilt, 0.5, f"Lift tilt {tilt:.3f} deg exceeds 0.5 deg tolerance")

        z_lift = [s.tcp_pose_mm_deg[2] / 1000.0 for s in lift_snaps]
        for i in range(1, len(z_lift)):
            self.assertGreaterEqual(z_lift[i], z_lift[i-1] - 1e-5, f"Lift Z must increase monotonically at step {i}")

        # 3. Transit stage validation (Z dev <= 1.0mm from z_transit, tilt <= 0.5 deg)
        for s in transit_snaps:
            p = np.array(s.tcp_pose_mm_deg[:3]) / 1000.0
            z_dev_mm = abs(p[2] - z_transit) * 1000.0
            self.assertLessEqual(z_dev_mm, 1.0, f"Transit Z deviation {z_dev_mm:.3f}mm exceeds 1.0mm tolerance")
            tilt = get_tilt_deg(s.tcp_pose_mm_deg[3:])
            self.assertLessEqual(tilt, 0.5, f"Transit tilt {tilt:.3f} deg exceeds 0.5 deg tolerance")

        # 4. Land stage validation (XY drift <= 1.0mm, Z monotonically decreasing, tilt <= 0.5 deg)
        for s in land_snaps:
            p = np.array(s.tcp_pose_mm_deg[:3]) / 1000.0
            xy_drift_mm = np.linalg.norm(p[:2] - p_dst_grasp[:2]) * 1000.0
            self.assertLessEqual(xy_drift_mm, 1.0, f"Land XY drift {xy_drift_mm:.3f}mm exceeds 1.0mm tolerance")
            tilt = get_tilt_deg(s.tcp_pose_mm_deg[3:])
            self.assertLessEqual(tilt, 0.5, f"Land tilt {tilt:.3f} deg exceeds 0.5 deg tolerance")

        z_land = [s.tcp_pose_mm_deg[2] / 1000.0 for s in land_snaps]
        for i in range(1, len(z_land)):
            self.assertLessEqual(z_land[i], z_land[i-1] + 1e-5, f"Land Z must decrease monotonically at step {i}")
        self.assertAlmostEqual(z_land[-1], z_grasp, delta=0.001, msg=f"Final landing altitude {z_land[-1]:.6f}m must reach grasp height {z_grasp:.6f}m")

        sim.stop()

    def test_collision_endpoint_safe_intermediate_collision(self):
        """Intermediate collision along Cartesian trajectory must be rejected and preserve start pose."""
        world = VirtualPhysicalWorld()
        guard = FR3CollisionGuard(world)
        backend = VirtualFR3Backend()
        backend.connect()
        backend.set_collision_guard(guard)

        # Place obstacle piece at intermediate cell (4, 4) hover path
        piece = world.pieces["black_cannon_0"]
        piece.set_pose_robot_base([-0.34, 0.0, 0.0805], [0, 0, 0, 1])

        p_start = [-340.0, -80.0, 80.5, 180.0, 0.0, 90.0]
        p_goal = [-340.0, 80.0, 80.5, 180.0, 0.0, 90.0]

        backend.move_cartesian(p_start, samples=5)
        start_joints = list(backend.get_state_snapshot().joints_deg)

        res = backend.move_cartesian(p_goal, samples=20)
        self.assertFalse(res, "MoveCartesian passing through intermediate obstacle piece must be rejected")
        self.assertEqual(backend.get_state_snapshot().motion_state, "COLLISION_REJECTED")
        self.assertIn("Gripper colliding with obstacle piece", backend._last_error)
        np.testing.assert_allclose(
            backend.get_state_snapshot().joints_deg,
            start_joints,
            atol=1e-2,
            err_msg="Start safe joints must be preserved upon intermediate collision",
        )

        backend.disconnect()
        world.close()

    def test_collision_non_gripper_arm_link_with_board(self):
        """Robot arm link (link 2) colliding with board must be rejected."""
        world = VirtualPhysicalWorld()
        guard = FR3CollisionGuard(world)
        q_board = np.deg2rad([-170.0, -150.0, -134.0, -90.0, 0.0, 0.0])
        res = guard.validate_configuration(q_board)
        self.assertFalse(res.safe, "Arm link colliding with board must be detected as unsafe")
        self.assertEqual(res.colliding_body, "robot")
        self.assertEqual(res.obstacle, "board")
        self.assertEqual(res.robot_link, 2)
        world.close()

    def test_collision_self_collision_rejection(self):
        """Robot self-collision (link 0 <-> link 2) must be detected and rejected."""
        world = VirtualPhysicalWorld()
        guard = FR3CollisionGuard(world)
        q_self = np.deg2rad([0.0, -45.0, -160.0, -260.0, -160.0, 0.0])
        res = guard.validate_configuration(q_self)
        self.assertFalse(res.safe, "Robot self-collision must be detected as unsafe")
        self.assertEqual(res.colliding_body, "robot")
        self.assertIn("self_link", str(res.obstacle))
        world.close()

    def test_preposition_fail_fast_unreachable_cell(self):
        """Unreachable source cell in execute_3stage_trajectory must fail fast at PREPOSITION."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        res = sim.execute_3stage_trajectory((99, 99), (4, 1))
        self.assertFalse(res["success"], "Unreachable cell trajectory must fail")
        self.assertEqual(res["failed_stage"], "PREPOSITION")
        self.assertIn("unreachable", res["error"].lower())
        sim.stop()

    def test_all_90_cells_dataset_reachability_and_collision_free(self):
        """Verify all 90 cells in shared/cell_reachability_dataset.json are 100% collision-free."""
        dataset_path = _PROJECT_ROOT / "shared" / "cell_reachability_dataset.json"
        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["metadata"]["total_cells"], 90)
        self.assertEqual(len(data["cells"]), 90)

        world = VirtualPhysicalWorld()
        guard = FR3CollisionGuard(world)

        for cell in data["cells"]:
            r, c = cell["row"], cell["col"]
            self.assertTrue(cell["reachable"], f"Cell ({r}, {c}) marked unreachable")

            # Check approach pose collision
            q_app = np.deg2rad(cell["approach_joints_deg"])
            col_app = guard.validate_configuration(q_app)
            self.assertTrue(col_app.safe, f"Approach collision at ({r}, {c}): {col_app.failure_reason}")

            # Check grasp pose collision
            q_gr = np.deg2rad(cell["grasp_joints_deg"])
            col_gr = guard.validate_configuration(q_gr, allowed_grasp_piece_id="*")
            self.assertTrue(col_gr.safe, f"Grasp collision at ({r}, {c}): {col_gr.failure_reason}")

        world.close()


if __name__ == "__main__":
    unittest.main()
