"""ONNX adapter for TheOne1006/chinese-chess-recognition's 90x16 output."""
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from src.core import xiangqi
from src.core.fen_utils import board_array_to_fen
from src.vision.qr_calibration import warp_for_recognizer


LABELS = tuple(".xKABNRCPkabnrcp")


def internal_piece(label):
    if label == ".":
        return "."
    if label == "x":
        return "?"
    return ("r_" if label.isupper() else "b_") + ("E" if label.upper() == "B" else label.upper())


@dataclass(frozen=True)
class BoardObservation:
    board: list
    confidence: np.ndarray
    certain: bool
    timestamp: float
    generation: int

    def fen(self, turn="r"):
        if not self.certain:
            raise ValueError("Unknown/low-confidence cells cannot be converted into a trusted FEN")
        return board_array_to_fen(self.board, turn)


class XiangqiRecognizer:
    def __init__(self, model_path, min_confidence=0.80, session=None):
        if not 0 < min_confidence <= 1:
            raise ValueError("min_confidence must be in (0,1]")
        if session is None:
            import onnxruntime as ort
            if not Path(model_path).is_file():
                raise FileNotFoundError(f"Missing cchess ONNX weights: {model_path}")
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            session = ort.InferenceSession(str(model_path), sess_options=options,
                                           providers=["CPUExecutionProvider"])
        self.session = session
        self.input_name = session.get_inputs()[0].name
        self.min_confidence = min_confidence

    def predict(self, frame, calibration):
        image = cv2.resize(warp_for_recognizer(frame, calibration), (280, 315))
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB).astype(np.float32)
        normalized = (rgb - np.float32([123.675, 116.28, 103.53])) / np.float32([58.395, 57.12, 57.375])
        tensor = np.ascontiguousarray(normalized.transpose(2, 0, 1)[None])
        scores = np.asarray(self.session.run(None, {self.input_name: tensor})[0])
        if (scores.shape != (1, 90, 16) or not np.isfinite(scores).all()
                or (scores < 0).any() or (scores > 1).any()
                or not np.allclose(scores.sum(axis=-1), 1, atol=1e-3)):
            raise ValueError(f"Expected softmax probabilities [1,90,16], got {scores.shape}")
        indices = scores[0].argmax(axis=1)
        confidence = scores[0, np.arange(90), indices].reshape(10, 9)
        tokens = [internal_piece(LABELS[i]) for i in indices]
        board = [tokens[r * 9:(r + 1) * 9] for r in range(10)]
        certain = bool((confidence >= self.min_confidence).all() and "?" not in tokens)
        return BoardObservation(board, confidence, certain, calibration.timestamp, calibration.generation)


class StableBoard:
    def __init__(self, frames=3):
        if frames < 1:
            raise ValueError("At least one frame is required")
        self.frames = frames
        self.reset()

    def reset(self):
        self._key, self._count, self._timestamp = None, 0, None
        self.current = None

    def update(self, observation):
        if observation is None or not observation.certain:
            self.reset()
            return None
        if self._timestamp is not None and observation.timestamp <= self._timestamp:
            return self.current
        self._timestamp = observation.timestamp
        key = (tuple(tuple(row) for row in observation.board), observation.generation)
        self._count = self._count + 1 if key == self._key else 1
        self._key = key
        self.current = observation if self._count >= self.frames else None
        return self.current


def infer_legal_move(before, after, turn="r"):
    """Accept exactly one legal move matching ALL 90 observed cells, captures included."""
    changed = [(c, r) for r in range(10) for c in range(9) if before[r][c] != after[r][c]]
    if len(changed) != 2:
        return None
    candidates = []
    for src in changed:
        dst = next(p for p in changed if p != src)
        if not before[src[1]][src[0]].startswith(turn + "_"):
            continue
        if xiangqi.is_valid_move(src, dst, before, turn):
            predicted, _ = xiangqi.make_temp_move(before, (src, dst))
            if predicted == after:
                candidates.append((src, dst, before[src[1]][src[0]]))
    return candidates[0] if len(candidates) == 1 else None
