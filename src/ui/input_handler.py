import time
from src.core import xiangqi  # type: ignore
from src.ui.board_renderer import (BoardRenderer, BTN_SURRENDER_RECT, BTN_NEW_GAME_RECT,
                                   BTN_RESUME_SCAN_RECT, NUM_COLS, NUM_ROWS)  # type: ignore
from src.vision.board_stability_monitor import BoardStabilityMonitor
from src.vision.player_turn_arbiter import PlayerTurnArbiter
from src.vision.player_turn_types import BoardObservation, CommitRequest, InteractionCapability, PlayerTurnMode, Visibility
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
                                                        self._player_turn_arbiter.turn_token),
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
                or not self.hw.yolo_detector or not self.hw.yolo_detector.has_baseline()):
            self._player_turn_arbiter.deactivate()
            self._unified_active = False
            return False
        if not self._unified_active:
            # SHADOW must remain observable with partial hardware, but it has
            # zero commit authority.  UNIFIED keeps the stricter capability.
            activation_capability = (InteractionCapability.AVAILABLE
                                     if self._player_turn_mode == PlayerTurnMode.SHADOW
                                     else capability)
            self._player_turn_arbiter.activate(self.state.board, activation_capability)
            self._unified_active = self._player_turn_arbiter.state.name != "INACTIVE"
        return self._unified_active

    def handle_mouse_down(self, mx, my):
        if (BTN_RESUME_SCAN_RECT.collidepoint(mx, my)
                and self.state.manual_override_active and not self.state.game_over):
            self.resume_automatic_scanning()
            return

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
            if self._player_turn_mode == PlayerTurnMode.UNIFIED:
                self.state.set_status("⚠️ UNIFIED: cần xác nhận bàn cờ vật lý trước.", color=(180, 100, 0))
                return
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
                        detector = getattr(self.hw, "yolo_detector", None)
                        if detector and detector.has_baseline():
                            occ = [row[:] for row in detector._baseline_occ]
                            self.state.save_rollback_state(occ, detector._baseline_time)
                        committed = self._commit_human_move(src, dst, p_name, source="MOUSE")
                        self.state.selected_pos = None
                        self.state.manual_override_active = not committed
                        
                        # Retake T1 baseline after manual override
                        if committed and self.hw.cam_monitor:
                            print("[UI] 📸 Đang chụp lại T1 baseline sau khi Override...")
                            self.state.set_status("📸 Cập nhật Mắt Camera...", color=(0, 100, 180), duration=2.0)
                            self.hw.capture_baseline_if_needed(force_delay=1.0)
                    else:
                        print(f"Invalid move: {src}->{dst}")
                        self.state.set_status("❌  Invalid move!", color=(180, 0, 0))
                        self.state.set_invalid_flash(dst[0], dst[1])
                        self.state.selected_pos = None

    def resume_automatic_scanning(self):
        """Install a fresh physical baseline, then re-enable automatic polling.

        The old baseline belongs to the board state before the unresolved
        observation, so retaining it would immediately report the same fault.
        A failed snapshot leaves scanning paused rather than accepting a blind
        recovery.
        """
        detector = getattr(self.hw, "yolo_detector", None)
        camera = getattr(self.hw, "cam_monitor", None)
        if detector is None or camera is None:
            self.state.set_status("❌ Không thể tiếp tục quét: camera chưa sẵn sàng.", color=(180, 0, 0), duration=8.0)
            return False

        # Do not turn an already divergent physical position into the new
        # reference image.  Hardware without an identity verifier keeps the
        # legacy supervised-baseline fallback, but a verifier is authoritative
        # whenever it is available.
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
        self._board_stability_monitor.reset()
        self._observed_baseline_time = None
        captured = bool(self.hw.capture_baseline_if_needed(force_delay=0.0))
        if not captured:
            self.state.set_status("❌ Không lấy được baseline; quét vẫn đang tạm dừng.", color=(180, 0, 0), duration=8.0)
            return False

        self.state.manual_override_active = False
        self._last_move_confirmation_failure = None
        self.state.set_status("✅ Đã tiếp tục tự động quét FEN.", color=(0, 120, 0), duration=6.0)
        return True

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

        # M KEY: Emergency client-side move mode. This is intentionally
        # explicit so a camera failure cannot silently switch control paths.
        elif key == pygame.K_m:
            self.state.manual_override_active = True
            self._board_stability_monitor.reset()
            self.state.set_status(
                "⚠️ Emergency client mode: chọn quân Đỏ rồi chọn ô đích.",
                color=(180, 100, 0), duration=12.0,
            )
            
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
        if self._player_turn_mode == PlayerTurnMode.UNIFIED:
            self.state.set_status("⚠️ UNIFIED: SPACE chỉ yêu cầu poll state-machine.", color=(180, 100, 0))
            return False
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
            has_new_move = self.hw.yolo_detector.has_new_human_move(
                detections, self.state.board, frame=frame, cchess_result=cchess_result
            )
            if has_new_move:
                self._last_move_confirmation_failure = "invalid"
                message = "❌ NƯỚC ĐI KHÔNG HỢP LỆ"
            else:
                # In auto-retry mode, retain earlier positive evidence of a
                # changed move rather than letting a later noisy frame erase it.
                if not auto_retry or self._last_move_confirmation_failure != "invalid":
                    self._last_move_confirmation_failure = "missing"
                message = "❌ KHÔNG NHẬN DIỆN ĐƯỢC NƯỚC ĐI MỚI"
            if not auto_retry:
                self.state.set_status(message, color=(180, 0, 0), duration=8.0)
                self.state.manual_override_active = True
                self.hw.clear_yolo_baseline()
            return False
            
        if not xiangqi.is_valid_move(src, dst, self.state.board, "r"):
            print(f"[SPACE] ❌ YOLO báo nước đi không hợp lệ: {src}->{dst}")
            self._last_move_confirmation_failure = "invalid"
            if not auto_retry:
                self.state.set_status("❌ NƯỚC ĐI KHÔNG HỢP LỆ", color=(180, 0, 0), duration=8.0)
                self.state.set_invalid_flash(dst[0], dst[1])
                self.state.manual_override_active = True
                self.hw.clear_yolo_baseline()
            return False

        # Commit move (state đã được save ở trên rồi)
        self._last_move_confirmation_failure = None
        committed = self._commit_human_move(src, dst, piece, source="SPACE")
        if committed:
            self.state.manual_override_active = False
        return committed

    def try_auto_confirm_move(self, retries=10, retry_seconds=0.2):
        """Reuse the existing rule-validated snapshot flow after hand exit."""
        import time
        if self.state.turn != "r" or self.state.game_over:
            return False
        if not self.hw.yolo_detector or not self.hw.yolo_detector.has_baseline():
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
            if attempt < retries:
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

    def poll_board_stability(self):
        """Commit one legal Red move after repeated stable board observations."""
        if (self.state.turn != "r" or self.state.game_over
                or getattr(self.state, "manual_override_active", False)):
            self._board_stability_monitor.reset()
            return False
        now = time.monotonic()
        sample_interval = getattr(
            getattr(self.hw, "config", None), "BOARD_STABILITY_SAMPLE_INTERVAL_SECONDS", 0.10
        )
        if now - self._last_stability_poll_at < float(sample_interval):
            return False
        self._last_stability_poll_at = now
        if not self.hw.yolo_detector or not self.hw.cam_monitor:
            return False
        if not self.hw.yolo_detector.has_baseline():
            self._board_stability_monitor.reset()
            self._observed_baseline_time = None
            return False

        baseline_time = self.hw.yolo_detector._baseline_time
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

        # UNIFIED only consumes a fully recognized layout.  A missing red
        # piece while being held is deliberately incomplete, never a move.
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
            # SHADOW deliberately leaves legacy authoritative while recording
            # the same decisions in the arbiter state.
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
        occ = [row[:] for row in self.hw.yolo_detector._baseline_occ]
        self.state.save_rollback_state(occ, self.hw.yolo_detector._baseline_time)
        print(
            "[STABILITY] Stable legal move confirmed: "
            f"{piece} {src}->{dst}; samples={self._board_stability_monitor.sample_count}, "
            f"elapsed={self._board_stability_monitor.elapsed_seconds():.2f}s"
        )
        self._last_move_confirmation_failure = None
        committed = self._commit_human_move(src, dst, piece, source="AUTO")
        self._board_stability_monitor.reset()
        return committed
