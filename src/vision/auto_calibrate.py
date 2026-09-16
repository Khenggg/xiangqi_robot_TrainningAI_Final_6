# =============================================================================
# === FILE: auto_calibrate.py ===
# === Tự Động Hiệu Chỉnh Camera Perspective cho Bàn Cờ Tướng (YOLO-Pose) ===
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
    """Tự động hiệu chỉnh ma trận phối cảnh camera (Auto-Calibration) bằng YOLO-Pose."""

    def __init__(self, pose_model_path=None, min_kpt_conf=0.65):
        """
        Args:
            pose_model_path: Đường dẫn tới file weights YOLO-Pose (vd: models/board_pose.pt)
            min_kpt_conf: Ngưỡng confidence tối thiểu cho mỗi keypoint
        """
        self.model = None
        self.min_kpt_conf = min_kpt_conf
        self.pose_model_path = pose_model_path

        if pose_model_path and os.path.exists(str(pose_model_path)):
            try:
                from ultralytics import YOLO
                self.model = YOLO(str(pose_model_path))
                print(f"[AUTO CALIBRATE] ✅ Đã tải mô hình Pose: {pose_model_path}")
            except Exception as e:
                print(f"[AUTO CALIBRATE] ⚠️ Không thể tải mô hình Pose ({pose_model_path}): {e}")
                self.model = None
        else:
            if pose_model_path:
                print(f"[AUTO CALIBRATE] ℹ️ File model chưa tồn tại: {pose_model_path}")

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
        """Dự đoán 4 góc bàn cờ từ frame ảnh đã warm-up.
        
        Returns:
            (kpts, mean_conf) nếu hợp lệ, hoặc (None, 0.0) nếu không đạt.
        """
        if self.model is None or frame is None:
            return None, 0.0

        h, w = frame.shape[:2]
        try:
            results = self.model.predict(frame, conf=0.3, verbose=False)
            if not results or len(results) == 0 or results[0].keypoints is None:
                return None, 0.0

            kpts_obj = results[0].keypoints
            if len(kpts_obj) == 0:
                return None, 0.0

            kpts_xy = kpts_obj[0].xy[0].cpu().numpy()  # (4, 2)
            kpts_conf = (
                kpts_obj[0].conf[0].cpu().numpy()
                if kpts_obj[0].conf is not None
                else np.array([1.0, 1.0, 1.0, 1.0])
            )

            # Cải tiến: Dùng Adaptive Confidence (Trung bình >= 0.65 VÀ điểm thấp nhất >= 0.40)
            mean_conf = float(np.mean(kpts_conf))
            min_conf = float(np.min(kpts_conf))
            if mean_conf < 0.65 or min_conf < 0.40:
                print(f"[AUTO CALIBRATE] ⚠️ Confidence keypoint thấp: mean={mean_conf:.2f}, min={min_conf:.2f} (yêu cầu mean>=0.65, min>=0.40)")
                return None, 0.0

            # Geometric Sanity Check
            is_valid, reason = self.sanity_check_geometry(kpts_xy, w, h)
            if not is_valid:
                print(f"[AUTO CALIBRATE] ⚠️ Sanity Check thất bại: {reason}")
                return None, 0.0

            return kpts_xy.astype(np.float32), mean_conf

        except Exception as e:
            print(f"[AUTO CALIBRATE] ❌ Lỗi inference: {e}")
            return None, 0.0


def run_calibration_flow(cap, perspective_path, pose_model_path=None, preview_sec=2.0):
    """Quy trình hiệu chỉnh Camera tích hợp:
    
    1. Warm-up camera một lần duy nhất (tránh race condition).
    2. Thử Auto-Calibration bằng YOLO-Pose nếu có model.
    3. Nếu Auto thành công: tính M, lưu .npy, hiển thị overlay lưới xác nhận rồi vào game.
    4. Nếu Auto thất bại hoặc chưa có model: Tự động fallback sang Click tay 4 góc (manual).
    """
    if getattr(config, "DRY_RUN", False):
        print("[CALIBRATE] DRY_RUN: bỏ qua calibration.")
        return None

    # --- BƯỚC 1: WARM UP CAMERA (Đồng nhất, không race condition) ---
    print("\n[CALIBRATE] ⏳ Đang ổn định Camera USB...")
    for _ in range(40):
        ret, _ = cap.read()
        if not ret:
            time.sleep(0.05)
        time.sleep(0.02)
    time.sleep(0.3)

    ret, warm_frame = cap.read()
    if not ret or warm_frame is None:
        print("[CALIBRATE] ❌ Không lấy được frame sau warm-up!")
        return None

    # --- BƯỚC 2: THỬ AUTO-CALIBRATION (Multi-frame Sampling) ---
    if pose_model_path and os.path.exists(str(pose_model_path)):
        print("[CALIBRATE] 🤖 Đang chạy AI Auto-Calibration phát hiện 4 góc (Multi-frame Sampling)...")
        calibrator = AutoCalibrator(pose_model_path=pose_model_path)

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
            print(f"[CALIBRATE] 🎯 AI phát hiện 4 góc bàn cờ thành công! (Confidence trung bình: {best_score:.2%})")
            for i, name in enumerate(["Đen Trái", "Đen Phải", "Đỏ Phải", "Đỏ Trái"]):
                print(f"   👉 P{i} ({name}): ({best_corners[i][0]:.1f}, {best_corners[i][1]:.1f})")

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
            print(f"[CALIBRATE] ✅ ĐÃ LƯU MA TRẬN AUTO-CALIBRATION: {perspective_path}")

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
                print(f"[CALIBRATE] ⚠️ Preview error: {e}")

            return M

        print("[CALIBRATE] ⚠️ Auto-Calibration không đạt độ tin cậy. Đang chuyển sang Manual Fallback...")

    # --- BƯỚC 3: FALLBACK CLICK TAY NẾU CHƯA CÓ MODEL HOẶC AUTO THẤT BẠI ---
    print("[CALIBRATE] 🖱️ Mở giao diện Click 4 góc thủ công...")
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
            print(f"[DRIFT WATCHDOG] ⚠️ Phát hiện bàn cờ bị lệch {max_error:.1f}px > ngưỡng {threshold_px}px!")
            dst = np.array([[0, 0], [8, 0], [8, 9], [0, 9]], dtype=np.float32)
            new_M = cv2.getPerspectiveTransform(new_corners.astype(np.float32), dst)
            return True, new_M, max_error

        return False, current_M, max_error
    except Exception as e:
        print(f"[DRIFT WATCHDOG] ⚠️ Lỗi kiểm tra drift: {e}")
        return False, current_M, 0.0

