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

from src.vision.calibrate_camera import (
    RETRY_AUTO_CALIBRATION,
    calibrate_perspective_camera,
)
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

        # 2. Kiểm tra nằm trong phạm vi ảnh
        for i, (x, y) in enumerate(kpts):
            if x < 0 or x >= img_w or y < 0 or y >= img_h:
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

        # Kiểm tra hướng ngang (P1 phải nằm bên phải P0, P2 phải bên phải P3)
        if v_top[0] <= 20 or v_bottom[0] <= 20:
            return False, "Hướng ngang bàn cờ bị đảo lộn (trái/phải)"

        # Kiểm tra hướng dọc (P3, P2 phải nằm phía dưới P0, P1)
        if kpts[3][1] <= kpts[0][1] + 30 or kpts[2][1] <= kpts[1][1] + 30:
            return False, "Hướng dọc bàn cờ bị đảo lộn (trên/dưới)"

        return True, "Hợp lệ"

    def predict_corners(self, frame):
        """Dự đoán 4 góc bàn cờ từ frame ảnh đã warm-up.
        
        Returns:
            kpts (numpy array 4x2) hoặc None nếu không thỏa mãn điều kiện.
        """
        if self.model is None or frame is None:
            return None

        h, w = frame.shape[:2]
        try:
            results = self.model.predict(frame, conf=0.4, verbose=False)
            if not results or len(results) == 0 or results[0].keypoints is None:
                return None

            kpts_obj = results[0].keypoints
            if len(kpts_obj) == 0:
                return None

            kpts_xy = kpts_obj[0].xy[0].cpu().numpy()  # (4, 2)
            kpts_conf = (
                kpts_obj[0].conf[0].cpu().numpy()
                if kpts_obj[0].conf is not None
                else np.array([1.0, 1.0, 1.0, 1.0])
            )

            # Kiểm tra confidence từng điểm
            if np.any(kpts_conf < self.min_kpt_conf):
                print(f"[AUTO CALIBRATE] ⚠️ Confidence keypoint thấp: {kpts_conf.round(2)} < {self.min_kpt_conf}")
                return None

            # Geometric Sanity Check
            is_valid, reason = self.sanity_check_geometry(kpts_xy, w, h)
            if not is_valid:
                print(f"[AUTO CALIBRATE] ⚠️ Sanity Check thất bại: {reason}")
                return None

            return kpts_xy.astype(np.float32)

        except Exception as e:
            print(f"[AUTO CALIBRATE] ❌ Lỗi inference: {e}")
            return None


def _run_calibration_attempt(cap, perspective_path, pose_model_path=None, preview_sec=2.0):
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

    # --- BƯỚC 2: THỬ AUTO-CALIBRATION ---
    if pose_model_path and os.path.exists(str(pose_model_path)):
        print("[CALIBRATE] 🤖 Đang chạy AI Auto-Calibration phát hiện 4 góc...")
        calibrator = AutoCalibrator(pose_model_path=pose_model_path)
        corners = calibrator.predict_corners(warm_frame)

        if corners is not None:
            print("[CALIBRATE] 🎯 AI phát hiện 4 góc bàn cờ thành công!")
            for i, name in enumerate(["Đen Trái", "Đen Phải", "Đỏ Phải", "Đỏ Trái"]):
                print(f"   👉 P{i} ({name}): ({corners[i][0]:.1f}, {corners[i][1]:.1f})")

            # Tính ma trận phối cảnh M: pixel -> grid
            src = corners.astype(np.float32)
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
                preview = warm_frame.copy()

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
                for i, pt in enumerate(corners):
                    cv2.circle(preview, (int(pt[0]), int(pt[1])), 6, (0, 0, 255), -1)
                    cv2.putText(preview, f"P{i}", (int(pt[0]) + 8, int(pt[1]) - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                cv2.putText(preview, "AUTO-CALIBRATION OK!", (30, 50),
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
    manual_result = calibrate_perspective_camera(cap, str(perspective_path))
    return manual_result


def run_calibration_flow(cap, perspective_path, pose_model_path=None, preview_sec=2.0):
    """Run calibration attempts until the operator saves, cancels, or retries AI."""
    while True:
        result = _run_calibration_attempt(
            cap,
            perspective_path,
            pose_model_path=pose_model_path,
            preview_sec=preview_sec,
        )
        if result is not RETRY_AUTO_CALIBRATION:
            return result
        print("[CALIBRATE] 🔄 Restarting AI Auto-Calibration...")

