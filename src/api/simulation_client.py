import sys
import time
import requests
import queue
import threading
from src.core.project_logging import event
import logging

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
        self._jobs = queue.Queue(maxsize=128)
        self._worker = None
        self._job_lock = threading.Lock()
        self._closing = threading.Event()
        # Desired session state is separate from the asynchronously updated room_id.
        # None also permits legacy callers that adopt an existing room directly.
        self._match_requested = None
        self._match_generation = 0
        
        self.headers_simulation = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    @property
    def pending(self):
        return self._jobs.unfinished_tasks > 0

    def _submit(self, operation, *args):
        with self._job_lock:
            return self._enqueue_locked(operation, *args)

    def _enqueue_locked(self, operation, *args):
        if not self.token or self._closing.is_set():
            return False
        try:
            self._jobs.put_nowait((operation, args))
        except queue.Full:
            event('api.queue_full', 'Hàng đợi cập nhật spectator đầy; game tiếp tục.', level=logging.ERROR)
            return False
        if self._worker is None:
            self._worker = threading.Thread(target=self._run, name='spectator-api', daemon=True)
            self._worker.start()
        return True

    def _run(self):
        while not self._closing.is_set() or self.pending:
            try:
                operation, args = self._jobs.get(timeout=.1)
            except queue.Empty:
                continue
            try:
                operation(*args)
            except Exception as exc:
                event('api.failed', str(exc), level=logging.WARNING)
            finally:
                self._jobs.task_done()

    def close(self, timeout=.2):
        with self._job_lock:
            self._closing.set()
        if self._worker is not None:
            self._worker.join(timeout)
            if self._worker.is_alive():
                event('api.shutdown_pending', 'Đang chờ cập nhật spectator; không giữ giao diện.', level=logging.WARNING)

    def _schedule_match_locked(self, red_name, black_name, initial_fen):
        generation = self._match_generation + 1
        if not self._enqueue_locked(self._create_and_publish, generation, red_name, black_name, initial_fen):
            return False
        self._match_generation = generation
        self._match_requested = True
        return True

    def create_match(self, red_name="Người chơi Đỏ", black_name="Robot AI", *, initial_fen=None):
        """Explicit New Game: enqueue a new room even if one is already open."""
        with self._job_lock:
            return self._schedule_match_locked(red_name, black_name, initial_fen)

    def ensure_match(self, red_name="Người chơi Đỏ", black_name="Robot AI", *, initial_fen=None):
        """Start/resume: reuse an open or queued room, reopen after an accepted end.

        True means locally scheduled/reused, not a remote HTTP acknowledgement.
        """
        with self._job_lock:
            if not self.token or self._closing.is_set():
                return False
            if self._match_requested or (self._match_requested is None and self.room_id):
                return True
            return self._schedule_match_locked(red_name, black_name, initial_fen)

    def _create_and_publish(self, generation, red_name, black_name, initial_fen):
        opened = False
        try:
            opened = self._create_match(red_name, black_name) is not None
            # Remote simulation API initializes new rooms with standard Xiangqi starting FEN.
            # Only publish initial_fen if customized (differs from standard starting layout);
            # sending the unchanged starting FEN causes HTTP 400 'FEN giống cũ hoặc thay đổi bất thường'.
            if opened and initial_fen is not None:
                fen_str = str(initial_fen).strip()
                if not fen_str.startswith("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR"):
                    self._send_move_update_board(fen_str)
        finally:
            if not opened:
                with self._job_lock:
                    # An older failed request must not cancel a newer queued session.
                    if self._match_generation == generation:
                        self._match_requested = False

    def send_move_update_board(self, fen, attempts=3):
        with self._job_lock:
            if self._match_requested is False or (not self.room_id and not self.pending):
                return False
            return self._enqueue_locked(self._send_move_update_board, str(fen), attempts)

    def end_match(self, winner="DRAW", reason="OTHER"):
        with self._job_lock:
            if self._match_requested is False or (not self.room_id and not self.pending):
                return False
            if not self._enqueue_locked(self._end_match, winner, reason):
                return False
            self._match_generation += 1
            self._match_requested = False
            return True

    def _create_match(self, red_name="Người chơi Đỏ", black_name="Robot AI"):
        """Tạo một trận đấu mới và lấy roomId."""
        if self.room_id is not None:
            self._end_match(reason='OTHER')
            # Never send the new game's FEN to an old room after close failure.
            self.room_id = None
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

    def _send_move_update_board(self, fen, attempts=3):
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

    def _end_match(self, winner="DRAW", reason="OTHER"):
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
