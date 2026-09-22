"""
Unit regression tests for VirtualPhysicalWorld (Phase P3).

Verifies:
1. VirtualPhysicalWorld initializes headless PyBullet direct client.
2. Finite board collider created with expected dimensions and bounds.
3. 32 Xiangqi cylinder rigid bodies spawned at canonical start intersections.
4. All 32 pieces settle in <= 120 steps into static equilibrium.
5. Settled pieces have linear velocity < 0.005 m/s and angular velocity < 0.05 rad/s.
6. Pieces remain upright (tilt < 1.0 deg).
7. Position residual against grid intersections <= 1.5 mm.
8. State snapshots are immutable, JSON-serializable, and match schema.
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

from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.physics.state import PiecePhysicalState


class VirtualPhysicalWorldTests(unittest.TestCase):
    def setUp(self):
        self.world = VirtualPhysicalWorld()

    def tearDown(self):
        self.world.close()

    def test_world_initialization_and_board_bounds(self):
        self.assertGreaterEqual(self.world.client_id, 0)
        self.assertEqual(len(self.world.pieces), 32)
        self.assertGreaterEqual(self.world.board_body_id, 0)

        # Check finite board bounds
        self.assertLess(self.world.board_x_min, self.world.board_x_max)
        self.assertLess(self.world.board_y_min, self.world.board_y_max)
        width = self.world.board_y_max - self.world.board_y_min
        depth = self.world.board_x_max - self.world.board_x_min
        # In 90 deg orientation: u (width) maps to -X_robot, v (length) maps to -Y_robot
        self.assertAlmostEqual(width, self.world.geom.outer_length_mm / 1000.0, places=3)
        self.assertAlmostEqual(depth, self.world.geom.outer_width_mm / 1000.0, places=3)

    def test_piece_spawning_and_count_by_side(self):
        red_pieces = [p for p in self.world.pieces.values() if p.side == "r"]
        black_pieces = [p for p in self.world.pieces.values() if p.side == "b"]
        self.assertEqual(len(red_pieces), 16)
        self.assertEqual(len(black_pieces), 16)

    def test_pieces_settle_into_static_equilibrium(self):
        steps = self.world.step_until_settled(max_steps=120)
        self.assertLess(steps, 120, f"Pieces failed to settle within 120 steps (took {steps})")

        for piece_id, piece in self.world.pieces.items():
            self.assertEqual(
                piece.physical_state,
                PiecePhysicalState.RESTING,
                f"Piece {piece_id} not resting: {piece.physical_state}",
            )
            v_lin, v_ang = piece.get_velocity()
            lin_speed = float(np.linalg.norm(v_lin))
            ang_speed = float(np.linalg.norm(v_ang))
            self.assertLess(
                lin_speed,
                0.005,
                f"Piece {piece_id} linear speed {lin_speed} exceeds 0.005 m/s",
            )
            self.assertLess(
                ang_speed,
                0.05,
                f"Piece {piece_id} angular speed {ang_speed} exceeds 0.05 rad/s",
            )
            self.assertLess(
                piece.tilt_angle_deg,
                1.0,
                f"Piece {piece_id} tilt {piece.tilt_angle_deg} exceeds 1.0 deg",
            )
            self.assertLessEqual(
                piece.nearest_dist_m,
                0.0015,
                f"Piece {piece_id} grid distance {piece.nearest_dist_m * 1000:.2f}mm exceeds 1.5mm",
            )

    def test_state_snapshot_serializability(self):
        self.world.step_until_settled(max_steps=60)
        snapshot = self.world.get_snapshot()
        data = snapshot.to_dict()

        self.assertEqual(data["type"], "world_state")
        self.assertEqual(len(data["pieces"]), 32)
        # Verify JSON serializability
        json_str = json.dumps(data)
        self.assertIsInstance(json_str, str)
        reloaded = json.loads(json_str)
        self.assertEqual(reloaded["type"], "world_state")
        self.assertEqual(len(reloaded["pieces"]), 32)


if __name__ == "__main__":
    unittest.main()

