import sys
import time
import requests

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


class TuongKyDaiSuClient:
    def __init__(self, base_url, token):
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.room_id = None
        
        self.headers_simulation = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def create_match(self, red_name="Người chơi Đỏ", black_name="Robot AI"):
        """Tạo một trận đấu mới và lấy roomId."""
        if not self.token:
            print("[-] [API] Bỏ qua tạo trận vì chưa có SIMULATION_TOKEN")
            return None
            
        url = f"{self.base_url}/api/simulation/matches"
        payload = {
            "redPlayerName": red_name,
            "blackPlayerName": black_name
        }
        
        try:
            response = requests.post(url, headers=self.headers_simulation, json=payload, timeout=5)
            data = response.json()
            
            if response.status_code == 200 and data.get("success"):
                self.room_id = data["data"]["roomId"]
                print(f"[+] [API] Tạo trận đấu thành công. Room ID: {self.room_id}")
                return self.room_id
            else:
                print(f"[-] [API] Lỗi tạo trận đấu: {data}")
                return None
        except Exception as e:
            print(f"[-] [API] Ngoại lệ khi tạo trận: {e}")
            return None

    def send_move_update_board(self, fen, attempts=3):
        """Gửi trạng thái bàn cờ (FEN) mới nhất mỗi khi CÓ MỘT NƯỚC ĐI ĐÃ HOÀN THÀNH."""
        if not self.token:
            return None
        if not self.room_id:
            print("[-] [API] Không thể gửi FEN vì Room ID trống!")
            return None
            
        url = f"{self.base_url}/api/simulation/matches/{self.room_id}/fen"
        payload = {
            "fen": fen
        }
        
        # Captures are committed locally before this call.  Retry transient
        # network/server failures so one dropped response cannot leave the
        # spectator client on the pre-capture FEN.
        for attempt in range(1, max(1, int(attempts)) + 1):
            try:
                response = requests.post(url, headers=self.headers_simulation, json=payload, timeout=5)
                try:
                    data = response.json()
                except ValueError:
                    data = {"raw_response": response.text}
                if response.status_code == 200 and data.get("success"):
                    move_info = data["data"].get("move")
                    print(f"[+] [API] Đã đồng bộ FEN thành công. Phe tiếp theo: {data['data'].get('currentTurn')}")
                    return move_info
                print(f"[-] [API] Lỗi gửi FEN (lần {attempt}): {data}")
                # Invalid FEN/authentication/state-conflict responses cannot
                # be repaired by replaying the same request.
                if response.status_code not in (408, 425, 429) and not 500 <= response.status_code < 600:
                    return None
            except requests.RequestException as exc:
                print(f"[-] [API] Không gửi được FEN (lần {attempt}): {exc}")
            if attempt < max(1, int(attempts)):
                time.sleep(0.25 * attempt)
        print("[-] [API] Đồng bộ FEN thất bại sau các lần thử lại.")
        return None

    def end_match(self, winner="DRAW", reason="OTHER"):
        """Kết thúc trận đấu."""
        if not self.token or not self.room_id:
            return
            
        url = f"{self.base_url}/api/simulation/matches/{self.room_id}/end"
        payload = {
            "winner": winner, 
            "reason": reason  
        }
        
        try:
            response = requests.post(url, headers=self.headers_simulation, json=payload, timeout=5)
            if response.status_code == 200:
                print(f"[+] [API] Đã kết thúc trận đấu phòng {self.room_id}. Người thắng: {winner}")
                self.room_id = None # Reset
            else:
                print(f"[-] [API] Lỗi kết thúc trận đấu: {response.text}")
        except Exception as e:
            print(f"[-] [API] Ngoại lệ khi kết thúc trận: {e}")
