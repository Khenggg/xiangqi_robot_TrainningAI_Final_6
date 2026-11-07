# ===================================================================================
# === FILE: main.py (CLEAN ARCHITECTURE) ===
# ===================================================================================
import sys
import os
from src.core.launch_options import parse_options, configure_runtime, ViewerServer, check_viewer_assets

# Parse before pygame or hardware imports so --help never opens a device.
launch_options = parse_options() if __name__ == "__main__" else parse_options([])

# Set SDL's DPI policy before pygame initializes the Windows display.
os.environ.setdefault("SDL_WINDOWS_DPI_AWARENESS", "permonitorv2")

# Đảm bảo in tiếng Việt không bị lỗi font/crash UnicodeEncodeError trên Windows console
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import time
import random
import threading
import atexit
import subprocess
import traceback
import signal

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE_DIR)

import config  # type: ignore
configure_runtime(config, launch_options)
from src.core.project_logging import start_logging, event as log_event, record_code_version
import logging
log_session = start_logging(
    os.path.join(_BASE_DIR, launch_options.log_dir), launch_options.log_level,
    secrets=[value for key, value in vars(config).items()
             if any(part in key.upper() for part in ("TOKEN", "PASSWORD", "SECRET", "API_KEY"))
             and isinstance(value, str)],
)
record_code_version(_BASE_DIR)
log_event("app.configuration", "Cấu hình phiên chạy", backend=config.ROBOT_BACKEND,
      dry_run=config.DRY_RUN, game_only=config.GAME_ONLY,
      viewer_port=launch_options.viewer_port, telemetry_port=config.TELEMETRY_PORT,
      frame="robot_base", position_unit="mm", joint_unit="deg")
import pygame  # type: ignore
from src.core import xiangqi  # type: ignore

from src.core.ai_execution import execute_ai_move
from src.core.self_play_controller import SelfPlayController
from src.hardware.telemetry_publisher import TelemetryPublisher
from src.core.game_state import GameState  # type: ignore
from src.hardware.hardware_manager import HardwareManager  # type: ignore
from src.ui.input_handler import InputHandler  # type: ignore
from src.ui.debug_dashboard import DebugDashboard  # type: ignore

# ==========================================
# 0. CHẾ ĐỘ & DỌN DẸP TIẾN TRÌNH CŨ
# ==========================================
_mode_label = '🛠️ DRY RUN (MOUSE & LOG)' if config.DRY_RUN else '🤖 REAL RUN (CAMERA & ROBOT)'
print(f"\n=== MODE: {_mode_label} ===")

def _kill_zombie_processes():
    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq moonfish*', '/FO', 'CSV', '/NH'],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip() and 'moonfish' in result.stdout.lower():
            print("[CLEANUP] ⚠️ Phát hiện moonfish zombie process — đang kill...")
            subprocess.run(['taskkill', '/F', '/IM', 'moonfish*'], capture_output=True, timeout=5)
            print("[CLEANUP] ✅ Killed zombie moonfish processes.")
            time.sleep(0.5)
    except Exception as e:
        print(f"[CLEANUP] ⚠️ Không thể kiểm tra zombie processes: {e}")

# Engine instances own and close their own processes.

# ==========================================
# 1. KHỞI TẠO HỆ THỐNG CỐT LÕI
# ==========================================
pygame.init()
pygame.font.init()

from src.ui.board_renderer import BoardRenderer, SCREEN_WIDTH, SCREEN_HEIGHT, BTN_NEW_GAME_RECT, BTN_MODE_SELECT_RECT, BTN_SURRENDER_RECT  # type: ignore
from src.ui.game_window import GameWindow
from src.ui.exit_confirmation import confirm_exit, exit_application
game_window = GameWindow((SCREEN_WIDTH, SCREEN_HEIGHT))
screen = game_window.canvas
pygame.display.set_caption(f"Xiangqi Robot VIP - { _mode_label }")
renderer = BoardRenderer(screen)

# Khởi tạo các module quản lý SRP
state = GameState(allow_mouse_move=config.DRY_RUN)
hw = None
telemetry = None
self_play = None
input_mgr = None
session_control = None
quit_requested = False
mode_disposal = None
mode_switching = False
mode_switch_failed = False
difficulty_menu_active = False
home_screen_active = True
home_mode = ("PHYSICAL" if getattr(launch_options, "physical", False)
             else "BOARD_ONLY" if getattr(launch_options, "virtual", False)
             else "SIMULATION")
# The checkbox requests manual four-corner camera calibration at physical
# startup. --recalibrate-camera preselects it.
physical_camera_recalibration_requested = bool(
    getattr(launch_options, "recalibrate_camera", False))
startup_message = ""
settings_menu_active = False
difficulty_menu_message = ""
debug_dashboard = None
viewer_server = None
physical_enable_pending = False
physical_enable_deadline = 0.0
from src.core.motion_worker import MotionWorker
startup_worker = MotionWorker()
startup_cancelled = threading.Event()
_cleanup_done = False
_cleanup_disposal = None


def set_debug_dashboard(enabled):
    """Enable or close the optional telemetry window for this app session."""
    global debug_dashboard
    config.DEBUG_DASHBOARD = enabled
    if enabled and debug_dashboard is None:
        debug_dashboard = DebugDashboard(config.DRY_RUN)
        if hw is not None:
            debug_dashboard.robot = hw.robot
            debug_dashboard.activity = "Game setup"
    elif not enabled and debug_dashboard is not None:
        debug_dashboard.close()
        debug_dashboard = None

def _start_selected_game():
    assert hw is not None
    profile = getattr(hw, "profile", None)
    captured = (hw.capture_baseline_if_needed(force_delay=0.0, expected_board=state.board)
                if profile is None or profile.camera_enabled else True)
    if profile is not None and profile.mouse_input == "VIRTUAL_TEST_ADAPTER":
        state.set_status("HvR ẢO: bộ nhập chuột phục vụ test, không phải xác nhận camera thật.", duration=30)
    if not config.DRY_RUN and not captured:
        state.manual_override_active = True
        state.snapshot_continue_required = True
        state.set_status("Camera chưa xác nhận bàn ban đầu. Sắp xếp quân rồi bấm V để đối soát.", duration=30)
        return
    if config.ROBOT_BACKEND == "PHYSICAL" and not hw.is_robot_ready:
        hint = ("O mở người Đen; hai bên chọn nước bằng chuột." if config.GAME_MODE == "HUMAN_VS_HUMAN_ROBOT"
                else "F6 bắt đầu self-play.")
        state.set_status("FR3 chỉ đọc. Kiểm tra setup, bấm F9 rồi F10 để bật robot; " + hint, duration=30)
    if config.GAME_MODE == "ROBOT_VS_ROBOT" and self_play is not None and hw.is_robot_ready:
        difficulty = getattr(config, "AI_DIFFICULTY", "medium")
        if self_play.start(difficulty, difficulty, run_mode="continuous"):
            state.set_status("Robot vs robot: continuous / F8 stop", duration=30)
    if state.api_client.token and not state.recovery_required:
        state.ensure_spectator_match()

def _retain_startup_failure(error):
    """Do not launch a second session above resources whose close failed."""
    global hw, telemetry, viewer_server, self_play, input_mgr, session_control
    global mode_disposal, mode_switch_failed, home_screen_active, difficulty_menu_active
    from src.core.session_control import SessionControl
    from src.core.session_disposal import SessionDisposal
    hw, telemetry, viewer_server = error.manager, error.telemetry, error.viewer
    self_play = input_mgr = None
    session_control = SessionControl(state, hw, None) if hw is not None else None
    mode_disposal = SessionDisposal(state, hw, None, telemetry, viewer_server, debug_dashboard,
                                   require_settled=False, publish_end=False)
    # A previous cleanup may have proved stop and closed the SDK before a camera
    # or web resource failed. Its frozen retirement proof remains valid here.
    mode_disposal._stop_proved = bool(hw is not None and getattr(hw, "_closing", False)
                                     and getattr(hw, "_cleanup_stop_proved", False))
    if hw is not None and not mode_disposal._stop_proved:
        hw.request_controlled_stop("Partial startup retirement")
    mode_switch_failed = True
    home_screen_active = difficulty_menu_active = False
    state.set_status(f"Giữ phiên khởi tạo lỗi: {error}. F2 đóng lại trước khi chọn chế độ mới.", duration=60)


def _finish_startup(result, error):
    global hw, telemetry, viewer_server, self_play, input_mgr, home_screen_active, state
    global difficulty_menu_active, startup_message, mirror_error, session_control
    if error:
        from src.core.session_startup import StartupRollbackError
        if isinstance(error, StartupRollbackError):
            _retain_startup_failure(error)
            return
        # Successful rollback closed its API worker/journal. A retry gets new
        # local owners; the next attach restores saved truth through recovery.
        state = GameState(allow_mouse_move=config.DRY_RUN)
        error_text = str(error)
        lower_error = error_text.lower()
        if "calibration" in lower_error or "perspective" in lower_error:
            calibration_hint = (
                " Tick Chấm lại 4 góc bàn từ camera trong thẻ ROBOT THẬT rồi thử lại.")
        elif "R1-R4" in error_text or "R1–R4" in error_text:
            calibration_hint = (
                " Kiểm tra/dạy lại R1–R4 trên pendant (cùng tool, user 0) trước khi thử lại.")
        else:
            calibration_hint = ""
        startup_message = (f"Không khởi tạo được: {error}. Khắc phục rồi chọn chế độ lại."
                           f"{calibration_hint} Chi tiết STARTUP_FAILED trong logs/.")
        log_event("startup.blocked", startup_message, level=logging.ERROR, code="STARTUP_FAILED")
        return
    manager, publisher, server, reason = result
    if getattr(manager, "profile", None) is None:
        from src.core.session_profile import profile_from_config
        manager.profile = profile_from_config(config)
    if getattr(manager, "stop_coordinator", None) is None:
        from src.hardware.controlled_stop import ControlledStopCoordinator
        manager._piece_move_lock = getattr(manager, "_piece_move_lock", None) or threading.Lock()
        manager.robot = getattr(manager, "robot", None)
        manager.stop_coordinator = ControlledStopCoordinator(manager)
    if not callable(getattr(manager, "request_controlled_stop", None)):
        manager.request_controlled_stop = manager.stop_coordinator.begin
    try:
        controller = SelfPlayController(state, manager)
        handler = InputHandler(state, manager)
        if manager.profile.game_mode == "HUMAN_VS_HUMAN_ROBOT":
            from src.core.robot_pvp import RobotPvPController
            manager.pvp_controller = RobotPvPController(state, manager)
    except Exception as exc:
        from src.core.session_startup import rollback_session, StartupRollbackError
        try:
            rollback_session(manager, publisher, server, state)
        except StartupRollbackError as cleanup_error:
            _retain_startup_failure(cleanup_error)
            return
        hw = telemetry = viewer_server = self_play = input_mgr = None
        home_screen_active = True
        difficulty_menu_active = False
        _finish_startup(None, exc)
        return
    hw, telemetry, viewer_server, mirror_error = manager, publisher, server, reason
    self_play, input_mgr = controller, handler
    profile = manager.profile
    caption = ("Người vs Người — Chuột, không Camera/FR3" if profile.game_mode == "HUMAN_VS_HUMAN"
               else ("ẢO / bộ nhập test" if profile.dry_run else "THẬT / Camera & FR3"))
    if profile.game_mode == "HUMAN_VS_HUMAN_ROBOT":
        caption = "2 người + robot — " + ("Mô phỏng" if profile.dry_run else "Camera & FR3 thật")
    pygame.display.set_caption(f"Xiangqi Robot — {caption}")
    from src.core.session_control import SessionControl
    session_control = SessionControl(state, manager, controller)
    handler.session_control = session_control
    if mirror_error:
        state.set_status(mirror_error, duration=30)
    home_screen_active = False
    startup_message = ""
    difficulty_menu_active = config.GAME_MODE not in {"HUMAN_VS_HUMAN", "HUMAN_VS_HUMAN_ROBOT"}
    if debug_dashboard is not None:
        debug_dashboard.robot, debug_dashboard.backend = hw.robot, hw.backend
    if not difficulty_menu_active:
        hw.motion_worker.start(_start_selected_game, _job_completed)


def _job_completed(value, error):
    if error:
        state.set_status(f"Thao tác thất bại: {error}. Đọc log để khắc phục.", duration=30)
        log_event("job.failed", str(error), level=logging.ERROR, code="STARTUP_FAILED")


def _refresh_game_baseline():
    captured = hw.capture_baseline_if_needed(force_delay=0)
    if not config.DRY_RUN and not captured:
        state.manual_override_active = True
        state.snapshot_continue_required = True
        state.set_status("Nước đã hoàn tất nhưng baseline camera lỗi. Bấm V để đối soát trước khi tiếp tục.", duration=30)
    return captured


def _select_difficulty(choice):
    global difficulty_menu_active, difficulty_menu_message
    def completed(result, error):
        global difficulty_menu_active, difficulty_menu_message
        if error:
            difficulty_menu_message = str(error)
            return
        ok, reason = result
        if ok:
            difficulty_menu_active = False
            difficulty_menu_message = ""
            state.set_status(reason, color=(0,110,70), duration=6)
            hw.motion_worker.start(_start_selected_game, _job_completed)
        else:
            difficulty_menu_message = reason
    hw.motion_worker.start(lambda: hw.select_difficulty(choice), completed)


def _request_mode_menu():
    if mode_switching:
        return
    if mode_switch_failed and mode_disposal is not None:
        _begin_mode_disposal()
    elif session_control is not None:
        session_control.request("home")


def _launch_session_mode(selected_mode, *, camera_recalibration=False):
    """Start one session, optionally forcing manual four-corner camera calibration."""
    global startup_message
    mode_label = {"BOARD_ONLY": "bàn cờ 2D", "SIMULATION": "mô phỏng 3D",
                  "PHYSICAL": "robot thật"}.get(selected_mode, selected_mode)
    startup_message = f"Đang khởi tạo {mode_label}… Có thể đóng cửa sổ để hủy."
    from src.core.session_startup import build_session
    previous_recalibrate = bool(getattr(config, "RECALIBRATE_CAMERA", False))
    previous_manual = bool(getattr(config, "CAMERA_CALIBRATION_MANUAL_ONLY", False))

    def _start_selected_session():
        config.RECALIBRATE_CAMERA = bool(previous_recalibrate or camera_recalibration)
        config.CAMERA_CALIBRATION_MANUAL_ONLY = bool(camera_recalibration)
        try:
            return build_session(config, launch_options, _BASE_DIR, state,
                                 startup_cancelled, selected_mode)
        finally:
            config.RECALIBRATE_CAMERA = previous_recalibrate
            config.CAMERA_CALIBRATION_MANUAL_ONLY = previous_manual

    if camera_recalibration:
        log_event("physical.camera_calibration_requested",
                  "Người vận hành yêu cầu chấm lại 4 góc bàn từ camera",
                  level=logging.INFO)
    return startup_worker.start(_start_selected_session, _finish_startup)


def _begin_mode_disposal():
    global mode_disposal, mode_switching, mode_switch_failed
    if mode_switching or startup_worker.busy or (hw is None and mode_disposal is None):
        return
    if mode_disposal is None:
        from src.core.session_disposal import SessionDisposal
        mode_disposal = SessionDisposal(state, hw, self_play, telemetry, viewer_server, debug_dashboard)
    mode_switching = True
    mode_switch_failed = False
    state.set_status("Đang đóng phiên cũ; chưa mở camera/robot của chế độ mới.", duration=60)
    camera = getattr(hw, "cam_monitor", None)
    if callable(getattr(camera, "close_display", None)):
        camera.close_display()
    if not startup_worker.start(mode_disposal.run, _finish_mode_disposal):
        mode_switching = False


def _finish_mode_disposal(result, error):
    global mode_disposal, mode_switching, mode_switch_failed, state, hw, telemetry, self_play
    global viewer_server, input_mgr, session_control, debug_dashboard, home_screen_active
    global difficulty_menu_active, settings_menu_active, startup_message, startup_cancelled
    global physical_enable_pending, physical_camera_recalibration_requested
    mode_switching = False
    if error or result is not True:
        mode_switch_failed = True
        reason = str(error or "Teardown did not complete")
        log_event("session.switch_failed", reason, level=logging.ERROR, code="SESSION_SWITCH_FAILED")
        state.set_status(f"Chưa đổi chế độ: {reason}. F2 thử lại sau khi xử lý; Ctrl+F9 chỉ khi đã tắt controller trên pendant.", duration=60)
        return
    # All old actor/read/projection owners are closed before replacing globals.
    hw = telemetry = self_play = viewer_server = input_mgr = session_control = debug_dashboard = None
    mode_disposal = None
    mode_switch_failed = False
    physical_enable_pending = False
    physical_camera_recalibration_requested = False
    difficulty_menu_active = settings_menu_active = False
    if not quit_requested:
        state = GameState(allow_mouse_move=True)
        startup_cancelled = threading.Event()
        startup_message = "Phiên cũ đã đóng. Chọn chế độ để bắt đầu ván mới."
        home_screen_active = True
        pygame.display.set_caption("Xiangqi Robot — Chọn chế độ")


def _cleanup_all():
    global _cleanup_done, _cleanup_disposal
    if _cleanup_done:
        return True
    startup_cancelled.set()
    failures = []
    def close(name, operation):
        try:
            operation()
            return True
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            log_event("cleanup.failed", f"{name}: {exc}", level=logging.ERROR)
            return False
    if not close("startup", startup_worker.close):
        return False
    if not close("startup result", startup_worker.poll):
        return False
    if _cleanup_disposal is None:
        from src.core.session_disposal import SessionDisposal
        _cleanup_disposal = mode_disposal or SessionDisposal(
            state, hw, self_play, telemetry, viewer_server, debug_dashboard, require_settled=False)
    # Once disposal has proved stop and frozen dispatch, SDK closure must not
    # force another telemetry read or replay controller stop/disable on retry.
    if hw is not None and not _cleanup_disposal._stop_proved:
        try:
            stop = hw.request_controlled_stop("Shutdown", workers_finished=lambda:
                (self_play is None or self_play._thread is None or not self_play._thread.is_alive())
                and (state.ai_thread is None or not state.ai_thread.is_alive())
                and all(not thread.is_alive() for thread in state._retired_ai_threads))
            if not stop.done.wait(7.0) or not stop.result.safe:
                raise RuntimeError("Chưa xác nhận robot dừng; giữ camera/controller/phiên")
        except Exception as exc:
            log_event("cleanup.recovery_required", str(exc), level=logging.ERROR)
            return False
    camera = getattr(hw, "cam_monitor", None)
    if callable(getattr(camera, "close_display", None)):
        close("camera display", camera.close_display)
    if not close("session disposal", _cleanup_disposal.run):
        return False
    if not close("pygame", pygame.quit):
        return False
    _cleanup_done = True
    log_event("app.cleanup", "Đã đóng các dịch vụ; kiểm tra lỗi còn chờ nếu có.", failures=failures)
    return True

atexit.register(_cleanup_all)


# Defer terminal Ctrl+C to the event loop. Cancelling its confirmation must not
# enter the exception-recovery path or request a session shutdown.
_interrupt_requested = False


def _queue_interrupt(signum, frame):
    global _interrupt_requested
    _interrupt_requested = True


_previous_sigint_handler = signal.signal(signal.SIGINT, _queue_interrupt)


def _recover_shutdown_after_exception(exc, *, cleanup_retry=False):
    """Keep recovery visible; confirmed application exit never waits on hardware."""
    global quit_requested
    quit_requested = True
    startup_cancelled.set()
    if session_control is not None and not cleanup_retry:
        session_control.request("quit")
    try:
        if not cleanup_retry:
            state.persist_checkpoint("RECOVERY_REQUIRED")
    except Exception as persist_error:
        log_event("session.persistence_failed", str(persist_error), level=logging.ERROR,
                  code="SESSION_PERSISTENCE_FAILED")
    message = f"RECOVERY REQUIRED: {type(exc).__name__}. Inspect arm/gripper on pendant, then Ctrl+F8."
    log_event("app.recovery_wait", message, level=logging.ERROR)
    recovery_clock = pygame.time.Clock()
    # Startup/hardware workers may already be closed by a partial teardown.
    # This worker performs operator-approved read-only confirmation only.
    operator_worker = MotionWorker()
    retry_requested = False
    while True:
        try:
            global _interrupt_requested
            if _interrupt_requested:
                _interrupt_requested = False
                if confirm_exit():
                    exit_application()
                    return
            for item in pygame.event.get():
                if (item.type == pygame.QUIT or
                        (item.type == pygame.KEYDOWN and item.key == pygame.K_c
                         and getattr(item, "mod", 0) & pygame.KMOD_CTRL)):
                    if confirm_exit():
                        exit_application()
                        return
                if item.type == pygame.KEYDOWN and item.key == pygame.K_F2:
                    retry_requested = True
                if (item.type == pygame.KEYDOWN and item.key == pygame.K_F8
                        and getattr(item, "mod", 0) & pygame.KMOD_CTRL
                        and hw is not None and not hw.motion_worker.running):
                    operator_worker.start(lambda: hw.confirm_operator_stop(approved=True), _job_completed)
                if (item.type == pygame.KEYDOWN and item.key == pygame.K_F9
                        and getattr(item, "mod", 0) & pygame.KMOD_CTRL
                        and hw is not None and not hw.motion_worker.running):
                    operator_worker.start(lambda: hw.confirm_operator_controller_disabled(approved=True), _job_completed)
            # Completed callbacks may themselves be the original failure source.
            # Poll once to retire ownership, preserving pending state on failure.
            for worker in (startup_worker, operator_worker, hw.motion_worker if hw is not None else None):
                if worker is not None:
                    try:
                        worker.poll()
                    except Exception as callback_error:
                        log_event("app.recovery_callback_failed", str(callback_error), level=logging.ERROR)
            if self_play is not None and not cleanup_retry:
                try:
                    self_play.tick()
                except Exception as controller_error:
                    self_play._fault(f"RECOVERY_REQUIRED: {controller_error}")
            # F2 retries cleanup from either recovery phase. Cleanup itself still
            # enforces the robot/camera stop barrier; F2 is not a force-kill.
            if (retry_requested and not operator_worker.busy and not startup_worker.running
                    and (hw is None or not hw.motion_worker.running)):
                operator_worker.close()
                return
            if not cleanup_retry:
                if session_control is not None:
                    if session_control.poll() == "quit":
                        operator_worker.close()
                        return
                elif not startup_worker.running:
                    operator_worker.close()
                    return
            # Render independently of the regular renderer which may have failed.
            surface = pygame.display.get_surface()
            if surface is not None:
                surface.fill((35, 20, 20))
                font = pygame.font.Font(None, 24)
                for index, line in enumerate(("RECOVERY REQUIRED - project is paused", str(exc)[:100],
                                              "Inspect/stop the arm and gripper on the pendant.",
                                              "Ctrl+F8: approve read-only stop verification.",
                                              "Ctrl+F9: confirm controller disabled on pendant (lost disable ACK).",
                                              "F2: retry closing unfinished resources.",
                                              "Close window / Ctrl+C: confirm once to exit immediately.",
                                              "Camera/controller and pending transaction are retained.")):
                    surface.blit(font.render(line, True, (255, 220, 200)), (20, 25 + index * 30))
                pygame.display.flip()
            recovery_clock.tick(10)
        except KeyboardInterrupt:
            if confirm_exit():
                exit_application()
                return
        except pygame.error as display_error:
            log_event("app.recovery_display_failed", str(display_error), level=logging.ERROR)
            time.sleep(.1)

# ==========================================
# 2. VÒNG LẶP CHÍNH
# ==========================================
running = True
clock = pygame.time.Clock()

print(f"\n[GAME] === GAME STARTED ===")
print(f"[FEN] {state.current_fen}")

# Khởi chạy main loop. The launcher keeps difficulty selection out of the boot flow.
try:
    last_ui_lag_warning = 0.0
    while running:
        if _interrupt_requested:
            _interrupt_requested = False
            if confirm_exit():
                exit_application()
                running = False
                break
        frame_started = time.monotonic()
        # 2a. Vẽ khung hình
        if settings_menu_active:
            renderer.draw_settings_menu(getattr(config, "DEBUG_DASHBOARD", False))
        elif home_screen_active:
            renderer.home_mode = home_mode
            renderer.physical_camera_recalibration_requested = physical_camera_recalibration_requested
            renderer.draw_home_screen(startup_message)
        else:
            state.is_robot_ready = hw.is_robot_ready if hw is not None else False
            state.physical_enable_pending = physical_enable_pending
            renderer.draw_ui(state.get_render_state())
            renderer.draw_pieces(state.pick_test_board if state.pick_test_mode else state.board)
            renderer.draw_highlight(state.last_move, state.selected_pos, state.invalid_flash_pos, state.invalid_flash_expiry)
            if state.game_over:
                renderer.draw_game_over(state.winner)
        if difficulty_menu_active:
            renderer.draw_difficulty_menu(hw.difficulty_availability(), difficulty_menu_message)

        # 2b. Xử lý Input
        for event in pygame.event.get():
            event = game_window.map_event(event)
            if event is None:
                continue
            if (event.type == pygame.QUIT or
                    (event.type == pygame.KEYDOWN and event.key == pygame.K_c
                     and getattr(event, "mod", 0) & pygame.KMOD_CTRL)):
                if confirm_exit():
                    exit_application()
                    running = False
                    break
                continue
            # Urgent controls bypass the normal busy-input filter.
            elif (event.type == pygame.KEYDOWN and event.key == pygame.K_F9
                  and getattr(event, "mod", 0) & pygame.KMOD_CTRL and hw is not None):
                if not startup_worker.busy:
                    startup_worker.start(lambda: hw.confirm_operator_controller_disabled(approved=True), _job_completed)
                continue
            elif (event.type == pygame.KEYDOWN and event.key == pygame.K_F2
                  and not home_screen_active and not settings_menu_active):
                _request_mode_menu()
                continue
            elif (event.type == pygame.MOUSEBUTTONDOWN and session_control is not None
                  and not mode_switching and not mode_switch_failed
                  and not home_screen_active and not settings_menu_active and not difficulty_menu_active
                  and BTN_SURRENDER_RECT.collidepoint(event.pos)
                  and not state.game_over and not (self_play is not None and self_play.active)):
                input_mgr.handle_mouse_down(*event.pos)
                continue
            elif (event.type == pygame.MOUSEBUTTONDOWN and session_control is not None
                  and not home_screen_active and not settings_menu_active
                  and BTN_MODE_SELECT_RECT.collidepoint(event.pos)):
                _request_mode_menu()
                continue
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F8 and hw is not None:
                if getattr(event, "mod", 0) & pygame.KMOD_CTRL:
                    verifier_worker = startup_worker if mode_switch_failed or getattr(hw, "_closing", False) else hw.motion_worker
                    verifier_worker.start(lambda: hw.confirm_operator_stop(approved=True), _job_completed)
                elif self_play is not None and self_play.active:
                    self_play.end_match()
                elif session_control is not None:
                    session_control.request("pause")
                continue
            elif (event.type == pygame.MOUSEBUTTONDOWN and session_control is not None
                  and not mode_switching and not mode_switch_failed
                  and not home_screen_active and not settings_menu_active and not difficulty_menu_active
                  and (input_mgr is None or (hw is not None and hw.motion_worker.busy)
                       or (self_play is not None and self_play.human_input_disabled and not self_play.recovery_input_allowed))
                  and BTN_NEW_GAME_RECT.collidepoint(event.pos)):
                session_control.request("reset")
                continue
            elif (mode_switching or mode_switch_failed) and event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                continue
            elif quit_requested and event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                if (event.type == pygame.KEYDOWN and input_mgr is not None
                        and event.key in (pygame.K_v, pygame.K_F4, pygame.K_1, pygame.K_2)
                        and not hw.motion_worker.busy):
                    input_mgr.handle_keyboard(event.key)
                continue
            elif ((startup_worker.busy or (hw is not None and hw.motion_worker.busy))
                  and event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN)):
                continue
            elif home_screen_active:
                home_action = None
                start_vs_robot = event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if (home_mode == "PHYSICAL"
                            and renderer.home_physical_camera_calibration_from_pixel(
                                event.pos[0], event.pos[1])):
                        physical_camera_recalibration_requested = not physical_camera_recalibration_requested
                        startup_message = ""
                        continue
                    selected_mode = renderer.home_mode_from_pixel(event.pos[0], event.pos[1])
                    if selected_mode is not None:
                        if selected_mode != home_mode:
                            physical_camera_recalibration_requested = False
                        home_mode = selected_mode
                        startup_message = ""
                        continue
                    home_action = renderer.home_action_from_pixel(event.pos[0], event.pos[1])
                    start_vs_robot = home_action in ("vs_robot", "self_play", "human_vs_human", "robot_pvp")
                    if home_action == "join_pvp":
                        from src.core.robot_pvp import launch_client
                        launch_client()
                        continue
                if start_vs_robot:
                    config.GAME_MODE = {"self_play": "ROBOT_VS_ROBOT", "human_vs_human": "HUMAN_VS_HUMAN",
                                        "robot_pvp": "HUMAN_VS_HUMAN_ROBOT"}.get(home_action, "HUMAN_VS_ROBOT")
                    if home_action == "robot_pvp" and home_mode == "BOARD_ONLY":
                        startup_message = "Hai người + robot cần chọn MÔ PHỎNG 3D hoặc ROBOT THẬT trước."
                        continue
                    selected_mode = home_mode
                    camera_recalibration = bool(
                        selected_mode == "PHYSICAL"
                        and config.GAME_MODE != "HUMAN_VS_HUMAN"
                        and physical_camera_recalibration_requested)
                    physical_camera_recalibration_requested = False
                    _launch_session_mode(selected_mode, camera_recalibration=camera_recalibration)
                elif event.type == pygame.MOUSEBUTTONDOWN and renderer.home_action_from_pixel(event.pos[0], event.pos[1]) == "settings":
                    home_screen_active = False
                    settings_menu_active = True
            elif settings_menu_active:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    settings_menu_active = False
                    home_screen_active = True
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    action = renderer.settings_action_from_pixel(event.pos[0], event.pos[1])
                    if action == "home":
                        settings_menu_active = False
                        home_screen_active = True
                    elif action == "toggle_debug_dashboard":
                        set_debug_dashboard(not getattr(config, "DEBUG_DASHBOARD", False))
            elif difficulty_menu_active:
                choice = None
                if event.type == pygame.KEYDOWN:
                    choice = {pygame.K_1: "easy", pygame.K_2: "medium", pygame.K_3: "hard", pygame.K_4: "impossible"}.get(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    choice = renderer.difficulty_from_pixel(event.pos[0], event.pos[1])
                if choice:
                    _select_difficulty(choice)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F9 and config.ROBOT_BACKEND == "PHYSICAL":
                    physical_enable_pending = not physical_enable_pending
                    physical_enable_deadline = time.monotonic() + 30.0
                    state.set_status("Đã kiểm tra setup và nút dừng khẩn cấp? F10 bật robot trong 30s; F9 hủy."
                                     if physical_enable_pending else "Đã hủy yêu cầu bật robot.", duration=30)
                    continue
                if event.key == pygame.K_F10 and physical_enable_pending:
                    physical_enable_pending = False
                    try:
                        if time.monotonic() > physical_enable_deadline:
                            raise RuntimeError("Xác nhận hết hạn; bấm F9 để bắt đầu lại")
                        def enabled(result, error):
                            if error:
                                log_event("physical.enable_failed", str(error), level=logging.ERROR,
                                          code="PHYSICAL_ENABLE_FAILED",
                                          exc_info=(type(error), error, error.__traceback__))
                            state.set_status(f"Không bật được robot: {error}" if error else
                                             "Robot đã được bật quyền chuyển động cho game.", duration=60)
                        hw.motion_worker.start(lambda: hw.activate_physical_game(state, commissioned=True), enabled)
                    except Exception as exc:
                        log_event("physical.enable_failed", str(exc), level=logging.ERROR,
                              code="PHYSICAL_ENABLE_FAILED", exc_info=True)
                        state.set_status(f"Không bật được robot: {exc}", duration=30)
                    continue
                if hw.motion_worker.busy:
                    continue
                if (self_play is not None and config.GAME_MODE == "ROBOT_VS_ROBOT"
                        and (event.key == pygame.K_y or
                             (event.key == pygame.K_v and self_play.status.value == "pick_paused"))):
                    self_play.retry_visual_pick(source="V" if event.key == pygame.K_v else "Y")
                    continue
                if event.key == pygame.K_F5 and not state.physical_sync_fault and not state.move_sync_error:
                    state.ai_retry_requested = True
                elif (event.key == pygame.K_F6 and config.GAME_MODE == "ROBOT_VS_ROBOT"
                      and self_play is not None and not state.ai_thinking):
                    difficulty = getattr(config, "AI_DIFFICULTY", "medium")
                    hw.motion_worker.start(lambda: self_play.start(difficulty, difficulty, run_mode="continuous"), _job_completed)
                elif event.key == pygame.K_F7 and self_play is not None:
                    self_play.request_next_move()
                elif event.key == pygame.K_F8 and self_play is not None:
                    self_play.end_match()
                elif self_play is not None and self_play.recovery_input_allowed:
                    if event.key in (pygame.K_v, pygame.K_F4, pygame.K_1, pygame.K_2, pygame.K_F12):
                        input_mgr.handle_keyboard(event.key)
                elif self_play is None or not self_play.human_input_disabled:
                    input_mgr.handle_keyboard(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if hw.motion_worker.busy:
                    continue
                if self_play is not None and self_play.status.value == "pick_paused":
                    from src.ui.board_renderer import BoardRenderer, BTN_SCAN_FEN_RECT
                    render_state = state.get_render_state()
                    retry_rect = BoardRenderer.client_continue_rect(render_state)
                    if retry_rect.collidepoint(event.pos) or BTN_SCAN_FEN_RECT.collidepoint(event.pos):
                        self_play.retry_visual_pick(source=("V" if BTN_SCAN_FEN_RECT.collidepoint(event.pos) else "CONTINUE"))
                        continue
                if self_play is not None and self_play.recovery_input_allowed:
                    from src.ui.board_renderer import BoardRenderer
                    render_state = state.get_render_state()
                    controls_visible = not render_state.get('game_over', False)
                    actions = BoardRenderer.client_action_controls(render_state) if controls_visible else ()
                    recovery_hit = any(rect.collidepoint(event.pos) for rect, key, _labels, _color in actions
                                       if key in (pygame.K_v, pygame.K_F12))
                    can_continue = (controls_visible and bool(render_state.get('snapshot_continue_required')
                                    or render_state.get('visual_pick_retry')
                                    or render_state.get('test_pick_retry')))
                    continue_hit = (can_continue and
                                    BoardRenderer.client_continue_rect(render_state, actions).collidepoint(event.pos))
                    if BTN_NEW_GAME_RECT.collidepoint(event.pos) or recovery_hit or continue_hit:
                        input_mgr.handle_mouse_down(event.pos[0], event.pos[1])
                    continue
                if self_play is not None and self_play.human_input_disabled:
                    from src.ui.board_renderer import BTN_CONFIRM_MOVE_RECT, BTN_SURRENDER_RECT
                    if BTN_CONFIRM_MOVE_RECT.collidepoint(event.pos):
                        self_play.request_next_move()
                    elif BTN_SURRENDER_RECT.collidepoint(event.pos):
                        # Accept the click during thinking/motion. The controller
                        # commits an in-flight piece before recording resignation.
                        if self_play.accepts_surrender:
                            winner = 'b' if state.turn == 'r' else 'r'
                            self_play.request_surrender(winner='BLACK' if winner == 'b' else 'RED')
                elif input_mgr is not None:
                    input_mgr.handle_mouse_down(event.pos[0], event.pos[1])

        if not running:
            break
        startup_worker.poll()
        if hw is not None:
            hw.motion_worker.poll()
            pvp = getattr(hw, "pvp_controller", None)
            if pvp is not None:
                pvp.tick()
        if self_play is not None and not mode_switching and not mode_switch_failed:
            self_play.finish_recovery()
        if self_play is not None and not mode_switching and not mode_switch_failed:
            self_play.tick()
        if session_control is not None and not mode_switching and not mode_switch_failed:
            control_action = session_control.poll()
            if control_action == "quit":
                running = False
                break
            if control_action == "home":
                _begin_mode_disposal()
        if quit_requested and (session_control is None or mode_switch_failed) and not startup_worker.busy:
            running = False
            break

        # 2c. Camera Feed update
        if not mode_switching and not mode_switch_failed and hw is not None and hw.cam_monitor is not None:
            key = hw.cam_monitor.update_display()
            if key == ord("q"):
                if confirm_exit():
                    exit_application()
                    running = False
                    break

        # Inspect the board itself rather than the object moving a piece.
        # SPACE remains the safe manual fallback when camera confidence is poor.
        if (getattr(config, "AUTO_MOVE_CONFIRM_ENABLED", False)
                and not mode_switching and not mode_switch_failed
                and input_mgr is not None and not home_screen_active and not settings_menu_active
                and not difficulty_menu_active and state.is_human_turn and not state.game_over
                and (self_play is None or not self_play.human_input_disabled)):
            input_mgr.poll_board_stability()

        # 2d. Xử lý AI Turn (Non-blocking)
        if (hw is not None and input_mgr is not None and not home_screen_active and not settings_menu_active
                and not mode_switching and not mode_switch_failed
                and hw.is_robot_ready
                and not difficulty_menu_active and state.turn == "b" and not state.game_over
                and config.GAME_MODE == "HUMAN_VS_ROBOT"
                and not hw.motion_worker.busy and not getattr(state, "visual_pick_retry", None)
                and not state.physical_sync_fault and not state.move_sync_error
                and not state.emergency_mode and not state.manual_override_active
                and (self_play is None or not self_play.human_input_disabled)):
            
            # --- Khởi động Thread suy nghĩ ---
            if state.can_start_ai_turn():
                board_snapshot = [row[:] for row in state.board]
                state.mark_ai_turn_started()
                ai_job_token = (state.game_epoch, state.ai_epoch, state.human_commit_generation)
                state.ai_job_token = ai_job_token
                state.ai_thinking = True
                state.ai_think_start = time.time()
                
                def _ai_worker(job_token, snapshot):
                    # Đã loại bỏ truyền difficulty, AI Controller sẽ tự handle sức mạnh cố định
                    try:
                        state.ai_results[job_token] = hw.ai_ctrl.pick_move(snapshot, color="b")
                    except Exception as exc:
                        print(f"[AI] Engine error: {exc}")
                        state.ai_results[job_token] = None
                    
                state.ai_thread = threading.Thread(target=_ai_worker, args=(ai_job_token, board_snapshot), daemon=True)
                state.ai_thread.start()
                print("[AI] 🧵 Thinking thread started...")

            # --- Chờ Thread xong ---
            elif state.ai_thinking and state.ai_thread is not None:
                if not state.ai_thread.is_alive():
                    state.ai_thinking = False
                    state.ai_thread = None
                    completed_token = state.ai_job_token
                    best = state.ai_results.pop(completed_token, None)
                    state.ai_result = None
                    result_is_current = completed_token == (state.game_epoch, state.ai_epoch, state.human_commit_generation)
                    if not result_is_current:
                        print("[AI] Discarded stale worker result.")
                        best = None
                    
                    # Chống Loop
                    if best:
                        try: s, d = best
                        except: s, d = best[0], best[1]
                        if len(state.move_history) > 8:
                            last_srcs = [m['src'] for m in state.move_history[-6:]]
                            if last_srcs.count(s) >= 3:
                                print(f"⚠️ AI LOOP DETECTED {xiangqi.format_move(s, d)} -> PANIC MODE!")
                                valid_moves = xiangqi.find_all_valid_moves("b", state.board)
                                if valid_moves:
                                    best = random.choice(valid_moves)
                                    s, d = best

                    if best:
                        try: s, d = best
                        except: s, d = best[0], best[1]
                        if getattr(config, "VISUAL_MOTION_ASYNC_ENABLED", True):
                            move_for_job = best
                            def completed(committed, error):
                                if error:
                                    state.set_status(f"Motion worker failed: {error}", duration=30)
                                    return
                                if committed:
                                    try:
                                        state.publish_committed_fen()
                                        if (xiangqi.get_king_pos(state.turn, state.board) is None
                                                or not xiangqi.find_all_valid_moves(state.turn, state.board)):
                                            state.handle_game_over("b")
                                            state.publish_match_end(winner="BLACK", reason="CHECKMATE")
                                        else:
                                            if not state.physical_sync_fault and not state.move_sync_error:
                                                hw.motion_worker.start(_refresh_game_baseline, _job_completed)
                                                state.set_status("Your turn!", duration=8)
                                    except Exception as exc:
                                        state.set_status(f"Move committed; API/baseline failed: {exc}", duration=30)
                            hw.motion_worker.start(lambda: execute_ai_move(state, hw, move_for_job, config.DRY_RUN,
                                                    getattr(config, "VISUAL_PICK_ENABLED", False)), completed)
                            committed = False
                        else:
                            committed = execute_ai_move(state, hw, best, config.DRY_RUN,
                                                        getattr(config, "VISUAL_PICK_ENABLED", False))
                        if committed:
                            state.publish_committed_fen()
                            if xiangqi.get_king_pos(state.turn, state.board) is None or not xiangqi.find_all_valid_moves(state.turn, state.board):
                                state.handle_game_over("b")
                                state.publish_match_end(winner="BLACK", reason="CHECKMATE")
                            else:
                                hw.capture_baseline_if_needed(force_delay=0.0)
                                state.set_status("Your turn! F6: self-play, F7: next, F8: stop", duration=8)
                    elif result_is_current:
                        if not xiangqi.find_all_valid_moves("b", state.board):
                            state.handle_game_over("r")
                            state.publish_match_end(winner="RED", reason="CHECKMATE")
                        else:
                            state.set_status("Engine failed; board unchanged. Check engine, then F5 to retry.", duration=30)

        game_window.present()
        frame_duration = time.monotonic() - frame_started
        if frame_duration > 0.25 and frame_started - last_ui_lag_warning >= 10:
            last_ui_lag_warning = frame_started
            log_event("ui.slow_frame", "Giao diện xử lý chậm; kiểm tra camera, AI hoặc API đang chờ.",
                      level=logging.WARNING, duration_ms=round(frame_duration * 1000),
                      motion_busy=hw.motion_worker.busy if hw else False)
        clock.tick(30)

except (KeyboardInterrupt, SystemExit) as exc:
    print("\n[MAIN] ⛔ Interrupted.")
    if confirm_exit():
        exit_application()
    else:
        _recover_shutdown_after_exception(exc)
except Exception as e:
    log_event("app.unhandled", str(e), level=logging.CRITICAL, code="APP_UNHANDLED", exc_info=True)
    _recover_shutdown_after_exception(e)
finally:
    signal.signal(signal.SIGINT, _previous_sigint_handler)
    while not _cleanup_all():
        _recover_shutdown_after_exception(
            RuntimeError("Session resources not fully closed"), cleanup_retry=True)
