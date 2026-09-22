import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.vision.visual_pick_estimator import VisualPickEstimator
from src.vision.visual_pick_estimator import GridTarget
from src.vision.board_reconciler import BoardReconciler
from src.hardware.robot_VIP import FR5Robot
from src.core.game_state import GameState


class VisualPickEstimatorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        perspective = Path(self.temp_dir.name) / "perspective.npy"
        # Identity makes pixel coordinates equal grid coordinates for deterministic tests.
        np.save(perspective, np.eye(3, dtype=np.float32))
        self.estimator = VisualPickEstimator(perspective, min_confidence=0.45,
                                             max_offset_cells=0.25, foot_ratio=0.85)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_selects_nearest_detection_using_foot_point(self):
        # Box foot point: x=3.10, y=1 + ((2.17647 - 1) * .85) = 2.00.
        detections = [
            (0, 0.80, (3.00, 1.00, 3.20, 2.17647)),
            (1, 0.99, (3.60, 1.00, 3.80, 2.17647)),
        ]
        target = self.estimator.estimate_pick_target(detections, expected_col=3.0, expected_row=2.0)
        self.assertIsNotNone(target)
        self.assertAlmostEqual(target.col, 3.10, places=5)
        self.assertAlmostEqual(target.row, 2.0, places=5)

    def test_rejects_low_confidence_out_of_board_and_far_detections(self):
        detections = [
            (0, 0.44, (2.0, 2.0, 2.0, 2.0)),
            (0, 0.90, (9.0, 2.0, 9.0, 2.0)),
            (0, 0.90, (2.6, 2.0, 2.6, 2.0)),
        ]
        self.assertIsNone(self.estimator.estimate_pick_target(detections, 2.0, 2.0))

    def test_aggregate_targets_uses_median_and_requires_stable_samples(self):
        first = self.estimator.estimate_pick_target([(0, 0.9, (1.9, 1.0, 2.1, 2.0))], 2.0, 1.85)
        second = self.estimator.estimate_pick_target([(0, 0.8, (2.0, 1.0, 2.2, 2.0))], 2.1, 1.85)
        self.assertIsNone(self.estimator.aggregate_targets([first], min_samples=2))
        target = self.estimator.aggregate_targets([first, second], min_samples=2)
        self.assertIsNotNone(target)

    def test_returns_target_when_foot_is_within_safe_offset(self):
        detections = [(5, 0.70, (2.00, 1.00, 2.20, 2.00))]
        target = self.estimator.estimate_pick_target(detections, expected_col=2.1, expected_row=1.85)
        self.assertIsNotNone(target)
        self.assertAlmostEqual(target.col, 2.1, places=5)
        self.assertAlmostEqual(target.row, 1.85, places=5)
        self.assertAlmostEqual(target.offset_cells, 0.0, places=5)


class PhysicalPoseTests(unittest.TestCase):
    def test_visual_grid_float_generates_physical_xy_and_pick_rotation(self):
        robot = FR5Robot()
        robot.teaching_points = {
            "R1": {"pose": [0, 0, 0, 0, 0, 0]},
            "R2": {"pose": [0, 80, 0, 0, 0, 0]},
            "R3": {"pose": [90, 80, 0, 0, 0, 0]},
            "R4": {"pose": [90, 0, 0, 0, 0, 0]},
        }
        target = GridTarget(col=4.0, row=4.5, confidence=0.9, offset_cells=0.1)
        # robot_VIP has Vietnamese/emoji diagnostic logging; it is irrelevant to
        # this coordinate unit test and may not be encodable by a Windows shell.
        with contextlib.redirect_stdout(io.StringIO()):
            pose = robot.board_to_pose_bilinear(target.col, target.row, 250.0,
                                                rotation=[10.0, 20.0, 30.0])
        # X includes the project-wide OFFSET_X (currently +5mm); Y has no offset.
        self.assertEqual(pose, [50.0, 40.0, 250.0, 10.0, 20.0, 30.0])

    def test_refreshes_actual_pick_target_after_capture_before_moving_piece(self):
        robot = FR5Robot()
        robot.connected = True
        events = []
        robot.pick_at = lambda col, row, visual_target=None: events.append(("pick", col, row, visual_target))
        robot.move_to_extra_safe = lambda col, row, visual_target=None: events.append(("safe", col, row, visual_target))
        robot.place_in_capture_bin = lambda current_z=None: events.append(("bin",))
        robot.place_at = lambda col, row: events.append(("place", col, row))
        robot.go_to_home_chess = lambda: events.append(("home",))
        fresh = GridTarget(col=2.15, row=3.05, confidence=0.9, offset_cells=0.16)

        robot.move_piece(
            2, 3, 4, 3, True,
            captured_visual_target=GridTarget(col=4.1, row=3.0, confidence=0.9, offset_cells=0.1),
            refresh_moving_visual_target=lambda: fresh,
        )

        self.assertEqual(events[0][0:3], ("pick", 4, 3))
        self.assertIn(("bin",), events)
        moving_pick = [event for event in events if event[0] == "pick"][1]
        self.assertIs(moving_pick[3], fresh)


class BoardReconcilerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        perspective = Path(self.temp_dir.name) / "perspective.npy"
        np.save(perspective, np.eye(3, dtype=np.float32))
        self.reconciler = BoardReconciler(
            VisualPickEstimator(perspective, min_confidence=0.45, max_offset_cells=0.25)
        )
        self.board = [["." for _ in range(9)] for _ in range(10)]
        self.board[2][3] = "b_R"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_accepts_matching_piece_and_returns_its_actual_offset(self):
        actual = [row[:] for row in self.board]
        report = self.reconciler.reconcile(
            self.board, {"moving": (3, 2)}, {"success": True, "board": actual},
            [(0, 0.9, (3.0, 1.0, 3.2, 2.17647))],
        )
        self.assertTrue(report.safe_to_execute)
        self.assertAlmostEqual(report.picks["moving"].target.col, 3.1, places=5)

    def test_rejects_wrong_physical_piece_even_when_yolo_box_is_nearby(self):
        actual = [row[:] for row in self.board]
        actual[2][3] = "b_N"
        report = self.reconciler.reconcile(
            self.board, {"moving": (3, 2)}, {"success": True, "board": actual},
            [(0, 0.9, (3.0, 1.0, 3.2, 2.17647))],
        )
        self.assertFalse(report.safe_to_execute)
        self.assertEqual(report.picks["moving"].reason, "physical piece identity does not match FEN")

    def test_reports_unexpected_piece_elsewhere_on_the_board(self):
        actual = [row[:] for row in self.board]
        actual[5][5] = "r_P"
        report = self.reconciler.reconcile(
            self.board, {"moving": (3, 2)}, {"success": True, "board": actual},
            [(0, 0.9, (3.0, 1.0, 3.2, 2.17647))],
        )
        self.assertIn((5, 5), report.mismatches)
        self.assertFalse(report.safe_to_execute)

    def test_can_verify_a_post_move_board_without_pick_targets(self):
        actual = [row[:] for row in self.board]
        report = self.reconciler.reconcile(
            self.board, {}, {"success": True, "board": actual}, [],
        )
        self.assertTrue(report.board_matches)
        self.assertTrue(report.picks_verified)

    def test_unknown_layout_cell_fails_closed_for_whole_board_verification(self):
        actual = [row[:] for row in self.board]
        actual[8][8] = "x"
        report = self.reconciler.reconcile(
            self.board, {"moving": (3, 2)}, {"success": True, "board": actual},
            [(0, 0.9, (3.0, 1.0, 3.2, 2.17647))],
        )
        self.assertIn((8, 8), report.unknown_cells)
        self.assertFalse(report.board_matches)
        self.assertFalse(report.safe_to_execute)


class PendingAiMoveTests(unittest.TestCase):
    def test_commits_a_verified_pending_move_once_and_releases_sync_fault(self):
        state = GameState.__new__(GameState)
        state.board = [["." for _ in range(9)] for _ in range(10)]
        state.board[2][3] = "b_R"
        state.turn = "b"
        state.move_number = 4
        state.move_history = []
        state.r_captured = []
        state.current_fen = ""
        state.physical_sync_fault = True
        expected_after = [row[:] for row in state.board]
        expected_after[2][3] = "."
        expected_after[2][5] = "b_R"

        state.set_pending_ai_move(((3, 2), (5, 2)), expected_after, ".")
        self.assertTrue(state.commit_pending_ai_move())
        self.assertEqual(state.board, expected_after)
        self.assertEqual(state.turn, "r")
        self.assertEqual(state.move_history, [{"turn": "b", "src": (3, 2), "dst": (5, 2)}])
        self.assertFalse(state.physical_sync_fault)
        self.assertIsNone(state.pending_ai_move)
        self.assertFalse(state.commit_pending_ai_move())


if __name__ == "__main__":
    unittest.main()
