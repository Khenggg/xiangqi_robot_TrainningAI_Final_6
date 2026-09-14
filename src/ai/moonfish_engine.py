# =============================================================================
# === FILE: moonfish_engine.py ===
# === Bridge between our custom board format and the Moonfish UCCI engine. ===
# =============================================================================
#
# SETUP:
#   Moonfish is a Python-based Xiangqi engine cloned from:
#   https://github.com/walker8088/moonfish.git
#   
#   The engine files should be in: <project_root>/moonfish/
#   Main file: moonfish_ucci.py
#
# USAGE (drop-in replacement for ai.pick_best_move):
#
#   from src.ai.moonfish_engine import MoonfishEngine
#   engine = MoonfishEngine("moonfish/moonfish_ucci.py")
#   engine.start()
#   move = engine.pick_best_move(board, "b", movetime_ms=3000)
#   engine.stop()

import subprocess
import threading
import time
import os
import atexit


class MoonfishEngine:
    """
    UCCI bridge for the Moonfish Xiangqi engine (Python-based).

    Coordinate systems:
      - Our board  : board[row][col], row=0 is Black's back rank, row=9 is Red's back rank
      - UCCI / FEN : ranks 0-9 from RED's back rank upward → '0' == our row 9, '9' == our row 0
                     files a-i → columns 0-8 left-to-right
    """

    # -------------------------------------------------------------------------
    # Piece mapping: our token → FEN character  (upper=Red, lower=Black)
    # Note: Elephant = 'B' (bishop) in standard Xiangqi FEN
    # -------------------------------------------------------------------------
    _PIECE_TO_FEN = {
        'r_K': 'K', 'r_A': 'A', 'r_E': 'B', 'r_N': 'N',
        'r_R': 'R', 'r_C': 'C', 'r_P': 'P',
        'b_K': 'k', 'b_A': 'a', 'b_E': 'b', 'b_N': 'n',
        'b_R': 'r', 'b_C': 'c', 'b_P': 'p',
    }

    def __init__(self, engine_path: str):
        """
        Args:
            engine_path: Absolute or relative path to moonfish_ucci.py
        """
        self.engine_path = engine_path
        self.process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._ready = False

        if not os.path.isfile(engine_path):
            raise FileNotFoundError(
                f"[MOONFISH] Engine not found at: {engine_path}\n"
                "Clone from: https://github.com/walker8088/moonfish.git"
            )

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self, nnue_path: str | None = None):
        """
        Launch the Moonfish Python subprocess and wait for 'ucciok'.

        Args:
            nnue_path: Not used for Moonfish (kept for compatibility).
        """
        import sys
        
        # Run Python script with current Python interpreter
        # Use absolute path for the script
        script_path = os.path.abspath(self.engine_path)
        script_dir = os.path.dirname(script_path)
        script_name = os.path.basename(script_path)
        
        self.process = subprocess.Popen(
            [sys.executable, script_name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # Capture stderr for debugging
            encoding='utf-8',
            bufsize=1,            # line-buffered
            cwd=script_dir,  # Run in the script's directory
        )

        # Đăng ký atexit handler để đảm bảo subprocess bị kill khi thoát
        atexit.register(self._atexit_cleanup)

        self._send('ucci')

        # Wait for 'ucciok' (with 10-second timeout)
        # Moonfish prints "Moonfish" first, then waits for commands
        deadline = time.time() + 10
        found_name = False
        while time.time() < deadline:
            line = self.process.stdout.readline().strip()
            if not line:
                # Check stderr for errors
                if self.process.stderr:
                    err_line = self.process.stderr.readline().strip()
                    if err_line:
                        print(f"[MOONFISH] stderr: {err_line}")
                continue
            
            # Debug output (comment out for production)
            # print(f"[MOONFISH] DEBUG: Received line: '{line}'")
            
            # Moonfish prints its name first
            if line == 'Moonfish' or 'Moonfish' in line:
                found_name = True
                # print("[MOONFISH] Engine name received.")
                continue
            
            if line == 'ucciok':
                self._ready = True
                print("[MOONFISH] ✅ Engine ready!")
                return
        
        if found_name:
            # Engine responded but didn't send ucciok - might be waiting for more input
            self._ready = True
            print("[MOONFISH] ✅ Engine ready (name received)!")
            return
            
        raise RuntimeError("[MOONFISH] Engine did not respond with 'ucciok' in time.")

    def _atexit_cleanup(self):
        """Được gọi bởi atexit — force kill subprocess nếu vẫn còn chạy."""
        if self.process and self.process.poll() is None:
            try:
                self.process.kill()
                self.process.wait(timeout=2)
                print("[MOONFISH] 🛑 atexit: subprocess killed.")
            except Exception:
                pass

    def stop(self):
        """Gracefully shut down the engine subprocess."""
        if self.process:
            try:
                self._send('quit')
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except Exception:
                    self.process.kill()
            self.process = None
            self._ready = False
            print("[MOONFISH] Engine stopped.")

    def __del__(self):
        self.stop()

    # -------------------------------------------------------------------------
    # Core public method — drop-in replacement for ai.pick_best_move()
    # -------------------------------------------------------------------------

    def pick_best_move(self, board: list, color: str, movetime_ms: int = 3000, depth: int = None):
        """
        Ask Moonfish for the best move from the given board position.

        Args:
            board      : 10×9 list-of-lists (our custom format).
            color      : 'r' for Red, 'b' for Black.
            movetime_ms: Time allowed for search, in milliseconds (converted to depth).
            depth      : Limit the search to a certain depth (if None, calculated from movetime_ms).

        Returns:
            ((src_col, src_row), (dst_col, dst_row))  in our coordinate system,
            or None if the engine has no move.
        """
        if not self._ready:
            raise RuntimeError("[MOONFISH] Engine is not started. Call engine.start() first.")

        with self._lock:
            fen = self.board_to_fen(board, color)
            print(f"[MOONFISH] FEN: {fen}")

            self._send(f'position fen {fen}')
            
            # Moonfish doesn't support movetime properly, use depth instead
            if depth is None:
                # Convert movetime to approximate depth (rough estimate)
                # 1000ms ~ depth 3, 3000ms ~ depth 5, 5000ms ~ depth 6
                if movetime_ms <= 1000:
                    depth = 3
                elif movetime_ms <= 3000:
                    depth = 5
                else:
                    depth = 6
            
            self._send(f'go depth {depth}')

            # Read lines until we get 'bestmove ...'
            best_move_str = None
            deadline = time.time() + 30  # Safety timeout
            while time.time() < deadline:
                line = self.process.stdout.readline().strip()
                if not line:
                    time.sleep(0.01)
                    continue
                if line.startswith('bestmove'):
                    parts = line.split()
                    best_move_str = parts[1] if len(parts) > 1 else None
                    print(f"[MOONFISH] bestmove: {best_move_str}")
                    break

            if best_move_str and best_move_str != '(none)' and best_move_str != 'null':
                return self._uci_to_move(best_move_str)

            print("[MOONFISH] ⚠️ No valid move returned.")
            return None

    # -------------------------------------------------------------------------
    # Board → FEN conversion
    # -------------------------------------------------------------------------

    def board_to_fen(self, board: list, color: str) -> str:
        """
        Convert our 10×9 board to a Xiangqi FEN string.

        Our board[0] = Black's back rank = FEN rank 9 (top of string).
        Our board[9] = Red's  back rank = FEN rank 0 (bottom of string).

        FEN colour: 'w' = Red to move, 'b' = Black to move.
        """
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
        # FEN format: <position> <color> - - 0 1
        return f"{'/'.join(rows)} {fen_color} - - 0 1"

    # -------------------------------------------------------------------------
    # UCI move → our coordinate format
    # -------------------------------------------------------------------------

    def _uci_to_move(self, uci_move: str):
        """
        Convert a UCCI move string to our ((src_col, src_row), (dst_col, dst_row)) format.

        UCCI move format: <file><rank><file><rank>  e.g. 'h2e2', 'e9e8'
          - file: 'a'–'i' → column 0–8
          - rank: '0'–'9' → UCCI rank (0 = Red's back rank = our row 9)
        """
        if len(uci_move) < 4:
            return None
        src_col = ord(uci_move[0]) - ord('a')      # 'a'=0 ... 'i'=8
        src_row = 9 - int(uci_move[1])             # UCCI rank 0 → our row 9, rank 9 → our row 0
        dst_col = ord(uci_move[2]) - ord('a')
        dst_row = 9 - int(uci_move[3])
        return (src_col, src_row), (dst_col, dst_row)

    # -------------------------------------------------------------------------
    # Internal helper
    # -------------------------------------------------------------------------

    def _send(self, cmd: str):
        """Write a command line to the engine's stdin."""
        self.process.stdin.write(cmd + '\n')
        self.process.stdin.flush()


# =============================================================================
# Quick self-test  (run: python moonfish_engine.py)
# =============================================================================
if __name__ == '__main__':
    import sys
    from src.core import xiangqi

    script_path = input("Enter path to moonfish_ucci.py: ").strip().strip('"')

    engine = MoonfishEngine(script_path)
    engine.start()

    board = xiangqi.get_board()
    print("\nStarting position FEN:", engine.board_to_fen(board, 'r'))

    print("\nAsking Moonfish for best move for Black...")
    move = engine.pick_best_move(board, 'b', movetime_ms=2000)
    print(f"Best move: {move}")

    engine.stop()
    print("Done.")
