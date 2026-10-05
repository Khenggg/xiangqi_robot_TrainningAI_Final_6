"""Run separately from RUN.bat: camera clicks or supervised grid/robot measurement."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
import config
from src.vision.geometry_measurement import (
    REFERENCE_CELLS, camera_grid_error, robot_xy_error, save_csv, draw_grid,
)


def output_dir():
    path = ROOT / 'measurement_reports' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    path.mkdir(parents=True, exist_ok=False)
    return path


def camera_measure(args):
    matrix_path = Path(args.perspective)
    matrix = np.load(matrix_path)
    if args.image:
        frame = cv2.imread(str(args.image))
        if frame is None:
            raise RuntimeError('Cannot read image')
        source = str(Path(args.image).resolve())
    else:
        source = f'camera:{args.camera}'
        cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
        try:
            if not cap.isOpened():
                raise RuntimeError(f'Cannot open camera {args.camera}')
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            frame = None
            for _ in range(40):
                ok, candidate = cap.read()
                if ok:
                    frame = candidate
                time.sleep(0.02)
            if frame is None:
                raise RuntimeError('Camera returned no frame')
        finally:
            cap.release()
    # Work on one frozen native-resolution image; click coordinates never
    # depend on window scaling, a moving board or a later camera frame.
    overlay = draw_grid(frame, matrix)
    directory = output_dir()
    cv2.imwrite(str(directory / 'camera-original.png'), frame)
    np.save(directory / 'perspective-used.npy', matrix)
    metadata = dict(source=source, width=frame.shape[1], height=frame.shape[0],
                    perspective_path=str(matrix_path.resolve()),
                    perspective_sha256=hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
                    expected_cells=REFERENCE_CELLS)
    (directory / 'camera-metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    rows = []
    cursor = [frame.shape[1] // 2, frame.shape[0] // 2]
    click = [None]
    window = 'CAMERA -> GRID | native pixels'
    cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)

    def mouse(event, x, y, flags, param):
        cursor[:] = [x, y]
        if event == cv2.EVENT_LBUTTONDOWN:
            click[0] = (x, y)

    cv2.setMouseCallback(window, mouse)
    print('Click PRINTED intersections, not piece centres or decorative border.')
    print('Use the SAME camera position/resolution as perspective.npy. Remove pieces covering reference points.')
    print('R=undo last | Q/ESC=finish and save partial results')
    try:
        while True:
            display = overlay.copy()
            for index, entry in enumerate(rows):
                pixel = (int(entry['pixel_x']), int(entry['pixel_y']))
                cv2.drawMarker(display, pixel, (0, 0, 255), cv2.MARKER_CROSS, 15, 2)
                cv2.putText(display, f"{index + 1}: {entry['error_cells']:.3f} cells", (pixel[0] + 8, pixel[1] - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
            prompt = (f'Click TRUE grid intersection {REFERENCE_CELLS[len(rows)]}' if len(rows) < len(REFERENCE_CELLS)
                      else 'All 9 points measured. Q=save, R=undo')
            # Put guidance below the image; don't cover measured intersections
            # or shift their native pixel coordinates.
            display = cv2.copyMakeBorder(display, 0, 58, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
            cv2.putText(display, prompt, (12, frame.shape[0] + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1)
            cv2.putText(display, 'RED=true clicked point | YELLOW=predicted grid | R=undo Q=save', (12, frame.shape[0] + 47),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.imshow(window, display)
            # Magnify original pixels separately; never cover click targets.
            x, y = cursor
            crop = frame[max(0, y-25):min(frame.shape[0], y+26), max(0, x-25):min(frame.shape[1], x+26)].copy()
            if crop.size:
                cv2.drawMarker(crop, (x-max(0, x-25), y-max(0, y-25)), (0, 0, 255), cv2.MARKER_CROSS, 9, 1)
                cv2.imshow('Intersection magnifier', cv2.resize(crop, (255, 255), interpolation=cv2.INTER_NEAREST))
            if click[0] is not None:
                pixel, click[0] = click[0], None
                if (len(rows) < len(REFERENCE_CELLS)
                        and 0 <= pixel[0] < frame.shape[1] and 0 <= pixel[1] < frame.shape[0]):
                    entry = camera_grid_error(matrix, pixel, REFERENCE_CELLS[len(rows)])
                    rows.append(entry)
                    print(f"{entry['expected_col'], entry['expected_row']}: delta="
                          f"({entry['delta_col']:+.4f},{entry['delta_row']:+.4f}) cells; error={entry['error_cells']:.4f}")
                    save_csv(directory / 'camera-grid.csv', rows)
            key = cv2.waitKey(30) & 0xFF
            if key == ord('r') and rows:
                rows.pop()
            if key in (ord('q'), 27) or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                cv2.imwrite(str(directory / 'camera-grid-overlay.png'), display)
                break
    finally:
        cv2.destroyWindow(window)
        cv2.destroyWindow('Intersection magnifier')
        save_csv(directory / 'camera-grid.csv', rows,
                 fieldnames=list(camera_grid_error(np.eye(3), (0, 0), (0, 0))))
    print(f'Report: {directory}')


def parse_xyz(text):
    values = [float(value) for value in text.replace(',', ' ').split()]
    if len(values) != 3 or not np.isfinite(values).all():
        raise ValueError('Enter X Y Z (three finite millimetre values)')
    return values


def robot_measure(args):
    from src.hardware.robot_VIP import FR5Robot, robot_sdk_core
    if robot_sdk_core is None:
        raise RuntimeError('Robot SDK unavailable')
    if config.DRY_RUN:
        raise RuntimeError('DRY_RUN enabled: no physical measurement possible')
    robot = FR5Robot()
    # Standard connect() opens/closes gripper. This read-only connection
    # deliberately bypasses that startup sequence.
    robot.robot = robot_sdk_core.RPC(robot.ip)
    try:
        time.sleep(2)
        robot.connected = bool(robot.robot.SDK_state)
        if not robot.connected:
            raise RuntimeError('Robot SDK not connected')
        robot._load_teaching_points()
        rotation = config.PICK_TOOL_ROTATION
        plans = [robot.board_to_pose_bilinear(*cell, config.SAFE_Z, rotation=rotation) for cell in REFERENCE_CELLS]
        directory = output_dir()
        metadata = dict(ip=robot.ip, tool=robot.tool_num, user=robot.user_num,
                        rotation=rotation, safe_z=config.SAFE_Z, measurement_z=args.z,
                        offset_x=config.OFFSET_X, offset_y=config.OFFSET_Y,
                        teaching_points=robot.teaching_points, mapping='production visual-pick bilinear')
        (directory / 'robot-metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        save_csv(directory / 'robot-plan.csv', [dict(col=c, row=r, x=p[0], y=p[1], z=p[2])
                                               for (c, r), p in zip(REFERENCE_CELLS, plans)])
        if not args.move:
            print(f'Read-only plan saved: {directory}. Add --move for supervised motion.')
            return
        print(f'Tool={robot.tool_num}, User={robot.user_num}; measurement Z={args.z}mm.')
        print('Pendant XYZ must use these SAME frames. Close RUN.bat; clear reference cells.')
        print('Only SAFE_Z motion is automatic. Lower/jog with pendant; gripper outputs are never commanded.')
        rows = []
        for cell, pose in zip(REFERENCE_CELLS, plans):
            print(f'Grid={cell}, command XY=({pose[0]:.3f},{pose[1]:.3f}), SAFE_Z={pose[2]:.3f}')
            if input('Type MOVE to position this point, or Q to stop: ').strip().upper() != 'MOVE':
                break
            # After manual jog the arm must be lifted before lateral travel.
            current = parse_xyz(input(f'Lift with pendant to Z >= {config.SAFE_Z}; enter current X Y Z (User {robot.user_num}): '))
            if current[2] < config.SAFE_Z:
                raise RuntimeError('Current Z is below SAFE_Z; no move issued')
            for name, command in (('Mode', lambda: robot.robot.Mode(0)),
                                  ('RobotEnable', lambda: robot.robot.RobotEnable(1))):
                result = command()
                if result != 0:
                    raise RuntimeError(f'{name} failed: {result}')
            # Remain at current safe height during lateral travel, then descend
            # to SAFE_Z. Errors including 112 abort rather than claiming arrival.
            travel = pose.copy()
            travel[2] = current[2]
            for target in (travel, pose):
                result = robot.move_safe_pose(target, speed=10, label='Grid measurement: no gripper action')
                if result != 0:
                    raise RuntimeError(f'Measurement MoveCart failed: {result}')
            print(f'With pendant, lower slowly to Z={args.z}, align jaw centre with TRUE printed intersection.')
            print('Read aligned XYZ in the SAME User/Tool frame; Q skips this point.')
            while True:
                text = input('Aligned X Y Z: ').strip()
                if text.upper() == 'Q':
                    break
                try:
                    entry = robot_xy_error(cell, pose, parse_xyz(text), args.z)
                except ValueError as exc:
                    print(exc)
                    continue
                rows.append(entry)
                save_csv(directory / 'grid-robot.csv', rows)
                print(f"Correction: delta X={entry['delta_x_mm']:+.3f}mm Y={entry['delta_y_mm']:+.3f}mm")
                break
        print(f'Report: {directory}. No automatic HOME movement after manual jog.')
    finally:
        close = getattr(robot.robot, 'CloseRPC', None)
        if callable(close):
            close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest='mode', required=True)
    camera = modes.add_parser('camera', help='Freeze frame and click 9 known intersections')
    camera.add_argument('--camera', type=int, default=config.VIDEO_SOURCE)
    camera.add_argument('--image', type=Path)
    camera.add_argument('--perspective', default=str(ROOT / 'perspective.npy'))
    robot = modes.add_parser('robot', help='Read-only grid plan; --move enables supervised SAFE_Z motion')
    robot.add_argument('--move', action='store_true')
    robot.add_argument('--z', type=float, default=config.PICK_Z, help='Pendant measurement height; not an automatic descent')
    args = parser.parse_args()
    if args.mode == 'camera':
        camera_measure(args)
    else:
        if not np.isfinite(args.z):
            parser.error('--z must be finite')
        robot_measure(args)


if __name__ == '__main__':
    main()
