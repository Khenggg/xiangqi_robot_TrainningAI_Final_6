# ==================================
# === FILE: VIP/ai_controller.py ===
# === AI Controller — Smart Engine Wrapper (Hybrid) ===
# ==================================
import traceback


class AIController:
    """Wrapper quản lý cả Local Moonfish Engine và Cloud Engine.

    Cách dùng từ main_VIP.py:
        ai_ctrl = AIController(local_engine, cloud_engine, config)
    """

    def __init__(self, local_engine, cloud_engine, config):
        """
        Args:
            local_engine: MoonfishEngine instance (có thể None nếu config là CLOUD)
            cloud_engine: CloudEngine instance (có thể None nếu config là LOCAL)
            config: module config
        """
        self.local_engine = local_engine
        self.cloud_engine = cloud_engine
        self.config = config

    def pick_move(self, board_snapshot, color="b"):
        """Gọi Moonfish để lấy nước đi tốt nhất.

        Hàm này chạy BLOCKING — phải gọi trong thread riêng.

        Args:
            board_snapshot: bản sao board 10x9 tại thời điểm AI bắt đầu nghĩ
            color:          màu AI đang đánh ('b' = đen)

        Returns:
            (src, dst) tuple nếu tìm được nước đi
            None nếu thất bại hoặc engine chưa khởi động
        """
        engine_type = getattr(self.config, "ENGINE_TYPE", "LOCAL")

        # THỬ CLOUD ENGINE (Nếu mode là HYBRID hoặc CLOUD)
        if engine_type in ["HYBRID", "CLOUD"]:
            if self.cloud_engine is not None:
                try:
                    result = self.cloud_engine.pick_best_move(board_snapshot, color)
                    return result
                except Exception as e:
                    if engine_type == "CLOUD":
                        print(f"[AI] ❌ Lỗi Cloud API (Chế độ chỉ Cloud): {e}")
                        return None
                    else:
                        print(f"[AI] ⚠️ Cloud API timeout/error: {e} -> Dùng Local Moonfish để cứu nguy!")
            else:
                 print("[AI] ⚠️ Chế độ Cloud được bật nhưng chưa có instance CloudEngine.")

        # THỬ LOCAL ENGINE (Nếu mode là LOCAL hoặc HYBRID fallback fail)
        if engine_type in ["HYBRID", "LOCAL"]:
            if self.local_engine is None:
                print("[AI] ❌ Moonfish engine chưa khởi động! "
                      "Kiểm tra file exe trong thư mục moonfish/.")
                return None
            
            try:
                result = self.local_engine.pick_best_move(
                    board_snapshot, color, movetime_ms=self.config.MOONFISH_THINK_MS
                )
                return result
            except Exception as e:
                print(f"[AI] ❌ Lỗi cả Local Moonfish: {e}")
                traceback.print_exc()
                return None
        
        return None
