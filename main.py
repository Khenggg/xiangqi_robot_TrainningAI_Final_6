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
from src.core.ai_execution import execute_ai_move  # type: ignore
from src.hardware.hardware_manager import HardwareManager  # type: ignore
from src.ui.input_handler import InputHandler  # type: ignore

# ==========================================
# 0. CHẾ ĐỘ & DỌN DẸP TIẾN TRÌNH CŨ
# ==========================================
_mode_label = '🛠️ DRY RUN (MOUSE & LOG)' if config.DRY_RUN else '🤖 REAL RUN (CAMERA & ROBOT)'
print(f"\n=== MODE: {_mode_label} ===")

def _kill_zombie_processes():
    for proc_name in ['moonfish*', 'Pikafish*']:
        try:
            result = subprocess.run(
                ['tasklist', '/FI', f'IMAGENAME eq {proc_name}', '/FO', 'CSV', '/NH'],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip() and ('moonfish' in result.stdout.lower() or 'pikafish' in result.stdout.lower()):
                print(f"[CLEANUP] ⚠️ Phát hiện {proc_name} zombie process — đang kill...")
                subprocess.run(['taskkill', '/F', '/IM', proc_name], capture_output=True, timeout=5)
                print(f"[CLEANUP] ✅ Killed zombie {proc_name} processes.")
                time.sleep(0.3)
        except Exception as e:
            print(f"[CLEANUP] ⚠️ Không thể kiểm tra zombie processes: {e}")

_kill_zombie_processes()

# ==========================================
# 1. KHỞI TẠO HỆ THỐNG CỐT LÕI
# ==========================================
pygame.init()
pygame.font.init()

from src.core.self_play_controller import SelfPlayController, SelfPlayStatus  # type: ignore
from src.ui.board_renderer import (
    BoardRenderer,
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    BTN_NEW_GAME_RECT,
    BTN_SELF_PLAY_TOGGLE_RECT,
)  # type: ignore
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption(f"Xiangqi Robot VIP - { _mode_label }")
renderer = BoardRenderer(screen)
renderer.draw_ui({})
pygame.display.flip()
pygame.event.pump()

# Khởi tạo các module quản lý SRP
hw = HardwareManager(config, _BASE_DIR).initialize_all()

# Cấp nguồn servo và cấu hình chế độ tự động cho robot thật sau khi đã calibrate thành công
if not config.DRY_RUN and getattr(config, "ROBOT_BACKEND", "VIRTUAL").upper() == "PHYSICAL":
    print("\n[MAIN] ⚡ Đang cấp nguồn servo cánh tay robot FR3 (RobotEnable & Mode 0)...")
    try:
        hw.set_operational_mode(0)
        if not hw.enable_robot():
            print("⚠️ [MAIN] CẢNH BÁO: Không thể cấp nguồn cho robot FR3! Vui lòng kiểm tra nút E-Stop hoặc nguồn tủ điện.")
        else:
            print("✅ [MAIN] Robot FR3 đã sẵn sàng chấp hành chuyển động (MOTION AUTHORIZED)!")
    except Exception as e:
        print(f"⚠️ [MAIN] Lỗi khi kích hoạt robot FR3: {e}")

state = GameState(allow_mouse_move=config.DRY_RUN)
renderer.draw_ui(state.get_render_state())
renderer.draw_pieces(state.board)
pygame.display.flip()
pygame.event.pump()
if hw.ai_ctrl:
    state.ai_elo, state.ai_elo_title = hw.ai_ctrl.get_elo_info()
input_mgr = InputHandler(state, hw)
self_play_ctrl = None

# 3D Digital Twin WebSocket Telemetry & Live Synchronization
telemetry = None
target_port = int(getattr(config, "TELEMETRY_PORT", 8765))
try:
    from src.hardware.telemetry_publisher import TelemetryPublisher
    try:
        telemetry = TelemetryPublisher.get_instance(
            host="127.0.0.1",
            port=target_port,
            robot_model="FR3",
        )
        telemetry.start()
    except Exception as e_port:
        if "10048" in str(e_port) or "address already in use" in str(e_port).lower():
            fallback_port = target_port + 1
            print(f"[MAIN] ⚠️ Cổng {target_port} bị bận -> Thử cổng dự phòng ws://127.0.0.1:{fallback_port}...")
            TelemetryPublisher._instance = None
            telemetry = TelemetryPublisher.get_instance(
                host="127.0.0.1",
                port=fallback_port,
                robot_model="FR3",
            )
            telemetry.start()
        else:
            raise e_port
    print(f"[MAIN] 🌐 3D Digital Twin Telemetry Publisher started on ws://127.0.0.1:{telemetry.port}")
except Exception as e:
    print(f"[MAIN] ⚠️ Could not start TelemetryPublisher: {e}")
    telemetry = None

# Connect Digital Twin & Move Observer
twin = hw.setup_digital_twin(telemetry=telemetry)
if twin is not None:
    state.set_move_observer(hw.reconcile_human_move)
    state.set_board_observer(hw.reconcile_board)
    if hw.reconcile_new_game():
        state.clear_move_sync_error()
    print("[MAIN] 🪞 Digital Twin live reconciliation & move observer activated!")


dashboard = None
if getattr(config, "ENABLE_DEBUG_DASHBOARD", False):
    try:
        from src.ui.debug_dashboard import DebugDashboard
        dashboard = DebugDashboard(dry_run=config.DRY_RUN, backend=hw.backend, robot=hw.robot)
    except Exception as e:
        print(f"[MAIN] ⚠️ Could not initialize DebugDashboard: {e}")

def _cleanup_all():
    print("\n[CLEANUP] Đang dọn dẹp hệ thống...")
    if dashboard is not None:
        try: dashboard.close()
        except: pass
    if telemetry is not None:
        try: telemetry.stop()
        except: pass
    if self_play_ctrl is not None:
        try: self_play_ctrl.end_match()
        except: pass
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

try:
    print(f"\n[GAME] === GAME STARTED ===")
    print(f"[FEN] {state.current_fen}")

    hw.capture_baseline_if_needed(force_delay=1.0)

    # [API] Bắt đầu khởi tạo trận đấu truyền hình trực tiếp
    if not config.DRY_RUN:
        state.api_client.create_match(red_name="Người chơi Thật", black_name="Robot AI")

    while running:
        # 2a. Vẽ khung hình
        ui_state = state.get_render_state()
        renderer.draw_ui(ui_state)
        renderer.draw_pieces(state.board)
        renderer.draw_highlight(
            last_move=state.last_move,
            selected_pos=state.selected_pos,
            invalid_flash_pos=state.invalid_flash_pos,
            invalid_flash_expiry=state.invalid_flash_expiry,
            legal_moves=ui_state.get("legal_moves"),
            board=state.board,
            is_check=ui_state.get("is_check", False),
            turn=state.turn,
            hint_move=ui_state.get("hint_move"),
        )
        if state.game_over:
            renderer.draw_game_over(state.winner, getattr(state, "game_over_reason", "CHIẾU BÍ"))
        if self_play_ctrl is not None:
            renderer.draw_self_play_controls(self_play_ctrl)

        # 2b. Xử lý Input
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if (state.turn_confirmation_required
                        and event.key in (pygame.K_1, pygame.K_KP1, pygame.K_2, pygame.K_KP2)):
                    input_mgr.handle_keyboard(event.key)
                elif self_play_ctrl is not None and self_play_ctrl.human_input_disabled:
                    if event.key == pygame.K_n:
                        self_play_ctrl.request_next_move()
                    elif event.key == pygame.K_e:
                        self_play_ctrl.end_match()
                    elif event.key == pygame.K_c:
                        self_play_ctrl.set_run_mode("continuous")
                    elif event.key == pygame.K_s:
                        self_play_ctrl.set_run_mode("step")
                    elif event.key == pygame.K_r:
                        if self_play_ctrl.status in {SelfPlayStatus.FAULTED, SelfPlayStatus.ENDED}:
                            self_play_ctrl.start(
                                red_difficulty=self_play_ctrl.red_difficulty or "medium",
                                black_difficulty=self_play_ctrl.black_difficulty or "medium",
                                run_mode=self_play_ctrl.run_mode,
                            )
                        else:
                            self_play_ctrl.end_match()
                else:
                    if event.key == pygame.K_r:
                        print("[MAIN] 🤖 Bắt đầu chế độ Tự đấu 2 AI (Self-Play Robot vs Robot)...")
                        self_play_ctrl = SelfPlayController(state, hw)
                        if not self_play_ctrl.start(run_mode="continuous"):
                            print(f"[MAIN] ⚠️ Không thể khởi động Self-Play: {state.status_message}")
                    else:
                        input_mgr.handle_keyboard(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if self_play_ctrl is not None and self_play_ctrl.human_input_disabled:
                    if (self_play_ctrl.status in {SelfPlayStatus.ENDED, SelfPlayStatus.FINISHED}
                            and BTN_NEW_GAME_RECT.collidepoint(event.pos)):
                        state.reset_game(hw)
                        self_play_ctrl = None
                    elif event.pos[0] < 160 and event.pos[1] > SCREEN_HEIGHT - 70:
                        self_play_ctrl.request_next_move()
                    elif (SCREEN_WIDTH // 2 - 100 < event.pos[0] < SCREEN_WIDTH // 2 + 100
                          and event.pos[1] > SCREEN_HEIGHT - 70):
                        self_play_ctrl.set_run_mode(
                            "continuous" if self_play_ctrl.run_mode == "step" else "step"
                        )
                    elif event.pos[0] > SCREEN_WIDTH - 160 and event.pos[1] > SCREEN_HEIGHT - 70:
                        self_play_ctrl.end_match()
                else:
                    if (self_play_ctrl is None or not self_play_ctrl.active) and BTN_SELF_PLAY_TOGGLE_RECT.collidepoint(event.pos) and not getattr(state, "manual_override_active", False):
                        print("[MAIN] 🤖 Bắt đầu chế độ Tự đấu 2 AI (Self-Play Robot vs Robot)...")
                        self_play_ctrl = SelfPlayController(state, hw)
                        if not self_play_ctrl.start(run_mode="continuous"):
                            print(f"[MAIN] ⚠️ Không thể khởi động Self-Play: {state.status_message}")
                    else:
                        input_mgr.handle_mouse_down(event.pos[0], event.pos[1])

        # 2c. Camera Feed update
        if hw.cam_monitor is not None:
            key = hw.cam_monitor.update_display()
            if key == ord("q"): running = False

        # Autonomous Self-Play tick
        if self_play_ctrl is not None:
            self_play_ctrl.tick()

        # Automatic Board Stability & Move Detection (Visual-Correction flow)
        if (self_play_ctrl is None or not self_play_ctrl.active):
            if state.is_human_turn and not state.game_over and getattr(config, "AUTO_MOVE_CONFIRM_ENABLED", False):
                # 1. Primary: Direct board state stability monitor from camera
                input_mgr.poll_board_stability()

                # 2. Hand-interaction event fallback if hand model is active
                if getattr(hw, "hand_model", None) is not None and hw.hand_interaction_finished():
                    input_mgr.try_auto_confirm_move(
                        retries=getattr(config, "AUTO_MOVE_CONFIRM_RETRIES", 10),
                        retry_seconds=getattr(config, "AUTO_MOVE_CONFIRM_RETRY_SECONDS", 0.2),
                    )

        # 2d. Xử lý AI Turn (Non-blocking) - Chế độ Người vs AI
        if (config.GAME_MODE == "HUMAN_VS_ROBOT"
                and (self_play_ctrl is None or not self_play_ctrl.human_input_disabled)
                and state.turn == "b" and not state.game_over
                and not state.move_sync_error and not state.physical_sync_fault):
            
            # --- Khởi động Thread suy nghĩ ---
            if not state.ai_thinking and state.ai_thread is None:
                board_snapshot = [row[:] for row in state.board]
                state.ai_thinking = True
                state.ai_think_start = time.time()
                
                def _ai_worker():
                    # Đã loại bỏ truyền difficulty, AI Controller sẽ tự handle sức mạnh cố định
                    state.ai_result = hw.ai_ctrl.pick_move(board_snapshot, color="b")
                    
                state.ai_thread = threading.Thread(target=_ai_worker, daemon=True)
                state.ai_thread.start()
                print("[AI] 🧵 Thinking thread started...")

            # --- Chờ Thread xong ---
            elif state.ai_thinking and state.ai_thread is not None:
                if not state.ai_thread.is_alive():
                    state.ai_thinking = False
                    state.ai_thread = None
                    best = state.ai_result
                    state.ai_result = None
                    
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
                        exec_ok = execute_ai_move(
                            state=state,
                            hw=hw,
                            best_move=best,
                            dry_run=bool(config.DRY_RUN),
                            visual_pick_enabled=bool(getattr(config, "VISUAL_PICK_ENABLED", False)),
                        )
                        if not exec_ok:
                            print(f"[AI] ⚠️ execute_ai_move không thành công. Giữ nguyên trạng thái để thử lại sau hoặc chờ người can thiệp.")
                            time.sleep(1.0)
                    else:
                        is_chk = xiangqi.is_king_in_check("b", state.board)
                        reason = "CHIẾU BÍ" if is_chk else "TUYỆT SÁT"
                        print(f"[AI] No moves available ({reason}) -> AI Lost")
                        state.handle_game_over("r", reason=reason)
                        state.api_client.end_match(winner="RED", reason="CHECKMATE")

        pygame.display.flip()
        clock.tick(30)

except (KeyboardInterrupt, SystemExit):
    print("\n[MAIN] ⛔ Interrupted.")
except Exception as e:
    print(f"\n[MAIN] ❌ Unexpected error: {e}")
    traceback.print_exc()
