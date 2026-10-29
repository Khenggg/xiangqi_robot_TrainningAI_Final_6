import sys
import time
import requests
import threading
import hashlib
import json
import os
from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class FenSyncResult:
    success: bool
    retryable: bool = False
    move: object = None
    error: str = ""

    def __bool__(self):
        return self.success


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
        self._sync_lock = threading.RLock()
        self._sync_jobs = {}
        self._sync_worker = None
        self._sync_sequence = 0
        self._unassigned_fen = None
        self._unassigned_end = None
        self._outbox_path = None
        self._persistence_error = ""
        self._stopping = False
        # Logical rollback commits survive an acknowledged/deleted HTTP job.
        self._fen_commits = {}
        
        self.headers_simulation = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def _outbox_scope(self):
        return {"base_url": self.base_url,
                "token_sha256": hashlib.sha256(self.token.encode("utf-8")).hexdigest()}

    def configure_outbox(self, path):
        """Load room-scoped work without creating rooms or making HTTP calls."""
        with self._sync_lock:
            target = Path(path)
            if self._sync_jobs or self._unassigned_fen is not None or self._unassigned_end is not None:
                raise RuntimeError("Configure outbox before queueing sync work")
            try:
                if target.exists():
                    saved = json.loads(target.read_text(encoding="utf-8"))
                    if not isinstance(saved, dict):
                        raise ValueError('Malformed outbox document')
                    if saved.get("version") != 1 or saved.get("scope") != self._outbox_scope():
                        self._persistence_error = "Outbox schema/account mismatch; retained original file"
                        return False
                    jobs = saved.get("jobs", {})
                    if not isinstance(jobs, dict):
                        raise ValueError("Malformed outbox jobs")
                    restored = {}
                    for room, job in jobs.items():
                        if not isinstance(room, str) or not room or not isinstance(job, dict):
                            raise ValueError("Malformed outbox room")
                        if not isinstance(job.get("fen", ""), str):
                            raise ValueError("Malformed outbox FEN")
                        end = job.get("end")
                        if end is not None and (not isinstance(end, dict)
                                or not isinstance(end.get("winner"), str)
                                or not isinstance(end.get("reason"), str)):
                            raise ValueError("Malformed outbox end payload")
                        if "fen" not in job and end is None:
                            raise ValueError("Empty outbox job")
                        restored[room] = dict(job, due=0.0)
                    pending = saved.get("unassigned_fen")
                    if pending is not None and not isinstance(pending, str):
                        raise ValueError("Malformed unassigned FEN")
                    pending_end = saved.get("unassigned_end")
                    if pending_end is not None and (not isinstance(pending_end, dict)
                            or not isinstance(pending_end.get("winner"), str)
                            or not isinstance(pending_end.get("reason"), str)):
                        raise ValueError("Malformed unassigned end")
                    sequence = max((int(job.get("sequence", 0))
                                    for job in restored.values()), default=0)
                    commits = saved.get("fen_commits", {})
                    if not isinstance(commits, dict) or any(
                            not isinstance(key, str) or not isinstance(value, dict)
                            or not isinstance(value.get("fen"), str)
                            or not isinstance(value.get("revision"), int)
                            for key, value in commits.items()):
                        raise ValueError("Malformed logical FEN commits")
                    self._sync_jobs = restored
                    self._fen_commits = commits
                    self._unassigned_fen = pending
                    self._unassigned_end = pending_end
                    self._sync_sequence = sequence
                self._outbox_path = target
                self._persist_locked()
                return not self._persistence_error
            except (OSError, ValueError, TypeError):
                self._persistence_error = "Cannot load/write durable simulation outbox"
                return False

    def _persist_locked(self):
        if self._outbox_path is None:
            return
        # Only protocol payload and generic failure state are serialized.
        # Credentials, headers and arbitrary exception/provider text stay out.
        jobs = {}
        for room, job in self._sync_jobs.items():
            jobs[room] = {key: job[key] for key in ("fen", "sequence", "end", "blocked") if key in job}
            if job.get("error"):
                jobs[room]["error"] = "Remote sync failed"
        payload = {"version": 1, "scope": self._outbox_scope(), "jobs": jobs,
                   "unassigned_fen": self._unassigned_fen,
                   "unassigned_end": self._unassigned_end,
                   "fen_commits": self._fen_commits}
        target = self._outbox_path
        temporary = target.with_name(target.name + ".tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            self._persistence_error = ""
        except (OSError, ValueError, TypeError):
            self._persistence_error = "Cannot write durable simulation outbox"

    def discard_unassigned_fen(self):
        """A deliberate New Game discards a no-room FEN from the old game."""
        with self._sync_lock:
            self._unassigned_fen = None
            self._unassigned_end = None
            self._persist_locked()

    @property
    def persistence_error(self):
        with self._sync_lock:
            return self._persistence_error

    def shutdown(self, wait_seconds=2.0):
        """Persist immediately, wait only a bounded interval, retain unacked work."""
        with self._sync_lock:
            self._stopping = True
            self._persist_locked()
            worker = self._sync_worker
        if worker is not None and worker is not threading.current_thread():
            worker.join(max(0.0, float(wait_seconds)))
        with self._sync_lock:
            self._persist_locked()
        return worker is None or not worker.is_alive()

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
                with self._sync_lock:
                    if self._unassigned_fen is not None:
                        fen = self._unassigned_fen
                        self._unassigned_fen = None
                        self._queue_room_fen_locked(fen)
                    if self._unassigned_end is not None:
                        job = self._sync_jobs.setdefault(str(self.room_id), {})
                        job["end"] = self._unassigned_end
                        job.setdefault("due", 0.0)
                        job.setdefault("blocked", False)
                        self._unassigned_end = None
                    self._persist_locked()
                self.refresh_sync()
                print(f"[+] [API] Tạo trận đấu thành công. Room ID: {self.room_id}")
                return self.room_id
            else:
                print(f"[-] [API] Lỗi tạo trận đấu: {data}")
                return None
        except Exception as e:
            print(f"[-] [API] Ngoại lệ khi tạo trận: {e}")
            return None

    def send_move_update_board(self, fen, attempts=3, _room_id=None):
        """Gửi trạng thái bàn cờ (FEN) mới nhất mỗi khi CÓ MỘT NƯỚC ĐI ĐÃ HOÀN THÀNH."""
        if not self.token:
            return FenSyncResult(True)
        room_id = _room_id if _room_id is not None else self.room_id
        if not room_id:
            print("[-] [API] Không thể gửi FEN vì Room ID trống!")
            return FenSyncResult(False, error="Room ID trống")
            
        url = f"{self.base_url}/api/simulation/matches/{room_id}/fen"
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
                if not isinstance(data, dict):
                    data = {"invalid_response": "Expected a JSON object"}
                if response.status_code == 200 and data.get("success"):
                    info = data.get("data") or {}
                    if not isinstance(info, dict):
                        info = {}
                    print(f"[+] [API] Đã đồng bộ FEN thành công. Phe tiếp theo: {info.get('currentTurn')}")
                    return FenSyncResult(True, move=info.get("move"))
                print(f"[-] [API] Lỗi gửi FEN (lần {attempt}): {data}")
                # Invalid FEN/authentication/state-conflict responses cannot
                # be repaired by replaying the same request.
                if response.status_code not in (408, 425, 429) and not 500 <= response.status_code < 600:
                    return FenSyncResult(False, error=str(data))
            except requests.RequestException as exc:
                print(f"[-] [API] Không gửi được FEN (lần {attempt}): {exc}")
            if attempt < max(1, int(attempts)):
                time.sleep(0.25 * attempt)
        print("[-] [API] Đồng bộ FEN thất bại sau các lần thử lại.")
        return FenSyncResult(False, retryable=True, error="Đồng bộ FEN thất bại")

    @property
    def sync_pending(self):
        with self._sync_lock:
            return bool(self._sync_jobs or self._unassigned_fen is not None or self._unassigned_end is not None)

    @property
    def sync_blocked(self):
        with self._sync_lock:
            job = self._sync_jobs.get(str(self.room_id))
            return bool(job and job.get("blocked")) or any(j.get("blocked") for j in self._sync_jobs.values())

    @property
    def sync_error(self):
        with self._sync_lock:
            job = self._sync_jobs.get(str(self.room_id))
            if self._unassigned_fen is not None or self._unassigned_end is not None:
                return "Room ID trống"
            return job.get("error", "") if job else next((j.get("error", "") for j in self._sync_jobs.values() if j.get("error")), "")

    @property
    def missing_room(self):
        with self._sync_lock:
            return self._unassigned_fen is not None or self._unassigned_end is not None

    def _queue_room_fen_locked(self, fen):
        self._sync_sequence += 1
        job = self._sync_jobs.setdefault(str(self.room_id), {})
        job.update(fen=fen, sequence=self._sync_sequence, due=0.0,
                   blocked=False, error="")

    def queue_fen(self, fen):
        if not self.token:
            return False
        with self._sync_lock:
            if self.room_id:
                self._unassigned_fen = None
                self._queue_room_fen_locked(fen)
            else:
                self._unassigned_fen = fen
            self._persist_locked()
        self.refresh_sync()
        return True

    def queue_fen_commit(self, fen, commit_id, revision, *, room_id=None):
        """Atomically deduplicate a verified rollback and its outbound FEN.

        HTTP is still serialized by the existing single worker. A retry after
        a journal/outbox crash must not requeue an older board over newer work.
        """
        if not isinstance(commit_id, str) or not commit_id or not isinstance(revision, int):
            raise ValueError("Invalid logical FEN commit")
        target_room = self.room_id if room_id is None else room_id
        key = f"{target_room}:{commit_id}"
        payload = {"fen": fen, "revision": revision}
        with self._sync_lock:
            previous = self._fen_commits.get(key)
            if previous is not None:
                if previous != payload:
                    raise ValueError("Logical FEN commit changed payload")
                if self._persistence_error:
                    self._persist_locked()
                return not self._persistence_error
            self._fen_commits[key] = payload
            if target_room:
                self._unassigned_fen = None
                self._sync_sequence += 1
                job = self._sync_jobs.setdefault(str(target_room), {})
                job.update(fen=fen, sequence=self._sync_sequence, due=0.0,
                           blocked=False, error='')
            else:
                self._unassigned_fen = fen
            self._persist_locked()
            persisted = not self._persistence_error
        self.refresh_sync()
        return persisted

    def end_match(self, winner="DRAW", reason="OTHER"):
        """Close only after the latest queued FEN is acknowledged.

        Jobs retain their own room ID across New Game. Closing an old room
        can never post its FEN or end payload to a newly created room.
        """
        if not self.token:
            return False
        with self._sync_lock:
            if not self.room_id:
                prior = self._unassigned_end
                if prior is None or (prior.get("reason") == "OTHER" and reason != "OTHER"):
                    self._unassigned_end = dict(winner=winner, reason=reason)
                self._persist_locked()
                return True
            job = self._sync_jobs.setdefault(str(self.room_id), {})
            prior = job.get("end")
            # Generic application cleanup must not replace a result already
            # declared by checkmate/resignation. A generic close may upgrade.
            if prior is None or (prior.get("reason") == "OTHER" and reason != "OTHER"):
                job["end"] = dict(winner=winner, reason=reason)
            job.setdefault("due", 0.0)
            job.setdefault("blocked", False)
            self._persist_locked()
        self.refresh_sync()
        return True

    def refresh_sync(self):
        """Schedule due retries; never perform HTTP on the UI thread."""
        with self._sync_lock:
            if self._stopping:
                return
            if self._sync_worker is not None and self._sync_worker.is_alive():
                return
            if not any(not job.get("blocked") and job.get("due", 0) <= time.monotonic()
                       for job in self._sync_jobs.values()):
                return
            self._sync_worker = threading.Thread(target=self._drain_sync, daemon=True,
                                                  name="remote-fen-sync")
            self._sync_worker.start()

    def _drain_sync(self):
        while True:
            with self._sync_lock:
                if self._stopping:
                    return
                ready = [(room, job.copy()) for room, job in self._sync_jobs.items()
                         if not job.get("blocked") and job.get("due", 0) <= time.monotonic()]
                if not ready:
                    return
                room, work = ready[0]
            try:
                if "fen" in work:
                    result = self.send_move_update_board(work["fen"], _room_id=room)
                else:
                    result = self._post_end(room, work["end"])
            except Exception as exc:
                # Unexpected client/response errors remain visible rather
                # than silently killing a worker and spinning new requests.
                result = FenSyncResult(False, error=f"Sync client error: {exc}")
            with self._sync_lock:
                job = self._sync_jobs.get(room)
                if job is None:
                    continue
                # A newer FEN queued while this request ran always wins. The
                # single worker posts it after the old response, never before.
                if "fen" in work and job.get("sequence") != work.get("sequence"):
                    continue
                if not result.success:
                    job.update(blocked=not result.retryable, due=time.monotonic() + 5.0,
                               error=result.error)
                    self._persist_locked()
                    continue
                if "fen" in work:
                    job.pop("fen", None)
                    job.pop("error", None)
                    if "end" in job:
                        self._persist_locked()
                        continue
                self._sync_jobs.pop(room, None)
                if "fen" not in work and str(self.room_id) == room:
                    self.room_id = None
                self._persist_locked()

    def _post_end(self, room, payload):
        url = f"{self.base_url}/api/simulation/matches/{room}/end"
        try:
            response = requests.post(url, headers=self.headers_simulation,
                                     json=payload, timeout=5)
            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError:
                    data = None
                if isinstance(data, dict) and data.get("success") is False:
                    return FenSyncResult(False, error="End match rejected")
                print(f"[+] [API] Đã kết thúc trận đấu phòng {room}.")
                return FenSyncResult(True)
            retryable = response.status_code in (408, 425, 429) or response.status_code >= 500
            return FenSyncResult(False, retryable, error=f"End match HTTP {response.status_code}")
        except requests.RequestException as exc:
            return FenSyncResult(False, True, error=str(exc))
