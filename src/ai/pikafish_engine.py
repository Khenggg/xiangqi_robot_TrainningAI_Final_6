# =============================================================================
# === FILE: pikafish_engine.py ===
# === Bridge between Xiangqi Robot and Pikafish (UCI/NNUE Xiangqi Engine) ===
# =============================================================================
import subprocess
import threading
import time
import os
import sys
import atexit
import random
from typing import Optional, Tuple, Dict, Any, List

# Đảm bảo in tiếng Việt / emoji an toàn trên Windows console mà không gây UnicodeEncodeError
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass



# Bảng định nghĩa các nấc ELO mô phỏng phong cách Chess.com
ELO_PRESETS: Dict[int, Dict[str, Any]] = {
    800: {
        "title": "Tập sự (800)",
        "depth": 1,
        "nodes": 150,
        "multipv": 5,
        "blunder_rate": 0.35,
    },
    1100: {
        "title": "Nhập môn (1100)",
        "depth": 3,
        "nodes": 800,
        "multipv": 3,
        "blunder_rate": 0.20,
    },
    1400: {
        "title": "Quán cóc (1400)",
        "depth": 5,
        "nodes": 4000,
        "multipv": 2,
        "blunder_rate": 0.08,
    },
    1700: {
        "title": "Cao thủ CLB (1700)",
        "depth": 8,
        "nodes": 20000,
        "multipv": 1,
        "blunder_rate": 0.0,
    },
    2000: {
        "title": "VĐV Tỉnh (2000)",
        "depth": 12,
        "nodes": 80000,
        "multipv": 1,
        "blunder_rate": 0.0,
    },
    2300: {
        "title": "Kiện tướng (2300)",
        "depth": 16,
        "movetime_ms": 1500,
        "multipv": 1,
        "blunder_rate": 0.0,
    },
    2600: {
        "title": "Đại kiện tướng (2600)",
        "depth": 20,
        "movetime_ms": 2500,
        "multipv": 1,
        "blunder_rate": 0.0,
    },
    3000: {
        "title": "Max AI (3000+)",
        "depth": 25,
        "movetime_ms": 3000,
        "multipv": 1,
        "blunder_rate": 0.0,
    },
}

DEFAULT_ELO = 1400


class PikafishEngine:
    """
    UCI bridge for Pikafish Xiangqi engine with NNUE evaluation and ELO rating control.

    Coordinate mapping:
      - Our board  : board[row][col], row=0 is Black's back rank, row=9 is Red's back rank
      - UCI / FEN  : ranks 0-9 from RED's back rank upward -> '0' == our row 9, '9' == our row 0
                     files a-i -> columns 0-8 left-to-right
    """

    _PIECE_TO_FEN = {
        'r_K': 'K', 'r_A': 'A', 'r_E': 'B', 'r_N': 'N',
        'r_R': 'R', 'r_C': 'C', 'r_P': 'P',
        'b_K': 'k', 'b_A': 'a', 'b_E': 'b', 'b_N': 'n',
        'b_R': 'r', 'b_C': 'c', 'b_P': 'p',
    }

    def __init__(self, engine_path: str, nnue_path: Optional[str] = None):
        self.engine_path = os.path.abspath(engine_path)
        self.nnue_path = os.path.abspath(nnue_path) if nnue_path else None
        self.process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._ready = False
        self.current_elo = DEFAULT_ELO
        self._current_multipv = 1

        if not os.path.isfile(self.engine_path):
            raise FileNotFoundError(f"[PIKAFISH] Engine executable not found at: {self.engine_path}")

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self, threads: int = 2, hash_mb: int = 64):
        """Khởi động tiến trình Pikafish qua giao thức UCI."""
        with self._lock:
            if self._ready and self.process and self.process.poll() is None:
                return

            script_dir = os.path.dirname(self.engine_path)
            self.process = subprocess.Popen(
                [self.engine_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',
                bufsize=1,
                cwd=script_dir,
            )

            atexit.register(self._atexit_cleanup)

            # Khởi tạo UCI
            self._send('uci')

            # Đợi phản hồi uciok
            deadline = time.time() + 10.0
            found_uciok = False
            while time.time() < deadline:
                line = self.process.stdout.readline()
                if not line:
                    time.sleep(0.02)
                    continue
                if 'uciok' in line:
                    found_uciok = True
                    break

            if not found_uciok:
                raise TimeoutError("[PIKAFISH] Engine did not respond with 'uciok' within 10s.")

            # Cấu hình Options cơ bản
            self._send(f'setoption name Threads value {threads}')
            self._send(f'setoption name Hash value {hash_mb}')
            if self.nnue_path and os.path.isfile(self.nnue_path):
                self._send(f'setoption name EvalFile value {self.nnue_path}')
            
            # Đồng bộ isready
            self._send('isready')
            deadline = time.time() + 5.0
            while time.time() < deadline:
                line = self.process.stdout.readline()
                if 'readyok' in line:
                    break

            self._ready = True
            print(f"[PIKAFISH] Engine started successfully (Threads={threads}, Hash={hash_mb}MB, Default ELO={self.current_elo})")

    def _atexit_cleanup(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

    def stop(self):
        """Dừng an toàn tiến trình Pikafish."""
        with self._lock:
            if self.process:
                try:
                    self._send('quit')
                    self.process.wait(timeout=2.0)
                except Exception:
                    try:
                        self.process.terminate()
                        self.process.wait(timeout=1.0)
                    except Exception:
                        self.process.kill()
                self.process = None
                self._ready = False
                print("[PIKAFISH] Engine stopped.")

    def __del__(self):
        self.stop()

    # -------------------------------------------------------------------------
    # ELO & Difficulty Control
    # -------------------------------------------------------------------------

    def set_elo(self, elo: int) -> int:
        """Đặt mức ELO cho AI. Tự động làm tròn về nấc gần nhất nếu không trùng."""
        available_elos = sorted(ELO_PRESETS.keys())
        closest_elo = min(available_elos, key=lambda x: abs(x - elo))
        self.current_elo = closest_elo
        preset = ELO_PRESETS[closest_elo]
        print(f"[PIKAFISH] ELO set to {closest_elo} - {preset['title']}")
        return self.current_elo

    def get_current_elo(self) -> int:
        return self.current_elo

    def get_elo_title(self) -> str:
        return ELO_PRESETS.get(self.current_elo, {}).get("title", f"ELO {self.current_elo}")

    def step_elo(self, direction: int = 1) -> int:
        """Tăng hoặc giảm 1 nấc ELO (+1: tăng, -1: giảm)."""
        available_elos = sorted(ELO_PRESETS.keys())
        idx = available_elos.index(self.current_elo) if self.current_elo in available_elos else 2
        new_idx = max(0, min(len(available_elos) - 1, idx + direction))
        return self.set_elo(available_elos[new_idx])

    # -------------------------------------------------------------------------
    # Core Move Generation
    # -------------------------------------------------------------------------

    def pick_best_move(
        self,
        board: list,
        color: str,
        elo: Optional[int] = None,
        movetime_ms: Optional[int] = None,
        depth: Optional[int] = None,
    ) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """
        Lấy nước đi tốt nhất từ Pikafish theo mức ELO đã cấu hình.

        Returns:
            ((src_col, src_row), (dst_col, dst_row)) hoặc None.
        """
        if not self._ready:
            raise RuntimeError("[PIKAFISH] Engine is not started. Call engine.start() first.")

        target_elo = elo if elo is not None else self.current_elo
        preset = ELO_PRESETS.get(target_elo, ELO_PRESETS[DEFAULT_ELO])

        cfg_depth = depth if depth is not None else preset.get("depth")
        cfg_nodes = preset.get("nodes")
        cfg_movetime = movetime_ms if movetime_ms is not None else preset.get("movetime_ms")
        cfg_multipv = preset.get("multipv", 1)
        blunder_rate = preset.get("blunder_rate", 0.0)

        with self._lock:
            # Điều chỉnh MultiPV nếu thay đổi
            if cfg_multipv != self._current_multipv:
                self._send(f'setoption name MultiPV value {cfg_multipv}')
                self._current_multipv = cfg_multipv

            fen = self.board_to_fen(board, color)
            self._send(f'position fen {fen}')

            # Xây dựng lệnh go
            go_cmd = 'go'
            if cfg_movetime:
                go_cmd += f' movetime {cfg_movetime}'
            elif cfg_depth:
                go_cmd += f' depth {cfg_depth}'
            if cfg_nodes:
                go_cmd += f' nodes {cfg_nodes}'

            self._send(go_cmd)

            # Thu thập PVs và bestmove
            multipv_moves: Dict[int, str] = {}
            best_move_str = None
            deadline = time.time() + (30.0 if not cfg_movetime else (cfg_movetime / 1000.0 + 10.0))

            while time.time() < deadline:
                line = self.process.stdout.readline().strip()
                if not line:
                    time.sleep(0.005)
                    continue

                if 'multipv' in line and 'pv' in line:
                    try:
                        parts = line.split()
                        mp_idx = int(parts[parts.index('multipv') + 1])
                        pv_idx = parts.index('pv') + 1
                        if pv_idx < len(parts):
                            multipv_moves[mp_idx] = parts[pv_idx]
                    except Exception:
                        pass

                if line.startswith('bestmove'):
                    parts = line.split()
                    best_move_str = parts[1] if len(parts) > 1 else None
                    break

            # Quyết định nước đi cuối cùng
            chosen_move = best_move_str

            # Mô phỏng sai sót con người ở ELO thấp bằng cách chọn nước trong MultiPV
            if blunder_rate > 0.0 and len(multipv_moves) > 1:
                if random.random() < blunder_rate:
                    sub_moves = [m for k, m in multipv_moves.items() if k > 1 and m]
                    if sub_moves:
                        chosen_move = random.choice(sub_moves)
                        print(f"[PIKAFISH] (ELO {target_elo}) Human-like inaccuracy: picked '{chosen_move}' instead of '{best_move_str}'")

            if chosen_move and chosen_move not in ('(none)', 'null'):
                return self._uci_to_move(chosen_move)

            print(f"[PIKAFISH] [WARN] No valid move returned for FEN: {fen}")
            return None

    # -------------------------------------------------------------------------
    # Coordinate & FEN Helpers
    # -------------------------------------------------------------------------

    def board_to_fen(self, board: list, color: str) -> str:
        rows = []
        for r in range(10):
            row_str = ''
            empty = 0
            for c in range(9):
                p = board[r][c]
                if p == '.':
                    empty += 1
                else:
                    if empty:
                        row_str += str(empty)
                        empty = 0
                    fen_char = self._PIECE_TO_FEN.get(p)
                    if fen_char is None:
                        raise ValueError(f"Unknown piece token: '{p}' at board[{r}][{c}]")
                    row_str += fen_char
            if empty:
                row_str += str(empty)
            rows.append(row_str)

        fen_color = 'w' if color == 'r' else 'b'
        return f"{'/'.join(rows)} {fen_color} - - 0 1"

    def _uci_to_move(self, uci_move: str) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        if len(uci_move) < 4:
            return None
        src_col = ord(uci_move[0]) - ord('a')
        src_row = 9 - int(uci_move[1])
        dst_col = ord(uci_move[2]) - ord('a')
        dst_row = 9 - int(uci_move[3])
        return (src_col, src_row), (dst_col, dst_row)

    def _send(self, cmd: str):
        if self.process and self.process.stdin:
            self.process.stdin.write(cmd + '\n')
            self.process.stdin.flush()
