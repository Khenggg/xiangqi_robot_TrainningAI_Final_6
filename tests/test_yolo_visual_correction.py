import time
import unittest
from types import SimpleNamespace

import numpy as np

from src.hardware.hardware_manager import HardwareManager
from src.vision.qr_calibration import Calibration
from src.vision.visual_correction import VisualTarget
from src.vision.yolo_visual_correction import YoloPieceCorrector


def calibration():
    # One grid interval is 100 image pixels in this synthetic camera frame.
    camera_to_grid = np.array([[.01, 0, 0], [0, .01, 0], [0, 0, 1]], dtype=float)
    return Calibration(camera_to_grid, np.linalg.inv(camera_to_grid),
                       np.zeros((4, 2)), time.monotonic(), 7, (1000, 900))


def box(class_id, confidence, xyxy):
    return SimpleNamespace(cls=np.array([class_id]), conf=np.array([confidence]),
                           xyxy=np.array([xyxy], dtype=float))


class FakeYOLO:
    names = {0: "piece", 1: "hand"}

    def __init__(self, boxes):
        self.boxes = boxes
        self.calls = []

    def predict(self, frame, **kwargs):
        self.calls.append((frame, kwargs))
        return [SimpleNamespace(boxes=self.boxes)]


class YoloVisualCorrectionTests(unittest.TestCase):
    def test_maps_box_centres_to_grid_and_ignores_other_classes(self):
        model = FakeYOLO([box(0, .90, [390, 380, 410, 420]), box(1, .99, [0, 0, 900, 900])])
        corrector = YoloPieceCorrector(model=model, confidence=.40, imgsz=640, max_offset_cells=.34)
        candidates = corrector.detect(np.zeros((900, 1000, 3), np.uint8), calibration())
        self.assertEqual(candidates, [(4.0, 4.0, .9)])
        self.assertEqual(model.calls[0][1]["imgsz"], 640)

    def test_selects_only_a_nearby_expected_piece(self):
        corrector = YoloPieceCorrector(model=FakeYOLO([]), max_offset_cells=.34)
        cal = calibration()
        target = corrector.target_for([(4.18, 3.91, .88), (5.0, 4.0, .99)], cal, 4, 4)
        self.assertIsNotNone(target)
        self.assertAlmostEqual(target.col, 4.18)
        self.assertAlmostEqual(target.row, 3.91)
        self.assertEqual(target.generation, 7)
        self.assertIsNone(corrector.target_for([(4.5, 4.0, .99)], cal, 4, 4))

    def test_rejects_model_without_piece_class(self):
        model = SimpleNamespace(names={0: "board"})
        with self.assertRaises(ValueError):
            YoloPieceCorrector(model=model)

    def test_fusion_refines_agreeing_measurements_and_rejects_conflict(self):
        yolo = VisualTarget(4.16, 3.98, .9, .16, 0, 7, 1)
        circle = VisualTarget(4.10, 4.03, .8, .10, .4, 7, 1)
        fused = HardwareManager._fuse_visual_targets(yolo, circle, 4, 4)
        self.assertIsNotNone(fused)
        self.assertAlmostEqual(fused.offset_cells,
                               np.hypot(fused.col - 4, fused.row - 4))
        far = VisualTarget(3.70, 4.0, .8, .3, .4, 7, 1)
        self.assertIsNone(HardwareManager._fuse_visual_targets(yolo, far, 4, 4))


if __name__ == "__main__":
    unittest.main()
