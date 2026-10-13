"""Per-session human and JSON logs. No device access and no motion authority."""
import atexit
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import platform
import re
import sys
import threading
import time
import subprocess
import warnings
from uuid import uuid4


ERRORS = {
    "APP_UNHANDLED": ("Chương trình gặp lỗi chưa được xử lý", "Phiên chạy có thể đã dừng", "Mở errors.log, tìm traceback cùng mã phiên; không chạy lại lệnh robot khi chưa xác định trạng thái"),
    "PORT_BUSY": ("Không mở được cổng dịch vụ", "Viewer hoặc backend chưa sẵn sàng", "Kiểm tra chương trình đang dùng cổng; chọn --viewer-port và --telemetry-port khác"),
    "CAMERA_VERIFY_FAILED": ("Camera chưa xác nhận được toàn bộ bàn cờ", "Nước robot chưa được phép thực hiện hoặc chưa được xác nhận", "Kiểm tra ảnh, ánh sáng, vật che camera, calibration và bố trí quân; quét lại bàn"),
    "BOARD_SYNC_FAILED": ("Bàn game và mô phỏng chưa đồng bộ", "Đã chặn lượt AI tiếp theo", "Giữ nguyên trạng thái robot, quét/xác nhận bàn rồi kiểm tra lại viewer"),
    "ROBOT_NOT_READY": ("Robot chưa sẵn sàng nhận nước đi", "Nước đi chưa được thực hiện", "Kiểm tra kết nối, chế độ backend và quyền chuyển động; với FR3 thật dùng F9 rồi F10 sau khi kiểm tra setup"),
    "MOVE_REJECTED": ("Nước đi hoặc chuyển động bị từ chối", "Không thể xác nhận hoàn tất nước đi", "Đọc chi tiết nguyên nhân và bước dừng; kiểm tra bàn thật trước khi tiếp tục, không tắt chống va chạm"),
    "TWIN_UNAVAILABLE": ("Mô phỏng không nhận được trạng thái hợp lệ", "Viewer có thể đang hiển thị trạng thái cũ", "Kiểm tra kết nối, độ mới telemetry, trạng thái idle và phiên calibration"),
    "PHYSICAL_ENABLE_FAILED": ("Không bật được quyền điều khiển FR3", "Robot chưa được phép chạy qua game", "Kiểm tra camera, telemetry idle, calibration và lỗi đồng bộ; xử lý nguyên nhân rồi xác nhận lại"),
    "ENGINE_ILLEGAL_MOVE": ("AI trả về nước đi không hợp lệ", "Bàn cờ chưa thay đổi", "Đối chiếu FEN, lượt chơi và log engine cùng move_id"),
    "STARTUP_FAILED": ("Không khởi tạo được một thành phần", "Phiên game chưa sẵn sàng", "Đọc component và traceback; kiểm tra dependency, thiết bị hoặc cổng tương ứng"),
    "VIEWER_FAILED": ("Viewer 3D gặp lỗi", "Hình ảnh mô phỏng có thể không tải hoặc không cập nhật", "Kiểm tra mạng tải thư viện/model và WebSocket; đối chiếu lỗi browser trong run.log"),
}
_session = None


def event(name, message, *, level=logging.INFO, code=None, exc_info=None, **data):
    """Log an observation; never let diagnostics change control flow."""
    try:
        logging.getLogger("xiangqi").log(level, message, extra={
            "event": name, "error_code": code, "event_data": data,
        }, exc_info=exc_info, stacklevel=2)
    except Exception:
        pass


class Redactor:
    def __init__(self, secrets=()):
        self.secrets = tuple(sorted((str(s) for s in secrets if s), key=len, reverse=True))

    def text(self, value):
        value = str(value)
        for secret in self.secrets:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)(bearer\s+)\S+", r"\1[REDACTED]", value)
        return re.sub(r"(?i)((?:password|token|api[_-]?key|authorization)[\"']?\s*[=:]\s*[\"']?)[^\s,;\"']+", r"\1[REDACTED]", value)

    def data(self, value):
        if isinstance(value, dict):
            return {str(k): "[REDACTED]" if re.search(r"(?i)password|token|secret|api.?key|authorization", str(k))
                    else self.data(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.data(v) for v in value]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        return self.text(value)[:12000]


class SessionFormatter(logging.Formatter):
    def __init__(self, session_id, redactor, *, json_mode=False, detailed=False):
        super().__init__()
        self.session_id, self.redactor = session_id, redactor
        self.json_mode, self.detailed = json_mode, detailed

    def format(self, record):
        code = getattr(record, "error_code", None)
        guidance = ERRORS.get(code)
        data = self.redactor.data(getattr(record, "event_data", {}))
        payload = {"timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                   "session_id": self.session_id, "level": record.levelname,
                   "component": record.name, "event": getattr(record, "event", "legacy.message"),
                   "error_code": code, "message": self.redactor.text(record.getMessage()),
                   "thread": record.threadName, "source": f"{record.pathname}:{record.lineno}",
                   "data": data}
        if guidance:
            payload.update(problem=guidance[0], impact=guidance[1], next_step=guidance[2])
        if record.exc_info:
            payload["traceback"] = self.redactor.text(self.formatException(record.exc_info))
        if self.json_mode:
            return json.dumps(payload, ensure_ascii=False, default=str)
        clock = datetime.fromtimestamp(record.created).astimezone().strftime("%H:%M:%S")
        line = f"{clock} {record.levelname:7} [{code or payload['event']}] {payload['message']}"
        if guidance:
            line += f"\n  Vấn đề: {guidance[0]}\n  Ảnh hưởng: {guidance[1]}\n  Cần làm: {guidance[2]}"
        if self.detailed:
            if data:
                line += "\n  Dữ liệu: " + json.dumps(data, ensure_ascii=False, default=str)
            if "traceback" in payload:
                line += "\n" + payload["traceback"]
        return line


class CapturedStream:
    def __init__(self, original, level):
        self.original, self.level = original, level
        self.buffers = {}
        self.lock = threading.RLock()

    def write(self, text):
        if not text:
            return 0
        ident = threading.get_ident()
        with self.lock:
            chunks = (self.buffers.get(ident, "") + text).split("\n")
            self.buffers[ident] = chunks.pop()
            if len(self.buffers[ident]) > 12000:
                chunks.append(self.buffers.pop(ident))
        for line in chunks:
            if line.strip():
                event("console.stderr" if self.level == logging.ERROR else "console.stdout",
                      line.rstrip("\r"), level=self.level, component="legacy_console")
        return len(text)

    def flush(self):
        with self.lock:
            lines = list(self.buffers.values())
            self.buffers.clear()
        for line in lines:
            if line.strip():
                event("console.partial", line, level=self.level)
        self.original.flush()

    def isatty(self):
        return self.original.isatty()

    def fileno(self):
        return self.original.fileno()

    @property
    def encoding(self):
        return getattr(self.original, "encoding", "utf-8")


class SafeFileHandler(RotatingFileHandler):
    def __init__(self, *args, fallback, **kwargs):
        self.fallback, self.failed = fallback, False
        super().__init__(*args, **kwargs)

    def emit(self, record):
        if not self.failed:
            super().emit(record)

    def handleError(self, record):
        # Writing logging's own traceback to captured stderr would recurse.
        self.failed = True
        try:
            self.fallback.write("[LOG_WRITE_FAILED] Không ghi được file log; kiểm tra dung lượng và quyền thư mục. Console vẫn hoạt động.\n")
            self.fallback.flush()
        except Exception:
            pass


class SafeConsoleHandler(logging.StreamHandler):
    """Console encoding/pipe failures must not recurse through captured stderr."""
    def __init__(self, stream, fallback):
        super().__init__(stream)
        self.fallback, self.failed = fallback, False

    def emit(self, record):
        if not self.failed:
            super().emit(record)

    def handleError(self, record):
        self.failed = True
        try:
            self.fallback.write("[LOG_CONSOLE_FAILED] Console unavailable; read the session log files.\n")
            self.fallback.flush()
        except Exception:
            pass


class TransportNoiseFilter(logging.Filter):
    def filter(self, record):
        return record.levelno >= logging.INFO or not (
            record.name == "websockets" or record.name.startswith("websockets."))


class LogSession:
    def __init__(self, directory, level="INFO", secrets=(), *, capture=True, max_bytes=5_000_000):
        self.id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
        self.path = Path(directory).resolve() / self.id
        self.path.mkdir(parents=True, exist_ok=False)
        self.redactor = Redactor(secrets)
        self.stdout, self.stderr = sys.stdout, sys.stderr
        self.handlers = []
        self.started = time.monotonic()
        self.closed = False
        root = logging.getLogger()
        self.old_level = root.level
        root.setLevel(logging.DEBUG)
        for name, json_mode, minimum in (("run.log", False, logging.DEBUG),
                                         ("events.jsonl", True, logging.DEBUG),
                                         ("errors.log", False, logging.WARNING)):
            handler = SafeFileHandler(self.path / name, maxBytes=max_bytes, backupCount=3,
                                      encoding="utf-8", fallback=self.stderr)
            handler.setLevel(minimum)
            handler.setFormatter(SessionFormatter(self.id, self.redactor, json_mode=json_mode, detailed=True))
            self.handlers.append(handler)
        console = SafeConsoleHandler(self.stdout, self.stderr)
        console.setLevel(level)
        console.setFormatter(SessionFormatter(self.id, self.redactor))
        self.handlers.append(console)
        for handler in self.handlers:
            handler.addFilter(TransportNoiseFilter())
            root.addHandler(handler)
        if capture:
            sys.stdout, sys.stderr = CapturedStream(self.stdout, logging.INFO), CapturedStream(self.stderr, logging.ERROR)
        self.sys_hook, self.thread_hook = sys.excepthook, threading.excepthook
        self.warning_hook = warnings.showwarning
        warnings.showwarning = lambda message, category, filename, lineno, file=None, line=None: event(
            "python.warning", str(message), level=logging.WARNING,
            warning_category=category.__name__, warning_source=f"{filename}:{lineno}")
        sys.excepthook = lambda kind, value, tb: event("app.unhandled", str(value), code="APP_UNHANDLED",
                                                    level=logging.CRITICAL, exc_info=(kind, value, tb))
        threading.excepthook = lambda args: event("thread.unhandled", str(args.exc_value), code="APP_UNHANDLED",
                                                level=logging.ERROR, failed_thread=args.thread.name,
                                                exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        metadata = {"session_id": self.id, "started_at": datetime.now(timezone.utc).isoformat(),
                    "python": platform.python_version(), "platform": platform.platform()}
        (self.path / "session.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        event("session.started", f"Nhật ký phiên: {self.path}", session_id=self.id)

    def close(self):
        global _session
        if self.closed:
            return
        if isinstance(sys.stdout, CapturedStream):
            sys.stdout.flush()
        if isinstance(sys.stderr, CapturedStream):
            sys.stderr.flush()
        event("session.ended", "Kết thúc ghi log phiên", duration_s=round(time.monotonic() - self.started, 3))
        sys.stdout, sys.stderr = self.stdout, self.stderr
        sys.excepthook, threading.excepthook = self.sys_hook, self.thread_hook
        warnings.showwarning = self.warning_hook
        root = logging.getLogger()
        for handler in self.handlers:
            root.removeHandler(handler)
            handler.close()
        root.setLevel(self.old_level)
        self.closed = True
        if _session is self:
            _session = None


def start_logging(directory, level="INFO", secrets=()):
    global _session
    if _session is not None and not _session.closed:
        return _session
    _session = LogSession(directory, level, secrets)
    atexit.register(_session.close)
    return _session


def record_code_version(repo):
    """Best-effort local provenance; no network and no Git mutation."""
    try:
        command = ["git", "-c", f"safe.directory={Path(repo).as_posix()}"]
        head = subprocess.run(command + ["rev-parse", "HEAD"], cwd=repo, capture_output=True,
                              text=True, timeout=2, check=True).stdout.strip()
        dirty = subprocess.run(command + ["status", "--porcelain", "-uno"], cwd=repo,
                               capture_output=True, text=True, timeout=2, check=True).stdout.strip()
        event("app.code_version", "Phiên bản mã đang chạy", git_head=head, tracked_changes=bool(dirty))
    except (OSError, subprocess.SubprocessError):
        event("app.code_version_unavailable", "Không đọc được phiên bản Git", level=logging.DEBUG)
