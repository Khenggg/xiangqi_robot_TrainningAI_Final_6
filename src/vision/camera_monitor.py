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
_PIECE_COLOR = (0, 255, 0)     # BGR - xanh lá (fallback YOLO)
_GRID_COLOR = (0, 215, 255)    # BGR - vàng kim cho lưới perspective

# Bảng nhãn hiển thị quân cờ tiếng Việt + màu sắc (text_color, bg_color)
_PIECE_BADGES = {
    "r_K": ("Tg", (0, 0, 220), (255, 255, 255)),   # Tướng Đỏ
    "r_A": ("Si", (0, 0, 220), (255, 255, 255)),   # Sĩ Đỏ
    "r_E": ("Tu", (0, 0, 220), (255, 255, 255)),   # Tượng Đỏ
    "r_N": ("Ma", (0, 0, 220), (255, 255, 255)),   # Mã Đỏ
    "r_R": ("Xe", (0, 0, 220), (255, 255, 255)),   # Xe Đỏ
    "r_C": ("Ph", (0, 0, 220), (255, 255, 255)),   # Pháo Đỏ
    "r_P": ("Tot", (0, 0, 220), (255, 255, 255)),  # Tốt Đỏ
    "b_K": ("Tg", (25, 25, 25), (235, 235, 235)),  # Tướng Đen
    "b_A": ("Si", (25, 25, 25), (235, 235, 235)),  # Sĩ Đen
    "b_E": ("Tu", (25, 25, 25), (235, 235, 235)),  # Tượng Đen
    "b_N": ("Ma", (25, 25, 25), (235, 235, 235)),  # Mã Đen
    "b_R": ("Xe", (25, 25, 25), (235, 235, 235)),  # Xe Đen
    "b_C": ("Ph", (25, 25, 25), (235, 235, 235)),  # Pháo Đen
    "b_P": ("Tot", (25, 25, 25), (235, 235, 235)), # Tốt Đen
}


class CameraMonitor:
    """Hiển thị camera feed liên tục với CChess ONNX layout classification + perspective grid.
    
    Đây là SINGLE OWNER duy nhất truy cập camera (cv2.VideoCapture).
    Các module khác (SnapshotDetector) nhận frame + detections từ đây.
    """

    def __init__(self, cap, model=None, perspective_path=None, window_name="Camera Monitor", conf=0.25, cchess_recognizer=None):
        """
        Args:
            cap: cv2.VideoCapture đã mở
            model: (Optional) YOLO model
            perspective_path: đường dẫn file perspective.npy
            window_name: tên cửa sổ OpenCV
            conf: ngưỡng confidence phát hiện quân cờ
            cchess_recognizer: (Optional) CChessRecognizer ONNX instance
        """
        self.cap = cap
        self.model = model
        self.cchess_recognizer = cchess_recognizer
        self.perspective_path = str(perspective_path) if perspective_path else None
        self.window_name = window_name
        self.conf = conf

        self._M = None  # perspective matrix (camera → grid)
        self._inv_M = None  # inverse (grid → camera pixel, để vẽ lưới)
        self._last_frame = None
        self._last_detections = []  # format: (cls_id, conf, (x1, y1, x2, y2))
        self._last_cchess_result = None  # Dict: {"success": True, "board": ..., "confidence": ...}
        self._stop_event = threading.Event()  # Thread-safe shutdown signal
        self._thread = None                 # Capture thread (30-60 FPS mượt mà)
        self._detect_thread = None          # Detect thread (Async background)
        self._lock = threading.Lock()       # Bảo vệ _last_frame/_last_detections
        self._cam_lock = threading.Lock()   # Bảo vệ truy cập camera (cap.read/grab)
        self._board_polygon = None  # Cache polygon bàn cờ trong pixel space (4 điểm)

        # Tự động chọn GPU nếu có CUDA, ngược lại CPU
        try:
            import torch
            self.device = 0 if torch.cuda.is_available() else 'cpu'
        except Exception:
            self.device = 'cpu'
        if self.cchess_recognizer is not None:
            print("[CAM MONITOR] CChessRecognizer layout enabled for live monitoring.")
        if self.model is not None:
            print(f"[CAM MONITOR] Using device: {self.device} for YOLO fallback")
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

    def _compute_board_polygon(self, expand_px=20):
        """Tính và cache đa giác bàn cờ trong không gian pixel (4 góc tứ giác).

        Dùng inv_M để map 4 góc lưới (0,0)→(8,0)→(8,9)→(0,9) về pixel.
        Giãn polygon ra ngoài expand_px pixel để đảm bảo quân ở biên bàn không bị cắt
        khi perspective hơi lệch so với thực tế.

        Args:
            expand_px: số pixel giãn ra ngoài mỗi cạnh (default: 20)

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
            pts = corners_px.reshape(-1, 2)

            # Giãn polygon: dịch chuyển mỗi điểm ra ngoài tính từ tâm
            cx = pts[:, 0].mean()
            cy = pts[:, 1].mean()
            expanded = []
            for (px, py) in pts:
                dx = px - cx
                dy = py - cy
                dist = (dx**2 + dy**2) ** 0.5
                if dist > 0:
                    expanded.append([px + dx / dist * expand_px,
                                     py + dy / dist * expand_px])
                else:
                    expanded.append([px, py])

            self._board_polygon = np.array(expanded, dtype=np.float32).reshape(-1, 1, 2)
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
        """Luồng 2: Chạy nền độc lập (Async) nhận diện cờ định kỳ.
        Ưu tiên CChessRecognizer ONNX (layout_nano_v3.onnx), fallback về YOLO nếu không có CChess."""
        while not self._stop_event.is_set():
            if self.cchess_recognizer is None and self.model is None:
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
            # 1. ƯU TIÊN: Chạy CChessRecognizer layout classification
            if self.cchess_recognizer is not None and self._inv_M is not None:
                try:
                    grid_kpts = np.array([
                        [[0.0, 0.0]], [[8.0, 0.0]], [[0.0, 9.0]], [[8.0, 9.0]]
                    ], dtype=np.float32)
                    kpts_px = cv2.perspectiveTransform(grid_kpts, self._inv_M).reshape(4, 2)
                    warped, _ = self.cchess_recognizer.extract_rectified_board(frame_to_detect, kpts_px)
                    board_proj, board_short, confs = self.cchess_recognizer.recognize_layout(warped)

                    # Tạo danh sách detections tương thích ngược từ các ô có quân
                    for r in range(10):
                        for c in range(9):
                            p = board_proj[r][c]
                            if p not in (".", "x"):
                                pt = cv2.perspectiveTransform(
                                    np.array([[[float(c), float(r)]]], dtype=np.float32), self._inv_M
                                )[0][0]
                                cx, cy = int(pt[0]), int(pt[1])
                                rad = 18
                                conf_val = float(confs[r][c])
                                detections.append((0, conf_val, (cx - rad, cy - rad, cx + rad, cy + rad)))

                    with self._lock:
                        self._last_cchess_result = {
                            "success": True,
                            "board": board_proj,
                            "board_short": board_short,
                            "confidence": confs,
                            "keypoints": kpts_px,
                            "warped_image": warped,
                        }
                        self._last_detections = detections
                except Exception as e:
                    pass

            # 2. FALLBACK: Chạy YOLO nếu không có CChess
            elif self.model is not None:
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
                    detections = self._filter_by_board(detections)
                    with self._lock:
                        self._last_detections = detections
                except Exception:
                    pass

            # Nghỉ ngắn giữa các lần quét (khoảng ~150-250ms)
            self._stop_event.wait(timeout=0.2)

        print("[CAM MONITOR] Detection background thread exited cleanly.")

    def _draw_overlay(self, frame, detections):
        """Vẽ hiển thị bàn cờ: Lưới phối cảnh + Quân cờ CChess (hoặc bounding box YOLO)."""
        display = frame.copy()

        # --- 1. Vẽ lưới perspective ---
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
            except Exception:
                pass

        # --- 2. Vẽ quân cờ CChess ONNX (ƯU TIÊN) ---
        has_cchess = False
        with self._lock:
            cchess_res = self._last_cchess_result.copy() if self._last_cchess_result else None

        if cchess_res and cchess_res.get("success") and self._inv_M is not None:
            has_cchess = True
            board_proj = cchess_res["board"]
            for r in range(10):
                for c in range(9):
                    p = board_proj[r][c]
                    if p in _PIECE_BADGES:
                        badge_txt, text_col, bg_col = _PIECE_BADGES[p]
                        pt = cv2.perspectiveTransform(
                            np.array([[[float(c), float(r)]]], dtype=np.float32), self._inv_M
                        )[0][0]
                        cx, cy = int(round(pt[0])), int(round(pt[1]))
                        # Vẽ vòng tròn quân cờ nền sáng, viền đậm
                        cv2.circle(display, (cx, cy), 16, bg_col, -1)
                        cv2.circle(display, (cx, cy), 16, text_col, 2)
                        # Vẽ tên quân cờ căn giữa
                        (tw, th), _ = cv2.getTextSize(badge_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                        cv2.putText(display, badge_txt, (cx - tw // 2, cy + th // 2),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, text_col, 1, cv2.LINE_AA)

            n_red = sum(1 for row in board_proj for p in row if p.startswith("r_"))
            n_black = sum(1 for row in board_proj for p in row if p.startswith("b_"))
            total = n_red + n_black
            info = f"[CChess ONNX] Do: {n_red} | Den: {n_black} (Tong: {total}) | SPACE=xac nhan nuoc di"
            # Banner nền tối ở trên cùng
            cv2.rectangle(display, (0, 0), (620, 32), (0, 0, 0), -1)
            cv2.putText(display, info, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 0), 2)

        # --- 3. Fallback YOLO nếu chưa có CChess ---
        if not has_cchess and detections:
            for (cls_id, conf, (x1, y1, x2, y2)) in detections:
                cv2.rectangle(display, (x1, y1), (x2, y2), _PIECE_COLOR, 2)
                text = f"piece {conf:.0%}"
                (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                cv2.rectangle(display, (x1, y1 - th - 6), (x1 + tw + 4, y1), _PIECE_COLOR, -1)
                cv2.putText(display, text, (x1 + 2, y1 - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

            n_pieces = len(detections)
            dev_tag = "GPU" if self.device != "cpu" else "CPU"
            info = f"[{dev_tag}] Detected: {n_pieces} pieces | SPACE=confirm | M=emergency client move"
            cv2.putText(display, info, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        return display

    def get_fresh_snapshot(self):
        """Chụp 1 snapshot MỚI: flush buffer + read.
        Cập nhật đồng thời CChess layout recognition và detections.
        
        Returns:
            (frame, detections) — giữ nguyên signature để tương thích các module gọi
        """
        if self.cap is None or not self.cap.isOpened():
            return None, []

        with self._cam_lock:
            for _ in range(5):
                self.cap.grab()
            ret, frame = self.cap.read()

        if not ret or frame is None:
            print("[CAM MONITOR] Camera read failed in get_fresh_snapshot!")
            return None, []

        detections = []
        # Chạy CChess nếu có
        if self.cchess_recognizer is not None and self._inv_M is not None:
            try:
                grid_kpts = np.array([
                    [[0.0, 0.0]], [[8.0, 0.0]], [[0.0, 9.0]], [[8.0, 9.0]]
                ], dtype=np.float32)
                kpts_px = cv2.perspectiveTransform(grid_kpts, self._inv_M).reshape(4, 2)
                warped, _ = self.cchess_recognizer.extract_rectified_board(frame, kpts_px)
                board_proj, board_short, confs = self.cchess_recognizer.recognize_layout(warped)

                with self._lock:
                    self._last_cchess_result = {
                        "success": True,
                        "board": board_proj,
                        "board_short": board_short,
                        "confidence": confs,
                        "keypoints": kpts_px,
                        "warped_image": warped,
                    }
            except Exception as e:
                print(f"[CAM MONITOR] CChess error in fresh snapshot: {e}")

        # YOLO supplies the *measured* pixel box for gripper correction.  It
        # must run alongside CChess: CChess identifies pieces by cell but its
        # cell centres are theoretical, not physical piece positions.
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
                detections = self._filter_by_board(detections)
            except Exception as e:
                print(f"[CAM MONITOR] YOLO error in snapshot: {e}")

        with self._lock:
            self._last_frame = frame.copy()
            self._last_detections = detections

        return frame, detections

    def get_latest_cchess_result(self):
        """Lấy kết quả nhận diện CChess layout mới nhất."""
        with self._lock:
            return self._last_cchess_result.copy() if self._last_cchess_result is not None else None


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
