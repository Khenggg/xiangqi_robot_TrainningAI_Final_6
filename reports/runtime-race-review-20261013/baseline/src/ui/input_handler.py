import time
import math
import config
from src.core import xiangqi  # type: ignore
from src.ui.board_renderer import (BoardRenderer, BTN_SURRENDER_RECT, BTN_NEW_GAME_RECT,
                                   BTN_CONTINUE_RECT, BTN_SCAN_FEN_RECT, BTN_CONFIRM_MOVE_RECT,
                                   BTN_EMERGENCY_RECT, BTN_ROLLBACK_RECT, BTN_PICK_TEST_RECT, BTN_HOVER_RECT, NUM_COLS, NUM_ROWS)  # type: ignore
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
        self._last_move_confirmation_failure = None
        stability_config = getattr(self.hw, "config", None)
        self._board_stability_monitor = BoardStabilityMonitor(
            stability_seconds=getattr(stability_config, "BOARD_STABILITY_SECONDS", 1.2),
            min_samples=getattr(stability_config, "BOARD_STABILITY_MIN_SAMPLES", 3),
        )
        self._observed_baseline_time = None
        self._last_stability_poll_at = 0.0
        self._last_stability_sample_at = 0.0
        self._stability_sample_after = 0.0
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
        match = LegalSuccessorMatcher(self.state.board, player_color=getattr(self.state, "turn", "r")).match(layout)
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
        permission = getattr(self.state, "is_human_turn", self.state.turn == "r")
        human_turn = permission() if callable(permission) else bool(permission)
        if (not human_turn or self.state.game_over
                or getattr(self.state, "physical_sync_fault", False)
                or getattr(self.state, "move_sync_error", None)
                or getattr(self.state, "turn_confirmation_required", False)
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
            self._player_turn_arbiter.activate(self.state.board, activation_capability,
                                               player_color=self.state.turn)
            self._unified_active = self._player_turn_arbiter.state.name != "INACTIVE"
        return self._unified_active

    def _unified_observation_confidence(self, result):
        """Validate cached recognition metadata without camera reads or inference."""
        if not result or result.get("success") is not True or result.get("quality_ok") is False:
            return None
        confidence = result.get("confidence")
        if confidence is None:
            # The camera worker may provide its explicit quality decision instead.
            return 1.0 if result.get("quality_ok") is True else None
        try:
            if len(confidence) != 10 or any(len(row) != 9 for row in confidence):
                return None
            values = [float(cell) for row in confidence for cell in row]
            threshold = float(getattr(getattr(self.hw, "config", None), "CCHESS_MIN_CELL_CONFIDENCE", 0.5))
            if (not math.isfinite(threshold) or not 0 <= threshold <= 1
                    or any(not math.isfinite(v) or not 0 <= v <= 1 for v in values)
                    or min(values) < threshold):
                return None
            return sum(values) / len(values)
        except (TypeError, ValueError):
            return None

    def _motion_busy(self):
        worker = getattr(self.hw, "motion_worker", None)
        return worker is not None and worker.busy is True

    def _queue_or_run(self, operation):
        worker = getattr(self.hw, "motion_worker", None)
        if (worker is None or getattr(self.hw, "simulation_runtime", None) is not None
                or getattr(self.hw, "dry_run", False) is True):
            return operation()
        if not worker.start(operation, lambda value, error: self.state.set_status(
                f"Motion worker failed: {error}", duration=30) if error else None):
            self.state.set_status("Đang có thao tác robot; chờ hoàn tất.", duration=8)

    def _retry_visual_pick(self):
        from src.core.visual_move_coordinator import retry_is_current
        request = getattr(self.state, "test_pick_retry", None)
        if request is not None:
            if (request["epoch"] != self.state.game_epoch or request["ids"] != self.state.pick_test_piece_ids
                    or request["board"] != self.state.pick_test_board or not self.state.pick_test_mode):
                self.state.test_pick_retry = None
                self.state.set_status("Test retry đã hết hiệu lực; không chạy robot.", duration=20)
                return
            self._queue_or_run(lambda: self._run_pick_test(request["source"], request["destination"]))
            return
        if not retry_is_current(self.state):
            self.state.set_status("Không có nước chờ hợp lệ để thử lại.", duration=10)
            return
        from src.core.ai_execution import execute_ai_move
        move = self.state.pending_ai_move["move"]
        def retry():
            if execute_ai_move(self.state, self.hw, move, self.hw.dry_run, True):
                try:
                    self.state.api_client.send_move_update_board(self.state.current_fen)
                    if (xiangqi.get_king_pos(self.state.turn, self.state.board) is None
                            or not xiangqi.find_all_valid_moves(self.state.turn, self.state.board)):
                        self.state.handle_game_over("b")
                    else:
                        self.hw.capture_baseline_if_needed(force_delay=0)
                except Exception as exc:
                    self.state.set_status(f"Nước đã commit; cập nhật API/baseline lỗi: {exc}", duration=30)
        self._queue_or_run(retry)

    def _run_hover_test(self):
        source = self.state.selected_pos
        if not self.state.pick_test_mode or source is None or self.state.pick_test_fault:
            self.state.set_status("T: bật test, chọn quân rồi H để hover.", duration=12)
            return
        def hover():
            try:
                self.hw.execute_hover_test(source)
                self.state.set_status("Hover xong: chỉ tiếp cận; chưa gắp hoặc thay đổi quân.", duration=20)
            except Exception as exc:
                self.state.set_status(f"Hover bị chặn: {exc}", color=(180,0,0), duration=30)
        self._queue_or_run(hover)

    def handle_mouse_down(self, mx, my):
        if self._motion_busy():
            return
        if (getattr(self.state, "visual_pick_retry", None)
                and not BTN_CONTINUE_RECT.collidepoint(mx, my) and not BTN_SCAN_FEN_RECT.collidepoint(mx, my)):
            return
        import pygame  # type: ignore
        client_actions = (
            (BTN_SCAN_FEN_RECT, pygame.K_v),
            (BTN_CONFIRM_MOVE_RECT, pygame.K_SPACE),
            (BTN_EMERGENCY_RECT, pygame.K_m),
            (BTN_ROLLBACK_RECT, pygame.K_z),
            (BTN_PICK_TEST_RECT, pygame.K_t),
            (BTN_HOVER_RECT, pygame.K_h),
        )
        for rect, key in client_actions:
            if rect.collidepoint(mx, my) and not self.state.game_over:
                self.handle_keyboard(key)
                return

        if BTN_CONTINUE_RECT.collidepoint(mx, my) and (getattr(self.state, "visual_pick_retry", None) or getattr(self.state, "test_pick_retry", None)):
            self._retry_visual_pick()
            return
        if BTN_CONTINUE_RECT.collidepoint(mx, my):
            if (getattr(self.state, "snapshot_continue_required", False)
                    and not self.state.game_over):
                self._queue_or_run(self._continue_after_snapshot_pause)
            return

        # Surrender Button
        if BTN_SURRENDER_RECT.collidepoint(mx, my) and not self.state.game_over:
            print("[GAME] YOU SURRENDER!")
            winner = 'b' if self.state.turn == 'r' else 'r'
            self.state.handle_game_over(winner, reason='RESIGN')
            self.state.api_client.end_match(winner="BLACK" if winner == 'b' else "RED", reason="RESIGN")
            return

        # New Game Button
        if BTN_NEW_GAME_RECT.collidepoint(mx, my):
            self._queue_or_run(lambda: self.state.reset_game(self.hw))
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
                        def commit_override():
                            detector = getattr(self.hw, "yolo_detector", None)
                            if detector and detector.has_baseline():
                                occ = [row[:] for row in detector._baseline_occ]
                                self.state.save_rollback_state(occ, detector._baseline_time)
                            if getattr(self.state, "emergency_mode", False):
                                emergency_commit = getattr(self.state, "process_emergency_move", None)
                                if callable(emergency_commit):
                                    committed = emergency_commit(src, dst, p_name) is True
                                else:
                                    # Lightweight test/dry-run state objects only
                                    # expose the legacy Red commit hook.
                                    committed = (active_color == "r" and
                                                 self._commit_human_move(src, dst, p_name, source="EMERGENCY"))
                            elif active_color == "r" or bool(getattr(self.state, "is_human_turn", False)):
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
                                if not self.hw.capture_baseline_if_needed(force_delay=1.0):
                                    self.state.manual_override_active = True
                                    self.state.snapshot_continue_required = True
                                    self.state.set_status("Baseline camera lỗi; bấm V để đối soát.", duration=30)
                        self._queue_or_run(commit_override)
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
            self.state.test_pick_retry = None
            self.state.pick_test_mode = False
            self.state.selected_pos = None
            self.state.set_status("Test đã tắt. Khôi phục bàn ban đầu rồi New Game để chơi; T để test tiếp.", duration=30)
            return
        if self.state.pick_test_fault or self.state.physical_sync_fault or self.state.move_sync_error or self.state.pending_move:
            self.state.set_status("Test bị khóa: khôi phục bàn rồi New Game để đối soát.", duration=30)
            return
        worker = getattr(self.state, "ai_thread", None)
        if (getattr(self.state, "ai_thinking", False)
                or (worker is not None and worker.is_alive())
                or getattr(self.state, "pending_ai_move", None)):
            self.state.set_status("Chờ hoàn tất/xử lý lượt AI trước khi vào test.", duration=8)
            return
        if getattr(self.state, "pick_test_board", None) is None:
            self.state.pick_test_board = [row[:] for row in self.state.board]
            self.state.pick_test_piece_ids = dict(self.state.piece_ids)
        self.state.pick_test_mode = True
        self.state.pick_test_resume_required = True
        self.state.emergency_mode = False
        self.state.selected_pos = None
        self._board_stability_monitor.reset()
        self.state.set_status("TEST: chọn quân Đỏ/Đen rồi chọn ô trống. T để thoát.", duration=30)


    def _handle_pick_test_click(self, mx, my):
        if self.state.pick_test_fault:
            self.state.set_status(f"Test bị khóa: {self.state.pick_test_fault}", duration=30)
            return
        col, row = BoardRenderer.pixel_to_grid(mx, my)
        if not (0 <= col < NUM_COLS and 0 <= row < NUM_ROWS):
            return
        board = self.state.pick_test_board
        if board[row][col] != ".":
            self.state.selected_pos = (col, row)
            self.state.set_status(f"TEST: đã chọn ({col},{row}); chọn ô trống để chạy arm.", duration=20)
            return
        source = self.state.selected_pos
        if source is None:
            return
        destination = (col, row)
        self.state.selected_pos = None
        self._queue_or_run(lambda: self._run_pick_test(source, destination))

    def _run_pick_test(self, source, destination):
        col, row = destination
        board = self.state.pick_test_board
        from src.vision.pick_consensus import PickTargetUnavailable
        try:
            self.state.set_status("TEST: arm đang gắp/thả...", duration=30)
            from src.domain.game_move import MoveContext, MoveActor
            ids = self.state.pick_test_piece_ids
            src, dst = (source[1], source[0]), (row, col)
            context = MoveContext(ids[src], src, dst, MoveActor.ROBOT)
            self.hw.execute_pick_place_test(source, destination, move_context=context)
            updated = dict(ids)
            updated[dst] = updated.pop(src)
            if not self.hw.sync_committed_board(updated):
                raise RuntimeError("Không đồng bộ được simulation sau test; cần khôi phục bàn")
            self.state.test_pick_retry = None
            self.state.pick_test_piece_ids = updated
            board[row][col] = board[source[1]][source[0]]
            board[source[1]][source[0]] = "."
            self.state.set_status(f"TEST xong: {source} → {destination}. Chọn quân để test tiếp.", duration=20)
        except PickTargetUnavailable as exc:
            if exc.stage != "pre_pick":
                self.state.pick_test_fault = str(exc)
                return
            self.state.test_pick_retry = dict(source=source, destination=destination,
                epoch=self.state.game_epoch, ids=dict(self.state.pick_test_piece_ids),
                board=[row[:] for row in board])
            self.state.set_status(f"Test chờ tâm ổn định: {exc}. Y: đo lại.", duration=30)
        except Exception as exc:
            self.state.test_pick_retry = None
            self.state.pick_test_fault = str(exc)
            self.state.pick_test_resume_required = True
            from src.core.project_logging import event
            import logging
            event("manual_test.failed", str(exc), level=logging.ERROR, code="MANUAL_TEST_BLOCKED",
                  exc_info=True, source_cell=source, destination_cell=destination)
            if getattr(self.hw, "simulation_runtime", None) is None and not getattr(self.hw, "dry_run", True):
                self.state.physical_sync_fault = True
                try:
                    self.hw.robot.deactivate_physical_control()
                except Exception as cleanup_error:
                    self.state.pick_test_fault += f"; không xác nhận được disable: {cleanup_error}; kiểm tra pendant"
                    event("manual_test.disable_failed", str(cleanup_error), level=logging.ERROR,
                          code="CONTROLLER_DISABLE_FAILED", exc_info=True)
            print(f"[PICK TEST] {exc}")
            self.state.set_status(f"TEST dừng: {self.state.pick_test_fault}", color=(180, 0, 0), duration=30)


    def _fresh_confirmed_layout(self):
        """Two separately captured, identical complete board observations."""
        import numpy as np
        from src.vision.cchess_recognizer import validate_board_sanity
        camera = getattr(self.hw, "cam_monitor", None)
        recognizer = getattr(self.hw, "recognize_board_state", None)
        if camera is None or not callable(recognizer):
            return None
        if self._physical_recovery_required() and not getattr(self.hw, "camera_calibration_ready", False):
            return None
        first = None
        threshold = float(getattr(getattr(self.hw, "config", None), "CCHESS_RECOVERY_MIN_CONFIDENCE", 0.5))
        try:
            for _ in range(2):
                frame, _ = camera.get_fresh_snapshot()
                result = recognizer(frame) if frame is not None else None
                if not result or not result.get("success"):
                    return None
                board = result.get("board")
                if (not isinstance(board, (list, tuple)) or len(board) != 10
                        or any(not isinstance(row, (list, tuple)) or len(row) != 9 for row in board)):
                    return None
                sane, _ = validate_board_sanity(board)
                if not sane:
                    return None
                if "quality_ok" in result:
                    quality = result["quality_ok"] is True
                else:
                    confidence = np.asarray(result.get("confidence", []), dtype=float)
                    quality = (confidence.shape == (10, 9) and np.isfinite(confidence).all()
                               and float(confidence.min()) >= threshold)
                if not quality:
                    return None
                board = [list(row) for row in board]
                if first is not None and board != first:
                    return None
                first = board
            return first
        except Exception as exc:
            print(f"[FULL SCAN] Fresh board unavailable: {exc}")
            return None

    def _rescan_confirmed_board(self):
        """Explicit operator recovery; never sends robot or gripper commands."""
        layout = self._fresh_confirmed_layout()
        apply = getattr(self.state, "apply_confirmed_board", None)
        if layout is None or not callable(apply) or not apply(layout):
            self.state.set_status("Full scan rejected: need two matching clear, calibrated board frames.", color=(180, 0, 0), duration=12.0)
            return False
        self._board_stability_monitor.reset()
        self._observed_baseline_time = None
        capture = getattr(self.hw, "capture_baseline_if_needed", None)
        captured = bool(capture(force_delay=0)) if callable(capture) else False
        self.state.manual_override_active = not captured
        self.state.snapshot_continue_required = not captured
        self.state.emergency_mode = False
        if not getattr(self.state, "turn_confirmation_required", False):
            self.state.set_status("Full board synchronized." if captured else "Board synchronized; capture a fresh baseline before continuing.", duration=10.0)
        return True

    def _confirm_human_camera_move(self):
        from src.vision.move_observation import derive_move_observation
        if getattr(self.state, "physical_sync_fault", False) or getattr(self.state, "move_sync_error", None):
            return False
        layout = self._fresh_confirmed_layout()
        if layout is None:
            return False
        observation = derive_move_observation(self.state.board, layout, player_color=self.state.turn)
        if not observation.success:
            return False
        expected, _ = xiangqi.make_temp_move(self.state.board, (observation.src, observation.dst))
        if expected != layout:
            return False
        return self._commit_human_move(observation.src, observation.dst, observation.piece, source="CAMERA_HUMAN_VS_HUMAN")

    def _physical_recovery_required(self):
        cfg = getattr(self.hw, "config", None)
        return str(getattr(cfg, "ROBOT_BACKEND", "VIRTUAL")).upper() == "PHYSICAL" and not getattr(self.hw, "dry_run", getattr(cfg, "DRY_RUN", True))

    def _verify_recovery_board(self, board):
        verifier = getattr(self.hw, "verify_physical_board", None)
        if not callable(verifier):
            return False
        try:
            pending = getattr(self.state, "pending_ai_move", None)
            if pending and board == pending.get("expected_board"):
                missing_color = {"r_K": "r", "b_K": "b"}.get(pending.get("captured_piece"))
                if missing_color is not None:
                    return bool(verifier(board, missing_king_color=missing_color))
            return bool(verifier(board))
        except Exception as exc:
            print(f"[RECOVERY] Fresh board verification failed: {exc}")
            return False

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
        if self._physical_recovery_required() and not callable(verifier):
            self.state.set_status("Camera identity verification unavailable; recovery remains paused.", color=(180, 0, 0), duration=10.0)
            return False
        if self._physical_recovery_required() or (reconciliation_available and callable(verifier)):
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
        if self._motion_busy():
            return
        import pygame
        if key == pygame.K_y:
            self._retry_visual_pick()
            return
        if key == pygame.K_h:
            self._run_hover_test()
            return
        if getattr(self.state, "visual_pick_retry", None) and key not in (pygame.K_v,):
            self.state.set_status("Nước robot đang chờ: Y đo lại / V đối soát bàn.", duration=15)
            return
        import pygame  # type: ignore
        if key != pygame.K_t and (getattr(self.state, "pick_test_mode", False) or getattr(self.state, "pick_test_resume_required", False)):
            self.state.set_status("Khôi phục bàn rồi New Game sau test trước khi thao tác game.", duration=20)
            return
        if key == pygame.K_F4:
            self._queue_or_run(self._rescan_confirmed_board)
            return
        if key in (pygame.K_1, pygame.K_2) and getattr(self.state, "turn_confirmation_required", False):
            self.state.confirm_turn_after_rescan("r" if key == pygame.K_1 else "b")
            return
        if self.state.game_over:
            return

        if key == pygame.K_t:
            self._toggle_pick_test()
            return
        if getattr(self.state, "pick_test_mode", False) or getattr(self.state, "pick_test_resume_required", False):
            self.state.set_status("Test đang dừng game. Khôi phục bàn rồi New Game để chơi.", duration=20)
            return
        if key == pygame.K_v:
            if self.state.physical_sync_fault:
                self._queue_or_run(self._reconcile_physical_sync_fault)
            else:
                self._queue_or_run(self.resume_automatic_scanning)
            return

        # Z KEY: Rollback
        if key == pygame.K_z:
            self.state.handle_rollback(self.hw)

        # M KEY: Emergency client-side move mode. This is intentionally
        # explicit so a camera failure cannot silently switch control paths.
        elif key == pygame.K_m:
            enabled = not getattr(self.state, "emergency_mode", False)
            if not enabled and self._physical_recovery_required():
                self.resume_automatic_scanning()
                return
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
            self._queue_or_run(self._handle_space_key)

    def _reconcile_physical_sync_fault(self):
        """Supervised recovery for a stopped physical-board synchronization."""
        pending = self.state.pending_ai_move
        if not pending and self._physical_recovery_required():
            if not self._verify_recovery_board(self.state.board):
                self.state.set_status("Fresh full-board verification failed; emergency correction remains paused.", color=(180, 0, 0), duration=10.0)
                return
            sync = getattr(self.state, "sync_current_board", None)
            if callable(sync) and not sync():
                return
            if self.resume_automatic_scanning():
                self.state.physical_sync_fault = False
                self.state.snapshot_continue_required = False
                self.state.snapshot_continue_can_commit_pending = False
                clear = getattr(self.state, "clear_move_sync_error", None)
                if callable(clear):
                    clear()
            return
        if not pending or not callable(getattr(self.hw, "verify_physical_board", None)):
            self.state.set_status("❌ Không có trạng thái đối soát để khôi phục.", color=(180, 0, 0), duration=8.0)
            return

        self.state.set_status("📸 Đang đối soát lại bàn thật...", color=(0, 100, 180), duration=5.0)
        # No robot command is issued here.  Matching the old board means the
        # arm did not complete the move; matching expected_board means it did.
        if self._verify_recovery_board(self.state.board):
            self.state.clear_pending_ai_move()
            self.state.snapshot_continue_required = False
            if self._physical_recovery_required():
                self.state.physical_sync_fault = True
                self.state.manual_override_active = True
                self.state.snapshot_continue_required = True
                self.state.set_status("Verified old board. Physical retry remains paused; inspect the arm before restarting.", color=(180, 100, 0), duration=15.0)
                return
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

        if self._verify_recovery_board(pending["expected_board"]):
            self._finalize_pending_ai_move(
                "✅ Đã xác nhận bàn thật — đến lượt bạn.", (0, 100, 180)
            )
            return

        src, dst = pending["move"]
        if pending.get("captured_piece") != ".":
            # Occupancy alone cannot prove captured identity or the rest of the board.
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
        if (xiangqi.get_king_pos(self.state.turn, self.state.board) is None
                or not xiangqi.find_all_valid_moves(self.state.turn, self.state.board)):
            winner = "b" if self.state.turn == "r" else "r"
            self.state.handle_game_over(winner)
            self.state.api_client.end_match(winner="BLACK" if winner == "b" else "RED", reason="CHECKMATE")
        else:
            if self.state.physical_sync_fault or self.state.move_sync_error:
                self.state.manual_override_active = True
                self.state.snapshot_continue_required = True
                self.state.set_status("Nước đã được ghi nhận nhưng mô phỏng chưa đồng bộ. Bấm V để đối soát lại.",
                                      color=(180, 0, 0), duration=30)
                return True
            captured = self.hw.capture_baseline_if_needed(force_delay=1.0)
            if self._physical_recovery_required() and not captured:
                self.state.manual_override_active = True
                self.state.snapshot_continue_required = True
                self.state.set_status("Move reconciled; camera baseline failed and scanning remains paused.", color=(180, 0, 0), duration=10.0)
                return True
            self.state.manual_override_active = False
            self.state.emergency_mode = False
            self.state.snapshot_continue_can_commit_pending = False
            clear = getattr(self.state, "clear_move_sync_error", None)
            if callable(clear):
                clear()
            self.state.set_status(status_message, color=status_color, duration=8.0)
        return True

    def _handle_space_key(self, auto_retry=False):
        import config
        # Offline mouse moves commit immediately. SPACE must not enter camera
        # confirmation or commit the same move a second time.
        backend = getattr(getattr(self.hw, "config", None), "ROBOT_BACKEND", "")
        if backend == "VIRTUAL" and getattr(self.hw, "dry_run", False) is True:
            if not (getattr(self.state, "physical_sync_fault", False)
                    or getattr(self.state, "move_sync_error", False)):
                self.state.set_status(
                    "Đi bằng chuột được xác nhận tự động; không cần SPACE.",
                    color=(0, 100, 180), duration=5.0,
                )
            return False
        if str(getattr(config, "GAME_MODE", "HUMAN_VS_ROBOT")).upper() == "HUMAN_VS_HUMAN":
            return self._confirm_human_camera_move()
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

        if self._physical_recovery_required() and not (cchess_result and cchess_result.get("success")):
            # Occupancy dropout alone cannot establish physical piece identity.
            src, dst, piece = None, None, None
        
        # Full identified layout must agree with the detected transition.
        # A positive occupancy guess cannot override a contradictory camera board.
        if cchess_result and cchess_result.get("success"):
            from src.vision.move_observation import derive_move_observation
            observation = derive_move_observation(
                self.state.board, cchess_result.get("board"), player_color="r",
                confidence_grid=cchess_result.get("confidence"),
            )
            if not observation.success or observation.as_tuple() != (src, dst, piece):
                src, dst, piece = None, None, None

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
        if getattr(self.state, "physical_sync_fault", False):
            self._reconcile_physical_sync_fault()
            return
        else:
            # Do not install a new baseline blindly: the physical Red move may
            # exist while FEN still describes the old board.  CChess must
            # prove either the old board or one unique legal successor.
            if self._physical_recovery_required():
                layout = self._fresh_confirmed_layout()
            else:
                recognizer = getattr(self.hw, "recognize_board_state", None)
                camera = getattr(self.hw, "cam_monitor", None)
                frame, _ = camera.get_fresh_snapshot() if camera else (None, [])
                result = recognizer(frame) if callable(recognizer) and frame is not None else None
                layout = result.get("board") if result and result.get("success") else None
            match = LegalSuccessorMatcher(self.state.board, player_color=getattr(self.state, "turn", "r")).match(layout)
            if match.kind == MatchKind.UNIQUE:
                src, dst = match.move
                piece = self.state.board[src[1]][src[0]]
                if not self._commit_human_move(src, dst, piece, source="CONTINUE"):
                    return
            elif match.kind != MatchKind.BASELINE_EQUAL:
                self.state.snapshot_continue_required = True
                self.state.emergency_mode = not self._physical_recovery_required()
                self.state.manual_override_active = True
                self.state.set_status(
                    "⚠️ Không thể xác nhận FEN. Emergency mode đã bật để nhập nước đi.",
                    color=(180, 100, 0), duration=12.0,
                )
                return
        self._board_stability_monitor.reset()
        capture = getattr(self.hw, "capture_baseline_if_needed", None)
        captured = bool(capture(force_delay=0.0)) if callable(capture) else False
        if not captured:
            self.state.manual_override_active = True
            self.state.snapshot_continue_required = True
            self.state.set_status("Fresh baseline unavailable; recovery remains paused.", color=(180, 0, 0), duration=10.0)
            return
        self.state.physical_sync_fault = False
        self.state.snapshot_continue_required = False
        self.state.snapshot_continue_can_commit_pending = False
        self.state.manual_override_active = False
        self.state.emergency_mode = False
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
        if self._motion_busy() or getattr(self.state, "visual_pick_retry", None):
            return False
        """Commit one legal Red move after repeated stable board observations."""
        if ((self.state.turn != "r" and getattr(config, 'GAME_MODE', '') != 'HUMAN_VS_HUMAN') or self.state.game_over
                or getattr(self.state, "pick_test_mode", False) or getattr(self.state, "pick_test_resume_required", False)
                or getattr(self.state, "manual_override_active", False)):
            self._board_stability_monitor.reset()
            self._player_turn_arbiter.deactivate()
            self._unified_active = False
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
            self._stability_sample_after = now

        # UI polling must never read the device, wait for inference, or rerun
        # CChess. The camera worker publishes one atomic, age-checked sample.
        getter = getattr(self.hw.cam_monitor, "get_latest_observation", None)
        observation = getter() if callable(getter) else None
        if observation is None:
            if self._board_stability_monitor.candidate is not None:
                print("[STABILITY] Candidate reset: camera returned no frame.")
            self._board_stability_monitor.observe(None)
            self._player_turn_arbiter.deactivate()
            self._unified_active = False
            return False
        sampled_at, frame, detections, cchess_result = observation
        if sampled_at <= max(self._last_stability_sample_at, self._stability_sample_after):
            return False
        self._last_stability_sample_at = sampled_at

        self._check_board_warning(cchess_result, now)

        # UNIFIED only consumes a fully recognized layout.  A missing red
        # piece while being held is deliberately incomplete, never a move.
        if self._player_turn_mode != PlayerTurnMode.LEGACY:
            active = self._maybe_activate_unified_turn()
            layout = cchess_result.get("board") if cchess_result and cchess_result.get("success") else None
            interaction = getattr(self.hw, "is_board_occluded", None)
            interaction = bool(interaction()) if callable(interaction) else False
            confidence = self._unified_observation_confidence(cchess_result)
            visibility = (Visibility.CLEAR if layout is not None and confidence is not None and not interaction
                          else Visibility.INSUFFICIENT)
            request = self._player_turn_arbiter.ingest(BoardObservation(
                observed_at=sampled_at, layout=layout, visibility=visibility,
                hand_or_object_present=interaction,
                aggregate_confidence=confidence if confidence is not None else 0.0,
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
                # Reconciliation failure can follow a local commit. Start the
                # next confirmation from current truth, never the old matcher.
                self._player_turn_arbiter.deactivate()
                self._unified_active = False
                return committed
            # SHADOW deliberately leaves legacy authoritative while recording
            # the same decisions in the arbiter state.
            if self._player_turn_mode == PlayerTurnMode.UNIFIED:
                return False

        if getattr(config, 'GAME_MODE', '') == 'HUMAN_VS_HUMAN':
            from src.vision.move_observation import derive_move_observation
            observed = derive_move_observation(self.state.board, cchess_result.get('board') if cchess_result else None,
                player_color=self.state.turn, confidence_grid=cchess_result.get('confidence') if cchess_result else None)
            src, dst, piece = observed.as_tuple() if observed.success else (None, None, None)
        else:
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
        elif xiangqi.is_valid_move(src, dst, self.state.board, self.state.turn):
            candidate = (src, dst, piece)
        else:
            rejection_reason = f"illegal Red move {src}->{dst}"

        previous_candidate = self._board_stability_monitor.candidate
        if candidate is None and previous_candidate is not None:
            print(f"[STABILITY] Candidate reset: {rejection_reason}.")
        elif candidate is not None and candidate != previous_candidate:
            print(f"[STABILITY] Candidate started: {candidate}")
        stable_move = self._board_stability_monitor.observe(candidate, now=sampled_at)
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
