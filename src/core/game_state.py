import time
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

    def set_move_observer(self, callback):
        """Observe committed human moves. The observer must not actuate the robot."""
        self._move_observer = callback

    def create_move_context(self, src_col_row, dst_col_row, actor) -> MoveContext:
        src = (int(src_col_row[1]), int(src_col_row[0]))
        dst = (int(dst_col_row[1]), int(dst_col_row[0]))
        piece_id = self.piece_ids.get(src)
        if piece_id is None or piece_symbol_for_identity(piece_id) != self.board[src[0]][src[1]]:
            raise ValueError(f"Piece identity is not reconciled at {src}")
        captured_id = self.piece_ids.get(dst)
        destination_symbol = self.board[dst[0]][dst[1]]
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
            return
        try:
            if self._move_observer(context) is not True:
                raise RuntimeError("Digital Twin rejected committed human move")
        except Exception as exc:
            self._require_scene_reconciliation(f"Digital Twin sync failed: {exc}")

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
        }

    def reset_game(self, hw_manager=None):
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
        context = self.create_move_context(src, dst, MoveActor.HUMAN)
        print(f"[HUMAN] ✅ Moved: {p_name} {src}->{dst}")
        self.set_status("✅  Move accepted — AI thinking...", color=(0, 120, 0), duration=5.0)
        
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

        self.move_history.append({"turn": "r", "src": src, "dst": dst})
        
        cap_p = self.board[dst[1]][dst[0]]
        if cap_p != ".": self.b_captured.append(cap_p)
        
        self.board, _ = xiangqi.make_temp_move(self.board, (src, dst))
        self.last_move = (src, dst)
        
        self.turn = "b"  # Chuyển lượt
        self.move_number += 1
        self.update_fen_from_board()
        self.commit_piece_identity(context)
        self._notify_human_commit(context)
        print(f"[FEN] {self.current_fen}")
        
        # [API] Đồng bộ nước đi lên máy chủ Simulation
        self.api_client.send_move_update_board(self.current_fen)
        
        # Kiểm tra Chiếu bí / Tuyệt sát hoặc Chiếu tướng đối với AI
        if xiangqi.is_checkmate("b", self.board):
            is_chk = xiangqi.is_king_in_check("b", self.board)
            reason = "CHIẾU BÍ" if is_chk else "TUYỆT SÁT"
            print(f"[GAME] 🏆 BẠN ĐÃ THẮNG! AI bị {reason}!")
            self.handle_game_over("r", reason=reason)
            self.turn = "r"
            if self.api_client:
                try:
                    self.api_client.end_match(winner="RED", reason="CHECKMATE")
                except Exception:
                    pass
        elif xiangqi.is_king_in_check("b", self.board):
            print("[GAME] ⚠️ ĐANG CHIẾU TƯỚNG AI!")
            self.set_status("⚠️ CHIẾU TƯỚNG! AI đang tìm cách chống đỡ...", color=(234, 88, 12), duration=3.0)
