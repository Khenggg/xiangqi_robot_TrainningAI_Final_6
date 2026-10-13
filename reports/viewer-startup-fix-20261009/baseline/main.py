# ===================================================================================
# === FILE: main.py (CLEAN ARCHITECTURE) ===
# ===================================================================================
import sys
import os
from src.core.launch_options import parse_options, configure_runtime, ViewerServer

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

from src.ui.board_renderer import BoardRenderer, SCREEN_WIDTH, SCREEN_HEIGHT  # type: ignore
from src.ui.game_window import GameWindow
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
difficulty_menu_active = False
home_screen_active = True
settings_menu_active = False
difficulty_menu_message = ""
debug_dashboard = None
viewer_server = None
physical_enable_pending = False
physical_enable_deadline = 0.0


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
    hw.capture_baseline_if_needed(force_delay=0.0)
    if config.ROBOT_BACKEND == "PHYSICAL" and not hw.is_robot_ready:
        state.set_status("FR3 chỉ đọc. Kiểm tra setup, bấm F9 rồi F10 để bật robot; F6 bắt đầu self-play.", duration=30)
    if config.GAME_MODE == "ROBOT_VS_ROBOT" and self_play is not None and hw.is_robot_ready:
        difficulty = getattr(config, "AI_DIFFICULTY", "medium")
        self_play.start(difficulty, difficulty, run_mode="step")
        state.set_status("Robot vs robot: F7 next move / F8 stop", duration=30)
    if not config.DRY_RUN:
        state.api_client.create_match(red_name="Người chơi Thật", black_name="Robot AI")

def _cleanup_all():
    log_event("app.cleanup", "Đang đóng game và các dịch vụ của phiên")
    print("\n[CLEANUP] Đang dọn dẹp hệ thống...")
    # [API] Force Kết thúc trận đấu khi thoát chương trình
    try:
        if state and state.api_client:
            state.api_client.end_match(reason="OTHER")
    except: pass
    if self_play is not None:
        self_play.close()
    if hw is not None:
        hw.cleanup()
    if telemetry is not None:
        telemetry.stop()
    if debug_dashboard is not None:
        debug_dashboard.close()
    if viewer_server is not None:
        viewer_server.close()
    try: pygame.quit()
    except: pass
    print("[CLEANUP] ✅ Xong!")

atexit.register(_cleanup_all)

# ==========================================
# 2. VÒNG LẶP CHÍNH
# ==========================================
running = True
clock = pygame.time.Clock()

print(f"\n[GAME] === GAME STARTED ===")
print(f"[FEN] {state.current_fen}")

# Khởi chạy main loop. The launcher keeps difficulty selection out of the boot flow.
try:
    while running:
        # 2a. Vẽ khung hình
        if settings_menu_active:
            renderer.draw_settings_menu(getattr(config, "DEBUG_DASHBOARD", False))
        elif home_screen_active:
            renderer.draw_home_screen()
        else:
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
            if event.type == pygame.QUIT:
                running = False
            elif (hw is not None and hw.motion_worker.busy
                  and event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN)):
                continue
            elif home_screen_active:
                home_action = None
                start_vs_robot = event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    home_action = renderer.home_action_from_pixel(event.pos[0], event.pos[1])
                    start_vs_robot = home_action in ("vs_robot", "self_play", "human_vs_human")
                if start_vs_robot:
                    config.GAME_MODE = {"self_play": "ROBOT_VS_ROBOT", "human_vs_human": "HUMAN_VS_HUMAN"}.get(home_action, "HUMAN_VS_ROBOT")
                    # Connecting to the robot and calibrating the camera can block, so defer
                    # both until the player explicitly chooses to play against the robot.
                    hw = HardwareManager(config, _BASE_DIR).initialize_all()
                    telemetry = TelemetryPublisher(host=config.TELEMETRY_HOST, port=config.TELEMETRY_PORT, robot_model="FR3")
                    bridge = hw.setup_digital_twin(telemetry)
                    if bridge is not None:
                        state.set_board_observer(hw.sync_committed_board)
                        state.sync_current_board()
                        telemetry.start()
                        if not launch_options.no_viewer and viewer_server is None:
                            try:
                                viewer_server = ViewerServer(_BASE_DIR, launch_options.viewer_port)
                                viewer_server.start(config.TELEMETRY_PORT)
                            except OSError as exc:
                                log_event("viewer.start_failed", str(exc), level=logging.ERROR,
                                      code="PORT_BUSY", port=launch_options.viewer_port, exc_info=True)
                                state.set_status(f"Viewer port unavailable: {exc}; use --viewer-port", duration=30)
                                print(f"[VIEWER] Could not start: {exc}")
                    self_play = SelfPlayController(state, hw)
                    input_mgr = InputHandler(state, hw)
                    if debug_dashboard is not None:
                        debug_dashboard.robot = hw.robot
                        debug_dashboard.backend = hw.backend
                        debug_dashboard.activity = "Game setup"
                    home_screen_active = False
                    difficulty_menu_active = config.GAME_MODE != "HUMAN_VS_HUMAN"
                    if not difficulty_menu_active:
                        _start_selected_game()
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
                    ok, reason = hw.select_difficulty(choice)
                    if ok:
                        difficulty_menu_active = False
                        difficulty_menu_message = ""
                        state.set_status(reason, color=(0, 110, 70), duration=6.0)
                        _start_selected_game()
                    else:
                        difficulty_menu_message = reason
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
                        hw.activate_physical_game(state, commissioned=True)
                        state.set_status("Robot đã được bật quyền chuyển động cho game.", duration=15)
                    except Exception as exc:
                        log_event("physical.enable_failed", str(exc), level=logging.ERROR,
                              code="PHYSICAL_ENABLE_FAILED", exc_info=True)
                        state.set_status(f"Không bật được robot: {exc}", duration=30)
                    continue
                if hw.motion_worker.busy:
                    continue
                if event.key == pygame.K_y and self_play is not None and self_play.status.value == "pick_paused":
                    self_play.retry_visual_pick()
                    continue
                if event.key == pygame.K_F5 and not state.physical_sync_fault and not state.move_sync_error:
                    state.ai_retry_requested = True
                elif event.key == pygame.K_F6 and self_play is not None and not state.ai_thinking:
                    difficulty = getattr(config, "AI_DIFFICULTY", "medium")
                    self_play.start(difficulty, difficulty, run_mode="step")
                elif event.key == pygame.K_F7 and self_play is not None:
                    self_play.request_next_move()
                elif event.key == pygame.K_F8 and self_play is not None:
                    self_play.end_match()
                elif self_play is None or not self_play.human_input_disabled:
                    input_mgr.handle_keyboard(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if hw.motion_worker.busy:
                    continue
                from src.ui.board_renderer import BTN_CONTINUE_RECT
                if (self_play is not None and self_play.status.value == "pick_paused"
                        and BTN_CONTINUE_RECT.collidepoint(event.pos)):
                    self_play.retry_visual_pick()
                    continue
                if self_play is not None and self_play.human_input_disabled:
                    from src.ui.board_renderer import BTN_CONFIRM_MOVE_RECT, BTN_SURRENDER_RECT
                    if BTN_CONFIRM_MOVE_RECT.collidepoint(event.pos):
                        self_play.request_next_move()
                    elif BTN_SURRENDER_RECT.collidepoint(event.pos):
                        # End only at a completed move boundary; do not invalidate
                        # the board while a robot worker is moving a piece.
                        if self_play.accepts_next:
                            self_play.end_match()
                            winner = 'b' if state.turn == 'r' else 'r'
                            state.handle_game_over(winner, reason='RESIGN')
                            state.api_client.end_match(winner='BLACK' if winner == 'b' else 'RED', reason='RESIGN')
                elif input_mgr is not None:
                    input_mgr.handle_mouse_down(event.pos[0], event.pos[1])

        if not running:
            break
        if hw is not None:
            hw.motion_worker.poll()
        if self_play is not None:
            self_play.tick()

        # 2c. Camera Feed update
        if hw is not None and hw.cam_monitor is not None:
            key = hw.cam_monitor.update_display()
            if key == ord("q"): running = False

        # Inspect the board itself rather than the object moving a piece.
        # SPACE remains the safe manual fallback when camera confidence is poor.
        if (getattr(config, "AUTO_MOVE_CONFIRM_ENABLED", False)
                and input_mgr is not None and not home_screen_active and not settings_menu_active
                and not difficulty_menu_active and state.is_human_turn and not state.game_over
                and (self_play is None or not self_play.human_input_disabled)):
            input_mgr.poll_board_stability()

        # 2d. Xử lý AI Turn (Non-blocking)
        if (hw is not None and input_mgr is not None and not home_screen_active and not settings_menu_active
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
                        if hw.simulation_runtime is None and getattr(config, "VISUAL_MOTION_ASYNC_ENABLED", True):
                            move_for_job = best
                            def completed(committed, error):
                                if error:
                                    state.set_status(f"Motion worker failed: {error}", duration=30)
                                    return
                                if committed:
                                    try:
                                        state.api_client.send_move_update_board(state.current_fen)
                                        if (xiangqi.get_king_pos(state.turn, state.board) is None
                                                or not xiangqi.find_all_valid_moves(state.turn, state.board)):
                                            state.handle_game_over("b")
                                        else:
                                            hw.capture_baseline_if_needed(force_delay=0)
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
                            state.api_client.send_move_update_board(state.current_fen)
                            if xiangqi.get_king_pos(state.turn, state.board) is None or not xiangqi.find_all_valid_moves(state.turn, state.board):
                                state.handle_game_over("b")
                            else:
                                hw.capture_baseline_if_needed(force_delay=0.0)
                                state.set_status("Your turn! F6: self-play, F7: next, F8: stop", duration=8)
                    elif result_is_current:
                        if not xiangqi.find_all_valid_moves("b", state.board):
                            state.handle_game_over("r")
                            state.api_client.end_match(winner="RED", reason="CHECKMATE")
                        else:
                            state.set_status("Engine failed; board unchanged. Check engine, then F5 to retry.", duration=30)

        game_window.present()
        clock.tick(30)

except (KeyboardInterrupt, SystemExit):
    print("\n[MAIN] ⛔ Interrupted.")
except Exception as e:
    log_event("app.unhandled", str(e), level=logging.CRITICAL, code="APP_UNHANDLED", exc_info=True)
