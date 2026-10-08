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

    def test_center_mode_uses_geometric_box_center_for_robot_pick(self):
        center_estimator = VisualPickEstimator(
            Path(self.temp_dir.name) / "perspective.npy", min_confidence=0.45,
            max_offset_cells=0.25, point_mode="center"
        )
        # Center is exactly (3, 2); the legacy foot point would be y=2.7.
        target = center_estimator.estimate_pick_target(
            [(0, 0.90, (2.0, 1.0, 4.0, 3.0))], expected_col=3.0, expected_row=2.0
        )
        self.assertIsNotNone(target)
        self.assertAlmostEqual(target.col, 3.0, places=5)
        self.assertAlmostEqual(target.row, 2.0, places=5)

    def test_rejects_low_confidence_out_of_board_and_far_detections(self):
        detections = [
            (0, 0.44, (2.0, 2.0, 2.0, 2.0)),
            (0, 0.90, (9.0, 2.0, 9.0, 2.0)),
            (0, 0.90, (2.6, 2.0, 2.6, 2.0)),
        ]
        self.assertIsNone(self.estimator.estimate_pick_target(detections, 2.0, 2.0))

    def test_accepts_outside_grid_margin_on_all_four_edges_without_clamping(self):
        for mode in ("center", "foot"):
            estimator = VisualPickEstimator(Path(self.temp_dir.name) / "perspective.npy", point_mode=mode)
            for measured, expected in (((2, -.2), (2, 0)), ((2, 9.2), (2, 9)),
                                       ((-.2, 4), (0, 4)), ((8.2, 4), (8, 4)),
                                       ((-.14, -.14), (0, 0)), ((8.14, 9.14), (8, 9))):
                col, row = measured
                ymin = row-(.05 if mode == "center" else .085)
                detection = [(0, .95, (col-.05, ymin, col+.05, ymin+.1))]
                with self.subTest(mode=mode, measured=measured):
                    target = estimator.estimate_pick_target(detection, *expected)
                    self.assertIsNotNone(target)
                    np.testing.assert_allclose([target.col, target.row], measured, atol=1e-6)

    def test_rejects_points_beyond_outside_margin_even_when_offset_is_below_quarter_cell(self):
        estimator = VisualPickEstimator(Path(self.temp_dir.name) / "perspective.npy", point_mode="center")
        for measured, expected in (((2, -.2001), (2, 0)), ((2, 9.2001), (2, 9)),
                                   ((-.2001, 4), (0, 4)), ((8.2001, 4), (8, 4))):
            col, row = measured
            with self.subTest(measured=measured):
                self.assertIsNone(estimator.estimate_pick_target(
                    [(0, .95, (col-.05, row-.05, col+.05, row+.05))], *expected))

    def test_outside_margin_keeps_confidence_and_radial_offset_limits(self):
        estimator = VisualPickEstimator(Path(self.temp_dir.name) / "perspective.npy", point_mode="center")
        for measured, expected, confidence in (((2, -.2), (2, 0), .44),
                                              ((-.18, -.18), (0, 0), .95),
                                              ((2.24, .12), (2, 0), .95)):
            col, row = measured
            with self.subTest(measured=measured, confidence=confidence):
                self.assertIsNone(estimator.estimate_pick_target(
                    [(0, confidence, (col-.05, row-.05, col+.05, row+.05))], *expected))

    def test_metric_margin_in_center_and_foot_modes_accepts_boundary_and_rejects_beyond(self):
        for mode in ("center", "foot"):
            estimator = VisualPickEstimator(
                Path(self.temp_dir.name) / "perspective.npy", point_mode=mode,
                board_mm=(324., 368.), outside_margin_mm=10.)
            for distance, accepted in ((10., True), (10.1, False)):
                dx, dy = distance * 8 / 324., distance * 9 / 368.
                positions = [((-dx, 4), (0, 4)), ((8+dx, 4), (8, 4)),
                             ((4, -dy), (4, 0)), ((4, 9+dy), (4, 9)),
                             ((-dx, -dy), (0, 0))]
                for measured, expected in positions:
                    with self.subTest(mode=mode, distance=distance, measured=measured):
                        col, row = measured
                        # Position the chosen bbox point at the measured coordinate.
                        fraction = .5 if mode == "center" else estimator.foot_ratio
                        box = (col-.05, row-.1*fraction, col+.05, row+.1*(1-fraction))
                        target = estimator.estimate_pick_target([(0, .95, box)], *expected)
                        if accepted:
                            self.assertIsNotNone(target)
                            np.testing.assert_allclose([target.col, target.row], measured, atol=1e-6)
                        else:
                            self.assertIsNone(target)

    def test_aggregate_targets_uses_median_and_requires_stable_samples(self):
        first = self.estimator.estimate_pick_target([(0, 0.9, (1.9, 1.0, 2.1, 2.0))], 2.0, 1.85)
        second = self.estimator.estimate_pick_target([(0, 0.8, (2.0, 1.0, 2.2, 2.0))], 2.1, 1.85)
        self.assertIsNone(self.estimator.aggregate_targets([first], min_samples=2))
        target = self.estimator.aggregate_targets([first, second], min_samples=2)
        self.assertIsNotNone(target)

    def test_center_pick_rejects_samples_that_do_not_form_a_tight_cluster(self):
        first = GridTarget(1.80, 2.0, 0.9, 0.20)
        second = GridTarget(2.20, 2.0, 0.9, 0.20)
        self.assertIsNone(
            self.estimator.aggregate_targets([first, second], min_samples=2, max_spread_cells=0.12)
        )

    def test_occupancy_uses_full_cell_even_when_piece_is_too_far_for_safe_pick(self):
        center_estimator = VisualPickEstimator(
            Path(self.temp_dir.name) / "perspective.npy", min_confidence=0.45,
            max_offset_cells=0.25, point_mode="center"
        )
        # Center is (2.4, 2.0): still in cell (2,2), but too far for a safe pick offset.
        detections = [(0, 0.90, (2.2, 1.8, 2.6, 2.2))]
        self.assertIsNone(center_estimator.estimate_pick_target(detections, 2.0, 2.0))
        self.assertTrue(center_estimator.has_detection_in_cell(detections, 2.0, 2.0))

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

    def test_stops_capture_when_destination_is_not_visually_cleared(self):
        robot = FR5Robot()
        robot.connected = True
        events = []
        robot.pick_at = lambda *args, **kwargs: events.append("pick")
        robot.move_to_extra_safe = lambda *args, **kwargs: events.append("safe")
        robot.place_in_capture_bin = lambda **kwargs: events.append("bin")
        robot.place_at = lambda *args, **kwargs: events.append("place")
        robot.go_to_home_chess = lambda: events.append("home")

        with self.assertRaisesRegex(RuntimeError, "not visually clear"):
            robot.move_piece(2, 3, 4, 3, True, verify_capture_cleared=lambda: False)
        self.assertEqual(events, ["pick", "safe", "bin"])


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
