"""Camera gameplay and physical occupancy regressions; no real devices."""
import threading
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import cv2
import config
from src.vision.camera_monitor import CameraMonitor
from src.vision.visual_pick_estimator import VisualPickEstimator
from src.hardware.hardware_manager import HardwareManager
from src.core.visual_move_coordinator import execute_pending_ai_motion
from src.core.game_state import GameState
from src.core import xiangqi
from src.vision.pick_geometry import BOARD_CORNERS


class CameraRecoveryTests(unittest.TestCase):
    def monitor(self):
        monitor = CameraMonitor.__new__(CameraMonitor)
        monitor._lock = threading.Lock()
        monitor._cam_lock = threading.Lock()
        monitor._last_pick_diagnostic = None
        monitor._pick_diagnostic_until = 0.
        monitor._last_detections = []
        monitor._last_cchess_result = None
        monitor._inv_M = None
        monitor._board_polygon = None
        monitor.cchess_recognizer = None
        monitor.model = None
        monitor.device = 'cpu'
        monitor.window_name = 'mock camera'
        monitor.cap = Mock()
        monitor.cap.isOpened.return_value = True
        return monitor

    def test_gameplay_display_keeps_live_frames_during_measured_diagnostic(self):
        monitor = self.monitor()
        monitor.pick_debug_frame = np.full((480, 640, 3), 99, np.uint8)
        monitor.cap.read.side_effect = [(True, np.full((480, 640, 3), n, np.uint8)) for n in (25, 30)]
        pixels = []
        with patch('src.vision.camera_monitor.cv2.imshow', side_effect=lambda _, frame: pixels.append(int(frame[100, 100, 0]))), patch('src.vision.camera_monitor.cv2.waitKey', return_value=-1):
            for _ in range(2):
                monitor.get_fresh_snapshot()
                monitor.update_display()
        self.assertEqual(pixels, [25, 30])

    def test_legacy_diagnostic_assignment_expires_without_test_mode_key(self):
        monitor = self.monitor()
        monitor._last_frame = np.zeros((480, 640, 3), np.uint8)
        with patch('src.vision.camera_monitor.cv2.imshow'), patch('src.vision.camera_monitor.cv2.waitKey', return_value=-1), patch('src.vision.camera_monitor.time.monotonic', return_value=10.):
            monitor.pick_debug_frame = np.ones((480, 640, 3), np.uint8)
            monitor.update_display()
        with patch('src.vision.camera_monitor.cv2.imshow'), patch('src.vision.camera_monitor.cv2.waitKey', return_value=-1), patch('src.vision.camera_monitor.time.monotonic', return_value=19.):
            monitor.update_display()
        self.assertIsNone(monitor.pick_debug_frame)

    def hardware(self, folder):
        path = Path(folder) / 'perspective.npy'
        matrix = np.array([[.02, 0, -2], [0, .02, -2], [0, 0, 1]], np.float32)
        np.save(path, matrix)
        monitor = self.monitor()
        monitor._inv_M = np.linalg.inv(matrix)
        monitor.model = object()
        monitor.cap.read.return_value = (True, np.zeros((640, 640, 3), np.uint8))
        hw = HardwareManager.__new__(HardwareManager)
        hw.config = SimpleNamespace(**{k: getattr(config, k) for k in dir(config) if k.startswith('VISUAL_')})
        hw.config.VISUAL_HEIGHT_BOARD_MM = (400., 450.)
        hw.config.VISUAL_CAMERA_INTRINSICS_PATH = 'intrinsics.json'
        intrinsics = dict(schema=1, camera_index=0, frame_size=[640, 640],
                          camera_matrix=[[1000., 0, 0], [0, 1000., 0], [0, 0, 1]], distortion=[0.] * 5)
        (Path(folder) / 'intrinsics.json').write_text(json.dumps(intrinsics), encoding='utf-8')
        hw.project_dir = folder
        hw.perspective_path = path
        hw.actual_camera_index = 0
        hw.cam_monitor = monitor
        hw.center_pick_estimator = VisualPickEstimator(path, point_mode='center')
        return hw

    def test_inference_failure_cannot_confirm_cleared_capture_in_default_height_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            hw = self.hardware(tmp)
            hw.cam_monitor._predict_yolo = Mock(side_effect=RuntimeError('inference unavailable'))
            self.assertFalse(hw.is_cell_visually_clear((4, 4)))

    def test_successful_edge_move_survives_post_move_occupancy_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            hw = self.hardware(tmp)
            # Centre is (4,9); the legacy 85%-foot filter discards this box.
            box = SimpleNamespace(cls=[0], conf=[.99], xyxy=[np.array([280, 525, 320, 575])])
            hw.cam_monitor._predict_yolo = Mock(return_value=[SimpleNamespace(boxes=[box])])
            self.assertTrue(hw.verify_visual_move((4, 8), (4, 9)))

    def test_no_vision_does_not_authorize_empty_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            hw = self.hardware(tmp)
            hw.cam_monitor.model = None
            self.assertFalse(hw.is_cell_visually_clear((4, 4)))

    def test_malformed_confident_box_is_not_evidence_of_empty_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            hw = self.hardware(tmp)
            box = SimpleNamespace(cls=[0], conf=[.99], xyxy=[np.array([0., 0., float('nan'), 30.])])
            hw.cam_monitor._predict_yolo = Mock(return_value=[SimpleNamespace(boxes=[box])])
            self.assertFalse(hw.is_cell_visually_clear((4, 4)))

    def test_tilted_camera_occupancy_uses_piece_height_plane(self):
        with tempfile.TemporaryDirectory() as tmp:
            hw = self.hardware(tmp)
            k = np.array([[850., 0, 640], [0, 850., 480], [0, 0, 1]])
            rvec, tvec = np.array([1.15, 0., 0.]), np.array([-183., -205., 550.])
            world = np.column_stack((BOARD_CORNERS * [366 / 8, 410 / 9], np.zeros(4)))
            pixels = cv2.projectPoints(world, rvec, tvec, k, np.zeros(5))[0].reshape(4, 2)
            matrix = cv2.getPerspectiveTransform(pixels.astype(np.float32), BOARD_CORNERS.astype(np.float32))
            np.save(hw.perspective_path, matrix)
            hw.center_pick_estimator = VisualPickEstimator(hw.perspective_path, point_mode='center')
            hw.config.VISUAL_HEIGHT_BOARD_MM = (366., 410.)
            hw.config.VISUAL_HEIGHT_PIECE_MM = 12.
            intrinsics = dict(schema=1, camera_index=0, frame_size=[1280, 960],
                              camera_matrix=k.tolist(), distortion=[0.] * 5)
            (Path(tmp) / 'intrinsics.json').write_text(json.dumps(intrinsics), encoding='utf-8')
            # Top faces toward the camera lie at Z=-12, above the board plane.
            point = np.array([[4 * 366 / 8, 9 * 410 / 9, -12.]])
            u, v = cv2.projectPoints(point, rvec, tvec, k, np.zeros(5))[0].reshape(2)
            box = SimpleNamespace(cls=[0], conf=[.99], xyxy=[np.array([u - 8, v - 8, u + 8, v + 8])])
            hw.cam_monitor.cap.read.return_value = (True, np.zeros((960, 1280, 3), np.uint8))
            hw.cam_monitor._predict_yolo = Mock(return_value=[SimpleNamespace(boxes=[box])])
            detection = [(0, .99, tuple(box.xyxy[0]))]
            self.assertFalse(hw.center_pick_estimator.has_detection_in_cell(detection, 4, 9))
            self.assertFalse(hw.is_cell_visually_clear((4, 9)))
            self.assertTrue(hw.verify_visual_move((4, 8), (4, 9)))

    def test_first_ai_motion_can_verify_then_commit_while_display_stays_live(self):
        with tempfile.TemporaryDirectory() as tmp:
            hw = self.hardware(tmp)
            state = GameState()
            state.api_client = Mock()
            state.process_human_move((0, 6), (0, 5), 'r_P')
            move = ((0, 3), (0, 4))
            expected, _ = xiangqi.make_temp_move(state.board, move)
            state.set_pending_ai_move(move, expected, '.')
            hw.get_robot_center_pick_targets = Mock(return_value={'moving': SimpleNamespace(col=0., row=3.)})
            hw.robot = Mock(connected=True)
            box = SimpleNamespace(cls=[0], conf=[.99], xyxy=[np.array([80, 280, 120, 320])])
            hw.cam_monitor._predict_yolo = Mock(return_value=[SimpleNamespace(boxes=[box])])
            hw.cam_monitor.pick_debug_frame = np.full((640, 640, 3), 99, np.uint8)
            execute_pending_ai_motion(state, hw, config)
            self.assertTrue(state.commit_pending_ai_move())
            self.assertEqual(state.board, expected)
            self.assertEqual(state.turn, 'r')
            hw.robot.move_piece.assert_called_once()
            with patch('src.vision.camera_monitor.cv2.imshow') as display, patch('src.vision.camera_monitor.cv2.waitKey', return_value=-1):
                hw.cam_monitor.update_display()
                self.assertEqual(int(display.call_args.args[1][100, 100, 0]), 0)


if __name__ == '__main__':
    unittest.main()
