"""Optical, routing and acquisition regressions; no camera or robot connections."""
import contextlib
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from src.hardware.hardware_manager import HardwareManager
from src.vision.pick_geometry import PickGeometry
from src.vision.pick_consensus import FreshPickTransientError
from src.vision.ring_pick_estimator import ColoredRingPickEstimator, resolve_ring_pick_targets
from src.vision.visual_pick_estimator import GridTarget


MODULE = "src.vision.ring_pick_estimator"


def geometry(rvec=(.25, -.2, .04)):
    rotation = cv2.Rodrigues(np.array(rvec))[0]
    return PickGeometry(dict(schema=1,
        camera_matrix=[[1000., 0., 1000.], [0., 1000., 900.], [0., 0., 1.]],
        distortion=[-.12, .025, .001, -.002, 0.], rvec=list(rvec),
        tvec=(-rotation @ np.array([162., 184., -650.])).tolist(),
        board_mm=[324., 368.], piece_height_mm=9., frame_size=[2000, 1800],
        camera_index=0), require_validation=False)


def circle_pixels(g, center, radius, top=True):
    angles = np.linspace(0, 2*np.pi, 240, endpoint=False)
    return g.project(center + radius*np.column_stack((np.cos(angles), np.sin(angles))), top=top)


def piece_image(g, cell=(4, 4), ink=(190, 35, 35), ring=True, shift=(.7, -.5)):
    center = g.grid_to_xy(cell) + shift
    top, base = circle_pixels(g, center, 12), circle_pixels(g, center, 12, False)
    hull = cv2.convexHull(np.rint(np.vstack((top, base))).astype(np.int32))
    frame = np.full((g.frame_size[1], g.frame_size[0], 3), 110, np.uint8)
    cv2.fillPoly(frame, [hull], (245, 245, 245))
    if ring:
        pixels = circle_pixels(g, center, 9.)
        cv2.polylines(frame, [np.rint(pixels).astype(np.int32)], True, ink, 1)
    middle = tuple(np.rint(g.project([center])[0]).astype(int))
    cv2.drawMarker(frame, middle, ink, cv2.MARKER_CROSS, 10, 1)
    pixels = hull.reshape(-1, 2)
    box = (*pixels.min(axis=0)-1., *pixels.max(axis=0)+1.)
    return frame, [(0, .9, box)], center


class ColoredRingOpticalTests(unittest.TestCase):
    def test_blue_purple_and_red_rings_recover_center_at_middle_edges_and_corners(self):
        g = geometry()
        for color in ((190, 35, 35), (190, 35, 190), (35, 35, 190)):
            for cell in ((0, 0), (8, 0), (8, 9), (0, 9), (4, 4), (0, 4), (8, 4)):
                with self.subTest(color=color, cell=cell):
                    frame, boxes, true_center = piece_image(g, cell, color)
                    estimator = ColoredRingPickEstimator(g)
                    target = estimator.estimate_pick_target(frame, boxes, *cell)
                    self.assertIsNotNone(target, estimator.last_reason)
                    np.testing.assert_allclose(g.grid_to_xy((target.col, target.row)), true_center, atol=.6)

    def test_oblique_oval_recovers_metric_circle_instead_of_mapping_ellipse_center(self):
        g = geometry((.65, -.45, .04))
        frame, boxes, true_center = piece_image(g)
        pixels = circle_pixels(g, true_center, 9.)
        axes = cv2.fitEllipse(pixels.astype(np.float32).reshape(-1, 1, 2))[1]
        self.assertGreater(max(axes)/min(axes), 1.2)
        estimator = ColoredRingPickEstimator(g)
        target = estimator.estimate_pick_target(frame, boxes, 4, 4)
        self.assertIsNotNone(target, estimator.last_reason)
        np.testing.assert_allclose(g.grid_to_xy((target.col, target.row)), true_center, atol=.6)

    def test_white_body_character_or_uncolored_ring_cannot_supply_a_pick(self):
        g = geometry()
        for ink, ring in (((190, 35, 35), False), ((15, 15, 15), True),
                          ((35, 190, 35), True)):
            frame, boxes, _ = piece_image(g, ink=ink, ring=ring)
            estimator = ColoredRingPickEstimator(g)
            self.assertIsNone(estimator.estimate_pick_target(frame, boxes, 4, 4))

    def test_occlusion_frame_mismatch_and_duplicate_boxes_reject(self):
        g = geometry()
        frame, boxes, center = piece_image(g)
        estimator = ColoredRingPickEstimator(g)
        self.assertIsNone(estimator.estimate_pick_target(frame, boxes*2, 4, 4))
        self.assertIn("multiple", estimator.last_reason)
        self.assertIsNone(estimator.estimate_pick_target(frame[:-1], boxes, 4, 4))
        pixel = g.project([center])[0]
        frame[:int(pixel[1]), int(boxes[0][2][0])-3:int(boxes[0][2][2])+3] = 110
        self.assertIsNone(estimator.estimate_pick_target(frame, boxes, 4, 4))

    def test_bbox_change_does_not_change_supported_ring_center(self):
        g = geometry()
        frame, boxes, _ = piece_image(g)
        estimator = ColoredRingPickEstimator(g)
        first = estimator.estimate_pick_target(frame, boxes, 4, 4)
        box = np.asarray(boxes[0][2])+[-3, -2, 4, 5]
        second = estimator.estimate_pick_target(frame, [(0, .9, box)], 4, 4)
        self.assertIsNotNone(first, estimator.last_reason)
        self.assertIsNotNone(second, estimator.last_reason)
        np.testing.assert_allclose([first.col, first.row], [second.col, second.row], atol=.005)


class RingAcquisitionTests(unittest.TestCase):
    def hardware(self):
        hw = HardwareManager.__new__(HardwareManager)
        hw.config = SimpleNamespace(VISUAL_RING_PICK_ENABLED=True, VISUAL_CURRENT_PICK_ENABLED=False,
            VISUAL_CAMERA_INTRINSICS_PATH="calibration/camera_intrinsics.json",
            VISUAL_HEIGHT_BOARD_MM=(324., 368.), VISUAL_HEIGHT_PIECE_MM=7.,
            VISUAL_HEIGHT_POSE_MAX_ERROR_PX=3., VISUAL_PICK_MIN_CONFIDENCE=.45,
            VISUAL_PICK_MAX_OFFSET_CELLS=.25)
        hw.project_dir, hw.perspective_path, hw.actual_camera_index = ".", "perspective.npy", 0
        hw.cam_monitor = Mock()
        hw.cam_monitor.pick_scan_session = contextlib.nullcontext
        hw.cam_monitor.get_fresh_pick_snapshot.return_value = (np.zeros((480, 640, 3), np.uint8), [])
        return hw

    def acquire(self, hw, observations):
        optical = Mock()
        optical.geometry = SimpleNamespace(width=324., height=368., frame_size=(640, 480))
        optical.estimate_pick_target.side_effect = observations
        optical.last_reason = "test ring evidence"
        with patch(MODULE+".np.load", return_value=np.eye(3)), \
             patch(MODULE+".geometry_from_board", return_value=optical.geometry) as pose, \
             patch(MODULE+".ColoredRingPickEstimator", return_value=optical), \
             patch(MODULE+".time.monotonic", return_value=0.), \
             contextlib.redirect_stdout(io.StringIO()):
            targets = resolve_ring_pick_targets(hw, {"moving": (4, 4)})
        return targets, pose, optical

    def test_fresh_metric_consensus_uses_active_height_and_dimensions(self):
        hw = self.hardware()
        measured = GridTarget(4.02, 4.01, .9, .03)
        result, pose, optical = self.acquire(hw, [measured]*3)
        self.assertEqual(result["moving"], measured)
        self.assertEqual(hw.last_pick_resolution["failure"], "")
        self.assertEqual(hw.cam_monitor.get_fresh_pick_snapshot.call_count, 3)
        self.assertEqual(pose.call_args.args[4:6], ((324., 368.), 7.))
        self.assertEqual(optical.estimate_pick_target.call_count, 3)

    def test_missing_latest_ring_never_returns_stale_or_bbox_target(self):
        hw = self.hardware()
        measured = GridTarget(4, 4, .9, 0)
        result, _, _ = self.acquire(hw, [measured, measured, None, None, None, None])
        self.assertIsNone(result["moving"])
        self.assertEqual(hw.last_pick_resolution["failure"], "consensus")
        self.assertEqual(hw.last_pick_resolution["attempts"], 6)

    def test_transient_acquisition_failure_is_bounded_and_retryable(self):
        hw = self.hardware()
        hw.cam_monitor.get_fresh_pick_snapshot.side_effect = FreshPickTransientError("busy")
        result, pose, optical = self.acquire(hw, [])
        self.assertIsNone(result["moving"])
        self.assertEqual(hw.last_pick_resolution["failure"], "consensus")
        self.assertEqual(hw.cam_monitor.get_fresh_pick_snapshot.call_count, 6)
        pose.assert_not_called()
        optical.estimate_pick_target.assert_not_called()

    def test_invalid_calibration_blocks_before_estimation(self):
        hw = self.hardware()
        with patch(MODULE+".np.load", return_value=np.eye(3)), \
             patch(MODULE+".geometry_from_board", side_effect=ValueError("wrong camera")), \
             patch(MODULE+".ColoredRingPickEstimator") as optical, \
             contextlib.redirect_stdout(io.StringIO()):
            result = resolve_ring_pick_targets(hw, {"moving": (4, 4)})
        self.assertIsNone(result["moving"])
        self.assertEqual(hw.last_pick_resolution["failure"], "hard")
        self.assertIn("wrong camera", hw.last_pick_resolution["reason"])
        optical.assert_not_called()

    def test_late_snapshot_is_rejected_before_geometry_or_motion(self):
        hw = self.hardware()
        with patch(MODULE+".np.load", return_value=np.eye(3)), \
             patch(MODULE+".time.monotonic", side_effect=[0., 0., 0., 4., 4., 4.]), \
             patch(MODULE+".geometry_from_board") as pose, \
             contextlib.redirect_stdout(io.StringIO()):
            result = resolve_ring_pick_targets(hw, {"moving": (4, 4)})
        self.assertIsNone(result["moving"])
        self.assertEqual(hw.last_pick_resolution["failure"], "deadline")
        pose.assert_not_called()


class RingRoutingTests(unittest.TestCase):
    def manager(self, **flags):
        hw = HardwareManager.__new__(HardwareManager)
        hw.config = SimpleNamespace(VISUAL_TOP_FACE_ENABLED=False, VISUAL_HEIGHT_PICK_ENABLED=True, **flags)
        hw._get_height_pick_targets = Mock(return_value={"moving": "current"})
        hw._get_top_face_targets = Mock(return_value={"moving": "commissioned"})
        hw.get_visual_pick_targets = Mock()
        return hw

    def test_current_logic_and_configs_without_switches_retain_original_route(self):
        for flags in ({}, dict(VISUAL_RING_PICK_ENABLED=False, VISUAL_CURRENT_PICK_ENABLED=True)):
            hw = self.manager(**flags)
            self.assertEqual(hw.get_robot_center_pick_targets({"moving": (4, 4)}), {"moving": "current"})
            hw._get_height_pick_targets.assert_called_once()

    def test_ring_mode_initializes_occupancy_with_older_visual_flags_off(self):
        hw = self.manager(VISUAL_RING_PICK_ENABLED=True, VISUAL_CURRENT_PICK_ENABLED=False)
        hw.config.VISUAL_PICK_ENABLED = False
        hw.config.VISUAL_HEIGHT_PICK_ENABLED = False
        hw.config.VISUAL_BOARD_SYNC_REQUIRED = False
        hw.config.CCHESS_RECOGNITION_ENABLED = False
        hw.config.VIDEO_SOURCE = 0
        hw.config.VISUAL_PICK_MIN_CONFIDENCE = .45
        hw.config.VISUAL_PICK_MAX_OFFSET_CELLS = .25
        hw.config.VISUAL_PICK_FOOT_RATIO = .85
        hw.project_dir, hw.perspective_path, hw.dry_run = ".", "perspective.npy", False
        hw.cchess_recognizer, hw.center_pick_estimator, hw.class_id_to_name = None, None, {}
        prefix = "src.hardware.hardware_manager."
        with patch(prefix+"YOLO"), patch(prefix+"open_camera"), \
             patch(prefix+"run_calibration_flow"), patch(prefix+"os.path.exists", return_value=True), \
             patch(prefix+"CameraMonitor"), patch(prefix+"YoloSnapshotDetector"), \
             patch(prefix+"VisualPickEstimator") as occupancy, patch(prefix+"BoardReconciler"), \
             contextlib.redirect_stdout(io.StringIO()):
            hw._init_camera()
        self.assertIsNotNone(hw.center_pick_estimator)
        self.assertEqual(occupancy.call_count, 2)

    def test_new_logic_has_priority_and_failure_does_not_fall_back(self):
        for old in (False, True):
            hw = self.manager(VISUAL_RING_PICK_ENABLED=True, VISUAL_CURRENT_PICK_ENABLED=old)
            hw.config.VISUAL_TOP_FACE_ENABLED = True
            with patch("src.hardware.hardware_manager.resolve_ring_pick_targets",
                       return_value={"moving": None}) as new:
                self.assertEqual(hw.get_robot_center_pick_targets({"moving": (4, 4)}), {"moving": None})
            new.assert_called_once()
            hw._get_height_pick_targets.assert_not_called()
            hw._get_top_face_targets.assert_not_called()
            hw.get_visual_pick_targets.assert_not_called()

    def test_both_disabled_block_instead_of_silently_selecting_a_logic(self):
        hw = self.manager(VISUAL_RING_PICK_ENABLED=False, VISUAL_CURRENT_PICK_ENABLED=False)
        self.assertIsNone(hw.get_robot_center_pick_targets({"moving": (4, 4)})["moving"])
        self.assertEqual(hw.last_pick_resolution["failure"], "hard")
        hw._get_height_pick_targets.assert_not_called()

    def test_pick_place_mode_blocks_missing_ring_before_arm_motion(self):
        hw = self.manager(VISUAL_RING_PICK_ENABLED=True, VISUAL_CURRENT_PICK_ENABLED=False)
        hw.robot = Mock(connected=True)
        hw.cam_monitor = Mock()
        hw.center_pick_estimator = None
        hw.is_cell_visually_clear = Mock(return_value=True)
        hw.verify_visual_move = Mock(return_value=True)
        hw.last_pick_resolution = dict(failure="hard", reason="No ring")
        with patch("src.hardware.hardware_manager.resolve_ring_pick_targets", return_value={"moving": None}):
            with self.assertRaisesRegex(RuntimeError, "No ring"):
                hw.execute_pick_place_test((4, 4), (5, 4))
        hw.robot.move_piece.assert_not_called()

    def test_ai_requires_new_target_even_when_older_visual_flags_are_off(self):
        from test_pick_consensus import state_with_pending
        from src.core.visual_move_coordinator import execute_pending_ai_motion

        for ring in (True, False):
            state = state_with_pending()
            fen, pending = state.current_fen, state.pending_ai_move
            config = SimpleNamespace(VISUAL_RING_PICK_ENABLED=ring, VISUAL_CURRENT_PICK_ENABLED=False,
                VISUAL_PICK_ENABLED=False, VISUAL_HEIGHT_PICK_ENABLED=False, VISUAL_TOP_FACE_ENABLED=False)
            hw = SimpleNamespace(robot=Mock(connected=True),
                get_robot_center_pick_targets=Mock(return_value={"moving": None}),
                last_pick_resolution=dict(failure="hard", reason="No selected pick target"))
            with self.subTest(ring=ring), self.assertRaisesRegex(RuntimeError, "No selected pick target"):
                execute_pending_ai_motion(state, hw, config)
            hw.robot.move_piece.assert_not_called()
            self.assertEqual(state.current_fen, fen)
            self.assertIs(state.pending_ai_move, pending)

    def test_ring_ai_capture_refresh_is_required_and_does_not_commit_fen(self):
        from test_pick_consensus import state_with_pending
        from src.core.visual_move_coordinator import execute_pending_ai_motion

        state = state_with_pending(capture=True)
        fen = state.current_fen
        config = SimpleNamespace(VISUAL_RING_PICK_ENABLED=True, VISUAL_CURRENT_PICK_ENABLED=False,
            VISUAL_PICK_ENABLED=False, VISUAL_HEIGHT_PICK_ENABLED=False, VISUAL_TOP_FACE_ENABLED=False)
        hw = SimpleNamespace(robot=Mock(connected=True),
            get_robot_center_pick_targets=Mock(return_value={"captured": GridTarget(6, 4, .9, 0)}),
            is_cell_visually_clear=Mock(return_value=True), verify_visual_move=Mock(return_value=True),
            last_pick_resolution=dict(failure="hard", reason="Source ring unavailable"))
        execute_pending_ai_motion(state, hw, config)
        call = hw.robot.move_piece.call_args.kwargs
        self.assertTrue(call["require_visual_target"])
        self.assertTrue(call["verify_capture_cleared"]())
        hw.get_robot_center_pick_targets.return_value = {"moving": None}
        with self.assertRaisesRegex(RuntimeError, "Source ring unavailable"):
            call["refresh_moving_visual_target"]()
        self.assertEqual(state.current_fen, fen)


if __name__ == "__main__":
    unittest.main()
