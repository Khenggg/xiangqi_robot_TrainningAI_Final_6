"""
Unit test for true mid-motion force drop during active robot trajectory (Phase P3.1).

Verifies:
1. schedule_force_drop() registers a mid-motion trigger threshold.
2. Drop occurs strictly while robot_motion_state == "MOVING".
3. Release linear speed exceeds 0.02 m/s inherited from trajectory.
4. DropEvent diagnostics captures sim_time, progress, pose, and velocities.
5. Robot continues executing trajectory to target while dropped piece undergoes
   independent ballistic flight and settles on the board.
"""

from pathlib import Path
import sys
import unittest
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.physics.state import PiecePhysicalState
from src.simulation.physics.transforms import quat_to_rot_matrix
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.runtime import SimulationRuntime
from src.simulation.virtual_fr3_backend import VirtualFR3Backend


class RuntimeMidMotionDropTests(unittest.TestCase):
    def setUp(self):
        self.world = VirtualPhysicalWorld()
        self.backend = VirtualFR3Backend(default_speed_factor=2.0)
        self.backend.connect()
        self.runtime = SimulationRuntime(
            world=self.world,
            backend=self.backend,
            auto_sync_telemetry=False,
        )
        self.runtime.start()
        # Let pieces settle
        self.world.step_until_settled(max_steps=60)

    def tearDown(self):
        self.runtime.stop()
        self.backend.disconnect()
        self.world.close()

    def test_mid_motion_drop_during_cartesian_move(self):
        piece_id = "black_knight_0"
        piece = self.world.pieces[piece_id]
        pos_init, _ = piece.get_pose_robot_base()

        # 1. Pick piece
        pick_res = self.runtime.pick_piece(piece_id)
        self.assertTrue(pick_res.success, f"Failed to pick {piece_id}: {pick_res.reason}")
        self.assertTrue(self.world.gripper.is_attached)
        self.assertEqual(self.world.gripper.attached_piece_id, piece_id)

        # 2. Schedule force drop at 50% trajectory progress
        self.runtime.schedule_force_drop(progress_threshold=0.5, target_piece_id=piece_id)

        # 3. Move across board towards (row=3, col=4)
        tx, ty, tz = self.runtime.cell_to_robot_xyz(3, 4)
        rx, ry, rz = self.runtime.target_tool_euler_deg
        grasp_center_offset = self.world.gripper.tcp_to_grasp_center[2]
        hover_z = pos_init[2] + grasp_center_offset + 0.070
        target_pose = [tx * 1000.0, ty * 1000.0, hover_z * 1000.0, rx, ry, rz]

        move_res = self.runtime.move_cartesian(target_pose, speed_factor=1.0)
        self.assertTrue(move_res, "Cartesian move should succeed")

        # 4. Verify DropEvent diagnostics
        drop_event = self.runtime.last_drop_event
        self.assertIsNotNone(drop_event, "DropEvent was not captured")
        self.assertTrue(drop_event.triggered, "DropEvent.triggered must be True")
        self.assertEqual(drop_event.robot_motion_state, "MOVING",
                         f"Drop must occur while robot is MOVING, got {drop_event.robot_motion_state}")
        self.assertEqual(drop_event.attached_piece_id, piece_id)
        self.assertGreaterEqual(drop_event.trajectory_progress, 0.35)
        self.assertLessEqual(drop_event.trajectory_progress, 0.75)
        self.assertGreater(drop_event.release_speed, 0.02,
                           f"Release speed must exceed 0.02 m/s, got {drop_event.release_speed}")
        self.assertEqual(len(drop_event.release_position), 3)
        self.assertEqual(len(drop_event.release_linear_velocity), 3)
        self.assertEqual(len(drop_event.release_angular_velocity), 3)
        self.assertIsNotNone(drop_event.release_gripper_position)
        self.assertEqual(len(drop_event.release_gripper_position), 3)
        self.assertIsNotNone(drop_event.release_gripper_orientation)
        self.assertEqual(len(drop_event.release_gripper_orientation), 4)
        self.assertIsNotNone(drop_event.release_piece_orientation)
        self.assertEqual(len(drop_event.release_piece_orientation), 4)

        # 5. Verify gripper is detached and robot reached target
        self.assertFalse(self.world.gripper.is_attached)
        robot_snapshot = self.backend.get_state_snapshot()
        self.assertEqual(robot_snapshot.motion_state, "IDLE")

        # 6. Step world to allow piece to finish settling
        self.world.step_until_settled(max_steps=120)
        self.assertIn(
            piece.physical_state,
            (PiecePhysicalState.RESTING, PiecePhysicalState.ON_BOARD, PiecePhysicalState.SETTLING),
        )
        pos_final, quat_final = piece.get_pose_robot_base()
        self.assertTrue(all(np.isfinite(pos_final)))
        self.assertTrue(all(np.isfinite(quat_final)))
        self.assertLess(piece.tilt_angle_deg, 5.0)

        # 7. Post-drop relative motion invariant (Phase P3.2.1)
        # Mathematically prove the piece is no longer kinematically attached to the moving gripper:
        # At release, T_rel,drop = T_gripper,drop^(-1) @ T_piece,drop was the grasp attachment transform.
        # After release, as robot arm continued along its independent trajectory and reached target,
        # T_rel,later = T_gripper,later^(-1) @ T_piece,later diverges substantially:
        # ||T_rel,later - T_rel,drop|| > epsilon
        p_piece_drop = np.array(drop_event.release_position, dtype=float)
        q_piece_drop = np.array(drop_event.release_piece_orientation, dtype=float)
        p_gripper_drop = np.array(drop_event.release_gripper_position, dtype=float)
        q_gripper_drop = np.array(drop_event.release_gripper_orientation, dtype=float)

        p_piece_final = np.array(pos_final, dtype=float)
        q_piece_final = np.array(quat_final, dtype=float)
        p_gripper_final = np.array(self.world.gripper.grasp_pos, dtype=float)
        q_gripper_final = np.array(self.world.gripper.grasp_quat, dtype=float)

        def make_se3(p_vec: np.ndarray, q_vec: np.ndarray) -> np.ndarray:
            T = np.eye(4, dtype=float)
            T[:3, :3] = quat_to_rot_matrix(q_vec)
            T[:3, 3] = p_vec
            return T

        def invert_se3(T: np.ndarray) -> np.ndarray:
            R = T[:3, :3]
            p_vec = T[:3, 3]
            T_inv = np.eye(4, dtype=float)
            T_inv[:3, :3] = R.T
            T_inv[:3, 3] = -R.T @ p_vec
            return T_inv

        T_gripper_drop = make_se3(p_gripper_drop, q_gripper_drop)
        T_piece_drop = make_se3(p_piece_drop, q_piece_drop)
        T_rel_drop = invert_se3(T_gripper_drop) @ T_piece_drop

        T_gripper_final = make_se3(p_gripper_final, q_gripper_final)
        T_piece_final = make_se3(p_piece_final, q_piece_final)
        T_rel_final = invert_se3(T_gripper_final) @ T_piece_final

        rel_change_distance = float(np.linalg.norm(T_rel_final[:3, 3] - T_rel_drop[:3, 3]))
        matrix_frobenius_norm = float(np.linalg.norm(T_rel_final - T_rel_drop))

        self.assertGreater(
            rel_change_distance,
            0.010,  # At least 10 mm change in relative vector
            f"Relative position should diverge after drop, changed by only {rel_change_distance*1000:.2f} mm"
        )
        self.assertGreater(
            matrix_frobenius_norm,
            0.010,
            f"Relative SE(3) transform should diverge after drop, got norm {matrix_frobenius_norm:.4f}"
        )

        # 8. Lateral displacement due to inherited velocity
        # The piece must have moved laterally (in XY) after release due to momentum, not merely fallen vertically
        lateral_displacement = float(np.linalg.norm(p_piece_final[:2] - p_piece_drop[:2]))
        self.assertGreater(
            lateral_displacement,
            0.005,  # At least 5 mm lateral drift
            f"Piece must have lateral displacement from inherited velocity, got {lateral_displacement*1000:.2f} mm"
        )


if __name__ == "__main__":
    unittest.main()

