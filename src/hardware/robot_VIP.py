# ==================================
# === FILE: VIP/robot_VIP.py ===
# === Điều khiển cánh tay robot FR5 — phiên bản VIP ===
# === Dựa trên robot.py gốc, dùng Controller DO2 (bộ điều khiển) ===
# ==================================
import time
import sys
import os
import json
import numpy as np
import cv2

# Đảm bảo import được config từ thư mục gốc project
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(os.path.dirname(_THIS_DIR))
sys.path.insert(0, _PROJECT_DIR)
import config

try:
    from src.hardware import robot_sdk_core
except ImportError:
    print("LỖI: Không tìm thấy module 'robot_sdk_core'...")
    robot_sdk_core = None


class FR5Robot:
    def __init__(self, ip=None):
        self.ip          = ip or config.ROBOT_IP
        self.robot       = None
        self.connected   = False
        self.dry         = config.DRY_RUN
        self.tool_num    = 0
        self.user_num    = 1
        self.default_vel = config.MOVE_SPEED

        # ⚙️ Kẹp: dùng Tool DO0 (Đầu cánh tay - cáp M12)
        self.gripper_do_id = 0

        # Ma trận hiệu chỉnh perspective (được set từ main_VIP.py)
        self.perspective_matrix = None
        
        # Cache teaching points để tránh Singularity
        self.teaching_points = {}  # {name: {"pose": [x,y,z,rx,ry,rz], "joints": [j1..j6]}}
        self.use_teaching_points = True  # Luôn dùng teaching points

        # Kích thước ô cờ (mm), mặc định theo config, tự động cập nhật khi load teaching points
        self.auto_cell_sizes = {"x": config.CELL_SIZE_X, "y": config.CELL_SIZE_Y}

    # -------------------------------------------------------------------------
    # SET MA TRẬN TỪ NGOÀI
    # -------------------------------------------------------------------------

    def set_perspective_matrix(self, matrix):
        """Nhận ma trận hiệu chỉnh từ main_VIP.py và lưu nó."""
        print("[ROBOT] ✅ Đã nhận và lưu Ma trận Hiệu chỉnh.")
        self.perspective_matrix = matrix

    # -------------------------------------------------------------------------
    # KẾT NỐI
    # -------------------------------------------------------------------------

    def connect(self):
        if self.dry:
            print("[ROBOT] DRY RUN — không kết nối thực tế")
            self.connected = True
            return

        if robot_sdk_core is None:
            raise Exception("Module robot_sdk_core chưa được import.")

        try:
            self.robot = robot_sdk_core.RPC(self.ip)
            time.sleep(2)
            self.connected = self.robot.SDK_state
            if not self.connected:
                raise Exception("SDK không thể kết nối tới robot")

            print(f"[ROBOT] ✅ Đã kết nối tới {self.ip}")

            err = self.robot.RobotEnable(1)
            if err != 0:
                print(f"[ROBOT] ⚠️ RobotEnable thất bại, code={err}")

            err = self.robot.Mode(0)
            if err != 0:
                print(f"[ROBOT] ⚠️ Set Mode(0) thất bại, code={err}")
            
            # Load teaching points để tránh Singularity
            self._load_teaching_points()

        except Exception as e:
            print(f"[ROBOT] ❌ Lỗi connect: {e}")
            self.connected = False
            raise
    
    def _load_teaching_points(self):
        """Đọc teaching points R1, R2, R3, R4 để tính toán Bilinear Interpolation."""
        if not self.connected or self.dry:
            return
        
        print("[ROBOT] 📍 Đang load teaching points...")
        
        # Load 4 góc bàn cờ (bắt buộc)
        point_names = ["R1", "R2", "R3", "R4"]
        
        for name in point_names:
            try:
                err, data = self.robot.GetRobotTeachingPoint(name)
                if err == 0 and len(data) >= 12:  # data = [x,y,z,rx,ry,rz, j1,j2,j3,j4,j5,j6]
                    # Safe convert string to float
                    pose_data = [float(str(data[i]).strip()) for i in range(6)]
                    joint_data = [float(str(data[i]).strip()) for i in range(6, 12)]
                    
                    self.teaching_points[name] = {
                        "pose": pose_data,
                        "joints": joint_data
                    }
                    print(f"[ROBOT]   ✅ Loaded {name}: X={pose_data[0]:.1f}, Y={pose_data[1]:.1f}, Z={pose_data[2]:.1f}")
                else:
                    raise Exception(f"Teaching point {name} không tồn tại (err={err})")
            except Exception as e:
                print(f"[ROBOT]   ❌ Lỗi đọc {name}: {e}")
                raise Exception(f"Thiếu teaching point {name} - Hệ thống không thể hoạt động")
        
        # Tính CELL_SIZE tự động từ 4 góc
        self._calculate_cell_sizes_from_corners()
        
        # Load R_Trash (optional - không bắt buộc)
        try:
            err, data = self.robot.GetRobotTeachingPoint("R_Trash")
            if err == 0 and len(data) >= 12:
                pose_data = [float(str(data[i]).strip()) for i in range(6)]
                joint_data = [float(str(data[i]).strip()) for i in range(6, 12)]
                
                self.teaching_points["R_Trash"] = {
                    "pose": pose_data,
                    "joints": joint_data
                }
                print(f"[ROBOT]   ✅ Loaded R_Trash: X={pose_data[0]:.1f}, Y={pose_data[1]:.1f}, Z={pose_data[2]:.1f}")
            else:
                print(f"[ROBOT]   ⚠️ R_Trash không tồn tại, sẽ dùng tọa độ config backup")
        except Exception as e:
            print(f"[ROBOT]   ⚠️ Không load được R_Trash: {e} (sẽ dùng config backup)")
        
        print(f"[ROBOT] ✅ Đã load {len(self.teaching_points)} teaching points")
        print(f"[ROBOT] 🎯 Sử dụng Bilinear Interpolation cho tất cả vị trí")

    # -------------------------------------------------------------------------
    # CHUYỂN ĐỔI TỌA ĐỘ BÀN CỜ → ROBOT
    # -------------------------------------------------------------------------
    
    def _get_teaching_point_for_position(self, col, row):
        """Kiểm tra xem vị trí (col, row) có teaching point tương ứng không."""
        # Mapping các vị trí đặc biệt với teaching points
        position_map = {
            (8, 0): "R2",  # Xe Đen Phải
            (8, 9): "R3",  # Xe Đỏ Phải  
            (0, 9): "R4",  # Xe Đỏ Trái
        }
        
        point_name = position_map.get((col, row))
        if point_name and point_name in self.teaching_points:
            return point_name, self.teaching_points[point_name]
        return None, None

    def board_to_pose(self, col, row, z_height, rotation=None):
        """Chuyển grid logic thành pose thật từ R1-R4.

        ``rotation`` là [Rx, Ry, Rz] của tool trong hệ pose FR5. Không truyền
        rotation sẽ giữ tương thích hoàn toàn với ``config.ROTATION`` cũ.
        """
        
        # Kiểm tra xem có teaching point trực tiếp cho vị trí cụ thể không
        point_name, point_data = self._get_teaching_point_for_position(col, row)
        if point_data:
            # Dùng tọa độ từ teaching point nhưng thay đổi Z
            pose = point_data["pose"].copy()
            pose[2] = z_height  # Thay đổi Z theo yêu cầu
            if rotation is not None:
                pose[3:6] = self._validated_rotation(rotation)
            print(f"[ROBOT] 📍 Dùng teaching point {point_name} cho ({col},{row}) → X={pose[0]:.1f}, Y={pose[1]:.1f}, Z={z_height:.1f}")
            return pose
        
        # Sử dụng Bilinear Interpolation cho tất cả vị trí khác
        return self.board_to_pose_bilinear(col, row, z_height, rotation=rotation)

    @staticmethod
    def _validated_rotation(rotation):
        """Return a copy of a Cartesian tool rotation, rejecting malformed config."""
        if not isinstance(rotation, (list, tuple)) or len(rotation) != 3:
            raise ValueError("Tool rotation must be a three-value [Rx, Ry, Rz] sequence")
        return [float(value) for value in rotation]

    def _calculate_cell_sizes_from_corners(self):
        """Tính CELL_SIZE tự động từ 4 góc teaching points."""
        r1 = self.teaching_points["R1"]["pose"]  # (0,0) - Đen Trái
        r2 = self.teaching_points["R2"]["pose"]  # (8,0) - Đen Phải  
        r3 = self.teaching_points["R3"]["pose"]  # (8,9) - Đỏ Phải
        r4 = self.teaching_points["R4"]["pose"]  # (0,9) - Đỏ Trái
        
        # Tính khoảng cách theo chiều Y (ngang - col)
        distance_y_top = abs(r2[1] - r1[1])     # R1 → R2: 8 ô ngang
        distance_y_bottom = abs(r3[1] - r4[1])  # R4 → R3: 8 ô ngang
        cell_size_x = (distance_y_top + distance_y_bottom) / (2 * 8)
        
        # Tính khoảng cách theo chiều X (dọc - row)  
        distance_x_left = abs(r4[0] - r1[0])    # R1 → R4: 9 ô dọc
        distance_x_right = abs(r3[0] - r2[0])   # R2 → R3: 9 ô dọc
        cell_size_y = (distance_x_left + distance_x_right) / (2 * 9)
        
        self.auto_cell_sizes = {"x": cell_size_x, "y": cell_size_y}

        print(f"[ROBOT] 📏 Tự động tính CELL_SIZE từ 4 góc:")
        print(f"[ROBOT]   CELL_SIZE_X = {cell_size_x:.2f}mm (ngang)")
        print(f"[ROBOT]   CELL_SIZE_Y = {cell_size_y:.2f}mm (dọc)")
        print(f"[ROBOT]   Distance Y: top={distance_y_top:.1f}mm, bottom={distance_y_bottom:.1f}mm")
        print(f"[ROBOT]   Distance X: left={distance_x_left:.1f}mm, right={distance_x_right:.1f}mm")

    def board_to_pose_bilinear(self, col, row, z_height, rotation=None):
        """Tính pose vật lý từ grid float qua Bilinear Interpolation R1-R4.

        Grid float được Visual Pick cung cấp chỉ bù XY. Tool orientation luôn
        lấy từ motion profile đã dạy, không nội suy Euler angles của các corner
        teaching points vì cách đó có thể tạo pose wrist không mong muốn.
        """
        try:
            # Tọa độ logic (0-8 cho col, 0-9 cho row)
            col_ratio = col / 8.0  # 0.0 → 1.0
            row_ratio = row / 9.0  # 0.0 → 1.0
            
            # 4 góc teaching points
            r1 = self.teaching_points["R1"]["pose"]  # (0,0) - Đen Trái
            r2 = self.teaching_points["R2"]["pose"]  # (8,0) - Đen Phải
            r3 = self.teaching_points["R3"]["pose"]  # (8,9) - Đỏ Phải  
            r4 = self.teaching_points["R4"]["pose"]  # (0,9) - Đỏ Trái
            
            # Nội suy theo chiều ngang (col) - Hàng trên (row=0)
            top_x = r1[0] + (r2[0] - r1[0]) * col_ratio
            top_y = r1[1] + (r2[1] - r1[1]) * col_ratio
            
            # Nội suy theo chiều ngang (col) - Hàng dưới (row=9)
            bottom_x = r4[0] + (r3[0] - r4[0]) * col_ratio
            bottom_y = r4[1] + (r3[1] - r4[1]) * col_ratio
            
            # Nội suy theo chiều dọc (row)
            final_x = top_x + (bottom_x - top_x) * row_ratio
            final_y = top_y + (bottom_y - top_y) * row_ratio
            
            # Áp dụng offset điều chỉnh
            final_x += config.OFFSET_X
            final_y += config.OFFSET_Y
            
            # Kiểm tra tọa độ an toàn
            if abs(final_x) > 900 or abs(final_y) > 900:
                print(f"[ROBOT] ⚠️ Tọa độ quá xa ({final_x:.1f}, {final_y:.1f}) — cẩn thận đập máy!")
            
            print(f"[ROBOT] 🎯 Bilinear Interpolation ({col},{row}) → X={final_x:.1f}, Y={final_y:.1f}, Z={z_height:.1f}")
            print(f"[ROBOT]   Ratios: col={col_ratio:.3f}, row={row_ratio:.3f}")
            
            tool_rotation = self._validated_rotation(
                config.ROTATION if rotation is None else rotation
            )
            return [final_x, final_y, z_height] + tool_rotation
            
        except Exception as e:
            print(f"[ROBOT] ⚠️ Lỗi Bilinear Interpolation: {e}, fallback sang linear")
            return self.board_to_pose_linear(col, row, z_height, rotation=rotation)

    def board_to_pose_linear(self, col, row, z_height, rotation=None):
        """Tính tọa độ bằng phương pháp linear từ R1 + CELL_SIZE (fallback)."""
        # Dùng CELL_SIZE tự động tính nếu có, không thì dùng config
        cell_x = self.auto_cell_sizes["x"]
        cell_y = self.auto_cell_sizes["y"]
        
        # Lấy gốc từ R1 nếu có, không thì dùng config
        if "R1" in self.teaching_points:
            origin_x = self.teaching_points["R1"]["pose"][0]
            origin_y = self.teaching_points["R1"]["pose"][1]
        else:
            origin_x = config.BOARD_ORIGIN_X
            origin_y = config.BOARD_ORIGIN_Y
        
        # Tính delta khoảng cách từ ô gốc (0,0)
        delta_x = row * cell_y  # row ảnh hưởng X (dọc)
        delta_y = col * cell_x  # col ảnh hưởng Y (ngang)
        
        # Bù thêm khe hở Sông (River gap) cho các quân nằm phía Đỏ (row >= 5)
        if row >= 5:
            delta_x += config.RIVER_GAP_Y
            
        # Áp dụng hướng (Direction) và cộng với Tọa độ gốc
        x_mm = origin_x + (delta_x * config.ROBOT_DIR_X) + config.OFFSET_X
        y_mm = origin_y + (delta_y * config.ROBOT_DIR_Y) + config.OFFSET_Y

        # Kiểm tra tọa độ an toàn
        if abs(x_mm) > 900 or abs(y_mm) > 900:
            print(f"[ROBOT] ⚠️ Tọa độ quá xa ({x_mm:.1f}, {y_mm:.1f}) — cẩn thận đập máy!")

        print(f"[ROBOT] 📐 Linear calculation ({col},{row}) → X={x_mm:.1f}, Y={y_mm:.1f}, Z={z_height:.1f}")
        print(f"[ROBOT]   CELL_SIZE: X={cell_x:.2f}, Y={cell_y:.2f}")
        
        tool_rotation = self._validated_rotation(
            config.ROTATION if rotation is None else rotation
        )
        return [x_mm, y_mm, z_height] + tool_rotation

    # -------------------------------------------------------------------------
    # DI CHUYỂN ROBOT
    # -------------------------------------------------------------------------

    def move_safe_pose(self, pose, speed=None, col=None, row=None):
        """Di chuyển an toàn đến pose. Luôn dùng MoveCart để đảm bảo đường thẳng."""
        vel = speed or self.default_vel
        if self.dry:
            print(f"[ROBOT] DRY MoveCart → {[round(v,1) for v in pose]} vel={vel}")
            time.sleep(0.2)
            return 0

        # Luôn dùng MoveCart để đảm bảo di chuyển thẳng, tránh đá quân cờ
        err = self.robot.MoveCart(
            desc_pos=pose, tool=self.tool_num, user=self.user_num,
            vel=vel, acc=0.0, ovl=100.0, blendT=-1.0, config=-1
        )
        if err not in (0, 112):
            print(f"[ROBOT] ❌ Lỗi MoveCart: {err}")
            raise Exception(f"Robot MoveCart error code: {err}")
        return err

    def movej_joint(self, joint_pos, desc_pos, speed=None):
        """Di chuyển trực tiếp bằng góc joint (MoveJ) nếu đã biết."""
        vel = speed or self.default_vel
        if self.dry:
            print(f"[ROBOT] DRY MoveJ_Joint → vel={vel}")
            time.sleep(0.2)
            return 0
            
        err = self.robot.MoveJ(
            joint_pos=joint_pos, desc_pos=desc_pos, tool=self.tool_num, user=self.user_num,
            vel=vel, acc=0.0, ovl=100.0, exaxis_pos=[0]*4, blendT=-1.0, offset_flag=0, offset_pos=[0]*6
        )
        if err not in (0, 112):
            print(f"[ROBOT] ❌ Lỗi movej_joint MoveJ: {err}")
            raise Exception(f"Robot movej_joint error code: {err}")
        return err

    def movel_pose(self, pose, speed=None):
        """Di chuyển thẳng đứng (MoveCart) đến pose."""
        vel = speed or self.default_vel
        if self.dry:
            print(f"[ROBOT] DRY MoveL → {[round(v,1) for v in pose]} vel={vel}")
            time.sleep(0.2)
            return 0

        err = self.robot.MoveCart(
            desc_pos=pose, tool=self.tool_num, user=self.user_num,
            vel=vel, acc=0.0, ovl=100.0, blendT=-1.0, config=-1
        )
        if err not in (0, 112):
            print(f"[ROBOT] ❌ Lỗi MoveCart (movel): {err}")
            raise Exception(f"Robot MoveCart error code: {err}")
        return err

    # -------------------------------------------------------------------------
    # VỀ NHÀ
    # -------------------------------------------------------------------------

    def go_to_idle_home(self):
        """Đưa robot về vị trí chờ an toàn (IDLE)."""
        print("[ROBOT] Về vị trí IDLE...")
        pose = [config.IDLE_X, config.IDLE_Y, config.IDLE_Z] + list(config.ROTATION)
        try:
            self.move_safe_pose(pose)
        except Exception as e:
            print(f"[ROBOT] ⚠️ Lỗi khi về IDLE trực tiếp: {e}. Thử nâng Z lên cao...")
            # Nâng Z an toàn trước khi di chuyển
            try:
                high_z_pose = [config.IDLE_X, config.IDLE_Y, config.IDLE_Z + 100.0] + list(config.ROTATION)
                self.move_safe_pose(high_z_pose)
                self.move_safe_pose(pose)
            except Exception as e2:
                print(f"[ROBOT] ❌ Lỗi cả khi qua điểm trung gian Z cao: {e2}")

    def go_to_home_chess(self):
        """Về vị trí HOMECHESS đã dạy trên bộ điều khiển."""
        print("[ROBOT] Về vị trí HOMECHESS...")
        if self.dry:
            print("[ROBOT] DRY RUN — bỏ qua HOMECHESS")
            return
        if self.robot is None:
            print("[ROBOT] Chưa kết nối — không thể về HOMECHESS")
            return
        try:
            err, data = self.robot.GetRobotTeachingPoint("HOMECHESS")
            if err != 0:
                print(f"[ROBOT] ⚠️ Không đọc được HOMECHESS (err={err}) → về IDLE")
                self.go_to_idle_home()
                return
                
            # If data contains joint pos, use it directly (data is typically >= 12 elements)
            pose = list(data[:6])
            
            if len(data) >= 12:
                joints = list(data[6:12])
                print(f"[ROBOT] Đọc được joints HOMECHESS: {joints}")
                try:
                    self.movej_joint(joints, pose)
                    print("[ROBOT] ✅ Đã về HOMECHESS (bằng Joint).")
                    return
                except Exception as je:
                    print(f"[ROBOT] ⚠️ Lỗi MoveJ bằng khớp: {je}. Tiếp tục thử MoveJ Pose...")
                    
            # Fallback to MoveJ with pose
            self.move_safe_pose(pose)
            print("[ROBOT] ✅ Đã về HOMECHESS (bằng Pose).")
            
        except Exception as e:
            print(f"[ROBOT] ⚠️ go_to_home_chess lỗi: {e} → về IDLE")
            self.go_to_idle_home()

    # -------------------------------------------------------------------------
    # GRIPPER — Controller DO2
    # -------------------------------------------------------------------------

    def gripper_ctrl(self, val):
        """Điều khiển kẹp qua Controller DO2 (bộ điều khiển, không phải Tool DO).
        
        val = config.GRIPPER_CLOSE (1) → Đóng kẹp
        val = config.GRIPPER_OPEN  (0) → Mở kẹp
        """
        if self.dry:
            action = "ĐÓNG" if val == config.GRIPPER_CLOSE else "MỞ"
            print(f"[ROBOT] DRY Gripper (SetDO ID={self.gripper_do_id}) → {action}")
            time.sleep(0.3)
            return 0

        # NẾU CẮM CÁP M12 8-PIN VÀO ĐẦU CÁNH TAY (Tool DO):
        # 1. Hãy dò tìm ID bằng file test_tool_do2.py trước (Thử ID=0, rồi ID=1)
        # 2. Sau khi biết ID thực (VD: 1), sửa self.gripper_do_id = 1 ở đầu file.
        # 3. Đổi hàm SetDO (dưới đây) thành SetToolDO:
        err = self.robot.SetToolDO(
            id=self.gripper_do_id,
            status=val,
            block=1
        )
        if err != 0:
            print(f"[ROBOT] ❌ Lỗi SetToolDO (gripper): {err}")
        return err

    # -------------------------------------------------------------------------
    # QUY TRÌNH GẮP / ĐẶT / ĂN QUÂN
    # -------------------------------------------------------------------------

    def pick_at(self, col, row, visual_target=None):
        """Gắp quân tại XY thực tế, với tool rotation đã dạy trong config.

        Khi ``visual_target`` hợp lệ, chính ``target.col,row`` (float) được
        dùng cho cả approach SAFE_Z và descent PICK_Z. Không có target thì
        fallback về tâm ô logic như hành vi cũ.
        """
        pick_rotation = getattr(config, "PICK_TOOL_ROTATION", config.ROTATION)
        if visual_target is not None:
            pose_safe = self.board_to_pose_bilinear(
                visual_target.col, visual_target.row, config.SAFE_Z, rotation=pick_rotation
            )
            pose_pick = self.board_to_pose_bilinear(
                visual_target.col, visual_target.row, config.PICK_Z, rotation=pick_rotation
            )
            print(f"[ROBOT] 👁️ Visual pick offset={visual_target.offset_cells:.3f} cells, "
                  f"conf={visual_target.confidence:.2f}")
        else:
            pose_safe = self.board_to_pose(col, row, config.SAFE_Z, rotation=pick_rotation)
            pose_pick = self.board_to_pose(col, row, config.PICK_Z, rotation=pick_rotation)
        print(f"[ROBOT] 🤏 Gắp tại grid=({col},{row}) → X={pose_safe[0]:.1f}, Y={pose_safe[1]:.1f}, Z={pose_safe[2]:.1f}")

        self.gripper_ctrl(config.GRIPPER_OPEN)   # Mở kẹp
        self.move_safe_pose(pose_safe, col=col, row=row)  # Đi đến vị trí an toàn trên ô
        self.movel_pose(pose_pick)                # Hạ xuống
        self.gripper_ctrl(config.GRIPPER_CLOSE)  # Đóng kẹp (gắp)
        time.sleep(0.5)                           # Đợi kẹp đóng
        self.movel_pose(pose_safe)                # Nhấc lên
        print(f"[ROBOT] ✅ Gắp xong ({col},{row})")

    def place_at(self, col, row):
        """Đặt quân ở tâm ô đích vật lý theo R1-R4 và pose đặt đã dạy."""
        place_rotation = getattr(config, "PLACE_TOOL_ROTATION", config.ROTATION)
        pose_safe = self.board_to_pose(col, row, config.SAFE_Z, rotation=place_rotation)
        pose_place = self.board_to_pose(col, row, config.PLACE_Z, rotation=place_rotation)
        print(f"[ROBOT] 📍 Đặt tại grid=({col},{row}) → X={pose_safe[0]:.1f}, Y={pose_safe[1]:.1f}, Z={pose_safe[2]:.1f}")

        self.move_safe_pose(pose_safe, col=col, row=row)  # Đến vị trí an toàn
        self.movel_pose(pose_place)               # Hạ xuống
        self.gripper_ctrl(config.GRIPPER_OPEN)   # Mở kẹp (thả)
        time.sleep(0.5)                           # Đợi thả
        self.movel_pose(pose_safe)                # Nhấc lên
        print(f"[ROBOT] ✅ Đặt xong ({col},{row})")
    
    def move_to_extra_safe(self, col, row, visual_target=None):
        """Nâng tại đúng XY vừa gắp, tránh quay lại tâm ô khi camera đã bù XY."""
        pick_rotation = getattr(config, "PICK_TOOL_ROTATION", config.ROTATION)
        if visual_target is not None:
            pose_safe = self.board_to_pose_bilinear(
                visual_target.col, visual_target.row, config.SAFE_Z, rotation=pick_rotation
            )
        else:
            pose_safe = self.board_to_pose(col, row, config.SAFE_Z, rotation=pick_rotation)
        print(f"[ROBOT] ⬆️ Nâng lên độ cao an toàn tại ({col},{row}) Z={config.SAFE_Z}")
        self.move_safe_pose(pose_safe, col=col, row=row)

    def place_in_capture_bin(self, current_z=None):
        """Thả quân bị ăn vào bãi thải sử dụng teaching point R_Trash.
        
        Args:
            current_z: Độ cao hiện tại của robot (nếu None, dùng SAFE_Z)
        
        Logic:
            1. Về home trước (waypoint an toàn)
            2. Từ home đi đến R_Trash bằng MoveJ (sử dụng teaching point)
            3. Thả quân
            4. Về home
        """
        print("[ROBOT] 🗑️ Thả quân bị ăn vào bãi...")
        
        # Bước 1: Về home trước (waypoint an toàn)
        print(f"[ROBOT] 🏠 Về home trước khi đi bãi thải (tránh đường cong)")
        self.go_to_home_chess()
        
        # Bước 2: Sử dụng teaching point R_Trash để đi đến bãi thải
        if "R_Trash" in self.teaching_points:
            print(f"[ROBOT] ✈️ Sử dụng teaching point R_Trash để đi bãi thải")
            trash_joints = self.teaching_points["R_Trash"]["joints"]
            trash_pose = self.teaching_points["R_Trash"]["pose"]
            
            # Di chuyển đến R_Trash bằng MoveJ (an toàn hơn)
            err = self.movej_joint(trash_joints, trash_pose)
            if err not in (0, 112):
                print(f"[ROBOT] ⚠️ Không thể đến R_Trash, dùng tọa độ config backup")
                # Fallback: dùng tọa độ từ config
                safe_z = current_z if current_z is not None else config.SAFE_Z
                pose_safe = [config.CAPTURE_BIN_X, config.CAPTURE_BIN_Y, safe_z] + list(config.ROTATION)
                self.move_safe_pose(pose_safe)
        else:
            print(f"[ROBOT] ⚠️ Không tìm thấy R_Trash, dùng tọa độ config")
            # Fallback: dùng tọa độ từ config
            safe_z = current_z if current_z is not None else config.SAFE_Z
            pose_safe = [config.CAPTURE_BIN_X, config.CAPTURE_BIN_Y, safe_z] + list(config.ROTATION)
            self.move_safe_pose(pose_safe)
        
        # Bước 3: Thả quân
        self.gripper_ctrl(config.GRIPPER_OPEN)
        time.sleep(0.5)
        
        # Bước 4: Về home sau khi thả xong (chuẩn bị cho bước tiếp theo)
        print(f"[ROBOT] 🏠 Về home sau khi thả quân (chuẩn bị bước tiếp theo)")
        self.go_to_home_chess()
        
        print("[ROBOT] ✅ Đã thả quân bị ăn.")

    # -------------------------------------------------------------------------
    # HÀM CHÍNH — GỌI TỪ main_VIP.py
    # -------------------------------------------------------------------------

    def move_piece(self, s_col, s_row, d_col, d_row, is_capture,
                   moving_visual_target=None, captured_visual_target=None):
        """Quy trình di chuyển hoàn chỉnh, bao gồm xử lý ăn quân.
        
        Args:
            s_col, s_row: ô nguồn
            d_col, d_row: ô đích
            is_capture:   True nếu ăn quân đối phương
            moving_visual_target: GridTarget camera cho quân đang di chuyển, hoặc None
            captured_visual_target: GridTarget camera cho quân bị ăn, hoặc None
        """
        print(f"[ROBOT] ♟️ Di chuyển: ({s_col},{s_row}) → ({d_col},{d_row})"
              + (" [ĂN QUÂN]" if is_capture else ""))
        print(f"[ROBOT] 🔍 DEBUG: s_col={s_col}, s_row={s_row}, d_col={d_col}, d_row={d_row}")

        if not self.connected and not self.dry:
            try:
                self.connect()
            except Exception as e:
                print(f"[ROBOT] ❌ Không thể kết nối, hủy nước đi: {e}")
                return

        # Tính khoảng cách di chuyển để quyết định có cần nâng cao hơn không
        distance = abs(d_col - s_col) + abs(d_row - s_row)
        use_extra_safe = distance >= 4  # Nếu di chuyển >= 4 ô, dùng độ cao an toàn

        # 1. Nếu ăn quân: gắp quân địch → thả vào bãi thải
        if is_capture:
            print(f"[ROBOT] 🎯 Gắp quân địch tại đích ({d_col},{d_row})")
            self.pick_at(d_col, d_row, visual_target=captured_visual_target)
            
            # Nâng lên độ cao an toàn (SAFE_Z)
            print(f"[ROBOT] ⬆️ Nâng lên SAFE_Z={config.SAFE_Z}mm")
            self.move_to_extra_safe(d_col, d_row, visual_target=captured_visual_target)
            
            # Bay thẳng đến bãi thải ở độ cao SAFE_Z (giữ nguyên Z)
            self.place_in_capture_bin(current_z=config.SAFE_Z)

        # 2. Gắp quân mình ở nguồn
        print(f"[ROBOT] 🤏 Gắp quân mình tại nguồn ({s_col},{s_row})")
        self.pick_at(s_col, s_row, visual_target=moving_visual_target)
        
        # Nâng lên độ cao an toàn nếu di chuyển xa
        if use_extra_safe:
            print(f"[ROBOT] 🛡️ Di chuyển xa ({distance} ô), sử dụng độ cao an toàn")
            self.move_to_extra_safe(s_col, s_row, visual_target=moving_visual_target)

        # 3. Đặt quân mình vào đích
        print(f"[ROBOT] 📍 Đặt quân mình tại đích ({d_col},{d_row})")
        self.place_at(d_col, d_row)

        # 4. Về vị trí chờ
        self.go_to_home_chess()

        print("[ROBOT] ✅ Hoàn tất di chuyển.")

    # -------------------------------------------------------------------------
    # TIỆN ÍCH
    # -------------------------------------------------------------------------

    def load_perspective(self, path):
        """Load ma trận perspective từ file .npy."""
        try:
            self.perspective_matrix = np.load(path)
            print(f"[ROBOT] ✅ Loaded perspective: {path}")
            return True
        except Exception as e:
            print(f"[ROBOT] ❌ load_perspective error: {e}")
            return False

    def pixel_to_grid(self, px, py):
        """Convert tọa độ pixel ảnh → (col, row) bàn cờ."""
        if self.perspective_matrix is None:
            raise RuntimeError("Chưa có perspective_matrix — hãy calibrate camera trước.")
        src = np.array([[[float(px), float(py)]]], dtype=np.float32)
        dst = cv2.perspectiveTransform(src, self.perspective_matrix)[0][0]
        col = max(0, min(8, int(round(dst[0]))))
        row = max(0, min(9, int(round(dst[1]))))
        return col, row


# ==================================
# === KẾT THÚC FILE: robot_VIP.py ===
# ==================================
