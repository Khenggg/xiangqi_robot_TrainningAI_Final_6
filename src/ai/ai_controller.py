# =============================================================================
# === FILE: src/ai/ai_controller.py ===
# === AI Controller — Smart Engine Wrapper (Hybrid / Pikafish / Moonfish) ===
# =============================================================================
import traceback
from typing import Optional, Tuple, Any


class AIController:
    """Wrapper quản lý cả Local Engine (Pikafish / Moonfish) và Cloud Engine.

    Hỗ trợ kiểm soát độ khó theo mức điểm ELO (800 - 3000+) tương tự Chess.com.
    """

    def __init__(self, local_engine: Any, cloud_engine: Any, config: Any):
        """
        Args:
            local_engine: PikafishEngine hoặc MoonfishEngine instance
            cloud_engine: CloudEngine instance
            config: module config
        """
        self.local_engine = local_engine
        self.cloud_engine = cloud_engine
        self.config = config
        self.current_elo = getattr(config, "DEFAULT_AI_ELO", 1400)
        
        # Đồng bộ ELO ban đầu xuống local engine nếu được hỗ trợ
        if self.local_engine and hasattr(self.local_engine, "set_elo"):
            self.current_elo = self.local_engine.set_elo(self.current_elo)

    def set_elo(self, elo: int) -> Tuple[int, str]:
        """Đặt mức ELO cho AI. Trả về (elo, title)."""
        if self.local_engine and hasattr(self.local_engine, "set_elo"):
            self.current_elo = self.local_engine.set_elo(elo)
            title = self.local_engine.get_elo_title()
            return self.current_elo, title
        self.current_elo = elo
        return self.current_elo, f"ELO {elo}"

    def step_elo(self, direction: int = 1) -> Tuple[int, str]:
        """Tăng hoặc giảm 1 nấc ELO (+1: tăng, -1: giảm)."""
        if self.local_engine and hasattr(self.local_engine, "step_elo"):
            self.current_elo = self.local_engine.step_elo(direction)
            title = self.local_engine.get_elo_title()
            return self.current_elo, title
        return self.current_elo, f"ELO {self.current_elo}"

    def get_elo_info(self) -> Tuple[int, str]:
        """Lấy thông tin ELO hiện tại: (elo_score, title)."""
        if self.local_engine and hasattr(self.local_engine, "get_elo_title"):
            return self.local_engine.get_current_elo(), self.local_engine.get_elo_title()
        return self.current_elo, f"ELO {self.current_elo}"

    def pick_move(self, board_snapshot: list, color: str = "b") -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """Gọi Engine để lấy nước đi tốt nhất.

        Hàm này chạy BLOCKING — phải gọi trong thread riêng.

        Args:
            board_snapshot: bản sao board 10x9 tại thời điểm AI bắt đầu nghĩ
            color:          màu AI đang đánh ('b' = đen)

        Returns:
            (src, dst) tuple nếu tìm được nước đi, hoặc None.
        """
        engine_type = getattr(self.config, "ENGINE_TYPE", "LOCAL")

        # 1. THỬ CLOUD ENGINE (Nếu mode là HYBRID hoặc CLOUD)
        # Lưu ý: Nếu ở mode HYBRID mà đang muốn chơi theo ELO địa phương của Pikafish,
        # ta vẫn ưu tiên Cloud nếu được cấu hình rõ ràng.
        if engine_type in ["HYBRID", "CLOUD"]:
            if self.cloud_engine is not None:
                try:
                    result = self.cloud_engine.pick_best_move(board_snapshot, color)
                    if result:
                        return result
                except Exception as e:
                    if engine_type == "CLOUD":
                        print(f"[AI] [ERR] Lỗi Cloud API (Chế độ chỉ Cloud): {e}")
                        return None
                    else:
                        print(f"[AI] [WARN] Cloud API timeout/error: {e} -> Chuyển sang Local Engine...")
            else:
                if engine_type == "CLOUD":
                    print("[AI] [WARN] Chế độ Cloud được bật nhưng chưa có instance CloudEngine.")
                    return None

        # 2. THỬ LOCAL ENGINE (Pikafish / Moonfish)
        if engine_type in ["HYBRID", "LOCAL"]:
            if self.local_engine is None:
                print("[AI] [ERR] Local engine chưa khởi động! Kiểm tra đường dẫn engine trong config.py.")
                return None
            
            try:
                # Nếu là PikafishEngine (có hỗ trợ ELO)
                if hasattr(self.local_engine, "pick_best_move"):
                    if hasattr(self.local_engine, "current_elo"):
                        result = self.local_engine.pick_best_move(
                            board_snapshot, color, elo=self.current_elo
                        )
                    else:
                        think_ms = getattr(self.config, "MOONFISH_THINK_MS", 1000)
                        result = self.local_engine.pick_best_move(
                            board_snapshot, color, movetime_ms=think_ms
                        )
                    return result
            except Exception as e:
                print(f"[AI] [ERR] Lỗi Local Engine: {e}")
                traceback.print_exc()
                return None
        
        return None
