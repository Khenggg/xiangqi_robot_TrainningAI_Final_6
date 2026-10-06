# ===================================================================================
# === FILE: main.py (CLEAN ARCHITECTURE) ===
# ===================================================================================
import sys
import os

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
import pygame  # type: ignore

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE_DIR)

import config  # type: ignore
from src.core import xiangqi  # type: ignore

from src.core.game_state import GameState  # type: ignore
from src.core.visual_move_coordinator import execute_pending_ai_motion
from src.vision.pick_consensus import PickTargetUnavailable
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

_kill_zombie_processes()

# ==========================================
# 1. KHỞI TẠO HỆ THỐNG CỐT LÕI
# ==========================================
pygame.init()
pygame.font.init()

from src.ui.board_renderer import BoardRenderer, SCREEN_WIDTH, SCREEN_HEIGHT  # type: ignore
# Keep the UI authored at its original canvas size, then present it a little
# smaller so the full client fits on more displays without rearranging controls.
DISPLAY_SCALE = 0.9
WINDOW_WIDTH = round(SCREEN_WIDTH * DISPLAY_SCALE)
WINDOW_HEIGHT = round(SCREEN_HEIGHT * DISPLAY_SCALE)
window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption(f"Xiangqi Robot VIP - { _mode_label }")
renderer = BoardRenderer(screen)


def canvas_position(position):
    """Convert a click in the scaled window to the renderer's canvas space."""
    return (
        round(position[0] * SCREEN_WIDTH / WINDOW_WIDTH),
        round(position[1] * SCREEN_HEIGHT / WINDOW_HEIGHT),
    )

# Khởi tạo các module quản lý SRP
state = GameState(allow_mouse_move=config.DRY_RUN)
hw = None
input_mgr = None
difficulty_menu_active = False
home_screen_active = True
settings_menu_active = False
difficulty_menu_message = ""
debug_dashboard = None


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
    hw.capture_baseline_if_needed(force_delay=1.0)
    if not config.DRY_RUN:
        state.api_client.create_match(red_name="Người chơi Thật", black_name="Robot AI")

def _cleanup_all():
    print("\n[CLEANUP] Đang dọn dẹp hệ thống...")
    # [API] Force Kết thúc trận đấu khi thoát chương trình
    try:
        if state and state.api_client:
            state.api_client.end_match(reason="OTHER")
    except: pass
    if hw is not None:
        hw.cleanup()
    if debug_dashboard is not None:
        debug_dashboard.close()
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
            if event.type == pygame.QUIT:
                running = False
            elif home_screen_active:
                start_vs_robot = event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER)
                if event.type == pygame.MOUSEBUTTONDOWN:
                    start_vs_robot = renderer.home_action_from_pixel(*canvas_position(event.pos)) == "vs_robot"
                if start_vs_robot:
                    # Connecting to the robot and calibrating the camera can block, so defer
                    # both until the player explicitly chooses to play against the robot.
                    hw = HardwareManager(config, _BASE_DIR).initialize_all()
                    input_mgr = InputHandler(state, hw)
                    if debug_dashboard is not None:
                        debug_dashboard.robot = hw.robot
                        debug_dashboard.activity = "Game setup"
                    home_screen_active = False
                    difficulty_menu_active = True
                elif event.type == pygame.MOUSEBUTTONDOWN and renderer.home_action_from_pixel(*canvas_position(event.pos)) == "settings":
                    home_screen_active = False
                    settings_menu_active = True
            elif settings_menu_active:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    settings_menu_active = False
                    home_screen_active = True
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    action = renderer.settings_action_from_pixel(*canvas_position(event.pos))
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
                    choice = renderer.difficulty_from_pixel(*canvas_position(event.pos))
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
                input_mgr.handle_keyboard(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                input_mgr.handle_mouse_down(*canvas_position(event.pos))

        # 2c. Camera Feed update
        if hw is not None and hw.cam_monitor is not None:
            key = hw.cam_monitor.update_display()
            if key == ord("q"): running = False

        # Inspect the board itself rather than the object moving a piece.
        # SPACE remains the safe manual fallback when camera confidence is poor.
        if (getattr(config, "AUTO_MOVE_CONFIRM_ENABLED", False)
                and input_mgr is not None and not home_screen_active and not settings_menu_active
                and not difficulty_menu_active and state.turn == "r" and not state.game_over):
            input_mgr.poll_board_stability()

        # 2d. Xử lý AI Turn (Non-blocking)
        if (hw is not None and input_mgr is not None and not home_screen_active and not settings_menu_active
                and not difficulty_menu_active and state.turn == "b" and not state.game_over
                and not state.physical_sync_fault):
            
            # --- Khởi động Thread suy nghĩ ---
            if state.can_start_ai_turn():
                board_snapshot = [row[:] for row in state.board]
                state.mark_ai_turn_started()
                ai_job_token = (state.game_epoch, state.ai_epoch, state.human_commit_generation)
                state.ai_job_token = ai_job_token
                state.ai_thinking = True
                state.ai_think_start = time.time()
                
                def _ai_worker(job_token):
                    # Đã loại bỏ truyền difficulty, AI Controller sẽ tự handle sức mạnh cố định
                    state.ai_results[job_token] = hw.ai_ctrl.pick_move(board_snapshot, color="b")
                    
                state.ai_thread = threading.Thread(target=_ai_worker, args=(ai_job_token,), daemon=True)
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
                        cap_p = state.board[d[1]][d[0]]
                        is_cap = cap_p != "."
                        expected_after, _ = xiangqi.make_temp_move(state.board, best)
                        state.set_pending_ai_move(best, expected_after, cap_p)
                        expected_after_capture = None
                        if is_cap:
                            expected_after_capture = [row[:] for row in state.board]
                            expected_after_capture[d[1]][d[0]] = "."

                        robot_success = True
                        if not config.DRY_RUN:
                            if hw.robot.connected:
                                print(f"[AI] Robot executing move: {xiangqi.format_move(s, d)}")
                                try:
                                    execute_pending_ai_motion(state, hw, config)
                                except PickTargetUnavailable as exc:
                                    robot_success = False
                                    state.pause_visual_pick("ai", s, d, exc)
                                except Exception as e:
                                    # Even 112/MoveCart errors are NOT proof of completion.
                                    robot_success = False
                                    state.physical_sync_fault = True
                                    state.snapshot_continue_required = True
                                    state.snapshot_continue_can_commit_pending = False
                                    error_str = str(e)
                                    print(f"⚠️ Robot error: {error_str}")
                                    state.set_status(f"Robot dừng: {error_str}. Kiểm tra bàn thật rồi V; FEN giữ nguyên.",
                                                     color=(180, 0, 0), duration=3600)
                                    if "112" in error_str or "MoveCart" in error_str:
                                        print("[ROBOT] Recoverable motion error; camera verification is required before FEN commit.")
                                    else:
                                        print("❌ [CRITICAL] Robot critical error, stopping game.")
                                        time.sleep(2)
                            else:
                                print(f"\n{'='*50}")
                                print(f"🤖 AI đi: {state.board[s[1]][s[0]]} {xiangqi.format_move(s, d)} {'ĂN' if is_cap else ''}")
                                print(f"👉 Hãy di quân này trên bàn thật, rồi bấm SPACE!")
                                print(f"{'='*50}\n")

                        if robot_success:
                            state.commit_pending_ai_move()
                            print(f"[FEN] {state.current_fen}")
                            
                            # [API] Gửi cập nhật nước đi của AI lên Server
                            state.api_client.send_move_update_board(state.current_fen)
                            
                            if xiangqi.get_king_pos('r', state.board) is None:
                                state.handle_game_over('b')
                                state.api_client.end_match(winner="BLACK", reason="CHECKMATE")
                            else:
                                if hw.robot.connected:
                                    hw.capture_baseline_if_needed(force_delay=1.0)
                                    state.set_status("Your turn!", color=(0, 100, 180), duration=5.0)
                                else:
                                    hw.clear_yolo_baseline()
                                    state.set_status(f"🤖 AI: ({s[0]},{s[1]})→({d[0]},{d[1]}) | Di quân rồi SPACE", color=(0, 80, 160), duration=30.0)
                                print("[GAME] Your turn...")
                    elif result_is_current:
                        print("[AI] No moves available -> AI Lost")
                        state.handle_game_over("r")
                        state.api_client.end_match(winner="RED", reason="CHECKMATE")

        window.blit(pygame.transform.smoothscale(screen, (WINDOW_WIDTH, WINDOW_HEIGHT)), (0, 0))
        pygame.display.flip()
        clock.tick(30)

except (KeyboardInterrupt, SystemExit):
    print("\n[MAIN] ⛔ Interrupted.")
except Exception as e:
    print(f"\n[MAIN] ❌ Unexpected error: {e}")
    traceback.print_exc()
