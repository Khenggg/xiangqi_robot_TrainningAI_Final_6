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
from src.vision.pick_geometry import PickGeometry
from src.vision.top_face_pick_estimator import TopFacePickEstimator
from src.vision.homography_pick_geometry import HomographyPickGeometry
from src.vision.pick_consensus import select_consensus, FreshPickTransientError, require_pick_target
from src.vision.board_reconciler import BoardReconciler
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
        self.center_pick_estimator = None
        self.top_face_pick_estimator = None
        self.actual_camera_index = None
        self.board_reconciler = None
        self._difficulty_availability = {"easy": False, "medium": False, "hard": False}
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
        difficulty = getattr(self.config, "AI_DIFFICULTY", "hard")

        # 1. Khởi tạo Local Moonfish (nếu cần)
        if engine_type in ["HYBRID", "LOCAL"] or difficulty in ("easy", "medium", "hard", "impossible"):
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
        self._difficulty_availability = {
            difficulty_name: local_engine is not None and local_engine._ready
            for difficulty_name in ("easy", "medium", "hard", "impossible")
        }

    def difficulty_availability(self):
        """Return which menu options can be selected without weakening a choice."""
        return dict(self._difficulty_availability)

    def select_difficulty(self, difficulty):
        """Switch engine only after its requested policy is usable."""
        if difficulty not in ("easy", "medium", "hard", "impossible"):
            return False, "Unknown difficulty"
        if not self.difficulty_availability().get(difficulty, False):
            return False, f"{difficulty.title()} is not ready on this machine"
        def confirmation():
            profile = getattr(self.config, "AI_DIFFICULTY_PROFILES", {}).get(difficulty, {})
            if difficulty == "impossible":
                return "Đã chọn IMPOSSIBLE — Moonfish nguyên gốc đang được sử dụng."
            return (f"Đã chọn {difficulty.upper()} — Moonfish depth {profile.get('depth')}, "
                    f"≤{profile.get('nodes'):,} nodes, ≤{profile.get('think_ms') / 1000:g}s.")

        if difficulty == getattr(self.config, "AI_DIFFICULTY", "hard"):
            message = confirmation()
            print(f"[GAME] {message}")
            return True, message
        if self.ai_ctrl is not None:
            if self.ai_ctrl.local_engine is not None:
                self.ai_ctrl.local_engine.stop()
            if self.ai_ctrl.cloud_engine is not None:
                self.ai_ctrl.cloud_engine.stop()
        self.config.AI_DIFFICULTY = difficulty
        self._init_ai()
        message = confirmation()
        print(f"[GAME] {message}")
        return True, message

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
                self.actual_camera_index = idx
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
            if (getattr(self.config, "VISUAL_PICK_ENABLED", False)
                    or getattr(self.config, "VISUAL_BOARD_SYNC_REQUIRED", True)):
                try:
                    self.pick_estimator = VisualPickEstimator(
                        self.perspective_path,
                        min_confidence=self.config.VISUAL_PICK_MIN_CONFIDENCE,
                        max_offset_cells=self.config.VISUAL_PICK_MAX_OFFSET_CELLS,
                        foot_ratio=self.config.VISUAL_PICK_FOOT_RATIO,
                    )
                    # Box center remains occupancy evidence and the explicitly
                    # selected legacy path, never a top-face fallback.
                    self.center_pick_estimator = VisualPickEstimator(
                        self.perspective_path,
                        min_confidence=self.config.VISUAL_PICK_MIN_CONFIDENCE,
                        max_offset_cells=self.config.VISUAL_PICK_MAX_OFFSET_CELLS,
                        foot_ratio=self.config.VISUAL_PICK_FOOT_RATIO,
                        point_mode="center",
                    )
                    self.board_reconciler = BoardReconciler(self.pick_estimator)
                    print("[INIT] ✅ Visual pick / board reconciliation initialized.")
                except Exception as e:
                    print(f"[INIT] ⚠️ Visual pick disabled: cannot initialize estimator: {e}")
            if self._top_face_enabled():
                try:
                    frame, _ = self.cam_monitor.get_fresh_pick_snapshot()
                    mode = getattr(self.config, "VISUAL_TOP_FACE_GEOMETRY_MODE", "metric")
                    if mode == "homography":
                        geometry = HomographyPickGeometry(
                            np.load(self.perspective_path), self.actual_camera_index,
                            frame.shape[1::-1],
                            (self.config.VISUAL_BOARD_WIDTH_MM, self.config.VISUAL_BOARD_HEIGHT_MM))
                    elif mode == "metric":
                        geometry = PickGeometry.load(Path(self.project_dir) / self.config.VISUAL_PICK_GEOMETRY_PATH)
                    else:
                        raise ValueError(f"Unknown top-face geometry mode: {mode}")
                    geometry.validate_context(
                        self.actual_camera_index, frame.shape[1::-1],
                        (self.config.VISUAL_BOARD_WIDTH_MM, self.config.VISUAL_BOARD_HEIGHT_MM),
                        self.config.VISUAL_PIECE_HEIGHT_MM, np.load(self.perspective_path),
                        self.config.VISUAL_GEOMETRY_CORNER_TOLERANCE_PX)
                    self.top_face_pick_estimator = TopFacePickEstimator(
                        geometry, self.config.VISUAL_PICK_MIN_CONFIDENCE,
                        self.config.VISUAL_PICK_MAX_OFFSET_CELLS,
                        self.config.VISUAL_TOP_MAX_RESIDUAL, self.config.VISUAL_TOP_MIN_COVERAGE,
                        self.config.VISUAL_TOP_MIN_BOX_FRACTION, self.config.VISUAL_TOP_RADIUS_MM,
                        self.config.VISUAL_TOP_AMBIGUITY_MM,
                        max_enclosing_area_ratio=self.config.VISUAL_TOP_MAX_ENCLOSING_AREA_RATIO,
                        annulus_offset_mm=self.config.VISUAL_TOP_ANNULUS_OFFSET_MM,
                        min_white_annulus_fraction=self.config.VISUAL_TOP_MIN_WHITE_ANNULUS_FRACTION,
                        max_white_saturation=self.config.VISUAL_TOP_MAX_WHITE_SATURATION,
                        min_white_value=self.config.VISUAL_TOP_MIN_WHITE_VALUE)
                    print(f"[TOP PICK] mode={mode}; geometry={geometry.profile_id}")
                except Exception as exc:
                    self.top_face_pick_estimator = None
                    print(f"[TOP PICK] BLOCKED: {exc}. Check selected geometry mode and recalibrate with RUN closed.")

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
    def _top_face_enabled(self):
        return bool(getattr(getattr(self, "config", None), "VISUAL_TOP_FACE_ENABLED", False))

    def _occupancy_snapshot(self):
        if self._top_face_enabled():
            return self.cam_monitor.get_fresh_pick_snapshot()
        return self.cam_monitor.get_fresh_snapshot()

    def _get_top_face_targets(self, expected_cells):
        targets = {name: None for name in expected_cells}
        self.last_pick_resolution = {"failure": "hard", "reason": "not measured", "attempts": 0, "elapsed_sec": 0.0}
        estimator = getattr(self, "top_face_pick_estimator", None)
        if estimator is None or not self.cam_monitor:
            self.last_pick_resolution["reason"] = "Missing top-face geometry/camera"
            print("[TOP PICK] Missing top-face geometry/camera; no fallback.")
            return targets
        samples = {name: [] for name in expected_cells}
        try:
            initial = getattr(self.config, "VISUAL_PICK_CONSENSUS_INITIAL_SAMPLES", 3)
            maximum = getattr(self.config, "VISUAL_PICK_CONSENSUS_MAX_SAMPLES", 6)
            minimum = getattr(self.config, "VISUAL_PICK_MIN_STABLE_SAMPLES", 2)
            budget = float(getattr(self.config, "VISUAL_PICK_CONSENSUS_TIMEOUT_SEC", 3.0))
            radius = float(getattr(self.config, "VISUAL_PICK_CONSENSUS_RADIUS_MM", 3.75))
            pitch = np.array([self.config.VISUAL_BOARD_WIDTH_MM / 8,
                              self.config.VISUAL_BOARD_HEIGHT_MM / 9], dtype=float)
            if (any(isinstance(v, bool) or int(v) != v for v in (initial, maximum, minimum))
                    or not 3 <= initial <= maximum <= 6 or not 2 <= minimum <= maximum
                    or not np.isfinite([budget, radius, *pitch]).all() or budget <= 0
                    or np.any(pitch <= 0) or not 0 < radius <= min(pitch) * .25):
                raise ValueError("Invalid consensus sampling configuration")
        except Exception as exc:
            self.last_pick_resolution["reason"] = str(exc)
            return targets
        started = time.monotonic()
        deadline = started + budget

        def expired():
            now = time.monotonic()
            self.last_pick_resolution["elapsed_sec"] = max(0.0, now - started)
            if now < deadline:
                return False
            self.last_pick_resolution.update(failure="deadline", reason="Pick sampling budget exhausted; late results rejected")
            print("[TOP PICK] Sampling deadline; no fallback.")
            return True

        for attempt in range(int(maximum)):
            if expired():
                return targets
            self.last_pick_resolution["attempts"] = attempt + 1
            try:
                frame, detections = self.cam_monitor.get_fresh_pick_snapshot()
                if expired():
                    return targets
                estimator.geometry.validate_context(
                    self.actual_camera_index, frame.shape[1::-1],
                    (self.config.VISUAL_BOARD_WIDTH_MM, self.config.VISUAL_BOARD_HEIGHT_MM),
                    self.config.VISUAL_PIECE_HEIGHT_MM, np.load(self.perspective_path),
                    self.config.VISUAL_GEOMETRY_CORNER_TOLERANCE_PX)
                for name, (col, row) in expected_cells.items():
                    samples[name].append(estimator.estimate_pick_target(frame, detections, col, row))
                    print(f"[TOP PICK] {name}: {estimator.last_reason}; profile={estimator.geometry.profile_id}")
                    self.cam_monitor.publish_pick_diagnostic(estimator.diagnostic)
                if expired():
                    return targets
            except FreshPickTransientError as exc:
                for values in samples.values():
                    values.append(None)
                print(f"[TOP PICK] Transient attempt {attempt + 1}: {exc}")
            except Exception as exc:
                self.last_pick_resolution.update(failure="hard", reason=str(exc))
                print(f"[TOP PICK] Snapshot rejected: {exc}")
                return targets
            if expired():
                return targets
            if attempt + 1 < initial:
                continue
            try:
                results = {name: select_consensus(values, pitch, minimum, radius)
                           for name, values in samples.items()}
                if expired():
                    return targets
                for name, result in results.items():
                    print(f"[TOP PICK] attempt={attempt + 1}/{maximum} {name}: {result.reason}; support={result.support}")
                    if result.target is not None:
                        col, row = expected_cells[name]
                        offset = np.hypot(result.target.col - col, result.target.row - row)
                        if offset > getattr(self.config, "VISUAL_PICK_MAX_OFFSET_CELLS", .25):
                            raise ValueError("Consensus center outside expected-cell correction limit")
                if all(result.target is not None for result in results.values()):
                    for name, result in results.items():
                        print(f"[TOP PICK] selected {name} grid=({result.target.col:.4f},{result.target.row:.4f}) "
                              f"support={result.support} valid={result.valid_count}")
                    if expired():
                        return targets
                    self.last_pick_resolution.update(failure="", reason="; ".join(r.reason for r in results.values()))
                    print(f"[TOP PICK] sampling={self.last_pick_resolution['elapsed_sec']:.3f}s")
                    if expired():
                        return targets
                    return {name: result.target for name, result in results.items()}
                self.last_pick_resolution.update(failure="consensus", reason="; ".join(
                    f"{name}: {result.reason}" for name, result in results.items()))
            except Exception as exc:
                self.last_pick_resolution.update(failure="hard", reason=str(exc))
                return targets
        return targets

    def get_robot_center_pick_targets(self, expected_cells):
        """Shared T/game resolver: selected top-rim geometry, or explicitly legacy.

        Top mode fails closed. Only when that mode is disabled does the old
        box-center/foot fallback path below remain available.
        """
        if self._top_face_enabled():
            return self._get_top_face_targets(expected_cells)
        targets = {name: None for name in expected_cells}
        if not self.center_pick_estimator or not self.cam_monitor:
            print("[CENTER PICK] Unavailable; using legacy visual-pick fallback.")
            return self.get_visual_pick_targets(expected_cells)

        samples = {name: [] for name in expected_cells}
        attempts = max(1, int(getattr(self.config, "VISUAL_CENTER_PICK_ATTEMPTS", 3)))
        for attempt in range(1, attempts + 1):
            try:
                frame, detections = self.cam_monitor.get_fresh_snapshot()
                if frame is None:
                    print(f"[CENTER PICK] Attempt {attempt}/{attempts}: no camera frame.")
                    continue
                for name, (col, row) in expected_cells.items():
                    samples[name].append(
                        self.center_pick_estimator.estimate_pick_target(detections, col, row)
                    )
            except Exception as exc:
                print(f"[CENTER PICK] Attempt {attempt}/{attempts} failed: {exc}")

        minimum = int(getattr(self.config, "VISUAL_PICK_MIN_STABLE_SAMPLES", 2))
        max_jitter = float(getattr(self.config, "VISUAL_CENTER_PICK_MAX_JITTER_CELLS", 0.12))
        for name, values in samples.items():
            targets[name] = self.center_pick_estimator.aggregate_targets(
                values, minimum, max_spread_cells=max_jitter
            )

        if all(target is not None for target in targets.values()):
            print(f"[CENTER PICK] Using stable centres from best.pt ({attempts} attempts).")
            return targets

        missing = [name for name, target in targets.items() if target is None]
        print(f"[CENTER PICK] No stable box centre after {attempts} attempts for {missing}; "
              "using legacy foot-point correction.")
        return self.get_visual_pick_targets(expected_cells)

    def execute_pick_place_test(self, source, destination, validate_request=None):
        """Run the production geometry path without AI, rules or FEN commits."""
        if validate_request:
            validate_request()
        if not self.robot or not self.robot.connected:
            raise RuntimeError("Robot chưa kết nối")
        if not self.center_pick_estimator or not self.cam_monitor:
            raise RuntimeError("Camera/visual correction chưa sẵn sàng")
        if not self.is_cell_visually_clear(destination):
            raise RuntimeError("Ô đích chưa trống hoặc camera không xác nhận được")
        target = self.get_robot_center_pick_targets({"moving": source}).get("moving")
        if target is None:
            require_pick_target(self, {"moving": None}, "moving")
        if validate_request:
            validate_request()
        print(f"[PICK TEST] logical={source} visual=({target.col:.4f},{target.row:.4f}) "
              f"destination={destination} conf={target.confidence:.3f} offset={target.offset_cells:.4f}")
        self.robot.move_piece(*source, *destination, False, moving_visual_target=target,
                              require_visual_target=True)
        if not self.verify_visual_move(source, destination):
            raise RuntimeError("Đã chạy arm nhưng chưa xác nhận được quân ở ô đích; kiểm tra bàn thật")
        if validate_request:
            validate_request()
        return target

    def _cell_has_center_detection(self, detections, cell):
        """Whether best.pt sees a confident box centre at a calibrated cell."""
        col, row = cell
        half_width = float(getattr(self.config, "VISUAL_OCCUPANCY_CELL_HALF_WIDTH", 0.5))
        return self.center_pick_estimator.has_detection_in_cell(
            detections, col, row, cell_half_width=half_width
        )

    def is_cell_visually_clear(self, cell):
        """Confirm that a capture square is clear without using CChess identity."""
        if not self.center_pick_estimator or not self.cam_monitor:
            print("[CENTER PICK] Cannot confirm cleared capture square: vision unavailable.")
            return False
        attempts = max(1, int(getattr(self.config, "VISUAL_CENTER_PICK_ATTEMPTS", 3)))
        required = int(getattr(self.config, "VISUAL_PICK_MIN_STABLE_SAMPLES", 2))
        clear_samples = 0
        for _ in range(attempts):
            try:
                frame, detections = self._occupancy_snapshot()
            except Exception as exc:
                print(f"[TOP PICK] Occupancy unavailable: {exc}")
                return False
            if frame is not None and not self._cell_has_center_detection(detections, cell):
                clear_samples += 1
        cleared = clear_samples >= required
        print(f"[CENTER PICK] Capture square {cell} clear: {clear_samples}/{attempts}.")
        return cleared

    def verify_visual_move(self, source_cell, destination_cell):
        """Verify the observed YOLO geometry after a robot move, not CChess/FEN."""
        if not self.center_pick_estimator or not self.cam_monitor:
            print("[CENTER PICK] Cannot verify completed move: vision unavailable.")
            return False
        attempts = max(1, int(getattr(self.config, "VISUAL_CENTER_PICK_ATTEMPTS", 3)))
        required = int(getattr(self.config, "VISUAL_PICK_MIN_STABLE_SAMPLES", 2))
        matching_samples = 0
        for _ in range(attempts):
            try:
                frame, detections = self._occupancy_snapshot()
            except Exception as exc:
                print(f"[TOP PICK] Move verification unavailable: {exc}")
                return False
            if frame is None:
                continue
            source_clear = not self._cell_has_center_detection(detections, source_cell)
            destination_occupied = self._cell_has_center_detection(detections, destination_cell)
            if source_clear and destination_occupied:
                matching_samples += 1
        verified = matching_samples >= required
        print(f"[CENTER PICK] Move geometry {source_cell}->{destination_cell}: "
              f"{matching_samples}/{attempts} matching snapshots.")
        return verified

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

        samples = {name: [] for name in expected_cells}
        for _ in range(max(1, int(getattr(self.config, "VISUAL_PICK_SAMPLE_COUNT", 3)))):
            try:
                frame, detections = self.cam_monitor.get_fresh_snapshot()
                if frame is None:
                    continue
                for name, (col, row) in expected_cells.items():
                    samples[name].append(self.pick_estimator.estimate_pick_target(detections, col, row))
            except Exception as e:
                print(f"[VISUAL PICK] ⚠️ Snapshot error: {e}")
        min_samples = getattr(self.config, "VISUAL_PICK_MIN_STABLE_SAMPLES", 2)
        for name, values in samples.items():
            targets[name] = self.pick_estimator.aggregate_targets(values, min_samples)
            if targets[name] is None:
                print(f"[VISUAL PICK] Fallback {name}: insufficient stable samples.")

        return targets

    def get_verified_visual_pick_targets(self, expected_board, expected_cells):
        """Verify the real board and return stable, camera-corrected pick points.

        The robot must only pick a source/capture piece after CChess confirms
        its identity against the FEN board.  Placement intentionally remains at
        the calibrated logical destination, which is handled by ``place_at``.
        """
        targets = {name: None for name in expected_cells}
        if not self.board_reconciler or not self.cam_monitor:
            print("[BOARD SYNC] CChess/visual reconciliation is unavailable.")
            return targets, False

        samples = {name: [] for name in expected_cells}
        valid_reports = 0
        sample_count = max(1, int(getattr(self.config, "VISUAL_PICK_SAMPLE_COUNT", 3)))
        for _ in range(sample_count):
            try:
                frame, detections = self.cam_monitor.get_fresh_snapshot()
                if frame is None:
                    continue
                report = self.board_reconciler.reconcile(
                    expected_board,
                    expected_cells,
                    self.recognize_board_state(frame),
                    detections,
                )
                if not report.available:
                    print(f"[BOARD SYNC] Recognition unavailable: {report.error}")
                    continue
                if not report.board_matches:
                    if report.mismatches:
                        print(f"[BOARD SYNC] FEN mismatch at {list(report.mismatches)}; robot motion blocked.")
                    else:
                        print(f"[BOARD SYNC] Unknown CChess cells at {list(report.unknown_cells)}; robot motion blocked.")
                    continue
                if not report.picks_verified:
                    failures = {name: obs.reason for name, obs in report.picks.items() if not obs.verified}
                    print(f"[BOARD SYNC] Pick verification failed: {failures}")
                    continue
                valid_reports += 1
                for name, observation in report.picks.items():
                    samples[name].append(observation.target)
            except Exception as e:
                print(f"[BOARD SYNC] Snapshot error: {e}")

        minimum = int(getattr(self.config, "VISUAL_PICK_MIN_STABLE_SAMPLES", 2))
        for name, values in samples.items():
            targets[name] = self.pick_estimator.aggregate_targets(values, minimum)

        verified = valid_reports >= minimum and all(target is not None for target in targets.values())
        if verified:
            print(f"[BOARD SYNC] ✅ {valid_reports}/{sample_count} snapshots match FEN; using physical pick offsets.")
        else:
            print("[BOARD SYNC] Robot motion blocked: board/pick state was not stable enough.")
        return targets, verified

    def verify_physical_board(self, expected_board):
        """Confirm the board after the robot has placed a piece before FEN commit."""
        if not self.board_reconciler or not self.cam_monitor:
            print("[BOARD SYNC] Post-move verification unavailable.")
            return False

        sample_count = max(1, int(getattr(self.config, "VISUAL_PICK_SAMPLE_COUNT", 3)))
        minimum = int(getattr(self.config, "VISUAL_PICK_MIN_STABLE_SAMPLES", 2))
        matches = 0
        for _ in range(sample_count):
            try:
                frame, detections = self.cam_monitor.get_fresh_snapshot()
                if frame is None:
                    continue
                report = self.board_reconciler.reconcile(
                    expected_board, {}, self.recognize_board_state(frame), detections
                )
                if report.board_matches:
                    matches += 1
                elif report.available:
                    print(f"[BOARD SYNC] Post-move mismatch at {list(report.mismatches)}.")
                else:
                    print(f"[BOARD SYNC] Post-move recognition unavailable: {report.error}")
            except Exception as e:
                print(f"[BOARD SYNC] Post-move snapshot error: {e}")

        verified = matches >= minimum
        print(
            f"[BOARD SYNC] {'✅' if verified else '❌'} Post-move FEN verification: "
            f"{matches}/{sample_count} matching snapshots."
        )
        return verified

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

    def interaction_capability(self):
        """Expose an explicit safety capability; never infer it from motion."""
        return getattr(self.config, "PLAYER_TURN_INTERACTION_CAPABILITY", "UNAVAILABLE")

    def is_board_occluded(self):
        """Optional integration point for a real hand/tool obstruction producer.

        The current camera stack has no such producer, so the safe answer is
        False only because UNIFIED is separately blocked by capability.
        """
        provider = getattr(self, "occlusion_provider", None)
        return bool(provider()) if callable(provider) else False

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
