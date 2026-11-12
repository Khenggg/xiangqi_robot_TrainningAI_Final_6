import os
import time
import sys
import numpy as np
import cv2
import threading
import logging
from uuid import uuid4
from src.core.project_logging import event
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

from src.vision.visual_pick_modes import VisualPickModes, PickGeometry, TopFacePickEstimator

class HardwareManager(VisualPickModes):
    """Manages Robot, Camera (Vision), and AI Engine connections."""
    def __init__(self, config, project_dir):
        self.config = config
        self.project_dir = project_dir
        self.scene_id = uuid4().hex
        from src.core.session_profile import profile_from_config
        profile = getattr(config, "SESSION_PROFILE", None)
        if profile is not None and profile.game_mode != getattr(config, "GAME_MODE", profile.game_mode):
            raise ValueError("Game mode changed without a new session profile; use controlled session startup")
        self.profile = profile if profile is not None else profile_from_config(config)
        self.dry_run = self.profile.dry_run
        fixed_points = getattr(config, "PHYSICAL_TEACHING_POINTS_FILE", None)
        fixed_points = Path(project_dir) / fixed_points if fixed_points else None
        
        # Hardware instances
        self.robot = (FR5Robot(ip=getattr(config, "ROBOT_IP", None), dry_run=self.profile.dry_run,
                              teaching_points_path=fixed_points)
                      if (self.profile.physical_robot_enabled or
                          str(getattr(config, "ROBOT_BACKEND", "VIRTUAL")).upper() == "PHYSICAL")
                      else None)
        self.backend = None
        self.simulation_runtime = None
        self.simulation_playback_profile = None
        self.board_pose_provider = None
        self.twin_bridge = None
        self.telemetry = None
        self.simulation_error = None
        self._piece_move_lock = threading.Lock()
        from src.core.motion_worker import MotionWorker
        self.motion_worker = MotionWorker()
        from src.hardware.controlled_stop import ControlledStopCoordinator
        self.stop_coordinator = ControlledStopCoordinator(self)
        self.engine = None
        self.ai_ctrl = None
        self.cap = None
        self.model = None
        self.cam_monitor = None
        self.yolo_detector = None
        self.cchess_recognizer = None
        self.pick_estimator = None
        self.top_face_pick_estimator = None
        self.actual_camera_index = None
        self.last_pick_resolution = {}
        self.center_pick_estimator = None
        self.board_reconciler = None
        self.camera_recognition_ready = False
        self._difficulty_availability = {"easy": False, "medium": False, "hard": False}
        self.perspective_path = Path(project_dir) / "perspective.npy"
        
        self.class_id_to_name = {
            0: "b_A", 1: "b_C", 2: "b_R", 3: "b_E", 4: "b_K", 5: "b_N", 6: "b_P",
            8: "r_A", 9: "r_C", 10: "r_R", 11: "r_E", 12: "r_K", 13: "r_N", 14: "r_P",
        }

    def initialize_all(self):
        """Khởi tạo toàn bộ Robot, AI, Camera theo đúng thứ tự."""
        try:
            profile = getattr(self, "profile", None)
            stages = []
            if profile is None or profile.ai_enabled:
                stages.append(("ai", self._init_ai))
            if profile is not None:
                if profile.physical_robot_enabled or profile.simulation_enabled:
                    stages.append(("robot", self._init_robot))
                if profile.camera_enabled:
                    stages.append(("camera", self._init_camera))
            elif getattr(getattr(self, "config", None), "GAME_ONLY", False) is not True:
                stages += [("robot", self._init_robot), ("camera", self._init_camera)]
            for component, initialize in stages:
                cancelled = getattr(self, "startup_cancelled", None)
                if cancelled is not None and cancelled.is_set():
                    raise RuntimeError("Startup cancelled")
                started = time.monotonic()
                event("startup.component_started", "Khởi tạo thành phần", component=component)
                initialize()
                event("startup.component_returned", "Hàm khởi tạo đã kết thúc", component=component,
                      duration_s=round(time.monotonic() - started, 3))
        except Exception:
            event("startup.failed", "Khởi tạo thất bại", level=logging.ERROR, code="STARTUP_FAILED",
                  exc_info=True, component=locals().get("component", "unknown"))
            # The caller has not received this manager yet. Release partial
            # startup resources here, including its engine and virtual world.
            try:
                self.cleanup()
                self._partial_cleanup_completed = True
            except Exception as cleanup_error:
                print(f"[CLEANUP] Partial startup cleanup failed: {cleanup_error}")
            raise
        return self

    @property
    def virtual_projection_pending(self):
        state = getattr(self, "game_state", None)
        if (self.simulation_runtime is None or state is None
                or state._projection_worker is None or state.pick_test_mode):
            return False
        journal = state._journal
        expected = (journal.session_id if journal is not None else state._local_session_id,
                    state.board_revision, self.simulation_runtime.scene_epoch)
        return getattr(self, "_virtual_board_projection", None) != expected

    @property
    def is_robot_ready(self):
        if getattr(self, "_closing", False):
            return False
        profile = getattr(self, "profile", None)
        if profile is not None and not profile.robot_moves_enabled:
            return False
        stop_coord = getattr(self, "stop_coordinator", None)
        if stop_coord is not None and stop_coord.blocked:
            return False
        if getattr(self.config, "GAME_ONLY", False) is True:
            return self.dry_run and self.config.ROBOT_BACKEND == "VIRTUAL"
        if self.simulation_runtime is not None:
            return (not self._piece_move_lock.locked() and not self.virtual_projection_pending
                    and self.backend.is_connected())
        return bool(self.robot is not None and self.robot.connected and not self.dry_run
                    and getattr(self.robot, "physical_motion_authorized", False))

    def _init_robot(self):
        profile = getattr(self, "profile", None)
        if profile is not None and not profile.physical_robot_enabled and profile.backend != "VIRTUAL":
            raise RuntimeError("Session has no physical robot capability")
        mode = str(getattr(self.config, "ROBOT_BACKEND", profile.backend if profile else "VIRTUAL")).upper()
        if mode == "VIRTUAL":
            from src.simulation.runtime import VirtualXiangqiSimulation
            from src.simulation.virtual_fr3_backend import VirtualFR3Backend
            from src.domain.board_pose_provider import FixedBoardPoseProvider
            from src.hardware.simulation_adapter import VirtualVisualRobot
            from src.core.simulation_playback import resolve_simulation_playback
            self.simulation_playback_profile = resolve_simulation_playback(self.config)
            self.backend = VirtualFR3Backend(default_speed_factor=self.simulation_playback_profile.speed_factor)
            self.simulation_runtime = VirtualXiangqiSimulation(backend=self.backend)
            self.simulation_runtime.connect()
            self.board_pose_provider = FixedBoardPoseProvider(self.simulation_runtime.placement_state)
            self.simulation_runtime.bind_board_pose_provider(self.board_pose_provider)
            self.robot = VirtualVisualRobot(self)
            event("simulation.playback_profile", "Chọn chế độ phát mô phỏng",
                  profile=self.simulation_playback_profile.to_dict(), environment="VIRTUAL")
            print("[ROBOT] Virtual runtime ready; physical hardware untouched.")
            return
        if mode != "PHYSICAL":
            raise ValueError("ROBOT_BACKEND must be VIRTUAL or PHYSICAL")
        if self.dry_run:
            print("[ROBOT] Physical DRY_RUN: no controller connection or actuation.")
            return
        if not getattr(self.config, "MOTION_PROFILE_VERIFIED", False):
            event("motion.profile_unverified",
                  "Motion profile chưa được đo trên robot hiện tại; kiểm tra SAFE_Z/ROTATION trước khi chạy",
                  level=logging.WARNING,
                  source=getattr(self.config, "MOTION_PROFILE_SOURCE", "unknown"),
                  safe_z=getattr(self.config, "SAFE_Z", None),
                  rotation=list(getattr(self.config, "ROTATION", [])),
                  move_speed=getattr(self.config, "MOVE_SPEED", None))
        try:
            self.robot.connect()  # Read-only; no enable, home, or gripper command.
            if not self.robot.connected:
                raise RuntimeError("Physical controller connection failed")
            self._calibrate_robot()
        except Exception as exc:
            self.simulation_error = str(exc)
            # The SDK receiver may recover after startup returned. Keep its
            # read-only mirror reachable; do not reconnect/enable via the UI.
            if self.robot.robot is not None:
                from src.hardware.simulation_adapter import BorrowedPhysicalStateSource
                self.backend = BorrowedPhysicalStateSource(self.robot)
                self.robot.telemetry_readiness = self.physical_telemetry_ready
            print(f"[ROBOT] Physical startup unavailable: {exc}")

    def _calibrate_robot(self):
        from src.hardware.simulation_adapter import physical_board_provider, BorrowedPhysicalStateSource
        self.board_pose_provider = None
        self.backend = BorrowedPhysicalStateSource(self.robot)
        self.robot.telemetry_readiness = self.physical_telemetry_ready
        if self.robot.teaching_points_error:
            self.simulation_error = self.robot.teaching_points_error
            print(f"[TWIN] Board mirror unavailable; raw arm telemetry retained: {self.simulation_error}")
            return
        try:
            self.board_pose_provider = physical_board_provider(self.robot, self.config)
        except Exception as exc:
            self.simulation_error = str(exc)
            print(f"[TWIN] Physical mirror unavailable: {exc}")
            # Connection alone does not grant calibrated motion authorization.
            self.robot.physical_motion_authorized = False

    def physical_telemetry_ready(self, require_idle=False):
        try:
            snapshot = self.backend.get_state_snapshot()
            measured = snapshot.measurement_timestamp
            return (snapshot.connected and snapshot.joints_valid and measured is not None
                    and 0 <= time.time() - measured <= .5
                    and snapshot.motion_state in (('IDLE', 'READY') if require_idle else ('IDLE', 'READY', 'MOVING')))
        except Exception:
            return False

    def request_controlled_stop(self, reason="Operator stop", *, workers_finished=None):
        return self.stop_coordinator.begin(reason, workers_finished)

    def refresh_stop_state(self):
        """Refresh an existing stop from telemetry without operator approval."""
        if self.stop_coordinator.request is not None:
            receipt = self.stop_coordinator.observe_idle()
            if receipt is not None:
                self.stop_coordinator.discard_idle_observation(receipt)

    def confirm_operator_controller_disabled(self, *, approved=False):
        if not approved or not self.stop_coordinator.workers_idle():
            raise RuntimeError("Finish workers and confirm pendant disable before continuing")
        request = self.stop_coordinator.request
        if request is None or not request.done.is_set() or not request.result.safe:
            raise RuntimeError("Resolve stop uncertainty before confirming controller disable")
        return self.robot.confirm_operator_disabled(approved=True)

    def setup_digital_twin(self, telemetry=None, poll_hz=25.0, start=True):
        if self.twin_bridge is not None:
            return self.twin_bridge
        if self.backend is None:
            return None
        if self.board_pose_provider is None:
            from src.digital_twin.physical_state_relay import PhysicalStateRelay
            from src.digital_twin.physical_board_display import PhysicalBoardDisplay
            from src.domain.board_pose import BoardPlacementState
            display = None
            if self.robot is not None and not self.robot.teaching_points_error:
                try:
                    display = PhysicalBoardDisplay(
                        self.robot, self.config, BoardPlacementState.compute(0).board_surface_z_m)
                except (ValueError, KeyError, TypeError) as exc:
                    event("twin.display_mapping_unavailable", str(exc), level=logging.WARNING)
            self.twin_bridge = PhysicalStateRelay(
                self.backend, telemetry, self.simulation_error, poll_hz, display_mapping=display)
            self.telemetry = telemetry
            if not self.dry_run and self.robot is not None:
                self.robot.motion_listener = self.twin_bridge.animate_command_gripper
            if start:
                self.twin_bridge.start()
            return self.twin_bridge
        from src.digital_twin.live_twin_bridge import LiveTwinBridge
        if self.twin_bridge is not None:
            return self.twin_bridge
        self.telemetry = telemetry
        virtual = self.simulation_runtime is not None
        if virtual and telemetry is not None:
            runtime = self.simulation_runtime
            if self.simulation_playback_profile is not None:
                telemetry.simulation_profile = self.simulation_playback_profile.to_dict()
            runtime.telemetry = telemetry
            runtime.backend.telemetry_publisher = telemetry
            runtime.client_command_validator = self._validate_virtual_viewer_command
            telemetry.register_command_handler(self._handle_virtual_viewer_command)
        self.twin_bridge = LiveTwinBridge(
            self.backend, self.board_pose_provider, telemetry=telemetry,
            world=self.simulation_runtime.world if virtual else None,
            physical=not virtual, owns_world=not virtual, poll_hz=poll_hz,
        )
        if virtual:
            self.simulation_runtime.bind_board_pose_provider(self.board_pose_provider, self.twin_bridge)
        elif not self.dry_run:
            self.robot.motion_listener = self.twin_bridge.animate_command_gripper
        if start:
            self.twin_bridge.start()
        event("twin.initialized", "Đã tạo bridge đồng bộ", physical=not virtual,
              placement=self.board_pose_provider.get_board_placement_state().to_dict())
        return self.twin_bridge

    def viewer_command_context(self):
        """Read committed identity without waiting behind a Game transition."""
        state = getattr(self, "game_state", None)
        if state is None or not state._transition_lock.acquire(blocking=False):
            return None
        try:
            runtime = self.simulation_runtime
            allowed = (runtime is not None and not getattr(self, "_closing", False)
                       and not self.stop_coordinator.blocked
                       and state.pending_move is None and state.pending_ai_move is None
                       and state.pending_test_motion is None and not state.ai_thinking)
            journal = state._journal
            return dict(session_id=journal.session_id if journal is not None else state._local_session_id,
                        board_revision=state.board_revision, game_epoch=state.game_epoch,
                        scene_id=self.scene_id,
                        scene_epoch=runtime.scene_epoch if runtime is not None else None,
                        placement_version=runtime.placement_state.placement_version if runtime is not None else None,
                        fen=state.current_fen, commands_allowed=allowed)
        finally:
            state._transition_lock.release()

    def _validate_virtual_viewer_command(self, command):
        supplied = command.get("command_context")
        expected = self.viewer_command_context()
        return (isinstance(supplied, dict) and expected is not None
                and expected["commands_allowed"] is True
                and all(type(supplied.get(key)) is int for key in ("board_revision", "game_epoch", "scene_epoch"))
                and supplied == expected)

    def _handle_virtual_viewer_command(self, command):
        # Own the whole command, including validation/animation, so gameplay,
        # reset and disposal observe it at the existing piece-operation barrier.
        if (getattr(self, "_closing", False) or self.simulation_runtime is None
                or not self._piece_move_lock.acquire(blocking=False)):
            if self.telemetry is not None:
                self.telemetry.broadcast_custom({"type": "error", "message": "Game/scene operation is busy; viewer command was not queued."})
            return
        try:
            self.simulation_runtime._handle_client_command(command)
        finally:
            self._piece_move_lock.release()

    def execute_piece_move(self, *args, **kwargs):
        from src.hardware.simulation_adapter import execute_virtual_move, rejected
        from src.motion.result import MotionFailureCategory, MotionExecutionResult
        if getattr(self, "_closing", False):
            return rejected("Session is closing; no new piece movement")
        profile = getattr(self, "profile", None)
        if profile is not None and not profile.robot_moves_enabled:
            return rejected("Session profile does not allow robot moves")
        stop_coord = getattr(self, "stop_coordinator", None)
        if stop_coord is not None and stop_coord.blocked:
            return rejected("RECOVERY_REQUIRED: session stop latched; no new piece move")
        if getattr(self.config, "GAME_ONLY", False) is True:
            if self.dry_run and self.config.ROBOT_BACKEND == "VIRTUAL":
                return MotionExecutionResult.ok()
            return rejected("Game-only mode cannot command physical hardware")
        if not self._piece_move_lock.acquire(blocking=False):
            return rejected("Another piece move is active", MotionFailureCategory.ROBOT_BUSY)
        try:
            if stop_coord is not None and stop_coord.blocked:
                return rejected("RECOVERY_REQUIRED: session stop requested before dispatch")
            if self.simulation_runtime is not None:
                if self.virtual_projection_pending:
                    return rejected("Virtual game board projection is pending; wait for synchronization before dispatch")
                self._record_game_dispatch(kwargs)
                state = getattr(self, "game_state", None)
                context = kwargs.get("move_context")
                expected = kwargs.get("expected_execution_binding")
                def guard():
                    if state is not None and context is state.pending_move:
                        state.assert_execution_binding(context)
                    elif state is not None and state.pending_test_motion is not None:
                        state.assert_test_execution_binding(context)
                    elif expected is not None and expected != self.capture_execution_binding():
                        raise RuntimeError("Test scene/calibration changed before virtual motion")
                return execute_virtual_move(self.simulation_runtime, *args, validity_guard=guard, **kwargs)
            if not self.is_robot_ready:
                return rejected("Physical control requires explicit operator enable")
            if not self.physical_telemetry_ready():
                return rejected("Robot telemetry stale/faulted; no new command dispatched")
            visual_required = any(bool(getattr(self.config, key, False)) for key in
                                  ("VISUAL_PICK_ENABLED", "VISUAL_HEIGHT_PICK_ENABLED",
                                   "VISUAL_TOP_FACE_ENABLED", "VISUAL_RING_PICK_ENABLED"))
            if visual_required:
                from src.vision.pick_consensus import require_pick_target
                capture = kwargs.get("is_capture", args[4] if len(args) > 4 else False)
                name = "captured" if capture else "moving"
                index = 6 if capture else 5
                target = kwargs.get(f"{name}_visual_target", args[index] if len(args) > index else None)
                try:
                    require_pick_target(self, {name: target}, name)
                    if capture and (not callable(kwargs.get("refresh_moving_visual_target"))
                                    or not callable(kwargs.get("verify_capture_cleared"))):
                        raise ValueError("Visual capture requires refresh and verified removal callbacks")
                except Exception as exc:
                    return rejected(str(exc), MotionFailureCategory.TARGET_INVALID)
            # The semantic context binds this command; the visual controller owns motion.
            self._record_game_dispatch(kwargs)
            call_kwargs = dict(kwargs)
            expected_binding = call_kwargs.pop("expected_execution_binding", None)
            for key in ("piece_id", "captured_piece_id", "move_context"):
                call_kwargs.pop(key, None)
            bridge = self.twin_bridge
            context = kwargs.get('move_context')
            state = getattr(self, "game_state", None)
            previous_guard = getattr(self.robot, "dispatch_validity", None)
            previous_trace = getattr(self.robot, "motion_trace", {})
            binding = state.pending_execution_binding if state is not None and context is state.pending_move else None
            if (binding is None and state is not None and state.pending_test_motion is not None
                    and state.pending_test_motion["context"] == context):
                binding = state.pending_test_motion["binding"]
            self.robot.motion_trace = dict(move_id=getattr(context, "move_id", None),
                session_id=binding.get("session_id") if binding else None,
                board_revision=binding.get("board_revision") if binding else None,
                calibration_version=(binding.get("authority") or {}).get("calibration_version") if binding else None)
            if state is not None and context is state.pending_move:
                self.robot.dispatch_validity = lambda: state.assert_execution_binding(context)
            elif expected_binding is not None:
                def guard():
                    if state is not None and state.pending_test_motion is not None:
                        state.assert_test_execution_binding(context)
                    if expected_binding != self.capture_execution_binding():
                        raise RuntimeError("Test calibration/command coordinates changed; no stale stage")
                self.robot.dispatch_validity = guard
            if context is not None and callable(getattr(bridge, 'begin_command_animation', None)):
                try:
                    bridge.begin_command_animation(context)
                except Exception as exc:
                    event('twin.animation_failed', str(exc), level=logging.WARNING)
            try:
                if getattr(self.robot, "dispatch_validity", None) is not None:
                    self.robot.dispatch_validity()
                return self.robot.move_piece(*args, **call_kwargs)
            finally:
                self.robot.dispatch_validity = previous_guard
                self.robot.motion_trace = previous_trace
                if callable(getattr(bridge, 'finish_command_animation', None)):
                    try:
                        bridge.finish_command_animation()
                    except Exception as exc:
                        event('twin.animation_failed', str(exc), level=logging.WARNING)
        finally:
            self._piece_move_lock.release()

    def _record_game_dispatch(self, kwargs):
        state = getattr(self, "game_state", None)
        context = kwargs.get("move_context")
        if state is not None and not state.pick_test_mode:
            from src.domain.game_move import MoveActor
            if context is None or context.actor is not MoveActor.ROBOT or context is not state.pending_move:
                raise RuntimeError("Game command requires its current semantic move; no dispatch")
        if state is not None and context is not None and context is state.pending_move:
            stage = "capture_removed" if state.visual_capture_checkpoint else "pre_pick"
            state.record_motion_dispatch(context, stage)
        elif state is not None and state.pick_test_mode:
            state.record_test_dispatch(context)

    def capture_execution_binding(self):
        from src.core.execution_binding import capture_execution_binding
        return capture_execution_binding(self)

    def sync_committed_board(self, piece_cells):
        """Reconcile only a complete board already accepted by the game/camera."""
        if (not callable(getattr(self.twin_bridge, 'reconcile_to_board_cells', None))
                or not self._piece_move_lock.acquire(blocking=False)):
            return False
        state_lock = None
        try:
            state = getattr(self, "game_state", None)
            if state is not None and any(
                    getattr(state, name, None) is not None
                    for name in ("pending_move", "pending_ai_move", "pending_test_motion")):
                # The virtual/full-board projection must never reconcile an
                # older board while a semantic move is waiting for its commit.
                return False
            if state is not None:
                if not state._transition_lock.acquire(blocking=False):
                    return False
                state_lock = state._transition_lock
            context = self.viewer_command_context() if state is not None else None
            if context is not None:
                context = {key: value for key, value in context.items() if key != "commands_allowed"}
                context["baseline_kind"] = "MANUAL_TEST" if state.pick_test_resume_required else "COMMITTED_GAME"
            synchronized = self.twin_bridge.reconcile_to_board_cells(
                piece_cells, blocking=False, projection_context=context)
            if (synchronized and self.simulation_runtime is not None and state is not None
                    and not state.pick_test_mode and piece_cells == state.piece_ids):
                journal = state._journal
                self._virtual_board_projection = (
                    journal.session_id if journal is not None else state._local_session_id,
                    state.board_revision, self.simulation_runtime.scene_epoch)
            return synchronized
        finally:
            if state_lock is not None:
                state_lock.release()
            self._piece_move_lock.release()

    def physical_recovery_block_reason(self):
        """Read-only explanation; never clear faults or authorize movement."""
        if self.dry_run or self.simulation_runtime is not None:
            return None
        try:
            snapshot = self.backend.get_state_snapshot()
        except Exception as exc:
            return f"Could not read robot state: {exc}"
        measured = snapshot.measurement_timestamp
        if (not snapshot.connected or not snapshot.joints_valid or measured is None
                or not 0 <= time.time()-measured <= .5):
            return "Robot telemetry is disconnected or stale; arm state could not be verified."
        if snapshot.motion_state == "ERROR" or snapshot.last_error:
            return (f"Robot error: {snapshot.last_error or snapshot.motion_state}. "
                    "Clear the alarm on the WebApp/pendant; V/FEN does not clear a controller fault.")
        if snapshot.motion_state not in {"IDLE", "READY"}:
            return f"Robot is not in the stopped state: {snapshot.motion_state}."
        return None

    def activate_physical_game(self, state, *, commissioned=False,
                               expected_stop_generation=None, startup_guard=None):
        """Enable after explicit manual or configured startup authorization."""
        if startup_guard is not None:
            startup_guard()
        if getattr(self, "_closing", False):
            raise RuntimeError("Session is closing; create a new session before enabling")
        controls = getattr(self, "session_control", None)
        if controls is not None and controls.action in {"home", "quit", "reset"}:
            raise RuntimeError("Finish the requested session action before enabling")
        stop_coord = getattr(self, "stop_coordinator", None)
        stop_generation = stop_coord.generation if stop_coord is not None else 0
        if expected_stop_generation is not None and (
                stop_coord is None or stop_generation != expected_stop_generation or stop_coord.blocked):
            raise RuntimeError("Automatic enable cancelled by a stop request")
        profile = getattr(self, "profile", None)
        if profile is not None and not profile.physical_robot_enabled:
            raise RuntimeError("This game mode/environment has no physical robot capability")
        if (not commissioned or self.dry_run or self.config.ROBOT_BACKEND != "PHYSICAL"
                or not self.robot.connected):
            raise RuntimeError("Physical connection and explicit operator enable required")
        reason_reader = getattr(self, "physical_recovery_block_reason", None)
        reason = reason_reader() if callable(reason_reader) else None
        if reason:
            raise RuntimeError(reason)
        if (state.ai_thinking or state.pending_move is not None or state.physical_sync_fault
                or state.pending_test_motion is not None
                or state.recovery_required or state.mode_change_pending or state.move_sync_error or self._piece_move_lock.locked()):
            raise RuntimeError("Resolve pending motion or board synchronization first")
        if isinstance(getattr(self.robot, "teaching_points_error", None), str) and self.robot.teaching_points_error:
            # Operator may have selected the required WObj after a blocked
            # startup. Refresh read-only metadata on this explicit F9/F10 retry,
            # before checking fresh telemetry/camera/stop generation again.
            try:
                self.robot._load_teaching_points()
            except Exception as exc:
                self.robot.teaching_points = {}
                self.robot.teaching_points_error = f"R1-R4 calibration unavailable: {exc}"
                raise RuntimeError(self.robot.teaching_points_error) from exc
        telemetry_ready_fn = getattr(self, "physical_telemetry_ready", None)
        if callable(telemetry_ready_fn):
            idle_ready = telemetry_ready_fn(require_idle=True)
        else:
            twin = getattr(self, "twin_bridge", None)
            idle_ready = bool(callable(getattr(twin, "_board_observation_ready", None)) and twin._board_observation_ready())
        if not idle_ready:
            raise RuntimeError("Fresh idle robot telemetry required")
        if not self.verify_physical_board(state.board):
            raise RuntimeError("Camera must confirm the current complete board")
        # Viewer alignment/projection is optional; FR3/camera remain authoritative.
        state.sync_current_board()
        stopped = stop_coord.blocked if stop_coord is not None else False
        # A stop that already finished is no longer a pause: the robot may be
        # re-enabled without a manual recovery confirmation. Only a stop that is
        # still running keeps the latch and has to be verified first.
        last_stop = getattr(stop_coord, "request", None) if stop_coord is not None else None
        stop_finished = last_stop is not None and last_stop.done.is_set()
        if stopped:
            request = stop_coord.request
            if (not request.done.is_set() or not request.result.safe
                or not stop_coord.safe_for_release(ignore_current_worker=True)):
                raise RuntimeError("RECOVERY_REQUIRED: verify stopped robot before enabling")
        if stop_coord is not None and stop_generation != stop_coord.generation:
            raise RuntimeError("Enable cancelled by a newer stop request")
        if startup_guard is not None:
            startup_guard()
        if expected_stop_generation is not None and (
                stop_coord.generation != expected_stop_generation or stop_coord.blocked):
            raise RuntimeError("Automatic enable cancelled by a stop request")
        if stop_coord is not None:
            enabled = self.robot.activate_physical_control(
                commissioned=True, stop_recovered=(stopped or stop_finished))
        else:
            enabled = self.robot.activate_physical_control(commissioned=True)
        try:
            if stop_coord is not None and stop_generation != stop_coord.generation:
                raise RuntimeError("Enable cancelled by a newer stop request")
            if (stopped or stop_finished) and stop_coord is not None:
                if stopped:
                    stop_coord.clear_after_recovery(ignore_current_worker=True,
                                                    expected_generation=stop_generation)
                else:
                    stop_coord.clear_after_recovery(ignore_current_worker=True, force=True)
                    if not (last_stop.done.is_set() and last_stop.result.safe):
                        event("motion.stop_unverified_released",
                              "Re-enabled after a stop without confirmation; recovery no longer blocks play",
                              level=logging.WARNING, reason=getattr(last_stop, "reason", None))
        except Exception:
            self.robot.latch_motion_stop()
            raise
        event("physical.enabled", "Người vận hành đã bật quyền chuyển động qua game", commissioned=True)
        return enabled

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
                return "IMPOSSIBLE selected — original Moonfish is in use."
            return (f"Selected {difficulty.upper()} — Moonfish depth {profile.get('depth')}, "
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

    def _prepare_perspective_calibration(self, cam_index):
        """Use a saved matrix unless recalibration was explicitly requested."""
        from src.vision.camera_startup import (
            load_saved_perspective, perspective_sha256, validate_perspective,
        )
        saved_path = self.perspective_path
        self.camera_calibration_ready = False
        self.camera_calibration_source = "UNAVAILABLE"
        recalibrate = bool(getattr(self.config, "RECALIBRATE_CAMERA", False))
        saved, error = load_saved_perspective(saved_path)
        if saved is not None and not recalibrate:
            self.camera_calibration_ready = True
            self.camera_calibration_source = "SAVED_CALIBRATION"
            event("camera.calibration_loaded", "Dùng calibration camera đã lưu",
                  path=str(saved_path), sha256=perspective_sha256(saved_path),
                  camera_index=cam_index, recalibrate=False)
            return
        if saved_path.exists() and saved is None and not recalibrate:
            raise RuntimeError(
                f"Saved perspective.npy cannot be used ({error}); "
                "run with --recalibrate-camera while seated at the machine")
        matrix = run_calibration_flow(
            self.cap, str(saved_path), cchess_recognizer=getattr(self, "cchess_recognizer", None),
            cancel_event=getattr(self, "startup_cancelled", None), capture_owner=self,
            manual_only=bool(getattr(self.config, "CAMERA_CALIBRATION_MANUAL_ONLY", False)))
        if not validate_perspective(matrix):
            raise RuntimeError("Fresh camera calibration failed/cancelled; saved perspective is not verified")
        if not saved_path.exists():
            raise RuntimeError("Fresh camera calibration was not saved")
        saved, error = load_saved_perspective(saved_path)
        if saved is None or not np.allclose(saved, matrix):
            raise RuntimeError(
                f"Saved perspective does not match fresh calibration ({error or 'mismatch'})")
        self.camera_calibration_ready = True
        self.camera_calibration_source = "FRESH_CALIBRATION"
        event("camera.calibration_created", "Đã tạo calibration camera mới",
              path=str(saved_path), sha256=perspective_sha256(saved_path),
              camera_index=cam_index, recalibrate=recalibrate)

    def _init_camera(self):
        self.camera_calibration_ready = False
        self.camera_calibration_source = "UNAVAILABLE"
        self.camera_recognition_ready = False
        self.camera_startup_error = None
        profile = getattr(self, "profile", None)
        if self.dry_run or (profile is not None and not profile.camera_enabled):
            return
        # Initialize CChessRecognizer (ONNX)
        if getattr(self.config, "CCHESS_RECOGNITION_ENABLED", True):
            try:
                from src.vision.cchess_recognizer import CChessRecognizer
                pose_onnx = Path(self.project_dir) / "models" / "cchess" / "pose_4_v6.onnx"
                layout_onnx = Path(self.project_dir) / "models" / "cchess" / "layout_nano_v3.onnx"
                if pose_onnx.exists() and layout_onnx.exists():
                    self.cchess_recognizer = CChessRecognizer(
                        pose_onnx, layout_onnx,
                        use_gpu=getattr(self.config, "VISION_DEVICE", "auto") != "cpu")
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
            
        from src.vision.camera_startup import open_validated_camera
        self.camera_calibration_ready = False
        self.camera_calibration_source = "UNAVAILABLE"
        self.camera_startup_error = None
        try:
            cancelled = getattr(self, "startup_cancelled", None)
            if cancelled is not None and cancelled.is_set():
                raise RuntimeError("Startup cancelled")
            requested_index = int(os.environ.get("VIDEO_INDEX", str(self.config.VIDEO_SOURCE)))
            candidates = [requested_index] + [index for index in range(3) if index != requested_index]
            errors = []
            for cam_index in candidates:
                if cancelled is not None and cancelled.is_set():
                    raise RuntimeError("Startup cancelled")
                try:
                    self.cap = open_validated_camera(cam_index)
                except RuntimeError as exc:
                    errors.append(f"index {cam_index}: {exc}")
                    print(f"[CAMERA] {errors[-1]}")
                    continue
                break
            else:
                raise RuntimeError("Cannot read any camera; " + "; ".join(errors))
            self.camera_selected_index = cam_index
            self.actual_camera_index = cam_index
            if cam_index != requested_index:
                print(f"[CAMERA] Requested {requested_index}; using {cam_index}. "
                      "Check board calibration for this camera before enabling motion.")
            print(f"[INIT] Camera VIDEO_INDEX={cam_index}: valid BGR frame received")
            self._prepare_perspective_calibration(cam_index)
        except Exception as exc:
            self.camera_startup_error = str(exc)
            calibration_reader = getattr(self, "_calibration_capture_thread", None)
            if self.cap is not None and (calibration_reader is None or not calibration_reader.is_alive()):
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
                device_preference=getattr(self.config, "VISION_DEVICE", "auto"),
            )
            dist_thresh = getattr(self.config, "SNAPSHOT_MAX_DIST_THRESHOLD", 0.45)
            foot_ratio = getattr(self.config, "SNAPSHOT_FOOT_RATIO", 0.50)
            self.yolo_detector = YoloSnapshotDetector(
                self.perspective_path, self.class_id_to_name,
                max_dist_threshold=dist_thresh,
                foot_ratio=foot_ratio,
            )
            print(f"[INIT] SnapshotDetector initialized (dist_thresh={dist_thresh}, foot_ratio={foot_ratio}).")
            if (getattr(self.config, "VISUAL_PICK_ENABLED", False)
                    or getattr(self.config, "VISUAL_RING_PICK_ENABLED", False)
                    or getattr(self.config, "VISUAL_HEIGHT_PICK_ENABLED", False)
                    or getattr(self.config, "VISUAL_TOP_FACE_ENABLED", False)
                    or getattr(self.config, "VISUAL_BOARD_SYNC_REQUIRED", True)):
                try:
                    board_mm = getattr(self.config, "VISUAL_HEIGHT_BOARD_MM", None)
                    if board_mm is None:
                        w_mm = getattr(self.config, "VISUAL_BOARD_WIDTH_MM", None) or getattr(self.config, "BOARD_WIDTH_MM", 320.0)
                        h_mm = getattr(self.config, "VISUAL_BOARD_HEIGHT_MM", None) or getattr(self.config, "BOARD_LENGTH_MM", 360.0)
                        board_mm = (float(w_mm), float(h_mm))
                    self.pick_estimator = VisualPickEstimator(
                        self.perspective_path,
                        min_confidence=self.config.VISUAL_PICK_MIN_CONFIDENCE,
                        max_offset_cells=self.config.VISUAL_PICK_MAX_OFFSET_CELLS,
                        foot_ratio=self.config.VISUAL_PICK_FOOT_RATIO,
                        board_mm=board_mm,
                        max_offset_mm=getattr(self.config, "VISUAL_PICK_MAX_OFFSET_MM", 6.0),
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
                        cell_half_width=0.45,
                        board_mm=board_mm,
                        outside_margin_mm=getattr(self.config, "VISUAL_PICK_OUTSIDE_MARGIN_MM", 0.0),
                        max_offset_mm=getattr(self.config, "VISUAL_PICK_MAX_OFFSET_MM", 6.0),
                    )
                    self.board_reconciler = BoardReconciler(self.pick_estimator)
                    print("[INIT] ✅ Visual pick / board reconciliation initialized.")
                except Exception as e:
                    print(f"[INIT] ⚠️ Visual pick disabled: cannot initialize estimator: {e}")

            if self._top_face_enabled():
                try:
                    geometry = PickGeometry.load(Path(self.project_dir) / self.config.VISUAL_PICK_GEOMETRY_PATH)
                    frame, _ = self.cam_monitor.get_fresh_pick_snapshot()
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
                        min_white_value=self.config.VISUAL_TOP_MIN_WHITE_VALUE,
                        max_offset_mm=getattr(self.config, "VISUAL_PICK_MAX_OFFSET_MM", 6.0))
                    print(f"[TOP PICK] Calibrated profile {geometry.profile_id} loaded.")
                except Exception as exc:
                    self.top_face_pick_estimator = None
                    print(f"[TOP PICK] BLOCKED: {exc}. Run scripts/windows/CALIBRATE_PICK_GEOMETRY.bat with RUN closed.")

            # Start exactly once, after startup calibration/profile reads.
            # The constructor only creates caches; without this there is no
            # continuous capture/inference and snapshots immediately age out.
            self.cam_monitor.start()

        missing = []
        if self.cchess_recognizer is None:
            missing.append("CChess ONNX layout recognizer")
        if self.model is None:
            missing.append("YOLO best.pt model")
        if self.yolo_detector is None:
            missing.append("YOLO snapshot detector")
        if self.cam_monitor is None:
            missing.append("CameraMonitor")
        if missing:
            message = (
                "Physical camera recognition unavailable: " + ", ".join(missing)
                + ". Physical board verification requires BOTH models and a running camera monitor."
            )
            self.camera_startup_error = message
            event("camera.recognition_unavailable", message, level=logging.ERROR,
                  code="STARTUP_FAILED", missing=missing,
                  camera_index=getattr(self, "actual_camera_index", None))
            if self.cam_monitor is not None:
                try:
                    self.cam_monitor.stop()
                    self.cam_monitor = None
                except Exception as exc:
                    event("camera.stop_failed", str(exc), level=logging.WARNING)
            if self.cam_monitor is None and self.cap is not None:
                try:
                    self.cap.release()
                finally:
                    self.cap = None
            self.yolo_detector = None
            raise RuntimeError(message)
        self.camera_recognition_ready = True
        event("camera.recognition_ready", "Camera recognition ready for physical play",
              camera_index=getattr(self, "actual_camera_index", None),
              calibration_source=self.camera_calibration_source)

    def cleanup(self):
        self._closing = True
        calibration_stop = getattr(self, "_calibration_capture_stop", None)
        calibration_reader = getattr(self, "_calibration_capture_thread", None)
        if calibration_stop is not None:
            calibration_stop.set()
        if calibration_reader is not None:
            calibration_reader.join(timeout=1.0)
            if calibration_reader.is_alive():
                raise RuntimeError("Camera calibration reader still running; resources retained until it exits")
            self._calibration_capture_thread = self._calibration_capture_stop = None
        stop_coord = getattr(self, "stop_coordinator", None)
        stop = stop_coord.request if stop_coord is not None else None
        robot = getattr(self, "robot", None)
        owned = (getattr(robot, "physical_motion_authorized", False) is True
                 or getattr(robot, "_activation_owned", False) is True)
        state = getattr(self, "game_state", None)
        unresolved = state is not None and (state.pending_move is not None
                    or state.pending_ai_move is not None or state.pending_test_motion is not None
                    or state.pick_test_resume_required)
        motion_worker = getattr(self, "motion_worker", None)
        piece_lock = getattr(self, "_piece_move_lock", None)
        motion_active = (unresolved
                         or (motion_worker is not None and motion_worker.running)
                         or (piece_lock is not None and piece_lock.locked())
                         or getattr(robot, "_gripper_pulse_active", False) is True)
        if stop is None and stop_coord is not None and (motion_active or (owned and self.backend is not None)):
            stop = self.request_controlled_stop("Hardware cleanup")
            stop.done.wait(7.0)
        if (not getattr(self, "_cleanup_stop_proved", False)
                and stop is not None and stop_coord is not None and not stop_coord.safe_for_release()):
            raise RuntimeError("RECOVERY_REQUIRED: hardware retained until stop is verified")
        self._cleanup_stop_proved = True
        closed_steps = getattr(self, "_cleanup_closed_steps", None)
        if closed_steps is None:
            closed_steps = self._cleanup_closed_steps = set()
        failures = []
        def close(name, operation):
            if name in closed_steps:
                return True
            try:
                operation()
                closed_steps.add(name)
                return True
            except Exception as exc:
                failures.append(f"{name}: {exc}")
                event('cleanup.failed', f"{name}: {exc}", level=logging.ERROR)
                return False
        worker = getattr(self, 'motion_worker', None)
        motion_stopped = worker is None or close('motion worker', worker.close)
        if motion_stopped:
            pvp = getattr(self, 'pvp_controller', None)
            if pvp is not None:
                close('two-player room', pvp.close)
            mirror_stopped = close('mirror', self.close_simulation)
            camera = getattr(self, 'cam_monitor', None)
            camera_stopped = camera is None or close('camera', camera.stop)
            cap = getattr(self, 'cap', None)
            if camera_stopped and cap is not None:
                close('camera capture', cap.release)
            robot = getattr(self, 'robot', None)
            if mirror_stopped and robot is not None and not getattr(self, 'dry_run', True):
                if (getattr(robot, 'physical_motion_authorized', False) is True
                        or getattr(robot, '_activation_owned', False) is True):
                    if not close('gripper idle', robot._set_gripper_safe_idle):
                        raise RuntimeError('; '.join(failures))
                    if not close('disable owned control', robot.deactivate_physical_control):
                        raise RuntimeError('; '.join(failures))
                rpc = getattr(robot, 'robot', None)
                if callable(getattr(rpc, 'CloseRPC', None)):
                    close('controller connection', rpc.CloseRPC)
                robot.connected = False
        controller = getattr(self, 'ai_ctrl', None)
        for engine in (getattr(controller, 'local_engine', None), getattr(controller, 'cloud_engine', None),
                       getattr(self, 'engine', None)):
            if engine is not None:
                close(f'engine:{id(engine)}', engine.stop)
        if failures:
            raise RuntimeError('; '.join(failures))

    # --- WRAPPER VISION UTILS ---
    def get_robot_center_pick_targets(self, expected_cells):
        """Locate robot pick points from centres of fresh ``best.pt`` boxes.

        CChess calibration owns ``perspective.npy`` (pixel -> 9x10 grid); YOLO
        measures where a physical piece actually is. Robot picks require a
        stable box centre; never silently substitute a lower foot point.
        """
        from src.vision.ring_pick_estimator import ring_pick_enabled, current_pick_enabled, resolve_ring_pick_targets
        from src.vision.pick_consensus import require_pick_target
        if ring_pick_enabled(self.config):
            targets = resolve_ring_pick_targets(self, expected_cells)
        elif not current_pick_enabled(self.config):
            raise RuntimeError("All picking modes disabled")
        elif self._top_face_enabled():
            targets = self._get_top_face_targets(expected_cells)
        elif getattr(self.config, "VISUAL_HEIGHT_PICK_ENABLED", False):
            targets = self._get_height_pick_targets(expected_cells)
        else:
            targets = None
        def _target_details(values):
            return {name: dict(col=t.col, row=t.row, offset_cells=t.offset_cells,
                               confidence=t.confidence)
                    for name, t in values.items() if t is not None}

        if targets is not None:
            try:
                for name in expected_cells:
                    require_pick_target(self, targets, name)
            except Exception:
                reason = (self.last_pick_resolution or {}).get("reason", "")
                event("vision.pick_failed", f"Không có tâm quân ổn định ({reason})",
                      level=logging.WARNING, mode="camera_geometry", cells=expected_cells,
                      resolution=self.last_pick_resolution)
                raise
            event("vision.pick_resolved",
                  "Đã đo tâm quân: " + ", ".join(
                      f"{name}=({t.col:.3f},{t.row:.3f})" for name, t in targets.items() if t is not None),
                  mode="camera_geometry", cells=expected_cells,
                  resolution=self.last_pick_resolution, targets=_target_details(targets))
            return targets
        targets = {name: None for name in expected_cells}
        if not self.center_pick_estimator or not self.cam_monitor:
            raise RuntimeError("Center pick unavailable: camera/centre estimator not ready")

        samples = {name: [] for name in expected_cells}
        attempts_detail = []
        attempts = max(1, int(getattr(self.config, "VISUAL_CENTER_PICK_ATTEMPTS", 3)))
        max_offset_mm = getattr(self.config, "VISUAL_PICK_MAX_OFFSET_MM", None)
        for attempt in range(1, attempts + 1):
            try:
                frame, detections = self._occupancy_snapshot()
                if frame is None:
                    print(f"[CENTER PICK] Attempt {attempt}/{attempts}: no camera frame.")
                    detail = dict(attempt=attempt, accepted=False, reason="no_camera_frame")
                    attempts_detail.append(detail)
                    event("vision.pick_attempt",
                          f"Đo tâm quân lần {attempt}: không có ảnh camera",
                          level=logging.DEBUG, **detail)
                    continue
                for name, (col, row) in expected_cells.items():
                    target = self.center_pick_estimator.estimate_pick_target(detections, col, row)
                    samples[name].append(target)
                    detail = dict(
                        attempt=attempt, cell=[col, row], accepted=target is not None,
                        reason=getattr(self.center_pick_estimator, "last_reason", ""),
                        measurement=getattr(self.center_pick_estimator, "last_measurement", {}),
                    )
                    if target is not None:
                        detail.update(col=target.col, row=target.row,
                                      offset_cells=target.offset_cells,
                                      confidence=target.confidence)
                        message = (f"Piece-center measurement ({col}) attempt {row}) lần {attempt}: "
                                   f"col={target.col:.3f}, row={target.row:.3f}, "
                                   f" square{target.offset_cells:.3f} ô")
                    else:
                        message = (f"Piece-center measurement ({col}) attempt {row}) lần {attempt}: "
                                   f"not reached ({detail['reason']})")
                    attempts_detail.append(detail)
                    event("vision.pick_attempt", message, level=logging.DEBUG, **detail)
            except Exception as exc:
                print(f"[CENTER PICK] Attempt {attempt}/{attempts} failed: {exc}")
                detail = dict(attempt=attempt, accepted=False, reason=str(exc))
                attempts_detail.append(detail)
                event("vision.pick_attempt", f"Đo tâm quân lần {attempt} lỗi: {exc}",
                      level=logging.DEBUG, **detail)

        minimum = int(getattr(self.config, "VISUAL_PICK_MIN_STABLE_SAMPLES", 2))
        max_jitter = float(getattr(self.config, "VISUAL_CENTER_PICK_MAX_JITTER_CELLS", 0.12))
        spreads = {}
        for name, values in samples.items():
            valid = [target for target in values if target is not None]
            if valid:
                median_col = float(np.median([target.col for target in valid]))
                median_row = float(np.median([target.row for target in valid]))
                spreads[name] = max(
                    float(np.hypot(target.col - median_col, target.row - median_row))
                    for target in valid
                )
            else:
                spreads[name] = None
            targets[name] = self.center_pick_estimator.aggregate_targets(
                values, minimum, max_spread_cells=max_jitter
            )

        resolution = dict(
            mode="center", attempts=attempts, attempts_detail=attempts_detail,
            valid_samples={name: sum(target is not None for target in values)
                           for name, values in samples.items()},
            spread_cells=spreads, jitter_limit_cells=max_jitter,
            max_offset_mm=max_offset_mm,
        )
        if all(target is not None for target in targets.values()):
            resolution.update(failure="", reason="Strict center consensus",
                              targets=_target_details(targets))
            self.last_pick_resolution = resolution
            print(f"[CENTER PICK] Using stable centres from best.pt ({attempts} attempts).")
            event("vision.pick_resolved",
                  "Đã đo tâm quân: " + ", ".join(
                      f"{name}=({t.col:.3f},{t.row:.3f})" for name, t in targets.items() if t is not None),
                  mode="center", cells=expected_cells,
                  resolution=resolution, targets=resolution["targets"])
            return targets

        missing = [name for name, target in targets.items() if target is None]
        from src.vision.pick_consensus import PickTargetUnavailable
        resolution.update(failure="consensus", reason=f"No stable center for {missing}",
                          missing=missing)
        self.last_pick_resolution = resolution
        summary = ", ".join(
            f"{name}: valid={resolution['valid_samples'][name]}, "
            f"spread={spreads[name] if spreads[name] is not None else 'n/a'}"
            for name in missing
        )
        limit = max_offset_mm if max_offset_mm is not None else "n/a"
        from src.vision.board_diagnostics import pick_cells_description
        board = getattr(getattr(self, 'game_state', None), 'board', None)
        named_targets = pick_cells_description({name: expected_cells[name] for name in missing}, board)
        event("vision.pick_failed",
              f"{named_targets}. Không có tâm quân ổn định ({summary}); giới hạn lệch {limit} mm, "
              f"dao động {max_jitter} ô",
              level=logging.WARNING, mode="center", cells=expected_cells, resolution=resolution)
        raise PickTargetUnavailable(
            f"No stable box centre after {attempts} attempts for {missing}; robot pick blocked",
            resolution=resolution)

    def execute_hover_test(self, source):
        """Approach only, through current placement and collision authority; no grip/commit."""
        if getattr(self, "_closing", False):
            raise RuntimeError("Session is closing; hover is unavailable")
        if self.profile is not None and not self.profile.robot_moves_enabled:
            raise RuntimeError("Robot tests are unavailable in this session profile")
        if not self._piece_move_lock.acquire(blocking=False):
            raise RuntimeError("Another robot operation is active")
        try:
            if self.simulation_runtime is not None:
                from src.simulation.runtime import RuntimeOperationState
                from src.motion.resolver import MotionResolver
                from src.motion.plan import BoardPickIntent
                from src.motion.coordinator import MotionProfile
                from src.motion.contracts import MotionType
                runtime = self.simulation_runtime
                if not self.backend.collision_guard_enabled or self.backend.collision_guard is None:
                    raise RuntimeError("Hover requires collision guard")
                with runtime.acquire_operation_state(RuntimeOperationState.MOTION):
                    runtime._board_adjustment_ready = False
                    placement = self.board_pose_provider.get_board_placement_state()
                    profile = MotionProfile(safe_clearance_above_board_mm=placement.safe_transit_height_mm)
                    plan = MotionResolver(self.board_pose_provider, profile,
                                          runtime.target_tool_euler_deg).resolve_pick(BoardPickIntent(source[1], source[0]))
                    step = next(step for step in plan.steps if step.motion_type in
                                (MotionType.CARTESIAN_LINEAR, MotionType.CARTESIAN_POINT))
                    if not self.backend.move_cartesian(step.waypoint.pose_mm_deg):
                        raise RuntimeError(f"Hover rejected: {self.backend._last_error}")
                    return tuple(step.waypoint.pose_mm_deg)
            if not self.is_robot_ready:
                raise RuntimeError("Physical hover requires explicit operator enable")
            expected_binding = self.capture_execution_binding()
            from src.vision.pick_consensus import require_pick_target
            targets = self.get_robot_center_pick_targets({"moving": source})
            target = require_pick_target(self, targets, "moving")
            if expected_binding != self.capture_execution_binding():
                raise RuntimeError("Calibration changed during hover target acquisition")
            return self.robot.hover_at(*source, visual_target=target)
        finally:
            self._piece_move_lock.release()

    def execute_pick_place_test(self, source, destination, *, move_context):
        """Manual moves share execution, identity and collision authority with gameplay."""
        from src.motion.result import MotionExecutionResult
        if move_context is None or move_context.src != (source[1], source[0]) or move_context.dst != (destination[1], destination[0]) or move_context.captured_piece_id is not None:
            raise ValueError("Test requires matching piece identity and an empty destination")
        virtual = self.simulation_runtime is not None
        state = getattr(self, "game_state", None)
        if state is None or not state.pick_test_mode or state.pending_test_motion is not None:
            raise RuntimeError("Test requires its isolated board and no unresolved command")
        expected_binding = self.capture_execution_binding()
        if not virtual and not self.verify_physical_board(state.pick_test_board):
            raise RuntimeError("Camera must verify the full test board before pickup")
        if not virtual and not self.is_cell_visually_clear(destination):
            raise RuntimeError("Target square is not empty or the camera has not confirmed; command not sent")
        target = None if virtual else self.get_robot_center_pick_targets({"moving": source})["moving"]
        if expected_binding != self.capture_execution_binding():
            raise RuntimeError("Calibration changed during test target acquisition")
        call_binding = dict(expected_execution_binding=expected_binding)
        result = self.execute_piece_move(*source, *destination, False,
            moving_visual_target=target, piece_id=move_context.piece_id, move_context=move_context,
            **call_binding)
        if not isinstance(result, MotionExecutionResult) or not result.success:
            raise RuntimeError(f"Test did not complete: {getattr(result, "executor returned no valid result", 'executor không trả kết quả hợp lệ')}")
        if not virtual:
            test = state.pending_test_motion
            if test is None or not self.verify_physical_board(test["expected_board"]):
                raise RuntimeError("Ran but the camera did not confirm the whole test board; V to reconcile, do not re-run")
            state.note_verified_test_board(move_context, "completed")
        return result

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
            frame, detections = self._occupancy_snapshot()
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
                sync_required = bool(getattr(self.config, "VISUAL_BOARD_SYNC_REQUIRED", True))
                if not report.board_matches:
                    if sync_required:
                        if report.mismatches:
                            print(f"[BOARD SYNC] FEN mismatch at {list(report.mismatches)}; robot motion blocked.")
                        else:
                            print(f"[BOARD SYNC] Unknown CChess cells at {list(report.unknown_cells)}; robot motion blocked.")
                        continue
                    else:
                        if report.mismatches:
                            print(f"[BOARD SYNC] ⚠️ FEN mismatch at {list(report.mismatches)} (tolerated as VISUAL_BOARD_SYNC_REQUIRED=False).")
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

    @staticmethod
    def _board_diff_cells(expected_board, observed_board):
        """Return per-cell differences for diagnostics; never used to relax matching."""
        if (not isinstance(observed_board, (list, tuple)) or len(observed_board) != 10
                or any(not isinstance(row, (list, tuple)) or len(row) != 9
                       for row in observed_board)):
            return [{"row": None, "col": None,
                     "expected": "valid 10x9 board", "observed": "malformed"}]
        return [
            {"row": row, "col": col,
             "expected": expected_board[row][col], "observed": observed_board[row][col]}
            for row in range(10) for col in range(9)
            if expected_board[row][col] != observed_board[row][col]
        ]

    def verify_physical_board(self, expected_board, *, missing_king_color=None):
        """Require consecutive fresh, quality-approved complete board observations.

        Exact board equality is mandatory. A bounded retry window waits for a
        hand/arm/lighting transient to clear before failing closed.
        """
        from src.vision.cchess_recognizer import validate_board_sanity, piece_confidence_ok
        from src.vision.board_diagnostics import recognition_diagnostics, diagnostic_message, board_position_fen
        from collections import Counter
        from uuid import uuid4
        verification_id = uuid4().hex
        if missing_king_color is not None:
            sane_expected, sanity_error = validate_board_sanity(expected_board, missing_king_color=missing_king_color)
            if not sane_expected:
                event("camera.verification_failed", diagnostic_message("BOARD_SANITY_FAILED", {"sanity_error": sanity_error}),
                      level=logging.WARNING, code="CAMERA_VERIFY_FAILED", verification_id=verification_id,
                      reason="BOARD_SANITY_FAILED", target="expected_board", sanity_error=sanity_error)
                return False
        camera = getattr(self, "cam_monitor", None)
        recognizer = getattr(self, "recognize_board_state", None)
        if not getattr(self, "camera_calibration_ready", False) or camera is None or not callable(recognizer):
            reason = ("CALIBRATION_UNAVAILABLE" if not getattr(self, "camera_calibration_ready", False)
                      else "CAMERA_UNAVAILABLE")
            event("camera.verification_unavailable", diagnostic_message(reason, {}),
                  level=logging.WARNING, code="CAMERA_VERIFY_FAILED", reason=reason,
                  verification_id=verification_id, operation="VERIFY_EXPECTED_BOARD")
            print("[BOARD SYNC] Fresh calibrated camera verification unavailable.")
            return False
        cfg = getattr(self, "config", None)
        minimum = max(2, int(getattr(cfg, "VISUAL_PICK_MIN_STABLE_SAMPLES", 2)))
        samples = max(minimum, int(getattr(cfg, "VISUAL_PICK_SAMPLE_COUNT", minimum)))
        threshold = float(getattr(cfg, "CCHESS_RECOVERY_MIN_CONFIDENCE", 0.5))
        timeout_s = max(0.0, float(getattr(cfg, "VERIFY_BOARD_RETRY_TIMEOUT_SEC", 0.0) or 0.0))
        poll_s = max(0.0, float(getattr(cfg, "VERIFY_BOARD_RETRY_POLL_SEC", 0.10) or 0.0))
        deadline = time.monotonic() + timeout_s
        attempts = 0
        consecutive = 0
        observed = None
        valid = quality = exact = False
        last_observation_at = None
        last_observation_id = None
        diff_cells = []
        last_reason, last_details = "INSUFFICIENT_STABLE_SAMPLES", {}
        failure_counts = Counter()

        def log_sample(reason, details=None, *, exc_info=None):
            nonlocal last_reason, last_details
            last_reason, last_details = reason, dict(details or {})
            if reason != "MATCH":
                failure_counts[reason] += 1
            event("camera.verification_sample", diagnostic_message(reason, last_details), level=logging.DEBUG,
                  verification_id=verification_id, operation="VERIFY_EXPECTED_BOARD", reason=reason,
                  attempt=attempts, recognized=valid, quality_ok=quality, board_matches=exact,
                  consecutive=consecutive, required=minimum, exc_info=exc_info,
                  board_diff_cells=diff_cells[:8], **last_details)

        while True:
            for _ in range(samples):
                if timeout_s > 0 and attempts > 0 and time.monotonic() >= deadline:
                    break
                attempts += 1
                # A rejected/missing latest frame must not inherit diagnostic
                # verdicts or board differences from an earlier sample.
                valid = quality = exact = False
                observed, diff_cells = None, []
                try:
                    fresh_observation = getattr(camera, "get_fresh_observation", None)
                    if callable(fresh_observation):
                        observation = fresh_observation()
                        if observation is None:
                            consecutive = 0
                            log_sample("NO_FRESH_OBSERVATION")
                            continue
                        observed_at, frame, _, result = observation
                        observation_id = result.get("observation_id") if isinstance(result, dict) else None
                        now = time.monotonic()
                        max_age = getattr(camera, "_max_result_age_s", 1.5)
                        rejection = None
                        if not np.isfinite(observed_at):
                            rejection = "INVALID_TIMESTAMP"
                        elif observed_at > now:
                            rejection = "FUTURE_FRAME"
                        elif now - observed_at > max_age:
                            rejection = "STALE_FRAME"
                        elif last_observation_at is not None and observed_at < last_observation_at:
                            rejection = "OUT_OF_ORDER_FRAME"
                        elif observation_id is None and observed_at == last_observation_at:
                            rejection = "DUPLICATE_FRAME"
                        elif observation_id is not None:
                            if type(observation_id) is not int or observation_id <= 0:
                                rejection = "INVALID_OBSERVATION_ID"
                            elif last_observation_id is not None and observation_id <= last_observation_id:
                                rejection = "DUPLICATE_FRAME" if observation_id == last_observation_id else "OUT_OF_ORDER_FRAME"
                        if rejection:
                            consecutive = 0
                            # Invalid evidence must still produce standard JSON,
                            # never bare NaN/Infinity tokens in events.jsonl.
                            timing = dict(observed_at=float(observed_at) if np.isfinite(observed_at) else None,
                                          observation_id=observation_id if type(observation_id) is int else None,
                                          previous_observed_at=last_observation_at,
                                          previous_observation_id=last_observation_id)
                            if not np.isfinite(observed_at):
                                timing["observed_at_repr"] = repr(observed_at)
                            if observation_id is not None and type(observation_id) is not int:
                                timing["observation_id_repr"] = repr(observation_id)
                            if np.isfinite(observed_at):
                                timing.update(frame_age_s=round(now - observed_at, 4),
                                              max_frame_age_s=float(max_age) if np.isfinite(max_age) else None)
                            log_sample(rejection, timing)
                            continue
                        last_observation_at = observed_at
                        last_observation_id = observation_id
                    else:
                        # Compatibility for external snapshot adapters; real CameraMonitor
                        # provides atomic observations and never reruns layout inference here.
                        frame, _ = camera.get_fresh_snapshot()
                        result = recognizer(frame) if frame is not None else None
                    valid = bool(result and result.get("success"))
                    observed = result.get("board") if result else None
                    from src.vision.cchess_recognizer import validate_board_sanity
                    sane, sanity_error = (validate_board_sanity(observed, missing_king_color=missing_king_color)
                               if isinstance(observed, (list, tuple)) else (False, None))
                    if result and "quality_ok" in result:
                        quality = result["quality_ok"] is True and sane
                    else:
                        quality = (sane and piece_confidence_ok(
                            observed, result.get("confidence") if result else None, threshold))
                    exact = (isinstance(observed, (list, tuple)) and len(observed) == 10
                             and all(isinstance(row, (list, tuple)) and len(row) == 9 for row in observed)
                             and observed == expected_board)
                    diff_cells = [] if exact else HardwareManager._board_diff_cells(expected_board, observed)
                    # Camera availability is never evidence that the physical move completed.
                    frame_ok = frame is not None and valid and quality and exact
                    consecutive = consecutive + 1 if frame_ok else 0
                    reason, details = recognition_diagnostics(
                        result, threshold, sane=sane, sanity_error=sanity_error,
                        quality=quality, exact=exact, diff_cells=diff_cells)
                    log_sample(reason if frame is not None else "FRAME_UNAVAILABLE", details)
                    if consecutive >= minimum:
                        event("camera.verified", "Camera xác nhận bàn dự kiến",
                              verification_id=verification_id, operation="VERIFY_EXPECTED_BOARD",
                              samples=consecutive, attempts=attempts)
                        state = getattr(self, "game_state", None)
                        if state is not None:
                            state.note_verified_pending_board(expected_board)
                        return True
                except Exception as exc:
                    print(f"[BOARD SYNC] Fresh verification failed: {exc}")
                    consecutive = 0
                    log_sample("EXCEPTION", dict(error=str(exc), exception_type=type(exc).__name__), exc_info=True)
            if time.monotonic() >= deadline:
                break
            event("camera.verification_retry", "Chưa đủ mẫu liên tiếp; chờ bàn ổn định để xác nhận lại",
                  level=logging.DEBUG, verification_id=verification_id, reason=last_reason,
                  attempts=attempts, consecutive=consecutive,
                  timeout_s=timeout_s,
                  remaining_s=round(max(0.0, deadline - time.monotonic()), 3),
                  board_diff_count=len(diff_cells), board_diff_cells=diff_cells[:8])
            time.sleep(poll_s)
        print("[BOARD SYNC] Full physical board was not confirmed by consecutive fresh frames.")
        reason = "INSUFFICIENT_STABLE_SAMPLES" if last_reason == "MATCH" else last_reason
        details = dict(last_details, consecutive=consecutive, required=minimum)
        details.setdefault("board_diff_count", len(diff_cells))
        details.setdefault("diff_cells", diff_cells)
        state = getattr(self, "game_state", None)
        event("camera.verification_failed",
              diagnostic_message(reason, details),
              level=logging.WARNING, code="CAMERA_VERIFY_FAILED", reason=reason,
              verification_id=verification_id, operation="VERIFY_EXPECTED_BOARD",
              attempts=attempts, timeout_s=timeout_s, failure_counts=dict(failure_counts),
              recognized=valid, quality_ok=quality, board_matches=exact,
              game_fen=getattr(state, "current_fen", None),
              board_revision=getattr(state, "board_revision", None),
              move_id=getattr(getattr(state, "pending_move", None), "move_id", None),
              expected_board_fen=board_position_fen(expected_board),
              expected_board=expected_board, observed_board=observed, **details)
        return False

    def capture_baseline_if_needed(self, force_delay=0.0, expected_board=None):
        if self.cam_monitor and self.yolo_detector:
            if force_delay > 0:
                time.sleep(force_delay)
            if expected_board is not None and not self.dry_run and not self.verify_physical_board(expected_board):
                self.yolo_detector.clear_baseline()
                event('camera.baseline_rejected', 'Camera chưa xác nhận bàn dự kiến; chưa lấy baseline.',
                      level=logging.WARNING, code='CAMERA_VERIFY_FAILED')
                return False
            frame, detections = self.cam_monitor.get_fresh_snapshot()
            success = self.yolo_detector.capture_baseline(frame, detections)
            occ = getattr(self.yolo_detector, '_baseline_occ', None)
            reference = expected_board if expected_board is not None else getattr(getattr(self, 'game_state', None), 'board', None)
            grid_types = (list, tuple, np.ndarray)
            valid_grid = lambda grid: (isinstance(grid, grid_types) and len(grid) == 10
                                      and all(isinstance(row, grid_types) and len(row) == 9 for row in grid))
            if success and valid_grid(occ) and valid_grid(reference):
                from src.vision.board_diagnostics import yolo_baseline_message
                occupied_count = sum(bool(cell) for row in occ for cell in row)
                expected_count = sum(piece != '.' for row in reference for piece in row)
                differences = [dict(row=r, col=c, expected_piece=reference[r][c], yolo_occupied=bool(occ[r][c]))
                               for r in range(10) for c in range(9)
                               if bool(occ[r][c]) != (reference[r][c] != '.')]
                event('camera.yolo_baseline',
                      yolo_baseline_message(occupied_count, expected_count, differences),
                      level=logging.WARNING if differences else logging.INFO,
                      source='YOLO_OCCUPANCY', raw_detection_count=len(detections),
                      yolo_occupied_count=occupied_count, expected_piece_count=expected_count,
                      occupancy_diff_count=len(differences), occupancy_diff_cells=differences,
                      cell_order='row,col', cell_index_base=0)
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
