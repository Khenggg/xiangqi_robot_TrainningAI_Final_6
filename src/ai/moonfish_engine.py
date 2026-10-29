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
import queue
import re
from collections import deque


class EngineError(RuntimeError):
    """Engine transport, process or protocol failure; never a no-move result."""


class EngineTimeoutError(EngineError):
    """The engine did not answer before the request deadline."""


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

    def __init__(self, engine_path: str, startup_timeout_sec=10, search_timeout_sec=30):
        """
        Args:
            engine_path: Absolute or relative path to moonfish_ucci.py
        """
        self.engine_path = engine_path
        self.process: subprocess.Popen | None = None
        self._lock = threading.RLock()
        self._ready = False
        self.startup_timeout_sec = startup_timeout_sec
        self.search_timeout_sec = search_timeout_sec
        self._output = None
        self._stderr = deque(maxlen=20)
        self._readers = []
        self._cancel = threading.Event()
        atexit.register(self._atexit_cleanup)

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
        with self._lock:
            if self._ready and self.process is not None and self.process.poll() is None:
                return
            self._dispose_process()
            self._cancel.clear()
            script_path = os.path.abspath(self.engine_path)
            try:
                self.process = subprocess.Popen(
                    [sys.executable, '-u', os.path.basename(script_path)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    encoding='utf-8', errors='replace', bufsize=1,
                    cwd=os.path.dirname(script_path),
                )
                # Readers capture only this session's queue and streams. Old output
                # can never become a bestmove response in a restarted session.
                output = self._output = queue.Queue()
                stderr = self._stderr = deque(maxlen=20)
                self._readers = [
                    threading.Thread(target=self._read_stdout,
                                     args=(self.process.stdout, output), daemon=True),
                    threading.Thread(target=self._drain_stderr,
                                     args=(self.process.stderr, stderr), daemon=True),
                ]
                for reader in self._readers:
                    reader.start()
                self._send('ucci')
                deadline = time.monotonic() + self.startup_timeout_sec
                while self._next_line(deadline, 'startup') != 'ucciok':
                    pass
                self._ready = True
                print('[MOONFISH] Engine ready!')
            except Exception as error:
                self._dispose_process()
                if isinstance(error, EngineError):
                    raise
                raise EngineError(f'[MOONFISH] Startup failed: {error}') from error

    @staticmethod
    def _read_stdout(stream, output):
        try:
            for line in stream:
                output.put(line.strip())
        finally:
            output.put(None)  # EOF is a failure, not a no-move answer.

    @staticmethod
    def _drain_stderr(stream, diagnostics):
        # Fixed-size reads drain even a very long line without retaining it all.
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            diagnostics.append(chunk)

    def _next_line(self, deadline, phase):
        while True:
            if self._cancel.is_set():
                raise EngineError(f'[MOONFISH] {phase} cancelled.')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise EngineTimeoutError(f'[MOONFISH] {phase} timeout.')
            try:
                line = self._output.get(timeout=min(remaining, 0.1))
            except queue.Empty:
                continue
            if line is None:
                details = ''.join(self._stderr)[-1000:]
                raise EngineError(f'[MOONFISH] Process ended during {phase}. {details}')
            return line

    def _dispose_process(self, graceful=False):
        """Called under the request lock; reap before closing reader streams."""
        process = self.process
        self._ready = False
        if process is None:
            return
        try:
            if process.poll() is None:
                if graceful:
                    try:
                        self._send('quit')
                        process.wait(timeout=0.3)
                    except (EngineError, subprocess.TimeoutExpired):
                        process.kill()
                else:
                    process.kill()
            process.wait(timeout=2)
        finally:
            for reader in self._readers:
                reader.join(timeout=1)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            self.process = None
            self._output = None
            self._readers = []

    def _atexit_cleanup(self):
        """Được gọi bởi atexit — force kill subprocess nếu vẫn còn chạy."""
        try:
            self.stop()
        except Exception:
            pass

    def stop(self):
        """Gracefully shut down the engine subprocess."""
        # Wake a pending request before acquiring its lock, so stop cannot wait
        # behind a silent search for the full search timeout.
        self._cancel.set()
        with self._lock:
            self._dispose_process(graceful=True)

    def __del__(self):
        if hasattr(self, '_lock'):
            self._atexit_cleanup()

    # -------------------------------------------------------------------------
    # Core public method — drop-in replacement for ai.pick_best_move()
    # -------------------------------------------------------------------------

    def pick_best_move(self, board: list, color: str, movetime_ms: int = 3000,
                       depth: int = None, nodes: int = None, temperature: float = None):
        """
        Ask Moonfish for the best move from the given board position.

        Args:
            board      : 10×9 list-of-lists (our custom format).
            color      : 'r' for Red, 'b' for Black.
            movetime_ms: Time allowed for search, in milliseconds (converted to depth).
            depth      : Limit the search to a certain depth (if None, calculated from movetime_ms).
            nodes      : Optional maximum number of Moonfish search nodes.
            temperature: Difficulty metadata. Moonfish's deterministic UCCI
                         search has no native temperature command, so this is
                         logged rather than silently changing move legality.

        Returns:
            ((src_col, src_row), (dst_col, dst_row))  in our coordinate system,
            or None if the engine has no move.
        """
        with self._lock:
            if not self._ready:
                raise EngineError('[MOONFISH] Engine is not started. Call engine.start() first.')
            try:
                return self._search(board, color, movetime_ms, depth, nodes, temperature)
            except EngineError:
                self._dispose_process()
                raise

    def _search(self, board, color, movetime_ms, depth, nodes, temperature):
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

        command = f'go depth {depth} movetime {max(1, int(movetime_ms))}'
        if nodes is not None:
            command += f' nodes {max(1, int(nodes))}'
        self._send(command)
        if temperature is not None:
            print(f"[MOONFISH] difficulty temperature={temperature:.2f}")

        # Read lines until we get 'bestmove ...'
        deadline = time.monotonic() + self.search_timeout_sec
        while True:
            line = self._next_line(deadline, 'search')
            if line == 'resign':
                return None
            if line.startswith('bestmove'):
                parts = line.split()
                if len(parts) < 2:
                    raise EngineError('[MOONFISH] Malformed bestmove response.')
                best_move_str = parts[1]
                print(f"[MOONFISH] bestmove: {best_move_str}")
                if best_move_str in ('(none)', 'null', '0000'):
                    return None
                return self._uci_to_move(best_move_str)

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
        if not re.fullmatch(r'[a-i][0-9][a-i][0-9]', uci_move):
            raise EngineError(f'[MOONFISH] Invalid move response: {uci_move!r}')
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
        try:
            if self.process is None or self.process.poll() is not None:
                raise EngineError('[MOONFISH] Engine process is unavailable.')
            self.process.stdin.write(cmd + '\n')
            self.process.stdin.flush()
        except (OSError, ValueError) as error:
            raise EngineError(f'[MOONFISH] Failed to send command: {error}') from error


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
