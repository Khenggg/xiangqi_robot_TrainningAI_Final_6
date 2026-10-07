"""Synthetic camera projections check metric recovery, including moved cameras."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np

from src.vision.pick_geometry import BOARD_CORNERS
from src.vision.height_pick_geometry import geometry_from_board, HeightPickEstimator
from src.hardware.hardware_manager import HardwareManager


class HeightGeometryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.k = np.array([[850., 0, 640], [0, 850, 480], [0, 0, 1]])
        self.dist = np.array([-.12, .025, .001, -.002, 0.])
        self.path = self.root / 'intrinsics.json'
        self.path.write_text(json.dumps({"schema": 1, "camera_matrix": self.k.tolist(),
            "distortion": self.dist.tolist(), "camera_index": 1, "frame_size": [1280, 960]}))
        self.rvec = np.array([.20, -.12, .03])
        self.tvec = np.array([-180., -205., 950.])

    def perspective(self, rvec=None, tvec=None):
        world = np.column_stack((BOARD_CORNERS * [366/8, 410/9], np.zeros(4)))
        pixels = cv2.projectPoints(world, self.rvec if rvec is None else rvec,
                                  self.tvec if tvec is None else tvec, self.k, self.dist)[0].reshape(4, 2)
        return cv2.getPerspectiveTransform(pixels.astype(np.float32), BOARD_CORNERS.astype(np.float32))

    def geometry(self, matrix=None, **kwargs):
        params = dict(camera_index=1, frame_size=(1280, 960), board_mm=(366, 410), piece_height_mm=12.)
        params.update(kwargs)
        return geometry_from_board(self.path, self.perspective() if matrix is None else matrix, **params)

    def test_top_points_recover_actual_position_not_board_plane_projection(self):
        geometry = self.geometry()
        # Independent ground truth points are displaced from logical intersections.
        cells = np.array([[.12, .16], [7.86, 8.83], [5.86, 5.91], [3.9, 4.55]])
        world = np.column_stack((cells * [366/8, 410/9], np.full(4, geometry.top_z)))
        pixels = cv2.projectPoints(world, self.rvec, self.tvec, self.k, self.dist)[0].reshape(4, 2)
        np.testing.assert_allclose(geometry.xy_to_grid(geometry.pixels_to_top_xy(pixels)), cells, atol=1e-5)
        estimator = HeightPickEstimator(geometry)
        u, v = pixels[2]
        target = estimator.estimate_pick_target([(0, .95, (u-12, v-12, u+12, v+12))], 6, 6)
        self.assertIsNotNone(target)
        np.testing.assert_allclose([target.col, target.row], cells[2], atol=1e-5)
        board_estimate = cv2.perspectiveTransform(pixels.astype(np.float32).reshape(1, -1, 2), self.perspective())[0]
        self.assertGreater(np.max(np.linalg.norm(board_estimate-cells, axis=1)), .02)

    def test_recalibrating_board_updates_camera_pose(self):
        old = self.geometry()
        matrix = self.perspective(np.array([-.2, .14, -.1]), np.array([-160., -210., 870.]))
        new = self.geometry(matrix)
        self.assertGreater(np.linalg.norm(old.camera_center-new.camera_center), 10)
        cells = np.array([[1.2, 7.8]])
        np.testing.assert_allclose(new.xy_to_grid(new.pixels_to_top_xy(new.project(new.grid_to_xy(cells)))), cells)

    def test_rejects_missing_height_wrong_camera_resolution_and_singular_board(self):
        for kwargs in ({'piece_height_mm': None}, {'piece_height_mm': -1},
                       {'camera_index': 2}, {'frame_size': (640, 480)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.geometry(**kwargs)
        with self.assertRaises(np.linalg.LinAlgError):
            self.geometry(np.zeros((3, 3)))

    def manager(self):
        manager = HardwareManager.__new__(HardwareManager)
        manager.config = SimpleNamespace(VISUAL_HEIGHT_PICK_ENABLED=True, VISUAL_TOP_FACE_ENABLED=False,
            VISUAL_CENTER_PICK_ATTEMPTS=3, VISUAL_CAMERA_INTRINSICS_PATH='intrinsics.json',
            VISUAL_HEIGHT_BOARD_MM=(366, 410), VISUAL_HEIGHT_PIECE_MM=12.,
            VISUAL_HEIGHT_POSE_MAX_ERROR_PX=3., VISUAL_PICK_MIN_CONFIDENCE=.45,
            VISUAL_PICK_MAX_OFFSET_CELLS=.25, VISUAL_PICK_MIN_STABLE_SAMPLES=2,
            VISUAL_CENTER_PICK_MAX_JITTER_CELLS=.12)
        manager.config.VISUAL_HEIGHT_SAMPLE_WINDOW_SEC = .3
        manager.project_dir = self.root
        manager.perspective_path = self.root / 'perspective.npy'
        np.save(manager.perspective_path, self.perspective())
        manager.actual_camera_index = 1
        manager.cam_monitor = Mock()
        from contextlib import nullcontext
        manager.cam_monitor.pick_scan_session = nullcontext
        return manager

    def test_manager_uses_raw_bbox_and_never_foot_fallback(self):
        manager = self.manager()
        geometry = self.geometry()
        u, v = geometry.project(geometry.grid_to_xy([[5.9, 5.92]]))[0]
        manager.cam_monitor.get_fresh_pick_snapshot.return_value = (
            np.zeros((960, 1280, 3), np.uint8), [(0, .9, (u-10, v-10, u+10, v+10))])
        manager.get_visual_pick_targets = Mock(side_effect=AssertionError('must not use foot point'))
        with contextlib.redirect_stdout(io.StringIO()):
            result = manager.get_robot_center_pick_targets({'moving': (6, 6)})
        np.testing.assert_allclose([result['moving'].col, result['moving'].row], [5.9, 5.92])
        manager.cam_monitor.get_fresh_snapshot.assert_not_called()
        manager.config.VISUAL_HEIGHT_PIECE_MM = None
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(manager.get_robot_center_pick_targets({'moving': (6, 6)})['moving'])
        self.assertEqual(manager.last_height_pick_resolution['mode'], 'blocked')
        self.assertIn('Measure', manager.last_height_pick_resolution['reason'])

    def test_height_test_mode_never_commands_logical_pick_when_target_missing(self):
        manager = self.manager()
        manager.robot = Mock(connected=True)
        manager.center_pick_estimator = object()
        manager.is_cell_visually_clear = Mock(return_value=True)
        manager.get_robot_center_pick_targets = Mock(return_value={'moving': None})
        manager.last_pick_resolution = {'failure': 'consensus', 'reason': 'Unstable bbox'}
        from src.vision.pick_consensus import PickTargetUnavailable
        with self.assertRaises(PickTargetUnavailable):
            manager.execute_pick_place_test((6, 6), (6, 5))
        manager.robot.move_piece.assert_not_called()

    def test_unstable_bbox_falls_back_and_transient_snapshot_can_retry(self):
        from src.vision.pick_consensus import FreshPickTransientError
        manager = self.manager()
        geometry = self.geometry()
        frame = np.zeros((960, 1280, 3), np.uint8)
        def snapshot(cell):
            u, v = geometry.project(geometry.grid_to_xy([cell]))[0]
            return frame, [(0, .9, (u-10, v-10, u+10, v+10))]
        import itertools
        manager.cam_monitor.get_fresh_pick_snapshot.side_effect = itertools.chain(
            [FreshPickTransientError('temporary')], itertools.repeat(snapshot((6, 6))))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNotNone(manager.get_robot_center_pick_targets({'moving': (6, 6)})['moving'])
        manager.cam_monitor.get_fresh_pick_snapshot.side_effect = itertools.chain(
            [snapshot((5.8, 6)), snapshot((6.2, 6))], itertools.repeat((frame, [])))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(manager.get_robot_center_pick_targets({'moving': (6, 6)})['moving'])

    def test_continuous_calls_use_full_window_and_exclude_late_results(self):
        for inference_sec, expected_calls in ((.5, 8), (4., 1)):
            manager = self.manager()
            manager.config.VISUAL_HEIGHT_SAMPLE_WINDOW_SEC = 3.6
            clock = [0.]
            call_times = []
            geometry = self.geometry()
            u, v = geometry.project(geometry.grid_to_xy([[6, 6]]))[0]
            def snapshot():
                call_times.append(clock[0])
                clock[0] += inference_sec
                return np.zeros((960, 1280, 3), np.uint8), [(0, .9, (u-10, v-10, u+10, v+10))]
            def sleep(seconds):
                clock[0] += seconds
            manager.cam_monitor.get_fresh_pick_snapshot.side_effect = snapshot
            with patch('src.hardware.hardware_manager.time.monotonic', side_effect=lambda: clock[0]), \
                    patch('src.hardware.hardware_manager.time.sleep', side_effect=sleep), \
                    contextlib.redirect_stdout(io.StringIO()):
                result = manager.get_robot_center_pick_targets({'moving': (6, 6)})['moving']
            self.assertEqual(len(call_times), expected_calls)
            if expected_calls == 8:
                np.testing.assert_allclose(call_times, np.arange(8) * .5)
                self.assertEqual(manager.last_height_pick_resolution["valid_samples"]["moving"], 7)
                self.assertIsNotNone(result)
            else:
                self.assertIsNone(result)
                self.assertEqual(manager.last_height_pick_resolution['valid_samples']['moving'], 0)


if __name__ == '__main__':
    unittest.main()
