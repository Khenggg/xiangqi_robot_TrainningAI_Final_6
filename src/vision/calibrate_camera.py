# =============================================================================
# === FILE: calibrate_camera.py (Tách từ main_VIP.py) ===
# === Hiệu chỉnh Camera Perspective cho bàn cờ Tướng ===
# =============================================================================
import cv2
import numpy as np
import time
import threading
import queue

import config


def calibrate_perspective_camera(cap, save_path, *, cancel_event=None, capture_owner=None):
    """Hiệu chỉnh perspective camera bằng cách click 4 góc bàn cờ.
    
    Args:
        cap: cv2.VideoCapture object đã mở
        save_path: đường dẫn lưu file .npy (perspective matrix)
    
    Returns:
        M: perspective transform matrix (3x3), hoặc None nếu hủy
    """
    if config.DRY_RUN:
        print("[CALIBRATE] DRY_RUN: bỏ qua calibration.")
        return None

    # --- WARM UP camera TRƯỚC khi bắt đầu thread ---
    # ⚠️ PHẢI warm-up TRƯỚC, KHÔNG ĐƯỢC chạy song song với capture thread
    #    vì race condition trên cv2.VideoCapture gây frame đen!
    print("[CALIBRATE] ⏳ Đang chờ camera warm up...")
    for i in range(60):  # Đọc ~60 frame để camera USB ổn định (bỏ frame đen)
        if cancel_event is not None and cancel_event.is_set():
            return None
        ret, _ = cap.read()
        if not ret:
            time.sleep(0.05)
        time.sleep(0.03)
    time.sleep(0.5)  # Chờ thêm cho camera ổn định hoàn toàn
    print("[CALIBRATE] ✅ Camera warm up xong!")

    # --- Thread đọc camera liên tục (bắt đầu SAU warm-up) ---
    cal_q = queue.Queue(maxsize=2)
    cal_stop = threading.Event()

    def _cal_capture():
        while not cal_stop.is_set() and not (cancel_event is not None and cancel_event.is_set()):
            ret, frm = cap.read()
            if ret and frm is not None:
                if not cal_q.empty():
                    try: cal_q.get_nowait()
                    except queue.Empty: pass
                cal_q.put(frm)
            time.sleep(0.005)

    cal_thread = threading.Thread(target=_cal_capture, name="calibration-capture", daemon=False)
    cal_thread.start()
    if capture_owner is not None:
        capture_owner._calibration_capture_thread = cal_thread
        capture_owner._calibration_capture_stop = cal_stop
    try:
        return _collect_manual_points(cal_q, save_path, cancel_event, cal_thread)
    finally:
        cal_stop.set()
        cal_thread.join(timeout=1.0)
        if cal_thread.is_alive():
            raise RuntimeError("Calibration capture is still stopping; retain camera until its reader exits")
        if capture_owner is not None:
            capture_owner._calibration_capture_thread = None
            capture_owner._calibration_capture_stop = None


def _collect_manual_points(cal_q, save_path, cancel_event, cal_thread):
    window = "CALIBRATE"
    try:
        return _manual_points_window(cal_q, save_path, cancel_event, cal_thread, window)
    finally:
        # UI errors must still stop/join the capture in the caller's finally.
        try:
            cv2.destroyWindow(window)
        except cv2.error:
            pass


def _manual_points_window(cal_q, save_path, cancel_event, cal_thread, window):
    # --- Xử lý click chuột ---
    points = []
    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append((x, y))
            print(f"  👉 Điểm {len(points)}: ({x}, {y})")

    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    try:
        cv2.setWindowProperty(window, cv2.WND_PROP_TOPMOST, 1)
    except cv2.error:
        pass
    cv2.setMouseCallback(window, mouse_callback)

    print("\n=== HƯỚNG DẪN CLICK (QUAN TRỌNG) ===")
    print("👉 Click lần lượt 4 góc bàn cờ thật trên màn hình:")
    print("   1️⃣  Góc Xe Đen (Trái)")
    print("   2️⃣  Góc Xe Đen (Phải)")
    print("   3️⃣  Góc Xe Đỏ (Phải)")
    print("   4️⃣  Góc Xe Đỏ (Trái)")
    print("Click GIAO DIEM LUOI tren mat ban, KHONG click vien trang tri/tam quan.")
    print("Kiem tra luoi o ca ria va ben trong truoc khi bam S.")
    print("---------------------------------------------")
    print("⌨️  Phím tắt: 'R'=Làm lại | 'S'=Lưu file | 'Q'=Thoát")

    import os
    M = None
    if os.path.exists(save_path):
        try:
            M = np.load(save_path)
            print(f"ℹ️ Đã nạp perspective cũ từ {save_path}. Bấm 'S' để giữ nguyên hoặc click 4 góc để tạo lại.")
        except Exception:
            M = None

    while True:
        if cancel_event is not None and cancel_event.is_set():
            return None
        try:
            frame = cal_q.get(timeout=0.1)
        except queue.Empty:
            # Keep Q/window-close responsive when the camera stops producing.
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27) or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return None
            if not cal_thread.is_alive():
                raise RuntimeError("Calibration camera reader stopped before a frame was available")
            continue

        display = frame.copy()
        # Keep the click order and keys visible inside the OpenCV window.
        cv2.rectangle(display, (0, 0), (display.shape[1], 78), (0, 0, 0), -1)
        cv2.putText(display, "CLICK 4 GIAO DIEM: Den trai -> Den phai -> Do phai -> Do trai",
                    (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 255, 0), 2)
        if len(points) < 4:
            help_text = f"Da cham {len(points)}/4 | R=lam lai | S=luu | Q/ESC=huy"
        elif M is None:
            help_text = "4 diem khong hop le hoac chua du | R=lam lai | Q/ESC=huy"
        else:
            help_text = "Kiem tra luoi vang | S=luu | R=lam lai | Q/ESC=huy"
        cv2.putText(display, help_text, (12, 56),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 255, 255), 2)

        # Vẽ các điểm đã click
        for i, p in enumerate(points):
            cv2.circle(display, p, 5, (0, 0, 255), -1)
            cv2.putText(display, str(i + 1), (p[0] + 10, p[1]),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # Khi đủ 4 điểm → tính matrix và vẽ lưới
        if len(points) == 4:
            src = np.array(points, dtype=np.float32)
            # Lazy import avoids the module-level auto/manual calibration cycle.
            from src.vision.auto_calibrate import AutoCalibrator
            valid, reason = AutoCalibrator().sanity_check_geometry(src, frame.shape[1], frame.shape[0])
            dst = np.array([
                [0, 0],   # 1. Đen Trái
                [8, 0],   # 2. Đen Phải
                [8, 9],   # 3. Đỏ Phải
                [0, 9],   # 4. Đỏ Trái
            ], dtype=np.float32)
            M = cv2.getPerspectiveTransform(src, dst) if valid else None
            if not valid:
                cv2.putText(display, "Invalid corners: R=reset", (20, 45),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        # Vẽ lưới perspective nếu đã có M
        if M is not None:
            try:
                inv_M = np.linalg.inv(M)
                # Vẽ 10 hàng ngang
                for r in range(10):
                    p1 = cv2.perspectiveTransform(
                        np.array([[[0, r]]], dtype=np.float32), inv_M)[0][0]
                    p2 = cv2.perspectiveTransform(
                        np.array([[[8, r]]], dtype=np.float32), inv_M)[0][0]
                    cv2.line(display, (int(p1[0]), int(p1[1])),
                             (int(p2[0]), int(p2[1])), (0, 255, 255), 1)
                # Vẽ 9 cột dọc
                for c in range(9):
                    p1 = cv2.perspectiveTransform(
                        np.array([[[c, 0]]], dtype=np.float32), inv_M)[0][0]
                    p2 = cv2.perspectiveTransform(
                        np.array([[[c, 9]]], dtype=np.float32), inv_M)[0][0]
                    cv2.line(display, (int(p1[0]), int(p1[1])),
                             (int(p2[0]), int(p2[1])), (0, 255, 255), 1)

                prompt_text = "OK? Bam 'S' de Luu / Dung lai"
                cv2.putText(display, prompt_text, (20, 45),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            except:
                pass

        cv2.imshow(window, display)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord('q'), 27) or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
            M = None
            break
        elif key == ord('r'):
            points.clear()
            M = None
            print("🔄 Đã xóa điểm, hãy click lại.")
        elif key == ord('s') and M is not None:
            if cancel_event is not None and cancel_event.is_set():
                return None
            np.save(save_path, M)
            print(f"✅ ĐÃ LƯU THÀNH CÔNG: {save_path}")
            break

    return M
