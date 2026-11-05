# ==================================
# === FILE: VIP/robot_VIP.py ===
# === Điều khiển cánh tay robot FR5 — phiên bản VIP ===
# === Dựa trên robot.py gốc, dùng Tool DO0/DO1 cho kẹp hai chiều ===
# ==================================
import time
import sys
import os
import json
import threading
import math
import logging
from xmlrpc.client import Fault
import numpy as np
import cv2

# Đảm bảo import được config từ thư mục gốc project
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(os.path.dirname(_THIS_DIR))
sys.path.insert(0, _PROJECT_DIR)
import config
from src.core.project_logging import event
from src.motion.result import MotionExecutionResult, MotionFailureCategory, PayloadState
from src.motion.stages import MotionStage
from src.domain.board_pose_provider import parse_frame_identifier

class MotionResult(MotionExecutionResult):
    def __bool__(self):
        return self.success

class RobotCommandError(RuntimeError):
    def __init__(self, message, backend_code=None):
        super().__init__(message)
        self.backend_code = backend_code


try:
    from src.hardware import robot_sdk_core
except ImportError:
    print("LỖI: Không tìm thấy module 'robot_sdk_core'...")
    robot_sdk_core = None


class GripperCommandError(RuntimeError):
    """The gripper output state is unsafe or could not be commanded."""


class FR5Robot:
    def __init__(self, ip=None, *, dry_run=None, teaching_points_path=None):
        if ip is not None and (not isinstance(ip, str) or not ip.strip()):
            raise ValueError("Robot IP must be a nonempty explicit address")
        self.ip          = ip or config.ROBOT_IP
        self.robot       = None
        self.fixed_teaching_points_path = os.fspath(teaching_points_path) if teaching_points_path is not None else None
        self.uses_fixed_teaching_points = teaching_points_path is not None
        self.physical_motion_authorized = False
        self._activation_owned = False
        self._disable_outcome_unknown = False
        self._motion_stop = threading.Event()
        self.gripper_closed_estimate = False
        self.gripper_command_known = False
        self._gripper_pulse_active = False
        self.motion_listener = None
        self.telemetry_readiness = None
        self.last_motion_result = None
        self._active_stage = MotionStage.PREPOSITION
        self._last_completed_stage = None
        self._payload_state = PayloadState.NONE
        self.connected   = False
        self.dry         = config.DRY_RUN if dry_run is None else bool(dry_run)
        configured_tool = getattr(config, "ROBOT_TOOL_FRAME", None)
        if configured_tool is not None:
            configured_tool = int(configured_tool)
            if configured_tool < 0:
                raise ValueError("ROBOT_TOOL_FRAME must be a nonnegative integer or None")
        configured_user = int(getattr(config, "ROBOT_USER_FRAME", 0))
        if configured_user != 0:
            raise ValueError("ROBOT_USER_FRAME must be 0 (robot base) for this project")
        self.expected_tool_num = configured_tool
        self.expected_user_num = configured_user
        self.tool_num    = 0 if configured_tool is None else configured_tool
        self.user_num    = configured_user
        self.default_vel = config.MOVE_SPEED

        # Two-direction direct-drive gripper: Tool DO1=open, Tool DO0=close.
        self.gripper_open_do_id = config.GRIPPER_OPEN_DO_ID
        self.gripper_close_do_id = config.GRIPPER_CLOSE_DO_ID
        self._gripper_lock = threading.RLock()

        # Ma trận hiệu chỉnh perspective (được set từ main_VIP.py)
        self.perspective_matrix = None
        
        # Cache teaching points để tránh Singularity
        self.teaching_points = {}  # {name: {"pose": [x,y,z,rx,ry,rz], "joints": [j1..j6]}}
        self.teaching_points_error = None
        self.teaching_points_version = 0
        self.wobj_identity_as_base = False
        self.identity_wobj_id = None
        self._wobj_by_id_unsupported = False
        self._frame_normalization_error = None
        self.dispatch_validity = None
        self.motion_trace = {}
        self.use_teaching_points = True  # Luôn dùng teaching points

        # Kích thước ô cờ (mm), mặc định theo config, tự động cập nhật khi load teaching points
        self.auto_cell_sizes = {"x": config.CELL_SIZE_X, "y": config.CELL_SIZE_Y}

        # Read-only state consumed by the optional debug dashboard. This does
        # not affect motion; it records the command immediately before sending it.
        self._planned_command_lock = threading.Lock()
        self._planned_command = None

    def _set_planned_command(self, command, pose, label):
        with self._planned_command_lock:
            self._planned_command = {
                "command": command,
                "pose": [float(value) for value in pose[:6]],
                "label": label,
            }

    def get_planned_command(self):
        """Return a copy safe for the dashboard's publishing thread."""
        with self._planned_command_lock:
            if self._planned_command is None:
                return None
            return dict(self._planned_command, pose=list(self._planned_command["pose"]))

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
        """Read-only connection: no servo, mode, motion or gripper command."""
        self.physical_motion_authorized = False
        self.teaching_points_error = None
        self.wobj_identity_as_base = False
        self.identity_wobj_id = None
        self._wobj_by_id_unsupported = False
        if self.dry:
            self.connected = True
            return True
        if robot_sdk_core is None:
            raise RobotCommandError("Robot SDK unavailable")
        self.teaching_points = {}
        try:
            self.robot = robot_sdk_core.RPC(self.ip)
            self.connected = bool(self.robot.SDK_state)
            if not self.connected:
                raise RobotCommandError("Robot SDK not connected")
        except Exception:
            self.connected = False
            raise
        # Board calibration does not decide whether the SDK is connected.
        # Retain read-only arm telemetry, while rejecting unverified targets.
        try:
            self._load_teaching_points()
        except Exception as exc:
            self.teaching_points = {}
            self.teaching_points_error = f"R1-R4 calibration unavailable: {exc}"
            print(f"[ROBOT] Connected read-only; {self.teaching_points_error}")
        return True

    def activate_physical_control(self, *, commissioned=False, stop_recovered=False):
        """Explicit operator gate after calibration and commissioning review."""
        self.physical_motion_authorized = False
        if not commissioned:
            raise RobotCommandError("Physical control requires commissioned authorization")
        if self._disable_outcome_unknown:
            raise RobotCommandError("Controller disable outcome unknown; confirm pendant disable before enabling")
        if self._motion_stop.is_set() and not stop_recovered:
            raise RobotCommandError("Controlled stop latched; operator recovery required")
        if self.dry:
            return True
        if not self.connected or self.robot is None:
            raise RobotCommandError("Robot is not connected")
        self._validated_corners()
        self._validate_gripper_config()
        for method, value in (("Mode", 0), ("RobotEnable", 1)):
            if method == "RobotEnable":
                # A lost enable reply may still have energized the controller.
                self._activation_owned = True
            err = getattr(self.robot, method)(value)
            if err != 0:
                raise RobotCommandError(f"{method} failed: {err}", err)
        self.physical_motion_authorized = True
        self._motion_stop.clear()
        return True

    def latch_motion_stop(self):
        """Block subsequent stages immediately; preserve the held payload."""
        self._motion_stop.set()

    def send_controlled_stop(self, timeout=2.0):
        """One stop command on an independent connection; never enable or retry."""
        if self.dry or not (self.physical_motion_authorized or self._activation_owned):
            raise RobotCommandError("Stop requires application-owned physical control")
        from src.hardware.rpc_transport import BoundedRPCProxy
        proxy = BoundedRPCProxy(f"http://{self.ip}:20003", timeout_s=timeout)
        return proxy.StopMotion()

    def deactivate_physical_control(self):
        """Revoke owned activation without gripper or HOME; leave read-only sessions alone."""
        was_authorized = self.physical_motion_authorized or self._activation_owned
        self.physical_motion_authorized = False
        if not was_authorized or self.dry:
            return True
        if not self.connected or self.robot is None:
            raise RobotCommandError("Cannot confirm controller disable: robot disconnected")
        if self._disable_outcome_unknown:
            raise RobotCommandError("Disable reply unknown; disable on pendant and Ctrl+F9 confirm. No RPC replay.")
        from src.hardware.rpc_transport import RpcOutcomeUnknown
        try:
            code = self.robot.RobotEnable(0)
        except RpcOutcomeUnknown:
            self._disable_outcome_unknown = True
            raise
        if code != 0:
            raise RobotCommandError(f"RobotEnable(0) failed: {code}; verify pendant", backend_code=code)
        self._activation_owned = False
        return True

    def confirm_operator_disabled(self, *, approved=False):
        """Operator evidence only; no controller/gripper command is dispatched."""
        if not approved or not self._disable_outcome_unknown or self.physical_motion_authorized:
            raise RobotCommandError("Explicit pendant disable confirmation is required")
        self._activation_owned = False
        self._disable_outcome_unknown = False
        return True

    def _require_actuation(self):
        if self._motion_stop.is_set():
            raise RobotCommandError("RECOVERY_REQUIRED: controlled stop requested; no new motion")
        if not self.dry and (not self.connected or not self.physical_motion_authorized):
            raise RobotCommandError("Physical actuation is not authorized")
        if not self.dry and self.teaching_points_error:
            raise RobotCommandError(self.teaching_points_error)
        if not self.dry and callable(self.telemetry_readiness) and not self.telemetry_readiness():
            raise RobotCommandError("Robot telemetry stale/faulted; no new command dispatched")

    @staticmethod
    def _validate_pose(pose):
        values = [float(v) for v in pose]
        if len(values) != 6 or not all(math.isfinite(v) for v in values):
            raise ValueError("Pose must contain six finite values")
        if abs(values[0]) > 900 or abs(values[1]) > 900:
            raise ValueError("Pose outside adapter XY envelope")
        return values

    def _validated_corners(self):
        if self.teaching_points_error:
            raise RobotCommandError(self.teaching_points_error)
        if not self.dry:
            frames = {(parse_frame_identifier(self.teaching_points[name].get("tool")),
                       parse_frame_identifier(self.teaching_points[name].get("user")))
                      for name in ("R1", "R2", "R3", "R4")}
            if len(frames) != 1 or None in next(iter(frames)):
                found = sorted(str(value) for value in frames)
                raise RobotCommandError(
                    f"R1–R4 must use one explicit tool/user frame; found {found}. "
                    "Re-teach R1–R4 in robot base user 0.")
            common_tool, common_user = next(iter(frames))
            if common_user != self.expected_user_num:
                raise RobotCommandError(
                    f"R1–R4 must use user {self.expected_user_num} (robot base); found user {common_user}. "
                    "Re-teach R1–R4 with user 0 selected on the pendant.")
            if self.expected_tool_num is not None and common_tool != self.expected_tool_num:
                raise RobotCommandError(
                    f"R1–R4 must use tool {self.expected_tool_num}; found tool {common_tool}.")
            if (common_tool, common_user) != (self.tool_num, self.user_num):
                raise RobotCommandError("R1–R4 cached frames changed; reload and verify before motion")
        corners = np.array([self._validate_pose(self.teaching_points[name]["pose"])[:3]
                            for name in ("R1", "R2", "R3", "R4")])
        edges = np.roll(corners, -1, axis=0) - corners
        crosses = np.cross(edges, np.roll(edges, -1, axis=0))[:, 2]
        if np.any(np.linalg.norm(edges[:, :2], axis=1) <= 1e-6) or not (
                np.all(crosses > 1e-6) or np.all(crosses < -1e-6)):
            raise ValueError("R1-R4 must form an ordered nondegenerate convex board")
        return corners

    def _run_stage(self, stage, operation, *args, **kwargs):
        self._require_actuation()
        if self.dispatch_validity is not None:
            self.dispatch_validity()
        self._active_stage = stage
        event("motion.stage_started", "Bắt đầu bước chuyển động", stage=stage.name,
              operation=getattr(operation, "__name__", str(operation)), **self.motion_trace)
        value = operation(*args, **kwargs)
        if self.dispatch_validity is not None:
            self.dispatch_validity()
        if isinstance(value, MotionExecutionResult):
            if not value.success:
                raise RobotCommandError(value.message, value.backend_code)
        elif value is False or (isinstance(value, (int, np.integer))
                               and not isinstance(value, bool) and value != 0):
            raise RobotCommandError(f"{stage.name} failed: {value}", value)
        self._last_completed_stage = stage
        event("motion.stage_completed", "Hoàn tất bước chuyển động", stage=stage.name, **self.motion_trace)
        return value


    def _normalize_identity_wobj_frames(self, point_names, frames):
        """Allow mixed user IDs only when the taught WObj offset is identity.

        R1-R4 may have been recorded while a work-object was selected even
        though its coordinate offset is exactly zero. In that case the numeric
        XYZ values are already robot-base coordinates; normalize only the
        metadata and keep a loud audit event. Non-identity WObj transforms are
        never accepted.
        """
        if not bool(getattr(config, "ALLOW_IDENTITY_WOBJ_AS_BASE", False)):
            return frames
        users = {point['user'] for name, point in self.teaching_points.items()
                 if name in point_names}
        if len(users) < 2:
            return frames
        nonbase_users = users - {0}
        if len(nonbase_users) != 1 or None in nonbase_users:
            return frames
        source_user = next(iter(nonbase_users))
        try:
            by_id = getattr(self.robot, "GetWObjCoordWithID", None)
            use_current = not callable(by_id) or getattr(self, "_wobj_by_id_unsupported", False)
            if not use_current:
                # Motion uses user 0 and can change the controller's active
                # selection. A restart must verify the frame named by R1-R4,
                # independently of whichever frame happens to be active now.
                try:
                    code, wobj_offset = by_id(source_user)
                    verification_source = "GetWObjCoordWithID"
                except Fault as exc:
                    if (exc.faultCode != -506 or "GetWObjCoordWithID" not in exc.faultString
                            or "not defined" not in exc.faultString):
                        raise
                    self._wobj_by_id_unsupported = True
                    use_current = True
                    event("robot.frame_query_unsupported",
                          "Firmware không hỗ trợ đọc WObj theo ID; chỉ đọc frame đang chọn",
                          level=logging.WARNING, wobj=source_user, fault_code=exc.faultCode)
            if use_current:
                code, current_user = self.robot.GetActualWObjNum()
                if int(code) != 0:
                    raise RobotCommandError(f"Không đọc được WObj đang chọn: {code}", code)
                if parse_frame_identifier(current_user) != source_user:
                    raise RobotCommandError(
                        f"Chọn User/WObj {source_user} trên pendant rồi F9/F10 để xác minh lại. "
                        f"Firmware chỉ đọc được WObj đang chọn (hiện tại: {current_user}).")
                code, wobj_offset = self.robot.GetCurWObjCoord()
                after_code, after_user = self.robot.GetActualWObjNum()
                if after_code != 0 or parse_frame_identifier(after_user) != source_user:
                    raise RobotCommandError("WObj thay đổi trong lúc đọc; giữ nguyên frame rồi F9/F10 thử lại")
                verification_source = "GetCurWObjCoord"
            if code != 0:
                raise RobotCommandError(f"WObj {source_user} query failed: {code}", code)
            offset = np.asarray(wobj_offset, dtype=float)
            if offset.shape != (6,) or not np.isfinite(offset).all():
                raise RobotCommandError(f"WObj {source_user} must contain six finite offsets")
        except Exception as exc:
            self._frame_normalization_error = str(exc)
            event("robot.frame_normalization_failed",
                  f"Không xác minh được WObj {source_user} để chuẩn hóa frame",
                  level=logging.WARNING, wobj=source_user, reason=str(exc))
            return frames
        if not np.allclose(offset, 0.0, atol=1e-6, rtol=0):
            event("robot.frame_normalization_refused",
                  f"WObj {source_user} không phải identity; không thể coi là robot base",
                  level=logging.WARNING, wobj=source_user, offset=offset.tolist())
            return frames
        for name in point_names:
            point = self.teaching_points[name]
            if point.get("user") == source_user:
                point["user"] = 0
        self.wobj_identity_as_base = True
        self.identity_wobj_id = source_user
        event("robot.frame_normalized_identity_wobj",
              "WObj identity được chuẩn hóa thành robot base (user 0)",
              level=logging.WARNING, source_wobj=source_user,
              source_offset=offset.tolist(), verification_source=verification_source, points=list(point_names))
        print(f"[ROBOT] WARNING: normalized identity WObj {source_user} -> user 0 for R1-R4")
        return {(point['tool'], point['user']) for name, point in self.teaching_points.items()
                if name in point_names}

    def normalize_board_observations(self, parsed):
        """Return observations with an identity-WObj user label mapped to base."""
        if not self.wobj_identity_as_base:
            return parsed
        from dataclasses import replace
        return {
            name: (replace(point, user_or_wobj_id=0)
                   if point.user_or_wobj_id == self.identity_wobj_id else point)
            for name, point in parsed.items()
        }

    def _load_fixed_teaching_points(self):
        """Load the explicitly selected frozen robot-base profile; no SDK reads."""
        with open(self.fixed_teaching_points_path, encoding="utf-8-sig") as source:
            profile = json.load(source)
        expected = {"schema_version": 1, "coordinate_frame": "robot_base",
                    "position_unit": "mm", "orientation_unit": "deg", "joint_unit": "deg"}
        if any(profile.get(key) != value for key, value in expected.items()):
            raise RobotCommandError("Fixed teaching-point profile has invalid schema/frame/units")
        points = {}
        for name in ("R1", "R2", "R3", "R4", "HOMECHESS", "R_Trash"):
            point = profile["points"][name]
            tool = parse_frame_identifier(point.get("tool"))
            user = parse_frame_identifier(point.get("user"))
            joints = [float(value) for value in point["joints"]]
            if tool is None or user != 0 or len(joints) != 6 or not all(math.isfinite(v) for v in joints):
                raise RobotCommandError(f"{name}: fixed points require explicit tool, user 0 and six finite joints")
            points[name] = dict(pose=self._validate_pose(point["pose"]), joints=joints, tool=tool, user=user)
        tools = {point["tool"] for point in points.values()}
        if len(tools) != 1 or (self.expected_tool_num is not None and tools != {self.expected_tool_num}):
            raise RobotCommandError("Fixed points must share the configured tool frame")
        self.tool_num, self.user_num = next(iter(tools)), 0
        self.teaching_points = points
        self.teaching_points_error = None
        try:
            self._calculate_cell_sizes_from_corners()
        except Exception:
            self.teaching_points = {}
            self.teaching_points_error = "Invalid fixed board corners"
            raise
        self.teaching_points_version += 1
        event("robot.fixed_profile_loaded", "Dùng tọa độ cố định đã chuẩn hóa user 0",
              profile_id=profile.get("profile_id"), path=self.fixed_teaching_points_path,
              points=list(points), tool=self.tool_num, user=self.user_num,
              coordinate_frame="robot_base", position_unit="mm", angle_unit="deg")

    def read_teaching_point(self, name):
        """Resolve all game waypoints from the selected command-coordinate source."""
        if getattr(self, "uses_fixed_teaching_points", False) is True:
            if self.teaching_points_error:
                raise RobotCommandError(self.teaching_points_error)
            point = self.teaching_points.get(name)
            if point is None:
                return -1, []
            return 0, list(point["pose"]) + list(point["joints"]) + [point["tool"], point["user"]]
        return self.robot.GetRobotTeachingPoint(name)

    def _load_teaching_points(self):
        """Đọc teaching points R1, R2, R3, R4 để tính toán Bilinear Interpolation."""
        if not self.connected or self.dry:
            return
        
        print("[ROBOT] 📍 Đang load teaching points...")
        self.teaching_points_error = "R1–R4 reload in progress or incomplete; command mapping unavailable"
        self.physical_motion_authorized = False
        self.teaching_points = {}
        self.wobj_identity_as_base = False
        self.identity_wobj_id = None
        self._frame_normalization_error = None
        if getattr(self, "uses_fixed_teaching_points", False) is True:
            self._load_fixed_teaching_points()
            return
        
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
                        "joints": joint_data,
                        "tool": parse_frame_identifier(data[12]) if len(data) >= 14 else None,
                        "user": parse_frame_identifier(data[13]) if len(data) >= 14 else None,
                    }
                    print(f"[ROBOT]   ✅ Loaded {name}: X={pose_data[0]:.1f}, Y={pose_data[1]:.1f}, Z={pose_data[2]:.1f}")
                else:
                    raise Exception(f"Teaching point {name} không tồn tại (err={err})")
            except Exception as e:
                print(f"[ROBOT]   ❌ Lỗi đọc {name}: {e}")
                raise Exception(f"Thiếu teaching point {name} - Hệ thống không thể hoạt động")
        
        frames = {(point['tool'], point['user']) for name, point in self.teaching_points.items()
                  if name in point_names}
        if len(frames) != 1 or any(value is None for value in next(iter(frames))):
            frames = self._normalize_identity_wobj_frames(point_names, frames)
        if len(frames) != 1 or any(value is None for value in next(iter(frames))):
            found = sorted(str(value) for value in frames)
            if self._frame_normalization_error:
                raise RobotCommandError(f"R1-R4: {self._frame_normalization_error}")
            raise RobotCommandError(
                f"R1-R4 require one explicit tool/user frame; found {found}. "
                "Re-teach R1-R4 in robot base user 0 with the same tool frame.")
        common_tool, common_user = next(iter(frames))
        if common_user != self.expected_user_num:
            raise RobotCommandError(
                f"R1-R4 user frame must be {self.expected_user_num} (robot base); found {common_user}. "
                "Re-teach R1-R4 with user 0 selected on the pendant.")
        if self.expected_tool_num is not None and common_tool != self.expected_tool_num:
            raise RobotCommandError(
                f"R1-R4 tool frame must be {self.expected_tool_num}; found {common_tool}. "
                "Re-teach R1-R4 with the configured tool frame.")
        self.tool_num, self.user_num = common_tool, common_user
        self.teaching_points_error = None
        # Tính CELL_SIZE tự động từ 4 góc
        self._calculate_cell_sizes_from_corners()
        
        # Load R_Trash (optional - không bắt buộc)
        try:
            err, data = self.robot.GetRobotTeachingPoint("R_Trash")
            if err == 0 and len(data) >= 12:
                pose_data = [float(str(data[i]).strip()) for i in range(6)]
                joint_data = [float(str(data[i]).strip()) for i in range(6, 12)]
                
                trash_tool = parse_frame_identifier(data[12]) if len(data) >= 14 else None
                trash_user = parse_frame_identifier(data[13]) if len(data) >= 14 else None
                if (self.wobj_identity_as_base and trash_tool == self.tool_num
                        and trash_user == self.identity_wobj_id):
                    trash_user = 0
                self.teaching_points["R_Trash"] = {
                    "pose": pose_data,
                    "joints": joint_data,
                    "tool": trash_tool,
                    "user": trash_user,
                }
                print(f"[ROBOT]   ✅ Loaded R_Trash: X={pose_data[0]:.1f}, Y={pose_data[1]:.1f}, Z={pose_data[2]:.1f}")
            else:
                print(f"[ROBOT]   ⚠️ R_Trash không tồn tại; nước ăn quân sẽ bị chặn.")
        except Exception as e:
            print(f"[ROBOT]   ⚠️ Không load được R_Trash: {e}; nước ăn quân sẽ bị chặn.")
        
        print(f"[ROBOT] ✅ Đã load {len(self.teaching_points)} teaching points")
        print(f"[ROBOT] 🎯 Sử dụng Bilinear Interpolation cho tất cả vị trí")
        self.teaching_points_version += 1

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
        # Physical coordinates follow visual-correction-v2: taught corners keep
        # their measured XY; interior/visual floating targets use bilinear XY.
        name, point = self._get_teaching_point_for_position(col, row)
        if point is not None:
            pose = list(point['pose'])
            pose[2] = z_height
            if rotation is not None:
                pose[3:] = self._validated_rotation(rotation)
            return self._validate_pose(pose)
        return self.board_to_pose_bilinear(col, row, z_height, rotation=rotation)

    @staticmethod


    def _validated_rotation(rotation):
        """Return a copy of a Cartesian tool rotation, rejecting malformed config."""
        if not isinstance(rotation, (list, tuple)) or len(rotation) != 3:
            raise ValueError("Tool rotation must be a three-value [Rx, Ry, Rz] sequence")
        values = [float(value) for value in rotation]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Tool rotation must be finite")
        return values

    def _calculate_cell_sizes_from_corners(self):
        r1, r2, r3, r4 = self._validated_corners()
        self.auto_cell_sizes = {
            "x": (np.linalg.norm(r2-r1) + np.linalg.norm(r3-r4)) / 16,
            "y": (np.linalg.norm(r4-r1) + np.linalg.norm(r3-r2)) / 18,
        }


    def board_to_pose_bilinear(self, col, row, z_height, rotation=None):
        if not all(math.isfinite(float(v)) for v in (col, row, z_height)):
            raise ValueError("Grid target must be finite")
        margin = float(getattr(config, "VISUAL_PICK_OUTSIDE_MARGIN_MM", 0.0))
        if not math.isfinite(margin) or not 0 <= margin <= 6:
            raise ValueError("Outside-grid margin must be within 0..6 mm")
        corners = self._validated_corners()
        width = min(np.linalg.norm(corners[1]-corners[0]), np.linalg.norm(corners[2]-corners[3]))
        height = min(np.linalg.norm(corners[3]-corners[0]), np.linalg.norm(corners[2]-corners[1]))
        if min(width, height) <= 0:
            raise ValueError("Degenerate board dimensions")
        if not (-8*margin/width <= col <= 8+8*margin/width
                and -9*margin/height <= row <= 9+9*margin/height):
            raise ValueError("Grid target outside board")
        r1, r2, r3, r4 = self._validated_corners()
        u, v = col/8.0, row/9.0
        xyz = (1-v)*((1-u)*r1+u*r2) + v*((1-u)*r4+u*r3)
        pose = [float(xyz[0])+config.OFFSET_X, float(xyz[1])+config.OFFSET_Y,
                float(z_height)] + self._validated_rotation(config.ROTATION if rotation is None else rotation)
        return self._validate_pose(pose)


    def board_to_pose_linear(self, col, row, z_height, rotation=None):
        """Compatibility alias; all targets require four valid corners."""
        return self.board_to_pose_bilinear(col, row, z_height, rotation=rotation)


    def move_safe_pose(self, pose, speed=None, col=None, row=None, label=None):
        """Di chuyển an toàn đến pose. Luôn dùng MoveCart để đảm bảo đường thẳng."""
        self._require_actuation()
        pose = self._validate_pose(pose)
        vel = self.default_vel if speed is None else float(speed)
        if not math.isfinite(vel) or not (0 < vel <= 100):
            raise ValueError("Speed must be finite within (0,100]")
        location = f"grid ({col}, {row})" if col is not None and row is not None else "waypoint"
        self._set_planned_command("MoveCart", pose, label or f"Approach {location}")
        if self.dry:
            print(f"[ROBOT] DRY MoveCart → {[round(v,1) for v in pose]} vel={vel}")
            time.sleep(0.2)
            return 0

        # Luôn dùng MoveCart để đảm bảo di chuyển thẳng, tránh đá quân cờ
        err = self.robot.MoveCart(
            desc_pos=pose, tool=self.tool_num, user=self.user_num,
            vel=vel, acc=0.0, ovl=100.0, blendT=-1.0, config=-1
        )
        if err != 0:
            print(f"[ROBOT] ❌ Lỗi MoveCart: {err}")
            raise RobotCommandError(f"Robot MoveCart error code: {err}", err)
        return err

    def movej_joint(self, joint_pos, desc_pos, speed=None, label=None):
        """Di chuyển trực tiếp bằng góc joint (MoveJ) nếu đã biết."""
        self._require_actuation()
        desc_pos = self._validate_pose(desc_pos)
        joint_pos = [float(v) for v in joint_pos]
        if len(joint_pos) != 6 or not all(math.isfinite(v) for v in joint_pos):
            raise ValueError("Joint target must contain six finite values")
        vel = self.default_vel if speed is None else float(speed)
        if not math.isfinite(vel) or not (0 < vel <= 100):
            raise ValueError("Speed must be finite within (0,100]")
        self._set_planned_command("MoveJ", desc_pos, label or "Joint waypoint")
        if self.dry:
            print(f"[ROBOT] DRY MoveJ_Joint → vel={vel}")
            time.sleep(0.2)
            return 0
            
        err = self.robot.MoveJ(
            joint_pos=joint_pos, desc_pos=desc_pos, tool=self.tool_num, user=self.user_num,
            vel=vel, acc=0.0, ovl=100.0, exaxis_pos=[0]*4, blendT=-1.0, offset_flag=0, offset_pos=[0]*6
        )
        if err != 0:
            print(f"[ROBOT] ❌ Lỗi movej_joint MoveJ: {err}")
            raise RobotCommandError(f"Robot movej_joint error code: {err}", err)
        return err

    def movel_pose(self, pose, speed=None, label=None):
        """Di chuyển thẳng đứng (MoveCart) đến pose."""
        self._require_actuation()
        pose = self._validate_pose(pose)
        vel = self.default_vel if speed is None else float(speed)
        if not math.isfinite(vel) or not (0 < vel <= 100):
            raise ValueError("Speed must be finite within (0,100]")
        self._set_planned_command("MoveCart", pose, label or "Vertical movement")
        if self.dry:
            print(f"[ROBOT] DRY MoveL → {[round(v,1) for v in pose]} vel={vel}")
            time.sleep(0.2)
            return 0

        err = self.robot.MoveCart(
            desc_pos=pose, tool=self.tool_num, user=self.user_num,
            vel=vel, acc=0.0, ovl=100.0, blendT=-1.0, config=-1
        )
        if err != 0:
            print(f"[ROBOT] ❌ Lỗi MoveCart (movel): {err}")
            raise RobotCommandError(f"Robot MoveCart error code: {err}", err)
        return err

    # -------------------------------------------------------------------------
    # VỀ NHÀ
    # -------------------------------------------------------------------------

    def go_to_idle_home(self):
        return self.move_safe_pose([config.IDLE_X,config.IDLE_Y,config.IDLE_Z]+list(config.ROTATION))


    def go_to_home_chess(self):
        self._require_actuation()
        if self.dry:
            return 0
        err, data = self.read_teaching_point("HOMECHESS")
        if err != 0 or len(data) < 6:
            raise RobotCommandError("Validated HOMECHESS teaching point unavailable",err)
        self._verify_waypoint_frame(data, 'HOMECHESS')
        pose = self._validate_pose(data[:6])
        if len(data) >= 12:
            return self.movej_joint([float(v) for v in data[6:12]],pose)
        return self.move_safe_pose(pose)

    def _verify_waypoint_frame(self, data, name):
        if len(data) < 14:
            raise RobotCommandError(f'{name}: tool/user frame differs from R1-R4 or metadata is missing')
        wp_tool, wp_user = parse_frame_identifier(data[12]), parse_frame_identifier(data[13])
        if (self.wobj_identity_as_base and wp_tool == self.tool_num
                and wp_user == self.identity_wobj_id):
            # HOMECHESS was recorded under the same identity WObj as R1-R3;
            # its numeric pose is already robot-base coordinates.
            wp_user = 0
        if (wp_tool, wp_user) != (self.tool_num, self.user_num):
            raise RobotCommandError(f'{name}: tool/user frame differs from R1-R4 or metadata is missing')


    def _validate_gripper_config(self):
        if self.gripper_open_do_id == self.gripper_close_do_id:
            raise GripperCommandError("Open and close gripper Tool DO IDs must differ")
        if {self.gripper_open_do_id, self.gripper_close_do_id} - {0, 1}:
            raise GripperCommandError("Gripper Tool DO IDs must be 0 or 1")
        timing_values = (
            config.GRIPPER_DIRECTION_DEADTIME_SEC,
            config.GRIPPER_OPEN_MAX_PULSE_SEC,
            config.GRIPPER_RELEASE_PULSE_SEC,
            config.GRIPPER_CLOSE_PULSE_SEC,
            config.GRIPPER_SAFE_GAP_CLOSE_PULSE_SEC,
            config.GRIPPER_OPEN_SETTLE_SEC,
            config.GRIPPER_CLOSE_SETTLE_SEC,
        )
        if (any(not isinstance(value, (int, float)) for value in timing_values)
                or any(not math.isfinite(value) or value < 0 for value in timing_values)):
            raise GripperCommandError("Gripper timing values must be non-negative numbers")

    def _set_tool_do(self, output_id, status):
        if status:
            self._require_actuation()
        if self.dry:
            print(f"[ROBOT] DRY Tool DO{output_id}={'ON' if status else 'OFF'}")
            return 0
        err = self.robot.SetToolDO(id=output_id, status=status, block=0)
        if err != 0:
            raise GripperCommandError(f"SetToolDO(DO{output_id}, {status}) failed: {err}")
        return err

    def _set_gripper_safe_idle(self):
        """Best-effort all-low state; raise if either DO cannot be reset."""
        failures = []
        for output_id in (self.gripper_open_do_id, self.gripper_close_do_id):
            try:
                self._set_tool_do(output_id, config.GRIPPER_IDLE_STATUS)
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise GripperCommandError("Could not force both gripper outputs LOW") from failures[0]
        self._gripper_pulse_active = False

    def gripper_ctrl(self, action):
        """Pulse one gripper motor direction, then leave both Tool DO outputs LOW."""
        self._require_actuation()
        self._validate_gripper_config()
        if action == config.GRIPPER_ACTION_OPEN_MAX:
            target_id = self.gripper_open_do_id
            pulse_seconds = config.GRIPPER_OPEN_MAX_PULSE_SEC
            settle_seconds = config.GRIPPER_OPEN_SETTLE_SEC
            label = "OPEN MAX"
        elif action == config.GRIPPER_ACTION_RELEASE:
            target_id = self.gripper_open_do_id
            pulse_seconds = config.GRIPPER_RELEASE_PULSE_SEC
            settle_seconds = config.GRIPPER_OPEN_SETTLE_SEC
            label = "RELEASE"
        elif action == config.GRIPPER_ACTION_CLOSE_TO_SAFE_GAP:
            target_id = self.gripper_close_do_id
            pulse_seconds = config.GRIPPER_SAFE_GAP_CLOSE_PULSE_SEC
            settle_seconds = config.GRIPPER_CLOSE_SETTLE_SEC
            label = "CLOSE TO SAFE GAP"
        elif action == config.GRIPPER_ACTION_CLOSE:
            target_id = self.gripper_close_do_id
            pulse_seconds = config.GRIPPER_CLOSE_PULSE_SEC
            settle_seconds = config.GRIPPER_CLOSE_SETTLE_SEC
            label = "CLOSE"
        else:
            raise GripperCommandError(f"Unknown gripper action: {action!r}")

        with self._gripper_lock:
            self._pulse_gripper_direction(target_id, pulse_seconds, label)
            time.sleep(settle_seconds)
        if self._motion_stop.is_set():
            self.gripper_command_known = False
            raise GripperCommandError("Gripper interrupted by controlled stop; inspect held payload")
        self.gripper_closed_estimate = action == config.GRIPPER_ACTION_CLOSE
        self.gripper_command_known = True
        if callable(self.motion_listener):
            try:
                self.motion_listener('gripper', self.gripper_closed_estimate, action)
            except Exception as exc:
                import logging
                event('twin.animation_failed', str(exc), level=logging.WARNING)
        return 0

    def _pulse_gripper_direction(self, target_id, pulse_seconds, label):
        """Interlocked single-direction pulse; callers must hold _gripper_lock."""
        self._set_gripper_safe_idle()
        time.sleep(config.GRIPPER_DIRECTION_DEADTIME_SEC)
        try:
            print(f"[ROBOT] Gripper {label}: DO{target_id} ON for {pulse_seconds:.2f}s")
            # Even a lost ON reply may have energized the motor.
            self._gripper_pulse_active = True
            self._set_tool_do(target_id, config.GRIPPER_ACTIVE_STATUS)
            self._motion_stop.wait(pulse_seconds)
        finally:
            self._set_gripper_safe_idle()

    # -------------------------------------------------------------------------
    # QUY TRÌNH GẮP / ĐẶT / ĂN QUÂN
    # -------------------------------------------------------------------------

    def hover_at(self, col, row, visual_target):
        """Same calibrated pick XY at SAFE_Z, with no descent or gripper command."""
        self._require_actuation()
        if visual_target is None:
            raise ValueError("Hover requires a measured target")
        rotation = getattr(config, "PICK_TOOL_ROTATION", config.ROTATION)
        pose = self.board_to_pose_bilinear(visual_target.col, visual_target.row, config.SAFE_Z, rotation)
        self.move_safe_pose(pose, col=col, row=row, label="Hover diagnostic")
        return pose

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
        reference = self.board_to_pose_bilinear(col, row, config.PICK_Z, rotation=pick_rotation) if visual_target is not None else pose_pick
        self.visual_pick_correction = dict(dx_mm=pose_pick[0]-reference[0], dy_mm=pose_pick[1]-reference[1],
            cell=[col, row], target=[visual_target.col, visual_target.row] if visual_target else [col, row],
            visual=visual_target is not None, active=True)
        event("motion.visual_correction", "Bù tâm quân theo camera", correction=self.visual_pick_correction)
        if self.gripper_command_known and self.gripper_closed_estimate:
            raise GripperCommandError(
                "Gripper is closed; inspect for a held payload before another pick")
        if not self.gripper_command_known:
            # First pick of a session: jaw state is unknown. Open before descent
            # instead of approaching a piece with closed jaws.
            self._run_stage(MotionStage.PREPOSITION, self.gripper_ctrl,
                            config.GRIPPER_ACTION_OPEN_MAX)
        try:
            self._run_stage(MotionStage.APPROACH, self.move_safe_pose, pose_safe, col=col, row=row)  # Đi đến vị trí an toàn trên ô
            self._run_stage(MotionStage.LAND, self.movel_pose, pose_pick)                # Hạ xuống
            self._run_stage(MotionStage.GRIP, self.gripper_ctrl, config.GRIPPER_ACTION_CLOSE)
            self._payload_state = PayloadState.EXPECTED_ATTACHED
            self._run_stage(MotionStage.LIFT, self.movel_pose, pose_safe)                # Nhấc lên
        finally:
            self.visual_pick_correction["active"] = False
        print(f"[ROBOT] ✅ Gắp xong ({col},{row})")

    def place_at(self, col, row):
        """Đặt quân ở tâm ô đích vật lý theo R1-R4 và pose đặt đã dạy."""
        place_rotation = getattr(config, "PLACE_TOOL_ROTATION", config.ROTATION)
        pose_safe = self.board_to_pose(col, row, config.SAFE_Z, rotation=place_rotation)
        pose_place = self.board_to_pose(col, row, config.PLACE_Z, rotation=place_rotation)
        print(f"[ROBOT] 📍 Đặt tại grid=({col},{row}) → X={pose_safe[0]:.1f}, Y={pose_safe[1]:.1f}, Z={pose_safe[2]:.1f}")

        self._run_stage(MotionStage.PLACE_APPROACH, self.move_safe_pose, pose_safe, col=col, row=row)  # Đến vị trí an toàn
        self._run_stage(MotionStage.PLACE_LAND, self.movel_pose, pose_place)               # Hạ xuống
        self._run_stage(MotionStage.RELEASE, self.gripper_ctrl, config.GRIPPER_ACTION_RELEASE)
        self._payload_state = PayloadState.EXPECTED_RELEASED
        self._run_stage(MotionStage.POST_RELEASE_LIFT, self.movel_pose, pose_safe)                # Nhấc lên
        # Short release retains the jaw gap; safe-gap closing assumes fully open jaws.
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
        self._run_stage(MotionStage.LIFT,self.move_safe_pose,pose_safe,col=col,row=row)

    def place_in_capture_bin(self, current_z=None):
        self._require_actuation()
        if "R_Trash" not in self.teaching_points:
            raise RobotCommandError("Validated R_Trash teaching point unavailable")
        trash = self.teaching_points["R_Trash"]
        self._run_stage(MotionStage.SERVICE_RETREAT,self.go_to_home_chess)
        self._run_stage(MotionStage.TRANSIT,self.movej_joint,trash["joints"],trash["pose"])
        self._run_stage(MotionStage.RELEASE,self.gripper_ctrl,config.GRIPPER_ACTION_OPEN_MAX)
        self._payload_state = PayloadState.EXPECTED_RELEASED
        self._run_stage(MotionStage.SERVICE_RETREAT,self.go_to_home_chess)
        self._run_stage(MotionStage.SETTLE,self.gripper_ctrl,config.GRIPPER_ACTION_CLOSE_TO_SAFE_GAP)
        return 0


    def move_piece(self, *args, **kwargs):
        self._active_stage = MotionStage.PREPOSITION
        self._last_completed_stage = None
        self._payload_state = PayloadState.NONE
        try:
            self._move_piece_sequence(*args, **kwargs)
            result = MotionResult.ok(payload_state=self._payload_state)
        except Exception as exc:
            from src.vision.pick_consensus import PickTargetUnavailable
            import logging
            event("motion.stage_failed", str(exc), level=logging.ERROR, code="MOVE_REJECTED",
                  exc_info=True, stage=self._active_stage.name,
                  last_completed_stage=getattr(self._last_completed_stage, "name", None),
                  payload_state=self._payload_state.name, backend_code=getattr(exc, "backend_code", None),
                  pick_resolution=getattr(exc, "resolution", None))
            category = (MotionFailureCategory.PRECONDITION_FAILED if isinstance(exc,PickTargetUnavailable)
                        else MotionFailureCategory.GRIPPER_FAILED if isinstance(exc,GripperCommandError)
                        else MotionFailureCategory.TARGET_INVALID if isinstance(exc,(ValueError,KeyError))
                        else MotionFailureCategory.MOTION_COMMAND_FAILED)
            retry_stage = exc.stage if isinstance(exc, PickTargetUnavailable) else None
            metadata = {}
            if retry_stage:
                metadata["visual_retry_stage"] = retry_stage
                metadata["pick_resolution"] = getattr(exc, "resolution", {})
            result = MotionResult.fail(self._active_stage,category,str(exc),
                last_completed_stage=self._last_completed_stage,payload_state=self._payload_state,
                backend_code=getattr(exc,"backend_code",None),
                metadata=metadata)
        self.last_motion_result = result
        return result

    execute_piece_move = move_piece

    def _move_piece_sequence(self, s_col, s_row, d_col, d_row, is_capture,
                   moving_visual_target=None, captured_visual_target=None,
                   refresh_moving_visual_target=None, verify_capture_cleared=None):
        """Quy trình di chuyển hoàn chỉnh, bao gồm xử lý ăn quân.
        
        Args:
            s_col, s_row: ô nguồn
            d_col, d_row: ô đích
            is_capture:   True nếu ăn quân đối phương
            moving_visual_target: GridTarget camera cho quân đang di chuyển, hoặc None
            captured_visual_target: GridTarget camera cho quân bị ăn, hoặc None
            refresh_moving_visual_target: callback chụp lại bàn thật ngay trước
                khi gắp quân di chuyển. Trả về GridTarget hoặc None để hủy an toàn.
        """
        print(f"[ROBOT] ♟️ Di chuyển: ({s_col},{s_row}) → ({d_col},{d_row})"
              + (" [ĂN QUÂN]" if is_capture else ""))
        print(f"[ROBOT] 🔍 DEBUG: s_col={s_col}, s_row={s_row}, d_col={d_col}, d_row={d_row}")

        self._require_actuation()
        self.board_to_pose(s_col,s_row,config.PICK_Z)
        self.board_to_pose(d_col,d_row,config.PLACE_Z)
        if is_capture:
            if "R_Trash" not in self.teaching_points:
                raise RobotCommandError("Validated R_Trash teaching point unavailable")
            self._validate_pose(self.teaching_points["R_Trash"]["pose"])
            trash = self.teaching_points['R_Trash']
            if (trash.get('tool'), trash.get('user')) != (self.tool_num, self.user_num):
                raise RobotCommandError('R_Trash tool/user frame differs from R1-R4')
            joints = self.teaching_points["R_Trash"]["joints"]
            if len(joints) != 6 or not all(math.isfinite(float(v)) for v in joints):
                raise ValueError("Capture-bin joint target is invalid")
        if not self.dry:
            code, home = self.read_teaching_point('HOMECHESS')
            if code != 0:
                raise RobotCommandError('HOMECHESS unavailable before motion', code)
            self._verify_waypoint_frame(home, 'HOMECHESS')

        distance = abs(d_col - s_col) + abs(d_row - s_row)
        use_extra_safe = distance >= 4  # Nếu di chuyển >= 4 ô, dùng độ cao an toàn

        # 1. Nếu ăn quân: gắp quân địch → thả vào bãi thải
        if is_capture:
            print(f"[ROBOT] 🎯 Gắp quân địch tại đích ({d_col},{d_row})")
            self._run_stage(MotionStage.LIFT,self.pick_at,d_col,d_row,visual_target=captured_visual_target)
            
            # Nâng lên độ cao an toàn (SAFE_Z)
            print(f"[ROBOT] ⬆️ Nâng lên SAFE_Z={config.SAFE_Z}mm")
            self._run_stage(MotionStage.LIFT,self.move_to_extra_safe,d_col,d_row,visual_target=captured_visual_target)
            
            # Bay thẳng đến bãi thải ở độ cao SAFE_Z (giữ nguyên Z)
            self._run_stage(MotionStage.RELEASE,self.place_in_capture_bin,current_z=config.SAFE_Z)
            self._active_stage = MotionStage.SETTLE
            if verify_capture_cleared is not None and not verify_capture_cleared():
                raise RuntimeError("Capture square is not visually clear after removal")

        # A capture changes the physical board.  Do not reuse a target measured
        # before that operation for the next pick; ask vision for a fresh pose.
        if refresh_moving_visual_target is not None:
            moving_visual_target = refresh_moving_visual_target()
            if moving_visual_target is None:
                raise RobotCommandError("Fresh visual correction unavailable after refresh")

        # 2. Gắp quân mình ở nguồn
        print(f"[ROBOT] 🤏 Gắp quân mình tại nguồn ({s_col},{s_row})")
        self._run_stage(MotionStage.LIFT,self.pick_at,s_col,s_row,visual_target=moving_visual_target)
        
        # Nâng lên độ cao an toàn nếu di chuyển xa
        if use_extra_safe:
            print(f"[ROBOT] 🛡️ Di chuyển xa ({distance} ô), sử dụng độ cao an toàn")
            self._run_stage(MotionStage.LIFT,self.move_to_extra_safe,s_col,s_row,visual_target=moving_visual_target)

        # 3. Đặt quân mình vào đích
        print(f"[ROBOT] 📍 Đặt quân mình tại đích ({d_col},{d_row})")
        self._run_stage(MotionStage.POST_RELEASE_LIFT,self.place_at,d_col,d_row)

        # 4. Về vị trí chờ
        self._run_stage(MotionStage.SERVICE_RETREAT,self.go_to_home_chess)

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
