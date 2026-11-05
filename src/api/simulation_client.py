import sys
import time
import requests
import queue
import threading
from src.core.project_logging import event
import logging
from urllib.parse import quote

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
        self._room_generation = None
        self._last_fen_ack = None
        self._session_id = None
        self._room_session_id = None
        self._room_created = None
        self._pending_room_binding = None
        self._pending_end_binding = None
        self._pending_fen_binding = None
        self._last_end_ack = None
        
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
            self._worker = threading.Thread(target=self._run, name='spectator-api', daemon=False)
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
            if self._worker.is_alive() is True:
                raise RuntimeError("Spectator callbacks still running; retain the journal and retry close")
        self._flush_receipts()

    def _flush_receipts(self):
        if self._pending_room_binding is not None:
            callback, args = self._pending_room_binding
            callback(*args)
            self._pending_room_binding = None
        if self._pending_fen_binding is not None:
            callback, args = self._pending_fen_binding
            callback(*args)
            self._pending_fen_binding = None
        if self._pending_end_binding is not None:
            callback, args = self._pending_end_binding
            callback(*args)
            self._pending_end_binding = None

    def bind_session(self, session_id, room_created, *, restored_room=None):
        """Capture local ownership separately from the currently queued remote room."""
        with self._job_lock:
            self._session_id, self._room_created = session_id, room_created
            if restored_room is not None:
                if (self._match_requested is True or self.room_id is not None
                        or restored_room["base_url"] != self.base_url):
                    raise RuntimeError("Cannot adopt spectator room while another room/server is active")
                self.room_id = restored_room["room_id"]
                self._room_session_id = session_id
                self._room_generation = self._match_generation
                self._last_fen_ack = (self.room_id, restored_room["acknowledged_fen"])
                self._match_requested = True

    def _schedule_match_locked(self, red_name, black_name, initial_fen):
        generation = self._match_generation + 1
        if not self._enqueue_locked(self._create_and_publish, generation, red_name, black_name, initial_fen,
                                    self._session_id, self._room_created):
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

    def _create_and_publish(self, generation, red_name, black_name, initial_fen,
                            session_id=None, room_created=None):
        opened = False
        try:
            self._flush_receipts()
            opened = self._create_match(red_name, black_name) is not None
            if opened:
                self._room_generation = generation
                self._room_session_id = session_id
                self._last_fen_ack = None
                from src.core.fen_utils import INITIAL_FEN
                # Creation ACK acknowledges the API's standard initial layout.
                # It is not a fresh read of a room restored on a later launch.
                self._last_fen_ack = (str(self.room_id), INITIAL_FEN)
                # Save the received room ID before any subsequent projection.
                # This callback captures the queued session, not mutable live state.
                if room_created is not None:
                    args = (session_id, self.base_url, self.room_id, INITIAL_FEN)
                    self._pending_room_binding = (room_created, args)
                    room_created(*args)
                    self._pending_room_binding = None
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

    def submit_board_projection(self, fen, completed, *, match_end=None, session_id=None,
                                room=None, fen_acknowledged=None, end_acknowledged=None,
                                room_refresh=None):
        """Queue display-only delivery; callback True requires an actual response ACK."""
        with self._job_lock:
            if room is not None:
                if room["base_url"] != self.base_url or not room.get("room_id"):
                    return False
                return self._enqueue_locked(self._deliver_room_projection, str(fen), completed,
                                            match_end, dict(room), fen_acknowledged, end_acknowledged,
                                            room_refresh)
            if (not self.token or not self.room_id and not self.pending
                    or self._match_requested is False and match_end is None):
                return False
            generation = self._match_generation
            return self._enqueue_locked(self._deliver_projection, str(fen), generation, completed,
                                        match_end, session_id, fen_acknowledged, end_acknowledged)

    def _deliver_projection(self, fen, generation, completed, match_end,
                            session_id=None, fen_acknowledged=None, end_acknowledged=None):
        success = False
        reason = "Remote board acknowledgement unavailable"
        try:
            self._flush_receipts()
            actual_generation = self._room_generation if self._room_generation is not None else self._match_generation
            if (generation != actual_generation
                    or session_id is not None and session_id != self._room_session_id):
                reason = "Projection belongs to a retired spectator room"
            else:
                receipt = []
                self._send_move_update_board(fen, attempts=1, receipt=receipt)
                success = receipt == [True]
                if success:
                    self._record_fen_ack(self.room_id, fen, fen_acknowledged)
                if success and match_end is not None:
                    target_room = self.room_id
                    success = self._end_match(match_end["winner"], match_end["reason"]) is True
                    reason = "Remote end-match acknowledgement unavailable"
                    if success:
                        self._record_end_ack(target_room, match_end, end_acknowledged)
                        with self._job_lock:
                            if self._match_generation == generation:
                                self._match_requested = False
        except Exception as exc:
            success, reason = False, str(exc)
        completed(success, None if success else reason)

    def _record_fen_ack(self, room_id, fen, fen_acknowledged):
        if fen_acknowledged is not None:
            args = (room_id, fen)
            self._pending_fen_binding = (fen_acknowledged, args)
            fen_acknowledged(*args)
            self._pending_fen_binding = None

    def _record_end_ack(self, room_id, match_end, end_acknowledged):
        if end_acknowledged is not None:
            args = (room_id, dict(match_end))
            self._pending_end_binding = (end_acknowledged, args)
            end_acknowledged(*args)
            self._pending_end_binding = None

    def _deliver_room_projection(self, fen, completed, match_end, room, fen_acknowledged,
                                 end_acknowledged, room_refresh):
        """Retry a known room without adopting it or changing the new room owner."""
        success, reason = False, "Archived spectator acknowledgement unavailable"
        try:
            self._flush_receipts()
            if room_refresh is not None:
                refreshed = room_refresh()
                if (refreshed is None or refreshed["base_url"] != room["base_url"]
                        or refreshed["room_id"] != room["room_id"]):
                    raise RuntimeError("Queued spectator route no longer matches its recorded room")
                room = refreshed
            receipt = []
            if room.get("acknowledged_fen") == fen:
                receipt.append(True)
            else:
                self._send_move_update_board(fen, attempts=1, receipt=receipt, room_id=room["room_id"])
            success = receipt == [True]
            if success:
                self._record_fen_ack(room["room_id"], fen, fen_acknowledged)
            if success and match_end is not None:
                success = (room.get("acknowledged_end") == match_end or self._end_match(
                    match_end["winner"], match_end["reason"],
                    room_id=room["room_id"], retire_current=False) is True)
                reason = "Archived end-match acknowledgement unavailable"
                if success:
                    self._record_end_ack(room["room_id"], match_end, end_acknowledged)
        except Exception as exc:
            success, reason = False, str(exc)
        completed(success, None if success else reason)

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
            if self._room_session_id is None:
                self._end_match(reason='OTHER')
            # Journal-owned old rooms retain their own terminal intent and route.
            # Closing them here could preempt an unacknowledged final capture/FEN.
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

    def _send_move_update_board(self, fen, attempts=3, receipt=None, *, room_id=None):
        """Gửi trạng thái bàn cờ (FEN) mới nhất mỗi khi CÓ MỘT NƯỚC ĐI ĐÃ HOÀN THÀNH."""
        if not self.token:
            return None
        target_room = self.room_id if room_id is None else str(room_id)
        if not target_room:
            print("[-] [API] Không thể gửi FEN vì Room ID trống!")
            return None
        if self._last_fen_ack == (str(target_room), fen):
            if receipt is not None:
                receipt.append(True)
            return None
            
        url = f"{self.base_url}/api/simulation/matches/{quote(str(target_room), safe='')}/fen"
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
                    details = data.get("data") or {}
                    move_info = details.get("move")
                    if str(target_room) == str(self.room_id):
                        self._last_fen_ack = (str(target_room), fen)
                    if receipt is not None:
                        receipt.append(True)
                    print(f"[+] [API] Đã đồng bộ FEN thành công. Phe tiếp theo: {details.get('currentTurn')}")
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

    def _end_match(self, winner="DRAW", reason="OTHER", *, room_id=None, retire_current=True):
        """Kết thúc trận đấu."""
        target_room = self.room_id if room_id is None else str(room_id)
        if not self.token or not target_room:
            return
        if self._last_end_ack == (str(target_room), winner, reason):
            return True
            
        url = f"{self.base_url}/api/simulation/matches/{quote(str(target_room), safe='')}/end"
        payload = {
            "winner": winner, 
            "reason": reason  
        }
        
        try:
            response = requests.post(url, headers=self.headers_simulation, json=payload, timeout=5)
            if response.status_code == 200:
                try:
                    body = response.json()
                except ValueError:
                    body = None
                if isinstance(body, dict) and body.get("success") is False:
                    return False
                self._last_end_ack = (str(target_room), winner, reason)
                print(f"[+] [API] Đã kết thúc trận đấu phòng {target_room}. Người thắng: {winner}")
                if retire_current and str(self.room_id) == str(target_room):
                    self.room_id = None
                    self._last_fen_ack = None
                return True
            else:
                print(f"[-] [API] Lỗi kết thúc trận đấu: {response.text}")
        except Exception as e:
            print(f"[-] [API] Ngoại lệ khi kết thúc trận: {e}")
        return False
