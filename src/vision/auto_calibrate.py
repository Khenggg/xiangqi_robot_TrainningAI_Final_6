# =============================================================================
# === FILE: auto_calibrate.py ===
# === Tự Động Hiệu Chỉnh Camera Perspective cho Bàn Cờ Tướng ===
# === Sử dụng RTMPose ONNX (pose_4_v6.onnx) thay cho YOLO-Pose cũ ===
# === Có cơ chế Geometric Sanity Check & Fallback an toàn về Click tay ===
# =============================================================================
import os
import time
import cv2
import numpy as np
from pathlib import Path

from src.vision.calibrate_camera import calibrate_perspective_camera
import config


class AutoCalibrator:
    """Tự động hiệu chỉnh ma trận phối cảnh camera (Auto-Calibration) bằng RTMPose ONNX.
    
    Sử dụng CChessRecognizer.detect_board_corners() để phát hiện 4 góc bàn cờ,
    thay thế YOLO-Pose (board_pose.pt) cũ bằng model RTMPose (pose_4_v6.onnx).
    
    Keypoint mapping:
        CChess A0 (idx 0) → P0 (Đen Trái,  col=0, row=0)
        CChess A8 (idx 1) → P1 (Đen Phải,  col=8, row=0)
        CChess J8 (idx 3) → P2 (Đỏ Phải,   col=8, row=9)
        CChess J0 (idx 2) → P3 (Đỏ Trái,   col=0, row=9)
    """

    def __init__(self, cchess_recognizer=None, pose_model_path=None, min_kpt_conf=0.65):
        """
        Args:
            cchess_recognizer: Instance CChessRecognizer đã khởi tạo (ưu tiên sử dụng)
            pose_model_path: (Legacy/unused) Giữ lại cho tương thích API cũ, không còn dùng YOLO-Pose
            min_kpt_conf: Ngưỡng confidence tối thiểu cho mỗi keypoint
        """
        self.recognizer = cchess_recognizer
        self.min_kpt_conf = min_kpt_conf
        self.pose_model_path = pose_model_path

        if self.recognizer is not None:
            print("[AUTO CALIBRATE] Da tai mo hinh RTMPose ONNX (pose_4_v6.onnx)")
        else:
            print("[AUTO CALIBRATE] Chua co CChessRecognizer - se fallback sang click tay")

    def sanity_check_geometry(self, kpts, img_w, img_h):
        """Kiểm tra tính hợp lệ hình học của 4 góc bàn cờ (P0, P1, P2, P3).
        
        P0: Đen Trái (col=0, row=0)
        P1: Đen Phải (col=8, row=0)
        P2: Đỏ Phải  (col=8, row=9)
        P3: Đỏ Trái  (col=0, row=9)
        """
        # 1. Kiểm tra đủ 4 điểm
        if len(kpts) != 4:
            return False, "Không đủ 4 keypoints"

        # 2. Kiểm tra nằm trong phạm vi ảnh (cho phép dung sai 2% ngoài biên nếu ảnh bị crop nhẹ)
        for i, (x, y) in enumerate(kpts):
            if x < -0.02 * img_w or x > 1.02 * img_w or y < -0.02 * img_h or y > 1.02 * img_h:
                return False, f"Keypoint P{i} nằm ngoài khung hình ({x:.1f}, {y:.1f})"

        # 3. Kiểm tra tính lồi (Convex Quadrilateral)
        pts_contour = np.array(kpts, dtype=np.int32).reshape((-1, 1, 2))
        if not cv2.isContourConvex(pts_contour):
            return False, "4 điểm không tạo thành tứ giác lồi hợp lệ"

        # 4. Kiểm tra thứ tự và chiều quay (Clockwise: P0 -> P1 -> P2 -> P3)
        # Vector P0 -> P1 (đường đỉnh, phía Đen)
        v_top = kpts[1] - kpts[0]
        # Vector P3 -> P2 (đường đáy, phía Đỏ)
        v_bottom = kpts[2] - kpts[3]

        # Kiểm tra hướng ngang theo tỷ lệ ảnh (P1 phải nằm bên phải P0, P2 phải bên phải P3 ít nhất 5% chiều rộng ảnh)
        min_horizontal_span = img_w * 0.05
        if v_top[0] <= min_horizontal_span or v_bottom[0] <= min_horizontal_span:
            return False, f"Hướng ngang bàn cờ bị đảo lộn (trái/phải): dx_top={v_top[0]:.1f}, dx_bot={v_bottom[0]:.1f}"

        # Kiểm tra hướng dọc theo tỷ lệ ảnh (P3, P2 phải nằm phía dưới P0, P1 ít nhất 5% chiều cao ảnh)
        min_vertical_span = img_h * 0.05
        if kpts[3][1] <= kpts[0][1] + min_vertical_span or kpts[2][1] <= kpts[1][1] + min_vertical_span:
            return False, "Hướng dọc bàn cờ bị đảo lộn (trên/dưới)"

        # 5. Kiểm tra kích thước bàn cờ tối thiểu (tránh bốc nhầm vật thể quá nhỏ)
        w_top = np.linalg.norm(v_top)
        w_bot = np.linalg.norm(v_bottom)
        h_left = np.linalg.norm(kpts[3] - kpts[0])
        h_right = np.linalg.norm(kpts[2] - kpts[1])
        if min(w_top, w_bot, h_left, h_right) < min(img_w, img_h) * 0.15:
            return False, "Kích thước bàn cờ dự đoán quá nhỏ so với khung hình"

        return True, "Hợp lệ"

    def predict_corners(self, frame):
        """Dự đoán 4 góc bàn cờ từ frame ảnh bằng RTMPose ONNX.
        
        CChessRecognizer trả về 4 keypoints theo thứ tự: A0, A8, J0, J8
        Ta chuyển đổi sang thứ tự P0, P1, P2, P3 để tương thích hệ thống cũ:
            P0 = A0 (Đen Trái)  = CChess idx 0
            P1 = A8 (Đen Phải)  = CChess idx 1
            P2 = J8 (Đỏ Phải)   = CChess idx 3
            P3 = J0 (Đỏ Trái)   = CChess idx 2
        
        Returns:
            (kpts, mean_conf) nếu hợp lệ, hoặc (None, 0.0) nếu không đạt.
        """
        if self.recognizer is None or frame is None:
            return None, 0.0

        h, w = frame.shape[:2]
        try:
            # RTMPose inference qua CChessRecognizer
            cchess_kpts, cchess_scores = self.recognizer.detect_board_corners(frame)
            # cchess_kpts shape (4, 2): [A0, A8, J0, J8]
            # cchess_scores shape (4,)

            # Chuyển đổi thứ tự CChess → P-order cho calibration
            # CChess: [0]=A0, [1]=A8, [2]=J0, [3]=J8
            # P-order: P0=A0, P1=A8, P2=J8, P3=J0
            reorder = [0, 1, 3, 2]
            kpts_xy = cchess_kpts[reorder].astype(np.float32)
            kpts_conf = cchess_scores[reorder]

            # Adaptive Confidence check for RTMPose SimCC
            # SimCC scores = max(softmax_x) * max(softmax_y), typically 0.15-0.35 for good predictions
            # Much lower than YOLO confidence (0.65+) because it's a product of two softmax values
            mean_conf = float(np.mean(kpts_conf))
            min_conf = float(np.min(kpts_conf))
            if mean_conf < 0.15 or min_conf < 0.08:
                print(f"[AUTO CALIBRATE] Confidence keypoint thap: mean={mean_conf:.4f}, min={min_conf:.4f} (yeu cau mean>=0.15, min>=0.08)")
                return None, 0.0

            # Geometric Sanity Check
            is_valid, reason = self.sanity_check_geometry(kpts_xy, w, h)
            if not is_valid:
                print(f"[AUTO CALIBRATE] Sanity Check that bai: {reason}")
                return None, 0.0

            return kpts_xy, mean_conf

        except Exception as e:
            print(f"[AUTO CALIBRATE] Loi inference RTMPose: {e}")
            return None, 0.0


def run_calibration_flow(cap, perspective_path, cchess_recognizer=None, pose_model_path=None, preview_sec=2.0):
    """Quy trình hiệu chỉnh Camera tích hợp:
    
    1. Warm-up camera một lần duy nhất (tránh race condition).
    2. Thử Auto-Calibration bằng RTMPose ONNX (pose_4_v6.onnx) nếu có CChessRecognizer.
    3. Nếu Auto thành công: tính M, lưu .npy, hiển thị overlay lưới xác nhận rồi vào game.
    4. Nếu Auto thất bại hoặc chưa có model: Tự động fallback sang Click tay 4 góc (manual).
    
    Args:
        cap: cv2.VideoCapture object đã mở
        perspective_path: đường dẫn lưu file .npy
        cchess_recognizer: Instance CChessRecognizer (ưu tiên sử dụng thay cho YOLO-Pose)
        pose_model_path: (Legacy/unused) Giữ lại cho tương thích API cũ
        preview_sec: Thời gian hiển thị preview (giây)
    """
    if getattr(config, "DRY_RUN", False):
        print("[CALIBRATE] DRY_RUN: bo qua calibration.")
        return None

    # --- BƯỚC 1: WARM UP CAMERA (Đồng nhất, không race condition) ---
    print("\n[CALIBRATE] Dang on dinh Camera USB...")
    for _ in range(40):
        ret, _ = cap.read()
        if not ret:
            time.sleep(0.05)
        time.sleep(0.02)
    time.sleep(0.3)

    ret, warm_frame = cap.read()
    if not ret or warm_frame is None:
        print("[CALIBRATE] Khong lay duoc frame sau warm-up!")
        return None

    # --- BƯỚC 2: THỬ AUTO-CALIBRATION (Multi-frame Sampling) ---
    if cchess_recognizer is not None:
        print("[CALIBRATE] Dang chay AI Auto-Calibration (RTMPose ONNX) phat hien 4 goc...")
        calibrator = AutoCalibrator(cchess_recognizer=cchess_recognizer)

        best_corners = None
        best_score = 0.0
        best_frame = None

        # Lấy mẫu 5 frame liên tiếp để chọn frame có độ tin cậy cao nhất, tránh nhiễu/bóng/tay che
        for attempt in range(5):
            ret, frame = cap.read()
            if ret and frame is not None:
                corners, score = calibrator.predict_corners(frame)
                if corners is not None and score > best_score:
                    best_corners = corners
                    best_score = score
                    best_frame = frame.copy()
            time.sleep(0.06)

        if best_corners is not None:
            print(f"[CALIBRATE] AI phat hien 4 goc ban co thanh cong! (Confidence: {best_score:.2%})")
            for i, name in enumerate(["Den Trai", "Den Phai", "Do Phai", "Do Trai"]):
                print(f"   P{i} ({name}): ({best_corners[i][0]:.1f}, {best_corners[i][1]:.1f})")

            # Tính ma trận phối cảnh M: pixel -> grid
            src = best_corners.astype(np.float32)
            dst = np.array([
                [0, 0],   # 1. Đen Trái (c=0, r=0)
                [8, 0],   # 2. Đen Phải (c=8, r=0)
                [8, 9],   # 3. Đỏ Phải  (c=8, r=9)
                [0, 9],   # 4. Đỏ Trái  (c=0, r=9)
            ], dtype=np.float32)

            M = cv2.getPerspectiveTransform(src, dst)
            np.save(str(perspective_path), M)
            print(f"[CALIBRATE] DA LUU MA TRAN AUTO-CALIBRATION: {perspective_path}")

            # Hiển thị Preview xác nhận trực quan (Grid Overlay)
            try:
                inv_M = np.linalg.inv(M)
                preview = (best_frame if best_frame is not None else warm_frame).copy()

                # Vẽ 10 hàng ngang
                for r in range(10):
                    p1 = cv2.perspectiveTransform(np.array([[[0, r]]], dtype=np.float32), inv_M)[0][0]
                    p2 = cv2.perspectiveTransform(np.array([[[8, r]]], dtype=np.float32), inv_M)[0][0]
                    cv2.line(preview, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), (0, 255, 255), 1)

                # Vẽ 9 cột dọc
                for c in range(9):
                    p1 = cv2.perspectiveTransform(np.array([[[c, 0]]], dtype=np.float32), inv_M)[0][0]
                    p2 = cv2.perspectiveTransform(np.array([[[c, 9]]], dtype=np.float32), inv_M)[0][0]
                    cv2.line(preview, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), (0, 255, 255), 1)

                # Vẽ 4 góc phát hiện
                for i, pt in enumerate(best_corners):
                    cv2.circle(preview, (int(pt[0]), int(pt[1])), 6, (0, 0, 255), -1)
                    cv2.putText(preview, f"P{i}", (int(pt[0]) + 8, int(pt[1]) - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                cv2.putText(preview, f"AUTO-CALIBRATION OK ({best_score:.0%})", (30, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

                win_name = "CALIBRATION_PREVIEW"
                cv2.namedWindow(win_name)
                cv2.imshow(win_name, preview)
                cv2.waitKey(int(preview_sec * 1000))
                cv2.destroyWindow(win_name)
            except Exception as e:
                print(f"[CALIBRATE] Preview error: {e}")

            return M

        print("[CALIBRATE] Auto-Calibration khong dat do tin cay. Chuyen sang Manual Fallback...")

    # --- BƯỚC 3: FALLBACK CLICK TAY NẾU CHƯA CÓ MODEL HOẶC AUTO THẤT BẠI ---
    print("[CALIBRATE] Mo giao dien Click 4 goc thu cong...")
    return calibrate_perspective_camera(cap, str(perspective_path))


def check_drift(frame, current_M, calibrator, threshold_px=8.0):
    """Kiểm tra xem bàn cờ có bị xê dịch so với ma trận M hiện tại hay không.
    
    Args:
        frame: Ảnh camera hiện tại
        current_M: Ma trận perspective hiện tại (3x3)
        calibrator: Đối tượng AutoCalibrator đã khởi tạo
        threshold_px: Ngưỡng sai số pixel tối đa cho phép
        
    Returns:
        (is_drifted, new_M, max_error_px)
    """
    if calibrator is None or current_M is None or frame is None:
        return False, current_M, 0.0

    new_corners, score = calibrator.predict_corners(frame)
    if new_corners is None:
        return False, current_M, 0.0

    # Lấy tọa độ 4 góc pixel kỳ vọng từ current_M nghịch đảo
    try:
        inv_M = np.linalg.inv(current_M)
        grid_corners = np.array([[[0, 0]], [[8, 0]], [[8, 9]], [[0, 9]]], dtype=np.float32)
        expected_corners = cv2.perspectiveTransform(grid_corners, inv_M).reshape(-1, 2)

        # Tính khoảng cách Euclidean sai lệch lớn nhất giữa thực tế và kỳ vọng
        errors = np.linalg.norm(new_corners - expected_corners, axis=1)
        max_error = float(np.max(errors))

        if max_error > threshold_px:
            print(f"[DRIFT WATCHDOG] Phat hien ban co bi lech {max_error:.1f}px > nguong {threshold_px}px!")
            dst = np.array([[0, 0], [8, 0], [8, 9], [0, 9]], dtype=np.float32)
            new_M = cv2.getPerspectiveTransform(new_corners.astype(np.float32), dst)
            return True, new_M, max_error

        return False, current_M, max_error
    except Exception as e:
        print(f"[DRIFT WATCHDOG] Loi kiem tra drift: {e}")
        return False, current_M, 0.0

