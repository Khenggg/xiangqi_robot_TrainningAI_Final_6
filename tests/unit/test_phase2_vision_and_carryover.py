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
from pathlib import Path
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
from src.vision.cchess_recognizer import (
    validate_board_sanity,
    check_recognition_quality,
    validate_recognition_result,
    RecognitionQuality,
)
from src.hardware.hardware_manager import HardwareManager
from src.ui.input_handler import InputHandler
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

    def test_controller_failure_fallback_unavailable(self):
        mock_robot = MagicMock()
        mock_robot.GetActualJointPosDegree.return_value = (0, [0.0] * 6)
        mock_robot.GetActualTCPPose.return_value = (0, [0.4, 0.0, 0.2, 180.0, 0.0, 0.0])
        mock_robot.GetActualToolFlangePose.return_value = (-1, [])  # Controller RPC failed

        backend = PhysicalFR3Backend(dry_run=False)
        backend._connected = True
        backend._rpc = mock_robot

        snap = backend.get_state_snapshot()
        self.assertEqual(snap.flange_pose_source, "UNAVAILABLE")
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


class MockCamConfig:
    DRY_RUN = False
    ROBOT_BACKEND = "VIRTUAL"
    VIDEO_SOURCE = 0
    VISUAL_PICK_ENABLED = False
    ROBOT_IP = "192.168.58.2"
    BOARD_CALIBRATION_MODE = "SIMULATION"


class TestAmbiguityAndManhattanRemoval(unittest.TestCase):
    """P0: Removal of Manhattan ambiguity guessing and strict fail-closed."""

    def setUp(self):
        self.detector = SnapshotDetector(perspective_path="nonexistent.npy", class_id_map={})
        self.board = [
            ["b_R", "b_N", "b_E", "b_A", "b_K", "b_A", "b_E", "b_N", "b_R"],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            [".", "b_C", ".", ".", ".", ".", ".", "b_C", "."],
            ["b_P", ".", "b_P", ".", "b_P", ".", "b_P", ".", "b_P"],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            ["r_P", ".", "r_P", ".", "r_P", ".", "r_P", ".", "r_P"],
            [".", "r_C", ".", ".", ".", ".", ".", "r_C", "."],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            ["r_R", "r_N", "r_E", "r_A", "r_K", "r_A", "r_E", "r_N", "r_R"],
        ]
        self.t1_occ = [[cell != "." for cell in row] for row in self.board]

    def test_unresolved_multiple_candidates_fail_closed_not_manhattan_guessed(self):
        """
        Two legal candidates: red cannon at (1, 7) could move to (1, 6) or (1, 5).
        Both are legal cannon moves on an empty column.
        Distance to (1, 6) is 1; distance to (1, 5) is 2.
        Under previous Manhattan fallback, (1, 6) was silently chosen.
        Now it MUST fail closed: return (None, None, None) and set last_detection_ambiguous = True.
        """
        t1_occ = [row[:] for row in self.t1_occ]
        t2_occ = [row[:] for row in self.t1_occ]
        # (1, 7) disappeared
        t2_occ[7][1] = False
        # (1, 6) and (1, 5) appeared
        t2_occ[6][1] = True
        t2_occ[5][1] = True

        src, dst, piece = self.detector._compare_snapshots(
            t1_occ=t1_occ,
            t2_occ=t2_occ,
            board=self.board,
            frame=None,
            cchess_result=None,
        )
        self.assertIsNone(src)
        self.assertIsNone(dst)
        self.assertIsNone(piece)
        self.assertTrue(self.detector.last_detection_ambiguous)

    def test_detect_move_observation_returns_ambiguous_on_unresolved_candidates(self):
        """detect_move_observation must return MoveObservation(success=False, is_ambiguous=True)."""
        t1_occ = [row[:] for row in self.t1_occ]
        t2_occ = [row[:] for row in self.t1_occ]
        t2_occ[7][1] = False
        t2_occ[6][1] = True
        t2_occ[5][1] = True

        self.detector._baseline_occ = t1_occ
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        detections = []

        obs = self.detector.detect_move_observation(
            frame=frame,
            detections=detections,
            board=self.board,
            t2_occ=t2_occ,
            cchess_result=None,
        )
        self.assertFalse(obs.success)
        self.assertTrue(obs.is_ambiguous)
        self.assertIn("Mơ hồ", obs.error)


class TestCChessQualityGate(unittest.TestCase):
    """Requirement 6: CChess full-board quality gate and board sanity checks."""

    def setUp(self):
        self.standard_board = [
            ["b_R", "b_N", "b_E", "b_A", "b_K", "b_A", "b_E", "b_N", "b_R"],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            [".", "b_C", ".", ".", ".", ".", ".", "b_C", "."],
            ["b_P", ".", "b_P", ".", "b_P", ".", "b_P", ".", "b_P"],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            ["r_P", ".", "r_P", ".", "r_P", ".", "r_P", ".", "r_P"],
            [".", "r_C", ".", ".", ".", ".", ".", "r_C", "."],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            ["r_R", "r_N", "r_E", "r_A", "r_K", "r_A", "r_E", "r_N", "r_R"],
        ]

    def test_validate_board_sanity_valid_board(self):
        is_sane, _ = validate_board_sanity(self.standard_board)
        self.assertTrue(is_sane)

    def test_validate_board_sanity_missing_king(self):
        bad_board = [row[:] for row in self.standard_board]
        bad_board[9][4] = "."  # Remove red king
        is_sane, _ = validate_board_sanity(bad_board)
        self.assertFalse(is_sane)

        bad_board2 = [row[:] for row in self.standard_board]
        bad_board2[0][4] = "."  # Remove black king
        is_sane2, _ = validate_board_sanity(bad_board2)
        self.assertFalse(is_sane2)

    def test_validate_board_sanity_king_outside_palace(self):
        # Red king in row 5 (outside rows 7-9)
        bad_board = [row[:] for row in self.standard_board]
        bad_board[9][4] = "."
        bad_board[5][4] = "r_K"
        is_sane, _ = validate_board_sanity(bad_board)
        self.assertFalse(is_sane)

        # Black king in col 1 (outside cols 3-5)
        bad_board2 = [row[:] for row in self.standard_board]
        bad_board2[0][4] = "."
        bad_board2[0][1] = "b_K"
        is_sane2, _ = validate_board_sanity(bad_board2)
        self.assertFalse(is_sane2)

    def test_validate_board_sanity_excessive_pieces(self):
        bad_board = [row[:] for row in self.standard_board]
        bad_board[4][4] = "r_P"  # 17th red piece
        is_sane, _ = validate_board_sanity(bad_board)
        self.assertFalse(is_sane)

    def test_check_recognition_quality_corners_and_sanity(self):
        # CChess ordering: A0 (top-left), A8 (top-right), J0 (bottom-left), J8 (bottom-right)
        corners = np.array([[50.0, 50.0], [550.0, 50.0], [50.0, 550.0], [550.0, 550.0]], dtype=np.float32)
        corner_scores = np.array([0.25, 0.30, 0.28, 0.22], dtype=np.float32)
        result = {
            "success": True,
            "corners": corners,
            "corner_scores": corner_scores,
            "board": self.standard_board,
        }
        quality = check_recognition_quality(result, img_shape=(600, 600))
        self.assertTrue(quality.is_valid)

        # Low SimCC corner score
        result_low_conf = dict(result)
        result_low_conf["corner_scores"] = np.array([0.02, 0.05, 0.04, 0.03], dtype=np.float32)
        q_low = check_recognition_quality(result_low_conf, img_shape=(600, 600))
        self.assertFalse(q_low.is_valid)
        self.assertIn("góc bàn cờ quá thấp", q_low.error)

        # Self-intersecting / bowtie corners
        result_inverted = dict(result)
        result_inverted["corners"] = np.array([[50.0, 50.0], [550.0, 550.0], [50.0, 550.0], [550.0, 50.0]], dtype=np.float32)
        q_inv = check_recognition_quality(result_inverted, img_shape=(600, 600))
        self.assertFalse(q_inv.is_valid)
        self.assertIn("tứ giác lồi", q_inv.error)

        # Malformed board rejected
        result_bad_board = dict(result)
        bad_b = [row[:] for row in self.standard_board]
        bad_b[9][4] = "."
        result_bad_board["board"] = bad_b
        q_board = check_recognition_quality(result_bad_board, img_shape=(600, 600))
        self.assertFalse(q_board.is_valid)
        self.assertIn("Tướng Đỏ", q_board.error)


class TestMoveObservationAndCChessAuthority(unittest.TestCase):
    """Requirements 4 & 5: CChess authoritative MoveObservation derivation & validation."""

    def setUp(self):
        self.before_board = [
            ["b_R", "b_N", "b_E", "b_A", "b_K", "b_A", "b_E", "b_N", "b_R"],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            [".", "b_C", ".", ".", ".", ".", ".", "b_C", "."],
            ["b_P", ".", "b_P", ".", "b_P", ".", "b_P", ".", "b_P"],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            ["r_P", ".", "r_P", ".", "r_P", ".", "r_P", ".", "r_P"],
            [".", "r_C", ".", ".", ".", ".", ".", "r_C", "."],
            [".", ".", ".", ".", ".", ".", ".", ".", "."],
            ["r_R", "r_N", "r_E", "r_A", "r_K", "r_A", "r_E", "r_N", "r_R"],
        ]

    def test_derive_move_observation_normal_move(self):
        after_board = [row[:] for row in self.before_board]
        after_board[7][1] = "."
        after_board[7][4] = "r_C"  # Cannon (1, 7) -> (4, 7)

        obs = derive_move_observation(self.before_board, after_board, player_color="r")
        self.assertTrue(obs.success)
        self.assertEqual(obs.src, (1, 7))
        self.assertEqual(obs.dst, (4, 7))
        self.assertEqual(obs.piece, "r_C")
        self.assertFalse(obs.is_capture)
        self.assertIsNone(obs.captured_piece)

    def test_derive_move_observation_capture(self):
        # Place red pawn at (1, 5) so exactly one screen piece exists between (1, 7) and (1, 2)
        before_board = [row[:] for row in self.before_board]
        before_board[6][2] = "."
        before_board[5][1] = "r_P"

        after_board = [row[:] for row in before_board]
        after_board[7][1] = "."
        after_board[2][1] = "r_C"  # Cannon at (1, 7) captures black cannon at (1, 2)

        obs = derive_move_observation(before_board, after_board, player_color="r")
        self.assertTrue(obs.success)
        self.assertEqual(obs.src, (1, 7))
        self.assertEqual(obs.dst, (1, 2))
        self.assertEqual(obs.piece, "r_C")
        self.assertTrue(obs.is_capture)
        self.assertEqual(obs.captured_piece, "b_C")

    def test_derive_move_observation_illegal_move_rejected(self):
        after_board = [row[:] for row in self.before_board]
        # Red elephant crosses river (illegal in Xiangqi)
        after_board[9][2] = "."
        after_board[4][2] = "r_E"

        obs = derive_move_observation(self.before_board, after_board, player_color="r")
        self.assertFalse(obs.success)
        self.assertFalse(obs.is_ambiguous)
        self.assertIn("Illegal move", obs.error)

    def test_derive_move_observation_multiple_changes_ambiguous(self):
        after_board = [row[:] for row in self.before_board]
        after_board[7][1] = "."
        after_board[7][4] = "r_C"
        after_board[6][0] = "."
        after_board[5][0] = "r_P"

        obs = derive_move_observation(self.before_board, after_board, player_color="r")
        self.assertFalse(obs.success)
        self.assertTrue(obs.is_ambiguous)
        self.assertIn("Multiple", obs.error)

    def test_derive_move_observation_malformed_board_rejected(self):
        after_board = [row[:] for row in self.before_board]
        after_board[9][4] = "."  # King missing

        obs = derive_move_observation(self.before_board, after_board, player_color="r")
        self.assertFalse(obs.success)
        self.assertIn("Malformed board", obs.error)


class TestCameraCalibrationFailClosed(unittest.TestCase):
    """Requirement 7: Auto-calibration must fail closed and never silently reuse stale matrix."""

    @patch("cv2.VideoCapture")
    @patch("src.vision.auto_calibrate.run_calibration_flow")
    def test_calibration_cancelled_fails_closed(self, mock_calib_flow, mock_vid_cap):
        mock_cap_instance = MagicMock()
        mock_cap_instance.isOpened.return_value = True
        mock_vid_cap.return_value = mock_cap_instance

        # User cancels calibration -> run_calibration_flow returns None
        mock_calib_flow.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg = MockCamConfig()
            hw = HardwareManager(config=cfg, project_dir=tmp_dir)

            stale_perspective = Path(tmp_dir) / "perspective.npy"
            np.save(stale_perspective, np.eye(3, dtype=np.float32))

            with self.assertRaises(SystemExit) as cm:
                hw._init_camera()
            self.assertEqual(cm.exception.code, 1)
            self.assertFalse(hw.camera_ready)
            self.assertIsNone(hw.cap)

    @patch("cv2.VideoCapture")
    @patch("src.vision.auto_calibrate.run_calibration_flow")
    def test_calibration_success_authorizes_startup(self, mock_calib_flow, mock_vid_cap):
        mock_cap_instance = MagicMock()
        mock_cap_instance.isOpened.return_value = True
        mock_vid_cap.return_value = mock_cap_instance

        valid_matrix = np.eye(3, dtype=np.float32)
        mock_calib_flow.return_value = valid_matrix

        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg = MockCamConfig()
            hw = HardwareManager(config=cfg, project_dir=tmp_dir)
            hw.model = None

            perspective = Path(tmp_dir) / "perspective.npy"
            np.save(perspective, valid_matrix)

            hw._init_camera()
            self.assertTrue(hw.camera_ready)
            self.assertIsNotNone(hw.cap)


class TestProductionSpaceKeyFlow(unittest.TestCase):
    """Requirements 4, 5, 10, 11: Production SPACE path with authoritative MoveObservation and fail-safe fusion."""

    def setUp(self):
        self.state = GameState()
        self.hw = MagicMock()
        self.input_handler = InputHandler(self.state, self.hw)

        self.mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        self.hw.cam_monitor.get_fresh_snapshot.return_value = (self.mock_frame, [])
        self.hw.yolo_detector.has_baseline.return_value = True

    def test_space_key_commits_valid_cchess_observation(self):
        rec_board = [row[:] for row in self.state.board]
        rec_board[7][1] = "."
        rec_board[7][4] = "r_C"  # Cannon (1, 7) -> (4, 7)

        self.hw.recognize_board_state.return_value = {
            "success": True,
            "quality_ok": True,
            "board": rec_board,
            "confidence": np.ones((10, 9), dtype=np.float32),
        }
        self.hw.yolo_detector.detect_move_observation.return_value = MoveObservation(
            success=True, src=(1, 7), dst=(4, 7), piece="r_C"
        )

        ok = self.input_handler._handle_space_key()
        self.assertTrue(ok)
        self.assertEqual(self.state.board[7][4], "r_C")
        self.assertEqual(self.state.board[7][1], ".")

    def test_space_key_rejects_ambiguous_cchess_observation(self):
        rec_board = [row[:] for row in self.state.board]
        rec_board[7][1] = "."
        rec_board[7][4] = "r_C"
        rec_board[6][0] = "."
        rec_board[5][0] = "r_P"

        self.hw.recognize_board_state.return_value = {
            "success": True,
            "quality_ok": True,
            "board": rec_board,
        }

        ok = self.input_handler._handle_space_key()
        self.assertFalse(ok)
        self.assertTrue(self.state.manual_override_active)
        self.assertEqual(self.state.board[7][1], "r_C")

    def test_space_key_rejects_sensor_disagreement(self):
        rec_board = [row[:] for row in self.state.board]
        rec_board[7][1] = "."
        rec_board[7][4] = "r_C"

        self.hw.recognize_board_state.return_value = {
            "success": True,
            "quality_ok": True,
            "board": rec_board,
        }
        self.hw.yolo_detector.detect_move_observation.return_value = MoveObservation(
            success=True, src=(0, 6), dst=(0, 5), piece="r_P"
        )

        ok = self.input_handler._handle_space_key()
        self.assertFalse(ok)
        self.assertTrue(self.state.manual_override_active)
        self.assertEqual(self.state.board[7][1], "r_C")
        self.assertEqual(self.state.board[6][0], "r_P")


if __name__ == "__main__":
    unittest.main()
