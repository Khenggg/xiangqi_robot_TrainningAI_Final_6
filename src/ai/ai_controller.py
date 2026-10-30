import math
import threading
import time


def ai_think_budget_seconds(config):
    """One wall-clock allowance for engine startup, cloud and local search."""
    try:
        requested = float(getattr(config, "AI_MAX_THINK_SECONDS", 30.0))
    except (TypeError, ValueError):
        return 30.0
    return min(30.0, requested) if math.isfinite(requested) and requested > 0 else 30.0


# ==================================
# === FILE: VIP/ai_controller.py ===
# === AI Controller — Smart Engine Wrapper (Hybrid) ===
# ==================================
class AIEngineError(RuntimeError):
    """AI could not produce a trustworthy result; the game must remain active."""


class AIController:
    """Wrapper quản lý cả Local Moonfish Engine và Cloud Engine.

    Cách dùng từ main_VIP.py:
        ai_ctrl = AIController(local_engine, cloud_engine, config)
    """

    def __init__(self, local_engine, cloud_engine, config, policy_engine=None):
        """
        Args:
            local_engine: MoonfishEngine instance (có thể None nếu config là CLOUD)
            cloud_engine: CloudEngine instance (có thể None nếu config là LOCAL)
            config: module config
        """
        self.local_engine = local_engine
        self.cloud_engine = cloud_engine
        self.config = config
        self.policy_engine = policy_engine
        self._search_lock = threading.Lock()
        self._search_thread = None

    def pick_move(self, board_snapshot, color="b"):
        """Bound all engine work; never queue another search behind a stuck one.

        An abandoned provider call retains its sole engine slot until it exits.
        The caller can immediately choose a legal fallback on timeout or busy.
        """
        deadline = time.monotonic() + ai_think_budget_seconds(self.config)
        completed = threading.Event()
        outcome = {}

        def search():
            try:
                outcome['move'] = self._pick_move_with_deadline(board_snapshot, color, deadline)
            except Exception as error:
                outcome['error'] = error
            finally:
                completed.set()

        with self._search_lock:
            if self._search_thread is not None and self._search_thread.is_alive():
                raise AIEngineError("Previous engine search is still busy; use a legal fallback.")
            worker = threading.Thread(target=search, daemon=True, name="ai-engine-search")
            self._search_thread = worker
            worker.start()
        if not completed.wait(max(0.0, deadline - time.monotonic())):
            raise AIEngineError("AI thinking deadline exceeded; use a legal fallback.")
        if time.monotonic() > deadline:
            raise AIEngineError("AI result arrived after the thinking deadline.")
        if 'error' in outcome:
            raise outcome['error']
        return outcome['move']

    def _pick_move_with_deadline(self, board_snapshot, color, deadline):
        """Gọi Moonfish để lấy nước đi tốt nhất.

        Hàm này chạy BLOCKING — phải gọi trong thread riêng.

        Args:
            board_snapshot: bản sao board 10x9 tại thời điểm AI bắt đầu nghĩ
            color:          màu AI đang đánh ('b' = đen)

        Returns:
            (src, dst) tuple nếu tìm được nước đi
            None chỉ khi engine báo hết nước. AIEngineError khi engine lỗi.
        """
        difficulty = getattr(self.config, "AI_DIFFICULTY", "hard")
        profiles = getattr(self.config, "AI_DIFFICULTY_PROFILES", {})
        profile = profiles.get(difficulty)

        # Player-selected levels must always stay local: cloud fallback would
        # make the advertised strength unpredictable.  Impossible deliberately
        # uses the old call signature so it remains the project's original
        # Moonfish strength, subject to the total thinking deadline.
        if difficulty in ("easy", "medium", "hard", "impossible"):
            if self.local_engine is None:
                raise AIEngineError(f"Moonfish {difficulty}-level engine is unavailable.")
            try:
                if difficulty == "impossible":
                    return self._pick_local(
                        board_snapshot, color, deadline=deadline, movetime_ms=self.config.MOONFISH_THINK_MS
                    )
                if profile is None:
                    raise ValueError(f"Missing configuration for difficulty: {difficulty}")
                return self._pick_local(
                    board_snapshot,
                    color,
                    deadline=deadline,
                    movetime_ms=profile["think_ms"],
                    depth=profile["depth"],
                    nodes=profile["nodes"],
                    temperature=profile["temperature"],
                )
            except Exception as e:
                raise AIEngineError(f"Moonfish {difficulty}-level engine failed: {e}") from e

        engine_type = getattr(self.config, "ENGINE_TYPE", "LOCAL")

        # THỬ CLOUD ENGINE (Nếu mode là HYBRID hoặc CLOUD)
        if engine_type in ["HYBRID", "CLOUD"]:
            if self.cloud_engine is not None:
                try:
                    result = self.cloud_engine.pick_best_move(board_snapshot, color)
                    return result
                except Exception as e:
                    if engine_type == "CLOUD":
                        raise AIEngineError(f"Cloud API failed: {e}") from e
                    else:
                        print(f"[AI] ⚠️ Cloud API timeout/error: {e} -> Dùng Local Moonfish để cứu nguy!")
            else:
                if engine_type == "CLOUD":
                    raise AIEngineError('Cloud engine is unavailable.')

        # THỬ LOCAL ENGINE (Nếu mode là LOCAL hoặc HYBRID fallback fail)
        if engine_type in ["HYBRID", "LOCAL"]:
            if self.local_engine is None:
                raise AIEngineError('Moonfish engine is unavailable.')
            
            try:
                result = self._pick_local(
                    board_snapshot, color, deadline=deadline, movetime_ms=self.config.MOONFISH_THINK_MS
                )
                return result
            except Exception as e:
                raise AIEngineError(f"Local Moonfish failed: {e}") from e
        
        raise AIEngineError(f"Unsupported engine configuration: {engine_type}")

    def _pick_local(self, board, color, *, deadline, **limits):
        # Startup consumes the same allowance as search. The outer worker owns
        # the engine until both finish, including after the caller times out.
        if getattr(self.local_engine, '_ready', True) is False:
            self.local_engine.start()
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            raise AIEngineError("AI thinking deadline exhausted before local search.")
        requested = limits.get("movetime_ms")
        if requested is None:
            requested = remaining_ms
        limits["movetime_ms"] = max(1, min(int(requested), remaining_ms, 30_000))
        return self.local_engine.pick_best_move(board, color, **limits)
