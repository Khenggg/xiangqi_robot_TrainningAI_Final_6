"""One UI job at a time; shutdown never releases hardware beneath a running job."""
import threading


class MotionWorker:
    def __init__(self):
        self._thread = None
        self._result = None
        self._done = False
        self._closed = False
        self._lock = threading.Lock()

    @property
    def busy(self):
        with self._lock:
            return self._thread is not None

    def start(self, operation, completed):
        with self._lock:
            if self._closed or self._thread is not None:
                return False
            self._done = False
            self._result = None
            self._completed = completed
            def run():
                try:
                    value, error = operation(), None
                except Exception as exc:
                    value, error = None, exc
                with self._lock:
                    self._result = (value, error)
                    self._done = True
            self._thread = threading.Thread(target=run, name="xiangqi-motion", daemon=False)
            self._thread.start()
            return True

    def poll(self):
        with self._lock:
            if not self._done:
                return False
            thread, completed, result = self._thread, self._completed, self._result
            self._thread = None
            self._done = False
        thread.join()
        completed(*result)
        return True

    def close(self, timeout=5.0):
        with self._lock:
            self._closed = True
            thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                raise RuntimeError("Motion still running; camera/controller kept open. Wait or stop using pendant.")
