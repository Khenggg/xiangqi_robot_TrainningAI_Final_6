"""Camera startup validation; no implicit device substitution."""
import time
import cv2
import numpy as np


def validate_perspective(matrix):
    try:
        value = np.asarray(matrix, dtype=float)
        return value.shape == (3, 3) and np.isfinite(value).all() and np.linalg.matrix_rank(value) == 3
    except (ValueError, TypeError, np.linalg.LinAlgError):
        return False


def open_validated_camera(index, attempts=10, capture_factory=None, backend="dshow", frame_size=(1280, 720)):
    """Select precisely the requested device and prove it supplies a frame."""
    factory = capture_factory or cv2.VideoCapture
    if capture_factory is None:
        from src.vision.camera_source import open_camera
        cap = open_camera(index, backend)
    else:
        cap = factory(index, cv2.CAP_DSHOW)
    try:
        if not cap.isOpened():
            raise RuntimeError(f"Camera VIDEO_INDEX={index} could not be opened")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, frame_size[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, frame_size[1])
        for _ in range(attempts):
            ok, frame = cap.read()
            if ok and frame is not None and frame.size and frame.ndim == 3 and frame.shape[2] == 3:
                return cap
            time.sleep(0.03)
        raise RuntimeError(f"Camera VIDEO_INDEX={index} opened but supplied no valid BGR frame")
    except Exception:
        cap.release()
        raise
