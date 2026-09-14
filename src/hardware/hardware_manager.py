import os
import time
import sys
import numpy as np
import cv2
import threading
from pathlib import Path

from src.hardware.robot_VIP import FR5Robot
from src.ai.moonfish_engine import MoonfishEngine
from src.ai.cloud_engine import CloudEngine
from src.ai.ai_controller import AIController
from src.vision.camera_monitor import CameraMonitor
from src.vision.snapshot_detector import SnapshotDetector as YoloSnapshotDetector
from src.vision.visual_pick_estimator import VisualPickEstimator
from src.vision.calibrate_camera import calibrate_perspective_camera

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None

class HardwareManager:
    """Manages Robot, Camera (Vision), and AI Engine connections."""
    def __init__(self, config, project_dir):
        self.config = config
        self.project_dir = project_dir
        self.dry_run = config.DRY_RUN
        
        # Hardware instances
        self.robot = FR5Robot()
        self.engine = None
        self.ai_ctrl = None
        self.cap = None
        self.model = None
        self.cam_monitor = None
        self.yolo_detector = None
        self.pick_estimator = None
        self.perspective_path = Path(project_dir) / "perspective.npy"
        
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
        if not self.dry_run:
            try:
                self.robot.connect()
                print("[MAIN] ✅ Robot kết nối thành công.")
            except Exception as e:
                print(f"⚠️ [MAIN] Robot connection error: {e}")
                print("   → Tiếp tục chạy KHÔNG có robot (camera + calibrate vẫn hoạt động)")
                self.robot.connected = False

            if self.robot.connected:
                try:
                    self.robot.go_to_home_chess()
                except Exception as e:
                    print(f"⚠️ [MAIN] go_to_home_chess lỗi: {e} → bỏ qua, robot vẫn CONNECTED")
        else:
            print("[MAIN] DRY_RUN: Skipping physical robot connection.")
            self.robot.connected = False

        self._calibrate_robot()

    def _calibrate_robot(self):
        print("\n--- ROBOT CALIBRATION (R1 ORIGIN) ---")
        if not self.robot.connected:
            print("  ℹ️ Robot chưa kết nối — sử dụng tọa độ gốc mặc định từ config.")
            return

        try:
            if self.dry_run:
                self.config.BOARD_ORIGIN_X = 200.0
                self.config.BOARD_ORIGIN_Y = -100.0
                print(f"  ✅ DRY RUN: Gán gốc giả định X={self.config.BOARD_ORIGIN_X:.3f}, Y={self.config.BOARD_ORIGIN_Y:.3f}")
            else:
                print("Reading coordinates from robot for R1...")
                err, data = self.robot.robot.GetRobotTeachingPoint("R1")
                if err != 0:
                    raise Exception(f"Error getting teaching point R1 (err={err})")
                self.config.BOARD_ORIGIN_X = float(str(data[0]).strip())
                self.config.BOARD_ORIGIN_Y = float(str(data[1]).strip())
                print(f"  ✅ Đã lấy gốc R1 thực tế: X={self.config.BOARD_ORIGIN_X:.3f}, Y={self.config.BOARD_ORIGIN_Y:.3f}")

            print("=== ROBOT CALIBRATION OK ===")
        except Exception as e:
            print(f"\n{'='*60}")
            print(f"❌ [CRITICAL] Robot calibration (R1) THẤT BẠI: {e}")
            self.robot.connected = False
            print("   Robot đã bị vô hiệu hóa. Game tiếp tục ở chế độ KHÔNG CÓ ROBOT.")

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

        # Calibrate Vision
        print("\n" + "=" * 60)
        print("  📐  CAMERA CALIBRATION — BẮT BUỘC KHI KHỞI ĐỘNG")
        print("=" * 60)
        if os.path.exists(str(self.perspective_path)):
            print(f"⚠️  Đã có file cũ: {self.perspective_path}")
            print("   Bấm 'S' để dùng lại hoặc calibrate lại bằng cách click 4 góc.")
        calibrate_perspective_camera(self.cap, str(self.perspective_path))
        
        if not os.path.exists(str(self.perspective_path)):
            print("❌ Chưa có perspective.npy! Không thể detect nước đi.")
            sys.exit()

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

    def cleanup(self):
        print("[CLEANUP] Đang dọn dẹp hardware...")
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
        if self.robot and self.robot.connected and not self.dry_run:
            try: self.robot.robot.RobotEnable(0)
            except: pass

    # --- WRAPPER VISION UTILS ---
    def get_visual_pick_targets(self, expected_cells):
        """Take one fresh pre-motion snapshot and estimate requested pick points.

        ``expected_cells`` maps labels (normally ``moving``/``captured``) to
        ``(col, row)`` logical cells. Every missing/unsafe result is ``None`` so
        the robot retains its existing center-of-cell fallback.
        """
        targets = {name: None for name in expected_cells}
        if not self.pick_estimator or not self.cam_monitor:
            print("[VISUAL PICK] Fallback: estimator or camera monitor unavailable.")
            return targets

        _frame, detections = self.cam_monitor.get_fresh_snapshot()
        if _frame is None:
            print("[VISUAL PICK] Fallback: fresh camera snapshot unavailable.")
            return targets

        for name, cell in expected_cells.items():
            try:
                col, row = cell
                targets[name] = self.pick_estimator.estimate_pick_target(detections, col, row)
            except (TypeError, ValueError) as e:
                print(f"[VISUAL PICK] Fallback for {name}: invalid expected cell {cell!r}: {e}")
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
