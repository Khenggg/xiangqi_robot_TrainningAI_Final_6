import time
from typing import Optional, Tuple, Dict, List, Any

from src.core import xiangqi  # type: ignore
from src.core.fen_utils import board_array_to_fen, fen_to_board_array, INITIAL_FEN  # type: ignore
from src.api.simulation_client import TuongKyDaiSuClient  # type: ignore
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
        self.last_move = None
        self.selected_pos = None
        self.r_captured = []
        self.b_captured = []
        self.move_history = []
        self.move_number = 1
        
        
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
        # AI may start only after a locally committed human move.  The main
        # loop consumes each generation once, so repeated camera samples or a
        # duplicate commit cannot create a second robot job.
        self.human_commit_generation: int = 0
        self.ai_started_for_human_commit_generation: int = 0
        self.game_epoch: int = 0
        self.ai_epoch: int = 0
        self.ai_job_token = None
        self.ai_results: Dict[Any, Any] = {}
        self.ai_retry_requested: bool = False
        
        # Rollback State
        self._pre_space_state: Optional[Dict[str, Any]] = None
        self.manual_override_active: bool = False
        # Set only when the snapshot/FEN pipeline has explicitly paused the
        # game.  Emergency mode is a separate, deliberate control mode.
        self.snapshot_continue_required: bool = False
        self.snapshot_continue_can_commit_pending: bool = False
        self.emergency_mode: bool = False
        # A failed post-move camera check means the physical board may have
        # changed while FEN was intentionally left untouched.  Do not retry the
        # same robot command until an operator resolves the discrepancy.
        self.physical_sync_fault: bool = False
        self.pending_ai_move: Optional[Dict[str, Any]] = None

    def update_fen_from_board(self):
        """Cập nhật current_fen từ board array hiện tại."""
        self.current_fen = board_array_to_fen(self.board, self.turn, self.move_number)

    def get_render_state(self):
        """Tạo dict game state cho renderer."""
        return {
            "game_over": self.game_over,
            "turn": self.turn,
            "allow_mouse": self.allow_mouse_move,
            "ai_thinking": self.ai_thinking,
            "ai_think_start": self.ai_think_start,
            "status_message": self.status_message,
            "status_color": self.status_color,
            "status_expiry": self.status_expiry,
            "manual_override_active": self.manual_override_active,
            "snapshot_continue_required": self.snapshot_continue_required,
            "emergency_mode": self.emergency_mode,
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
        
        self.game_epoch += 1
        self.ai_epoch += 1
        self.current_fen = INITIAL_FEN
        self.board, self.turn = fen_to_board_array(self.current_fen)
        self.game_over = False
        self.winner = None
        self.last_move = None
        self.selected_pos = None
        self.r_captured = []
        self.b_captured = []
        self.move_history = []
        self.move_number = 1
        self.status_message = ""
        self.status_expiry = 0.0
        self.invalid_flash_pos = None
        self.invalid_flash_expiry = 0.0
        self.ai_thread = None
        self.ai_result = None
        self.ai_thinking = False
        self.ai_think_start = 0.0
        self.ai_job_token = None
        self.ai_results = {}
        self.ai_retry_requested = False
        self.human_commit_generation = 0
        self.ai_started_for_human_commit_generation = 0
        self.manual_override_active = False
        self.snapshot_continue_required = False
        self.snapshot_continue_can_commit_pending = False
        self.emergency_mode = False
        self.physical_sync_fault = False
        self.pending_ai_move = None

        print("[GAME] 🔄 New game started!")
        print(f"[FEN] {self.current_fen}")
        
        if hw_manager:
            hw_manager.capture_baseline_if_needed(force_delay=1)
        
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

    def handle_game_over(self, the_winner):
        self.winner = the_winner
        self.game_over = True
        self.ai_epoch += 1
        self.ai_job_token = None

    def save_rollback_state(self, baseline_occ=None, baseline_time=None):
        self._pre_space_state = {
            "board": [row[:] for row in self.board],
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
        self.game_epoch += 1
        self.ai_epoch += 1
        self.ai_job_token = None
        self.ai_results = {}
        self.ai_retry_requested = False
        self.ai_thread = None
        self.ai_result = None
        self.ai_thinking = False
        s = self._pre_space_state
        self.board = [row[:] for row in s["board"]]
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
        self.snapshot_continue_required = False
        self.snapshot_continue_can_commit_pending = False
        self.emergency_mode = False

    def set_pending_ai_move(self, move, expected_board, captured_piece):
        """Remember the only state transition a fault-recovery may commit."""
        self.pending_ai_move = {
            "move": move,
            "expected_board": [row[:] for row in expected_board],
            "captured_piece": captured_piece,
        }

    def clear_pending_ai_move(self):
        self.pending_ai_move = None
        self.physical_sync_fault = False

    def prepare_ai_retry_after_physical_miss(self):
        """Re-open the current Black AI turn after a verified missed pickup.

        The FEN board remains unchanged.  A dedicated retry flag lets the main
        loop create one fresh AI job for that same human move; it never reuses
        a potentially stale robot command.
        """
        if self.game_over or self.turn != "b":
            return False
        worker = self.ai_thread
        is_alive = getattr(worker, "is_alive", None)
        if callable(is_alive) and is_alive():
            # Moonfish is a shared UCCI subprocess; never start a second
            # request while an earlier worker is still using it.
            return False
        self.ai_epoch += 1
        self.ai_job_token = None
        self.ai_thread = None
        self.ai_thinking = False
        self.ai_results = {}
        self.ai_retry_requested = True
        return True

    def can_start_ai_turn(self):
        """Whether the main loop may create exactly one Black AI worker."""
        return (
            not self.ai_thinking
            and self.ai_thread is None
            and (
                self.human_commit_generation > self.ai_started_for_human_commit_generation
                or self.ai_retry_requested
            )
        )

    def mark_ai_turn_started(self):
        """Consume the normal-generation or one-shot retry start authority."""
        self.ai_started_for_human_commit_generation = self.human_commit_generation
        self.ai_retry_requested = False

    def commit_pending_ai_move(self):
        """Atomically commit a camera-verified physical AI move to the FEN board."""
        if self.pending_ai_move is None:
            return False
        pending = self.pending_ai_move
        src, dst = pending["move"]
        captured_piece = pending["captured_piece"]
        self.move_history.append({"turn": "b", "src": src, "dst": dst})
        if captured_piece != ".":
            self.r_captured.append(captured_piece)
        self.board = [row[:] for row in pending["expected_board"]]
        self.last_move = pending["move"]
        self.turn = "r"
        self.update_fen_from_board()
        self.pending_ai_move = None
        self.physical_sync_fault = False
        return True

    def process_human_move(self, src, dst, p_name):
        print(f"[HUMAN] ✅ Moved: {p_name} {src}->{dst}")
        self.set_status("✅  Move accepted — AI thinking...", color=(0, 120, 0), duration=5.0)
        
        self.move_history.append({"turn": "r", "src": src, "dst": dst})
        
        cap_p = self.board[dst[1]][dst[0]]
        if cap_p != ".": self.b_captured.append(cap_p)
        
        self.board, _ = xiangqi.make_temp_move(self.board, (src, dst))
        self.last_move = (src, dst)
        
        self.turn = "b"  # Chuyển lượt
        self.human_commit_generation += 1
        self.move_number += 1
        self.update_fen_from_board()
        print(f"[FEN] {self.current_fen}")
        
        # [API] Đồng bộ nước đi lên máy chủ Simulation
        self.api_client.send_move_update_board(self.current_fen)
        
        if xiangqi.get_king_pos("b", self.board) is None:
            self.handle_game_over("r")
            self.turn = "r"

    def process_emergency_move(self, src, dst, p_name):
        """Commit one rule-checked client move for the side currently to move.

        A Red move intentionally follows the normal human path, which opens
        exactly one AI/robot reply.  A Black move is an operator correction:
        it cancels any in-flight AI result and hands the turn back to Red.
        """
        # An operator edit supersedes any unverified robot transition.  Never
        # let a later Continue overwrite the corrected client position.
        self.pending_ai_move = None
        self.physical_sync_fault = False
        self.snapshot_continue_required = False
        self.snapshot_continue_can_commit_pending = False
        color = self.turn
        if color == "r":
            self.process_human_move(src, dst, p_name)
            return

        print(f"[EMERGENCY] ✅ Manual Black move: {p_name} {src}->{dst}")
        captured_piece = self.board[dst[1]][dst[0]]
        self.move_history.append({"turn": "b", "src": src, "dst": dst})
        if captured_piece != ".":
            self.r_captured.append(captured_piece)
        self.board, _ = xiangqi.make_temp_move(self.board, (src, dst))
        self.last_move = (src, dst)
        self.turn = "r"
        self.move_number += 1
        # Invalidate a worker which may have been calculating the old Black
        # position; Python cannot safely kill that thread, but its result is
        # discarded by the main-loop token check.
        self.ai_epoch += 1
        self.ai_job_token = None
        self.ai_thinking = False
        self.ai_thread = None
        self.ai_results = {}
        self.ai_retry_requested = False
        self.update_fen_from_board()
        self.api_client.send_move_update_board(self.current_fen)
        self.set_status("✅ Emergency Black move accepted — Red to move.", color=(0, 120, 0), duration=6.0)
        if xiangqi.get_king_pos("r", self.board) is None:
            self.handle_game_over("b")
