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
    BTN_RESUME_SCAN_RECT,
    ELO_BUTTON_RECTS,
    BTN_ELO_PREV_RECT,
    BTN_ELO_NEXT_RECT,
    NUM_COLS,
    NUM_ROWS,
)
from src.vision.move_observation import MoveObservation, derive_move_observation
from src.digital_twin.live_twin_bridge import LiveTwinBridge
from src.vision.board_stability_monitor import BoardStabilityMonitor
from src.vision.player_turn_arbiter import PlayerTurnArbiter
from src.vision.player_turn_types import (
    BoardObservation,
    CommitRequest,
    InteractionCapability,
    PlayerTurnMode,
    Visibility,
)
from src.core.human_move_commit_coordinator import HumanMoveCommitCoordinator


class InputHandler:
    """Manages Pygame Key/Mouse events and bridges them to GameState and HardwareManager."""

    def __init__(self, game_state, hw_manager):
        self.state = game_state
        self.hw = hw_manager
        self._last_move_confirmation_failure = None
        stability_config = getattr(self.hw, "config", None)
        self._board_stability_monitor = BoardStabilityMonitor(
            stability_seconds=getattr(stability_config, "BOARD_STABILITY_SECONDS", 1.2),
            min_samples=getattr(stability_config, "BOARD_STABILITY_MIN_SAMPLES", 3),
        )
        self._observed_baseline_time = None
        self._last_stability_poll_at = 0.0
        configured_mode = getattr(stability_config, "PLAYER_TURN_MODE", "LEGACY")
        try:
            self._player_turn_mode = PlayerTurnMode(configured_mode.upper())
        except (AttributeError, ValueError):
            self._player_turn_mode = PlayerTurnMode.LEGACY
        self._player_turn_arbiter = PlayerTurnArbiter(
            clear_seconds=getattr(stability_config, "PLAYER_TURN_CLEAR_SECONDS", 0.8),
            clear_samples=getattr(stability_config, "PLAYER_TURN_CLEAR_SAMPLES", 3),
            interaction_settle_seconds=getattr(stability_config, "PLAYER_TURN_INTERACTION_SETTLE_SECONDS", 1.2),
            idle_settle_seconds=getattr(stability_config, "PLAYER_TURN_IDLE_SETTLE_SECONDS", 3.0),
            idle_samples=getattr(stability_config, "PLAYER_TURN_IDLE_SETTLE_SAMPLES", 5),
        )
        self._human_commit_coordinator = HumanMoveCommitCoordinator(game_state)
        self._unified_active = False
        self._observed_game_epoch = getattr(game_state, "game_epoch", 0)

    @property
    def _human_turn(self):
        return bool(getattr(self.state, "is_human_turn", self.state.turn == "r"))

    @property
    def _has_twin(self):
        return isinstance(getattr(self.hw, "twin_bridge", None), LiveTwinBridge)

    def _interaction_capability(self):
        """Hardware must explicitly provide obstruction evidence for UNIFIED."""
        capability = getattr(self.hw, "interaction_capability", None)
        if callable(capability):
            capability = capability()
        if isinstance(capability, InteractionCapability):
            return capability
        try:
            return InteractionCapability(str(capability).upper())
        except ValueError:
            return InteractionCapability.UNAVAILABLE

    def _commit_human_move(self, src, dst, piece, source="LEGACY"):
        request = type("Request", (), {"turn_token": (getattr(self.state, "game_epoch", 0),
                                                        getattr(self.state, "human_commit_generation", 0),
                                                        getattr(self._player_turn_arbiter, "turn_token", 0)),
                                         "move": (src, dst), "source": source})()
        return self._human_commit_coordinator.try_commit(request, piece) == "ACCEPTED"

    def _maybe_activate_unified_turn(self):
        current_epoch = getattr(self.state, "game_epoch", 0)
        if current_epoch != self._observed_game_epoch:
            self._player_turn_arbiter.deactivate()
            self._unified_active = False
            self._observed_game_epoch = current_epoch
        if self._player_turn_mode == PlayerTurnMode.LEGACY:
            return False
        capability = self._interaction_capability()
        if (self.state.turn != "r" or self.state.game_over
                or not getattr(self.hw, "yolo_detector", None) or not self.hw.yolo_detector.has_baseline()):
            self._player_turn_arbiter.deactivate()
            self._unified_active = False
            return False
        if not self._unified_active:
            activation_capability = (InteractionCapability.AVAILABLE
                                     if self._player_turn_mode == PlayerTurnMode.SHADOW
                                     else capability)
            self._player_turn_arbiter.activate(self.state.board, activation_capability)
            self._unified_active = self._player_turn_arbiter.state.name != "INACTIVE"
        return self._unified_active

    # =========================================================================
    # 1. XỬ LÝ CHUỘT (MOUSE INPUT - CLICK BUTTONS & CLICK-TO-MOVE)
    # =========================================================================
    def handle_mouse_down(self, mx: int, my: int):
        # 0. Nút Tiếp tục quét FEN khi đang ở manual override
        if BTN_RESUME_SCAN_RECT.collidepoint(mx, my) and getattr(self.state, "manual_override_active", False):
            self.resume_automatic_scanning()
            return

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
        if (self.state.allow_mouse_move or getattr(self.state, "manual_override_active", False)) and self._human_turn and not self.state.game_over:
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
                    if clicked_piece.startswith(self.state.turn):
                        self.state.selected_pos = (c, r)
                        return

                    # Thử đi tới ô được click
                    p_name = self.state.board[src[1]][src[0]]
                    if xiangqi.is_valid_move(src, dst, self.state.board, self.state.turn):
                        if (getattr(getattr(self.hw, "config", None), "ROBOT_BACKEND", "VIRTUAL").upper() == "PHYSICAL"
                                and not getattr(self.hw, "dry_run", True)):
                            expected, _ = xiangqi.make_temp_move(self.state.board, (src, dst))
                            if not self.hw.verify_physical_board(expected):
                                self.state.set_status("❌ Bàn thật chưa xác nhận nước đi.", color=(180, 0, 0), duration=7)
                                return
                        if getattr(self.state, "manual_override_active", False) and hasattr(self.state, "save_rollback_state"):
                            occ = getattr(getattr(self.hw, "yolo_detector", None), "_baseline_occ", None)
                            b_time = getattr(getattr(self.hw, "yolo_detector", None), "_baseline_time", None)
                            self.state.save_rollback_state(occ, b_time)

                        print(f"[UI] 🖱️ Người dùng đi cờ: {p_name} {src} ➜ {dst}")
                        accepted = self.state.process_human_move(src, dst, p_name)
                        if accepted is False:
                            return
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
                    if clicked_piece.startswith(self.state.turn):
                        self.state.selected_pos = (c, r)

    # =========================================================================
    # 2. XỬ LÝ PHÍM TẮT (KEYBOARD INPUT)
    # =========================================================================
    def handle_keyboard(self, key):
        if getattr(self.state, "turn_confirmation_required", False):
            if key in (pygame.K_1, pygame.K_KP1):
                self.state.confirm_turn_after_rescan("r")
            elif key in (pygame.K_2, pygame.K_KP2):
                self.state.confirm_turn_after_rescan("b")
            return
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
        # M KEY: Emergency manual client mode
        if key == pygame.K_m and not self.state.game_over:
            self.state.manual_override_active = True
            self.state.set_status("⚠️ Emergency client mode enabled: Click to move manually.", color=(234, 88, 12), duration=10.0)
            return

        if self.state.allow_mouse_move or self.state.game_over or not self._human_turn:
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
        if self._player_turn_mode == PlayerTurnMode.UNIFIED:
            self.state.set_status("⚠️ UNIFIED: SPACE chỉ yêu cầu poll state-machine.", color=(180, 100, 0))
            return False
        print("\n[SPACE] 🎯 Người chơi bấm SPACE — đang chụp T2 snapshot...")
        self.state.set_status("📸 Đang phân tích bàn cờ...", color=(0, 100, 180), duration=3.0)

        if not self._human_turn or self.state.game_over:
            print("[SPACE] ⚠️ Chưa đến lượt người chơi hoặc ván đấu đã kết thúc.")
            return False

        if not getattr(self.hw, "yolo_detector", None) or not getattr(self.hw, "cam_monitor", None):
            self.state.set_status("❌ Hệ thống nhận diện chưa khởi tạo!", color=(180, 0, 0))
            return False

        frame, detections = self.hw.cam_monitor.get_fresh_snapshot()

        # Validate / Capture YOLO baseline if detector is active
        if not self.hw.yolo_detector.has_baseline():
            print("[SPACE] ⚠️ Chưa có T1 baseline — chụp ngay...")
            if hasattr(self.hw.yolo_detector, "capture_baseline") and self.hw.yolo_detector.capture_baseline(frame, detections):
                self.state.set_status("📸 Đã làm mới Trạng thái bàn cờ hiện tại", color=(0, 100, 180), duration=5.0)
            else:
                self.state.set_status("❌ Không chụp được baseline!", color=(180, 0, 0))
            return False

        # SAVE ROLLBACK STATE TRƯỚC KHI DETECT (để có thể rollback khi lỗi)
        occ = [row[:] for row in getattr(self.hw.yolo_detector, "_baseline_occ", [])]
        b_time = getattr(self.hw.yolo_detector, "_baseline_time", None)
        self.state.save_rollback_state(occ, b_time)

        # CCHESS ONNX Recognition (nếu đã kích hoạt)
        cchess_result = None
        if getattr(self.hw, "cchess_recognizer", None) is not None and frame is not None:
            try:
                print("[SPACE] 🧠 Chạy CChess ONNX Recognition (Cross-validation)...")
                cchess_result = self.hw.recognize_board_state(frame)
                if cchess_result and cchess_result.get("success"):
                    print("[CChess ONNX] ✅ Nhận diện bàn cờ & quân cờ thành công!")
            except Exception as e:
                print(f"[CChess ONNX] ⚠️ Lỗi khi nhận diện CChess: {e}")

        # Perform Detection
        print("[SPACE] 🔍 Chạy YOLO Detector...")
        src, dst, piece = self.hw.yolo_detector.detect_move(
            frame, detections, self.state.board, cchess_result=cchess_result
        )

        if src:
            print(f"[YOLO] 👉 Nhận diện đi từ Cột {src[0]} Hàng {src[1]} đến Cột {dst[0]} Hàng {dst[1]}")

        # Verify result
        if src is None:
            print("[SPACE] ❌ YOLO KHÔNG thấy nước đi hợp lệ!")
            has_new_move = self.hw.yolo_detector.has_new_human_move(
                detections, self.state.board, frame=frame, cchess_result=cchess_result
            )
            if has_new_move:
                self._last_move_confirmation_failure = "invalid"
                message = "❌ NƯỚC ĐI KHÔNG HỢP LỆ"
            else:
                if not auto_retry or self._last_move_confirmation_failure != "invalid":
                    self._last_move_confirmation_failure = "missing"
                message = "❌ KHÔNG NHẬN DIỆN ĐƯỢC NƯỚC ĐI MỚI"
            if not auto_retry:
                self.state.set_status(message, color=(180, 0, 0), duration=8.0)
                self.state.manual_override_active = True
                if hasattr(self.hw, "clear_yolo_baseline"):
                    self.hw.clear_yolo_baseline()
            return False

        if not xiangqi.is_valid_move(src, dst, self.state.board, "r"):
            print(f"[SPACE] ❌ YOLO báo nước đi không hợp lệ: {src}->{dst}")
            self._last_move_confirmation_failure = "invalid"
            if not auto_retry:
                self.state.set_status("❌ NƯỚC ĐI KHÔNG HỢP LỆ", color=(180, 0, 0), duration=8.0)
                self.state.set_invalid_flash(dst[0], dst[1])
                self.state.manual_override_active = True
                if hasattr(self.hw, "clear_yolo_baseline"):
                    self.hw.clear_yolo_baseline()
            return False

        # Commit move (state đã được save ở trên rồi)
        self._last_move_confirmation_failure = None
        committed = self._commit_human_move(src, dst, piece, source="SPACE")
        if committed:
            self.state.manual_override_active = False
            if hasattr(self.hw, "yolo_detector") and hasattr(self.hw.yolo_detector, "capture_baseline"):
                self.hw.yolo_detector.capture_baseline(frame, detections)
        return committed

    def try_auto_confirm_move(self, retries=10, retry_seconds=0.2) -> bool:
        """Reuse the existing rule-validated snapshot flow after hand exit."""
        if not self._human_turn or self.state.game_over:
            return False
        if not getattr(self.hw, "yolo_detector", None) or not self.hw.yolo_detector.has_baseline():
            reset_monitor = getattr(self.hw, "reset_hand_interaction_monitor", None)
            if reset_monitor:
                reset_monitor()
            self.state.set_status("⚠️ Chưa có baseline. Hãy nhấn SPACE để xác minh.", color=(180, 100, 0), duration=12.0)
            return False
        self._last_move_confirmation_failure = None
        self.state.set_status("✋ Hand left board — verifying move...", color=(0, 100, 180), duration=3.0)
        for attempt in range(1, int(retries) + 1):
            if self._handle_space_key(auto_retry=True):
                reset_monitor = getattr(self.hw, "reset_hand_interaction_monitor", None)
                if reset_monitor:
                    reset_monitor()
                return True
            if attempt < retries and float(retry_seconds) > 0:
                time.sleep(float(retry_seconds))
        self.state.manual_override_active = False
        reset_monitor = getattr(self.hw, "reset_hand_interaction_monitor", None)
        if reset_monitor:
            reset_monitor()
        message = ("❌ NƯỚC ĐI KHÔNG HỢP LỆ"
                   if self._last_move_confirmation_failure == "invalid"
                   else "❌ KHÔNG NHẬN DIỆN ĐƯỢC NƯỚC ĐI MỚI")
        self.state.set_status(message, color=(180, 0, 0), duration=12.0)
        print("[AUTO CONFIRM] Failed after retry limit; waiting for SPACE fallback.")
        return False

    def resume_automatic_scanning(self) -> bool:
        """Install a fresh physical baseline, then re-enable automatic polling."""
        detector = getattr(self.hw, "yolo_detector", None)
        camera = getattr(self.hw, "cam_monitor", None)
        if detector is None or camera is None:
            self.state.set_status("❌ Không thể tiếp tục quét: camera chưa sẵn sàng.", color=(180, 0, 0), duration=8.0)
            return False

        verifier = getattr(self.hw, "verify_physical_board", None)
        reconciliation_available = bool(
            getattr(self.hw, "board_reconciler", None) and camera
        )
        if reconciliation_available and callable(verifier):
            try:
                board_matches = verifier(self.state.board)
            except Exception as exc:
                print(f"[RESUME SCAN] Physical-board verification error: {exc}")
                board_matches = False
            if not board_matches:
                self.state.set_status(
                    "❌ Bàn thật chưa khớp FEN. Chỉnh lại bàn rồi bấm tiếp tục quét.",
                    color=(180, 0, 0), duration=10.0,
                )
                return False

        self.state.set_status("📸 Đang lấy baseline mới để tiếp tục quét...", color=(0, 100, 180), duration=4.0)
        if hasattr(self, "_board_stability_monitor"):
            self._board_stability_monitor.reset()
        self._observed_baseline_time = None
        captured = bool(self.hw.capture_baseline_if_needed(force_delay=0.0))
        if not captured:
            self.state.set_status("❌ Không lấy được baseline; quét vẫn đang tạm dừng.", color=(180, 0, 0), duration=8.0)
            return False

        self.state.manual_override_active = False
        self._last_move_confirmation_failure = None
        if getattr(self.state, "turn_confirmation_required", False):
            self.state.set_status(self.state.move_sync_error, color=(180, 100, 0), duration=30.0)
        else:
            self.state.set_status("✅ Đã tiếp tục tự động quét FEN.", color=(0, 120, 0), duration=6.0)
        return True

    def poll_board_stability(self) -> bool:
        """Commit one legal Red move after repeated stable board observations."""
        if (self.state.turn != "r" or self.state.game_over
                or getattr(self.state, "manual_override_active", False)):
            if hasattr(self, "_board_stability_monitor"):
                self._board_stability_monitor.reset()
            return False
        now = time.monotonic()
        sample_interval = getattr(
            getattr(self.hw, "config", None), "BOARD_STABILITY_SAMPLE_INTERVAL_SECONDS", 0.10
        )
        if now - self._last_stability_poll_at < float(sample_interval):
            return False
        self._last_stability_poll_at = now
        if not getattr(self.hw, "yolo_detector", None) or not getattr(self.hw, "cam_monitor", None):
            return False
        if not self.hw.yolo_detector.has_baseline():
            self._board_stability_monitor.reset()
            self._observed_baseline_time = None
            return False

        baseline_time = getattr(self.hw.yolo_detector, "_baseline_time", None)
        if baseline_time != self._observed_baseline_time:
            if self._board_stability_monitor.candidate is not None:
                print("[STABILITY] Candidate reset: T1 baseline changed.")
            self._board_stability_monitor.reset()
            self._observed_baseline_time = baseline_time

        frame, detections = self.hw.cam_monitor.get_fresh_snapshot()
        if frame is None:
            if self._board_stability_monitor.candidate is not None:
                print("[STABILITY] Candidate reset: camera returned no frame.")
            self._board_stability_monitor.observe(None)
            return False

        cchess_result = None
        if getattr(self.hw, "cchess_recognizer", None) is not None:
            try:
                cchess_result = self.hw.recognize_board_state(frame)
            except Exception as exc:
                print(f"[STABILITY] CChess recognition error: {exc}")

        # UNIFIED only consumes a fully recognized layout.
        if self._player_turn_mode != PlayerTurnMode.LEGACY:
            active = self._maybe_activate_unified_turn()
            layout = cchess_result.get("board") if cchess_result and cchess_result.get("success") else None
            interaction = getattr(self.hw, "is_board_occluded", None)
            interaction = bool(interaction()) if callable(interaction) else False
            visibility = Visibility.CLEAR if layout is not None and not interaction else Visibility.INSUFFICIENT
            request = self._player_turn_arbiter.ingest(BoardObservation(
                observed_at=now, layout=layout, visibility=visibility,
                hand_or_object_present=interaction,
            )) if active else None
            if request is not None and self._player_turn_mode == PlayerTurnMode.UNIFIED:
                src, dst = request.move
                piece = self.state.board[src[1]][src[0]]
                scoped_request = CommitRequest(
                    (getattr(self.state, "game_epoch", 0),
                     getattr(self.state, "human_commit_generation", 0),
                     request.turn_token),
                    request.move,
                )
                committed = self._human_commit_coordinator.try_commit(scoped_request, piece) == "ACCEPTED"
                if committed:
                    self._player_turn_arbiter.deactivate()
                return committed
            if self._player_turn_mode == PlayerTurnMode.UNIFIED:
                return False

        src, dst, piece = self.hw.yolo_detector.detect_move(
            frame, detections, self.state.board, cchess_result=cchess_result
        )
        candidate = None
        rejection_reason = None
        if src is None:
            has_changed = self.hw.yolo_detector.has_new_human_move(
                detections, self.state.board, frame=frame, cchess_result=cchess_result
            )
            rejection_reason = (
                "board changed but no valid move was resolved"
                if has_changed else "no board change from T1"
            )
        elif xiangqi.is_valid_move(src, dst, self.state.board, "r"):
            candidate = (src, dst, piece)
        else:
            rejection_reason = f"illegal Red move {src}->{dst}"

        previous_candidate = self._board_stability_monitor.candidate
        if candidate is None and previous_candidate is not None:
            print(f"[STABILITY] Candidate reset: {rejection_reason}.")
        elif candidate is not None and candidate != previous_candidate:
            print(f"[STABILITY] Candidate started: {candidate}")
        stable_move = self._board_stability_monitor.observe(candidate)
        if stable_move is None:
            return False

        src, dst, piece = stable_move
        occ = [row[:] for row in getattr(self.hw.yolo_detector, "_baseline_occ", [])]
        self.state.save_rollback_state(occ, getattr(self.hw.yolo_detector, "_baseline_time", None))
        print(
            "[STABILITY] Stable legal move confirmed: "
            f"{piece} {src}->{dst}; samples={self._board_stability_monitor.sample_count}, "
            f"elapsed={self._board_stability_monitor.elapsed_seconds():.2f}s"
        )
        self._last_move_confirmation_failure = None
        committed = self._commit_human_move(src, dst, piece, source="AUTO")
        self._board_stability_monitor.reset()
        if committed:
            if hasattr(self.hw, "yolo_detector") and hasattr(self.hw.yolo_detector, "capture_baseline"):
                self.hw.yolo_detector.capture_baseline(frame, detections)
        return committed
