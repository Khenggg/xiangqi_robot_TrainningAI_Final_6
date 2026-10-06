"""Synthetic optical/motion tests; never open a camera or a robot connection."""
import copy
import ast
import contextlib
import io
import runpy
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from src.vision.pick_geometry import (
    BOARD_CORNERS, VALIDATION_CELLS, PickGeometry,
    calibrate_intrinsics, estimate_board_pose,
)
from src.vision.top_face_pick_estimator import TopFacePickEstimator, fit_metric_circle
from src.vision.visual_pick_estimator import GridTarget, VisualPickEstimator
from src.vision.camera_monitor import CameraMonitor
from src.hardware.hardware_manager import HardwareManager
from src.hardware.robot_VIP import FR5Robot


def profile_data():
    rotation = cv2.Rodrigues(np.array([.25, -.2, .04]))[0]
    center = np.array([125., 140.625, -650.])
    data = dict(schema=1, camera_matrix=[[800., 0., 640.], [0., 800., 480.], [0., 0., 1.]],
                distortion=[-.13, .03, .001, -.001, 0.], rvec=[.25, -.2, .04],
                tvec=(-rotation @ center).tolist(), board_mm=[250., 281.25],
                piece_height_mm=10., frame_size=[1280, 960], camera_index=1,
                quality=dict(intrinsic_rms_px=.3, pose_max_error_px=.5, max_error_mm=1.,
                             intrinsic_views=15, diverse_views=True, operator_approved=True))
    geometry = PickGeometry(data, require_validation=False)
    cells = np.array([(x, y) for x in (0, 4, 8) for y in (0, 4, 9)], float)
    data['pattern'] = dict(inner_corners=[9, 6], square_mm=20.)
    data['pose_observations'] = dict(cells=cells.tolist(), pixels=geometry.project(
        geometry.grid_to_xy(cells), top=False).tolist())
    data['height_validation'] = [dict(cell=list(cell), pixel=geometry.project(
        [geometry.grid_to_xy(cell)])[0].tolist()) for cell in VALIDATION_CELLS]
    return data


def circle_pixels(geometry, center, radius=12., count=240):
    angles = np.linspace(0, 2*np.pi, count, endpoint=False)
    xy = np.asarray(center) + radius*np.column_stack((np.cos(angles), np.sin(angles)))
    return geometry.project(xy)


class PickGeometryTests(unittest.TestCase):
    def setUp(self):
        self.data = profile_data()
        self.geometry = PickGeometry(self.data)

    def test_piece_plane_is_ten_mm_not_camera_height(self):
        self.assertEqual(abs(self.geometry.top_z), 10.)
        self.assertAlmostEqual(abs(self.geometry.camera_center[2]), 650.)
        np.testing.assert_allclose(self.geometry.grid_to_xy((8, 9)), [250, 281.25])
        np.testing.assert_allclose(self.geometry.grid_to_xy((1, 1)), [31.25, 31.25])

    def test_distorted_oblique_top_rim_recovers_center_and_all_four_corners(self):
        for cell in VALIDATION_CELLS:
            with self.subTest(cell=cell):
                actual = self.geometry.grid_to_xy(cell) + [.5, -.4]
                projected = circle_pixels(self.geometry, actual)
                recovered = self.geometry.pixels_to_top_xy(projected)
                center, radius, residual, coverage = fit_metric_circle(recovered)
                np.testing.assert_allclose(center, actual, atol=.002)
                self.assertAlmostEqual(radius, 12., places=3)
                self.assertLess(residual, .0001)
                self.assertEqual(coverage, 1.)

    def test_camera_on_positive_board_normal_uses_positive_top_plane(self):
        data = copy.deepcopy(self.data)
        rotation = np.diag([1., -1., -1.])
        data['rvec'] = cv2.Rodrigues(rotation)[0].ravel().tolist()
        data['tvec'] = (-rotation @ np.array([125., 140.625, 650.])).tolist()
        geometry = PickGeometry(data, require_validation=False)
        self.assertEqual(geometry.top_z, 10.)
        for cell in VALIDATION_CELLS:
            actual = geometry.grid_to_xy(cell)
            np.testing.assert_allclose(geometry.pixels_to_top_xy(geometry.project([actual]))[0],
                                       actual, atol=.002)

    def test_image_ellipse_center_is_not_physical_circle_center(self):
        geometry = self.geometry
        actual = np.array([0., 0.])
        pixels = circle_pixels(geometry, actual, radius=15.)
        ellipse_center = cv2.fitEllipse(pixels.astype(np.float32).reshape(-1, 1, 2))[0]
        transformed_center = geometry.pixels_to_top_xy([ellipse_center])[0]
        physical_center = fit_metric_circle(geometry.pixels_to_top_xy(pixels))[0]
        self.assertGreater(np.linalg.norm(transformed_center-actual), .02)
        np.testing.assert_allclose(physical_center, actual, atol=.005)

    def test_fresh_homography_can_differ_in_scale_without_invalidating_context(self):
        pixels = self.geometry.project(self.geometry.grid_to_xy(BOARD_CORNERS), top=False)
        matrix = cv2.getPerspectiveTransform(pixels.astype(np.float32), BOARD_CORNERS.astype(np.float32))
        for scale in (1., 17.):
            self.geometry.validate_context(1, (1280, 960), (250, 281.25), 10, matrix*scale)
        changed = pixels.copy()
        changed[0] += [9, 0]
        with self.assertRaises(ValueError):
            self.geometry.validate_context(1, (1280, 960), (250, 281.25), 10,
                cv2.getPerspectiveTransform(changed.astype(np.float32), BOARD_CORNERS.astype(np.float32)))
        for args in ((2, (1280, 960), (250, 281.25), 10),
                     (1, (1280, 720), (250, 281.25), 10),
                     (1, (1280, 960), (250, 250), 10),
                     (1, (1280, 960), (250, 281.25), 20)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.geometry.validate_context(*args, matrix)

    def test_bad_intrinsics_pose_or_missing_independent_checks_rejected(self):
        changes = [('camera_matrix', [[0, 0, 640], [0, 1000, 480], [0, 0, 1]]),
                   ('distortion', [float('nan')]*5), ('distortion', [0, 0]),
                   ('rvec', [float('inf'), 0, 0]), ('tvec', [0, 0, -650]),
                   ('height_validation', [])]
        for key, value in changes:
            data = copy.deepcopy(self.data)
            data[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                PickGeometry(data)
        for key, value in [('operator_approved', False), ('diverse_views', False),
                           ('intrinsic_views', 11), ('intrinsic_rms_px', 1.1),
                           ('pose_max_error_px', 2.1), ('max_error_mm', float('nan'))]:
            data = copy.deepcopy(self.data)
            data['quality'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                PickGeometry(data)

    def test_independent_height_measurement_not_just_approval_flag(self):
        data = copy.deepcopy(self.data)
        data['height_validation'][0]['pixel'][0] += 15
        with self.assertRaisesRegex(ValueError, 'validation exceeds'):
            PickGeometry(data)
        data = copy.deepcopy(self.data)
        data['height_validation'][1] = copy.deepcopy(data['height_validation'][0])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            PickGeometry(data)

    def test_printed_target_and_stored_pose_evidence_required(self):
        for square in (0, float('nan')):
            data = copy.deepcopy(self.data)
            data['pattern']['square_mm'] = square
            with self.subTest(square=square), self.assertRaises(ValueError):
                PickGeometry(data)
        for field in ('pattern', 'pose_observations'):
            data = copy.deepcopy(self.data)
            del data[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                PickGeometry(data)
        data = copy.deepcopy(self.data)
        data['pose_observations']['pixels'][4][0] += 15
        with self.assertRaisesRegex(ValueError, 'reprojection'):
            PickGeometry(data)

    def test_nonfinite_grazing_and_backwards_rays_fail(self):
        with self.assertRaises(ValueError):
            self.geometry.pixels_to_top_xy([[float('nan'), 20]])
        # Controlled normalized ray; geometry still has a valid real pose.
        row = self.geometry.rotation[:, 2]
        x = -row[2]/row[0]
        with patch('src.vision.pick_geometry.cv2.undistortPoints', return_value=np.array([[[x, 0.]]])):
            with self.assertRaisesRegex(ValueError, 'parallel'):
                self.geometry.pixels_to_top_xy([[1, 1]])
        # Camera below board needs positive world-Z ray; choose negative instead.
        x_back = x - np.sign(row[0])*10
        with patch('src.vision.pick_geometry.cv2.undistortPoints', return_value=np.array([[[x_back, 0.]]])):
            with self.assertRaisesRegex(ValueError, 'behind'):
                self.geometry.pixels_to_top_xy([[1, 1]])

    def test_atomic_approved_save_round_trip_and_recoverable_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'geometry.json'
            self.geometry.save_approved(path)
            first = path.read_bytes()
            self.geometry.save_approved(path)
            self.assertEqual(PickGeometry.load(path).profile_id, self.geometry.profile_id)
            backups = list(Path(folder).glob('geometry.json.backup-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), first)
            self.assertFalse(path.with_name('geometry.json.tmp').exists())

    def test_intrinsics_require_new_measured_square_and_diverse_views(self):
        points = np.mgrid[0:9, 0:6].T.reshape(-1, 2)*20. + [100, 100]
        for count, square in ((11, 20), (15, 0), (15, float('nan'))):
            with self.subTest(count=count, square=square), self.assertRaises(ValueError):
                calibrate_intrinsics([points]*count, (9, 6), square, (1280, 960))
        with self.assertRaisesRegex(ValueError, 'edges'):
            calibrate_intrinsics([points+i for i in range(15)], (9, 6), 20, (1280, 960))
        views = [points+[x, y] for x in (0, 200, 400, 600) for y in (0, 200, 400)]
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            calibrate_intrinsics(views+[views[0]], (9, 6), 20, (1280, 960))
        fake_poses = [np.zeros((3, 1)) for _ in views]
        for rms in (.1, 1.1):
            with patch('src.vision.pick_geometry.cv2.calibrateCamera',
                       return_value=(rms, self.geometry.k, self.geometry.dist, fake_poses, [])):
                with self.assertRaisesRegex(ValueError, 'tilts'):
                    calibrate_intrinsics(views, (9, 6), 20, (1280, 960))

    def test_nine_board_pose_points_and_consistency_gates(self):
        cells = np.array([(x, y) for x in (0, 4, 8) for y in (0, 4, 9)], float)
        pixels = self.geometry.project(self.geometry.grid_to_xy(cells), top=False)
        rvec, tvec, error = estimate_board_pose(cells, pixels, self.geometry.k,
                                               self.geometry.dist, (250, 281.25))
        self.assertLess(error, .001)
        np.testing.assert_allclose(rvec.ravel(), self.geometry.rvec.ravel(), atol=.001)
        np.testing.assert_allclose(tvec.ravel(), self.geometry.tvec.ravel(), atol=.01)
        with self.assertRaises(ValueError):
            estimate_board_pose(cells[:8], pixels[:8], self.geometry.k, self.geometry.dist, (250, 281.25))
        with self.assertRaisesRegex(ValueError, 'Degenerate'):
            estimate_board_pose(np.column_stack((np.arange(9), np.zeros(9))), pixels,
                                self.geometry.k, self.geometry.dist, (250, 281.25))
        pixels[4] += 25
        with self.assertRaisesRegex(ValueError, 'inconsistent'):
            estimate_board_pose(cells, pixels, self.geometry.k, self.geometry.dist, (250, 281.25))

    def test_real_opencv_intrinsics_fit_from_diverse_synthetic_projections(self):
        objects = np.zeros((9*6, 3), np.float32)
        objects[:, :2] = np.mgrid[0:9, 0:6].T.reshape(-1, 2)*20.
        views = []
        for i, x in enumerate((-240., -80., 80., 240.)):
            for j, y in enumerate((-200., 0., 200.)):
                projected = cv2.projectPoints(objects,
                    np.array([.15+i*.1, -.3+j*.3, .03]),
                    np.array([x, y, 600.+40*(i % 2)]), self.geometry.k, self.geometry.dist)[0]
                views.append(projected)
        rms, matrix, distortion = calibrate_intrinsics(views, (9, 6), 20., (1280, 960))
        self.assertLess(rms, .001)
        np.testing.assert_allclose(matrix, self.geometry.k, atol=.01)
        np.testing.assert_allclose(distortion.ravel(), self.geometry.dist, atol=.001)


class TopFaceEstimatorTests(unittest.TestCase):
    def setUp(self):
        self.geometry = PickGeometry(profile_data())
        self.estimator = TopFacePickEstimator(self.geometry)

    def image(self, cell=(4, 4), offset=(0, 0), character=True):
        center = self.geometry.grid_to_xy(cell) + offset
        points = circle_pixels(self.geometry, center)
        frame = np.full((960, 1280, 3), 110, np.uint8)
        cv2.fillPoly(frame, [np.rint(points).astype(np.int32)], (245, 245, 245))
        # Independent printed inner ring, surrounded by white top face on both
        # sides. Outer body silhouette alone is NOT top-plane evidence.
        inner_rim = circle_pixels(self.geometry, center, radius=9.)
        cv2.polylines(frame, [np.rint(inner_rim).astype(np.int32)], True, (15, 15, 15), 1)
        if character:
            pixel = tuple(np.rint(self.geometry.project([center])[0]).astype(int))
            cv2.drawMarker(frame, pixel, (0, 0, 0), cv2.MARKER_CROSS, 12, 2)
        minimum, maximum = points.min(axis=0)-1, points.max(axis=0)+1
        box = (*minimum, *maximum)
        return frame, [(0, .9, box)], center

    def cylinder_image(self, cell, printed_rim=False):
        center = self.geometry.grid_to_xy(cell)
        angles = np.linspace(0, 2*np.pi, 240, endpoint=False)
        xy = center+12*np.column_stack((np.cos(angles), np.sin(angles)))
        top = self.geometry.project(xy, top=True)
        base = self.geometry.project(xy, top=False)
        hull = cv2.convexHull(np.rint(np.vstack((top, base))).astype(np.int32))
        frame = np.full((960, 1280, 3), 110, np.uint8)
        cv2.fillPoly(frame, [hull], (245, 245, 245))
        if printed_rim:
            inner = circle_pixels(self.geometry, center, radius=9.)
            cv2.polylines(frame, [np.rint(inner).astype(np.int32)], True, (15, 15, 15), 1)
        pixels = hull.reshape(-1, 2)
        box = (*pixels.min(axis=0)-1., *pixels.max(axis=0)+1.)
        return frame, [(0, .9, box)], center

    def test_raster_top_rim_with_character_at_center_and_edges(self):
        for cell in VALIDATION_CELLS:
            with self.subTest(cell=cell):
                frame, detections, center = self.image(cell, (.7, -.5))
                target = self.estimator.estimate_pick_target(frame, detections, *cell)
                self.assertIsNotNone(target, self.estimator.last_reason)
                np.testing.assert_allclose(self.geometry.grid_to_xy((target.col, target.row)), center, atol=.6)
                self.assertEqual(self.estimator.diagnostic.shape, frame.shape)
                self.assertFalse(np.array_equal(frame, self.estimator.diagnostic))

    def test_character_only_and_occluded_face_do_not_become_bbox_pick(self):
        frame, detections, _ = self.image()
        x1, y1, x2, y2 = detections[0][2]
        frame[int(y1)-3:int(y2)+3, int(x1)-3:int(x2)+3] = 110
        center = tuple(np.rint(self.geometry.project([self.geometry.grid_to_xy((4, 4))])[0]).astype(int))
        cv2.drawMarker(frame, center, (0, 0, 0), cv2.MARKER_CROSS, 12, 2)
        self.assertIsNone(self.estimator.estimate_pick_target(frame, detections, 4, 4))
        frame, detections, _ = self.image()
        frame[:center[1], int(x1)-3:int(x2)+3] = 110
        self.assertIsNone(self.estimator.estimate_pick_target(frame, detections, 4, 4))

    def test_raster_body_silhouette_without_independent_top_ring_is_rejected(self):
        # A 10mm cylinder's white top+visible side form a near-circle body hull.
        # Mapping that mixed-height silhouette to Z=10 can fit a biased circle;
        # the two Canny traces of its ONE edge are not independent top evidence.
        for cell in ((0, 0), (8, 0), (8, 9), (0, 9), (4, 4)):
            with self.subTest(cell=cell):
                frame, detections, _ = self.cylinder_image(cell)
                target = self.estimator.estimate_pick_target(frame, detections, *cell)
                self.assertIsNone(target, self.estimator.last_reason)

    def test_printed_top_rim_recovers_center_despite_visible_body_silhouette(self):
        for cell in VALIDATION_CELLS:
            with self.subTest(cell=cell):
                frame, detections, center = self.cylinder_image(cell, printed_rim=True)
                target = self.estimator.estimate_pick_target(frame, detections, *cell)
                self.assertIsNotNone(target, self.estimator.last_reason)
                np.testing.assert_allclose(self.geometry.grid_to_xy((target.col, target.row)), center, atol=.6)

    def test_frame_roi_confidence_and_offset_gates(self):
        frame, detections, _ = self.image()
        for changed in ([ (0, .4, detections[0][2]) ],
                        [ (0, .9, (1, 1, 45, 45)) ],
                        [ (0, .9, (float('nan'), 1, 45, 45)) ]):
            with self.subTest(changed=changed):
                self.assertIsNone(self.estimator.estimate_pick_target(frame, changed, 4, 4))
        self.assertIsNone(self.estimator.estimate_pick_target(frame[:720], detections, 4, 4))
        self.assertIsNone(self.estimator.estimate_pick_target(frame, detections, 3, 4))

    def test_candidate_contours_without_actual_white_annulus_evidence_are_rejected(self):
        frame, detections, center = self.image()
        box = detections[0][2]
        pad = max(box[2]-box[0], box[3]-box[1])*.1+2
        left, top = int(np.floor(box[0]-pad)), int(np.floor(box[1]-pad))
        contours = [np.rint(circle_pixels(self.geometry, center+delta)-[left, top]).astype(np.int32).reshape(-1, 1, 2)
                    for delta in ((0, 0), (2.5, 0))]
        with patch('src.vision.top_face_pick_estimator.cv2.findContours', return_value=(contours, None)):
            self.assertIsNone(self.estimator.estimate_pick_target(frame, detections, 4, 4))

    def test_ambiguous_supported_rims_rejected_before_expected_cell_offset_filter(self):
        # Two nested, eccentric printed rims have independent white support.
        # One center is safely within the .25-cell gate; the other is just
        # outside it. Cell proximity must NOT erase evidence of ambiguity.
        data = copy.deepcopy(self.geometry.data)
        data['camera_matrix'] = (self.geometry.k*np.array([[2, 1, 2], [1, 2, 2], [1, 1, 1]])).tolist()
        data['frame_size'] = [2560, 1920]
        geometry = PickGeometry(data, require_validation=False)
        reference = geometry.grid_to_xy((4, 4))
        body = circle_pixels(geometry, reference+[8.2, 0], radius=14.)
        frame = np.full((1920, 2560, 3), 110, np.uint8)
        cv2.fillPoly(frame, [np.rint(body).astype(np.int32)], (245, 245, 245))
        for center, radius in ((reference+[9.2, 0], 10.), (reference+[7.2, 0], 6.)):
            pixels = circle_pixels(geometry, center, radius)
            cv2.polylines(frame, [np.rint(pixels).astype(np.int32)], True, (15, 15, 15), 1)
        box = (*body.min(axis=0)-1., *body.max(axis=0)+1.)
        estimator = TopFacePickEstimator(geometry, min_box_fraction=.4)
        target = estimator.estimate_pick_target(frame, [(0, .9, box)], 4, 4)
        self.assertIsNone(target, estimator.last_reason)
        self.assertIn('ambiguous', estimator.last_reason)

    def test_multiple_nearby_boxes_and_unstable_samples_fail(self):
        frame, detections, _ = self.image()
        self.assertIsNone(self.estimator.estimate_pick_target(frame, detections*2, 4, 4))
        self.assertIn('multiple', self.estimator.last_reason)
        self.assertIsNone(self.estimator.aggregate_targets([GridTarget(4, 4, .9, 0)], 2))
        self.assertIsNone(self.estimator.aggregate_targets(
            [GridTarget(3.8, 4, .9, .2), GridTarget(4.2, 4, .9, .2)], 2, max_spread_cells=.12))

    def test_invalid_fit_thresholds_are_rejected_at_configuration_time(self):
        for kwargs in ({'max_residual': float('nan')}, {'min_coverage': 2.},
                       {'min_box_fraction': -1.}, {'radius_mm': (15., 5.)},
                       {'ambiguity_mm': 0.}, {'max_offset_cells': float('inf')},
                       {'max_enclosing_area_ratio': .9}, {'annulus_offset_mm': 0.},
                       {'min_white_annulus_fraction': .5}, {'max_white_saturation': 100},
                       {'min_white_value': 110}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                TopFacePickEstimator(self.geometry, **kwargs)


class GuardedMotionTests(unittest.TestCase):
    def robot(self):
        robot = FR5Robot.__new__(FR5Robot)
        robot.connected, robot.dry = True, True
        for method in ('pick_at', 'move_to_extra_safe', 'place_in_capture_bin', 'place_at', 'go_to_home_chess', 'connect'):
            setattr(robot, method, Mock())
        return robot

    def move(self, robot, capture=False, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            robot.move_piece(2, 3, 4, 3, capture, **kwargs)

    def test_missing_or_nonfinite_source_stops_before_any_motion(self):
        for target in (None, GridTarget(float('nan'), 3, .9, 0)):
            robot = self.robot()
            with self.assertRaises(RuntimeError):
                self.move(robot, require_visual_target=True, moving_visual_target=target)
            robot.pick_at.assert_not_called()
            robot.connect.assert_not_called()

    def test_capture_guard_requires_measured_capture_and_refresh_and_clear_check(self):
        good = GridTarget(4, 3, .9, 0)
        for kwargs in ({}, {'captured_visual_target': good},
                       {'captured_visual_target': good, 'refresh_moving_visual_target': lambda: good}):
            robot = self.robot()
            with self.assertRaises(RuntimeError):
                self.move(robot, True, require_visual_target=True, **kwargs)
            robot.pick_at.assert_not_called()

    def test_none_or_nonfinite_refresh_stops_source_after_capture(self):
        for fresh in (None, GridTarget(2, float('inf'), .9, 0)):
            robot = self.robot()
            capture = GridTarget(4, 3, .9, 0)
            with self.assertRaises(RuntimeError):
                self.move(robot, True, require_visual_target=True, captured_visual_target=capture,
                          refresh_moving_visual_target=lambda: fresh, verify_capture_cleared=lambda: True)
            robot.pick_at.assert_called_once_with(4, 3, visual_target=capture)
            robot.place_at.assert_not_called()

    def test_non_capture_missing_refresh_stops_and_legacy_logical_mode_remains(self):
        robot = self.robot()
        with self.assertRaises(RuntimeError):
            self.move(robot, require_visual_target=True, refresh_moving_visual_target=lambda: None)
        robot.pick_at.assert_not_called()
        self.move(robot, require_visual_target=False)
        robot.pick_at.assert_called_once_with(2, 3, visual_target=None)
        robot.place_at.assert_called_once_with(4, 3)

    def test_refresh_is_resolved_before_connect_for_non_capture(self):
        robot = self.robot()
        robot.connected, robot.dry = False, False
        with self.assertRaises(RuntimeError):
            self.move(robot, require_visual_target=True, refresh_moving_visual_target=lambda: None)
        robot.connect.assert_not_called()
        robot.pick_at.assert_not_called()


class FreshPickSnapshotTests(unittest.TestCase):
    def monitor(self):
        monitor = CameraMonitor.__new__(CameraMonitor)
        monitor.cap = Mock()
        monitor.cap.isOpened.return_value = True
        self.frame = np.full((50, 60, 3), (10, 20, 30), dtype=np.uint8)
        monitor.cap.read.return_value = (True, self.frame)
        monitor._cam_lock, monitor._lock = threading.Lock(), threading.Lock()
        monitor.model = object()
        monitor.cchess_recognizer = Mock()
        monitor._inv_M = np.eye(3)
        monitor._filter_by_board = Mock(return_value=[])
        box = SimpleNamespace(cls=[0], conf=[.912], xyxy=[[1.25, 2.5, 15.75, 22.125]])
        monitor._predict_yolo = Mock(return_value=[SimpleNamespace(boxes=[box])])
        return monitor

    def test_float_boxes_exact_frame_no_board_foot_filter_or_synthetic_cchess(self):
        monitor = self.monitor()
        frame, detections = monitor.get_fresh_pick_snapshot()
        self.assertIs(frame, self.frame)
        self.assertEqual(detections, [(0, .912, (1.25, 2.5, 15.75, 22.125))])
        monitor._filter_by_board.assert_not_called()
        monitor.cchess_recognizer.extract_rectified_board.assert_not_called()
        self.assertIs(monitor._predict_yolo.call_args.args[0], self.frame)
        np.testing.assert_array_equal(monitor._predict_yolo.call_args.args[0], self.frame)
        self.assertEqual(monitor.cap.grab.call_count, 5)

    def test_inference_read_or_model_failure_is_not_empty_detection(self):
        for failure in ('inference', 'read', 'model', 'unavailable'):
            monitor = self.monitor()
            if failure == 'inference':
                monitor._predict_yolo.side_effect = RuntimeError('bad network')
            elif failure == 'read':
                monitor.cap.read.return_value = (False, None)
            elif failure == 'model':
                monitor.model = None
            else:
                monitor.cap.isOpened.return_value = False
            with self.subTest(failure=failure), self.assertRaises(RuntimeError):
                monitor.get_fresh_pick_snapshot()
        monitor = self.monitor()
        monitor._predict_yolo.return_value = [SimpleNamespace(boxes=[])]
        self.assertEqual(monitor.get_fresh_pick_snapshot()[1], [])

    def test_frozen_diagnostic_survives_long_motion_until_first_actual_display(self):
        monitor = CameraMonitor.__new__(CameraMonitor)
        monitor._lock = threading.Lock()
        monitor._inv_M = None
        monitor._last_cchess_result = None
        monitor.device = 'cpu'
        measured = np.full((50, 60, 3), (10, 20, 30), np.uint8)
        original = measured.copy()
        live = np.full((50, 60, 3), (40, 50, 60), np.uint8)
        with patch('src.vision.camera_monitor.time.monotonic', return_value=100.) as timer:
            monitor.publish_pick_diagnostic(measured)
            self.assertEqual(monitor._pick_diagnostic_until, 0.)
            timer.assert_not_called()
            # The robot's blocking SDK calls consumed 100s, far longer than
            # the 8s visibility interval. It must still show the measured frame.
            timer.return_value = 200.
            display = monitor._draw_overlay(live, [])
            np.testing.assert_array_equal(display, original)
            self.assertEqual(monitor._pick_diagnostic_until, 208.)
            self.assertIsNot(display, measured)
            display[0, 0] = 0
            np.testing.assert_array_equal(measured, original)
            np.testing.assert_array_equal(monitor._last_pick_diagnostic, original)
            timer.return_value = 207.
            np.testing.assert_array_equal(monitor._draw_overlay(live, []), original)
            timer.return_value = 209.
            np.testing.assert_array_equal(monitor._draw_overlay(live, []), live)
            self.assertIsNone(monitor._last_pick_diagnostic)
            np.testing.assert_array_equal(measured, original)


class HardwareTopModeTests(unittest.TestCase):
    def hardware(self):
        hw = HardwareManager.__new__(HardwareManager)
        hw.config = SimpleNamespace(VISUAL_TOP_FACE_ENABLED=True, VISUAL_CENTER_PICK_ATTEMPTS=3,
            VISUAL_PICK_MIN_STABLE_SAMPLES=2, VISUAL_CENTER_PICK_MAX_JITTER_CELLS=.12,
            VISUAL_BOARD_WIDTH_MM=250., VISUAL_BOARD_HEIGHT_MM=281.25,
            VISUAL_PIECE_HEIGHT_MM=10., VISUAL_GEOMETRY_CORNER_TOLERANCE_PX=4.,
            VISUAL_OCCUPANCY_CELL_HALF_WIDTH=.5)
        hw.actual_camera_index = 1
        hw.perspective_path = 'unused.npy'
        hw.cam_monitor = Mock()
        hw.cam_monitor.get_fresh_pick_snapshot.return_value = (np.zeros((960, 1280, 3), np.uint8), [])
        hw.top_face_pick_estimator = Mock()
        hw.top_face_pick_estimator.geometry.profile_id = 'synthetic'
        hw.top_face_pick_estimator.aggregate_targets = VisualPickEstimator.aggregate_targets
        hw.top_face_pick_estimator.last_reason = 'synthetic'
        hw.get_visual_pick_targets = Mock()
        hw.center_pick_estimator = Mock()
        return hw

    def test_missing_profile_or_bad_top_never_uses_foot_fallback(self):
        for missing in (False, True):
            hw = self.hardware()
            if missing:
                hw.top_face_pick_estimator = None
            else:
                hw.top_face_pick_estimator.estimate_pick_target.return_value = None
            with patch('src.hardware.hardware_manager.np.load', return_value=np.eye(3)):
                self.assertEqual(hw.get_robot_center_pick_targets({'moving': (2, 3)}), {'moving': None})
            hw.get_visual_pick_targets.assert_not_called()

    def test_stable_top_targets_and_geometry_failure_blocks_move(self):
        hw = self.hardware()
        target = GridTarget(2.1, 3.03, .9, .11)
        hw.top_face_pick_estimator.estimate_pick_target.return_value = target
        with patch('src.hardware.hardware_manager.np.load', return_value=np.eye(3)):
            self.assertEqual(hw.get_robot_center_pick_targets({'moving': (2, 3)})['moving'], target)
            hw.top_face_pick_estimator.geometry.validate_context.side_effect = ValueError('camera moved')
            self.assertIsNone(hw.get_robot_center_pick_targets({'moving': (2, 3)})['moving'])
        hw.get_visual_pick_targets.assert_not_called()

    def test_occupancy_uses_boxes_even_when_no_top_face_is_available(self):
        hw = self.hardware()
        hw.top_face_pick_estimator = None
        hw.center_pick_estimator.has_detection_in_cell.return_value = True
        self.assertFalse(hw.is_cell_visually_clear((4, 3)))
        hw.center_pick_estimator.has_detection_in_cell.assert_called()
        hw.cam_monitor.get_fresh_snapshot.assert_not_called()
        hw.center_pick_estimator.has_detection_in_cell.return_value = False
        self.assertTrue(hw.is_cell_visually_clear((4, 3)))
        hw.cam_monitor.get_fresh_pick_snapshot.side_effect = RuntimeError('inference failed')
        self.assertFalse(hw.is_cell_visually_clear((4, 3)))


class CommissioningLauncherTests(unittest.TestCase):
    def test_help_never_opens_camera_and_script_has_no_hardware_imports(self):
        script = Path(__file__).resolve().parents[1]/'scripts/calibrate_pick_geometry.py'
        source = script.read_text(encoding='utf-8')
        imports = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom):
                imports.append(node.module or '')
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
        self.assertFalse(any('hardware' in module or 'robot' in module.lower() or
                             'fairino' in module.lower() for module in imports))
        with patch.object(sys, 'argv', [str(script), '--help']), \
                patch('cv2.VideoCapture') as camera, contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaises(SystemExit) as raised:
            runpy.run_path(str(script), run_name='__main__')
        self.assertEqual(raised.exception.code, 0)
        camera.assert_not_called()


if __name__ == '__main__':
    unittest.main()
