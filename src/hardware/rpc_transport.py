"""Bounded, single-attempt RPC transport. Never replay actuation on lost replies."""
import socket
import threading
import time
import xmlrpc.client


class RpcOutcomeUnknown(RuntimeError):
    pass


class SingleAttemptTransport(xmlrpc.client.Transport):
    def __init__(self, timeout_s=10.0):
        super().__init__()
        self.timeout_s = timeout_s

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = self.timeout_s
        return connection

    def request(self, host, handler, request_body, verbose=False):
        # Transport.request normally retries a disconnected response once.
        # Closing the connection after each request guarantees that subsequent calls
        # (even after a long player pause) always use a clean, fresh connection
        # rather than failing on an idle socket closed by the robot controller.
        try:
            return self.single_request(host, handler, request_body, verbose)
        finally:
            self.close()


class BoundedRPCProxy:
    def __init__(self, url, timeout_s=10.0, proxy=None):
        self._proxy = proxy or xmlrpc.client.ServerProxy(
            url, transport=SingleAttemptTransport(timeout_s), allow_none=True)
        self._lock = threading.RLock()
        self.timeout_s = timeout_s

    def __getattr__(self, name):
        method = getattr(self._proxy, name)
        def call(*args, **kwargs):
            if not self._lock.acquire(timeout=self.timeout_s):
                raise RpcOutcomeUnknown(f"{name}: RPC busy; no command dispatched")
            try:
                return method(*args, **kwargs)
            except (OSError, xmlrpc.client.ProtocolError) as exc:
                raise RpcOutcomeUnknown(
                    f"{name}: controller reply unavailable; outcome unknown, do not resend") from exc
            finally:
                self._lock.release()
        return call


def wait_for_reconnect(rpc, timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while rpc.reconnect_flag:
        stop = getattr(rpc, 'stop_event', None)
        if time.monotonic() >= deadline or (stop is not None and stop.is_set()):
            raise RpcOutcomeUnknown("Controller reconnect timed out; no new command dispatched")
        time.sleep(.05)
