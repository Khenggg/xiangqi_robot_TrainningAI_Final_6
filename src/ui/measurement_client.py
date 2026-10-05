"""Step-by-step desktop geometry measurement. No gameplay or gripper actions."""
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import cv2
import numpy as np
from PIL import Image, ImageTk
import config
from src.vision.geometry_measurement import (
    REFERENCE_CELLS, camera_grid_error, robot_xy_error, save_csv, draw_grid,
)

ROOT = Path(__file__).resolve().parents[2]


def new_report():
    directory = ROOT / 'measurement_reports' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    directory.mkdir(parents=True)
    return directory


def parse_xyz(text):
    values = [float(v) for v in text.replace(',', ' ').split()]
    if len(values) != 3 or not np.isfinite(values).all():
        raise ValueError('Nhập đủ X Y Z, ngăn cách bằng dấu cách, đơn vị mm.')
    return values


def canvas_to_pixel(x, y, image_width, image_height, canvas_width=780, canvas_height=440):
    scale = min(canvas_width / image_width, canvas_height / image_height)
    width, height = round(image_width * scale), round(image_height * scale)
    offset_x = (canvas_width - width) / 2
    offset_y = (canvas_height - height) / 2
    px, py = (x - offset_x) * image_width / width, (y - offset_y) * image_height / height
    if 0 <= px < image_width and 0 <= py < image_height:
        return px, py
    return None


class CameraMeasurement:
    def __init__(self, frame, matrix):
        matrix = np.asarray(matrix, dtype=float)
        if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
            raise ValueError('perspective.npy không phải ma trận 3×3 hợp lệ.')
        try:
            inverse = np.linalg.inv(matrix)
        except np.linalg.LinAlgError as exc:
            raise ValueError('perspective.npy không khả nghịch; cần calibration hợp lệ.') from exc
        if not np.isfinite(inverse).all():
            raise ValueError('perspective.npy không khả nghịch hữu hạn.')
        self.frame = frame
        self.matrix = matrix
        self.rows = []
        self.directory = new_report()
        cv2.imwrite(str(self.directory / 'camera-original.png'), frame)
        np.save(self.directory / 'perspective-used.npy', matrix)
        (self.directory / 'camera-metadata.json').write_text(json.dumps({
            'width': frame.shape[1], 'height': frame.shape[0],
            'expected_cells': REFERENCE_CELLS, 'interface': 'guided client',
        }, indent=2), encoding='utf-8')

    def save(self):
        fields = list(camera_grid_error(np.eye(3), (0, 0), (0, 0)))
        save_csv(self.directory / 'camera-grid.csv', self.rows, fields)
        image = draw_grid(self.frame, self.matrix)
        for index, row in enumerate(self.rows):
            point = (round(row['pixel_x']), round(row['pixel_y']))
            cv2.drawMarker(image, point, (0, 0, 255), cv2.MARKER_CROSS, 15, 2)
            cv2.putText(image, f"{index + 1}: {row['error_cells']:.3f}", (point[0] + 9, point[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, .45, (0, 0, 255), 1)
        cv2.imwrite(str(self.directory / 'camera-grid-overlay.png'), image)
        return image

    def click(self, pixel):
        if len(self.rows) >= len(REFERENCE_CELLS):
            return
        self.rows.append(camera_grid_error(self.matrix, pixel, REFERENCE_CELLS[len(self.rows)]))
        self.save()

    def undo(self):
        if self.rows:
            self.rows.pop()
        self.save()


class RobotMeasurement:
    def __init__(self, robot):
        self.robot = robot
        self.rows = []
        self.index = 0
        self.arrived = False
        self.directory = new_report()
        self.z = float(config.PICK_Z)
        self.plans = [robot.board_to_pose_bilinear(*cell, config.SAFE_Z, rotation=config.PICK_TOOL_ROTATION)
                      for cell in REFERENCE_CELLS]
        if not np.isfinite([self.z, config.SAFE_Z]).all() or self.z > config.SAFE_Z:
            raise ValueError('PICK_Z / SAFE_Z không hợp lệ.')
        for pose in self.plans:
            if len(pose) != 6 or not np.isfinite(pose).all() or pose[2] != config.SAFE_Z:
                raise ValueError('Kế hoạch robot không hợp lệ; kiểm tra config và R1–R4.')
        (self.directory / 'robot-metadata.json').write_text(json.dumps(dict(
            tool=robot.tool_num, user=robot.user_num, rotation=config.PICK_TOOL_ROTATION,
            measurement_z=self.z, safe_z=config.SAFE_Z, offset_x=config.OFFSET_X,
            offset_y=config.OFFSET_Y, teaching_points=robot.teaching_points,
            mapping='production visual-pick bilinear', interface='guided client',
        ), indent=2), encoding='utf-8')
        save_csv(self.directory / 'robot-plan.csv', [dict(col=c, row=r, x=p[0], y=p[1], z=p[2])
                                                   for (c, r), p in zip(REFERENCE_CELLS, self.plans)])

    def move(self, current):
        if self.arrived or self.index >= len(self.plans):
            raise RuntimeError('Điểm này đã chạy hoặc đã đo hết.')
        if len(current) != 3 or not np.isfinite(current).all() or current[2] < config.SAFE_Z:
            raise ValueError(f'Nâng bằng pendant tới Z ≥ {config.SAFE_Z}mm trước khi chạy.')
        if not self.robot.connected:
            raise RuntimeError('Robot chưa kết nối.')
        for label, action in (('Mode', lambda: self.robot.robot.Mode(0)),
                              ('RobotEnable', lambda: self.robot.robot.RobotEnable(1))):
            result = action()
            if result != 0:
                raise RuntimeError(f'{label}: lỗi {result}')
        pose = self.plans[self.index]
        travel = pose.copy()
        travel[2] = current[2]
        for target in (travel, pose):
            result = self.robot.move_safe_pose(target, speed=10, label='Guided grid measurement')
            if result != 0:
                raise RuntimeError(f'MoveCart lỗi {result}; kiểm tra vị trí thật trước khi tiếp tục.')
        self.arrived = True

    def record(self, aligned):
        if not self.arrived:
            raise RuntimeError('Chưa chạy đến điểm chuẩn.')
        entry = robot_xy_error(REFERENCE_CELLS[self.index], self.plans[self.index], aligned, self.z)
        self.rows.append(entry)
        save_csv(self.directory / 'grid-robot.csv', self.rows)
        self.index += 1
        self.arrived = False
        return entry


def capture_camera():
    cap = cv2.VideoCapture(config.VIDEO_SOURCE, cv2.CAP_DSHOW)
    try:
        if not cap.isOpened():
            raise RuntimeError(f'Không mở được camera {config.VIDEO_SOURCE}. Đóng RUN.bat và kiểm tra USB.')
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        frame = None
        for _ in range(40):
            ok, candidate = cap.read()
            if ok:
                frame = candidate
            time.sleep(.02)
        if frame is None:
            raise RuntimeError('Camera không trả về ảnh.')
        return frame
    finally:
        cap.release()


def connect_robot():
    from src.hardware.robot_VIP import FR5Robot, robot_sdk_core
    if config.DRY_RUN or robot_sdk_core is None:
        raise RuntimeError('Cần DRY_RUN=False và SDK robot để đo thật.')
    robot = FR5Robot()
    # Avoid normal connect(): that method pulses the gripper at startup.
    robot.robot = robot_sdk_core.RPC(robot.ip)
    try:
        time.sleep(2)
        robot.connected = bool(robot.robot.SDK_state)
        if not robot.connected:
            raise RuntimeError('SDK chưa kết nối robot.')
        robot._load_teaching_points()
        return RobotMeasurement(robot)
    except Exception:
        robot.robot.CloseRPC()
        raise


class MeasurementClient(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Xiangqi • Đo sai số Camera / Robot')
        self.geometry('1080x830')
        self.configure(bg='#f6efdc')
        self.busy = False
        self.messages = queue.Queue()
        self.robot_session = None
        self.camera_session = None
        self.report_paths = []
        self.heading = tk.StringVar()
        self.instructions = tk.StringVar()
        self.status = tk.StringVar(value='Chọn phép đo để bắt đầu.')
        ttk.Label(self, textvariable=self.heading, font=('Segoe UI', 20, 'bold')).pack(pady=(16, 8))
        ttk.Label(self, textvariable=self.instructions, wraplength=1000, justify='left',
                  font=('Segoe UI', 11)).pack(padx=30, anchor='w')
        self.body = ttk.Frame(self)
        self.body.pack(fill='both', expand=True, padx=30, pady=14)
        ttk.Label(self, textvariable=self.status, wraplength=1000, font=('Segoe UI', 10)).pack(padx=30, pady=12, anchor='w')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)
        self.home()

    def clear(self, title, instructions):
        self.heading.set(title)
        self.instructions.set(instructions)
        for child in self.body.winfo_children():
            child.destroy()

    def button(self, text, command):
        def guarded():
            if not self.busy:
                command()
        ttk.Button(self.body, text=text, command=guarded).pack(pady=6, anchor='w')

    def run(self, job, success):
        if self.busy:
            return
        self.busy = True
        self.status.set('Đang thực hiện… vui lòng chờ. Các nút tạm khóa.')
        def worker():
            try:
                self.messages.put((success, job(), None))
            except Exception as exc:
                self.messages.put((success, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            callback, result, error = self.messages.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            if error:
                self.status.set(error)
                messagebox.showerror('Chưa thể tiếp tục', error)
            else:
                self.status.set('Hoàn tất bước hiện tại.')
                try:
                    callback(result)
                except Exception as exc:
                    self.status.set(str(exc))
                    messagebox.showerror('Chưa thể tiếp tục', str(exc))
        self.after(100, self.poll)

    def home(self):
        self.clear('Đo riêng Camera → Grid và Grid → Robot',
                   'Đóng RUN.bat trước khi đo. Giữ bàn/camera cố định. Chọn Camera trước, sau đó Robot.\n'
                   'Kết quả lưu tự động; không cần ghi chép công thức hoặc dùng lệnh console.')
        self.button('1. Đo Camera → Grid', self.camera_prepare)
        self.button('2. Đo Grid → Robot', self.robot_prepare)
        self.button('Mở thư mục kết quả', lambda: self.open_reports())
        if self.report_paths:
            ttk.Label(self.body, text='Đã lưu:\n' + '\n'.join(map(str, self.report_paths)), wraplength=950).pack(anchor='w', pady=15)

    def checks(self, labels):
        variables = []
        for label in labels:
            var = tk.BooleanVar(value=False)
            ttk.Checkbutton(self.body, text=label, variable=var).pack(anchor='w', pady=5)
            variables.append(var)
        return variables

    def require(self, checks, action):
        if not all(var.get() for var in checks):
            messagebox.showinfo('Chuẩn bị trước', 'Đánh dấu đủ các điều kiện sau khi đã thực hiện.')
            return
        action()

    def camera_prepare(self):
        self.clear('Camera • Bước 1: chuẩn bị',
                   'Dọn quân che 9 giao điểm chuẩn. Công cụ chụp một ảnh đứng yên để bạn click.\n'
                   'Click đường kẻ IN THẬT, không theo lưới vàng, viền trang trí hoặc tâm quân.')
        checks = self.checks(['Đã đóng RUN.bat; camera không bị ứng dụng khác chiếm.',
                              'Camera/bàn, độ phân giải và crop giống lúc tạo perspective.npy.',
                              'Đã thấy rõ giao điểm giữa bàn, bốn góc và giữa các cạnh.'])
        def start(image_path=None):
            def capture():
                frame = cv2.imread(image_path) if image_path else capture_camera()
                if frame is None:
                    raise RuntimeError('Không đọc được ảnh.')
                return CameraMeasurement(frame, np.load(ROOT / 'perspective.npy'))
            self.run(capture, self.camera_ready)
        self.button('Đã chuẩn bị → chụp camera', lambda: self.require(checks, start))
        def choose_image():
            path = filedialog.askopenfilename(filetypes=[('Ảnh camera', '*.png *.jpg *.jpeg *.bmp')])
            if path:
                start(path)
        self.button('Hoặc mở ảnh camera gốc cùng calibration', lambda: self.require(checks, choose_image))
        self.button('Về menu', self.home)

    def camera_ready(self, session):
        self.camera_session = session
        self.report_paths.append(session.directory)
        self.camera_page()

    def camera_page(self):
        session = self.camera_session
        index = len(session.rows)
        if index == len(REFERENCE_CELLS):
            self.clear('Camera • Đã đo đủ 9 điểm', 'Ảnh gốc, overlay, ma trận và CSV đã lưu. Có thể đo lại một lần để so độ ổn định.')
            ttk.Label(self.body, text='\n'.join(f"({r['expected_col']},{r['expected_row']}): "
                      f"Δc={r['delta_col']:+.4f}, Δr={r['delta_row']:+.4f}, lệch={r['error_cells']:.4f} ô" for r in session.rows)).pack(anchor='w')
            self.button('Sửa điểm cuối', self.camera_undo)
            self.button('Tiếp tục đo Robot / về menu', self.home)
            return
        cell = REFERENCE_CELLS[index]
        self.clear(f'Camera • Điểm {index + 1}/9: giao điểm {cell}',
                   f'Click đúng giao điểm thật tại cột {cell[0]}, hàng {cell[1]}.\n'
                   'Gốc (0,0) = P0; (8,0) = P1; (8,9) = P2; (0,9) = P3 của calibration.\n'
                   'Hàng 0 phía ĐEN, hàng 9 phía ĐỎ; hàng 4 là mép sông phía ĐEN. Đếm từ 0.\n'
                   'Click đường IN THẬT, không theo lưới vàng. Di chuột để phóng to; click nhầm thì Bỏ điểm cuối.')
        image = session.save()
        h, w = image.shape[:2]
        scale = min(780 / w, 440 / h)
        resize_w, resize_h = int(round(w * scale)), int(round(h * scale))
        self.camera_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).resize((resize_w, resize_h)))
        image_panel = ttk.Frame(self.body)
        image_panel.pack(anchor='w')
        canvas = tk.Canvas(image_panel, width=780, height=440, bg='#232e2a', highlightthickness=0)
        canvas.pack(side='left')
        canvas.create_image(390, 220, image=self.camera_photo)
        side = ttk.Frame(image_panel)
        side.pack(side='left', padx=12, anchor='n')
        self.board_guide(side, cell)
        magnifier = ttk.Label(side, text='Phóng to\nở con trỏ')
        magnifier.pack(pady=8)
        def click(event):
            pixel = canvas_to_pixel(event.x, event.y, w, h)
            if pixel and not self.busy:
                session.click(pixel)
                last = session.rows[-1]
                self.status.set(f"Đã lưu: Δc={last['delta_col']:+.4f}, Δr={last['delta_row']:+.4f}, lệch={last['error_cells']:.4f} ô.")
                self.camera_page()
        def hover(event):
            pixel = canvas_to_pixel(event.x, event.y, w, h)
            if not pixel:
                return
            x, y = map(round, pixel)
            left, top = max(0, x-18), max(0, y-18)
            crop = session.frame[top:min(h, y+19), left:min(w, x+19)].copy()
            cv2.drawMarker(crop, (x-left, y-top), (0, 0, 255), cv2.MARKER_CROSS, 9, 1)
            self.zoom_photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)).resize((111, 111)))
            magnifier.configure(image=self.zoom_photo)
        canvas.bind('<Button-1>', click)
        canvas.bind('<Motion>', hover)
        self.button('Bỏ điểm cuối', self.camera_undo)
        self.button('Kết thúc và về menu (đã lưu)', self.home)

    def camera_undo(self):
        self.camera_session.undo()
        self.camera_page()

    def robot_prepare(self):
        self.clear('Robot • Bước 1: chuẩn bị',
                   f'Đo đúng phép nội suy visual pick. Robot chỉ đi ở SAFE_Z={config.SAFE_Z}mm, không tự gắp.\n'
                   f'Bạn hạ/căn bằng pendant tại Z={config.PICK_Z}mm. Mọi XYZ nhập phải thuộc Tool 0 / User 1.')
        checks = self.checks(['Đã đóng RUN.bat, vùng chuyển động và các điểm chuẩn đã được dọn.',
                              'Đã xác nhận Tool 0 / User 1 trên pendant và đúng góc ngàm.',
                              'Biết cách jog chậm, nâng Z và dừng robot bằng pendant.'])
        def start():
            if self.robot_session:
                self.robot_session.robot.robot.CloseRPC()
                self.robot_session = None
            self.run(connect_robot, self.robot_ready)
        self.button('Đã chuẩn bị → đọc R1–R4 (chưa chạy arm)',
                    lambda: self.require(checks, start))
        self.button('Về menu', self.home)

    def robot_ready(self, session):
        self.robot_session = session
        self.report_paths.append(session.directory)
        self.robot_page()

    def xyz_entry(self):
        ttk.Label(self.body, text='Nhập X Y Z (mm), ví dụ: 300 100 210', font=('Segoe UI', 11)).pack(anchor='w', pady=8)
        value = tk.StringVar()
        ttk.Entry(self.body, textvariable=value, width=45, font=('Segoe UI', 14)).pack(anchor='w', pady=6)
        return value

    def board_guide(self, parent, cell):
        diagram = tk.Canvas(parent, width=180, height=245, bg='#f6efdc', highlightthickness=0)
        diagram.pack(anchor='w')
        diagram.create_text(90, 12, text='ĐEN — hàng 0 / P0 → P1')
        for col in range(9):
            x = 22 + col * 17
            diagram.create_line(x, 42, x, 195, fill='#888888')
            diagram.create_text(x, 29, text=str(col))
        for row in range(10):
            y = 42 + row * 17
            diagram.create_line(22, y, 158, y, fill='#888888')
            diagram.create_text(9, y, text=str(row))
        diagram.create_rectangle(23, 111, 157, 126, fill='#f6efdc', outline='')
        diagram.create_text(90, 119, text='SÔNG', fill='#777777')
        x, y = 22 + cell[0] * 17, 42 + cell[1] * 17
        diagram.create_oval(x-5, y-5, x+5, y+5, fill='red', outline='red')
        diagram.create_text(90, 216, text='ĐỎ — hàng 9 / P3 → P2')
        diagram.create_text(90, 236, text=f'Điểm cần đo: {cell}')

    def robot_page(self):
        session = self.robot_session
        if session.index == len(REFERENCE_CELLS):
            self.clear('Robot • Đã đo đủ 9 điểm', 'CSV đã lưu. Dùng pendant nâng về vị trí an toàn; client không tự HOME.')
            ttk.Label(self.body, text='\n'.join(f"({r['col']},{r['row']}): ΔX={r['delta_x_mm']:+.3f}, ΔY={r['delta_y_mm']:+.3f} mm" for r in session.rows)).pack(anchor='w')
            self.button('Về menu / mở kết quả', self.home)
            return
        cell, pose = REFERENCE_CELLS[session.index], session.plans[session.index]
        if not session.arrived:
            self.clear(f'Robot • Điểm {session.index + 1}/9 {cell} — nâng trước khi chạy',
                       f'1. Dùng pendant nâng Z ≥ {config.SAFE_Z}mm.\n'
                       '2. Đọc XYZ hiện tại trong Tool 0 / User 1, nhập bên dưới.\n'
                       f'3. Bấm Chạy: robot sẽ chuyển AUTO, đi chậm tới X={pose[0]:.3f}, Y={pose[1]:.3f} ở trên cao.')
            self.board_guide(self.body, cell)
            value = self.xyz_entry()
            checks = self.checks(['Đã nâng thật đến SAFE_Z, nhập đúng hệ tọa độ; vùng chuyển động thông thoáng.'])
            def move():
                try:
                    current = parse_xyz(value.get())
                    if current[2] < config.SAFE_Z:
                        raise ValueError(f'Z phải ≥ {config.SAFE_Z}mm.')
                except ValueError as exc:
                    messagebox.showerror('XYZ chưa hợp lệ', str(exc))
                    return
                self.run(lambda: session.move(current), lambda _: self.robot_page())
            self.button('Chạy arm tới điểm chuẩn ở trên cao', lambda: self.require(checks, move))
        else:
            self.clear(f'Robot • Điểm {session.index + 1}/9 {cell} — căn và ghi số đo',
                       '1. Chuyển chế độ jog trên pendant; giữ cùng góc ngàm.\n'
                       f'2. Hạ chậm đến Z={session.z}mm, căn tâm ngàm vào giao điểm thật.\n'
                       f'3. Nhập XYZ đã căn (Tool 0 / User 1). XY ra lệnh ban đầu: {pose[0]:.3f}, {pose[1]:.3f}.')
            self.board_guide(self.body, cell)
            value = self.xyz_entry()
            checks = self.checks(['Tâm ngàm đã căn đúng giao điểm, cùng chiều cao/góc và Tool 0 / User 1.'])
            def record():
                try:
                    entry = session.record(parse_xyz(value.get()))
                except (ValueError, RuntimeError) as exc:
                    messagebox.showerror('Chưa ghi được', str(exc))
                    return
                self.status.set(f"Đã lưu: ΔX={entry['delta_x_mm']:+.3f}mm, ΔY={entry['delta_y_mm']:+.3f}mm. Nâng Z trước điểm kế tiếp.")
                self.robot_page()
            self.button('Lưu sai số → điểm kế tiếp', lambda: self.require(checks, record))
        self.button('Dừng đo và về menu (không tự HOME)', self.home)

    def open_reports(self):
        directory = ROOT / 'measurement_reports'
        directory.mkdir(exist_ok=True)
        os.startfile(str(directory))

    def close(self):
        if self.busy:
            messagebox.showinfo('Đang thực hiện', 'Chờ tác vụ kết thúc. Nếu cần dừng chuyển động, dùng nút dừng trên pendant.')
            return
        try:
            if self.robot_session:
                self.robot_session.robot.robot.CloseRPC()
        finally:
            self.destroy()


def launch():
    MeasurementClient().mainloop()
