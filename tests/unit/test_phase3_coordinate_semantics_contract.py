#!/usr/bin/env python3
"""
Unit tests for Phase 3 - 90 deg Coordinate Semantics and Backend Contract Corrective.
Covers requirements S90-01 through S90-10, and S90-13:

  S90-01: BoardCell row/col bounds and tuple unpacking
  S90-02: cell_to_board_local(row, col) mathematical properties
  S90-03: board_local_to_cell(u, v) returns (row, col) in canonical order
  S90-04: All 90 cells exact round-trip (cell -> local -> robot -> local -> cell)
  S90-05: Asymmetric cells: (2, 7) != (7, 2) never transpose physically or logically
  S90-06: robot_xyz_to_nearest_cell returns (row, col, dist)
  S90-07: runtime.find_nearest_cell needs no manual swap and returns (row, col)
  S90-08: All 32 starting pieces preserve semantic (row, col)
  S90-09: Placement verification nearest-cell comparison uses (row, col)
  S90-10: WebSocket src/dst are [row, col] and parsed without transpose
  S90-13: Board pose yaw perturbation test: 89, 90, 91 deg coordinate transforms remain internally consistent
"""

import math
from pathlib import Path
import unittest
from unittest import mock
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

from src.simulation.placement import (
    BoardCell,
    BoardPlacementState,
    canonical_cell_to_robot_xyz_m,
    find_nearest_cell,
)
from src.simulation.physics.transforms import (
    continuous_board_coord,
    nearest_intersection_metrics,
)
from src.simulation.runtime import VirtualXiangqiSimulation, PiecePhysicalState


class TestPhase3CoordinateSemanticsContract(unittest.TestCase):
    """Test suite for 90-degree coordinate semantics normalization."""

    def test_s90_01_board_cell_bounds_and_interface(self):
        """S90-01: BoardCell(row, col) bounds [0..9] x [0..8] and tuple unpacking."""
        # Valid cells
        c00 = BoardCell(0, 0)
        self.assertEqual(c00.row, 0)
        self.assertEqual(c00.col, 0)
        self.assertEqual(c00.to_tuple(), (0, 0))

        # Iteration / unpacking
        r, c = c00
        self.assertEqual((r, c), (0, 0))

        # Indexing
        self.assertEqual(c00[0], 0)
        self.assertEqual(c00[1], 0)

        # Equality with tuple
        self.assertEqual(c00, (0, 0))

        c98 = BoardCell(9, 8)
        self.assertEqual(c98.to_tuple(), (9, 8))
        self.assertEqual(c98, (9, 8))

        # Invalid rows
        with self.assertRaises(ValueError):
            BoardCell(-1, 4)
        with self.assertRaises(ValueError):
            BoardCell(10, 4)

        # Invalid cols
        with self.assertRaises(ValueError):
            BoardCell(4, -1)
        with self.assertRaises(ValueError):
            BoardCell(4, 9)

        # Invalid indexing
        with self.assertRaises(IndexError):
            _ = c00[2]

    def test_s90_02_cell_to_board_local_math(self):
        """S90-02: cell_to_board_local(row, col) preserves canonical u (col) and v (row)."""
        state = BoardPlacementState.compute(0.0, board_yaw_deg=90.0)

        # col 0 -> u = (0 - 4) * 0.040 = -0.160 m
        # row 0 -> v = (0 - 4.5) * 0.040 = -0.180 m
        u00, v00 = state.cell_to_board_local(0, 0)
        self.assertAlmostEqual(u00, -0.160, places=6)
        self.assertAlmostEqual(v00, -0.180, places=6)

        # col 8 -> u = +0.160 m
        # row 9 -> v = +0.180 m
        u98, v98 = state.cell_to_board_local(9, 8)
        self.assertAlmostEqual(u98, +0.160, places=6)
        self.assertAlmostEqual(v98, +0.180, places=6)

        # Center area: row 4, col 4 -> u = 0.0, v = -0.020
        u44, v44 = state.cell_to_board_local(4, 4)
        self.assertAlmostEqual(u44, 0.0, places=6)
        self.assertAlmostEqual(v44, -0.020, places=6)

        # row 5, col 4 -> u = 0.0, v = +0.020
        u54, v54 = state.cell_to_board_local(5, 4)
        self.assertAlmostEqual(u54, 0.0, places=6)
        self.assertAlmostEqual(v54, +0.020, places=6)

    def test_s90_03_board_local_to_cell_returns_row_col(self):
        """S90-03: board_local_to_cell(u, v) returns (row, col) in that canonical order."""
        state = BoardPlacementState.compute(0.0, board_yaw_deg=90.0)

        # (-0.160, -0.180) -> (row=0, col=0)
        r0, c0 = state.board_local_to_cell(-0.160, -0.180)
        self.assertAlmostEqual(r0, 0.0, places=5)
        self.assertAlmostEqual(c0, 0.0, places=5)

        # (+0.160, +0.180) -> (row=9, col=8)
        r9, c8 = state.board_local_to_cell(+0.160, +0.180)
        self.assertAlmostEqual(r9, 9.0, places=5)
        self.assertAlmostEqual(c8, 8.0, places=5)

        # Asymmetric local point: u = +0.120 (col 7), v = -0.100 (row 2)
        r_asym, c_asym = state.board_local_to_cell(+0.120, -0.100)
        self.assertAlmostEqual(r_asym, 2.0, places=5)
        self.assertAlmostEqual(c_asym, 7.0, places=5)

    def test_s90_04_exact_roundtrip_all_90_cells(self):
        """S90-04: all 90 cells round-trip cell -> local -> robot -> local -> cell exactly."""
        state = BoardPlacementState.compute(15.0, board_yaw_deg=90.0)

        for r in range(10):
            for c in range(9):
                # 1. Local round trip
                u, v = state.cell_to_board_local(r, c)
                r_loc, c_loc = state.board_local_to_cell(u, v)
                self.assertAlmostEqual(r_loc, float(r), places=5)
                self.assertAlmostEqual(c_loc, float(c), places=5)

                # 2. Robot base round trip
                p_rob = state.cell_to_robot_xyz(r, c, 0.0)
                p_loc = state.robot_to_board_local(p_rob)
                self.assertAlmostEqual(p_loc[0], u, places=5)
                self.assertAlmostEqual(p_loc[1], v, places=5)
                self.assertAlmostEqual(p_loc[2], 0.0, places=5)

                # 3. Nearest cell recovery
                r_rec, c_rec, dist = state.robot_xyz_to_nearest_cell(p_rob)
                self.assertEqual(r_rec, r, f"Row mismatch at ({r}, {c})")
                self.assertEqual(c_rec, c, f"Col mismatch at ({r}, {c})")
                self.assertLess(dist, 1e-5, f"Non-zero distance residual at ({r}, {c})")

    def test_s90_05_asymmetric_cells_proof(self):
        """S90-05: asymmetric (2, 7) != (7, 2) never transpose physically or logically."""
        state = BoardPlacementState.compute(15.0, board_yaw_deg=90.0)

        p27 = state.cell_to_robot_xyz(2, 7, 0.0)
        p72 = state.cell_to_robot_xyz(7, 2, 0.0)

        # Under +90 deg orientation:
        # col 7 is near far edge (-X), col 2 is near front (-X)
        # row 2 is +Y, row 7 is -Y
        dist_between = float(np.linalg.norm(p27 - p72))
        self.assertGreater(dist_between, 0.200, f"Distance between (2,7) and (7,2) should be large, got {dist_between}m")

        # Recover nearest cell for each
        r27, c27, d27 = state.robot_xyz_to_nearest_cell(p27)
        self.assertEqual((r27, c27), (2, 7))
        self.assertLess(d27, 1e-5)

        r72, c72, d72 = state.robot_xyz_to_nearest_cell(p72)
        self.assertEqual((r72, c72), (7, 2))
        self.assertLess(d72, 1e-5)

    def test_s90_06_robot_xyz_to_nearest_cell_order(self):
        """S90-06: robot_xyz_to_nearest_cell returns (row, col, dist)."""
        state = BoardPlacementState.compute(15.0, board_yaw_deg=90.0)

        p_exact = state.cell_to_robot_xyz(3, 6, 0.0)
        p_perturbed = p_exact + np.array([0.003, -0.004, 0.0])

        ret = state.robot_xyz_to_nearest_cell(p_perturbed)
        self.assertIsInstance(ret, tuple)
        self.assertEqual(len(ret), 3)

        r_res, c_res, dist = ret
        self.assertEqual(r_res, 3)
        self.assertEqual(c_res, 6)
        self.assertAlmostEqual(dist, 0.005, places=4)

    def test_s90_07_runtime_find_nearest_cell(self):
        """S90-07: runtime.find_nearest_cell needs no manual swap and returns (row, col)."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        try:
            for test_cell in [(0, 0), (0, 8), (9, 0), (9, 8), (2, 7), (7, 2), (4, 4)]:
                xyz = sim.cell_to_robot_xyz_m(test_cell[0], test_cell[1])
                res = sim.find_nearest_cell(xyz)
                self.assertEqual(res, test_cell, f"Mismatch for cell {test_cell}, got {res}")
                self.assertEqual(res[0], test_cell[0], "First element must be row")
                self.assertEqual(res[1], test_cell[1], "Second element must be col")
        finally:
            sim.stop()

    def test_s90_08_all_32_starting_pieces_preserve_semantic_row_col(self):
        """S90-08: all 32 starting pieces preserve semantic (row, col) in physics world."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        try:
            layout_pieces = sim.world.layout_cfg.get("pieces", [])
            self.assertEqual(len(layout_pieces), 32)

            for p_info in layout_pieces:
                pid = p_info["id"]
                expected_row = int(p_info["row"])
                expected_col = int(p_info["col"])

                p_body = sim.world.pieces.get(pid)
                self.assertIsNotNone(p_body, f"Piece {pid} not found in physics world")

                r_p, c_p, dist = p_body.get_nearest_intersection()
                self.assertEqual(r_p, expected_row, f"Row mismatch for {pid}: expected {expected_row}, got {r_p}")
                self.assertEqual(c_p, expected_col, f"Col mismatch for {pid}: expected {expected_col}, got {c_p}")
                self.assertLess(dist, 0.010, f"Distance too large for settled piece {pid}: {dist}m")
        finally:
            sim.stop()

    def test_s90_09_placement_verification_uses_row_col(self):
        """S90-09: placement verification nearest-cell comparison uses (row, col)."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        try:
            # Check black_cannon_0 at initial cell (2, 1)
            p_obj = sim.world.pieces["black_cannon_0"]
            r_p, c_p, d_p = p_obj.get_nearest_intersection()
            target_cell_tuple = (2, 1)

            # Verification expression without any swap:
            cell_match = (r_p, c_p) == target_cell_tuple and d_p < 0.025
            self.assertTrue(cell_match)

            # Must NOT match swapped tuple
            swapped_tuple = (1, 2)
            self.assertFalse((r_p, c_p) == swapped_tuple)
        finally:
            sim.stop()

    def test_s90_10_websocket_src_dst_row_col_contract(self):
        """S90-10: WebSocket src/dst commands are [row, col] and parsed without transpose."""
        sim = VirtualXiangqiSimulation()
        sim.start()
        try:
            with mock.patch.object(sim, "_run_trajectory_async") as mock_traj:
                # Dispatch EXECUTE_3STAGE with asymmetric cells
                cmd = {
                    "command": "EXECUTE_3STAGE",
                    "src": [2, 7],
                    "dst": [7, 2],
                    "placement_version": 1,
                    "grasp_piece": False,
                }
                sim._handle_client_command(cmd)

                mock_traj.assert_called_once_with((2, 7), (7, 2), 1, False)
        finally:
            sim.stop()

    def test_s90_13_yaw_perturbation_transforms_remain_consistent(self):
        """
        S90-13: Board pose yaw perturbation test: 89, 90, 91 deg.
        Verifies coordinate transform remains internally consistent across small yaw perturbations,
        proving the architecture is based on true matrix/quaternion rotation, not hardcoded swaps.
        """
        for yaw in [89.0, 90.0, 91.0]:
            state = BoardPlacementState.compute(15.0, board_yaw_deg=yaw)

            # Check orthonormal properties of R_robot_from_board
            R = state.R_robot_from_board
            np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-6)
            self.assertAlmostEqual(float(np.linalg.det(R)), 1.0, places=6)

            # Check all 90 cells round-trip accurately under perturbed yaw
            for r in range(10):
                for c in range(9):
                    p_rob = state.cell_to_robot_xyz(r, c, 0.0)
                    r_rec, c_rec, dist = state.robot_xyz_to_nearest_cell(p_rob)
                    self.assertEqual(r_rec, r, f"Yaw {yaw} failed at row {r}, col {c}")
                    self.assertEqual(c_rec, c, f"Yaw {yaw} failed at row {r}, col {c}")
                    self.assertLess(dist, 1e-4, f"Yaw {yaw} distance residual at ({r}, {c})")


if __name__ == "__main__":
    unittest.main()
