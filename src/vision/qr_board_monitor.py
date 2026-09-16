"""Single camera owner publishing frame-matched QR and board observations."""
import threading
import time

import cv2
import numpy as np

from src.vision.qr_calibration import CORNER_GRID, transform
from src.vision.xiangqi_recognizer import StableBoard


class QRBoardMonitor:
    def __init__(self, cap, calibrator, recognizer, stable_frames=3):
        self.cap, self.calibrator, self.recognizer = cap, calibrator, recognizer
        self.stability = StableBoard(stable_frames)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._frame = None
        self._analyzed_frame = None
        self._frame_time = 0
        self._processed = 0
        self._observation = None
        self._visual_targets = {}
        self._calibration = None
        self.error = "Waiting for camera"
        self._threads = []

    def start(self):
        for target in (self._capture, self._detect):
            thread = threading.Thread(target=target, daemon=True)
            self._threads.append(thread)
            thread.start()

    def _capture(self):
        while not self._stop.is_set():
            ok, frame = self.cap.read()
            with self._lock:
                if ok:
                    self._frame, self._frame_time = frame, time.monotonic()
                else:
                    self._frame = None
                    self._observation = self._calibration = None
                    self.error = "Camera read failed"
            self._stop.wait(0.01 if ok else 0.1)

    def _detect(self):
        while not self._stop.is_set():
            with self._lock:
                frame = None if self._frame is None else self._frame.copy()
                stamp = self._frame_time
            if frame is None or stamp <= self._processed:
                self._stop.wait(0.02)
                continue
            self._processed = stamp
            try:
                calibration = self.calibrator.update(frame, stamp)
                observation = self.recognizer.predict(frame, calibration) if calibration else None
                stable = self.stability.update(observation)
                with self._lock:
                    self._calibration = calibration
                    self._observation = stable
                    self._analyzed_frame = frame
                    self.error = (self.calibrator.reason if calibration is None else
                                  "Board uncertain / waiting for stable frames" if stable is None else "Ready")
            except Exception as exc:
                self.stability.reset()
                self.calibrator.invalidate(str(exc))
                with self._lock:
                    self._calibration = self._observation = None
                    self.error = str(exc)
            self._stop.wait(0.03)

    def require_calibration(self):
        with self._lock:
            value = self._calibration
            if self._frame is None:
                raise RuntimeError("No live camera frame")
            if value is None or time.monotonic() - value.timestamp > self.calibrator.max_age:
                raise RuntimeError(self.error if value is None else "QR/camera measurement expired")
            return value

    def require_qr_calibration(self):
        """Physical motion never accepts pose-only fallback calibration."""
        with self._lock:
            value = self.require_calibration()
            if not hasattr(self.calibrator, "require_qr_current"):
                return value
            return self.calibrator.require_qr_current(time.monotonic())

    def require_board(self):
        with self._lock:
            calibration = self.require_calibration()
            value = self._observation
            if (value is None or value.generation != calibration.generation
                    or time.monotonic() - value.timestamp > self.calibrator.max_age):
                raise RuntimeError(self.error if value is None else "Board observation expired")
            return value

    def reference_snapshot(self):
        with self._lock:
            calibration = self.require_calibration()
            return self._analyzed_frame.copy(), calibration

    def set_visual_targets(self, targets):
        """Display-only targets from the same QR calibration generation."""
        with self._lock:
            self._visual_targets = dict(targets or {})

    def update_display(self):
        with self._lock:
            frame = None if self._frame is None else self._frame.copy()
            message = self.error
        if frame is not None:
            try:
                cal = self.require_calibration()
                for r in range(10):
                    pts = transform([[0, r], [8, r]], cal.grid_to_camera).astype(int)
                    cv2.line(frame, tuple(pts[0]), tuple(pts[1]), (0, 220, 220), 1)
                for c in range(9):
                    pts = transform([[c, 0], [c, 9]], cal.grid_to_camera).astype(int)
                    cv2.line(frame, tuple(pts[0]), tuple(pts[1]), (0, 220, 220), 1)
                for label, point in zip(("TL (0,0)", "TR (8,0)", "BR (8,9)", "BL (0,9)"), cal.corners_px):
                    cv2.putText(frame, label, tuple(point.astype(int)), cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 0, 0), 1)
                with self._lock:
                    targets = dict(self._visual_targets)
                for name, target in targets.items():
                    if target is not None and target.generation == cal.generation:
                        point = transform([[target.col, target.row]], cal.grid_to_camera)[0].astype(int)
                        cv2.circle(frame, tuple(point), 8, (255, 0, 255), 2)
                        cv2.putText(frame, f"{name} {target.offset_cells:.2f}", tuple(point + [8, -8]),
                                    cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 0, 255), 1)
            except RuntimeError:
                message = "WAIT: " + message
            cv2.putText(frame, message[:100], (10, 25), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 0, 255), 2)
            cv2.imshow("QR Xiangqi Camera", frame)
        return cv2.waitKey(1)

    def stop(self):
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=3)
        # Do not release VideoCapture concurrently with a blocked read.
        if not any(thread.is_alive() for thread in self._threads):
            self.cap.release()
        cv2.destroyAllWindows()
