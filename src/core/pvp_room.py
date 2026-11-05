"""Local room transport selectively ported from nguoivsnguoifinal@73af0f1.

Preserves six-character rooms/host Red/client Black. Only queues requests and
read-only snapshots; no game authority, hardware imports or actuator calls.
"""
import json
from pathlib import Path
import queue
import secrets
import socket
import tempfile
import threading
import time
from uuid import uuid4

ROOM_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
ROOM_REGISTRY = Path(tempfile.gettempdir()) / 'xiangqi_robot_rooms_v2'
MAX_FRAME = 16384


def _encode(packet):
    raw = (json.dumps(packet, ensure_ascii=True, allow_nan=False)+'\n').encode()
    if len(raw) > MAX_FRAME:
        raise ValueError('Room packet too large')
    return raw


def _messages(sock, closed):
    buf = b''
    while not closed.is_set():
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            yield None
            continue
        if not chunk:
            return
        buf += chunk
        while b'\n' in buf:
            line, buf = buf.split(b'\n', 1)
            if len(line) > MAX_FRAME:
                raise ValueError('Room frame too large')
            packet = json.loads(line.decode('utf-8'))
            if not isinstance(packet, dict):
                raise ValueError('Room packet must be an object')
            yield packet
        if len(buf) > MAX_FRAME:
            raise ValueError('Room frame too large')


def _shutdown(sock):
    if sock is None:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()


class LocalRoomHost:
    def __init__(self, registry=None):
        self.registry = Path(registry) if registry is not None else ROOM_REGISTRY
        self.registry.mkdir(parents=True, exist_ok=True)
        self.session = uuid4().hex
        self.events = queue.Queue(maxsize=128)
        self._closed = threading.Event()
        self._lock = threading.RLock()
        self._peer = None
        self._generation = None
        self._latest = None
        self._out = queue.Queue(maxsize=32)
        self._threads = []
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(2)
        self.listener.settimeout(.1)
        self.port = self.listener.getsockname()[1]
        for _ in range(100):
            self.code = ''.join(secrets.choice(ROOM_ALPHABET) for _ in range(6))
            self.path = self.registry / f'{self.code}.json'
            try:
                with self.path.open('x', encoding='utf-8') as f:
                    json.dump(dict(version=2, port=self.port, session=self.session), f)
                break
            except FileExistsError:
                continue
        else:
            self.listener.close()
            raise RuntimeError('Could not allocate room code')
        self._acceptor = threading.Thread(target=self._accept, name='pvp-room-host', daemon=True)
        self._acceptor.start()

    @property
    def generation(self):
        with self._lock:
            return self._generation

    @property
    def connected(self):
        return self.generation is not None

    def _event(self, packet):
        self.events.put_nowait(packet)

    def _accept(self):
        while not self._closed.is_set():
            try:
                sock, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            thread = threading.Thread(target=self._serve, args=(sock,), name='pvp-room-peer', daemon=True)
            self._threads.append(thread)
            thread.start()

    def _serve(self, sock):
        generation = None
        try:
            sock.settimeout(.05)
            packets = _messages(sock, self._closed)
            deadline = time.monotonic()+2
            auth = None
            while auth is None and time.monotonic() < deadline:
                auth = next(packets)
            if (not auth or auth.get('type') != 'join' or auth.get('code') != self.code
                    or auth.get('session') != self.session):
                return
            with self._lock:
                if self._peer is not None or self._closed.is_set():
                    sock.sendall(_encode(dict(type='rejected', reason='ROOM_OCCUPIED')))
                    return
                generation = uuid4().hex
                self._peer, self._generation = sock, generation
                while not self._out.empty():
                    try: self._out.get_nowait()
                    except queue.Empty: break
                welcome = dict(type='welcome', side='b', session=self.session, generation=generation)
                sock.sendall(_encode(welcome))
                if self._latest is not None:
                    sock.sendall(_encode(self._latest))
            self._event(dict(type='joined', generation=generation))
            for packet in packets:
                if packet is not None:
                    self._event(dict(type='request', generation=generation, packet=packet))
                while True:
                    try:
                        outgoing_generation, outgoing = self._out.get_nowait()
                    except queue.Empty:
                        break
                    if outgoing_generation == generation:
                        sock.sendall(_encode(outgoing))
        except (OSError, ValueError, StopIteration, queue.Full, UnicodeError):
            pass
        finally:
            _shutdown(sock)
            with self._lock:
                if generation is not None and self._generation == generation:
                    self._peer = self._generation = None
                    try: self._event(dict(type='disconnected', generation=generation))
                    except queue.Full: pass

    def send(self, packet):
        generation = self.generation
        if generation is None:
            return False
        try:
            self._out.put_nowait((generation, packet))
            return True
        except queue.Full:
            with self._lock:
                _shutdown(self._peer)
            return False

    def publish(self, snapshot):
        packet = dict(snapshot, type='state', session=self.session)
        with self._lock:
            self._latest = packet
        return self.send(packet)

    def close(self):
        if self._closed.is_set():
            return
        self._closed.set()
        self.listener.close()
        with self._lock:
            _shutdown(self._peer)
            self._peer = self._generation = None
        self._acceptor.join(1)
        for thread in self._threads:
            thread.join(1)
        try:
            if json.loads(self.path.read_text())['session'] == self.session:
                self.path.unlink()
        except (FileNotFoundError, ValueError, KeyError):
            pass


class LocalRoomClient:
    def __init__(self, code, registry=None):
        if len(code) != 6 or any(c not in ROOM_ALPHABET for c in code):
            raise ValueError('Mã phòng phải có 6 ký tự')
        self.code = code
        self.events = queue.Queue(maxsize=128)
        self.connected = False
        self.session = self.generation = None
        self._closed = threading.Event()
        self._out = queue.Queue(maxsize=16)
        self._socket = None
        self._registry = Path(registry) if registry is not None else ROOM_REGISTRY
        self._thread = threading.Thread(target=self._run, name='pvp-room-client', daemon=True)
        self._thread.start()

    def _run(self):
        try:
            info = json.loads((self._registry/f'{self.code}.json').read_text())
            if info.get('version') != 2 or type(info.get('port')) is not int or not 1 <= info['port'] <= 65535:
                raise ValueError('Phòng không hợp lệ')
            sock = self._socket = socket.create_connection(('127.0.0.1',info['port']),timeout=2)
            sock.settimeout(.05)
            sock.sendall(_encode(dict(type='join', code=self.code, session=info['session'])))
            for packet in _messages(sock,self._closed):
                if packet is not None:
                    if packet.get('type') == 'welcome':
                        if packet.get('session') != info['session'] or packet.get('side') != 'b':
                            raise ValueError('Sai phiên/phía người chơi')
                        self.session, self.generation = packet['session'],packet['generation']
                        self.connected = True
                    self.events.put_nowait(packet)
                try: outgoing = self._out.get_nowait()
                except queue.Empty: continue
                sock.sendall(_encode(outgoing))
        except (OSError, ValueError, KeyError, queue.Full, UnicodeError) as exc:
            try: self.events.put_nowait(dict(type='error', reason=str(exc)))
            except queue.Full: pass
        finally:
            self.connected = False
            _shutdown(self._socket)
            try: self.events.put_nowait(dict(type='disconnected'))
            except queue.Full: pass

    def send_move(self, src, dst, revision):
        if not self.connected or self._closed.is_set():
            return None
        request_id = uuid4().hex
        packet = dict(type='move', session=self.session, generation=self.generation,
                      request_id=request_id, revision=revision, src=list(src),dst=list(dst))
        try: self._out.put_nowait(packet)
        except queue.Full: return None
        return request_id

    def close(self):
        self._closed.set()
        _shutdown(self._socket)
        self._thread.join(3)
