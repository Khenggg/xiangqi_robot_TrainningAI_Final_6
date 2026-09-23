"""
Unit tests for Phase 2: Vision Runtime Integration and Phase 1 Carryover Closure.

Covers:
1. Carryover A1: Gripper state consistency on driver success/failure
2. Carryover A2: Flange pose provenance (CONTROLLER, DERIVED, MOCK, UNAVAILABLE)
3. Carryover A3: Safe AI execution without manual fallback in physical mode
4. Part B: MoveObservation contract & semantic board observation
5. Part B: SnapshotDetector CChess tiebreaker and recovery fallback
6. Part B: Coordinate boundary preservation (Vision -> Board -> Robot) & Canonical Geometry
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from src.hardware.backends.physical_fr3 import PhysicalFR3Backend
from src.simulation.virtual_fr3_backend import VirtualFR3Backend
from src.core.ai_execution import execute_ai_move
from src.core.game_state import GameState
from src.core import xiangqi
from src.vision.move_observation import MoveObservation, derive_move_observation
from src.vision.snapshot_detector import SnapshotDetector
from src.vision.visual_pick_estimator import VisualPickEstimator, GridTarget
from src.domain.geometry import (
    CANONICAL_CELL_SPACING_MM,
    CANONICAL_GRID_WIDTH_MM,
    CANONICAL_GRID_LENGTH_MM,
    get_physical_geometry,
)


class TestGripperStateConsistency(unittest.TestCase):
    """Carryover A1: Ensure _gripper_closed only mutates when hardware succeeds."""

    def setUp(self):
        self.mock_driver = MagicMock()
        self.backend = PhysicalFR3Backend(dry_run=False, gripper_driver=self.mock_driver)

    def test_initial_state_not_closed(self):
        self.assertFalse(self.backend._gripper_closed)

    def test_close_success_updates_state(self):
        self.mock_driver.close.return_value = True
        ok = self.backend.set_gripper(True)
        self.assertTrue(ok)
        self.assertTrue(self.backend._gripper_closed)

    def test_close_failure_preserves_previous_state(self):
        # Set state initially to False (OPEN)
        self.backend._gripper_closed = False
        self.mock_driver.close.return_value = False

        ok = self.backend.set_gripper(True)
        self.assertFalse(ok)
        # MUST NOT become True on failure
        self.assertFalse(self.backend._gripper_closed)

    def test_open_failure_preserves_previous_state(self):
        # Set state initially to True (CLOSED)
        self.backend._gripper_closed = True
        self.mock_driver.open.return_value = False

        ok = self.backend.set_gripper(False)
        self.assertFalse(ok)
        # MUST NOT become False on failure
        self.assertTrue(self.backend._gripper_closed)

    def test_open_success_updates_state(self):
        self.backend._gripper_closed = True
        self.mock_driver.open.return_value = True

        ok = self.backend.set_gripper(False)
        self.assertTrue(ok)
        self.assertFalse(self.backend._gripper_closed)

    def test_exception_preserves_state(self):
        self.backend._gripper_closed = False
        self.mock_driver.close.side_effect = RuntimeError("Gripper bus timeout")

        ok = self.backend.set_gripper(True)
        self.assertFalse(ok)
        self.assertFalse(self.backend._gripper_closed)


class TestFlangePoseProvenance(unittest.TestCase):
    """Carryover A2: RobotStateSnapshot exposes accurate flange_pose_source."""

    def test_dry_run_source_is_mock(self):
        backend = PhysicalFR3Backend(dry_run=True)
        snap = backend.get_state_snapshot()
        self.assertEqual(snap.flange_pose_source, "MOCK")

    def test_controller_success_source_is_controller(self):
        mock_robot = MagicMock()
        mock_robot.GetActualJointPosDegree.return_value = (0, [0.0] * 6)
        mock_robot.GetActualTCPPose.return_value = (0, [0.4, 0.0, 0.2, 180.0, 0.0, 0.0])
        mock_robot.GetActualToolFlangePose.return_value = (0, [0.4, 0.0, 0.35, 180.0, 0.0, 0.0])

        backend = PhysicalFR3Backend(dry_run=False)
        backend._connected = True
        backend._rpc = mock_robot

        snap = backend.get_state_snapshot()
        self.assertEqual(snap.flange_pose_source, "CONTROLLER")
        self.assertTrue(backend._flange_authoritative)

    def test_controller_failure_fallback_derived(self):
        mock_robot = MagicMock()
        mock_robot.GetActualJointPosDegree.return_value = (0, [0.0] * 6)
        mock_robot.GetActualTCPPose.return_value = (0, [0.4, 0.0, 0.2, 180.0, 0.0, 0.0])
        mock_robot.GetActualToolFlangePose.return_value = (-1, [])  # Controller RPC failed

        backend = PhysicalFR3Backend(dry_run=False)
        backend._connected = True
        backend._rpc = mock_robot

        snap = backend.get_state_snapshot()
        self.assertEqual(snap.flange_pose_source, "DERIVED")
        self.assertFalse(backend._flange_authoritative)

    def test_unavailable_when_no_data(self):
        mock_robot = MagicMock()
        mock_robot.GetActualJointPosDegree.return_value = (-1, [])
        mock_robot.GetActualTCPPose.return_value = (-1, [])
        mock_robot.GetActualToolFlangePose.return_value = (-1, [])

        backend = PhysicalFR3Backend(dry_run=False)
        backend._connected = True
        backend._rpc = mock_robot

        snap = backend.get_state_snapshot()
        self.assertEqual(snap.flange_pose_source, "UNAVAILABLE")
        self.assertFalse(backend._flange_authoritative)

    def test_virtual_backend_source_is_derived(self):
        backend = VirtualFR3Backend()
        snap = backend.get_state_snapshot()
        self.assertEqual(snap.flange_pose_source, "DERIVED")


class TestSafeAIExecution(unittest.TestCase):
    """Carryover A3: Physical robot-not-ready must NEVER commit logical GameState."""

    def setUp(self):
        self.state = GameState()
        self.state.turn = "b"  # AI's turn
        self.mock_hw = MagicMock()
        # Normal starting move for black cannon: (1, 2) -> (4, 2)
        self.test_move = ((1, 2), (4, 2))

    def test_physical_not_ready_rejects_commit(self):
        self.mock_hw.is_robot_ready = False
        initial_board = [row[:] for row in self.state.board]

        result = execute_ai_move(
            state=self.state,
            hw=self.mock_hw,
            best_move=self.test_move,
            dry_run=False,
            visual_pick_enabled=False,
        )

        self.assertFalse(result)
        # GameState must NOT have changed
        self.assertEqual(self.state.board, initial_board)
        self.assertEqual(self.state.turn, "b")
        # Hardware motion must NOT have been called
        self.mock_hw.move_piece.assert_not_called()

    def test_physical_ready_motion_failure_rejects_commit(self):
        self.mock_hw.is_robot_ready = True
        self.mock_hw.move_piece.return_value = False
        initial_board = [row[:] for row in self.state.board]

        result = execute_ai_move(
            state=self.state,
            hw=self.mock_hw,
            best_move=self.test_move,
            dry_run=False,
            visual_pick_enabled=False,
        )

        self.assertFalse(result)
        # GameState must NOT have changed
        self.assertEqual(self.state.board, initial_board)
        self.assertEqual(self.state.turn, "b")

    def test_physical_ready_motion_success_commits_state(self):
        self.mock_hw.is_robot_ready = True
        self.mock_hw.move_piece.return_value = True

        result = execute_ai_move(
            state=self.state,
            hw=self.mock_hw,
            best_move=self.test_move,
            dry_run=False,
            visual_pick_enabled=False,
        )

        self.assertTrue(result)
        # Move committed: destination has black piece, source is empty
        self.assertEqual(self.state.board[2][4], "b_C")
        self.assertEqual(self.state.board[2][1], ".")
        # Turn switched to red
        self.assertEqual(self.state.turn, "r")


class TestMoveObservationContract(unittest.TestCase):
    """Part B: MoveObservation contract and semantic board derivation."""

    def setUp(self):
        self.t1_board = xiangqi.get_board()

    def test_valid_normal_move(self):
        # Red cannon moves (1, 7) -> (4, 7)
        t2_board = [row[:] for row in self.t1_board]
        t2_board[7][4] = t2_board[7][1]
        t2_board[7][1] = "."

        obs = derive_move_observation(self.t1_board, t2_board, player_color="r")
        self.assertTrue(obs.success)
        self.assertEqual(obs.src, (1, 7))
        self.assertEqual(obs.dst, (4, 7))
        self.assertEqual(obs.piece, "r_C")
        self.assertFalse(obs.is_capture)
        self.assertIsNone(obs.captured_piece)
        self.assertIsNone(obs.error)

    def test_valid_capture_move(self):
        # Red chariot at (0, 9) captures black chariot at (0, 0)
        # Kings placed non-facing in palace: b_K at (3, 0), r_K at (4, 9)
        t1_board = [["." for _ in range(9)] for _ in range(10)]
        t1_board[9][4] = "r_K"
        t1_board[0][3] = "b_K"
        t1_board[9][0] = "r_R"
        t1_board[0][0] = "b_R"

        t2_board = [row[:] for row in t1_board]
        t2_board[0][0] = "r_R"
        t2_board[9][0] = "."

        obs = derive_move_observation(t1_board, t2_board, player_color="r")
        self.assertTrue(obs.success)
        self.assertEqual(obs.src, (0, 9))
        self.assertEqual(obs.dst, (0, 0))
        self.assertEqual(obs.piece, "r_R")
        self.assertTrue(obs.is_capture)
        self.assertEqual(obs.captured_piece, "b_R")

    def test_multi_change_rejection(self):
        # 2 red pieces disappear at the same time
        t2_board = [row[:] for row in self.t1_board]
        t2_board[7][1] = "."
        t2_board[7][7] = "."

        obs = derive_move_observation(self.t1_board, t2_board, player_color="r")
        self.assertFalse(obs.success)
        self.assertTrue(obs.is_ambiguous)
        self.assertIn("Multiple piece changes", obs.error)

    def test_illegal_move_rejection(self):
        # Red cannon moves illegally (diagonal step to empty square (2, 8))
        t2_board = [row[:] for row in self.t1_board]
        t2_board[8][2] = t2_board[7][1]
        t2_board[7][1] = "."

        obs = derive_move_observation(self.t1_board, t2_board, player_color="r")
        self.assertFalse(obs.success)
        self.assertIn("Illegal move", obs.error)


class TestSnapshotDetectorCChessIntegration(unittest.TestCase):
    """Part B: SnapshotDetector CChess ONNX tiebreaker and recovery."""

    def setUp(self):
        self.detector = SnapshotDetector(perspective_path="nonexistent.npy", class_id_map={})
        self.board = xiangqi.get_board()
        self.t1_occ = [[(self.board[r][c] != ".") for c in range(9)] for r in range(10)]

    def test_cchess_tiebreaker_resolves_multiple_valid_moves(self):
        # Red cannon at (1, 7) disappeared
        t1_occ = [row[:] for row in self.t1_occ]
        t2_occ = [row[:] for row in t1_occ]
        t2_occ[7][1] = False
        # Appeared at both (4, 7) and (1, 4) — both valid moves for a cannon
        t2_occ[7][4] = True
        t2_occ[4][1] = True

        # Provide CChess result where (4, 7) has "r_C"
        rec_board = [["." for _ in range(9)] for _ in range(10)]
        rec_board[7][4] = "r_C"
        cchess_result = {"success": True, "board": rec_board}

        src, dst, piece = self.detector._compare_snapshots(
            t1_occ=t1_occ,
            t2_occ=t2_occ,
            board=self.board,
            frame=None,
            cchess_result=cchess_result,
        )
        self.assertEqual(src, (1, 7))
        self.assertEqual(dst, (4, 7))
        self.assertEqual(piece, "r_C")

    def test_cchess_recovery_when_occupancy_misses_disappeared(self):
        # Occupancy grid detects no change (e.g. glare/lighting issue)
        t1_occ = [row[:] for row in self.t1_occ]
        t2_occ = [row[:] for row in self.t1_occ]

        # But CChess model detected red soldier moved from (4, 6) to (4, 5)
        rec_board = [row[:] for row in self.board]
        rec_board[6][4] = "."
        rec_board[5][4] = "r_P"
        cchess_result = {"success": True, "board": rec_board}

        src, dst, piece = self.detector._compare_snapshots(
            t1_occ=t1_occ,
            t2_occ=t2_occ,
            board=self.board,
            frame=None,
            cchess_result=cchess_result,
        )
        self.assertEqual(src, (4, 6))
        self.assertEqual(dst, (4, 5))
        self.assertEqual(piece, "r_P")


class TestCoordinateBoundariesAndCanonicalGeometry(unittest.TestCase):
    """Part B: Coordinate Boundaries & Strict Canonical Board Geometry."""

    def test_canonical_board_geometry_constants(self):
        geom = get_physical_geometry()
        # 40 mm grid spacing
        self.assertAlmostEqual(CANONICAL_CELL_SPACING_MM, 40.0, places=2)
        # 320 x 360 mm active grid
        self.assertAlmostEqual(CANONICAL_GRID_WIDTH_MM, 320.0, places=2)
        self.assertAlmostEqual(CANONICAL_GRID_LENGTH_MM, 360.0, places=2)
        # 367 x 410 mm board dimensions
        self.assertAlmostEqual(geom.outer_width_mm, 367.0, places=2)
        self.assertAlmostEqual(geom.outer_length_mm, 410.0, places=2)

    def test_visual_pick_estimator_outputs_board_space_only(self):
        with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as f:
            np.save(f, np.eye(3, dtype=np.float32))
            tmp_path = f.name
        try:
            estimator = VisualPickEstimator(perspective_path=tmp_path)
            # Target (3, 5): box center around x=3, foot around y=5
            detections = [("r_C", 0.9, (2.8, 4.0, 3.2, 5.0))]
            target = estimator.estimate_pick_target(detections, expected_col=3, expected_row=5)

            self.assertIsNotNone(target)
            self.assertIsInstance(target, GridTarget)
            # Must output continuous grid row and col
            self.assertIsInstance(target.col, float)
            self.assertIsInstance(target.row, float)
            # Must not contain robot XYZ coordinates
            self.assertFalse(hasattr(target, "robot_x"))
            self.assertFalse(hasattr(target, "robot_y"))
            self.assertFalse(hasattr(target, "robot_z"))
            # Range should remain near the logical cell (3, 5)
            self.assertTrue(2.0 <= target.col <= 4.0)
            self.assertTrue(4.0 <= target.row <= 6.0)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
