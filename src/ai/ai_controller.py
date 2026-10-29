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

    def pick_move(self, board_snapshot, color="b"):
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
        # Moonfish strength.
        if difficulty in ("easy", "medium", "hard", "impossible"):
            if self.local_engine is None:
                raise AIEngineError(f"Moonfish {difficulty}-level engine is unavailable.")
            try:
                if difficulty == "impossible":
                    return self._pick_local(
                        board_snapshot, color, movetime_ms=self.config.MOONFISH_THINK_MS
                    )
                if profile is None:
                    raise ValueError(f"Missing configuration for difficulty: {difficulty}")
                return self._pick_local(
                    board_snapshot,
                    color,
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
                    board_snapshot, color, movetime_ms=self.config.MOONFISH_THINK_MS
                )
                return result
            except Exception as e:
                raise AIEngineError(f"Local Moonfish failed: {e}") from e
        
        raise AIEngineError(f"Unsupported engine configuration: {engine_type}")

    def _pick_local(self, board, color, **limits):
        # Timeout invalidates the old process. A subsequent operator-requested
        # pick starts a fresh bounded session in the AI worker, never in the UI.
        if getattr(self.local_engine, '_ready', True) is False:
            self.local_engine.start()
        return self.local_engine.pick_best_move(board, color, **limits)
