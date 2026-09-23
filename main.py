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
from src.hardware.hardware_manager import HardwareManager  # type: ignore
from src.ui.input_handler import InputHandler  # type: ignore

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
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption(f"Xiangqi Robot VIP - { _mode_label }")
renderer = BoardRenderer(screen)

# Khởi tạo các module quản lý SRP
hw = HardwareManager(config, _BASE_DIR).initialize_all()
state = GameState(allow_mouse_move=config.DRY_RUN)
input_mgr = InputHandler(state, hw)
difficulty_menu_active = True
difficulty_menu_message = ""

def _start_selected_game():
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
    hw.cleanup()
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

# Khởi chạy main loop.  The first game starts only after difficulty selection.
try:
    while running:
        # 2a. Vẽ khung hình
        renderer.draw_ui(state.get_render_state())
        renderer.draw_pieces(state.board)
        renderer.draw_highlight(state.last_move, state.selected_pos, state.invalid_flash_pos, state.invalid_flash_expiry)
        if state.game_over:
            renderer.draw_game_over(state.winner)
        if difficulty_menu_active:
            renderer.draw_difficulty_menu(hw.difficulty_availability(), difficulty_menu_message)

        # 2b. Xử lý Input
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
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
                input_mgr.handle_keyboard(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                input_mgr.handle_mouse_down(event.pos[0], event.pos[1])

        # 2c. Camera Feed update
        if hw.cam_monitor is not None:
            key = hw.cam_monitor.update_display()
            if key == ord("q"): running = False

        # Inspect the board itself rather than the object moving a piece.
        # SPACE remains the safe manual fallback when camera confidence is poor.
        if (getattr(config, "AUTO_MOVE_CONFIRM_ENABLED", False)
                and not difficulty_menu_active and state.turn == "r" and not state.game_over):
            input_mgr.poll_board_stability()

        # 2d. Xử lý AI Turn (Non-blocking)
        if (not difficulty_menu_active and state.turn == "b" and not state.game_over
                and not state.physical_sync_fault):
            
            # --- Khởi động Thread suy nghĩ ---
            if (not state.ai_thinking and state.ai_thread is None
                    and state.human_commit_generation
                    > state.ai_started_for_human_commit_generation):
                board_snapshot = [row[:] for row in state.board]
                state.ai_started_for_human_commit_generation = state.human_commit_generation
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
                                print(f"⚠️ AI LOOP DETECTED ({s}->{d}) -> PANIC MODE!")
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
                                print(f"[AI] Robot executing move: {s}->{d}")
                                try:
                                    pick_targets = {"moving": None, "captured": None}
                                    # CChess creates the calibration matrix; best.pt measures
                                    # the physical box centre used for each robot pick.
                                    expected_cells = {"captured": d} if is_cap else {"moving": s}
                                    if getattr(config, "VISUAL_PICK_ENABLED", False):
                                        pick_targets = hw.get_robot_center_pick_targets(expected_cells)
                                    if robot_success:
                                        def refresh_moving_target():
                                            if not is_cap:
                                                return pick_targets.get("moving")
                                            refreshed = hw.get_robot_center_pick_targets({"moving": s})
                                            return refreshed.get("moving")

                                        def verify_capture_cleared():
                                            return not is_cap or hw.is_cell_visually_clear(d)

                                        hw.robot.move_piece(
                                            s[0], s[1], d[0], d[1], is_cap,
                                            moving_visual_target=pick_targets.get("moving"),
                                            captured_visual_target=pick_targets.get("captured"),
                                            refresh_moving_visual_target=refresh_moving_target,
                                            verify_capture_cleared=verify_capture_cleared,
                                        )
                                        # Confirm the observed source->destination geometry. CChess
                                        # identity/FEN is deliberately not a robot-motion gate.
                                        if getattr(config, "VISUAL_PICK_ENABLED", False):
                                            if not hw.verify_visual_move(s, d):
                                                robot_success = False
                                                state.physical_sync_fault = True
                                                state.set_status(
                                                    "⚠️ Không xác nhận được vị trí quân sau khi thả — FEN chưa được cập nhật.",
                                                    color=(180, 100, 0), duration=20.0,
                                                )
                                except Exception as e:
                                    error_str = str(e)
                                    print(f"⚠️ Robot error: {error_str}")
                                    if "112" in error_str or "MoveCart" in error_str:
                                        print("[ROBOT] Recoverable motion error; camera verification is required before FEN commit.")
                                    else:
                                        print("❌ [CRITICAL] Robot critical error, stopping game.")
                                        robot_success = False
                                        state.physical_sync_fault = True
                                        time.sleep(2)
                            else:
                                print(f"\n{'='*50}")
                                print(f"🤖 AI đi: {state.board[s[1]][s[0]]} ({s[0]},{s[1]}) → ({d[0]},{d[1]}) {'ĂN' if is_cap else ''}")
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

        pygame.display.flip()
        clock.tick(30)

except (KeyboardInterrupt, SystemExit):
    print("\n[MAIN] ⛔ Interrupted.")
except Exception as e:
    print(f"\n[MAIN] ❌ Unexpected error: {e}")
    traceback.print_exc()
