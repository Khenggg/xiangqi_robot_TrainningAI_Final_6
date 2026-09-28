# =============================================================================
# === FILE: input_handler.py ===
# === Quản lý sự kiện Chuột & Bàn phím với trải nghiệm chuẩn App Cờ Tướng ===
# =============================================================================
import time
import threading
import pygame
from typing import Optional, Tuple
from src.core import xiangqi
from src.ui.board_renderer import (
    BoardRenderer,
    BTN_SURRENDER_RECT,
    BTN_NEW_GAME_RECT,
    BTN_UNDO_RECT,
    BTN_HINT_RECT,
    ELO_BUTTON_RECTS,
    BTN_ELO_PREV_RECT,
    BTN_ELO_NEXT_RECT,
    NUM_COLS,
    NUM_ROWS,
)
from src.vision.move_observation import MoveObservation, derive_move_observation


class InputHandler:
    """Manages Pygame Key/Mouse events and bridges them to GameState and HardwareManager."""

    def __init__(self, game_state, hw_manager):
        self.state = game_state
        self.hw = hw_manager

    # =========================================================================
    # 1. XỬ LÝ CHUỘT (MOUSE INPUT - CLICK BUTTONS & CLICK-TO-MOVE)
    # =========================================================================
    def handle_mouse_down(self, mx: int, my: int):
        # 1. Nút Xin đi lại (Undo Round)
        if BTN_UNDO_RECT.collidepoint(mx, my):
            self.state.undo_round(self.hw)
            return

        # 2. Nút Gợi ý nước đi (Hint)
        if BTN_HINT_RECT.collidepoint(mx, my):
            self._handle_hint()
            return

        # 3. Nút Ván mới (New Game)
        if BTN_NEW_GAME_RECT.collidepoint(mx, my):
            self.state.reset_game(self.hw)
            return

        # 4. Nút Xin thua (Surrender / Resign)
        if BTN_SURRENDER_RECT.collidepoint(mx, my):
            self._handle_surrender()
            return

        # 5. Nút Giảm ELO [-]
        if BTN_ELO_PREV_RECT.collidepoint(mx, my):
            self._step_elo(-1)
            return

        # 6. Nút Tăng ELO [+]
        if BTN_ELO_NEXT_RECT.collidepoint(mx, my):
            self._step_elo(1)
            return

        # 7. Danh sách 8 nút chọn nhanh ELO (800 - 3000)
        for target_elo, rect in ELO_BUTTON_RECTS.items():
            if rect.collidepoint(mx, my):
                self._set_elo(target_elo)
                return

        # 8. Tương tác bàn cờ (Click-to-Move cho người chơi)
        if (self.state.allow_mouse_move or self.state.manual_override_active) and self.state.turn == "r" and not self.state.game_over:
            c, r = BoardRenderer.pixel_to_grid(mx, my)
            if 0 <= c < NUM_COLS and 0 <= r < NUM_ROWS:
                clicked_piece = self.state.board[r][c]

                # Nếu đang có quân được chọn
                if self.state.selected_pos is not None:
                    src = self.state.selected_pos
                    dst = (c, r)

                    # Bấm lại chính nó -> Hủy chọn (Deselect)
                    if dst == src:
                        self.state.selected_pos = None
                        return

                    # Bấm sang một quân khác của phe Đỏ -> Đổi quân được chọn
                    if clicked_piece.startswith("r"):
                        self.state.selected_pos = (c, r)
                        return

                    # Thử đi tới ô được click
                    p_name = self.state.board[src[1]][src[0]]
                    if xiangqi.is_valid_move(src, dst, self.state.board, "r"):
                        print(f"[UI] 🖱️ Người dùng đi cờ: {p_name} {src} ➜ {dst}")
                        self.state.process_human_move(src, dst, p_name)
                        self.state.selected_pos = None
                        self.state.hint_move = None
                        self.state.manual_override_active = False

                        # Chụp lại baseline nếu camera đang hoạt động
                        if self.hw and hasattr(self.hw, "cam_monitor") and self.hw.cam_monitor:
                            self.hw.capture_baseline_if_needed(force_delay=1.0)
                    else:
                        print(f"[UI] ❌ Nước đi không hợp lệ: {src} ➜ {dst}")
                        self.state.set_status("❌ Nước đi không hợp lệ!", color=(220, 38, 38), duration=2.5)
                        self.state.set_invalid_flash(dst[0], dst[1])
                else:
                    # Chưa có quân chọn -> Nếu bấm trúng quân Đỏ thì chọn quân
                    if clicked_piece.startswith("r"):
                        self.state.selected_pos = (c, r)

    # =========================================================================
    # 2. XỬ LÝ PHÍM TẮT (KEYBOARD INPUT)
    # =========================================================================
    def handle_keyboard(self, key):
        # U KEY: Undo Last Move (Hoàn tác nước cờ)
        if key == pygame.K_u:
            self.state.undo_round(self.hw)
            return

        # H KEY: Gợi ý nước đi (Hint)
        if key == pygame.K_h:
            self._handle_hint()
            return

        # N KEY: Ván mới (New Game)
        if key == pygame.K_n:
            self.state.reset_game(self.hw)
            return

        # PHÍM 1-8: Đổi cấp độ ELO của AI
        elo_key_map = {
            pygame.K_1: 800,
            pygame.K_2: 1100,
            pygame.K_3: 1400,
            pygame.K_4: 1700,
            pygame.K_5: 2000,
            pygame.K_6: 2300,
            pygame.K_7: 2600,
            pygame.K_8: 3000,
        }
        if key in elo_key_map:
            self._set_elo(elo_key_map[key])
            return

        # [ KEY / ] KEY / - / +: Tăng hoặc giảm nấc ELO
        if key in (pygame.K_LEFTBRACKET, pygame.K_MINUS):
            self._step_elo(-1)
            return
        elif key in (pygame.K_RIGHTBRACKET, pygame.K_EQUALS):
            self._step_elo(1)
            return

        # G KEY: Test Gripper Tool DO0
        if key == pygame.K_g:
            self._handle_gripper_test(do_id=0)
            return

        # I KEY: Lấy dữ liệu & Kiểm tra kết nối từ Robot FR3
        elif key == pygame.K_i:
            self._handle_robot_info()
            return

        if self.state.allow_mouse_move or self.state.game_over or self.state.turn != "r":
            return

        # Z KEY: Rollback
        if key == pygame.K_z:
            self.state.handle_rollback(self.hw)

        # SPACE KEY: Trigger YOLO / Camera Detection
        elif key == pygame.K_SPACE:
            self._handle_space_key()

    # =========================================================================
    # 3. HELPER ACTIONS (ĐỔI ELO, GỢI Ý, XIN THUA, TEST THIẾT BỊ)
    # =========================================================================
    def _set_elo(self, target_elo: int):
        """Đặt mức ELO cho AI qua AIController."""
        if self.hw and hasattr(self.hw, "ai_ctrl") and self.hw.ai_ctrl:
            elo, title = self.hw.ai_ctrl.set_elo(target_elo)
            self.state.ai_elo = elo
            self.state.ai_elo_title = title
            self.state.set_status(f"🎯 AI ELO: {title}", color=(234, 88, 12), duration=3.0)
            print(f"[UI] 🎯 Đã đổi AI ELO thành {elo} ({title})")

    def _step_elo(self, direction: int):
        """Tăng hoặc giảm 1 nấc ELO."""
        if self.hw and hasattr(self.hw, "ai_ctrl") and self.hw.ai_ctrl:
            elo, title = self.hw.ai_ctrl.step_elo(direction)
            self.state.ai_elo = elo
            self.state.ai_elo_title = title
            self.state.set_status(f"🎯 AI ELO: {title}", color=(234, 88, 12), duration=3.0)
            print(f"[UI] 🎯 Đã đổi AI ELO thành {elo} ({title})")

    def _handle_hint(self):
        """Tìm và hiển thị nước đi gợi ý cho người chơi."""
        if self.state.game_over:
            return
        if self.state.turn != "r":
            self.state.set_status("⚠️ Đang trong lượt của AI, hãy đợi AI đi xong!", color=(200, 100, 0), duration=2.5)
            return

        if self.hw and hasattr(self.hw, "ai_ctrl") and self.hw.ai_ctrl:
            board_snap = [row[:] for row in self.state.board]

            def _hint_worker():
                self.state.set_status("💡 AI đang tìm nước gợi ý tốt nhất...", color=(202, 138, 4), duration=2.0)
                hint = self.hw.ai_ctrl.pick_move(board_snap, color="r")
                if hint:
                    self.state.hint_move = hint
                    self.state.hint_expiry = time.time() + 6.0
                    hs, hd = hint
                    p = self.state.board[hs[1]][hs[0]]
                    self.state.set_status(f"💡 Gợi ý: {p} ({hs[0]},{hs[1]}) ➜ ({hd[0]},{hd[1]})", color=(168, 85, 247), duration=6.0)
                    print(f"[HINT] 💡 Gợi ý nước đi: {p} {hs} ➜ {hd}")
                else:
                    self.state.set_status("⚠️ Không tìm được nước gợi ý!", color=(180, 100, 0), duration=2.5)

            threading.Thread(target=_hint_worker, daemon=True).start()

    def _handle_surrender(self):
        """Xử lý khi người chơi xin thua."""
        if not self.state.game_over:
            print("[GAME] YOU SURRENDER!")
            self.state.handle_game_over("b", reason="XIN THUA")
            if hasattr(self.state, "api_client") and self.state.api_client:
                try:
                    self.state.api_client.end_match(winner="BLACK", reason="RESIGN")
                except Exception:
                    pass
            self.state.set_status("🏳️ Bạn đã xin thua ván cờ!", color=(220, 38, 38), duration=5.0)

    def _handle_gripper_test(self, do_id=0):
        if self.hw.gripper_driver is not None:
            def _driver_worker():
                action_name = "CLOSE" if do_id == 0 else "OPEN"
                print(f"\n[GRIPPER TEST] 🔧 Đang test kích hoạt GripperDriver: {action_name}...")
                self.state.set_status(f"🔧 Test Gripper: {action_name}...", color=(0, 150, 0), duration=2.0)
                try:
                    if do_id == 0:
                        ok = self.hw.gripper_driver.close()
                    else:
                        ok = self.hw.gripper_driver.open()
                    msg = "✅ Thành công!" if ok else "⚠️ Thất bại!"
                    self.state.set_status(f"Gripper {action_name}: {msg}", color=(0, 100, 180), duration=2.0)
                except Exception as e:
                    print(f"[GRIPPER TEST] ❌ Lỗi test Gripper: {e}")
                    self.state.set_status(f"❌ Lỗi: {e}", color=(180, 0, 0), duration=3.0)

            threading.Thread(target=_driver_worker, daemon=True).start()
            return

        if not self.hw.gripper_driver:
            print("[GRIPPER TEST] ❌ GripperDriver chưa được cấu hình!")
            self.state.set_status("❌ GripperDriver chưa cấu hình!", color=(180, 0, 0), duration=3.0)
            return

    def _handle_robot_info(self):
        if self.hw.backend is not None:
            snap = self.hw.backend.get_state_snapshot()
            print("\n" + "="*50)
            print("🤖 [THÔNG TIN TRẠNG THÁI ROBOT FR3 - UNIFIED BACKEND]")
            print(f"  - Robot Model: {snap.robot_model}")
            print(f"  - Kết nối: {'✅ ĐANG KẾT NỐI' if snap.connected else '❌ MẤT KẾT NỐI'}")
            print(f"  - Trạng thái Motion: {snap.motion_state}")
            print(f"  - Khớp Joints (deg): {[round(q, 2) for q in snap.joints_deg]}")
            print(f"  - TCP Pose (mm, deg): {[round(p, 2) for p in snap.tcp_pose_mm_deg]}")
            print(f"  - Flange Pose (mm, deg): {[round(p, 2) for p in snap.flange_pose_mm_deg]}")
            print("="*50 + "\n")
            self.state.set_status("✅ Đã lấy thông số từ Backend (Xem Terminal)", color=(0, 100, 180), duration=4.0)
            return

        if not self.hw.robot or not self.hw.robot.connected:
            print("[ROBOT INFO] ❌ Robot chưa kết nối!")
            self.state.set_status("❌ Robot chưa kết nối!", color=(180, 0, 0), duration=3.0)
            return

    def _handle_space_key(self, auto_retry=False) -> bool:
        print("\n[SPACE] 🎯 Người chơi bấm SPACE — đang chụp T2 snapshot...")
        self.state.set_status("📸 Đang phân tích bàn cờ...", color=(0, 100, 180), duration=3.0)

        if self.state.turn != "r" or self.state.game_over:
            print("[SPACE] ⚠️ Chưa đến lượt Đỏ hoặc ván đấu đã kết thúc.")
            return False

        if not self.hw.cam_monitor:
            self.state.set_status("❌ Hệ thống Camera chưa khởi tạo!", color=(180, 0, 0))
            return False

        frame, detections = self.hw.cam_monitor.get_fresh_snapshot()
        if frame is None:
            print("[SPACE] ❌ Không lấy được camera frame!")
            if not auto_retry:
                self.state.set_status("❌ Không lấy được hình ảnh từ Camera!", color=(180, 0, 0))
            return False

        # Validate / Capture YOLO baseline if detector is active
        if self.hw.yolo_detector and not self.hw.yolo_detector.has_baseline():
            print("[SPACE] ⚠️ Chưa có T1 baseline — chụp ngay...")
            if self.hw.yolo_detector.capture_baseline(frame, detections):
                self.state.set_status("📸 Đã làm mới Trạng thái bàn cờ hiện tại", color=(0, 100, 180), duration=5.0)
            else:
                self.state.set_status("❌ Không chụp được baseline!", color=(180, 0, 0))
            return False

        # SAVE ROLLBACK STATE TRƯỚC KHI DETECT (để có thể rollback khi lỗi)
        if self.hw.yolo_detector and self.hw.yolo_detector.has_baseline():
            occ = [row[:] for row in self.hw.yolo_detector._baseline_occ]
            b_time = self.hw.yolo_detector._baseline_time
            self.state.save_rollback_state(occ, b_time)

        obs = None
        cchess_result = None

        if hasattr(self.hw, "recognize_board_state") and self.hw.cchess_recognizer is not None:
            try:
                cchess_result = self.hw.recognize_board_state(frame)
                if cchess_result and cchess_result.get("success") and cchess_result.get("quality_ok", True):
                    rec_board = cchess_result.get("board")
                    confs = cchess_result.get("confidence")
                    obs = derive_move_observation(
                        before_board=self.state.board,
                        after_board=rec_board,
                        player_color="r",
                        confidence_grid=confs,
                    )
            except Exception as e:
                print(f"[SPACE] ⚠️ CChess recognizer error: {e}")

        if self.hw.yolo_detector and self.hw.yolo_detector.has_baseline():
            yolo_obs = self.hw.yolo_detector.detect_move_observation(
                frame, detections, self.state.board, cchess_result=cchess_result
            )
            if obs is not None and obs.success:
                if yolo_obs.success and (yolo_obs.src, yolo_obs.dst) != (obs.src, obs.dst):
                    obs = MoveObservation(
                        success=False,
                        is_ambiguous=True,
                        error=f"Xung đột cảm biến: CChess != YOLO",
                    )
            elif obs is None or (not obs.success and not obs.is_ambiguous):
                obs = yolo_obs

        if obs is None:
            obs = MoveObservation(success=False, error="Không có hệ thống nhận diện khả dụng")

        if not obs.success:
            if obs.is_ambiguous:
                self.state.set_status(f"⚠️ Nước đi mơ hồ: {obs.error}", color=(180, 100, 0), duration=10.0)
            else:
                self.state.set_status(f"❌ {obs.error or 'Không thấy nước đi hợp lệ!'}", color=(180, 0, 0), duration=5.0)
            self.state.manual_override_active = True
            self.hw.clear_yolo_baseline()
            return False

        if not xiangqi.is_valid_move(obs.src, obs.dst, self.state.board, "r"):
            self.state.set_status("⚠️ Lỗi nhận diện / Đi sai luật! Dùng chuột kéo thả.", color=(180, 100, 0), duration=10.0)
            self.state.manual_override_active = True
            self.hw.clear_yolo_baseline()
            return False

        self.state.process_human_move(obs.src, obs.dst, obs.piece)
        if self.hw.yolo_detector:
            self.hw.yolo_detector.capture_baseline(frame, detections)
        return True

    def try_auto_confirm_move(self, retries=10, retry_seconds=0.2) -> bool:
        if self.state.turn != "r" or self.state.game_over:
            return False
        if not self.hw.yolo_detector or not self.hw.yolo_detector.has_baseline():
            self.hw.reset_hand_interaction_monitor()
            return False
        for _ in range(int(retries)):
            if self._handle_space_key(auto_retry=True):
                self.hw.reset_hand_interaction_monitor()
                return True
            time.sleep(float(retry_seconds))
        self.state.manual_override_active = False
        self.hw.reset_hand_interaction_monitor()
        return False
