import json
import logging
from pathlib import Path
import sys
import threading
import warnings
from types import SimpleNamespace
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import Mock
import pytest

from src.core.project_logging import LogSession, event, Redactor
from src.core.launch_options import ViewerServer

pytestmark = pytest.mark.serial


def records(session):
    return [json.loads(line) for line in (session.path / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def test_console_encoding_failure_does_not_recurse(tmp_path, monkeypatch):
    import io
    class LegacyConsole(io.StringIO):
        def write(self, text):
            text.encode('cp1252')
            return super().write(text)
    fallback = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', LegacyConsole())
    monkeypatch.setattr(sys, 'stderr', fallback)
    session = LogSession(tmp_path)
    try:
        event('test.unicode', 'Lỗi tọa độ bàn cờ')
        event('test.after_console_failure', 'File vẫn ghi bình thường')
    finally:
        session.close()
    assert fallback.getvalue().count('LOG_CONSOLE_FAILED') == 1
    assert any(r['event'] == 'test.after_console_failure' for r in records(session))


def test_transport_packet_debug_is_filtered_but_warnings_remain(tmp_path):
    session = LogSession(tmp_path, capture=False)
    logger = logging.getLogger('websockets.protocol')
    try:
        logger.debug('OUTGOING_TELEMETRY_PACKET')
        logger.warning('Transport connection interrupted')
        event('camera.sample', 'Chi tiết ứng dụng', level=logging.DEBUG)
    finally:
        session.close()
    rows = records(session)
    assert not any('OUTGOING_TELEMETRY_PACKET' in r['message'] for r in rows)
    assert any('Transport connection interrupted' in r['message'] for r in rows)
    assert any(r['event'] == 'camera.sample' for r in rows)


def test_human_error_json_and_traceback_are_correlated(tmp_path):
    session = LogSession(tmp_path, capture=False)
    try:
        try:
            raise ValueError("Camera returned a different board")
        except ValueError:
            event("board.sync_failed", "Bàn cờ chưa khớp", level=logging.ERROR,
                  code="BOARD_SYNC_FAILED", exc_info=True, move_id="move-42", fen="example")
    finally:
        session.close()
    item = next(r for r in records(session) if r["event"] == "board.sync_failed")
    assert item["session_id"] == session.id
    assert item["data"]["move_id"] == "move-42"
    assert "test_project_logging.py:" in item["source"]
    assert "ValueError" in item["traceback"] and item["next_step"]
    assert "Ảnh hưởng" in (session.path / "errors.log").read_text(encoding="utf-8")
    assert "session.ended" == records(session)[-1]["event"]


def test_redaction_covers_messages_data_and_legacy_prints(tmp_path, capsys):
    assert "abc" not in Redactor().text('{"token": "abc"}')
    session = LogSession(tmp_path, secrets=["private-value"])
    try:
        print("secret: private-value")
        event("test", "Authorization=BearerSomething token=abc", api_key="key123",
              nested={"password": "pass123", "detail": "private-value"})
    finally:
        session.close()
    output = capsys.readouterr().out
    files = "".join(p.read_text(encoding="utf-8") for p in session.path.glob("*.log"))
    files += (session.path / "events.jsonl").read_text(encoding="utf-8")
    for secret in ("private-value", "key123", "pass123", "BearerSomething", "token=abc"):
        assert secret not in files
    assert "private-value" not in output
    assert any(r["event"] == "console.stdout" for r in records(session))


def test_stream_threads_flush_and_hooks_restore(tmp_path):
    stdout, stderr, hook, thread_hook = sys.stdout, sys.stderr, sys.excepthook, threading.excepthook
    session = LogSession(tmp_path)
    try:
        threads = [threading.Thread(target=lambda: (sys.stdout.write("hello"), sys.stdout.write(" world\n"))) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        sys.stderr.write("partial error")
        sys.excepthook(ValueError, ValueError("unhandled test"), None)
        warnings.warn("warning test", UserWarning)
    finally:
        session.close()
        session.close()
    assert (sys.stdout, sys.stderr, sys.excepthook, threading.excepthook) == (stdout, stderr, hook, thread_hook)
    rows = records(session)
    assert len([r for r in rows if r["message"] == "hello world"]) == 3
    assert any(r["message"] == "partial error" for r in rows)
    assert any(r["error_code"] == "APP_UNHANDLED" for r in rows)
    assert any(r["event"] == "python.warning" and r["level"] == "WARNING" for r in rows)


def test_rotation_limits_backups_and_files_remain_json(tmp_path):
    session = LogSession(tmp_path, capture=False, max_bytes=800)
    try:
        for i in range(30):
            event("rotation.test", "x" * 80, index=i)
    finally:
        session.close()
    files = list(session.path.glob("events.jsonl*"))
    assert len(files) == 4
    for file in files:
        for line in file.read_text(encoding="utf-8").splitlines():
            assert json.loads(line)["session_id"] == session.id


def test_file_failure_does_not_recurse_into_captured_stderr(tmp_path, capsys):
    session = LogSession(tmp_path)
    try:
        handler = session.handlers[0]
        handler.handleError(logging.makeLogRecord({"msg": "failure"}))
        assert handler.failed
        event("still.alive", "Console continues")
    finally:
        session.close()
    assert "LOG_WRITE_FAILED" in capsys.readouterr().err
    assert any(r["event"] == "still.alive" for r in records(session))


def test_browser_diagnostics_validate_origin_payload_and_rate(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.launch_options.webbrowser.open", Mock())
    session = LogSession(tmp_path / "logs", capture=False)
    server = ViewerServer(tmp_path, 0)
    server.start(8765)
    url = server.url + "diagnostics"
    try:
        req = Request(url, json.dumps({"message": "Model failed", "source": "viewer.init"}).encode(),
                      headers={"Content-Type": "application/json"})
        assert urlopen(req).status == 204
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url, b"{}", headers={"Origin": "http://outside.example"}))
        assert error.value.code == 403
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url, b"[]"))
        assert error.value.code == 400
        server.server.diagnostic_count = 30
        with pytest.raises(HTTPError) as error:
            urlopen(req)
        assert error.value.code == 429
    finally:
        server.close()
        session.close()
    assert len([r for r in records(session) if r["event"] == "viewer.browser_error"]) == 1
