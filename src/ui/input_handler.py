import time
from src.core import xiangqi  # type: ignore
from src.ui.board_renderer import BoardRenderer, BTN_SURRENDER_RECT, BTN_NEW_GAME_RECT, NUM_COLS, NUM_ROWS  # type: ignore

class InputHandler:
    """Manages Pygame Key/Mouse events and bridges them to GameState and HardwareManager."""
    def __init__(self, game_state, hw_manager):
        self.state = game_state
        self.hw = hw_manager

    def handle_mouse_down(self, mx, my):
        # Surrender Button
        if BTN_SURRENDER_RECT.collidepoint(mx, my) and not self.state.game_over:
            print("[GAME] YOU SURRENDER!")
            self.state.handle_game_over("b")
            self.state.api_client.end_match(winner="BLACK", reason="RESIGN")
            return

        # New Game Button
        if BTN_NEW_GAME_RECT.collidepoint(mx, my):
            self.state.reset_game(self.hw)
            return

        # Manual Override (Mouse Drag)
        if (self.state.allow_mouse_move or self.state.manual_override_active) and self.state.turn == "r" and not self.state.game_over:
            c, r = BoardRenderer.pixel_to_grid(mx, my)
            if 0 <= c < NUM_COLS and 0 <= r < NUM_ROWS:
                clicked_piece = self.state.board[r][c]
                
                # Select a piece
                if clicked_piece.startswith("r"):
                    self.state.selected_pos = (c, r)
                    
                # Move a selected piece
                elif self.state.selected_pos:
                    src, dst = self.state.selected_pos, (c, r)
                    p_name = self.state.board[src[1]][src[0]]
                    
                    if xiangqi.is_valid_move(src, dst, self.state.board, "r"):
                        print("[UI] 🖱️ Người dùng đi cờ trên màn hình.")
                        self.state.process_human_move(src, dst, p_name)
                        self.state.selected_pos = None
                        self.state.manual_override_active = False
                        
                        # Retake T1 baseline after manual override
                        if self.hw.cam_monitor:
                            print("[UI] 📸 Đang chụp lại T1 baseline sau khi Override...")
                            self.state.set_status("📸 Cập nhật Mắt Camera...", color=(0, 100, 180), duration=2.0)
                            self.hw.capture_baseline_if_needed(force_delay=1.0)
                    else:
                        print(f"Invalid move: {src}->{dst}")
                        self.state.set_status("❌  Invalid move!", color=(180, 0, 0))
                        self.state.set_invalid_flash(dst[0], dst[1])
                        self.state.selected_pos = None

    def handle_keyboard(self, key):
        import pygame  # type: ignore
        if key == pygame.K_v and self.state.physical_sync_fault:
            self._reconcile_physical_sync_fault()
            return

        if self.state.allow_mouse_move or self.state.game_over or self.state.turn != "r":
            return

        # Z KEY: Rollback
        if key == pygame.K_z:
            self.state.handle_rollback(self.hw)
            
        # SPACE KEY: Trigger YOLO Detection
        elif key == pygame.K_SPACE:
            self._handle_space_key()

    def _reconcile_physical_sync_fault(self):
        """Supervised recovery for a stopped physical-board synchronization."""
        pending = self.state.pending_ai_move
        if not pending or not self.hw.verify_physical_board:
            self.state.set_status("❌ Không có trạng thái đối soát để khôi phục.", color=(180, 0, 0), duration=8.0)
            return

        self.state.set_status("📸 Đang đối soát lại bàn thật...", color=(0, 100, 180), duration=5.0)
        # No robot command is issued here.  Matching the old board means the
        # arm did not complete the move; matching expected_board means it did.
        if self.hw.verify_physical_board(self.state.board):
            self.state.clear_pending_ai_move()
            self.state.set_status("↩️ Bàn thật vẫn ở FEN cũ — có thể thử lại nước AI.", color=(0, 100, 180), duration=10.0)
            return

        if self.hw.verify_physical_board(pending["expected_board"]):
            if self.state.commit_pending_ai_move():
                self.state.api_client.send_move_update_board(self.state.current_fen)
                if xiangqi.get_king_pos("r", self.state.board) is None:
                    self.state.handle_game_over("b")
                    self.state.api_client.end_match(winner="BLACK", reason="CHECKMATE")
                else:
                    self.hw.capture_baseline_if_needed(force_delay=1.0)
                    self.state.set_status("✅ Đã xác nhận bàn thật — đến lượt bạn.", color=(0, 100, 180), duration=8.0)
            return

        self.state.set_status("❌ Bàn thật không khớp trước/sau nước đi. Chỉnh tay rồi nhấn V.", color=(180, 0, 0), duration=15.0)

    def _handle_space_key(self, auto_retry=False):
        print("\n[SPACE] 🎯 Người chơi bấm SPACE — đang chụp T2 snapshot...")
        self.state.set_status("📸  Đang phân tích YOLO...", color=(0, 100, 180), duration=3.0)
        
        if not self.hw.yolo_detector or not self.hw.cam_monitor:
            self.state.set_status("❌  Hệ thống nhận diện chưa khởi tạo!", color=(180, 0, 0))
            return False
            
        frame, detections = self.hw.cam_monitor.get_fresh_snapshot()
        
        # Validate Baseline
        if not self.hw.yolo_detector.has_baseline():
            print("[SPACE] ⚠️ Chưa có T1 baseline — chụp ngay...")
            if self.hw.yolo_detector.capture_baseline(frame, detections):
                self.state.set_status("📸 Đã làm mới Trạng thái bàn cờ hiện tại", color=(0, 100, 180), duration=5.0)
            else:
                self.state.set_status("❌ Không chụp được baseline!", color=(180, 0, 0))
            return False

        # SAVE ROLLBACK STATE TRƯỚC KHI DETECT (để có thể rollback khi lỗi)
        occ = [row[:] for row in self.hw.yolo_detector._baseline_occ]
        b_time = self.hw.yolo_detector._baseline_time
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
            # Note: Vietnamese name resolution skipped here for brevity, handled by detector UI largely
            print(f"[YOLO] 👉 Nhận diện đi từ Cột {src[0]} Hàng {src[1]} đến Cột {dst[0]} Hàng {dst[1]}")
            
        # Verify result
        if src is None:
            print("[SPACE] ❌ YOLO KHÔNG thấy nước đi hợp lệ!")
            if not auto_retry:
                self.state.set_status("❌  Không thấy nước đi! Di quân trên màn hình.", color=(180, 0, 0), duration=5.0)
                self.state.manual_override_active = True
                self.hw.clear_yolo_baseline()
            return False
            
        if not xiangqi.is_valid_move(src, dst, self.state.board, "r"):
            print(f"[SPACE] ❌ YOLO báo nước đi không hợp lệ: {src}->{dst}")
            if not auto_retry:
                self.state.set_status("⚠️  Lỗi nhận diện / Đi sai luật! Dùng chuột kéo thả.", color=(180, 100, 0), duration=60.0)
                self.state.set_invalid_flash(dst[0], dst[1])
                self.state.manual_override_active = True
                self.hw.clear_yolo_baseline()
            return False

        # Commit move (state đã được save ở trên rồi)
        self.state.process_human_move(src, dst, piece)
        return True

    def try_auto_confirm_move(self, retries=10, retry_seconds=0.2):
        """Reuse the existing rule-validated snapshot flow after hand exit."""
        import time
        if self.state.turn != "r" or self.state.game_over:
            return False
        if not self.hw.yolo_detector or not self.hw.yolo_detector.has_baseline():
            self.hw.reset_hand_interaction_monitor()
            self.state.set_status("⚠️ Chưa có baseline. Hãy nhấn SPACE để xác minh.", color=(180, 100, 0), duration=12.0)
            return False
        self.state.set_status("✋ Hand left board — verifying move...", color=(0, 100, 180), duration=3.0)
        for attempt in range(1, int(retries) + 1):
            if self._handle_space_key(auto_retry=True):
                self.hw.reset_hand_interaction_monitor()
                return True
            if attempt < retries:
                time.sleep(float(retry_seconds))
        self.state.manual_override_active = False
        self.hw.reset_hand_interaction_monitor()
        self.state.set_status("⚠️ Không xác minh được nước đi. Hãy nhấn SPACE.", color=(180, 100, 0), duration=12.0)
        print("[AUTO CONFIRM] Failed after retry limit; waiting for SPACE fallback.")
        return False
