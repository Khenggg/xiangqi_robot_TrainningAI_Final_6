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

    def __init__(self, cchess_recognizer=None, pose_model_path=None, min_kpt_conf=0.05):
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
        if np.asarray(kpts).shape != (4, 2) or not np.isfinite(kpts).all():
            return False, "Không đủ 4 keypoints"

        # 2. Kiểm tra nằm trong phạm vi ảnh (cho phép dung sai 2% ngoài biên nếu ảnh bị crop nhẹ)
        for i, (x, y) in enumerate(kpts):
            if x < -0.02 * img_w or x > 1.02 * img_w or y < -0.02 * img_h or y > 1.02 * img_h:
                return False, f"Keypoint P{i} nằm ngoài khung hình ({x:.1f}, {y:.1f})"

        # 3. Kiểm tra tính lồi (Convex Quadrilateral)
        pts_contour = np.array(kpts, dtype=np.int32).reshape((-1, 1, 2))
        if not cv2.isContourConvex(pts_contour):
            return False, "4 điểm không tạo thành tứ giác lồi hợp lệ"

        # 4. Kiểm tra chiều quay và diện tích tứ giác (Oriented Area: Clockwise P0 -> P1 -> P2 -> P3)
        oriented_area = cv2.contourArea(pts_contour, oriented=True)
        if oriented_area <= 0:
            return False, f"Thứ tự các góc không đúng chiều kim đồng hồ (oriented_area={oriented_area:.1f})"

        # 5. Kiểm tra diện tích bàn cờ tối thiểu (ít nhất 8% diện tích khung hình)
        total_frame_area = float(img_w * img_h)
        if abs(oriented_area) < 0.08 * total_frame_area:
            return False, f"Diện tích bàn cờ quá nhỏ ({abs(oriented_area):.0f} < {0.08*total_frame_area:.0f} px)"

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
            # SimCC scores = max(softmax_x) * max(softmax_y), typically 0.08-0.35 for good predictions
            mean_conf = float(np.mean(kpts_conf))
            min_conf = float(np.min(kpts_conf))
            if not np.isfinite(kpts_conf).all() or mean_conf < 0.08 or min_conf < self.min_kpt_conf:
                print(f"[AUTO CALIBRATE] Confidence keypoint thap: mean={mean_conf:.4f}, min={min_conf:.4f}")
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


def stable_corner_consensus(samples, min_samples=6, max_jitter_px=3.0):
    """Require a strict majority of consistent whole-board predictions.

    Scores do not determine accuracy. Reject a frame if ANY corner disagrees
    with the median; never combine independently selected corners from frames.
    """
    values = np.asarray(samples, dtype=np.float32)
    if len(samples) < min_samples or values.shape[1:] != (4, 2) or not np.isfinite(values).all():
        return None
    median = np.median(values, axis=0)
    errors = np.linalg.norm(values - median, axis=2).max(axis=1)
    inliers = values[errors <= max_jitter_px]
    if len(inliers) < max(min_samples, len(values) // 2 + 1):
        return None
    consensus = np.median(inliers, axis=0)
    if np.linalg.norm(inliers - consensus, axis=2).max() > max_jitter_px:
        return None
    return consensus.astype(np.float32)


def run_calibration_flow(cap, perspective_path, cchess_recognizer=None, pose_model_path=None, preview_sec=2.0):
    """Quy trình hiệu chỉnh Camera tích hợp:
    
    1. Warm-up camera một lần duy nhất (tránh race condition).
    2. Thử Auto-Calibration bằng RTMPose ONNX (pose_4_v6.onnx) nếu có CChessRecognizer.
    3. Nếu góc ổn định: hiển thị lưới; chỉ lưu sau khi người dùng xác nhận.
    4. Nếu Auto thất bại hoặc chưa có model: Tự động fallback sang Click tay 4 góc (manual).
    
    Args:
        cap: cv2.VideoCapture object đã mở
        perspective_path: đường dẫn lưu file .npy
        cchess_recognizer: Instance CChessRecognizer (ưu tiên sử dụng thay cho YOLO-Pose)
        pose_model_path: (Legacy/unused) Giữ lại cho tương thích API cũ
        preview_sec: Legacy compatibility; preview now waits for explicit acceptance.
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
        raise RuntimeError("Camera calibration failed: no fresh frame")

    # --- BƯỚC 2: THỬ AUTO-CALIBRATION (Multi-frame Sampling) ---
    if cchess_recognizer is not None:
        print("[CALIBRATE] Dang chay AI Auto-Calibration (RTMPose ONNX) phat hien 4 goc...")
        calibrator = AutoCalibrator(cchess_recognizer=cchess_recognizer)

        best_score = 0.0
        best_frame = None
        samples = []

        # Require a stable majority rather than trusting the highest model score.
        for attempt in range(12):
            ret, frame = cap.read()
            if ret and frame is not None:
                corners, score = calibrator.predict_corners(frame)
                if corners is not None:
                    samples.append(corners)
                if corners is not None:
                    best_score = score
                    best_frame = frame.copy()
            time.sleep(0.06)

        best_corners = stable_corner_consensus(samples)
        if best_corners is not None:
            valid, reason = calibrator.sanity_check_geometry(best_corners, warm_frame.shape[1], warm_frame.shape[0])
            if not valid:
                best_corners = None

        if best_corners is not None:
            print(f"[CALIBRATE] Stable corner candidate; waiting for grid approval (model score: {best_score:.2%})")
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

                cv2.rectangle(preview, (0, 0), (preview.shape[1], 78), (0, 0, 0), -1)
                cv2.putText(preview, "CHECK GRID: S=accept | M=manual corners | Q=cancel", (15, 28),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
                cv2.putText(preview, "Verify printed intersections at edges AND inside board. Score is not accuracy.", (15, 58),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

                win_name = "CALIBRATION_PREVIEW"
                cv2.namedWindow(win_name)
                cv2.imshow(win_name, preview)
                accepted = False
                cancelled = False
                while True:
                    key = cv2.waitKey(50) & 0xFF
                    if key in (ord('s'), ord('S')):
                        accepted = True
                        break
                    if key in (ord('m'), ord('M')):
                        break
                    if key in (ord('q'), ord('Q'), 27) or cv2.getWindowProperty(win_name, cv2.WND_PROP_VISIBLE) < 1:
                        cancelled = True
                        break
                cv2.destroyWindow(win_name)
                if cancelled:
                    raise RuntimeError("Camera calibration cancelled; previous matrix was not accepted")
                if accepted:
                    np.save(str(perspective_path), M)
                    print(f"[CALIBRATE] Accepted and saved: {perspective_path}")
                    return M
            except RuntimeError:
                raise
            except Exception as e:
                print(f"[CALIBRATE] Preview error: {e}")

        print("[CALIBRATE] Automatic candidate not accepted; switching to manual calibration.")

    # --- BƯỚC 3: FALLBACK CLICK TAY NẾU CHƯA CÓ MODEL HOẶC AUTO THẤT BẠI ---
    print("[CALIBRATE] Mo giao dien Click 4 goc thu cong...")
    matrix = calibrate_perspective_camera(cap, str(perspective_path))
    if matrix is None:
        raise RuntimeError("Camera calibration cancelled or failed")
    return matrix


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

