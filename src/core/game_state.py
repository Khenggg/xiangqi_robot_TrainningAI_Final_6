import time
from collections import Counter, defaultdict
from typing import Optional, Tuple, Dict, List, Any

from src.core import xiangqi  # type: ignore
from src.core.fen_utils import board_array_to_fen, fen_to_board_array, INITIAL_FEN  # type: ignore
from src.api.simulation_client import TuongKyDaiSuClient  # type: ignore
from src.domain.game_move import MoveActor, MoveContext, initial_piece_identities, piece_symbol_for_identity
import config  # type: ignore

class GameState:
    def __init__(self, allow_mouse_move=False):
        self.allow_mouse_move = allow_mouse_move
        self.api_client = TuongKyDaiSuClient(config.SIMULATION_API_URL, config.SIMULATION_TOKEN)
        
        # Core Game State
        self.current_fen = INITIAL_FEN
        self.board, self.turn = fen_to_board_array(self.current_fen)
        self.game_over = False
        self.winner = None
        self.game_over_reason: str = ""
        self.last_move = None
        self.selected_pos = None
        self.r_captured = []
        self.b_captured = []
        self.move_history = []
        self.move_number = 1
        self.piece_ids = initial_piece_identities()
        self._move_observer = None
        self._board_observer = None
        self.turn_confirmation_required = False
        self.move_sync_error: Optional[str] = None
        self.pending_move: Optional[MoveContext] = None
        self.last_committed_move: Optional[MoveContext] = None
        self.move_execution_status = "IDLE"
        self.move_execution_error: Optional[str] = None
        
        
        # AI ELO State
        self.ai_elo: int = getattr(config, "DEFAULT_AI_ELO", 1400)
        self.ai_elo_title: str = "Quán cóc (1400)"
        self.history_snapshots: List[Dict[str, Any]] = []

        # UI Feedback State
        self.status_message: str = ""
        self.status_color: Tuple[int, int, int] = (0, 0, 0)
        self.status_expiry: float = 0.0
        self.invalid_flash_pos: Optional[Tuple[int, int]] = None
        self.invalid_flash_expiry: float = 0.0
        
        # AI Thread State
        self.ai_thread: Any = None
        self.ai_result: Any = None
        self.ai_thinking: bool = False
        self.ai_think_start: float = 0.0
        
        # Rollback State
        self._pre_space_state: Optional[Dict[str, Any]] = None
        self.manual_override_active: bool = False

        # Hint State
        self.hint_move: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None
        self.hint_expiry: float = 0.0

        # Physical / Robot Move Tracking
        self.pending_ai_move: Optional[Dict[str, Any]] = None
        self.physical_sync_fault: bool = False

    def set_move_observer(self, callback):
        """Observe committed human moves. The observer must not actuate the robot."""
        self._move_observer = callback

    def set_board_observer(self, callback):
        """Install the observer for a complete, camera-confirmed cell map."""
        self._board_observer = callback

    @property
    def is_human_turn(self) -> bool:
        mode = getattr(config, "GAME_MODE", "HUMAN_VS_ROBOT").upper()
        return mode == "HUMAN_VS_HUMAN" or (mode == "HUMAN_VS_ROBOT" and self.turn == "r")

    def create_move_context(self, src_col_row, dst_col_row, actor) -> MoveContext:
        src = (int(src_col_row[1]), int(src_col_row[0]))
        dst = (int(dst_col_row[1]), int(dst_col_row[0]))
        src_sym = self.board[src[0]][src[1]]
        piece_id = self.piece_ids.get(src)

        if piece_id is None or piece_symbol_for_identity(piece_id) != src_sym:
            raise ValueError(f"Piece identity is not reconciled at {src}")

        destination_symbol = self.board[dst[0]][dst[1]]
        captured_id = self.piece_ids.get(dst)

        if (captured_id is None) != (destination_symbol == "."):
            raise ValueError(f"Destination identity is not reconciled at {dst}")
        if captured_id is not None and piece_symbol_for_identity(captured_id) != destination_symbol:
            raise ValueError(f"Captured identity is not reconciled at {dst}")
        return MoveContext(piece_id=piece_id, src=src, dst=dst, actor=actor,
                           captured_piece_id=captured_id)

    def commit_piece_identity(self, context: MoveContext):
        if self.piece_ids.get(context.src) != context.piece_id:
            raise ValueError("Moving piece identity changed before commit")
        if self.piece_ids.get(context.dst) != context.captured_piece_id:
            raise ValueError("Captured piece identity changed before commit")
        self.piece_ids.pop(context.src)
        self.piece_ids[context.dst] = context.piece_id
        self.last_committed_move = context
        self.pending_move = None
        self.move_execution_status = "COMMITTED"
        self.move_execution_error = None

    def mark_move_pending(self, context: MoveContext):
        self.pending_move = context
        self.move_execution_status = "PENDING"
        self.move_execution_error = None

    def mark_move_failed(self, message: str):
        self.move_execution_status = "FAILED"
        self.move_execution_error = str(message)

    def clear_move_sync_error(self):
        """Call only after explicitly reconciling the game and physical scene."""
        self.move_sync_error = None
        self.pending_move = None
        self.move_execution_status = "IDLE"
        self.move_execution_error = None

    def _require_scene_reconciliation(self, reason: str):
        if self._move_observer is not None:
            self.move_sync_error = reason
            self.set_status(reason, color=(180, 0, 0), duration=10.0)

    def _notify_human_commit(self, context: MoveContext):
        if self._move_observer is None:
            return True
        try:
            if self._move_observer(context) is not True:
                raise RuntimeError("Digital Twin rejected committed human move")
        except Exception as exc:
            self._require_scene_reconciliation(f"Digital Twin sync failed: {exc}")
            return False
        return True

    def apply_confirmed_board(self, observed_board) -> bool:
        """Apply an approved complete camera board with canonical stable IDs.

        Retain IDs for unchanged cells, then assign unmatched same-type pieces
        from the remaining starting-layout IDs in sorted order. A full image
        cannot distinguish two identical physical pawns, so this is a logical
        deterministic identity assignment rather than visual re-identification.
        """
        from src.vision.cchess_recognizer import validate_board_sanity

        # A failed robot command leaves a pending semantic move. An explicit
        # complete rescan is the recovery path; the bridge itself rejects a
        # moving arm or attached payload before accepting the new board.
        if (not isinstance(observed_board, (list, tuple)) or len(observed_board) != 10
                or any(not isinstance(row, (list, tuple)) or len(row) != 9 for row in observed_board)):
            return False
        canonical = initial_piece_identities()
        allowed = Counter(piece_symbol_for_identity(pid) for pid in canonical.values())
        if any(not isinstance(cell, str) or (cell != "." and cell not in allowed)
               for row in observed_board for cell in row):
            return False
        seen = Counter(cell for row in observed_board for cell in row if cell != ".")
        if any(symbol not in allowed or count > allowed[symbol] for symbol, count in seen.items()):
            return False
        sane, _ = validate_board_sanity(observed_board)
        if not sane:
            return False

        # A full image says where pieces are, but not whose turn it is. Infer
        # only a single legal transition from the previously known board.
        # Interrupted robot motion may be observed at either endpoint.
        old_turn = self.turn
        board_changed = [list(row) for row in observed_board] != self.board
        next_turn = old_turn
        needs_turn_confirmation = False
        if board_changed:
            from src.vision.move_observation import derive_move_observation
            observation = derive_move_observation(self.board, observed_board, player_color=self.turn)
            if observation.success:
                expected, _ = xiangqi.make_temp_move(self.board, (observation.src, observation.dst))
                if expected == [list(row) for row in observed_board]:
                    next_turn = "b" if self.turn == "r" else "r"
                else:
                    needs_turn_confirmation = True
            else:
                needs_turn_confirmation = True

        remaining = defaultdict(list)
        new_ids = {}
        used = set()
        for row in range(10):
            for col in range(9):
                symbol = observed_board[row][col]
                old = self.piece_ids.get((row, col))
                if symbol != "." and old in canonical.values() and old not in used and piece_symbol_for_identity(old) == symbol:
                    new_ids[(row, col)] = old
                    used.add(old)
        for pid in sorted(canonical.values()):
            if pid not in used:
                remaining[piece_symbol_for_identity(pid)].append(pid)
        for row in range(10):
            for col in range(9):
                symbol = observed_board[row][col]
                if symbol != "." and (row, col) not in new_ids:
                    if not remaining[symbol]:
                        return False
                    new_ids[(row, col)] = remaining[symbol].pop(0)
        if self._board_observer is not None:
            try:
                if self._board_observer(new_ids) is not True:
                    raise RuntimeError("Digital Twin rejected complete camera board")
            except Exception as exc:
                self._require_scene_reconciliation(f"Board scan sync failed: {exc}")
                return False
        self.board = [list(row) for row in observed_board]
        self.piece_ids = new_ids
        self.turn = next_turn
        self.move_number += int(board_changed and next_turn != old_turn)
        self.update_fen_from_board()
        self.last_move = None
        self.last_committed_move = None
        self.pending_ai_move = None
        self.history_snapshots.clear()
        self.move_history.clear()
        missing = allowed - seen
        self.r_captured = [symbol for symbol in sorted(missing) if symbol.startswith("r_")
                           for _ in range(missing[symbol])]
        self.b_captured = [symbol for symbol in sorted(missing) if symbol.startswith("b_")
                           for _ in range(missing[symbol])]
        self.move_sync_error = None
        self.physical_sync_fault = False
        self.clear_move_sync_error()
        self.turn_confirmation_required = needs_turn_confirmation
        if needs_turn_confirmation:
            self.move_sync_error = "Bàn đã đồng bộ; xác nhận lượt tiếp theo bằng phím 1 (Đỏ) hoặc 2 (Đen)."
            self.set_status(self.move_sync_error, color=(180, 100, 0), duration=30.0)
        if self.api_client and not needs_turn_confirmation:
            try:
                self.api_client.send_move_update_board(self.current_fen)
            except Exception as exc:
                print(f"[API] Full-board rescan update failed: {exc}")
        return True

    def confirm_turn_after_rescan(self, color: str) -> bool:
        """Explicit operator confirmation after a multi-change recovery scan."""
        if not self.turn_confirmation_required or color not in ("r", "b"):
            return False
        self.turn = color
        self.update_fen_from_board()
        self.turn_confirmation_required = False
        self.move_sync_error = None
        self.physical_sync_fault = False
        if self.api_client:
            try:
                self.api_client.send_move_update_board(self.current_fen)
            except Exception as exc:
                print(f"[API] Confirmed-turn update failed: {exc}")
        self.set_status("Đã xác nhận lượt tiếp theo.", color=(0, 120, 0), duration=5.0)
        return True

    def get_legal_moves_for_selected(self) -> List[Tuple[int, int]]:
        """Trả về danh sách toạ độ (col, row) các ô hợp lệ mà quân cờ đang chọn có thể đi tới."""
        if not self.selected_pos:
            return []
        sc, sr = self.selected_pos
        p = self.board[sr][sc]
        if p == '.' or p[0] != self.turn:
            return []

        valid_dests = []
        for r in range(xiangqi.NUM_ROWS):
            for c in range(xiangqi.NUM_COLS):
                if xiangqi.is_valid_move((sc, sr), (c, r), self.board, self.turn):
                    valid_dests.append((c, r))
        return valid_dests

    def update_fen_from_board(self):
        """Cập nhật current_fen từ board array hiện tại."""
        self.current_fen = board_array_to_fen(self.board, self.turn, self.move_number)

    def set_pending_ai_move(self, move, expected_board, captured_piece):
        """Remember the only state transition a fault-recovery may commit."""
        self.set_pending_physical_move(move, expected_board, captured_piece, "b")

    def set_pending_physical_move(self, move, expected_board, captured_piece, moving_color="b"):
        """Remember a verified physical move without committing it yet."""
        self.pending_ai_move = {
            "move": move,
            "expected_board": [row[:] for row in expected_board],
            "captured_piece": captured_piece,
            "moving_color": moving_color,
        }

    def clear_pending_ai_move(self):
        self.pending_ai_move = None
        self.physical_sync_fault = False

    def commit_pending_ai_move(self):
        """Atomically commit a camera-verified physical AI move to the FEN board."""
        return self.commit_pending_physical_move()

    def commit_pending_physical_move(self):
        """Atomically commit a verified robot move for either color."""
        if self.pending_ai_move is None:
            return False
        pending = self.pending_ai_move
        src, dst = pending["move"]
        captured_piece = pending["captured_piece"]
        moving_color = pending.get("moving_color", "b")
        if self.turn != moving_color:
            return False
        context = self.pending_move
        if context is not None:
            if (context.actor != MoveActor.ROBOT or context.src != (src[1], src[0])
                    or context.dst != (dst[1], dst[0])
                    or self.piece_ids.get(context.src) != context.piece_id
                    or self.piece_ids.get(context.dst) != context.captured_piece_id):
                self.mark_move_failed("Robot move identity changed before commit")
                self.move_sync_error = self.move_execution_error
                return False
        elif self._move_observer is not None:
            self.mark_move_failed("Robot move lacks a semantic identity")
            self.move_sync_error = self.move_execution_error
            return False
        self.move_history.append({"turn": moving_color, "src": src, "dst": dst})
        if captured_piece != ".":
            (self.b_captured if moving_color == "r" else self.r_captured).append(captured_piece)
        self.board = [row[:] for row in pending["expected_board"]]
        self.last_move = pending["move"]
        self.turn = "b" if moving_color == "r" else "r"
        self.move_number += 1
        self.update_fen_from_board()
        if context is not None:
            self.commit_piece_identity(context)
        self.pending_ai_move = None
        self.physical_sync_fault = False
        print(f"[FEN] {self.current_fen}")
        return True

    def get_render_state(self):
        """Tạo dict game state cho renderer."""
        return {
            "game_over": self.game_over,
            "winner": self.winner,
            "turn": self.turn,
            "allow_mouse": self.allow_mouse_move,
            "ai_thinking": self.ai_thinking,
            "ai_think_start": self.ai_think_start,
            "status_message": self.status_message,
            "status_color": self.status_color,
            "status_expiry": self.status_expiry,
            "ai_elo": self.ai_elo,
            "ai_elo_title": self.ai_elo_title,
            "legal_moves": self.get_legal_moves_for_selected(),
            "move_history": list(self.move_history),
            "is_check": xiangqi.is_king_in_check(self.turn, self.board),
            "hint_move": self.hint_move if time.time() < self.hint_expiry else None,
            "game_over_reason": self.game_over_reason,
            "manual_override_active": self.manual_override_active,
        }

    def reset_game(self, hw_manager=None):
        if (hw_manager is not None
                and getattr(getattr(hw_manager, "config", None), "ROBOT_BACKEND", "VIRTUAL").upper() == "PHYSICAL"
                and not getattr(hw_manager, "dry_run", True)):
            expected, _ = fen_to_board_array(INITIAL_FEN)
            if not hw_manager.verify_physical_board(expected):
                self._require_scene_reconciliation("Reset blocked: physical board does not match initial layout")
                return False
        # [API] Đóng room cũ trước khi tạo game mới
        if self.api_client.room_id:
            print("[GAME] 🔚 Đóng room cũ trước khi tạo game mới...")
            winner = "DRAW"
            reason = "OTHER"
            
            # Nếu game đã kết thúc, dùng winner thực tế
            if self.game_over and self.winner:
                winner = "RED" if self.winner == "r" else "BLACK"
                reason = "CHECKMATE"
            
            self.api_client.end_match(winner=winner, reason=reason)
        
        self.current_fen = INITIAL_FEN
        self.board, self.turn = fen_to_board_array(self.current_fen)
        self.piece_ids = initial_piece_identities()
        self.pending_move = None
        self.turn_confirmation_required = False
        self.last_committed_move = None
        self.move_execution_status = "IDLE"
        self.move_execution_error = None
        self.game_over = False
        self.winner = None
        self.last_move = None
        self.selected_pos = None
        self.r_captured = []
        self.b_captured = []
        self.move_history = []
        self.history_snapshots = []
        self.move_number = 1
        self.status_message = ""
        self.status_expiry = 0.0
        self.invalid_flash_pos = None
        self.invalid_flash_expiry = 0.0
        self.ai_thread = None
        self.ai_result = None
        self.ai_thinking = False
        self.ai_think_start = 0.0
        self.manual_override_active = False

        self._require_scene_reconciliation("New game requires Digital Twin scene reconciliation")

        print("[GAME] 🔄 New game started!")
        print(f"[FEN] {self.current_fen}")
        
        if hw_manager:
            hw_manager.capture_baseline_if_needed(force_delay=1)
            if hasattr(hw_manager, "reconcile_new_game"):
                try:
                    if hw_manager.reconcile_new_game():
                        self.clear_move_sync_error()
                except Exception as exc:
                    print(f"[GAME] ⚠️ Digital twin new game reconciliation failed: {exc}")
        
        # [API] Tạo room mới (nếu không ở chế độ DRY_RUN)
        if not config.DRY_RUN:
            self.api_client.create_match(red_name="Người chơi Thật", black_name="Robot AI")
        return self.move_sync_error is None

    def set_status(self, msg, color=(200, 0, 0), duration=2.5):
        self.status_message = msg
        self.status_color = color
        self.status_expiry = time.time() + duration

    def set_invalid_flash(self, col, row, duration=0.6):
        self.invalid_flash_pos = (col, row)
        self.invalid_flash_expiry = time.time() + duration

    def handle_game_over(self, the_winner: str, reason: str = "CHIẾU BÍ"):
        self.winner = the_winner
        self.game_over = True
        self.game_over_reason = reason
        if the_winner == "r":
            self.set_status(f"🏆 CHIẾN THẮNG! AI bị {reason}!", color=(34, 197, 94), duration=12.0)
        elif the_winner == "b":
            self.set_status(f"💀 BẠN ĐÃ THUA! Bạn bị {reason}!", color=(220, 38, 38), duration=12.0)
        else:
            self.set_status("🤝 VÁN ĐẤU HÒA!", color=(234, 88, 12), duration=12.0)

    def save_rollback_state(self, baseline_occ=None, baseline_time=None):
        self._pre_space_state = {
            "board": [row[:] for row in self.board],
            "piece_ids": dict(self.piece_ids),
            "turn": self.turn,
            "last_move": self.last_move,
            "current_fen": self.current_fen,
            "move_number": self.move_number,
            "r_captured": list(self.r_captured),
            "b_captured": list(self.b_captured),
            "move_history": list(self.move_history),
            "baseline_occ": baseline_occ,
            "baseline_time": baseline_time,
        }
        print("[SPACE] 💾 State saved for rollback (Z to undo).")

    def handle_rollback(self, hw_manager=None):
        """Rollback về trạng thái trước khi bấm SPACE lần cuối (phím Z)."""
        if self._pre_space_state is None:
            print("[ROLLBACK] ⚠️ Không có state để rollback!")
            self.set_status("⚠️  Không có nước nào để rollback!", color=(180, 100, 0), duration=2.5)
            return

        if (hw_manager is not None
                and getattr(getattr(hw_manager, "config", None), "ROBOT_BACKEND", "VIRTUAL").upper() == "PHYSICAL"
                and not getattr(hw_manager, "dry_run", True)):
            if not hw_manager.verify_physical_board(self._pre_space_state["board"]):
                self._require_scene_reconciliation("Rollback blocked: physical board differs from saved board")
                return

        print("[ROLLBACK] ↩️ Khôi phục trạng thái trước SPACE...")
        s = self._pre_space_state
        self.board = [row[:] for row in s["board"]]
        self.piece_ids = dict(s["piece_ids"])
        self.turn = s["turn"]
        self.last_move = s["last_move"]
        self.current_fen = s["current_fen"]
        self.move_number = s["move_number"]
        self.r_captured = list(s["r_captured"])
        self.b_captured = list(s["b_captured"])
        self.move_history = list(s["move_history"])

        if hw_manager:
            hw_manager.restore_yolo_baseline(s.get("baseline_occ"), s.get("baseline_time"))

        print("[ROLLBACK] 📸 T1 baselines restored.")

        self._pre_space_state = None   # Xóa sau khi rollback
        self.set_status("↩️  Đã rollback! Di quân lại rồi bấm SPACE.", color=(180, 100, 0), duration=5.0)
        print(f"[ROLLBACK] ✅ Done. FEN: {self.current_fen}")
        
        self.manual_override_active = False
        self._require_scene_reconciliation("Rollback requires Digital Twin scene reconciliation")

    def undo_round(self, hw_manager=None) -> bool:
        """Hoàn tác nước cờ gần nhất của người chơi và nước đáp trả của AI (phím U)."""
        if self.ai_thinking:
            self.set_status("⚠️ AI đang tính toán, vui lòng đợi!", color=(200, 100, 0), duration=2.5)
            return False

        if not self.history_snapshots:
            print("[UNDO] ⚠️ Không có nước đi nào để Undo!")
            self.set_status("⚠️ Chưa có nước đi nào để hoàn tác!", color=(180, 100, 0), duration=2.5)
            return False

        if (hw_manager is not None
                and getattr(getattr(hw_manager, "config", None), "ROBOT_BACKEND", "VIRTUAL").upper() == "PHYSICAL"
                and not getattr(hw_manager, "dry_run", True)):
            if not hw_manager.verify_physical_board(self.history_snapshots[-1]["board"]):
                self._require_scene_reconciliation("Undo blocked: physical board differs from saved board")
                return False

        print("[UNDO] ↩️ Đang hoàn tác nước cờ...")
        snap = self.history_snapshots.pop()
        self.board = [row[:] for row in snap["board"]]
        self.piece_ids = dict(snap["piece_ids"])
        self.turn = snap["turn"]
        self.last_move = snap["last_move"]
        self.current_fen = snap["current_fen"]
        self.move_number = snap["move_number"]
        self.r_captured = list(snap["r_captured"])
        self.b_captured = list(snap["b_captured"])
        self.move_history = list(snap["move_history"])
        self.game_over = False
        self.winner = None
        self.selected_pos = None

        if hw_manager and hasattr(hw_manager, "clear_yolo_baseline"):
            hw_manager.clear_yolo_baseline()

        if self.api_client:
            try:
                self.api_client.send_move_update_board(self.current_fen)
            except Exception:
                pass

        print(f"[UNDO] ✅ Hoàn tác thành công! FEN: {self.current_fen}")
        self.set_status("↩️ Đã hoàn tác nước cờ (Undo)! Đến lượt bạn đi.", color=(0, 150, 0), duration=4.0)
        self._require_scene_reconciliation("Undo requires Digital Twin scene reconciliation")
        if hw_manager and hasattr(hw_manager, "reconcile_board"):
            try:
                if hw_manager.reconcile_board(self.piece_ids):
                    self.clear_move_sync_error()
            except Exception as exc:
                print(f"[GAME] ⚠️ Digital twin undo reconciliation failed: {exc}")
        return True

    def process_human_move(self, src, dst, p_name):
        if self.move_sync_error or self.pending_move is not None or self.pending_ai_move is not None or not self.is_human_turn:
            return False
        if not xiangqi.is_valid_move(src, dst, self.board, self.turn):
            return False
        context = self.create_move_context(src, dst, MoveActor.HUMAN)
        print(f"[HUMAN] ✅ Moved: {p_name} {src}->{dst}")
        self.set_status("✅  Move accepted." if getattr(config, "GAME_MODE", "HUMAN_VS_ROBOT") == "HUMAN_VS_HUMAN"
                        else "✅  Move accepted — AI thinking...", color=(0, 120, 0), duration=5.0)
        
        # Lưu snapshot trạng thái trước nước đi để phục vụ Undo
        self.history_snapshots.append({
            "board": [row[:] for row in self.board],
            "piece_ids": dict(self.piece_ids),
            "turn": self.turn,
            "last_move": self.last_move,
            "current_fen": self.current_fen,
            "move_number": self.move_number,
            "r_captured": list(self.r_captured),
            "b_captured": list(self.b_captured),
            "move_history": list(self.move_history),
        })

        moving_color = self.turn
        self.move_history.append({"turn": moving_color, "src": src, "dst": dst})
        
        cap_p = self.board[dst[1]][dst[0]]
        if cap_p != ".":
            (self.b_captured if moving_color == "r" else self.r_captured).append(cap_p)
        
        self.board, _ = xiangqi.make_temp_move(self.board, (src, dst))
        self.last_move = (src, dst)
        
        self.turn = "b" if moving_color == "r" else "r"
        self.move_number += 1
        self.update_fen_from_board()
        self.commit_piece_identity(context)
        # A camera-confirmed human move has already happened in the real
        # world. Preserve that game fact even if PyBullet rejects it; latch a
        # synchronization fault and prevent any subsequent robot motion.
        synchronized = self._notify_human_commit(context)
        print(f"[FEN] {self.current_fen}")
        
        # [API] Đồng bộ nước đi lên máy chủ Simulation
        self.api_client.send_move_update_board(self.current_fen)
        
        # Kiểm tra Chiếu bí / Tuyệt sát hoặc Chiếu tướng đối với AI
        opponent = self.turn
        if xiangqi.is_checkmate(opponent, self.board):
            is_chk = xiangqi.is_king_in_check(opponent, self.board)
            reason = "CHIẾU BÍ" if is_chk else "TUYỆT SÁT"
            print(f"[GAME] 🏆 BẠN ĐÃ THẮNG! AI bị {reason}!")
            self.handle_game_over(moving_color, reason=reason)
            self.turn = moving_color
            if self.api_client:
                try:
                    self.api_client.end_match(winner="RED" if moving_color == "r" else "BLACK", reason="CHECKMATE")
                except Exception:
                    pass
        elif xiangqi.is_king_in_check(opponent, self.board):
            print("[GAME] ⚠️ ĐANG CHIẾU TƯỚNG AI!")
            self.set_status("⚠️ CHIẾU TƯỚNG! AI đang tìm cách chống đỡ...", color=(234, 88, 12), duration=3.0)
        return synchronized
