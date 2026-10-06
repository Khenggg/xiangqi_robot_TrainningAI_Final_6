"""Camera-only commissioning. This module never imports a robot/hardware manager."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
import config
from src.vision.pick_geometry import (
    PickGeometry, VALIDATION_CELLS, calibrate_intrinsics, estimate_board_pose,
)

WINDOW = "Pick geometry - CAMERA ONLY - ESC cancels"
BANNER_HEIGHT = 105
POSE_CELLS = ((0, 0), (4, 0), (8, 0), (0, 4), (4, 4), (8, 4),
              (0, 9), (4, 9), (8, 9))


def show(frame, lines):
    banner = np.full((BANNER_HEIGHT, frame.shape[1], 3), 25, dtype=np.uint8)
    for i, line in enumerate(lines):
        cv2.putText(banner, line, (10, 28 + i*30), 0, .6, (0, 255, 255), 1, cv2.LINE_AA)
    cv2.imshow(WINDOW, np.vstack((banner, frame)))


def read_frame(cap, frame_size=None):
    ok, frame = cap.read()
    if not ok or frame is None:
        raise RuntimeError("Camera read failed")
    if frame_size and tuple(frame.shape[1::-1]) != tuple(frame_size):
        raise RuntimeError("Camera resolution changed during commissioning")
    return frame


def cancel_key(key):
    if key in (27, ord('q')) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
        raise KeyboardInterrupt


def capture_pattern(cap, pattern, square_mm, frame_size):
    samples = []
    message = "Move/tilt target: center, left/right, top/bottom. S=capture, C=fit (>=12)."
    while True:
        frame = read_frame(cap, frame_size)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        found, corners = cv2.findChessboardCornersSB(gray, pattern)
        if found:
            cv2.drawChessboardCorners(frame, pattern, corners, found)
        show(frame, [f"STEP 1: optical target {pattern[0]}x{pattern[1]} INNER corners; views={len(samples)}",
                     message, "ESC=abort; fixed camera/focus/zoom throughout ALL steps"])
        key = cv2.waitKey(30) & 255
        cancel_key(key)
        if key == ord('s') and found:
            points = corners.reshape(-1, 2)
            if any(np.sqrt(np.mean((points - p) ** 2)) < 5 for p in samples):
                message = "Duplicate rejected. Move AND tilt target before S."
            else:
                samples.append(points.copy())
                message = "Captured. Move AND tilt target; S=next, C=fit (>=12)."
        elif key == ord('c'):
            try:
                rms, k, dist = calibrate_intrinsics(samples, pattern, square_mm, frame_size)
                return rms, k, dist, len(samples)
            except (ValueError, cv2.error) as exc:
                print(f"[CALIBRATION REJECTED] {exc}")
                message = str(exc)[:110] + "; collect more / R=restart views"
        elif key == ord('r'):
            samples.clear()
            message = "Views cleared. Start diverse captures again."


def click_points(cap, cells, title, frame_size):
    """Live preview -> F freezes raw frame -> exact-pixel clicks. U undo, R retry."""
    points = []
    frozen = None

    def click(event, x, y, _flags, _param):
        y -= BANNER_HEIGHT
        if (event == cv2.EVENT_LBUTTONDOWN and frozen is not None and len(points) < len(cells)
                and 0 <= x < frozen.shape[1] and 0 <= y < frozen.shape[0]):
            points.append((float(x), float(y)))

    cv2.setMouseCallback(WINDOW, click)
    try:
        while True:
            frame = read_frame(cap, frame_size) if frozen is None else frozen.copy()
            for number, point in enumerate(points):
                cv2.drawMarker(frame, tuple(map(int, point)), (255, 0, 255), 0, 12, 2)
                cv2.putText(frame, str(cells[number]), tuple(map(int, point)), 0, .5, (255, 0, 255), 1)
            next_text = (f"Click {cells[len(points)]}" if len(points) < len(cells)
                         else "All clicked. ENTER=accept these observations")
            show(frame, [title, next_text, "F=freeze; U=undo; R=live retry; ESC=abort"])
            key = cv2.waitKey(30) & 255
            cancel_key(key)
            if key == ord('f') and frozen is None:
                frozen = read_frame(cap, frame_size)
                points.clear()
            elif key == ord('u') and points:
                points.pop()
            elif key == ord('r'):
                frozen = None
                points.clear()
            elif key in (10, 13) and len(points) == len(cells):
                return np.asarray(points)
    finally:
        cv2.setMouseCallback(WINDOW, lambda *_args: None)


def run(args):
    # Require explicit measured value; no assumed DPI/square size.
    square_mm = args.square_mm
    if square_mm is None:
        print("In assets/calibration/checkerboard-20mm.svg, in 100% / Actual size.")
        print("Đây là tờ hiệu chuẩn ống kính TẠM THỜI, không phải bàn cờ tướng.")
        square_mm = float(input("Đo cạnh MỘT ô đen/trắng sau khi in, nhập mm: "))
    tolerance = args.max_error_mm
    if tolerance is None:
        tolerance = float(input("Sai số XY tối đa chấp nhận để lưu (mm, >0 và <=5): "))
    if not np.isfinite([square_mm, tolerance]).all() or square_mm <= 0 or not 0 < tolerance <= 5:
        raise ValueError("Measured square/tolerance invalid")
    print("Đóng RUN.bat trước. Tool chỉ mở camera, KHÔNG điều khiển arm/gripper.")
    print("1. Giữ camera cố định, di chuyển/NGHIÊNG tờ đen trắng qua giữa và rìa ảnh.")
    print("2. Bỏ tờ mẫu, bỏ quân, giữ bàn cố định; click 9 giao điểm được yêu cầu.")
    print("3. Đặt quân cao 10mm có dấu tâm trên mặt vào 5 ô kiểm tra, click dấu tâm.")
    print("   KHÔNG dùng 5 điểm này để fit pose; chỉ kiểm tra độc lập.")
    print("4. Chỉ khi kiểm tra đạt, nhấn S mới ghi profile; ESC giữ nguyên profile cũ.")
    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    try:
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open requested camera {args.camera}; no camera fallback")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        frame = read_frame(cap)
        frame_size = tuple(frame.shape[1::-1])
        cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        rms, k, dist, count = capture_pattern(cap, (args.cols, args.rows), square_mm, frame_size)
        print(f"Intrinsic RMS: {rms:.3f}px. Bỏ tờ mẫu và bỏ quân, KHÔNG dịch camera/bàn.")
        pixels = click_points(cap, POSE_CELLS,
                              "STEP 2: EMPTY board intersections (0,0 = Black-left rook)", frame_size)
        board_mm = [config.VISUAL_BOARD_WIDTH_MM, config.VISUAL_BOARD_HEIGHT_MM]
        rvec, tvec, pose_error = estimate_board_pose(POSE_CELLS, pixels, k, dist, board_mm)
        data = dict(schema=1, created_at=datetime.now(timezone.utc).isoformat(),
                    camera_index=args.camera, frame_size=list(frame_size), board_mm=board_mm,
                    piece_height_mm=config.VISUAL_PIECE_HEIGHT_MM,
                    camera_matrix=k.tolist(), distortion=dist.ravel().tolist(),
                    rvec=rvec.ravel().tolist(), tvec=tvec.ravel().tolist(),
                    pattern=dict(inner_corners=[args.cols, args.rows], square_mm=square_mm),
                    pose_observations=dict(cells=POSE_CELLS, pixels=pixels.tolist()),
                    quality=dict(intrinsic_rms_px=rms, intrinsic_views=count, diverse_views=True,
                                 pose_max_error_px=pose_error, max_error_mm=tolerance,
                                 operator_approved=False), height_validation=[])
        geometry = PickGeometry(data, require_validation=False)
        for cell in VALIDATION_CELLS:
            print(f"Đặt quân 10mm tại giao điểm {cell}, căn tâm đáy đúng giao điểm.")
            print("Click DẤU TÂM THẬT trên mặt trên, không click tâm box/ellipse bằng mắt.")
            pixel = click_points(cap, [cell],
                                 f"STEP 3: 10mm piece at {cell}; click its TOP CENTER MARK", frame_size)[0]
            measured = geometry.pixels_to_top_xy([pixel])[0]
            error = float(np.linalg.norm(measured - geometry.grid_to_xy(cell)))
            print(f"Independent {cell}: XY={measured.round(3)} error={error:.3f}mm / limit={tolerance}mm")
            if error > tolerance:
                raise ValueError("Independent height check failed; old profile unchanged. Recommission.")
            data["height_validation"].append(dict(cell=cell, pixel=pixel.tolist(), error_mm=error))
        print("5 điểm độc lập đạt tolerance. Kiểm tra thông tin, S=phê duyệt và lưu; ESC=hủy.")
        while True:
            show(read_frame(cap, frame_size), [f"STEP 4: 5 height checks PASS within {tolerance}mm",
                                              "S=operator approval and SAVE; ESC=cancel (no write)"])
            key = cv2.waitKey(30) & 255
            cancel_key(key)
            if key == ord('s'):
                data["quality"]["operator_approved"] = True
                commissioned = PickGeometry(data)
                commissioned.save_approved(args.output)
                print(f"Saved {args.output}; profile={commissioned.profile_id}. Robot remains untouched.")
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def parser():
    result = argparse.ArgumentParser(description="NEW camera-only top-face/10mm geometry commissioning; no robot.")
    result.add_argument("--camera", type=int, default=config.VIDEO_SOURCE)
    result.add_argument("--cols", type=int, default=9, help="printed INNER corner columns")
    result.add_argument("--rows", type=int, default=6, help="printed INNER corner rows")
    result.add_argument("--square-mm", type=float, help="MEASURED printed square side in mm")
    result.add_argument("--max-error-mm", type=float, help="operator acceptance tolerance, 0 < mm <= 5")
    result.add_argument("--output", type=Path, default=ROOT / config.VISUAL_PICK_GEOMETRY_PATH)
    return result


if __name__ == "__main__":
    try:
        run(parser().parse_args())
    except KeyboardInterrupt:
        print("Cancelled. Existing profile unchanged; no robot activated.")
    except Exception as exc:
        print(f"[BLOCKED] {exc}; no profile activated.")
        sys.exit(1)
