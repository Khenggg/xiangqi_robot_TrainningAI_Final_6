"""Optional spectator projection must not retry archived entries forever."""

import json
import threading
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock

from src.core.projection_worker import ProjectionWorker


def test_no_token_retires_archived_spectator_entry_once():
    worker = object.__new__(ProjectionWorker)
    worker._closed = threading.Event()
    worker._wake = threading.Event()
    worker._lock = threading.Lock()
    worker._inflight = {}
    worker._completions = deque()
    worker._retry_after = {}
    worker._failures = {}
    worker._last_errors = {}
    worker._spectator_disabled_logged = False
    worker.state = SimpleNamespace(
        api_client=SimpleNamespace(token=None),
        board_revision=1,
        update_projection_status=Mock(),
    )
    worker.journal = SimpleNamespace(session_id="current", acknowledge_projection=Mock())

    entry = ("archived", 1, "spectator", json.dumps({"current_fen": "x"}))
    worker._submit(entry)
    assert len(worker._completions) == 1
    assert worker._spectator_disabled_logged is True
    worker._drain_completions()
    worker.journal.acknowledge_projection.assert_called_once_with(entry)

    second = ("archived", 2, "spectator", json.dumps({"current_fen": "y"}))
    worker._submit(second)
    assert len(worker._completions) == 1
    worker._drain_completions()
    assert worker.journal.acknowledge_projection.call_count == 2
