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
from src.vision.auto_calibrate import run_calibration_flow

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
        self.cchess_recognizer = None
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
        # Initialize CChessRecognizer (ONNX)
        if getattr(self.config, "CCHESS_RECOGNITION_ENABLED", True):
            try:
                from src.vision.cchess_recognizer import CChessRecognizer
                pose_onnx = Path(self.project_dir) / "models" / "cchess" / "pose_4_v6.onnx"
                layout_onnx = Path(self.project_dir) / "models" / "cchess" / "layout_nano_v3.onnx"
                if pose_onnx.exists() and layout_onnx.exists():
                    self.cchess_recognizer = CChessRecognizer(pose_onnx, layout_onnx)
                    print("[INIT] [CChess] CChessRecognizer loaded successfully (pose + layout ONNX).")
                else:
                    print("[INIT] [CChess] ONNX models not found in models/cchess/.")
            except Exception as e:
                print(f"[INIT] [CChess] Could not initialize CChessRecognizer: {e}")

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

        # Calibrate Vision (RTMPose ONNX thay cho YOLO-Pose cũ)
        print("\n" + "=" * 60)
        print("  CAMERA CALIBRATION - BAT BUOC KHI KHOI DONG")
        print("=" * 60)
        run_calibration_flow(self.cap, str(self.perspective_path), cchess_recognizer=self.cchess_recognizer)
        
        if not os.path.exists(str(self.perspective_path)):
            print("❌ Chưa có perspective.npy! Không thể detect nước đi.")
            sys.exit()

        # Start Monitor (Ưu tiên CChessRecognizer ONNX)
        if self.model is not None or self.cchess_recognizer is not None:
            self.cam_monitor = CameraMonitor(
                self.cap,
                model=self.model,
                perspective_path=self.perspective_path,
                cchess_recognizer=self.cchess_recognizer,
            )
            self.cam_monitor.start()
            self.yolo_detector = YoloSnapshotDetector(self.perspective_path, self.class_id_to_name)
            print("[INIT] SnapshotDetector & CameraMonitor initialized (CChess ONNX enabled).")
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
            try: self.robot._set_gripper_safe_idle()
            except Exception as e: print(f"[CLEANUP] ⚠️ Không thể tắt gripper Tool DO: {e}")
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
        Ưu tiên dùng ma trận phối cảnh đã cân chỉnh để nắn bàn cờ chuẩn xác và ổn định nhất.
        
        Args:
            frame: OpenCV BGR frame. Nếu None, sẽ lấy từ CameraMonitor.
            
        Returns:
            dict kết quả nhận diện bàn cờ hoặc None nếu không khả dụng.
        """
        if self.cchess_recognizer is None:
            return None

        if frame is None and self.cam_monitor is not None:
            frame, _ = self.cam_monitor.get_latest_frame_and_detections()

        if frame is None:
            return None

        # 1. Ưu tiên nắn bằng 4 góc đã hiệu chỉnh (calibrated perspective)
        if os.path.exists(str(self.perspective_path)):
            try:
                M = np.load(str(self.perspective_path))
                inv_M = np.linalg.inv(M)
                grid_kpts = np.array([
                    [[0.0, 0.0]], [[8.0, 0.0]], [[0.0, 9.0]], [[8.0, 9.0]]
                ], dtype=np.float32)
                kpts_px = cv2.perspectiveTransform(grid_kpts, inv_M).reshape(4, 2)
                warped, _ = self.cchess_recognizer.extract_rectified_board(frame, kpts_px)
                board_proj, board_short, confs = self.cchess_recognizer.recognize_layout(warped)
                return {
                    "success": True,
                    "board": board_proj,
                    "board_short": board_short,
                    "confidence": confs,
                    "keypoints": kpts_px,
                    "warped_image": warped,
                    "error": None,
                }
            except Exception as e:
                print(f"[RECOGNIZE] Fallback to full_recognize: {e}")

        # 2. Fallback sang phát hiện lại 4 góc nếu chưa có perspective.npy
        return self.cchess_recognizer.full_recognize(frame)
