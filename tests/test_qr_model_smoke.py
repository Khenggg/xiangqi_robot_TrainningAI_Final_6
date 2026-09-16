"""Real upstream model + existing sample photo; no camera/robot calls."""
from pathlib import Path
import time
import unittest

import cv2
import numpy as np

from src.core import xiangqi
from src.vision.qr_calibration import Calibration, CORNER_GRID
from src.vision.xiangqi_recognizer import XiangqiRecognizer
from src.vision.visual_correction import VisualCorrector


class ModelSmokeTests(unittest.TestCase):
    def test_real_model_on_upstream_sample(self):
        root = Path(__file__).resolve().parents[1]
        photo = root.parent / "chinese-chess-recognition-main/assets/demo001.png"
        model_path = root / "models/cchess_nano_v3.onnx"
        if not photo.is_file() or not model_path.is_file():
            self.skipTest("Upstream sample/model not present")
        frame = cv2.imread(str(photo))
        # Manually identified outer intersections in the sample photo.
        # This tests model preprocessing, not automatic QR calibration accuracy.
        corners = np.float32([[486, 637], [552, 394], [864, 383], [899, 640]])
        matrix = cv2.getPerspectiveTransform(corners, CORNER_GRID)
        cal = Calibration(matrix, np.linalg.inv(matrix), corners, time.monotonic(), 1,
                          (frame.shape[1], frame.shape[0]))
        observation = XiangqiRecognizer(model_path).predict(frame, cal)
        self.assertEqual(observation.board, xiangqi.get_board())
        self.assertEqual(observation.confidence.shape, (10, 9))
        self.assertTrue(observation.certain)
        corrector = VisualCorrector()
        visual_targets = [
            corrector.locate(frame, cal, col, row)
            for row, values in enumerate(observation.board)
            for col, piece in enumerate(values)
            if piece != "."
        ]
        self.assertGreaterEqual(sum(target is not None for target in visual_targets), 30)


if __name__ == "__main__":
    unittest.main()
