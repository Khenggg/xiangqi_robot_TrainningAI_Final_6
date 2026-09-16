"""
Unit tests for piece release, dynamic drop, velocity inheritance, and out-of-bounds (Phase P3).

Verifies:
1. Normal release settles piece back into RESTING state on board.
2. Dynamic mid-flight release inherits current gripper velocity.
3. Dropping piece off the finite board triggers OUT_OF_BOUNDS state.
4. Piece-on-piece collision resolves without solver divergence or NaN poses.
"""

from pathlib import Path
import sys
import time
import unittest
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.physics.state import PiecePhysicalState
from src.simulation.physics.world import VirtualPhysicalWorld


class PieceDropTests(unittest.TestCase):
    def setUp(self):
        self.world = VirtualPhysicalWorld()
        self.gripper = self.world.gripper
        self.world.step_until_settled(max_steps=60)

    def tearDown(self):
        self.world.close()

    def test_normal_release_settles_on_board(self):
        piece = self.world.pieces["black_rook_0"]
        pos_init, _ = piece.get_pose_robot_base()

        # Position gripper and grasp
        tcp = pos_init - self.gripper.tcp_to_grasp_center
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp, [0, 0, 0, 1], time.time())
        res = self.world.try_grasp()
        self.assertTrue(res.success)

        # Lift 20mm and hold stationary
        t1 = time.time() + 0.1
        self.gripper.set_tcp_pose(tcp + [0, 0, 0.02], [0, 0, 0, 1], t1)
        self.gripper.set_tcp_pose(tcp + [0, 0, 0.02], [0, 0, 0, 1], t1 + 0.1)
        self.world.step(2)

        # Normal release
        released = self.world.release_attached_piece()
        self.assertIsNotNone(released)
        self.assertEqual(released.piece_id, "black_rook_0")

        # Step until re-settled
        steps = self.world.step_until_settled(max_steps=120)
        self.assertLess(steps, 120)
        self.assertEqual(piece.physical_state, PiecePhysicalState.RESTING)
        self.assertLess(piece.tilt_angle_deg, 1.0)

    def test_dynamic_release_inherits_motion_velocity(self):
        piece = self.world.pieces["black_rook_0"]
        pos_init, _ = piece.get_pose_robot_base()

        tcp = pos_init - self.gripper.tcp_to_grasp_center
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp, [0, 0, 0, 1], time.time())
        self.world.try_grasp()

        # Move horizontally at ~0.2 m/s: dx = 0.02m over dt = 0.1s
        t_base = 100.0
        self.gripper.set_tcp_pose(tcp + [0, 0, 0.04], [0, 0, 0, 1], t_base)
        self.gripper.set_tcp_pose(tcp + [0.02, 0, 0.04], [0, 0, 0, 1], t_base + 0.1)

        # Release mid-flight
        self.world.release_attached_piece()

        v_lin, _ = piece.get_velocity()
        # Should have positive velocity along +X
        self.assertGreater(v_lin[0], 0.10, f"Piece did not inherit forward velocity: {v_lin[0]}")

    def test_off_board_drop_triggers_out_of_bounds(self):
        piece = self.world.pieces["black_rook_0"]
        pos_init, _ = piece.get_pose_robot_base()

        tcp = pos_init - self.gripper.tcp_to_grasp_center
        self.gripper.set_gripper_state(True)
        self.gripper.set_tcp_pose(tcp, [0, 0, 0, 1], time.time())
        self.world.try_grasp()

        # Carry outside board: board_x_min is approx -0.565, move to x = -0.65 (beyond edge)
        off_board_pos = [self.world.board_x_min - 0.08, 0.0, self.world.board_surface_z + 0.08]
        self.gripper.set_tcp_pose(off_board_pos, [0, 0, 0, 1], time.time())
        self.world.step(2)

        # Force drop
        self.world.force_drop_attached_piece()
        # Retract gripper upward so it does not obstruct the falling piece
        self.gripper.set_tcp_pose(np.array(off_board_pos) + [0, 0, 0.05], [0, 0, 0, 1], time.time())

        # Step simulation as piece falls into the abyss
        for _ in range(150):
            self.world.step(1)
            if piece.physical_state == PiecePhysicalState.OUT_OF_BOUNDS:
                break

        self.assertEqual(
            piece.physical_state,
            PiecePhysicalState.OUT_OF_BOUNDS,
            f"Piece failed to reach OUT_OF_BOUNDS state: {piece.physical_state}",
        )

    def test_piece_on_piece_contact_stability(self):
        p1 = self.world.pieces["black_rook_0"]
        p2 = self.world.pieces["black_knight_0"]

        # Drop p2 from directly above p1
        pos1, _ = p1.get_pose_robot_base()
        p2.set_pose_robot_base([pos1[0], pos1[1], pos1[2] + 0.03], [0, 0, 0, 1])

        # Step simulation for contact resolution
        for _ in range(100):
            self.world.step(1)
            pos2, quat2 = p2.get_pose_robot_base()
            # Verify no NaN or infinite explosion
            self.assertTrue(all(np.isfinite(pos2)), f"Non-finite position: {pos2}")
            self.assertTrue(all(np.isfinite(quat2)), f"Non-finite quaternion: {quat2}")

        self.assertIn(
            p2.physical_state,
            (PiecePhysicalState.RESTING, PiecePhysicalState.SETTLING, PiecePhysicalState.ON_BOARD),
        )


if __name__ == "__main__":
    unittest.main()

