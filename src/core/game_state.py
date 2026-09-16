import time
import threading
import queue
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

        # Robot motion must never run on the Pygame/UI thread. The worker only
        # writes a result into this queue; game state remains main-thread owned.
        self.robot_thread: Any = None
        self.robot_result_queue: queue.Queue = queue.Queue(maxsize=1)
        self.robot_busy: bool = False
        self.robot_fault: bool = False
        self.robot_move_context: Optional[Dict[str, Any]] = None
        self.preview_board = None

        # HTTP syncing is serialized but never stalls UI input/rendering.
        self._api_sync_lock = threading.Lock()
        self.api_sync_busy = False
        
        # Rollback State
        self._pre_space_state: Optional[Dict[str, Any]] = None
        self.manual_override_active: bool = False

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
            "robot_busy": self.robot_busy,
            "ai_think_start": self.ai_think_start,
            "status_message": self.status_message,
            "status_color": self.status_color,
            "status_expiry": self.status_expiry,
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
        self.robot_thread = None
        self.robot_busy = False
        self.robot_fault = False
        self.robot_move_context = None
        self.preview_board = None
        self.manual_override_active = False

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

    def sync_fen_async(self, fen):
        """Synchronize the server without blocking the Pygame main loop."""
        self.api_sync_busy = True
        def _sync_worker():
            with self._api_sync_lock:
                try:
                    self.api_client.send_move_update_board(fen)
                finally:
                    self.api_sync_busy = False

        threading.Thread(target=_sync_worker, daemon=True, name="fen-api-sync").start()

    def set_invalid_flash(self, col, row, duration=0.6):
        self.invalid_flash_pos = (col, row)
        self.invalid_flash_expiry = time.time() + duration

    def handle_game_over(self, the_winner):
        self.winner = the_winner
        self.game_over = True

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

    def process_human_move(self, src, dst, p_name):
        print(f"[HUMAN] ✅ Moved: {p_name} {src}->{dst}")
        self.set_status("✅  Move accepted — AI thinking...", color=(0, 120, 0), duration=5.0)
        
        self.move_history.append({"turn": "r", "src": src, "dst": dst})
        
        cap_p = self.board[dst[1]][dst[0]]
        if cap_p != ".": self.b_captured.append(cap_p)
        
        self.board, _ = xiangqi.make_temp_move(self.board, (src, dst))
        self.last_move = (src, dst)
        
        self.turn = "b"  # Chuyển lượt
        self.move_number += 1
        self.update_fen_from_board()
        print(f"[FEN] {self.current_fen}")
        
        # [API] Đồng bộ nước đi lên máy chủ Simulation
        self.sync_fen_async(self.current_fen)
        
        if xiangqi.get_king_pos("b", self.board) is None:
            self.handle_game_over("r")
            self.turn = "r"
