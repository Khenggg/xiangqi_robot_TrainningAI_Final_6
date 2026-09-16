import time
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from src.core import xiangqi
from src.vision.qr_calibration import BoardGeometry, QRCalibrator, CORNER_GRID, transform, qr_center
from src.vision.xiangqi_recognizer import XiangqiRecognizer, StableBoard, BoardObservation, infer_legal_move, LABELS
from src.hardware.board_robot_mapping import BoardRobotMapping


def geometry():
    return BoardGeometry.from_dict({"cell_mm": [40, 45], "markers": {
        "TL": {"id": "XQ:TL", "qr_to_corner_mm": [30, 25]},
        "TR": {"id": "XQ:TR", "qr_to_corner_mm": [-35, 20]},
        "BR": {"id": "XQ:BR", "qr_to_corner_mm": [-25, -30]},
        "BL": {"id": "XQ:BL", "qr_to_corner_mm": [20, -35]},
    }})


BASE = np.array([[50, 0, 150], [0, 48, 130], [0, 0, 1]], dtype=float)


def centres(matrix=BASE):
    g = geometry()
    return dict(zip(g.marker_ids, transform(g.marker_grid, matrix)))


def calibration(matrix=BASE, stamp=None):
    return QRCalibrator(geometry(), stable_frames=1).update_centres(
        centres(matrix), (900, 1000), time.monotonic() if stamp is None else stamp)


class CalibrationTests(unittest.TestCase):
    def test_offsets_under_translation_rotation_and_perspective(self):
        for degrees in (0, 15, 90, 180, 270):
            a = np.deg2rad(degrees)
            rotation = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
            shift = np.array([[1, 0, 500], [0, 1, 450], [0, 0, 1]])
            scale = np.array([[38, 0, -152], [0, 39, -175.5], [.0005, -.0003, 1]])
            matrix = shift @ rotation @ scale
            cal = calibration(matrix)
            self.assertIsNotNone(cal)
            np.testing.assert_allclose(cal.corners_px, transform(CORNER_GRID, matrix), atol=.002)
            grid = np.array([[c, r] for r in range(10) for c in range(9)])
            np.testing.assert_allclose(transform(transform(grid, matrix), cal.camera_to_grid), grid, atol=.0001)

    def test_projective_qr_centre_is_diagonal_intersection(self):
        matrix = np.array([[100, 4, 30], [2, 90, 50], [.15, .07, 1]])
        quad = transform([[0, 0], [1, 0], [1, 1], [0, 1]], matrix)
        np.testing.assert_allclose(qr_center(quad), transform([[.5, .5]], matrix)[0])

    def test_stability_loss_and_reacquisition(self):
        tracker = QRCalibrator(geometry(), stable_frames=3)
        self.assertIsNone(tracker.update_centres(centres(), (900, 1000), 0))
        self.assertIsNone(tracker.update_centres(centres(), (900, 1000), .1))
        old = tracker.update_centres(centres(), (900, 1000), .2)
        self.assertIsNotNone(old)
        moved = BASE.copy(); moved[0, 2] += 35
        self.assertIsNone(tracker.update_centres(centres(moved), (900, 1000), .3))
        tracker.update_centres(centres(moved), (900, 1000), .4)
        new = tracker.update_centres(centres(moved), (900, 1000), .5)
        self.assertGreater(new.generation, old.generation)
        partial = centres(moved); partial.pop("XQ:TL")
        self.assertIsNone(tracker.update_centres(partial, (900, 1000), .6))
        with self.assertRaises(RuntimeError):
            tracker.require_current(.7)

    def test_stale_and_mirrored(self):
        tracker = QRCalibrator(geometry(), stable_frames=1)
        tracker.update_centres(centres(), (900, 1000), 1)
        with self.assertRaises(RuntimeError):
            tracker.require_current(4)
        mirrored = {name: [1000 - x, y] for name, (x, y) in centres().items()}
        self.assertIsNone(tracker.update_centres(mirrored, (900, 1000), 5))

    def test_real_qr_decode_from_generated_image(self):
        image = np.full((900, 1000, 3), 255, np.uint8)
        encoder = cv2.QRCodeEncoder_create()
        for name, (x, y) in centres().items():
            code = encoder.encode(name)
            code = cv2.copyMakeBorder(code, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
            code = cv2.resize(code, (100, 100), interpolation=cv2.INTER_NEAREST)
            x, y = round(x), round(y)
            image[y-50:y+50, x-50:x+50] = cv2.cvtColor(code, cv2.COLOR_GRAY2BGR)
        cal = QRCalibrator(geometry(), stable_frames=1).update(image)
        self.assertIsNotNone(cal)
        np.testing.assert_allclose(cal.corners_px, transform(CORNER_GRID, BASE), atol=2)

    def test_unmeasured_layout_rejected(self):
        with self.assertRaises(ValueError):
            BoardGeometry.from_dict({"cell_mm": [None, None]})


class RecognitionTests(unittest.TestCase):
    def fake_recognizer(self, scores):
        self.input_tensor = None
        def run(_outputs, inputs):
            self.input_tensor = inputs["input"]
            return [scores]
        return XiangqiRecognizer("unused", session=SimpleNamespace(
            get_inputs=lambda: [SimpleNamespace(name="input")], run=run))

    def test_mapping_preprocessing_unknown_and_low_confidence(self):
        scores = np.zeros((1, 90, 16), np.float32); scores[:, :, 0] = 1
        scores[0, 0] = 0; scores[0, 0, LABELS.index("B")] = 1
        model = self.fake_recognizer(scores)
        frame = np.zeros((900, 1000, 3), np.uint8); frame[:] = [10, 20, 30]
        obs = model.predict(frame, calibration())
        self.assertEqual(obs.board[0][0], "r_E")
        self.assertEqual(self.input_tensor.shape, (1, 3, 315, 280))
        np.testing.assert_allclose(self.input_tensor[0, :, 120, 120],
                                   (np.array([30, 20, 10]) - [123.675, 116.28, 103.53]) / [58.395, 57.12, 57.375], rtol=1e-6)
        self.assertTrue(obs.certain)
        scores[0, 0] = 0; scores[0, 0, 1] = 1
        unknown = model.predict(frame, calibration())
        self.assertEqual(unknown.board[0][0], "?")
        with self.assertRaises(ValueError):
            unknown.fen()
        scores[0, 0] = 0; scores[0, 0, 2:4] = [.6, .4]
        self.assertFalse(model.predict(frame, calibration()).certain)

    def test_bad_model_contract(self):
        model = self.fake_recognizer(np.zeros((1, 90, 15), np.float32))
        with self.assertRaises(ValueError):
            model.predict(np.zeros((900, 1000, 3), np.uint8), calibration())

    def test_stable_board_requires_distinct_frames_and_resets(self):
        obs = BoardObservation(xiangqi.get_board(), np.ones((10, 9)), True, 1, 1)
        stable = StableBoard(3)
        self.assertIsNone(stable.update(obs))
        self.assertIsNone(stable.update(obs))
        self.assertIsNone(stable.update(replace(obs, timestamp=2)))
        self.assertIsNotNone(stable.update(replace(obs, timestamp=3)))
        self.assertIsNone(stable.update(replace(obs, timestamp=4, generation=2)))
        self.assertIsNone(stable.update(replace(obs, timestamp=5, certain=False)))

    def test_legal_move_capture_and_mismatch(self):
        board = xiangqi.get_board()
        after, _ = xiangqi.make_temp_move(board, ((0, 6), (0, 5)))
        self.assertEqual(infer_legal_move(board, after), ((0, 6), (0, 5), "r_P"))
        after[0][0] = "."
        self.assertIsNone(infer_legal_move(board, after))
        # Cannon captures a knight with exactly one intervening cannon.
        captured, _ = xiangqi.make_temp_move(board, ((1, 7), (1, 0)))
        self.assertEqual(infer_legal_move(board, captured), ((1, 7), (1, 0), "r_C"))
        illegal, _ = xiangqi.make_temp_move(board, ((0, 6), (0, 4)))
        self.assertIsNone(infer_legal_move(board, illegal))


class RobotMappingTests(unittest.TestCase):
    def setUp(self):
        self.cal = calibration()
        self.mapping = BoardRobotMapping({
            "camera_points_px": transform(CORNER_GRID, BASE).tolist(),
            "robot_points_xy_mm": [[100, 200], [420, 200], [420, 605], [100, 605]],
            "frame_size": [1000, 900], "xy_limits_mm": [[0, 800], [0, 800]],
        }, lambda: self.cal)

    def test_moved_board_updates_real_xy_not_old_teaching_points(self):
        self.mapping.begin()
        np.testing.assert_allclose(self.mapping.xy(4, 4), [260, 380], atol=.001)
        self.mapping.end()
        matrix = BASE.copy(); matrix[0, 2] += 25
        self.cal = calibration(matrix)
        self.mapping.begin()
        np.testing.assert_allclose(self.mapping.xy(4, 4), [280, 380], atol=.001)

    def test_motion_rejects_changed_board_and_limits(self):
        self.mapping.begin()
        matrix = BASE.copy(); matrix[0, 2] += 25
        self.cal = calibration(matrix)
        with self.assertRaises(RuntimeError):
            self.mapping.xy(4, 4)
        self.mapping.end()
        self.mapping.bounds = np.array([[0, 10], [0, 10]])
        with self.assertRaises(RuntimeError):
            self.mapping.begin()
        self.assertIsNone(self.mapping.frozen)

    def test_reference_resolution_mismatch(self):
        self.cal = replace(self.cal, frame_size=(1280, 720))
        with self.assertRaises(RuntimeError):
            self.mapping.begin()

    def test_fr5_uses_qr_mapping_even_at_old_teaching_corners(self):
        from src.hardware.robot_VIP import FR5Robot
        robot = FR5Robot()
        robot.board_mapping = self.mapping
        robot.teaching_points = {"R2": {"pose": [999, 999, 0, 0, 0, 0]}}
        self.mapping.begin()
        pose = robot.board_to_pose(8, 0, 100, [10, 20, 30])
        np.testing.assert_allclose(pose, [420, 200, 100, 10, 20, 30], atol=.001)
        self.mapping.end()

    def test_fr5_fault_does_not_retry_or_use_legacy_fallback(self):
        from src.hardware.robot_VIP import FR5Robot
        robot = FR5Robot()
        robot.board_mapping = self.mapping
        with patch.object(robot, "_move_piece_impl", side_effect=RuntimeError("blocked")) as motion:
            with self.assertRaisesRegex(RuntimeError, "blocked"):
                robot.move_piece(0, 0, 0, 1, False)
            self.assertEqual(motion.call_count, 1)
        self.assertIsNone(self.mapping.frozen)

    def test_fr5_guard_prevents_dispatch_after_board_moves(self):
        from src.hardware.robot_VIP import FR5Robot
        robot = FR5Robot()
        robot.dry = False
        robot.robot = Mock()
        robot.board_mapping = self.mapping
        self.mapping.begin()
        matrix = BASE.copy(); matrix[0, 2] += 25
        self.cal = calibration(matrix)
        with self.assertRaises(RuntimeError):
            robot.move_safe_pose([0, 0, 100, 0, 0, 0])
        with self.assertRaises(RuntimeError):
            robot.gripper_ctrl(1)
        robot.robot.MoveCart.assert_not_called()
        robot.robot.SetToolDO.assert_not_called()

    def test_frame_or_qr_loss_prevents_robot_coordinates(self):
        self.mapping.begin()
        self.mapping.provider = Mock(side_effect=RuntimeError("QR missing"))
        with self.assertRaisesRegex(RuntimeError, "QR missing"):
            self.mapping.xy(1, 1)


if __name__ == "__main__":
    unittest.main()
