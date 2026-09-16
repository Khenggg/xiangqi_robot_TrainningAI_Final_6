# ==================================
# === FILE: src/ai/cloud_engine.py ===
# === AI Engine via tuongkydaisu.com ===
# ==================================
import requests
import time
from src.core.fen_utils import board_array_to_fen

class CloudEngine:
    def __init__(self, api_url, timeout_sec=5):
        self.api_url = api_url
        self.timeout_sec = timeout_sec

    def start(self):
        """Khởi động Cloud Engine (Có thể test ping nhanh nếu cần)"""
        print(f"[CLOUD_ENGINE] ☁️ Bắt đầu kết nối đến {self.api_url}")
        try:
            # Gửi 1 request rỗng hoặc không làm gì, chỉ báo hiệu là đã sẵn sàng
            pass
        except Exception as e:
            print(f"[CLOUD_ENGINE] ⚠️ Cảnh báo khởi động: {e}")

    def stop(self):
        """Dừng Cloud Engine (Không cần làm gì đặc biệt với REST API)"""
        print("[CLOUD_ENGINE] ☁️ Đã dừng.")

    def pick_best_move(self, board, turn_color="b", movetime_ms=None):
        """
        Gọi REST API tuongkydaisu.com để lấy nước đi tốt nhất.
        
        Args:
            board: Mảng 2D 10x9 chứa trạng thái cờ hiện tại.
            turn_color: Lượt của bên nào ('r' hoặc 'b').
            movetime_ms: Không sử dụng trên Cloud API (cố định ở server).
            
        Returns:
            Tuple ((src_col, src_row), (dst_col, dst_row)) hoặc None nếu lỗi.
        """
        # 1. Chuyển đổi trạng thái bàn cờ sang chuỗi FEN
        fen = board_array_to_fen(board, turn_color, move_number=1)
        
        # 2. Chuẩn bị payload
        payload = {"fen": fen}
        headers = {"Content-Type": "application/json"}
        
        print(f"[CLOUD_ENGINE] 📡 Đang gửi FEN lên server: {fen}")
        start_time = time.time()
        
        # 3. Gửi Request
        response = requests.post(
            self.api_url, 
            json=payload, 
            headers=headers, 
            timeout=self.timeout_sec
        )
        
        # Sẽ tung ra lỗi (Exception) nếu status code không phải 2xx
        # Lỗi này sẽ được ai_controller.py bắt lại để Fallback
        response.raise_for_status() 
        
        data = response.json()
        
        if data.get("success"):
            best_move_uci = data.get("data", {}).get("bestMove")
            if best_move_uci:
                elapsed = time.time() - start_time
                nodes = data.get("data", {}).get("nodes", "N/A")
                print(f"[CLOUD_ENGINE] ✅ Nhận phản hồi sau {elapsed:.2f}s (Nodes: {nodes}) -> Move: {best_move_uci}")
                return self._uci_to_move(best_move_uci)
        
        raise ValueError(f"Server trả về dữ liệu không hợp lệ: {data}")

    def _uci_to_move(self, uci_str):
        """
        Dịch chuỗi UCI (VD: 'h2e2') thành tuple tọa độ lưới cho app.
        a-i -> 0-8
        0-9 -> 9-0 (inversion for internal board representation)
        """
        if len(uci_str) < 4:
            return None
            
        src_col_char = uci_str[0].lower()
        src_row_char = uci_str[1]
        dst_col_char = uci_str[2].lower()
        dst_row_char = uci_str[3]

        # a=0, b=1, ..., i=8
        c1 = ord(src_col_char) - ord('a')
        c2 = ord(dst_col_char) - ord('a')

        # Hàng 0 (đỏ) -> index 9, Hàng 9 (đen) -> index 0
        r1 = 9 - int(src_row_char)
        r2 = 9 - int(dst_row_char)

        return ((c1, r1), (c2, r2))
