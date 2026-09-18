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

    def __init__(self, cap, model, perspective_path, window_name="Camera Monitor", conf=0.35):
        """
        Args:
            cap: cv2.VideoCapture đã mở
            model: YOLO model đã load
            perspective_path: đường dẫn file perspective.npy
            window_name: tên cửa sổ OpenCV
            conf: ngưỡng confidence phát hiện quân cờ (default: 0.35)
                  Giữ thấp để không bỏ sót quân — false positives ngoài bàn cờ
                  đã được chặn bởi ROI polygon filter (_filter_by_board).
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
        self._thread = None
        self._lock = threading.Lock()       # Bảo vệ _last_frame/_last_detections
        self._cam_lock = threading.Lock()   # Bảo vệ truy cập camera (cap.read/grab)

        self._board_polygon = None  # Cache polygon bàn cờ trong pixel space (4 điểm)
        self._load_perspective()

    # -------------------------------------------------------------------------
    # ROI BOARD FILTER — Lọc detections nằm ngoài bàn cờ (pixel space)
    # -------------------------------------------------------------------------

    def _load_perspective(self):
        """Load perspective matrix từ file."""
        if os.path.exists(self.perspective_path):
            self._M = np.load(self.perspective_path)
            try:
                self._inv_M = np.linalg.inv(self._M)
            except:
                self._inv_M = None
            self._board_polygon = None  # Invalidate polygon cache sau khi reload
            print(f"[CAM MONITOR] ✅ Perspective loaded: {self.perspective_path}")
        else:
            print(f"[CAM MONITOR] ⚠️ Không tìm thấy perspective.npy")

    def reload_perspective(self):
        """Reload perspective sau khi calibrate lại."""
        self._load_perspective()

    def _compute_board_polygon(self):
        """Tính và cache đa giác bàn cờ trong không gian pixel (4 góc tứ giác).

        Dùng inv_M để map 4 góc lưới (0,0)→(8,0)→(8,9)→(0,9) về pixel.
        Kết quả cache vào self._board_polygon để tránh tính lại mỗi frame.

        Returns:
            np.ndarray shape (4,1,2) float32 hoặc None nếu không có perspective.
        """
        if self._board_polygon is not None:
            return self._board_polygon
        if self._inv_M is None:
            return None
        try:
            corners_grid = np.array([
                [[0.0, 0.0]],   # Góc trên-trái (Black, left)
                [[8.0, 0.0]],   # Góc trên-phải (Black, right)
                [[8.0, 9.0]],   # Góc dưới-phải (Red, right)
                [[0.0, 9.0]],   # Góc dưới-trái (Red, left)
            ], dtype=np.float32)
            corners_px = cv2.perspectiveTransform(corners_grid, self._inv_M)
            self._board_polygon = corners_px.reshape(-1, 1, 2).astype(np.float32)
            return self._board_polygon
        except Exception:
            return None

    def _filter_by_board(self, detections):
        """Lọc danh sách detections: chỉ giữ lại những detection có contact point
        nằm BÊN TRONG đa giác bàn cờ (pixel space).

        Nếu không có perspective matrix, trả về detections gốc (không lọc).
        Đây là 'Layer 0' — lọc trước khi _build_occupancy chạy.

        Args:
            detections: list of (cls_id, conf, (x1, y1, x2, y2))

        Returns:
            list — tập con của detections đã lọc
        """
        poly = self._compute_board_polygon()
        if poly is None:
            return detections  # Không có perspective → fallback, không lọc

        filtered = []
        for det in detections:
            cls_id, conf, (x1, y1, x2, y2) = det
            h = y2 - y1
            if h <= 0:
                continue
            cx = float((x1 + x2) / 2)
            cy = float(y1 + h * 0.85)  # Contact point (điểm chân quân)

            # pointPolygonTest >= 0 → điểm nằm trong hoặc trên biên đa giác
            if cv2.pointPolygonTest(poly, (cx, cy), False) >= 0:
                filtered.append(det)

        return filtered

    def _capture_and_detect(self):
        """Thread: đọc camera + chạy YOLO detect liên tục."""
        while not self._stop_event.is_set():
            if self.cap is None or not self.cap.isOpened():
                time.sleep(0.1)
                continue

            # Dùng _cam_lock để không race với get_fresh_snapshot()
            with self._cam_lock:
                if self._stop_event.is_set():
                    break
                
                # FLUSH BUFFER: Xóa sạch các frame cũ bị stack (dồn ứ) 
                # trong thời gian CPU đang bận chạy YOLO ở vòng lặp trước.
                # Đây là lý do chính gây ra hiện tượng "khựng/delay" (hình đi chậm hơn thực tế).
                for _ in range(5):
                    self.cap.grab()
                    
                ret, frame = self.cap.read()

            if not ret:
                time.sleep(0.01)
                continue

            # Chạy YOLO
            detections = []
            if self.model is not None:
                try:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    results = self.model.predict(
                        frame_rgb, conf=self.conf, iou=0.35,
                        imgsz=1280, verbose=False
                    )
                    for box in results[0].boxes:
                        cls_id = int(box.cls[0])
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        detections.append((cls_id, conf, (x1, y1, x2, y2)))
                except:
                    pass

            # Layer 0: Lọc những detection nằm ngoài vùng bàn cờ (pixel space)
            detections = self._filter_by_board(detections)

            with self._lock:
                self._last_frame = frame.copy()
                self._last_detections = detections


            # Bản thân model YOLO đã mất ~100-200ms để chạy xong,
            # nên vòng lặp này đã có delay tự nhiên, không cần sleep 0.15s nữa.
            self._stop_event.wait(timeout=0.02)

        print("[CAM MONITOR] 🛑 Background thread exited cleanly.")

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
        info = f"Detected: {n_pieces} pieces | SPACE=confirm move"
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
                    imgsz=1280, verbose=False
                )
                for box in results[0].boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    detections.append((cls_id, conf, (x1, y1, x2, y2)))
            except Exception as e:
                print(f"[CAM MONITOR] ⚠️ YOLO error in snapshot: {e}")

        # Layer 0: Lọc những detection nằm ngoài vùng bàn cờ (pixel space)
        detections = self._filter_by_board(detections)

        # Cập nhật cache luôn
        with self._lock:
            self._last_frame = frame.copy()
            self._last_detections = detections

        return frame, detections


    def start(self):
        """Bắt đầu thread capture + detect."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_and_detect, daemon=True)
        self._thread.start()
        print("[CAM MONITOR] 🎥 Camera Monitor started (background thread)")

    def stop(self):
        """Dừng thread và giải phóng camera AN TOÀN.
        
        Đảm bảo background thread HOÀN TOÀN dừng trước khi release camera
        để tránh race condition gây khóa camera cho lần chạy sau.
        """
        print("[CAM MONITOR] 🛑 Stopping Camera Monitor...")
        
        # 1. Signal thread dừng
        self._stop_event.set()
        
        # 2. Chờ thread kết thúc (tối đa 5s, đủ cho YOLO predict xong)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                print("[CAM MONITOR] ⚠️ Background thread chưa tắt sau 5s! Force continue...")
        
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
