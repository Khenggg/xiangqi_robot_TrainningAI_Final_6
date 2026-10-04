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
        self.backend = None
        self.simulation_runtime = None
        self.board_pose_provider = None
        self.twin_bridge = None
        self.telemetry = None
        self.simulation_error = None
        self._piece_move_lock = threading.Lock()
        self.engine = None
        self.ai_ctrl = None
        self.cap = None
        self.model = None
        self.cam_monitor = None
        self.yolo_detector = None
        self.cchess_recognizer = None
        self.pick_estimator = None
        self.center_pick_estimator = None
        self.board_reconciler = None
        self._difficulty_availability = {"easy": False, "medium": False, "hard": False}
        self.perspective_path = Path(project_dir) / "perspective.npy"
        
        self.class_id_to_name = {
            0: "b_A", 1: "b_C", 2: "b_R", 3: "b_E", 4: "b_K", 5: "b_N", 6: "b_P",
            8: "r_A", 9: "r_C", 10: "r_R", 11: "r_E", 12: "r_K", 13: "r_N", 14: "r_P",
        }

    def initialize_all(self):
        """Khởi tạo toàn bộ Robot, AI, Camera theo đúng thứ tự."""
        try:
            self._init_ai()
            self._init_robot()
            self._init_camera()
        except Exception:
            # The caller has not received this manager yet. Release partial
            # startup resources here, including its engine and virtual world.
            try:
                self.cleanup()
            except Exception as cleanup_error:
                print(f"[CLEANUP] Partial startup cleanup failed: {cleanup_error}")
            raise
        return self

    @property
    def is_robot_ready(self):
        if self.simulation_runtime is not None:
            return self.backend.is_connected()
        return bool(self.robot.connected and not self.dry_run
                    and getattr(self.robot, "physical_motion_authorized", False))

    def _init_robot(self):
        mode = getattr(self.config, "ROBOT_BACKEND", "VIRTUAL").upper()
        if mode == "VIRTUAL":
            from src.simulation.runtime import VirtualXiangqiSimulation
            from src.simulation.virtual_fr3_backend import VirtualFR3Backend
            from src.domain.board_pose_provider import FixedBoardPoseProvider
            from src.hardware.simulation_adapter import VirtualVisualRobot
            self.backend = VirtualFR3Backend(default_speed_factor=float(
                getattr(self.config, "SIMULATION_SPEED_FACTOR", 0.2)))
            self.simulation_runtime = VirtualXiangqiSimulation(backend=self.backend)
            self.simulation_runtime.connect()
            self.board_pose_provider = FixedBoardPoseProvider(self.simulation_runtime.placement_state)
            self.simulation_runtime.bind_board_pose_provider(self.board_pose_provider)
            self.robot = VirtualVisualRobot(self)
            print("[ROBOT] Virtual runtime ready; physical hardware untouched.")
            return
        if mode != "PHYSICAL":
            raise ValueError("ROBOT_BACKEND must be VIRTUAL or PHYSICAL")
        if self.dry_run:
            print("[ROBOT] Physical DRY_RUN: no controller connection or actuation.")
            return
        try:
            self.robot.connect()  # Read-only; no enable, home, or gripper command.
            if not self.robot.connected:
                raise RuntimeError("Physical controller connection failed")
            self._calibrate_robot()
        except Exception as exc:
            self.simulation_error = str(exc)
            print(f"[ROBOT] Physical startup unavailable: {exc}")

    def _calibrate_robot(self):
        from src.hardware.simulation_adapter import physical_board_provider, BorrowedPhysicalStateSource
        self.board_pose_provider = None
        try:
            self.board_pose_provider = physical_board_provider(self.robot, self.config)
            self.backend = BorrowedPhysicalStateSource(self.robot)
        except Exception as exc:
            self.simulation_error = str(exc)
            print(f"[TWIN] Physical mirror unavailable: {exc}")
            # Connection alone does not grant calibrated motion authorization.
            self.robot.physical_motion_authorized = False

    def setup_digital_twin(self, telemetry=None, poll_hz=25.0, start=True):
        if self.board_pose_provider is None or self.backend is None:
            return None
        from src.digital_twin.live_twin_bridge import LiveTwinBridge
        if self.twin_bridge is not None:
            return self.twin_bridge
        self.telemetry = telemetry
        virtual = self.simulation_runtime is not None
        if virtual and telemetry is not None:
            runtime = self.simulation_runtime
            runtime.telemetry = telemetry
            runtime.backend.telemetry_publisher = telemetry
            telemetry.register_command_handler(runtime._handle_client_command)
        self.twin_bridge = LiveTwinBridge(
            self.backend, self.board_pose_provider, telemetry=telemetry,
            world=self.simulation_runtime.world if virtual else None,
            physical=not virtual, owns_world=not virtual, poll_hz=poll_hz,
        )
        if virtual:
            self.simulation_runtime.bind_board_pose_provider(self.board_pose_provider, self.twin_bridge)
        if start:
            self.twin_bridge.start()
        return self.twin_bridge

    def execute_piece_move(self, *args, **kwargs):
        from src.hardware.simulation_adapter import execute_virtual_move, rejected
        from src.motion.result import MotionFailureCategory
        if not self._piece_move_lock.acquire(blocking=False):
            return rejected("Another piece move is active", MotionFailureCategory.ROBOT_BUSY)
        try:
            if self.simulation_runtime is not None:
                return execute_virtual_move(self.simulation_runtime, *args, **kwargs)
            if not self.is_robot_ready or self.board_pose_provider is None:
                return rejected("Physical control requires explicit commissioning and calibrated board parity")
            # Context IDs are mirror metadata; the visual controller owns motion.
            call_kwargs = dict(kwargs)
            for key in ("piece_id", "captured_piece_id", "move_context"):
                call_kwargs.pop(key, None)
            return self.robot.move_piece(*args, **call_kwargs)
        finally:
            self._piece_move_lock.release()

    def sync_committed_board(self, piece_cells):
        """Reconcile only a complete board already accepted by the game/camera."""
        if self.twin_bridge is None or self._piece_move_lock.locked():
            return False
        return self.twin_bridge.reconcile_to_board_cells(piece_cells)

    def close_simulation(self):
        if self.twin_bridge is not None:
            self.twin_bridge.close()
            self.twin_bridge = None
        if self.simulation_runtime is not None:
            self.simulation_runtime.stop()
            self.simulation_runtime = None

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
        self.camera_calibration_ready = False
        self.camera_calibration_source = "UNAVAILABLE"
        self.camera_startup_error = None
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
            
        from src.vision.camera_startup import open_validated_camera, validate_perspective
        self.camera_calibration_ready = False
        self.camera_calibration_source = "UNAVAILABLE"
        self.camera_startup_error = None
        try:
            cam_index = int(os.environ.get("VIDEO_INDEX", str(self.config.VIDEO_SOURCE)))
            self.cap = open_validated_camera(cam_index)
            self.camera_selected_index = cam_index
            print(f"[INIT] Camera VIDEO_INDEX={cam_index}: valid BGR frame received")
            # A cancelled/failed fresh session cannot be rescued by an old file.
            matrix = run_calibration_flow(self.cap, str(self.perspective_path),
                                          cchess_recognizer=self.cchess_recognizer)
            if not validate_perspective(matrix):
                raise RuntimeError("Fresh camera calibration failed/cancelled; saved perspective is not verified")
            if not self.perspective_path.exists():
                raise RuntimeError("Fresh camera calibration was not saved")
            saved = np.load(str(self.perspective_path), allow_pickle=False)
            if not validate_perspective(saved) or not np.allclose(saved, matrix):
                raise RuntimeError("Saved perspective does not match fresh calibration")
            self.camera_calibration_ready = True
            self.camera_calibration_source = "FRESH_STARTUP_CALIBRATION"
        except Exception as exc:
            self.camera_startup_error = str(exc)
            if self.cap is not None:
                self.cap.release()
                self.cap = None
            print(f"[INIT] Camera unavailable: {exc}")
            raise RuntimeError(f"Camera startup blocked: {exc}") from exc

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
                    # The primary robot path picks at the geometric centre of
                    # best.pt's measured box.  The existing foot-point estimator
                    # stays available as the supervised fallback.
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

    def cleanup(self):
        self.close_simulation()
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
        if (self.robot and self.robot.connected and not self.dry_run
                and getattr(self.robot, "physical_motion_authorized", False)):
            try: self.robot._set_gripper_safe_idle()
            except Exception as e: print(f"[CLEANUP] ⚠️ Không thể tắt gripper Tool DO: {e}")
            try: self.robot.robot.RobotEnable(0)
            except: pass

    # --- WRAPPER VISION UTILS ---
    def get_robot_center_pick_targets(self, expected_cells):
        """Locate robot pick points from centres of fresh ``best.pt`` boxes.

        CChess calibration owns ``perspective.npy`` (pixel -> 9x10 grid); YOLO
        measures where a physical piece actually is.  After three unsuccessful
        centre-box samples, retain the prior foot-point visual correction as a
        fallback instead of making CChess/FEN identity a motion gate.
        """
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
            frame, detections = self.cam_monitor.get_fresh_snapshot()
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
            frame, detections = self.cam_monitor.get_fresh_snapshot()
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
        """Require consecutive fresh, quality-approved complete board observations."""
        camera = getattr(self, "cam_monitor", None)
        recognizer = getattr(self, "recognize_board_state", None)
        if not getattr(self, "camera_calibration_ready", False) or camera is None or not callable(recognizer):
            print("[BOARD SYNC] Fresh calibrated camera verification unavailable.")
            return False
        cfg = getattr(self, "config", None)
        minimum = max(2, int(getattr(cfg, "VISUAL_PICK_MIN_STABLE_SAMPLES", 2)))
        samples = max(minimum, int(getattr(cfg, "VISUAL_PICK_SAMPLE_COUNT", minimum)))
        threshold = float(getattr(cfg, "CCHESS_RECOVERY_MIN_CONFIDENCE", 0.5))
        consecutive = 0
        for _ in range(samples):
            try:
                frame, _ = camera.get_fresh_snapshot()
                result = recognizer(frame) if frame is not None else None
                valid = bool(result and result.get("success"))
                observed = result.get("board") if result else None
                from src.vision.cchess_recognizer import validate_board_sanity
                sane, _ = validate_board_sanity(observed) if isinstance(observed, (list, tuple)) else (False, None)
                if result and "quality_ok" in result:
                    quality = result["quality_ok"] is True and sane
                else:
                    confidence = np.asarray(result.get("confidence", []) if result else [], dtype=float)
                    quality = (sane and confidence.shape == (10, 9) and np.isfinite(confidence).all()
                               and float(confidence.min()) >= threshold)
                exact = (isinstance(observed, (list, tuple)) and len(observed) == 10
                         and all(isinstance(row, (list, tuple)) and len(row) == 9 for row in observed)
                         and observed == expected_board)
                consecutive = consecutive + 1 if valid and quality and exact else 0
                if consecutive >= minimum:
                    return True
            except Exception as exc:
                print(f"[BOARD SYNC] Fresh verification failed: {exc}")
                consecutive = 0
        print("[BOARD SYNC] Full physical board was not confirmed by consecutive fresh frames.")
        return False

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
