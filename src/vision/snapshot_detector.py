# =============================================================================
# === FILE: snapshot_detector.py (T1/T2 Snapshot Move Detection System) ===
# === So sánh 2 snapshot camera (trước/sau khi đi) để phát hiện nước đi ===
# === KHÔNG truy cập camera trực tiếp — nhận frame+detections từ ngoài ===
# =============================================================================
import cv2
import numpy as np
import os
import time

from src.vision.move_observation import MoveObservation


class SnapshotDetector:
    """
    Hệ thống phát hiện nước đi bằng so sánh 2 snapshot (T1/T2).
    
    Dùng OCCUPANCY GRID (có quân / trống) kết hợp với MEMORY BOARD
    để phát hiện nước đi. KHÔNG dựa vào YOLO để phân loại quân đỏ/đen.
    
    Flow:
        1. capture_baseline(frame, detections, board)  → Lưu T1 occupancy + board
        2. Người chơi di chuyển quân trên bàn thật
        3. detect_move(frame, detections)               → So sánh T1 vs T2 → nước đi
        4. AI đi quân
        5. capture_baseline(frame, detections, board)   → Lưu T1 mới
        6. Lặp lại từ bước 2
    
    ⚠️ Module này KHÔNG truy cập camera trực tiếp.
       Frame + detections được truyền vào từ CameraMonitor.
    """

    def __init__(self, perspective_path, class_id_map, num_cols=9, num_rows=10, max_dist_threshold=0.32):
        """
        Args:
            perspective_path: đường dẫn file perspective.npy
            class_id_map:     dict {class_id: "r_P", "b_N", ...} (dùng để filter valid detections)
            num_cols:         số cột bàn cờ (9)
            num_rows:         số hàng bàn cờ (10)
            max_dist_threshold: dung sai khoảng cách tối đa tới giao điểm ô cờ (default: 0.32)
        """
        self.perspective_path = str(perspective_path)
        self.class_id_map = class_id_map
        self.num_cols = num_cols
        self.num_rows = num_rows
        self.max_dist_threshold = max_dist_threshold

        # T1 baseline
        self._baseline_occ = None    # occupancy grid: True/False
        self._baseline_frame = None  # actual camera frame tại T1 (cho absdiff)
        self._baseline_time = None
        self.last_detection_ambiguous = False

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def capture_baseline(self, frame, detections):
        """Lưu T1 — snapshot baseline trước khi người chơi đi.
        
        Args:
            frame:      OpenCV frame (BGR) từ CameraMonitor
            detections: list of (cls_id, conf, (x1, y1, x2, y2)) từ CameraMonitor
        
        Returns:
            True nếu thành công, False nếu thất bại.
        """
        if frame is None:
            print("[SNAPSHOT] ❌ Không có frame cho T1 baseline!")
            return False

        occ = self._build_occupancy(detections)
        self._baseline_occ = occ
        self._baseline_frame = frame.copy()  # Lưu frame thực để dùng absdiff
        self._baseline_time = time.time()

        # Debug: đếm quân detect được
        n_occupied = sum(1 for r in occ for cell in r if cell)
        print(f"[SNAPSHOT] 📸 T1 Baseline captured: {n_occupied} quân detected by camera")
        return True

    def detect_move(self, frame, detections, board, cchess_result=None):
        """Chụp T2 và so sánh với T1 để phát hiện nước đi của quân ĐỎ.
        
        Args:
            frame:          OpenCV frame (BGR) từ CameraMonitor
            detections:     list of (cls_id, conf, (x1, y1, x2, y2)) từ CameraMonitor
            board:          memory board hiện tại (10x9 list, biết quân nào ở đâu)
            cchess_result:  (optional) kết quả từ CChessRecognizer.full_recognize()
        
        Returns:
            (src, dst, piece_name) nếu phát hiện nước đi hợp lệ
            (None, None, None) nếu không phát hiện được
        """
        self.last_detection_ambiguous = False
        if self._baseline_occ is None:
            print("[SNAPSHOT] ⚠️ Chưa có T1 baseline! Gọi capture_baseline() trước.")
            return None, None, None

        if frame is None:
            print("[SNAPSHOT] ❌ Không có frame cho T2!")
            return None, None, None

        # Build T2 occupancy
        t2_occ = self._build_occupancy(detections)

        # Debug
        n_occupied = sum(1 for r in t2_occ for cell in r if cell)
        print(f"[SNAPSHOT] 📸 T2 captured: {n_occupied} quân detected")

        # So sánh T1 vs T2 (dùng occupancy + memory board + CChess ONNX hỗ trợ)
        return self._compare_snapshots(self._baseline_occ, t2_occ, board, frame, cchess_result=cchess_result)

    def detect_move_observation(self, frame, detections, board, cchess_result=None, t2_occ=None):
        """Phát hiện nước đi trả về MoveObservation có cấu trúc.
        
        Args:
            frame: OpenCV frame (BGR)
            detections: list of detections
            board: current memory board
            cchess_result: optional CChess result
            t2_occ: optional precomputed occupancy grid
            
        Returns:
            MoveObservation
        """
        self.last_detection_ambiguous = False
        if self._baseline_occ is None:
            return MoveObservation(success=False, error="Chưa có T1 baseline! Gọi capture_baseline() trước.")

        if frame is None:
            return MoveObservation(success=False, error="Không có frame cho T2!")

        if t2_occ is None:
            t2_occ = self._build_occupancy(detections)

        src, dst, piece = self._compare_snapshots(
            self._baseline_occ, t2_occ, board, frame, cchess_result=cchess_result
        )

        if src is not None and dst is not None:
            dst_c, dst_r = dst
            orig_dest = board[dst_r][dst_c]
            is_capture = (orig_dest != ".")
            captured_piece = orig_dest if is_capture else None
            return MoveObservation(
                success=True,
                src=src,
                dst=dst,
                piece=piece,
                is_capture=is_capture,
                captured_piece=captured_piece,
                confidence=1.0,
            )

        if self.last_detection_ambiguous:
            return MoveObservation(
                success=False,
                is_ambiguous=True,
                error="Mơ hồ: Có nhiều ứng viên nước đi hợp lệ nhưng không thể phân định duy nhất.",
            )

        return MoveObservation(
            success=False,
            error="Không phát hiện được nước đi hợp lệ từ thay đổi bàn cờ.",
        )

    def has_baseline(self):
        """Kiểm tra đã có T1 baseline chưa."""
        return self._baseline_occ is not None

    def clear_baseline(self):
        """Xóa T1 baseline (dùng khi reset game)."""
        self._baseline_occ = None
        self._baseline_frame = None
        self._baseline_time = None
        print("[SNAPSHOT] 🗑️ Baseline cleared.")

    def get_baseline_grid(self):
        """Trả về occupancy grid T1 hiện tại (hoặc None)."""
        return self._baseline_occ

    # -------------------------------------------------------------------------
    # INTERNAL: Build occupancy grid từ detections
    # -------------------------------------------------------------------------

    def _build_occupancy(self, detections):
        """Convert detections → 10x9 occupancy grid (True/False).
        
        Không dựa vào class_id để phân loại quân — chỉ check "có quân / trống".
        
        Args:
            detections: list of (cls_id, conf, (x1, y1, x2, y2))
        
        Returns:
            10x9 grid of booleans (True = occupied, False = empty)
        """
        M = None
        if os.path.exists(self.perspective_path):
            M = np.load(self.perspective_path)

        grid = [[False for _ in range(self.num_cols)] for _ in range(self.num_rows)]
        if M is None:
            return grid

        for cls_id, conf, (x1, y1, x2, y2) in detections:
            w = x2 - x1
            h = y2 - y1
            if w <= 0 or h <= 0:
                continue

            # 1. BỘ LỌC TỶ LỆ KHUNG HÌNH (Aspect Ratio)
            # Quân cờ tròn nhìn từ góc xiên camera nằm trong khoảng 0.55 - 1.80
            aspect_ratio = float(w) / float(h)
            if aspect_ratio < 0.55 or aspect_ratio > 1.80:
                continue

            # Điểm chân quân cờ tiếp xúc mặt bàn (foot_point)
            cx = (x1 + x2) / 2
            cy = y1 + h * 0.85

            try:
                dst = cv2.perspectiveTransform(
                    np.array([[[float(cx), float(cy)]]], dtype=np.float32), M
                )[0][0]
                c_raw, r_raw = dst[0], dst[1]

                # 2a. BỘ LỌC BOUNDS CÁC GIÁ TRỊ THỰC (Raw Bounds Check)
                # Kiểm tra c_raw/r_raw TRƯỚC KHI round để tránh trường hợp:
                # c_raw = -0.28 → round → c=0 (hợp lệ) → dist=0.28 < 0.32 → PASS nhầm
                # Chỉ chấp nhận nếu giá trị thực nằm trong [-0.45, num_cols-0.55] và tương tự row
                if not (-0.45 <= c_raw <= (self.num_cols - 1) + 0.45):
                    continue
                if not (-0.45 <= r_raw <= (self.num_rows - 1) + 0.45):
                    continue

                c, r = int(round(c_raw)), int(round(r_raw))

                # 2b. BỘ LỌC BIÊN BÀN CỜ NGHIÊM NGẶT (Strict Boundary Check)
                # Chỉ chấp nhận nếu điểm rơi vào trong phạm vi hợp lệ 0..8 và 0..9
                # Tuyệt đối không clamp các vật thể ngoài biên vào cột 0 / hàng 0
                if 0 <= c < self.num_cols and 0 <= r < self.num_rows:
                    # 3. BỘ LỌC KHOẢNG CÁCH TỚI GIAO ĐIỂM (Distance-to-Intersection Gate)
                    # Tính khoảng cách Euclide giữa vị trí thực tế và giao điểm cờ nguyên
                    dist = ((c_raw - c) ** 2 + (r_raw - r) ** 2) ** 0.5
                    if dist <= self.max_dist_threshold:
                        grid[r][c] = True
            except (cv2.error, TypeError, ValueError):
                continue


        return grid

    # -------------------------------------------------------------------------
    # INTERNAL: Blind Capture Resolution (pixel differencing)
    # -------------------------------------------------------------------------

    def _get_pixel_box_from_grid(self, col, row, inv_M, frame_shape, padding=4):
        """Map tọa độ ô cờ (col, row) về bounding box pixel trên camera gốc.

        Dùng ma trận perspective nghịch đảo (grid→pixel) để map 4 góc của ô,
        rồi lấy bounding rect bao quanh.

        Args:
            col, row:    tọa độ ô cờ (0-indexed)
            inv_M:       ma trận nghịch đảo perspective (3x3, float32)
            frame_shape: (height, width, ...) của frame camera
            padding:     mở rộng bounding box thêm vài pixel mỗi phía

        Returns:
            (x1, y1, x2, y2) clipped vào kích thước frame, hoặc None nếu lỗi
        """
        try:
            h, w = frame_shape[:2]
            # 4 góc của ô cờ trong toạ độ grid
            corners_grid = np.array([[
                [float(col),     float(row)    ],
                [float(col + 1), float(row)    ],
                [float(col + 1), float(row + 1)],
                [float(col),     float(row + 1)],
            ]], dtype=np.float32)

            # Map về tọa độ pixel
            corners_px = cv2.perspectiveTransform(corners_grid, inv_M)[0]

            xs = corners_px[:, 0]
            ys = corners_px[:, 1]
            x1 = int(np.clip(np.min(xs) - padding, 0, w - 1))
            y1 = int(np.clip(np.min(ys) - padding, 0, h - 1))
            x2 = int(np.clip(np.max(xs) + padding, 0, w - 1))
            y2 = int(np.clip(np.max(ys) + padding, 0, h - 1))

            if x2 <= x1 or y2 <= y1:
                return None  # Ô quá nhỏ hoặc nằm ngoài frame

            return x1, y1, x2, y2
        except Exception as e:
            print(f"[SNAPSHOT] ⚠️ _get_pixel_box_from_grid error: {e}")
            return None

    def _resolve_capture_ambiguity(self, candidates, curr_frame):
        """Dùng pixel differencing (absdiff) để xác định ô đích thực sự.

        Khi YOLO không thể phân biệt ô nào bị ăn (vì occupancy-only),
        so sánh từng ô candidate giữa T1 (baseline_frame) và T2 (curr_frame).
        Ô bị ăn sẽ có sự thay đổi pixel lớn nhất (quân đen → quân đỏ).

        Args:
            candidates: list of (col, row) — các ô đích tiềm năng từ FEN
            curr_frame: OpenCV frame (BGR) tại thời điểm T2

        Returns:
            (col, row) của ô đích thực sự, hoặc None nếu không xác định được
        """
        if self._baseline_frame is None:
            print("[SNAPSHOT] ⚠️ resolve_capture_ambiguity: không có baseline_frame!")
            return None
        if curr_frame is None or len(candidates) == 0:
            return None

        # Load perspective matrix để tính inverse
        if not os.path.exists(self.perspective_path):
            print("[SNAPSHOT] ⚠️ resolve_capture_ambiguity: không có perspective.npy!")
            return None

        try:
            M = np.load(self.perspective_path)
            inv_M = np.linalg.inv(M)
        except Exception as e:
            print(f"[SNAPSHOT] ⚠️ resolve_capture_ambiguity: lỗi load/invert M: {e}")
            return None

        best_candidate = None
        best_score = -1
        score_log = []

        for (col, row) in candidates:
            box = self._get_pixel_box_from_grid(col, row, inv_M, curr_frame.shape)
            if box is None:
                score_log.append(f"  ({col},{row}): box=None")
                continue

            x1, y1, x2, y2 = box

            prev_crop = self._baseline_frame[y1:y2, x1:x2]
            curr_crop = curr_frame[y1:y2, x1:x2]

            if prev_crop.size == 0 or curr_crop.size == 0:
                score_log.append(f"  ({col},{row}): empty crop")
                continue

            # Grayscale để loại trừ nhiễu ánh sáng màu
            prev_gray = cv2.cvtColor(prev_crop, cv2.COLOR_BGR2GRAY)
            curr_gray = cv2.cvtColor(curr_crop, cv2.COLOR_BGR2GRAY)

            diff = cv2.absdiff(prev_gray, curr_gray)
            score = int(np.sum(diff))

            score_log.append(f"  ({col},{row}): score={score}")

            if score > best_score:
                best_score = score
                best_candidate = (col, row)

        print("[SNAPSHOT] 🔬 Blind Capture Resolution scores:")
        for s in score_log:
            print(s)
        print(f"[SNAPSHOT] ✅ Best candidate: {best_candidate} (score={best_score})")

        return best_candidate

    # -------------------------------------------------------------------------
    # INTERNAL: So sánh 2 snapshot T1 vs T2
    # -------------------------------------------------------------------------

    def _compare_snapshots(self, t1_occ, t2_occ, board, frame=None, cchess_result=None):
        """So sánh T1 vs T2 occupancy, dùng memory board để xác định quân.
        
        Dùng VALIDATE-FIRST approach: tìm tất cả cặp (src, dst) khả dĩ
        mà dst thuộc tập changed_to_true HOẶC là ô quân đen bị THAY ĐỔI
        THỰC SỰ từ camera (không quét toàn bộ quân đen để tránh false positives).
        
        Args:
            t1_occ:        10x9 bool grid (T1 occupancy)
            t2_occ:        10x9 bool grid (T2 occupancy)
            board:         10x9 memory board (tại thời điểm T1)
            frame:         OpenCV frame BGR tại T2 (dùng cho pixel absdiff fallback)
            cchess_result: (optional) kết quả từ CChessRecognizer
        
        Returns:
            (src, dst, piece_name) hoặc (None, None, None)
        """
        # Import xiangqi để validate
        try:
            from src.core import xiangqi
        except ImportError:
            xiangqi = None

        disappeared = []  # Ô T1 có quân → T2 trống
        appeared = []     # Ô T1 trống → T2 có quân
        self.last_detection_ambiguous = False

        for r in range(self.num_rows):
            for c in range(self.num_cols):
                t1_has = t1_occ[r][c]
                t2_has = t2_occ[r][c]

                if t1_has and not t2_has:
                    piece = board[r][c]
                    disappeared.append((c, r, piece))
                elif not t1_has and t2_has:
                    appeared.append((c, r))

        # Debug log
        print(f"[SNAPSHOT] 🔍 Compare: disappeared={len(disappeared)}, appeared={len(appeared)}")
        if disappeared:
            print(f"  Biến mất: {[(c, r, p) for c, r, p in disappeared]}")
        if appeared:
            print(f"  Xuất hiện: {[(c, r) for c, r in appeared]}")

        # === SRC candidates: quân ĐỎ biến mất ===
        red_disappeared = [(c, r, p) for c, r, p in disappeared if p.startswith("r")]
        if not red_disappeared:
            # Fallback về CChess ONNX recovery nếu có layout nhận diện đầy đủ bàn cờ
            if cchess_result and cchess_result.get("success") and xiangqi:
                rec_board = cchess_result.get("board", [])
                if rec_board:
                    c_src = []
                    c_dst = []
                    for r in range(self.num_rows):
                        for c in range(self.num_cols):
                            orig_p = board[r][c]
                            rec_p = rec_board[r][c]
                            if orig_p.startswith("r") and rec_p != orig_p:
                                c_src.append(((c, r), orig_p))
                            elif rec_p.startswith("r") and orig_p != rec_p:
                                c_dst.append(((c, r), rec_p))
                    for (s_c, s_r), p_src in c_src:
                        for (d_c, d_r), p_dst in c_dst:
                            if p_src == p_dst and xiangqi.is_valid_move((s_c, s_r), (d_c, d_r), board, "r"):
                                print(f"[SNAPSHOT] ✅ Fallback (CChess ONNX Recovery from 0 disappeared): {p_src} ({s_c},{s_r})→({d_c},{d_r})")
                                return (s_c, s_r), (d_c, d_r), p_src
            print("[SNAPSHOT] ❌ Không có quân đỏ nào biến mất.")
            return None, None, None

        print(f"  Quân đỏ biến mất: {red_disappeared}")

        # === DST candidates: chỉ dựa vào thay đổi THỰC SỰ từ camera ===
        # Loại 1: Ô T1 trống → T2 có quân (di chuyển thường)
        dst_candidates_move = set((c, r) for c, r in appeared)

        # Loại 2: Ô quân ĐEN THỰC SỰ biến mất ở T2 (bị ăn, YOLO miss quân đỏ)
        dst_candidates_black_gone = set()
        for c, r, p in disappeared:
            if p.startswith("b"):
                dst_candidates_black_gone.add((c, r))

        # Loại 3: Ô quân ĐEN trong memory board mà T1 & T2 đều có quân
        # → Trường hợp ăn quân phổ biến: YOLO detect được quân đỏ đang đứng tại ô dst
        #   sau khi ăn, nên occupancy không thay đổi (T1=True, T2=True).
        #   Cần chủ động add mọi ô đen "T1=True, T2=True (stable)" làm candidate.
        dst_candidates_capture_stable = set()
        if len(red_disappeared) == 1:  # Chỉ khi rõ ràng có 1 quân đỏ di chuyển
            for r in range(self.num_rows):
                for c in range(self.num_cols):
                    if (board[r][c].startswith("b")       # ô này có quân đen trong memory
                            and t1_occ[r][c]              # T1 camera detect có quân
                            and t2_occ[r][c]):             # T2 camera vẫn detect có quân (YOLO thấy quân đỏ mới)
                        dst_candidates_capture_stable.add((c, r))

        # Gộp dst candidates
        all_dst = dst_candidates_move | dst_candidates_black_gone | dst_candidates_capture_stable

        if all_dst:
            print(f"  DST candidates: move={dst_candidates_move}, "
                  f"black_gone={dst_candidates_black_gone}, "
                  f"capture_stable={dst_candidates_capture_stable}")

        # === VALIDATE: thử từng cặp (src, dst) với luật cờ ===
        valid_moves = []
        for src_c, src_r, piece in red_disappeared:
            src = (src_c, src_r)
            for dst in all_dst:
                if dst == src:
                    continue
                if xiangqi and xiangqi.is_valid_move(src, dst, board, "r"):
                    dst_piece = board[dst[1]][dst[0]]
                    move_type = "ăn quân" if dst_piece.startswith("b") else "di chuyển"
                    valid_moves.append((src, dst, piece, move_type))
                    print(f"  ✅ Valid: {piece} {src}→{dst} ({move_type})")

        if len(valid_moves) == 1:
            src, dst, piece, move_type = valid_moves[0]
            print(f"[SNAPSHOT] ✅ Detected ({move_type}): {piece} {src}→{dst}")
            return src, dst, piece

        if len(valid_moves) > 1:
            # 1. CCHESS ONNX TIEBREAKER: Nếu có kết quả nhận diện quân từ CChess ONNX
            if cchess_result and cchess_result.get("success"):
                rec_board = cchess_result.get("board", [])
                if rec_board:
                    # Kiểm tra candidate nào mà ô đích trên rec_board khớp với quân cờ đang đi
                    cchess_matched = [
                        (s, d, p, mt) for s, d, p, mt in valid_moves
                        if rec_board[d[1]][d[0]] == p
                    ]
                    if len(cchess_matched) == 1:
                        s, d, p, mt = cchess_matched[0]
                        print(f"[SNAPSHOT] ✅ Detected ({mt}, CChess ONNX tiebreaker): {p} {s}→{d}")
                        return s, d, p

            # 2. Pixel absdiff tiebreaker
            print(f"[SNAPSHOT] ⚠️ Ambiguous: {len(valid_moves)} valid moves — dùng pixel absdiff tiebreaker...")
            dst_candidates = [(dst[0], dst[1]) for src, dst, piece, move_type in valid_moves]
            best_dst = self._resolve_capture_ambiguity(dst_candidates, frame) if frame is not None else None
            if best_dst is not None:
                matched = [(s, d, p, mt) for s, d, p, mt in valid_moves if d == best_dst]
                if len(matched) == 1:
                    src, dst, piece, move_type = matched[0]
                    print(f"[SNAPSHOT] ✅ Detected ({move_type}, pixel absdiff of {len(valid_moves)}): {piece} {src}→{dst}")
                    return src, dst, piece

            # P0: REMOVE MANHATTAN GUESSING
            # If multiple legal candidates cannot be uniquely resolved, FAIL CLOSED.
            print(f"[SNAPSHOT] ❌ Ambiguous: {len(valid_moves)} valid moves remain unresolved. Failing closed.")
            self.last_detection_ambiguous = True
            return None, None, None

        # === FALLBACK 1: Không có valid move qua occupancy grid ===
        # Dùng pixel absdiff để phát hiện capture (khi YOLO miss hoàn toàn dst)
        if len(red_disappeared) == 1 and frame is not None:
            src_c, src_r, piece = red_disappeared[0]
            src = (src_c, src_r)

            # Trường hợp: cả đỏ src VÀ đen dst đều "biến mất" (YOLO miss cả 2)
            black_disappeared = [(c, r) for c, r, p in disappeared if p.startswith("b")]
            if len(black_disappeared) == 1:
                dst = black_disappeared[0]
                if xiangqi and xiangqi.is_valid_move(src, dst, board, "r"):
                    print(f"[SNAPSHOT] ✅ Fallback (ăn quân, cả 2 biến mất): {piece} {src}→{dst}")
                    return src, dst, piece

            # Dùng pixel absdiff để tìm ô quân đen có thay đổi nhiều nhất
            black_candidates = [
                (c, r)
                for r in range(self.num_rows)
                for c in range(self.num_cols)
                if board[r][c].startswith("b")
                and (xiangqi and xiangqi.is_valid_move(src, (c, r), board, "r"))
            ]
            if black_candidates:
                best = self._resolve_capture_ambiguity(black_candidates, frame)
                if best is not None:
                    print(f"[SNAPSHOT] ✅ Fallback (pixel absdiff capture): {piece} {src}→{best}")
                    return src, best, piece

        # === FALLBACK 2: CCHESS RECOVERY (So sánh trực tiếp memory board vs CChess ONNX layout) ===
        if cchess_result and cchess_result.get("success") and xiangqi:
            rec_board = cchess_result.get("board", [])
            if rec_board:
                candidates_src = []
                candidates_dst = []
                for r in range(self.num_rows):
                    for c in range(self.num_cols):
                        orig_p = board[r][c]
                        rec_p = rec_board[r][c]
                        if orig_p.startswith("r") and rec_p != orig_p:
                            candidates_src.append(((c, r), orig_p))
                        elif rec_p.startswith("r") and orig_p != rec_p:
                            candidates_dst.append(((c, r), rec_p))

                for (s_c, s_r), p_src in candidates_src:
                    for (d_c, d_r), p_dst in candidates_dst:
                        if p_src == p_dst and xiangqi.is_valid_move((s_c, s_r), (d_c, d_r), board, "r"):
                            print(f"[SNAPSHOT] ✅ Fallback (CChess ONNX Recovery): {p_src} ({s_c},{s_r})→({d_c},{d_r})")
                            return (s_c, s_r), (d_c, d_r), p_src

        print("[SNAPSHOT] ❌ Không tìm được nước đi hợp lệ.")
        return None, None, None


