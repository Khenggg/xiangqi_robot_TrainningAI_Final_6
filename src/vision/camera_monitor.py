# =============================================================================
# === FILE: camera_monitor.py (Tách từ main_VIP.py) ===
# === Hiển thị Camera Monitor liên tục với YOLO occupancy detection + lưới ===
# === YOLO chỉ detect "có quân" / "không có" — quân gì thì tra bộ nhớ ===
# === SINGLE CAMERA OWNER: Chỉ file này truy cập camera trực tiếp ===
# =============================================================================
import cv2
import numpy as np
import time
import threading
import os

# Màu hiển thị
_PIECE_COLOR = (0, 255, 0)     # BGR - xanh lá cho tất cả quân detect được
_GRID_COLOR = (0, 255, 255)    # BGR - vàng cho lưới perspective


class CameraMonitor:
    """Hiển thị camera feed liên tục với YOLO detections + perspective grid.
    
    Đây là SINGLE OWNER duy nhất truy cập camera (cv2.VideoCapture).
    Các module khác (SnapshotDetector) nhận frame + detections từ đây.
    """

    def __init__(self, cap, model, perspective_path, window_name="Camera Monitor", conf=0.45):
        """
        Args:
            cap: cv2.VideoCapture đã mở
            model: YOLO model đã load
            perspective_path: đường dẫn file perspective.npy
            window_name: tên cửa sổ OpenCV
            conf: ngưỡng confidence phát hiện quân cờ (default: 0.45)
        """
        self.cap = cap
        self.model = model
        self.perspective_path = str(perspective_path)
        self.window_name = window_name
        self.conf = conf
        self._M = None  # perspective matrix (camera → grid)
        self._inv_M = None  # inverse (grid → camera pixel, để vẽ lưới)
        self._last_frame = None
        self._last_detections = []  # format: (cls_id, conf, (x1, y1, x2, y2))
        self._stop_event = threading.Event()  # Thread-safe shutdown signal
        self._thread = None                 # Capture thread (30-60 FPS mượt mà)
        self._detect_thread = None          # YOLO detect thread (Async background)
        self._lock = threading.Lock()       # Bảo vệ _last_frame/_last_detections
        self._cam_lock = threading.Lock()   # Bảo vệ truy cập camera (cap.read/grab)

        # Tự động chọn GPU nếu có CUDA, ngược lại CPU
        try:
            import torch
            self.device = 0 if torch.cuda.is_available() else 'cpu'
        except Exception:
            self.device = 'cpu'
        print(f"[CAM MONITOR] 🚀 Using device: {self.device} for YOLO")

        self._load_perspective()

    def _load_perspective(self):
        """Load perspective matrix từ file."""
        if os.path.exists(self.perspective_path):
            self._M = np.load(self.perspective_path)
            try:
                self._inv_M = np.linalg.inv(self._M)
            except:
                self._inv_M = None
            print(f"[CAM MONITOR] ✅ Perspective loaded: {self.perspective_path}")
        else:
            print(f"[CAM MONITOR] ⚠️ Không tìm thấy perspective.npy")

    def reload_perspective(self):
        """Reload perspective sau khi calibrate lại."""
        self._load_perspective()

    def _capture_loop(self):
        """Luồng 1: Chuyên đọc frame liên tục từ camera ở tốc độ cao nhất (30-60 FPS).
        Đảm bảo cửa sổ hiển thị mượt mà 100%, không bao giờ bị nghẽn bởi YOLO."""
        while not self._stop_event.is_set():
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.1)
                continue

            with self._cam_lock:
                if self._stop_event.is_set():
                    break
                ret, frame = self.cap.read()

            if not ret or frame is None:
                time.sleep(0.01)
                continue

            with self._lock:
                self._last_frame = frame

            time.sleep(0.005)

        print("[CAM MONITOR] 🛑 Camera capture thread exited cleanly.")

    def _detect_loop(self):
        """Luồng 2: Chạy nền độc lập (Async) nhận diện YOLO định kỳ ở imgsz=640.
        Cập nhật bounding box đè lên video mà không bao giờ làm đứng hình camera."""
        while not self._stop_event.is_set():
            if self.model is None:
                time.sleep(0.2)
                continue

            frame_to_detect = None
            with self._lock:
                if self._last_frame is not None:
                    frame_to_detect = self._last_frame.copy()

            if frame_to_detect is None:
                time.sleep(0.05)
                continue

            detections = []
            try:
                frame_rgb = cv2.cvtColor(frame_to_detect, cv2.COLOR_BGR2RGB)
                results = self.model.predict(
                    frame_rgb, conf=self.conf, iou=0.35,
                    imgsz=640, device=self.device, verbose=False
                )
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    detections.append((cls_id, conf, (x1, y1, x2, y2)))
            except Exception:
                pass

            with self._lock:
                self._last_detections = detections

            # Nghỉ ngắn giữa các lần quét để không quá tải tài nguyên
            self._stop_event.wait(timeout=0.05)

        print("[CAM MONITOR] 🛑 Detection background thread exited cleanly.")

    def _draw_overlay(self, frame, detections):
        """Vẽ bounding box + lưới perspective lên frame."""
        display = frame.copy()

        # --- Vẽ bounding box YOLO ---
        for (cls_id, conf, (x1, y1, x2, y2)) in detections:
            cv2.rectangle(display, (x1, y1), (x2, y2), _PIECE_COLOR, 2)

            # Nhãn: confidence %
            text = f"piece {conf:.0%}"
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(display, (x1, y1 - th - 6), (x1 + tw + 4, y1), _PIECE_COLOR, -1)
            cv2.putText(display, text, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

        # --- Vẽ lưới perspective ---
        if self._inv_M is not None:
            try:
                # 10 hàng ngang
                for r in range(10):
                    p1 = cv2.perspectiveTransform(
                        np.array([[[0, r]]], dtype=np.float32), self._inv_M)[0][0]
                    p2 = cv2.perspectiveTransform(
                        np.array([[[8, r]]], dtype=np.float32), self._inv_M)[0][0]
                    cv2.line(display, (int(p1[0]), int(p1[1])),
                             (int(p2[0]), int(p2[1])), _GRID_COLOR, 1)
                # 9 cột dọc
                for c in range(9):
                    p1 = cv2.perspectiveTransform(
                        np.array([[[c, 0]]], dtype=np.float32), self._inv_M)[0][0]
                    p2 = cv2.perspectiveTransform(
                        np.array([[[c, 9]]], dtype=np.float32), self._inv_M)[0][0]
                    cv2.line(display, (int(p1[0]), int(p1[1])),
                             (int(p2[0]), int(p2[1])), _GRID_COLOR, 1)
            except:
                pass

        # --- Info text ---
        n_pieces = len(detections)
        dev_tag = "GPU" if self.device != "cpu" else "CPU"
        info = f"[{dev_tag}] Detected: {n_pieces} pieces | SPACE=confirm move"
        cv2.putText(display, info, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        return display

    def get_fresh_snapshot(self):
        """Chụp 1 snapshot MỚI: flush buffer + read + YOLO.
        
        Dùng khi SnapshotDetector cần ảnh chính xác tại thời điểm hiện tại
        (ví dụ: khi người chơi bấm SPACE).
        
        ⚠️ Hàm này BLOCK thread gọi nó (~200-500ms) vì phải chạy YOLO.
        
        Returns:
            (frame, detections) hoặc (None, []) nếu lỗi
            detections format: [(cls_id, conf, (x1, y1, x2, y2)), ...]
        """
        if self.cap is None or not self.cap.isOpened():
            return None, []

        # Dùng _cam_lock để không race với background thread
        with self._cam_lock:
            # Flush buffer camera để lấy frame mới nhất
            for _ in range(5):
                self.cap.grab()

            ret, frame = self.cap.read()

        if not ret:
            print("[CAM MONITOR] ❌ Camera read failed in get_fresh_snapshot!")
            return None, []

        # Chạy YOLO (bên ngoài cam_lock vì không cần camera nữa)
        detections = []
        if self.model is not None:
            try:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = self.model.predict(
                    frame_rgb, conf=self.conf, iou=0.35,
                    imgsz=640, device=self.device, verbose=False
                )
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    detections.append((cls_id, conf, (x1, y1, x2, y2)))
            except Exception as e:
                print(f"[CAM MONITOR] ⚠️ YOLO error in snapshot: {e}")

        # Cập nhật cache luôn
        with self._lock:
            self._last_frame = frame.copy()
            self._last_detections = detections

        return frame, detections

    def start(self):
        """Bắt đầu 2 thread song song: capture camera mượt mà và detect background."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._detect_thread = threading.Thread(target=self._detect_loop, daemon=True)
        self._thread.start()
        self._detect_thread.start()
        print("[CAM MONITOR] 🎥 Camera Monitor started (decoupled capture & detect threads)")

    def stop(self):
        """Dừng thread và giải phóng camera AN TOÀN."""
        print("[CAM MONITOR] 🛑 Stopping Camera Monitor...")
        
        # 1. Signal thread dừng
        self._stop_event.set()
        
        # 2. Chờ thread kết thúc
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        if self._detect_thread is not None and self._detect_thread.is_alive():
            self._detect_thread.join(timeout=2)
        
        # 3. Release camera SAU KHI thread đã dừng
        if self.cap is not None:
            try:
                self.cap.release()
                print("[CAM MONITOR] ✅ Camera released.")
            except Exception as e:
                print(f"[CAM MONITOR] ⚠️ Camera release error: {e}")
        
        # 4. Đóng cửa sổ OpenCV
        try:
            cv2.destroyWindow(self.window_name)
        except cv2.error:
            pass  # Window may not exist yet
        
        print("[CAM MONITOR] ✅ Camera Monitor stopped.")

    def update_display(self):
        """Gọi mỗi frame trong game loop — hiển thị camera window.
        
        Returns:
            key pressed in OpenCV window (or -1)
        """
        with self._lock:
            frame = self._last_frame
            detections = self._last_detections

        if frame is not None:
            display = self._draw_overlay(frame, detections)
            cv2.imshow(self.window_name, display)

        return cv2.waitKey(1)

    def get_latest_frame_and_detections(self):
        """Lấy frame + detections mới nhất (cached từ background thread).
        
        Returns:
            (frame, detections) — frame có thể None nếu chưa capture
            detections format: [(cls_id, conf, (x1, y1, x2, y2)), ...]
        """
        with self._lock:
            return (
                self._last_frame.copy() if self._last_frame is not None else None,
                list(self._last_detections)
            )
