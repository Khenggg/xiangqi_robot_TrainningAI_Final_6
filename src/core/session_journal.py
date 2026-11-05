"""Durable session truth and command receipts; never replay controller commands."""
from contextlib import contextmanager
from dataclasses import asdict
from enum import Enum
import json
from numbers import Integral, Real
import os
from pathlib import Path
import sqlite3
import threading
import time
from uuid import uuid4

from src.domain.game_move import MoveContext


class JournalError(RuntimeError):
    pass


def encode(value):
    if isinstance(value, MoveContext):
        return {"$kind": "move", "value": encode(asdict(value))}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return {"$kind": "tuple", "value": [encode(item) for item in value]}
    if isinstance(value, list):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        if all(isinstance(key, str) for key in value):
            return {key: encode(item) for key, item in value.items()}
        return {"$kind": "mapping", "value": [[encode(key), encode(item)] for key, item in value.items()]}
    if value is None or type(value) in (str, bool, int, float):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        return float(value)
    raise JournalError(f"Unsupported journal value: {type(value).__name__}")


def decode(value):
    if isinstance(value, list):
        return [decode(item) for item in value]
    if isinstance(value, dict):
        kind = value.get("$kind")
        if kind is None:
            return {key: decode(item) for key, item in value.items()}
        if set(value) != {"$kind", "value"}:
            raise JournalError("Malformed journal value")
        if kind == "tuple":
            return tuple(decode(item) for item in value["value"])
        if kind == "mapping":
            return {decode(key): decode(item) for key, item in value["value"]}
        if kind == "move":
            return MoveContext(**decode(value["value"]))
        raise JournalError("Unknown journal value type")
    return value


def dumps(value):
    return json.dumps(encode(value), ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class SessionJournal:
    def __init__(self, path, environment, game_mode):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.environment, self.game_mode = environment, game_mode
        self._lock = threading.RLock()
        self._lease = open(str(self.path) + ".lock", "a+b")
        self._db = None
        try:
            if self._lease.seek(0, 2) == 0:
                self._lease.write(b"\0")
                self._lease.flush()
            self._lease.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._lease.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._db = sqlite3.connect(self.path, timeout=2.0, check_same_thread=False)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS current_session (
                    id INTEGER PRIMARY KEY CHECK(id=1), session_id TEXT NOT NULL,
                    environment TEXT NOT NULL, game_mode TEXT NOT NULL,
                    revision INTEGER NOT NULL, state TEXT NOT NULL,
                    phase TEXT NOT NULL, clean INTEGER NOT NULL, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS command_receipts (
                    session_id TEXT NOT NULL, move_id TEXT NOT NULL, stage TEXT NOT NULL,
                    created REAL NOT NULL, PRIMARY KEY(session_id,move_id,stage));
                CREATE TABLE IF NOT EXISTS committed_moves (
                    session_id TEXT NOT NULL, move_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    state TEXT NOT NULL, PRIMARY KEY(session_id,move_id),
                    UNIQUE(session_id,revision));
                CREATE TABLE IF NOT EXISTS session_archive (
                    session_id TEXT PRIMARY KEY, environment TEXT NOT NULL,
                    game_mode TEXT NOT NULL, revision INTEGER NOT NULL,
                    state TEXT NOT NULL, phase TEXT NOT NULL, clean INTEGER NOT NULL,
                    updated REAL NOT NULL, archived_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS projection_outbox (
                    session_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    channel TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(session_id,revision,channel));
                CREATE TABLE IF NOT EXISTS spectator_rooms (
                    session_id TEXT PRIMARY KEY, base_url TEXT NOT NULL,
                    room_id TEXT NOT NULL, acknowledged_fen TEXT, updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS spectator_end_receipts (
                    session_id TEXT PRIMARY KEY, room_id TEXT NOT NULL,
                    end_metadata TEXT NOT NULL);
            """)
            row = self._db.execute("SELECT session_id,environment,game_mode,revision,state,phase,clean FROM current_session WHERE id=1").fetchone()
            self.loaded = None
            self.session_id = uuid4().hex if row is None else row[0]
            if row is not None:
                if row[1] != environment:
                    raise JournalError("Journal execution environment mismatch")
                self.loaded = {"state": decode(json.loads(row[4])), "revision": row[3],
                               "phase": row[5], "clean": bool(row[6]), "game_mode": row[2]}
        except Exception as exc:
            self.close()
            raise JournalError(f"Session journal unavailable; no game motion permitted: {exc}") from exc

    @contextmanager
    def transaction(self):
        with self._lock:
            if self._db is None:
                raise JournalError("Session journal is closed")
            database = self._db
            try:
                database.execute("BEGIN IMMEDIATE")
                yield
                database.commit()
            except Exception as exc:
                database.rollback()
                raise JournalError(f"Session write failed: {exc}") from exc

    def _write(self, snapshot, phase, clean=False):
        self._db.execute("INSERT OR REPLACE INTO current_session VALUES(1,?,?,?,?,?,?,?,?)",
                         (self.session_id, self.environment, self.game_mode,
                          snapshot["board_revision"], dumps(snapshot), phase, int(clean), time.time()))

    def _enqueue_projections(self, snapshot, *, match_end=None):
        projection = {name: snapshot.get(name) for name in (
            "piece_ids", "current_fen", "board_revision", "last_committed_move",
            "game_over", "winner", "game_over_reason")}
        match_end = match_end if match_end is not None else snapshot.get("match_end")
        if match_end is not None:
            projection["match_end"] = match_end
        payload = dumps(projection)
        for channel in ("twin", "spectator"):
            self._db.execute("INSERT OR REPLACE INTO projection_outbox VALUES(?,?,?,?)",
                             (self.session_id, snapshot["board_revision"], channel, payload))

    def checkpoint(self, snapshot, phase):
        with self.transaction():
            self._write(snapshot, phase)
            if phase in {"READY", "TERMINAL", "ROLLBACK", "UNDO", "OPERATOR_RECONCILED_BOARD", "OPERATOR_CONFIRMED_TURN"}:
                self._enqueue_projections(snapshot)

    def has_command_stage(self, move_id, stage):
        with self._lock:
            if self._db is None or not move_id:
                return False
            return self._db.execute(
                "SELECT 1 FROM command_receipts WHERE session_id=? AND move_id=? AND stage=?",
                (self.session_id, str(move_id), str(stage))).fetchone() is not None

    def dispatch(self, snapshot, context, stage):
        if context is None or stage not in {"pre_pick", "capture_removed", "manual_test"}:
            raise JournalError("Semantic move/stage required before dispatch")
        with self.transaction():
            if self._db.execute("SELECT 1 FROM committed_moves WHERE session_id=? AND move_id=?",
                                (self.session_id, context.move_id)).fetchone():
                raise JournalError("Move already committed; command replay forbidden")
            self._db.execute("INSERT INTO command_receipts VALUES(?,?,?,?)",
                             (self.session_id, context.move_id, stage, time.time()))
            self._write(snapshot, "TEST_DISPATCHED" if stage == "manual_test" else "DISPATCHED")

    def commit_move(self, snapshot, context):
        if context is None:
            raise JournalError("Semantic move required for durable commit")
        payload = dumps(snapshot)
        with self.transaction():
            row = self._db.execute("SELECT revision FROM current_session WHERE id=1").fetchone()
            if row is None or snapshot["board_revision"] != row[0] + 1:
                raise JournalError("Commit revision mismatch; reconcile session")
            self._db.execute("INSERT INTO committed_moves VALUES(?,?,?,?)",
                             (self.session_id, context.move_id, snapshot["board_revision"], payload))
            self._write(snapshot, "COMMITTED")
            self._enqueue_projections(snapshot)

    def new_session(self, snapshot, *, retiring_snapshot=None, archive_previous=False):
        old_session = self.session_id
        try:
            with self.transaction():
                if archive_previous:
                    # Keep interrupted commands and the exact old board for audit.
                    # Archiving is not evidence of a completed/finished game.
                    self._db.execute("""INSERT INTO session_archive
                        SELECT session_id,environment,game_mode,revision,state,phase,
                               clean,updated,? FROM current_session WHERE id=1""", (time.time(),))
                if retiring_snapshot is not None:
                    # End the old room and create its replacement atomically.
                    # No network callback may observe an end from a failed reset.
                    self._enqueue_projections(retiring_snapshot)
                self.session_id = uuid4().hex
                self._write(snapshot, "READY")
                self._enqueue_projections(snapshot)
        except Exception:
            self.session_id = old_session
            raise

    def request_projection(self, snapshot, *, match_end=None):
        with self.transaction():
            self._enqueue_projections(snapshot, match_end=match_end)

    def bind_spectator_room(self, session_id, base_url, room_id, acknowledged_fen=None):
        if not session_id or not base_url or room_id is None:
            raise JournalError("Spectator binding requires session, server and room")
        with self.transaction():
            previous = self._db.execute("SELECT base_url,room_id FROM spectator_rooms WHERE session_id=?",
                                        (session_id,)).fetchone()
            binding = (str(base_url).rstrip('/'), str(room_id))
            if previous is not None and previous != binding:
                raise JournalError("Session already bound to another spectator room; refusing reassignment")
            self._db.execute("""INSERT INTO spectator_rooms VALUES(?,?,?,?,?)
                ON CONFLICT(session_id) DO UPDATE SET
                acknowledged_fen=COALESCE(excluded.acknowledged_fen,spectator_rooms.acknowledged_fen),
                updated=excluded.updated""",
                (session_id, *binding, acknowledged_fen, time.time()))

    def spectator_room(self, session_id):
        with self._lock:
            if self._db is None:
                raise JournalError("Session journal is closed")
            row = self._db.execute("SELECT base_url,room_id,acknowledged_fen FROM spectator_rooms WHERE session_id=?",
                                   (session_id,)).fetchone()
            if row is None:
                return None
            ended = self._db.execute("SELECT end_metadata FROM spectator_end_receipts WHERE session_id=? AND room_id=?",
                                     (session_id, row[1])).fetchone()
            return dict(base_url=row[0], room_id=row[1], acknowledged_fen=row[2],
                        acknowledged_end=None if ended is None else decode(json.loads(ended[0])))

    def acknowledge_spectator_end(self, session_id, room_id, match_end):
        with self.transaction():
            route = self._db.execute("SELECT room_id FROM spectator_rooms WHERE session_id=?",
                                     (session_id,)).fetchone()
            if route is None or route[0] != str(room_id):
                raise JournalError("End acknowledgement does not match the recorded room")
            previous = self._db.execute("SELECT end_metadata FROM spectator_end_receipts WHERE session_id=?",
                                        (session_id,)).fetchone()
            if previous is not None and decode(json.loads(previous[0])) != match_end:
                raise JournalError("Remote match outcome was already acknowledged; refusing replacement")
            self._db.execute("INSERT OR IGNORE INTO spectator_end_receipts VALUES(?,?,?)",
                             (session_id, str(room_id), dumps(match_end)))

    def pending_projections(self, *, include_retired=False):
        with self._lock:
            if self._db is None:
                raise JournalError("Session journal is closed")
            # Twin coalesces complete snapshots; spectator must preserve move order.
            rows = self._db.execute("""SELECT session_id,revision,channel,payload FROM projection_outbox
                WHERE session_id=? OR (? AND channel='spectator') ORDER BY revision ASC""",
                (self.session_id, int(include_retired))).fetchall()
            selected = {}
            retired_terminal = set()
            for session_id, revision, channel, payload in rows:
                key = (session_id, channel)
                entry = (session_id, revision, channel, payload)
                if channel == "twin":
                    selected[key] = entry
                else:
                    # The spectator endpoint validates successive legal moves.
                    # Keep its oldest unacknowledged state; do not skip captures.
                    selected.setdefault(key, entry)
                    value = decode(json.loads(payload))
                    if value.get("match_end") is not None or value.get("game_over"):
                        retired_terminal.add(session_id)
            return [entry for entry in selected.values() if entry[0] == self.session_id
                    or entry[0] in retired_terminal]

    def acknowledge_projection(self, entry):
        session_id, revision, channel, payload = entry
        with self.transaction():
            # A same-revision terminal update may have replaced an in-flight board
            # payload. An old ACK must never delete the replacement.
            cursor = self._db.execute("""DELETE FROM projection_outbox WHERE session_id=?
                AND revision=? AND channel=? AND payload=?""", entry)
            if cursor.rowcount:
                self._db.execute("DELETE FROM projection_outbox WHERE session_id=? AND channel=? AND revision<?",
                                 (session_id, channel, revision))
            return bool(cursor.rowcount)

    def close(self):
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None
            if self._lease is not None:
                # Closing releases the kernel lease, including startup failure paths.
                self._lease.close()
                self._lease = None
