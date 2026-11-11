"""Retry optional projections of committed truth; this worker never commands FR3."""
from collections import deque
import json
import logging
import threading
import time

from src.core.project_logging import event
from src.core.session_journal import decode


class ProjectionWorker:
    def __init__(self, state, journal):
        self.state, self.journal = state, journal
        self._closed = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self._inflight = {}
        self._completions = deque()
        self._retry_after = {}
        self._failures = {}
        self._last_errors = {}
        self._spectator_disabled_logged = False
        self._thread = threading.Thread(target=self._run, name="committed-projection", daemon=False)
        self._thread.start()

    def wake(self):
        self._wake.set()

    def _current(self, entry):
        return (not self._closed.is_set() and entry[0] == self.journal.session_id
                and entry[1] == self.state.board_revision)

    def _eligible(self, entry):
        if self._closed.is_set():
            return False
        if entry[2] == "twin":
            return self._current(entry)
        # Spectator states remain ordered, including old revisions of the live
        # match and archived matches with their own durable room binding.
        return entry[0] != self.journal.session_id or entry[1] <= self.state.board_revision

    def _completed(self, entry, success, error=None):
        if self._closed.is_set():
            return
        with self._lock:
            self._completions.append((entry, success, error))
        self.wake()

    def _drain_completions(self):
        with self._lock:
            completions = list(self._completions)
            self._completions.clear()
        for entry, success, error in completions:
            key = (entry[0], entry[2])
            if self._inflight.get(key) != entry:
                continue
            self._inflight.pop(key, None)
            if success:
                self.journal.acknowledge_projection(entry)
                self._failures.pop(key, None)
                self._retry_after.pop(key, None)
                self._last_errors.pop(key, None)
            else:
                failures = self._failures.get(key, 0) + 1
                self._failures[key] = failures
                self._retry_after[key] = time.monotonic() + min(30.0, 2.0 ** min(failures, 5))
                if self._last_errors.get(key) != error:
                    self._last_errors[key] = error
                    event("projection.pending", "Display update pending; the game keeps the committed move",
                          level=logging.WARNING, channel=entry[2], revision=entry[1], reason=error)
            if entry[0] == self.journal.session_id:
                pending = self.journal.pending_projections()
                self.state.update_projection_status(self.state.board_revision, bool(pending), error if not success else None)

    def _submit(self, entry):
        key = (entry[0], entry[2])
        if (key in self._inflight or time.monotonic() < self._retry_after.get(key, 0)
                or not self._eligible(entry)):
            return
        payload = decode(json.loads(entry[3]))
        self._inflight[key] = entry
        if entry[2] == "twin":
            # Reset/commit cannot replace this board between validation and the
            # local mirror update. Never wait behind a business transition.
            if not self.state._transition_lock.acquire(blocking=False):
                self._inflight.pop(key, None)
                return
            try:
                if (not self._current(entry) or self.state.pending_move is not None
                        or self.state.pending_test_motion is not None
                        or self.state.pick_test_mode or self.state.pick_test_resume_required):
                    self._inflight.pop(key, None)
                    return
                observer = self.state._board_observer
                if observer is None:
                    event("projection.disabled", "Viewer sync is not configured", channel="twin")
                    self._completed(entry, True)
                else:
                    try:
                        success = observer(dict(payload["piece_ids"])) is True
                        self._completed(entry, success, None if success else "Twin busy or unavailable")
                    except Exception as exc:
                        self._completed(entry, False, str(exc))
            finally:
                self.state._transition_lock.release()
        elif entry[2] == "spectator":
            client = self.state.api_client
            if not getattr(client, "token", None):
                # No configured external service. Retire the entry instead of
                # retrying archived terminal states forever; a later startup
                # enqueues the current snapshot if the service is enabled.
                if not self._spectator_disabled_logged:
                    event("projection.disabled", "Spectator token is not configured",
                          channel="spectator")
                    self._spectator_disabled_logged = True
                self._completed(entry, True, None)
                return
            room = self.journal.spectator_room(entry[0])
            if entry[0] != self.journal.session_id and room is None:
                self._completed(entry, False, "Archived room has no recorded route; cannot send to live room")
                return
            match_end = payload.get("match_end")
            if match_end is None and payload.get("game_over"):
                match_end = dict(winner="RED" if payload["winner"] == "r" else "BLACK",
                                 reason=payload.get("game_over_reason") or "CHECKMATE")
            def fen_acknowledged(room_id, fen):
                self.journal.bind_spectator_room(entry[0], client.base_url, room_id, fen)
            def end_acknowledged(room_id, match_end):
                self.journal.acknowledge_spectator_end(entry[0], room_id, match_end)
            accepted = client.submit_board_projection(
                payload["current_fen"], lambda success, error: self._completed(entry, success, error),
                match_end=match_end, session_id=entry[0], room=room,
                fen_acknowledged=fen_acknowledged, end_acknowledged=end_acknowledged,
                room_refresh=lambda: self.journal.spectator_room(entry[0]))
            if not accepted:
                self._completed(entry, False, "Spectator room/queue not ready")

    def _run(self):
        while not self._closed.is_set():
            self._wake.wait(.5)
            self._wake.clear()
            if self._closed.is_set():
                break
            try:
                self._drain_completions()
                pending = self.journal.pending_projections(include_retired=True)
                if not any(entry[0] == self.journal.session_id for entry in pending):
                    self.state.update_projection_status(self.state.board_revision, False, None)
                for entry in pending:
                    try:
                        self._submit(entry)
                    except Exception as exc:
                        key = (entry[0], entry[2])
                        self._inflight.setdefault(key, entry)
                        self._completed(entry, False, str(exc))
            except Exception as exc:
                # Retain every durable row on worker/database failure. No game or
                # physical fault flag is changed by a derived-view failure.
                event("projection.worker_failed", str(exc), level=logging.ERROR,
                      code="PROJECTION_FAILED")
                self._closed.wait(1.0)

    def close(self, timeout=2.0):
        self._closed.set()
        self.wake()
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise RuntimeError("Projection callback still running; keep scene/journal open")
