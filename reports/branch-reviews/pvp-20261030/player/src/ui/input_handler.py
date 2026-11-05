import time
import math
from src.core import xiangqi  # type: ignore
from src.ui.board_renderer import (BoardRenderer, BTN_SURRENDER_RECT, BTN_NEW_GAME_RECT,
                                   BTN_CONTINUE_RECT, BTN_SCAN_FEN_RECT, BTN_CONFIRM_MOVE_RECT,
                                   BTN_EMERGENCY_RECT, BTN_ROLLBACK_RECT, BTN_PICK_TEST_RECT, NUM_COLS, NUM_ROWS)  # type: ignore
from src.ui.board_renderer import BTN_PICK_RETRY_RECT, BTN_PICK_CANCEL_RECT
from src.core.game_state import GameState
from src.core.visual_move_coordinator import execute_pending_ai_motion
from src.vision.pick_consensus import PickTargetUnavailable
from src.vision.board_stability_monitor import BoardStabilityMonitor
from src.vision.player_turn_arbiter import PlayerTurnArbiter
from src.vision.player_turn_types import BoardObservation, CommitRequest, InteractionCapability, PlayerTurnMode, Visibility
from src.core.human_move_commit_coordinator import HumanMoveCommitCoordinator
from src.vision.legal_successor_matcher import LegalSuccessorMatcher
from src.vision.player_turn_types import MatchKind

CHECK_STATUS_MESSAGE = (
    "⚠️ CHECK — Your General is in check. "
    "Block, capture, or move your General."
)


class InputHandler:
    """Manages Pygame Key/Mouse events and bridges them to GameState and HardwareManager."""
    def __init__(self, game_state, hw_manager):
        self.state = game_state
        self.hw = hw_manager
        self._motion_thread = None
        self._last_move_confirmation_failure = None
        stability_config = getattr(self.hw, "config", None)
        self._board_stability_monitor = BoardStabilityMonitor(
            stability_seconds=getattr(stability_config, "BOARD_STABILITY_SECONDS", 1.2),
            min_samples=getattr(stability_config, "BOARD_STABILITY_MIN_SAMPLES", 3),
        )
        self._observed_baseline_time = None
        self._last_stability_poll_at = 0.0
        self._last_board_warning_check_at = 0.0
        self._board_warning_candidate = None
        self._board_warning_samples = 0
        self._board_warning_message = None
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

    def _rejected_red_move_status(self, src, dst):
        """Explain an invalid Red move without hiding an active check threat."""
        if xiangqi.is_king_in_check("r", self.state.board):
            return CHECK_STATUS_MESSAGE
        return f"❌ Illegal move: {xiangqi.format_move(src, dst)} — move not accepted."

    def _check_board_warning(self, cchess_result, now):
        """Surface unexplained full-board changes without mutating game state."""
        try:
            interval = float(getattr(
                getattr(self.hw, "config", None), "BOARD_WARNING_CHECK_INTERVAL_SECONDS", 2.0
            ))
        except (TypeError, ValueError):
            interval = 2.0
        interval = max(0.1, interval) if math.isfinite(interval) else 2.0
        if now - self._last_board_warning_check_at < interval:
            return
        self._last_board_warning_check_at = now

        occluded = getattr(self.hw, "is_board_occluded", None)
        if callable(occluded) and occluded():
            self._clear_board_warning()
            return

        layout = cchess_result.get("board") if cchess_result and cchess_result.get("success") else None
        if layout is None:
            self._clear_board_warning()
            return
        match = LegalSuccessorMatcher(self.state.board).match(layout)
        if match.kind in (MatchKind.BASELINE_EQUAL, MatchKind.UNIQUE, MatchKind.UNAVAILABLE):
            self._clear_board_warning()
            return
        try:
            candidate = (match.kind, tuple(tuple(row) for row in layout))
        except TypeError:
            self._board_warning_candidate = None
            self._board_warning_samples = 0
            return
        if candidate != self._board_warning_candidate:
            self._board_warning_candidate = candidate
            self._board_warning_samples = 1
            return
        self._board_warning_samples += 1
        try:
            minimum = max(1, int(getattr(
                getattr(self.hw, "config", None), "BOARD_WARNING_MIN_STABLE_SAMPLES", 2
            )))
        except (TypeError, ValueError):
            minimum = 2
        if self._board_warning_samples < minimum:
            return
        illegal_move = self._single_observed_red_move(layout)
        if illegal_move is not None and illegal_move[0] == illegal_move[1]:
            message = f"⚠️ Unstable FEN detection at {xiangqi.format_square(illegal_move[0])}"
        elif illegal_move is not None:
            message = self._rejected_red_move_status(*illegal_move)
        else:
            message = "⚠️ Board does not match the expected position."
        color = (180, 0, 0) if message == CHECK_STATUS_MESSAGE else (180, 100, 0)
        self.state.set_status(message, color=color, duration=5.0)
        self._board_warning_message = message

    def _clear_board_warning(self):
        self._board_warning_candidate = None
        self._board_warning_samples = 0
        set_status = getattr(self.state, "set_status", None)
        if (self._board_warning_message is not None
                and getattr(self.state, "status_message", None) == self._board_warning_message
                and callable(set_status)):
            set_status("", duration=0)
        self._board_warning_message = None

    def _single_observed_red_move(self, layout):
        """Return one observed Red source/destination pair, if unambiguous."""
        sources, destinations = [], []
        try:
            for row in range(10):
                for col in range(9):
                    expected = self.state.board[row][col]
                    observed = layout[row][col]
                    if not isinstance(observed, str):
                        return None
                    if expected.startswith("r") and observed != expected:
                        sources.append((col, row))
                    if observed.startswith("r") and observed != expected:
                        destinations.append((col, row))
        except (IndexError, TypeError):
            return None
        if len(sources) == 1 and len(destinations) == 1:
            return sources[0], destinations[0]
        return None

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

    def _defer_motion(self, operation):
        """One physical job at a time; the worker owns state until completion."""
        import threading
        if not getattr(getattr(self.hw, "config", None), "VISUAL_MOTION_ASYNC_ENABLED", False):
            return False
        if threading.current_thread() is getattr(self, "_motion_thread", None):
            return False
        if getattr(self.state, "physical_motion_busy", False):
            return True
        self.state.physical_motion_busy = True
        def run():
            try:
                operation()
            finally:
                self.state.physical_motion_busy = False
        self._motion_thread = threading.Thread(target=run, name="visual-robot-motion", daemon=True)
        self._motion_thread.start()
        return True

    def start_pending_ai_motion(self):
        if self._defer_motion(self.start_pending_ai_motion):
            return
        source, destination = self.state.pending_ai_move["move"]
        try:
            execute_pending_ai_motion(self.state, self.hw, self.hw.config)
            self._finalize_pending_ai_move("Your turn!", (0, 100, 180))
        except PickTargetUnavailable as exc:
            self.state.pause_visual_pick("ai", source, destination, exc)
        except Exception as exc:
            if self.state.pending_ai_move is None:
                self.state.manual_override_active = True
                self.state.set_status(f"FEN đã cập nhật; lỗi đồng bộ: {exc}. V để lấy lại baseline.", duration=30)
                return
            self.state.physical_sync_fault = True
            self.state.snapshot_continue_required = True
            self.state.snapshot_continue_can_commit_pending = False
            self.state.set_status(f"Robot dừng: {exc}. Kiểm tra bàn thật rồi V.",
                                  color=(180, 0, 0), duration=3600)

    def handle_mouse_down(self, mx, my):
        import pygame  # type: ignore
        if getattr(self.state, "physical_motion_busy", False):
            return
        if getattr(self.state, "visual_pick_retry", None):
            if BTN_PICK_RETRY_RECT.collidepoint(mx, my):
                self.handle_keyboard(pygame.K_r)
                return
            if BTN_PICK_CANCEL_RECT.collidepoint(mx, my):
                self.handle_keyboard(pygame.K_x)
                return
            if not (BTN_NEW_GAME_RECT.collidepoint(mx, my) or BTN_SURRENDER_RECT.collidepoint(mx, my)):
                return
        client_actions = (
            (BTN_SCAN_FEN_RECT, pygame.K_v),
            (BTN_CONFIRM_MOVE_RECT, pygame.K_SPACE),
            (BTN_EMERGENCY_RECT, pygame.K_m),
            (BTN_ROLLBACK_RECT, pygame.K_z),
            (BTN_PICK_TEST_RECT, pygame.K_t),
        )
        for rect, key in client_actions:
            if rect.collidepoint(mx, my) and not self.state.game_over:
                self.handle_keyboard(key)
                return

        if BTN_CONTINUE_RECT.collidepoint(mx, my):
            if getattr(self.state, "pick_test_mode", False) or getattr(self.state, "pick_test_resume_required", False):
                return
            if (getattr(self.state, "snapshot_continue_required", False)
                    and not self.state.game_over):
                self._continue_after_snapshot_pause()
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

        if getattr(self.state, "pick_test_mode", False):
            self._handle_pick_test_click(mx, my)
            return
        if getattr(self.state, "pick_test_resume_required", False):
            return

        # Manual Override (Mouse Drag)
        if (self.state.allow_mouse_move or self.state.manual_override_active) and not self.state.game_over:
            if self._player_turn_mode == PlayerTurnMode.UNIFIED:
                self.state.set_status("⚠️ UNIFIED: cần xác nhận bàn cờ vật lý trước.", color=(180, 100, 0))
                return
            c, r = BoardRenderer.pixel_to_grid(mx, my)
            if 0 <= c < NUM_COLS and 0 <= r < NUM_ROWS:
                clicked_piece = self.state.board[r][c]
                
                # Select a piece
                active_color = self.state.turn
                if clicked_piece.startswith(active_color):
                    self.state.selected_pos = (c, r)
                    
                # Move a selected piece
                elif self.state.selected_pos:
                    src, dst = self.state.selected_pos, (c, r)
                    p_name = self.state.board[src[1]][src[0]]
                    
                    if xiangqi.is_valid_move(src, dst, self.state.board, active_color):
                        print("[UI] 🖱️ Người dùng đi cờ trên màn hình.")
                        detector = getattr(self.hw, "yolo_detector", None)
                        if detector and detector.has_baseline():
                            occ = [row[:] for row in detector._baseline_occ]
                            self.state.save_rollback_state(occ, detector._baseline_time)
                        if getattr(self.state, "emergency_mode", False):
                            emergency_commit = getattr(self.state, "process_emergency_move", None)
                            if callable(emergency_commit):
                                emergency_commit(src, dst, p_name)
                                committed = True
                            else:
                                # Lightweight test/dry-run state objects only
                                # expose the legacy Red commit hook.
                                committed = (active_color == "r" and
                                             self._commit_human_move(src, dst, p_name, source="EMERGENCY"))
                        elif active_color == "r":
                            committed = self._commit_human_move(src, dst, p_name, source="MOUSE")
                        else:
                            committed = False
                        self.state.selected_pos = None
                        # Emergency mode remains active until the operator
                        # presses M again; normal mouse fallback keeps its old
                        # one-move behavior.
                        if not getattr(self.state, "emergency_mode", False):
                            self.state.manual_override_active = not committed
                        
                        # Retake T1 baseline after manual override
                        if committed and self.hw.cam_monitor:
                            print("[UI] 📸 Đang chụp lại T1 baseline sau khi Override...")
                            self.state.set_status("📸 Cập nhật Mắt Camera...", color=(0, 100, 180), duration=2.0)
                            self.hw.capture_baseline_if_needed(force_delay=1.0)
                    else:
                        print(f"Invalid move: {xiangqi.format_move(src, dst)}")
                        self.state.set_status(
                            self._rejected_red_move_status(src, dst),
                            color=(180, 0, 0),
                        )
                        self.state.set_invalid_flash(dst[0], dst[1])
                        self.state.selected_pos = None

    def _toggle_pick_test(self):
        if getattr(self.state, "pick_test_mode", False):
            self.state.visual_pick_retry = None
            self.state.pick_test_mode = False
            self.state.selected_pos = None
            self.state.set_status("Test đã tắt. Khôi phục bàn ban đầu rồi New Game để chơi; T để test tiếp.", duration=30)
            return
        worker = getattr(self.state, "ai_thread", None)
        if (getattr(self.state, "ai_thinking", False)
                or (worker is not None and worker.is_alive())
                or getattr(self.state, "pending_ai_move", None)):
            self.state.set_status("Chờ hoàn tất/xử lý lượt AI trước khi vào test.", duration=8)
            return
        if getattr(self.state, "pick_test_board", None) is None:
            self.state.pick_test_board = [row[:] for row in self.state.board]
        self.state.pick_test_mode = True
        self.state.pick_test_resume_required = True
        self.state.emergency_mode = False
        self.state.selected_pos = None
        self._board_stability_monitor.reset()
        self.state.set_status("TEST: chọn quân Đỏ/Đen rồi chọn ô trống. T để thoát.", duration=30)

    def _handle_pick_test_click(self, mx, my):
        col, row = BoardRenderer.pixel_to_grid(mx, my)
        if not (0 <= col < NUM_COLS and 0 <= row < NUM_ROWS):
            return
        board = self.state.pick_test_board
        if board[row][col] != ".":
            self.state.selected_pos = (col, row)
            self.state.set_status(f"TEST: đã chọn ({col},{row}); H xem XY ở SAFE_Z / chọn ô trống để gắp.", duration=20)
            return
        source = self.state.selected_pos
        if source is None:
            return
        destination = (col, row)
        self.state.selected_pos = None
        self._run_pick_test(source, destination)

    def _run_hover_test(self, source):
        if self._defer_motion(lambda: self._run_hover_test(source)):
            return
        try:
            self.state.set_status("HOVER: đo tâm và đến SAFE_Z...", duration=30)
            target = self.hw.execute_hover_test(source)
            self.state.set_status(f"HOVER: ({target.col:.3f},{target.row:.3f}); dừng trên quân. Không gắp.", duration=30)
        except Exception as exc:
            print(f"[HOVER TEST] {exc}")
            self.state.set_status(f"HOVER dừng: {exc}", duration=30)

    def _run_pick_test(self, source, destination, request=None):
        if self._defer_motion(lambda: self._run_pick_test(source, destination, request)):
            return
        board = self.state.pick_test_board

        def validate_request():
            if request is not None and not self.state.visual_pick_retry_is_current(request):
                raise RuntimeError("Stale test retry; no motion/board update authorized")

        try:
            self.state.set_status("TEST: arm đang gắp/thả...", duration=30)
            validate_request()
            # The worker owns this request; also validate at the motion boundary.
            if request is not None:
                target = self.hw.execute_pick_place_test(source, destination, validate_request=validate_request)
            else:
                target = self.hw.execute_pick_place_test(source, destination)
            validate_request()
            col, row = destination
            board[row][col] = board[source[1]][source[0]]
            board[source[1]][source[0]] = "."
            self.state.visual_pick_retry = None
            self.state.set_status(f"TEST xong: ({target.col:.3f},{target.row:.3f}) → ({col},{row}). Chọn quân để test tiếp.", duration=20)
        except PickTargetUnavailable as exc:
            if exc.stage != "pre_pick":
                self.state.visual_pick_retry = None
                self.state.set_status("TEST dừng sau chuyển động; kiểm tra bàn thật, không tự thử lại.", duration=30)
            else:
                GameState.pause_visual_pick(self.state, "test", source, destination, exc)
        except Exception as exc:
            self.state.visual_pick_retry = None
            print(f"[PICK TEST] {exc}")
            self.state.set_status(f"TEST dừng: {exc}", color=(180, 0, 0), duration=30)

    def _retry_visual_pick(self):
        if self._defer_motion(self._retry_visual_pick):
            return
        request = self.state.visual_pick_retry
        if not self.state.visual_pick_retry_is_current(request):
            self.state.visual_pick_retry = None
            self.state.set_status("Yêu cầu thử lại đã hết hiệu lực; không chạy arm.", duration=30)
            return
        if request["owner"] == "test":
            self._run_pick_test(request["source"], request["destination"], request)
            return
        finalization_started = False
        try:
            execute_pending_ai_motion(self.state, self.hw, self.hw.config, request["stage"])
            if not self.state.visual_pick_retry_is_current(request):
                raise RuntimeError("Retry changed ownership before finalization")
            finalization_started = True
            self._finalize_pending_ai_move("Đã xác nhận nước đi — đến lượt bạn.", (0, 120, 0))
        except PickTargetUnavailable as exc:
            self.state.pause_visual_pick("ai", request["source"], request["destination"], exc)
        except Exception as exc:
            self.state.visual_pick_retry = None
            if finalization_started and self.state.pending_ai_move is None:
                # Commit already succeeded. API/baseline failure must neither
                # replay the arm nor pretend the FEN stayed at the old board.
                self.state.physical_sync_fault = False
                self.state.snapshot_continue_required = False
                self.state.snapshot_continue_can_commit_pending = False
                self.state.manual_override_active = True
                self.state.set_status(f"Nước đi đã hoàn tất/FEN đã cập nhật; lỗi đồng bộ: {exc}. V để lấy lại baseline.", duration=30)
                return
            self.state.physical_sync_fault = True
            self.state.snapshot_continue_required = True
            self.state.snapshot_continue_can_commit_pending = False
            self.state.set_status(f"Thử lại dừng: {exc}. Kiểm tra bàn thật rồi V; FEN giữ nguyên.", duration=3600)

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
        self.state.emergency_mode = False
        self._last_move_confirmation_failure = None
        self.state.set_status("✅ Đã tiếp tục tự động quét FEN.", color=(0, 120, 0), duration=6.0)
        return True

    def handle_keyboard(self, key):
        import pygame  # type: ignore
        if getattr(self.state, "physical_motion_busy", False):
            return
        if self.state.game_over:
            return

        if getattr(self.state, "visual_pick_retry", None):
            if key == pygame.K_r:
                self._retry_visual_pick()
            elif key == pygame.K_x:
                self.state.cancel_visual_pick_retry()
            elif key == pygame.K_t and self.state.visual_pick_retry["owner"] == "test":
                self._toggle_pick_test()
            else:
                self.state.set_status("Đang chờ đo tâm: R thử lại cùng nước đi / X hủy.", duration=30)
            return

        if key == pygame.K_h and getattr(self.state, "pick_test_mode", False):
            source = self.state.selected_pos
            if source is None:
                self.state.set_status("HOVER: chọn quân trước rồi nhấn H.", duration=15)
            else:
                self._run_hover_test(source)
            return
        if key == pygame.K_d and getattr(self.state, "pick_test_mode", False):
            if self.hw.cam_monitor:
                self.hw.cam_monitor.pick_debug_frame = None
            self.state.set_status("Đã trở lại camera live.", duration=10)
            return
        if key == pygame.K_t:
            self._toggle_pick_test()
            return
        if getattr(self.state, "pick_test_mode", False) or getattr(self.state, "pick_test_resume_required", False):
            self.state.set_status("Test đang tạm dừng game. T để test; khôi phục bàn rồi New Game để chơi.", duration=15)
            return

        if key == pygame.K_v:
            if self.state.physical_sync_fault:
                self._reconcile_physical_sync_fault()
            else:
                self.resume_automatic_scanning()
            return

        # Z KEY: Rollback
        if key == pygame.K_z:
            self.state.handle_rollback(self.hw)

        # M KEY: Emergency client-side move mode. This is intentionally
        # explicit so a camera failure cannot silently switch control paths.
        elif key == pygame.K_m:
            enabled = not getattr(self.state, "emergency_mode", False)
            self.state.emergency_mode = enabled
            self.state.manual_override_active = enabled
            self._board_stability_monitor.reset()
            self.state.set_status(
                ("⚠️ Manual/Emergency mode active — automatic camera confirmation is paused."
                 if enabled else "✅ Đã tắt Emergency mode — tiếp tục quét camera."),
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
            self.state.snapshot_continue_required = False
            retry = getattr(self.state, "prepare_ai_retry_after_physical_miss", None)
            if callable(retry) and retry():
                self.state.set_status(
                    "↩️ AI retrying after a physical board mismatch.",
                    color=(0, 100, 180), duration=10.0,
                )
            else:
                self.state.set_status(
                    "↩️ Bàn thật vẫn ở FEN cũ, nhưng không thể khởi động lại lượt AI.",
                    color=(180, 0, 0), duration=10.0,
                )
            return

        if self.hw.verify_physical_board(pending["expected_board"]):
            self._finalize_pending_ai_move(
                "✅ Đã xác nhận bàn thật — đến lượt bạn.", (0, 100, 180)
            )
            return

        src, dst = pending["move"]
        if pending.get("captured_piece") != ".":
            # CChess can misclassify unrelated pieces, making a whole-board
            # FEN comparison too strict for the supervised capture recovery.
            # V is pressed only after the operator has completed this known
            # pending move, so the source/destination occupancy check is the
            # relevant physical evidence here.
            verify_geometry = getattr(self.hw, "verify_visual_move", None)
            geometry_matches = False
            if callable(verify_geometry):
                try:
                    geometry_matches = verify_geometry(src, dst)
                except Exception as exc:
                    print(f"[BOARD SYNC] Manual-capture geometry check failed: {exc}")
            if geometry_matches:
                self._finalize_pending_ai_move(
                    "✅ Đã xác nhận nước ăn thủ công — FEN đã cập nhật.", (0, 120, 0)
                )
                return
            self.state.set_status(
                "⚠️ Nước ăn chưa hoàn tất: chuyển quân Đen "
                f"({src[0]},{src[1]})→({dst[0]},{dst[1]}) rồi nhấn V.",
                color=(180, 100, 0), duration=20.0,
            )
        else:
            self.state.set_status(
                "❌ Bàn thật không khớp trước/sau nước đi. Chỉnh tay rồi nhấn V.",
                color=(180, 0, 0), duration=15.0,
            )

    def _finalize_pending_ai_move(self, status_message, status_color):
        """Commit the one pending AI move after a verified recovery path."""
        if not self.state.commit_pending_ai_move():
            return False
        self.state.snapshot_continue_required = False
        self.state.api_client.send_move_update_board(self.state.current_fen)
        if xiangqi.get_king_pos("r", self.state.board) is None:
            self.state.handle_game_over("b")
            self.state.api_client.end_match(winner="BLACK", reason="CHECKMATE")
        else:
            self.hw.capture_baseline_if_needed(force_delay=1.0)
            self.state.set_status(status_message, color=status_color, duration=8.0)
        return True

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
            print(f"[YOLO] 👉 Nhận diện nước đi: {xiangqi.format_move(src, dst)}")
            
        # Verify result
        if src is None:
            print("[SPACE] ❌ YOLO KHÔNG thấy nước đi hợp lệ!")
            has_new_move = self.hw.yolo_detector.has_new_human_move(
                detections, self.state.board, frame=frame, cchess_result=cchess_result
            )
            if has_new_move:
                self._last_move_confirmation_failure = "invalid"
                message = "⚠️ Board changed, but one legal move could not be identified."
            else:
                # In auto-retry mode, retain earlier positive evidence of a
                # changed move rather than letting a later noisy frame erase it.
                if not auto_retry or self._last_move_confirmation_failure != "invalid":
                    self._last_move_confirmation_failure = "missing"
                message = "⚠️ No legal move could be identified."
            if not auto_retry:
                self.state.set_status(message, color=(180, 0, 0), duration=8.0)
                self.state.manual_override_active = True
                self.state.snapshot_continue_required = True
                self.state.snapshot_continue_can_commit_pending = False
                self.hw.clear_yolo_baseline()
            return False
            
        if not xiangqi.is_valid_move(src, dst, self.state.board, "r"):
            print(f"[SPACE] ❌ YOLO báo nước đi không hợp lệ: {xiangqi.format_move(src, dst)}")
            self._last_move_confirmation_failure = "invalid"
            if not auto_retry:
                self.state.set_status(
                    self._rejected_red_move_status(src, dst),
                    color=(180, 0, 0), duration=8.0,
                )
                self.state.set_invalid_flash(dst[0], dst[1])
                self.state.manual_override_active = True
                self.state.snapshot_continue_required = True
                self.state.snapshot_continue_can_commit_pending = False
                self.hw.clear_yolo_baseline()
            return False

        # Commit move (state đã được save ở trên rồi)
        self._last_move_confirmation_failure = None
        committed = self._commit_human_move(src, dst, piece, source="SPACE")
        if committed:
            self.state.manual_override_active = False
            self.state.emergency_mode = False
            self.state.snapshot_continue_required = False
        return committed

    def _continue_after_snapshot_pause(self):
        """Apply the operator-approved recovery shown by the Continue button."""
        if (getattr(self.state, "physical_sync_fault", False)
                and getattr(self.state, "snapshot_continue_can_commit_pending", False)
                and getattr(self.state, "pending_ai_move", None)):
            # The robot command completed but visual confirmation returned e.g.
            # 0/3.  Continue is an explicit operator override to advance the
            # FEN to the move already made on the physical board.
            if self.state.commit_pending_ai_move():
                self.state.api_client.send_move_update_board(self.state.current_fen)
        elif getattr(self.state, "physical_sync_fault", False):
            # A robot exception is not proof that it completed the move.  Keep
            # the original verified reconciliation path instead of guessing.
            self._reconcile_physical_sync_fault()
            return
        else:
            # Do not install a new baseline blindly: the physical Red move may
            # exist while FEN still describes the old board.  CChess must
            # prove either the old board or one unique legal successor.
            recognizer = getattr(self.hw, "recognize_board_state", None)
            camera = getattr(self.hw, "cam_monitor", None)
            frame, _ = camera.get_fresh_snapshot() if camera else (None, [])
            result = recognizer(frame) if callable(recognizer) and frame is not None else None
            layout = result.get("board") if result and result.get("success") else None
            match = LegalSuccessorMatcher(self.state.board).match(layout)
            if match.kind == MatchKind.UNIQUE:
                src, dst = match.move
                piece = self.state.board[src[1]][src[0]]
                self._commit_human_move(src, dst, piece, source="CONTINUE")
            elif match.kind != MatchKind.BASELINE_EQUAL:
                self.state.snapshot_continue_required = False
                self.state.emergency_mode = True
                self.state.manual_override_active = True
                self.state.set_status(
                    "⚠️ Không thể xác nhận FEN. Emergency mode đã bật để nhập nước đi.",
                    color=(180, 100, 0), duration=12.0,
                )
                return
        self.state.physical_sync_fault = False
        self.state.snapshot_continue_required = False
        self.state.snapshot_continue_can_commit_pending = False
        self.state.manual_override_active = False
        self.state.emergency_mode = False
        self._board_stability_monitor.reset()
        capture = getattr(self.hw, "capture_baseline_if_needed", None)
        captured = bool(capture(force_delay=0.0)) if callable(capture) else False
        message = ("✅ Continue: FEN đã tiếp tục, đang quét bàn cờ mới."
                   if captured else "✅ Continue: FEN đã tiếp tục. Nhấn SPACE để tạo baseline mới.")
        self.state.set_status(message, color=(0, 120, 0), duration=10.0)

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
        if (getattr(self.state, "physical_motion_busy", False)
                or self.state.turn != "r" or self.state.game_over
                or getattr(self.state, "visual_pick_retry", None)
                or getattr(self.state, "pick_test_mode", False)
                or getattr(self.state, "pick_test_resume_required", False)
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

        self._check_board_warning(cchess_result, now)

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
