"""Use a trained YOLO piece detector as the primary real-piece localizer."""
import math
from pathlib import Path

import numpy as np

from src.vision.qr_calibration import transform
from src.vision.visual_correction import VisualTarget


class YoloPieceCorrector:
    """Map one-class/multi-class YOLO boxes into continuous Xiangqi grid space."""

    def __init__(self, model_path=None, *, model=None, confidence=.45, imgsz=640,
                 max_offset_cells=.34, piece_class_names=("piece",)):
        if not 0 < confidence <= 1 or imgsz < 160 or not 0 < max_offset_cells < .5:
            raise ValueError("Invalid YOLO visual-correction settings")
        if model is None:
            if not Path(model_path).is_file():
                raise FileNotFoundError(f"Missing YOLO piece model: {model_path}")
            try:
                from ultralytics import YOLO
            except ImportError as exc:
                raise RuntimeError("Install ultralytics to use YOLO visual correction") from exc
            model = YOLO(str(model_path))
        self.model = model
        self.confidence = float(confidence)
        self.imgsz = int(imgsz)
        self.max_offset = float(max_offset_cells)
        names = getattr(model, "names", {})
        names = names.values() if isinstance(names, dict) else names
        self.piece_class_names = {str(name) for name in piece_class_names}
        self.class_ids = {index for index, name in enumerate(names) if str(name) in self.piece_class_names}
        if not self.class_ids:
            raise ValueError(f"YOLO model has no piece class among {sorted(self.piece_class_names)}")

    def detect(self, frame, calibration):
        """Run one YOLO inference and return safe candidates in board coordinates."""
        result = self.model.predict(frame, conf=self.confidence, imgsz=self.imgsz, verbose=False)[0]
        candidates = []
        boxes = getattr(result, "boxes", None)
        for box in (() if boxes is None else boxes):
            class_id = int(float(box.cls[0]))
            if class_id not in self.class_ids:
                continue
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            if x2 <= x1 or y2 <= y1 or not np.isfinite([x1, y1, x2, y2, confidence]).all():
                continue
            col, row = transform([[(x1 + x2) / 2, (y1 + y2) / 2]], calibration.camera_to_grid)[0]
            if not (-.5 <= col <= 8.5 and -.5 <= row <= 9.5):
                continue
            candidates.append((float(col), float(row), confidence))
        return candidates

    def target_for(self, candidates, calibration, expected_col, expected_row):
        best = None
        for col, row, confidence in candidates:
            offset = math.hypot(col - expected_col, row - expected_row)
            if offset > self.max_offset:
                continue
            score = .70 * confidence + .30 * (1.0 - offset / self.max_offset)
            entry = (score, col, row, offset, confidence)
            if best is None or entry[0] > best[0]:
                best = entry
        if best is None:
            return None
        score, col, row, offset, _confidence = best
        return VisualTarget(col, row, score, offset, 0.0,
                            calibration.generation, calibration.timestamp)
