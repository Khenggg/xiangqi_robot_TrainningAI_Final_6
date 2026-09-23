import os
import time
import sys
import math
import numpy as np
import cv2
import threading
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from src.hardware.robot_VIP import FR5Robot
from src.hardware.backends import RobotBackend, PhysicalFR3Backend, VirtualFR3Backend
from src.hardware.gripper import TwoOutputGripperDriver
from src.domain.board_pose_provider import (
    BoardPoseProvider,
    FixedBoardPoseProvider,
    PhysicalTeachingPointBoardPoseProvider,
    BoardCalibrationResult,
    BoardCalibrationProfile,
    BoardCalibrationTolerancePolicy,
)
from src.motion.coordinator import MotionCoordinator, MotionProfile
from src.motion.stages import MotionStage
from src.motion.contracts import (
    MotionType,
    GripperCommand,
)
from src.motion.plan import PieceMoveIntent, CaptureIntent
from src.motion.resolver import MotionResolver
from src.motion.executor import MotionExecutor
from src.motion.result import (
    PayloadState,
    MotionFailureCategory,
    ExecutionFailureCategory,
    MotionExecutionResult,
)
from src.ai.moonfish_engine import MoonfishEngine
from src.ai.cloud_engine import CloudEngine
from src.ai.ai_controller import AIController
from src.vision.camera_monitor import CameraMonitor
from src.vision.snapshot_detector import SnapshotDetector as YoloSnapshotDetector
from src.vision.visual_pick_estimator import VisualPickEstimator
from src.vision.calibrate_camera import calibrate_perspective_camera
from src.vision.turn_completion_monitor import TurnCompletionMonitor

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

class HardwareManager:
    """Manages Robot, Camera (Vision), and AI Engine connections."""
    def __init__(
        self,
        config,
        project_dir,
        board_calibration_profile: Optional[BoardCalibrationProfile] = None,
        board_calibration_policy: Optional[BoardCalibrationTolerancePolicy] = None,
        simulation_runtime: Optional[Any] = None,
    ):
        self.config = config
        self.project_dir = project_dir
        self.dry_run = config.DRY_RUN
        self.board_calibration_profile = board_calibration_profile
        self.board_calibration_policy = board_calibration_policy
        self.simulation_runtime = simulation_runtime
        
        # Hardware instances
        self.robot = FR5Robot()
        self.backend = None
        self.gripper_driver = None
        self.board_pose_provider = None
        self.motion_profile = None
        self.motion_coordinator = None
        self.motion_resolver = None
        self.motion_executor = None
        self.physical_motion_authorized = False
        self.engine = None
        self.ai_ctrl = None
        self.cap = None
        self.model = None
        self.cam_monitor = None
        self.yolo_detector = None
        self.pick_estimator = None
        self.hand_model = None
        self.turn_completion_monitor = None
        self._last_hand_check = 0.0
        self.cchess_recognizer = None
        self.perspective_path = Path(project_dir) / "perspective.npy"
        self.camera_ready = False
        
        self.class_id_to_name = {
            0: "b_A", 1: "b_C", 2: "b_R", 3: "b_E", 4: "b_K", 5: "b_N", 6: "b_P",
            8: "r_A", 9: "r_C", 10: "r_R", 11: "r_E", 12: "r_K", 13: "r_N", 14: "r_P",
        }

    def initialize_all(self):
        """Khởi tạo toàn bộ Robot, AI, Camera theo đúng thứ tự."""
        self._init_ai()
        self._init_robot()
        self._init_camera()
        return self

    def _init_robot(self):
        backend_type = getattr(self.config, "ROBOT_BACKEND", "PHYSICAL").upper()
        if backend_type == "VIRTUAL":
            print("[MAIN] 🎮 Initializing Virtual FR3 Backend (Simulation)...")
            if self.simulation_runtime is not None:
                self.backend = self.simulation_runtime.backend
                if not getattr(self.backend, "connected", False):
                    self.backend.connect()
                print("[MAIN] ✅ Virtual FR3 Backend connected via simulation runtime.")
            elif self.backend is None:
                try:
                    self.backend = VirtualFR3Backend()
                    self.backend.connect()
                    print("[MAIN] ✅ Virtual FR3 Backend connected.")
                except Exception as e:
                    print(f"⚠️ [MAIN] Virtual FR3 init error: {e}")
                    self.backend = None

            # Setup Board Pose Provider & Motion Pipeline for Virtual Backend
            forward_shift_mm = getattr(self.config, "FORWARD_SHIFT_MM", 0.0)
            self.board_pose_provider = FixedBoardPoseProvider.from_forward_shift(
                forward_shift_mm=forward_shift_mm
            )
            self.motion_profile = MotionProfile(
                pick_tcp_height_above_board_mm=getattr(self.config, "PICK_TCP_HEIGHT_MM", 4.715),
                place_tcp_height_above_board_mm=getattr(self.config, "PLACE_TCP_HEIGHT_MM", 4.715),
                safe_clearance_above_board_mm=getattr(self.config, "SAFE_CLEARANCE_Z_MM", 40.0),
                provenance="SIMULATION_GEOMETRIC_DEFAULT",
            )

            # Create payload verifier for virtual simulation
            def virtual_payload_verifier(state: PayloadState) -> bool:
                if self.simulation_runtime is not None and hasattr(self.simulation_runtime, "world"):
                    piece = self.simulation_runtime.world.get_attached_piece()
                    if state in (PayloadState.EXPECTED_ATTACHED, PayloadState.ATTACHED):
                        return piece is not None
                    elif state in (PayloadState.EXPECTED_RELEASED, PayloadState.RELEASED, PayloadState.NONE):
                        return piece is None
                elif self.backend is not None and hasattr(self.backend, "is_gripper_closed"):
                    if state in (PayloadState.EXPECTED_ATTACHED, PayloadState.ATTACHED):
                        return bool(self.backend.is_gripper_closed())
                    elif state in (PayloadState.EXPECTED_RELEASED, PayloadState.RELEASED, PayloadState.NONE):
                        return not bool(self.backend.is_gripper_closed())
                return True

            tool_rot = getattr(self.config, "PICK_TOOL_ROTATION", [-179.164, -3.047, -26.304])
            if self.backend is not None:
                self.motion_resolver = MotionResolver(
                    board_pose_provider=self.board_pose_provider,
                    motion_profile=self.motion_profile,
                    tool_rotation_deg=tool_rot,
                )
                self.motion_executor = MotionExecutor(
                    backend=self.backend,
                    payload_verifier=virtual_payload_verifier,
                )
                self.motion_coordinator = MotionCoordinator(
                    backend=self.backend,
                    board_pose_provider=self.board_pose_provider,
                    motion_profile=self.motion_profile,
                    tool_rotation_deg=tool_rot,
                )
                print("[MAIN] 🧭 MotionResolver & MotionExecutor initialized (Virtual Mode).")
            self.physical_motion_authorized = True
        else:
            print("[MAIN] 🦾 Initializing Physical FR3 Backend...")
            try:
                self.backend = PhysicalFR3Backend(
                    ip=getattr(self.config, "ROBOT_IP", "192.168.58.2"),
                    dry_run=self.dry_run,
                )
                self.gripper_driver = TwoOutputGripperDriver(
                    set_do_fn=self.backend.set_tool_do,
                    dry_run=self.dry_run,
                    open_do_id=getattr(self.config, "TOOL_DO_OPEN", 1),
                    close_do_id=getattr(self.config, "TOOL_DO_CLOSE", 0),
                    open_pulse_sec=getattr(self.config, "TOOL_DO_OPEN_PULSE_SEC", 0.30),
                    close_pulse_sec=getattr(self.config, "TOOL_DO_CLOSE_PULSE_SEC", 0.30),
                    deadtime_sec=getattr(self.config, "TOOL_DO_DEADTIME_SEC", 0.10),
                )
                self.backend.gripper_driver = self.gripper_driver
                self.backend.connect()
                if not self.dry_run:
                    print("[MAIN] ✅ Physical FR3 Backend connected (READ-ONLY).")
            except Exception as e:
                print(f"⚠️ [MAIN] Physical FR3 Backend init error: {e}")
                self.backend = None

            # Legacy double connection REMOVED: Do NOT call self.robot.connect()!
            # HardwareManager interacts with physical hardware exclusively through self.backend.
            self.robot.connected = False

            # Physical board calibration from R1-R4 teaching points
            # TUYỆT ĐỐI KHÔNG GỌI MOTION (go_to_home_chess, MoveJ, MoveL, MoveCart) TRƯỚC KHI CALIBRATE
            self._calibrate_robot()

    def _calibrate_robot(self):
        print("\n--- ROBOT CALIBRATION (R1-R4 TEACHING POINTS) ---")
        backend_type = getattr(self.config, "ROBOT_BACKEND", "PHYSICAL").upper()
        if backend_type == "VIRTUAL":
            self.physical_motion_authorized = True
            return

        if self.backend is None:
            print("  ⚠️ Backend không khả dụng — không thể calibrate physical board pose.")
            self.physical_motion_authorized = False
            self.board_pose_provider = None
            self.motion_profile = None
            self.motion_resolver = None
            self.motion_executor = None
            self.motion_coordinator = None
            return

        # Explicit Physical Calibration Profile Resolution
        cal_profile: Optional[BoardCalibrationProfile] = None
        if self.board_calibration_profile is not None:
            cal_profile = self.board_calibration_profile
        else:
            cal_mode = getattr(self.config, "BOARD_CALIBRATION_MODE", None)
            if cal_mode == "POINTER_CONTACT":
                cal_profile = BoardCalibrationProfile(
                    tcp_to_board_contact_offset_mm=[0.0, 0.0, 0.0],
                    offset_frame="ROBOT_BASE",
                    provenance="CALIBRATED_POINTER_CONTACT",
                )
            elif cal_mode == "KNOWN_OFFSET":
                offset = getattr(self.config, "BOARD_CALIBRATION_OFFSET_MM", None)
                frame = getattr(self.config, "BOARD_CALIBRATION_OFFSET_FRAME", None)
                prov = getattr(self.config, "BOARD_CALIBRATION_PROVENANCE", None)
                if (
                    not isinstance(offset, (list, tuple))
                    or len(offset) != 3
                    or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in offset)
                    or frame not in ("TOOL", "ROBOT_BASE")
                    or not prov
                    or not str(prov).strip()
                ):
                    print(f"\n{'='*60}")
                    print("❌ [CRITICAL] Cấu hình KNOWN_OFFSET không hợp lệ hoặc thiếu thông số:")
                    print(f"   BOARD_CALIBRATION_OFFSET_MM: {offset}")
                    print(f"   BOARD_CALIBRATION_OFFSET_FRAME: {frame}")
                    print(f"   BOARD_CALIBRATION_PROVENANCE: {prov}")
                    print("   Robot motion đã bị VÔ HIỆU HÓA. Physical board calibration failed closed.")
                    print(f"{'='*60}\n")
                    self.physical_motion_authorized = False
                    self.board_pose_provider = None
                    self.motion_profile = None
                    self.motion_resolver = None
                    self.motion_executor = None
                    self.motion_coordinator = None
                    return
                cal_profile = BoardCalibrationProfile(
                    tcp_to_board_contact_offset_mm=[float(offset[0]), float(offset[1]), float(offset[2])],
                    offset_frame=frame,
                    provenance=str(prov).strip(),
                )
            else:
                print(f"\n{'='*60}")
                print("❌ [CRITICAL] Thiếu hoặc sai cấu hình chế độ calibrate bàn cờ thật (BOARD_CALIBRATION_MODE):")
                print(f"   BOARD_CALIBRATION_MODE hiện tại: {cal_mode}")
                print("   PHYSICAL mode yêu cầu cấu hình rõ ràng: 'POINTER_CONTACT' hoặc 'KNOWN_OFFSET'.")
                print("   Robot motion đã bị VÔ HIỆU HÓA. Physical board calibration failed closed.")
                print(f"{'='*60}\n")
                self.physical_motion_authorized = False
                self.board_pose_provider = None
                self.motion_profile = None
                self.motion_resolver = None
                self.motion_executor = None
                self.motion_coordinator = None
                return

        # Explicit Physical Calibration Tolerance Policy Resolution
        cal_policy: BoardCalibrationTolerancePolicy
        if self.board_calibration_policy is not None:
            cal_policy = self.board_calibration_policy
        else:
            warning_tilt = getattr(self.config, "BOARD_MAX_TILT_WARNING_DEG", 2.5)
            hard_fail_tilt = getattr(self.config, "BOARD_MAX_TILT_HARD_FAIL_DEG", 5.0)
            cal_policy = BoardCalibrationTolerancePolicy(
                max_board_tilt_warning_deg=float(warning_tilt),
                max_board_tilt_hard_fail_deg=float(hard_fail_tilt),
            )

        try:
            provider = PhysicalTeachingPointBoardPoseProvider.from_controller(
                self.backend,
                calibration_profile=cal_profile,
                tolerance_policy=cal_policy,
            )
            res = provider.calibration_result

            if not res.success:
                print(f"\n{'='*60}")
                print(f"❌ [CRITICAL] Physical board calibration THẤT BẠI: {res.error_message}")
                print(f"   RMS error: {res.rms_error_mm:.3f} mm, Max error: {res.max_error_mm:.3f} mm")
                print("   Robot motion đã bị VÔ HIỆU HÓA. Không fallback sang simulation.")
                print(f"{'='*60}\n")
                self.physical_motion_authorized = False
                self.board_pose_provider = None
                self.motion_profile = None
                self.motion_resolver = None
                self.motion_executor = None
                self.motion_coordinator = None
                return

            self.board_pose_provider = provider
            self.physical_motion_authorized = True
            print(f"  ✅ Calibrated physical board pose thành công:")
            if res.calibration_log:
                print(f"{res.calibration_log}")
            if res.warnings:
                for w in res.warnings:
                    print(f"  ⚠️ [CALIBRATION WARNING] {w}")

            # Setup MotionProfile with explicit provenance
            prov = getattr(self.config, "PICK_HEIGHT_PROVENANCE", "PROVISIONAL_SIMULATION")
            self.motion_profile = MotionProfile(
                pick_tcp_height_above_board_mm=getattr(self.config, "PICK_TCP_HEIGHT_MM", 4.715),
                place_tcp_height_above_board_mm=getattr(self.config, "PLACE_TCP_HEIGHT_MM", 4.715),
                safe_clearance_above_board_mm=getattr(self.config, "SAFE_CLEARANCE_Z_MM", 40.0),
                provenance=prov,
            )
            if not self.motion_profile.is_physical_validated:
                print(f"  ⚠️ [MAIN WARNING] Physical grasp height is {prov}, not measured physical truth.")

            tool_rot = getattr(self.config, "PICK_TOOL_ROTATION", [-179.164, -3.047, -26.304])
            self.motion_resolver = MotionResolver(
                board_pose_provider=self.board_pose_provider,
                motion_profile=self.motion_profile,
                tool_rotation_deg=tool_rot,
            )
            self.motion_executor = MotionExecutor(
                backend=self.backend,
                payload_verifier=None,
            )
            self.motion_coordinator = MotionCoordinator(
                backend=self.backend,
                board_pose_provider=self.board_pose_provider,
                motion_profile=self.motion_profile,
                tool_rotation_deg=tool_rot,
            )
            print("[MAIN] 🧭 MotionResolver & MotionExecutor initialized with Calibrated Physical Board Pose.")

            # Deprecated: Keep legacy config variables populated for non-migrated code
            # Note: The new motion path (MotionResolver/Executor) does NOT depend on these.
            state = self.board_pose_provider.get_board_placement_state()
            p_r1 = state.cell_to_robot_xyz(0, 0, height_above_board_mm=0.0)
            self.config.BOARD_ORIGIN_X = float(p_r1[0]) * 1000.0
            self.config.BOARD_ORIGIN_Y = float(p_r1[1]) * 1000.0
            print(f"  [LEGACY] Synced deprecated config.BOARD_ORIGIN_X={self.config.BOARD_ORIGIN_X:.3f}, Y={self.config.BOARD_ORIGIN_Y:.3f}")

        except Exception as e:
            print(f"\n{'='*60}")
            print(f"❌ [CRITICAL] Lỗi trong quá trình calibrate physical board: {e}")
            print("   Robot motion đã bị VÔ HIỆU HÓA. Không fallback sang simulation.")
            print(f"{'='*60}\n")
            self.physical_motion_authorized = False
            self.board_pose_provider = None
            self.motion_profile = None
            self.motion_resolver = None
            self.motion_executor = None
            self.motion_coordinator = None

    def _init_ai(self):
        engine_type = getattr(self.config, "ENGINE_TYPE", "LOCAL")
        local_engine = None
        cloud_engine = None

        # 1. Khởi tạo Local Moonfish (nếu cần)
        if engine_type in ["HYBRID", "LOCAL"]:
            try:
                exe_path = self.config.MOONFISH_EXE
                nnue_path = self.config.MOONFISH_NNUE
                local_engine = MoonfishEngine(exe_path)
                local_engine.start(nnue_path=nnue_path)
                print(f"✅ Moonfish engine started! (think={self.config.MOONFISH_THINK_MS}ms)")
            except Exception as e:
                print(f"⚠️ Moonfish init error: {e}")
                local_engine = None
            
            if local_engine is None and not self.dry_run:
                print("\n========================================================")
                print("⚠️ CẢNH BÁO: KHÔNG TÌM THẤY MOONFISH ENGINE DỰ PHÒNG LOCAL!")
                print("   Hệ thống sẽ duy trì hoạt động bằng API Cloud Engine.")
                print("========================================================\n")

        # 2. Khởi tạo Cloud Engine (nếu cần)
        if engine_type in ["HYBRID", "CLOUD"]:
            try:
                cloud_api = getattr(self.config, "CLOUD_API_URL", "https://tuongkydaisu.com/api/engine/bestmove")
                cloud_timeout = getattr(self.config, "CLOUD_TIMEOUT_SEC", 5)
                cloud_engine = CloudEngine(api_url=cloud_api, timeout_sec=cloud_timeout)
                cloud_engine.start()
                print(f"✅ Cloud Engine initialized! (API: {cloud_api})")
            except Exception as e:
                print(f"⚠️ Cloud Engine init error: {e}")
                cloud_engine = None

        # 3. Giao cho AI Controller quản lý cả 2
        self.ai_ctrl = AIController(local_engine, cloud_engine, self.config)

    def _init_camera(self):
        # Initialize CChessRecognizer if ONNX models exist
        try:
            from src.vision.cchess_recognizer import CChessRecognizer
            pose_onnx = Path(self.project_dir) / getattr(self.config, "CCHESS_POSE_MODEL_PATH", "models/cchess/pose_4_v6.onnx")
            layout_onnx = Path(self.project_dir) / getattr(self.config, "CCHESS_LAYOUT_MODEL_PATH", "models/cchess/layout_nano_v3.onnx")
            if pose_onnx.exists() and layout_onnx.exists():
                self.cchess_recognizer = CChessRecognizer(pose_onnx, layout_onnx)
                print("[INIT] [CChess] ✅ CChessRecognizer loaded successfully (pose + layout ONNX).")
            else:
                print(f"[INIT] [CChess] ⚠️ ONNX models not found ({pose_onnx}, {layout_onnx}).")
        except Exception as e:
            print(f"[INIT] [CChess] ⚠️ Could not initialize CChessRecognizer: {e}")

        if self.dry_run:
            return

        model_path = str(Path(self.project_dir) / "models" / "best.pt")
        try:
            if YOLO is not None:
                self.model = YOLO(model_path)
                print(f"✅ Model loaded: {model_path}")
            else:
                print("⚠️ Warning: Module 'ultralytics' chưa được cài đặt, bỏ qua load YOLO model.")
        except Exception as e:
            print(f"⚠️ Warning: Could not load YOLO model: {e}")
            
        cam_index = int(os.environ.get("VIDEO_INDEX", str(self.config.VIDEO_SOURCE)))
        for idx in [cam_index] + [i for i in [0, 1, 2] if i != cam_index]:
            cap_try = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if cap_try.isOpened():
                self.cap = cap_try
                print(f"✅ Camera opened at index {idx}")
                break
            else:
                cap_try.release()
                
        if self.cap is None:
            print("❌ Lỗi: Không mở được Camera!")
            sys.exit()
            
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        # Calibrate Vision (RTMPose ONNX Auto-Calibration + Manual Fallback)
        print("\n" + "=" * 60)
        print("  📐  CAMERA CALIBRATION — BẮT BUỘC KHI KHỞI ĐỘNG")
        print("=" * 60)
        from src.vision.auto_calibrate import run_calibration_flow
        calib_matrix = run_calibration_flow(
            self.cap, str(self.perspective_path), cchess_recognizer=self.cchess_recognizer
        )
        
        if calib_matrix is None:
            print("\n" + "=" * 60)
            print("❌ [CRITICAL] Camera calibration thất bại hoặc bị hủy!")
            print("   Không thể tái sử dụng perspective matrix cũ một cách ngầm định.")
            print("   Hệ thống Vision không thể khởi động an toàn. Thao tác bị dừng.")
            print("=" * 60 + "\n")
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            self.camera_ready = False
            sys.exit(1)

        self.camera_ready = True

        # Start Monitor
        if self.model is not None:
            self.cam_monitor = CameraMonitor(self.cap, self.model, self.perspective_path)
            self.cam_monitor.start()
            self.yolo_detector = YoloSnapshotDetector(self.perspective_path, self.class_id_to_name)
            print("[INIT] ✅ YoloSnapshotDetector initialized.")
            if getattr(self.config, "VISUAL_PICK_ENABLED", False):
                try:
                    self.pick_estimator = VisualPickEstimator(
                        self.perspective_path,
                        min_confidence=self.config.VISUAL_PICK_MIN_CONFIDENCE,
                        max_offset_cells=self.config.VISUAL_PICK_MAX_OFFSET_CELLS,
                        foot_ratio=self.config.VISUAL_PICK_FOOT_RATIO,
                    )
                    print("[INIT] ✅ VisualPickEstimator initialized.")
                except Exception as e:
                    print(f"[INIT] ⚠️ Visual pick disabled: cannot initialize estimator: {e}")

        if getattr(self.config, "AUTO_MOVE_CONFIRM_ENABLED", False) and YOLO is not None:
            hand_path = Path(self.project_dir) / getattr(self.config, "HAND_MODEL_PATH", "models/hand_best_egohands.pt")
            try:
                if hand_path.exists():
                    self.hand_model = YOLO(str(hand_path))
                    self.turn_completion_monitor = TurnCompletionMonitor(
                        getattr(self.config, "HAND_ABSENCE_SECONDS", 0.8),
                        getattr(self.config, "HAND_MIN_PRESENT_SECONDS", 0.25),
                    )
                    print("[INIT] ✅ Hand-aware automatic move confirmation enabled.")
                else:
                    print(f"[INIT] ⚠️ Hand model not found: {hand_path}")
            except Exception as e:
                print(f"[INIT] ⚠️ Hand-aware confirmation disabled: {e}")

    def hand_interaction_finished(self) -> bool:
        """Return True once after a hand has entered then cleared the board ROI."""
        if self.hand_model is None or self.turn_completion_monitor is None or self.cam_monitor is None:
            return False
        now = time.monotonic()
        if now - self._last_hand_check < 0.10:
            return False
        self._last_hand_check = now
        frame, _ = self.cam_monitor.get_latest_frame_and_detections()
        if frame is None:
            return False
        hand_on_board = False
        try:
            result = self.hand_model(frame, conf=getattr(self.config, "HAND_CONFIDENCE", 0.45), verbose=False)[0]
            boxes = getattr(result, "boxes", None)
            if boxes is not None and len(boxes) > 0:
                polygon = self.cam_monitor._compute_board_polygon()
                if polygon is None:
                    return False
                for box in boxes.xyxy.cpu().tolist():
                    cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
                    if cv2.pointPolygonTest(polygon, (cx, cy), False) >= 0:
                        hand_on_board = True
                        break
        except Exception as e:
            print(f"[HAND] ⚠️ Detection error: {e}")
            return False
        return self.turn_completion_monitor.observe(hand_on_board, now)

    def reset_hand_interaction_monitor(self):
        if self.turn_completion_monitor is not None:
            self.turn_completion_monitor.reset()

    def enable_robot(self) -> bool:
        """Explicitly enable robot actuators for motion (non-read-only)."""
        if self.backend is not None and hasattr(self.backend, "enable_robot"):
            return self.backend.enable_robot()
        return True

    def disable_robot(self) -> bool:
        """Explicitly disable robot actuators (safe idling)."""
        if self.backend is not None and hasattr(self.backend, "disable_robot"):
            return self.backend.disable_robot()
        return True

    def set_operational_mode(self, mode: int = 0) -> bool:
        """Set robot controller operational mode (0: automatic, 1: manual)."""
        if self.backend is not None and hasattr(self.backend, "set_operational_mode"):
            return self.backend.set_operational_mode(mode)
        return True

    @property
    def is_robot_ready(self) -> bool:
        """
        Returns True if authoritative backend is ready for motion.
        For Physical mode, strictly requires:
          1. backend connected
          2. backend enabled (or dry_run)
          3. board provider calibrated
          4. motion_resolver and motion_executor available
          5. physical motion authorized
        For Virtual mode, requires:
          1. backend connected
          2. board_pose_provider available
          3. motion_resolver and motion_executor available
        """
        backend_type = getattr(self.config, "ROBOT_BACKEND", "PHYSICAL").upper()
        if backend_type == "PHYSICAL":
            if self.backend is None:
                return False
            snapshot = self.backend.get_state_snapshot()
            if not snapshot.connected:
                return False
            backend_enabled = getattr(self.backend, "is_enabled", False)
            if not self.dry_run and not backend_enabled:
                return False
            board_calibrated = (
                self.board_pose_provider is not None
                and getattr(self.board_pose_provider, "is_calibrated", False)
            )
            if not board_calibrated:
                return False
            if self.motion_resolver is None or self.motion_executor is None:
                return False
            return bool(self.physical_motion_authorized)
        elif backend_type == "VIRTUAL":
            if self.backend is None:
                return False
            snapshot = self.backend.get_state_snapshot()
            return bool(
                snapshot.connected
                and self.board_pose_provider is not None
                and self.motion_resolver is not None
                and self.motion_executor is not None
            )
        else:
            if self.backend is not None:
                return bool(
                    self.backend.get_state_snapshot().connected
                    and self.motion_resolver is not None
                    and self.motion_executor is not None
                )
            return bool(self.robot and self.robot.connected and self.physical_motion_authorized)

    def execute_piece_move(
        self,
        s_col: int,
        s_row: int,
        d_col: int,
        d_row: int,
        is_capture: bool,
        moving_visual_target: Optional[object] = None,
        captured_visual_target: Optional[object] = None,
        piece_id: Optional[str] = None,
        captured_piece_id: Optional[str] = None,
    ) -> MotionExecutionResult:
        """
        Execute pick-and-place move through the authoritative MotionResolver and MotionExecutor.
        """
        backend_type = getattr(self.config, "ROBOT_BACKEND", "PHYSICAL").upper()
        if not self.is_robot_ready:
            print("[ROBOT] ❌ Motion rejected: robot is not ready or calibration failed.")
            return MotionExecutionResult.fail(
                failed_stage=MotionStage.PREPOSITION,
                category=ExecutionFailureCategory.PRECONDITION_FAILED,
                message=f"Robot is not ready for motion (backend_type={backend_type}, dry_run={self.dry_run}).",
            )

        if is_capture and backend_type == "PHYSICAL":
            if not getattr(self.config, "CAPTURE_BIN_VALIDATED", False):
                print("[ROBOT] ❌ Physical capture rejected: CAPTURE_BIN_VALIDATED is False.")
                return MotionExecutionResult.fail(
                    failed_stage=MotionStage.PREPOSITION,
                    category=ExecutionFailureCategory.SAFETY_INTERLOCK,
                    message="Physical capture bin is not validated (CAPTURE_BIN_VALIDATED=False). Autonomous physical captures disabled until Phase 4 validation.",
                )

        if self.motion_resolver is None or self.motion_executor is None:
            return MotionExecutionResult.fail(
                failed_stage=MotionStage.PREPOSITION,
                category=ExecutionFailureCategory.PRECONDITION_FAILED,
                message="MotionResolver or MotionExecutor is not initialized.",
            )

        capture_pose = getattr(self.config, "CAPTURE_BIN_POSE_MM_DEG", None)
        if capture_pose is None:
            capture_pose = [
                getattr(self.config, "CAPTURE_BIN_X", -226.123),
                getattr(self.config, "CAPTURE_BIN_Y", 225.024),
                getattr(self.config, "CAPTURE_BIN_Z", 291.68),
            ] + list(getattr(self.config, "ROTATION", [-179.164, -3.047, -26.304]))

        try:
            if is_capture:
                intent = CaptureIntent(
                    src_row=float(s_row),
                    src_col=float(s_col),
                    dst_row=float(d_row),
                    dst_col=float(d_col),
                    bin_pose_mm_deg=tuple(float(v) for v in capture_pose),  # type: ignore
                    attacker_piece_id=piece_id,
                    captured_piece_id=captured_piece_id,
                )
                plan = self.motion_resolver.resolve_capture(
                    intent=intent,
                    moving_visual_target=moving_visual_target,
                    captured_visual_target=captured_visual_target,
                )
            else:
                intent = PieceMoveIntent(
                    src_row=float(s_row),
                    src_col=float(s_col),
                    dst_row=float(d_row),
                    dst_col=float(d_col),
                    piece_id=piece_id,
                )
                plan = self.motion_resolver.resolve_move(
                    intent=intent,
                    moving_visual_target=moving_visual_target,
                )
        except Exception as e:
            return MotionExecutionResult.fail(
                failed_stage=MotionStage.PREPOSITION,
                category=ExecutionFailureCategory.INVALID_PLAN,
                message=f"Plan resolution error: {e}",
            )

        if self.simulation_runtime is not None and hasattr(self.simulation_runtime, "acquire_operation_state"):
            try:
                from src.simulation.runtime import RuntimeOperationState
                with self.simulation_runtime.acquire_operation_state(RuntimeOperationState.MOTION):
                    res = self.motion_executor.execute_plan(plan)
            except Exception as e:
                return MotionExecutionResult.fail(
                    failed_stage=MotionStage.PREPOSITION,
                    category=ExecutionFailureCategory.ROBOT_BUSY,
                    message=f"Simulation runtime operation error: {e}",
                )
        else:
            res = self.motion_executor.execute_plan(plan)

        self._last_execution_result = res
        return res

    def move_piece(
        self,
        s_col: int,
        s_row: int,
        d_col: int,
        d_row: int,
        is_capture: bool,
        moving_visual_target: Optional[object] = None,
        captured_visual_target: Optional[object] = None,
        piece_id: Optional[str] = None,
        captured_piece_id: Optional[str] = None,
    ) -> bool:
        """
        Legacy compatibility wrapper over execute_piece_move.
        Returns True if execution succeeded, False otherwise.
        """
        res = self.execute_piece_move(
            s_col=s_col,
            s_row=s_row,
            d_col=d_col,
            d_row=d_row,
            is_capture=is_capture,
            moving_visual_target=moving_visual_target,
            captured_visual_target=captured_visual_target,
            piece_id=piece_id,
            captured_piece_id=captured_piece_id,
        )
        return bool(res.success)

    def cleanup(self):
        print("[CLEANUP] Đang dọn dẹp hardware...")
        if self.gripper_driver is not None and hasattr(self.gripper_driver, "safe_idle"):
            try: self.gripper_driver.safe_idle()
            except: pass
        if self.simulation_runtime is not None and hasattr(self.simulation_runtime, "stop"):
            try: self.simulation_runtime.stop()
            except: pass
        if self.backend is not None:
            try: self.backend.disconnect()
            except: pass
        if self.cam_monitor:
            try: self.cam_monitor.stop()
            except: pass
        if getattr(self, 'ai_ctrl', None):
            if self.ai_ctrl.local_engine:
                try: self.ai_ctrl.local_engine.stop()
                except: pass
            if self.ai_ctrl.cloud_engine:
                try: self.ai_ctrl.cloud_engine.stop()
                except: pass
        if getattr(self, 'engine', None): # Legacy support
            try: self.engine.stop()
            except: pass
        if self.cap and self.cap.isOpened():
            try: self.cap.release()
            except: pass
        if self.robot and getattr(self.robot, "connected", False) and not self.dry_run:
            try: self.robot.robot.RobotEnable(0)
            except: pass

    # --- WRAPPER VISION UTILS ---
    def get_visual_pick_targets(self, expected_cells):
        """Lấy snapshot trước khi robot di chuyển và ước lượng điểm gắp thực tế.
        Bọc phòng thủ toàn diện: Mọi ngoại lệ đều tự động fallback về None (tâm ô lý thuyết).
        """
        targets = {name: None for name in expected_cells}
        if not self.pick_estimator:
            print("[VISUAL PICK] Fallback: pick_estimator chưa được khởi tạo.")
            return targets

        if not self.cam_monitor:
            print("[VISUAL PICK] Fallback: cam_monitor chưa được khởi tạo.")
            return targets

        # 1. Bọc an toàn khi lấy snapshot từ camera
        try:
            if not hasattr(self.cam_monitor, "get_fresh_snapshot"):
                print("[VISUAL PICK] ⚠️ cam_monitor thiếu method 'get_fresh_snapshot'. Dùng fallback tâm ô.")
                return targets

            _frame, detections = self.cam_monitor.get_fresh_snapshot()
            if _frame is None:
                print("[VISUAL PICK] ⚠️ Không lấy được frame mới từ camera. Dùng fallback tâm ô.")
                return targets
        except Exception as e:
            print(f"[VISUAL PICK] ⚠️ Ngoại lệ khi snapshot camera: {e}. Dùng fallback tâm ô.")
            return targets

        # 2. Bọc an toàn khi ước lượng từng ô cờ
        for name, cell in expected_cells.items():
            try:
                col, row = cell
                targets[name] = self.pick_estimator.estimate_pick_target(detections, col, row)
            except Exception as e:
                print(f"[VISUAL PICK] ⚠️ Lỗi ước lượng cho {name} tại {cell!r}: {e}. Fallback ô này.")
                targets[name] = None

        return targets

    def capture_baseline_if_needed(self, force_delay=0.0):
        if self.cam_monitor and self.yolo_detector:
            if force_delay > 0:
                time.sleep(force_delay)
            frame, detections = self.cam_monitor.get_fresh_snapshot()
            success = self.yolo_detector.capture_baseline(frame, detections)
            return success
        return False

    def clear_yolo_baseline(self):
        if self.yolo_detector:
            self.yolo_detector._baseline_occ = None

    def restore_yolo_baseline(self, occ, baseline_time):
        if self.yolo_detector and occ is not None:
            self.yolo_detector._baseline_occ = [row[:] for row in occ]
            self.yolo_detector._baseline_time = baseline_time

    def recognize_board_state(self, frame=None):
        """Nhận diện toàn bộ bàn cờ (10x9) bằng CChessRecognizer ONNX models.
        
        Args:
            frame: OpenCV BGR frame. Nếu None, sẽ lấy từ CameraMonitor.
            
        Returns:
            dict kết quả từ CChessRecognizer.full_recognize() hoặc None nếu không khả dụng.
        """
        if self.cchess_recognizer is None:
            return None

        if frame is None and self.cam_monitor is not None:
            frame, _ = self.cam_monitor.get_latest_frame_and_detections()

        if frame is None:
            return None

        return self.cchess_recognizer.full_recognize(frame)
