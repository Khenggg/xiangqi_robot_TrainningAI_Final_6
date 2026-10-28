"""VS Human screens embedded in the main Pygame window."""
import os
import json
import queue
import random
import socket
import tempfile
import threading

import pygame

from src.core import xiangqi


ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PIECE_GLYPHS = {
    "r_K": "帥", "r_A": "仕", "r_E": "相", "r_R": "俥", "r_N": "傌", "r_C": "炮", "r_P": "兵",
    "b_K": "將", "b_A": "士", "b_E": "象", "b_R": "車", "b_N": "馬", "b_C": "砲", "b_P": "卒",
}
INK = (33, 48, 43)
MUTED = (94, 101, 77)
JADE = (25, 111, 91)
JADE_DARK = (18, 75, 63)
GOLD = (177, 142, 82)
RED = (177, 59, 47)
PAPER = (249, 245, 232)
BOARD_WOOD = (232, 199, 142)
ROOM_REGISTRY = os.path.join(tempfile.gettempdir(), "xiangqi_robot_local_rooms")


def _send_json(sock, message, lock=None):
    payload = (json.dumps(message, ensure_ascii=True) + "\n").encode("utf-8")
    if lock is None:
        sock.sendall(payload)
    else:
        with lock:
            sock.sendall(payload)


class LocalRoomHost:
    """Loopback-only room endpoint so a second local app process can join by code."""

    def __init__(self, code, mode):
        os.makedirs(ROOM_REGISTRY, exist_ok=True)
        self.code = code
        self.mode = mode
        self.events = queue.Queue()
        self.closed = threading.Event()
        self.send_lock = threading.Lock()
        self.connection_lock = threading.Lock()
        self.connection = None
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(2)
        self.listener.settimeout(0.5)
        self.port = self.listener.getsockname()[1]
        self.registry_path = os.path.join(ROOM_REGISTRY, f"{code}.json")
        with open(self.registry_path, "w", encoding="utf-8") as registry:
            json.dump({"port": self.port}, registry)
        self.thread = threading.Thread(target=self._serve, name="xiangqi-local-room", daemon=True)
        self.thread.start()

    def _serve(self):
        while not self.closed.is_set():
            try:
                conn, _address = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                conn.settimeout(15)
                stream = conn.makefile("rb")
                auth = json.loads(stream.readline().decode("utf-8"))
                if auth.get("type") != "join" or auth.get("code") != self.code:
                    _send_json(conn, {"ok": False, "error": "Mã phòng không đúng."})
                    conn.close()
                    continue
                with self.connection_lock:
                    old_conn = self.connection
                    self.connection = conn
                if old_conn is not None:
                    try:
                        old_conn.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    try:
                        old_conn.close()
                    except OSError:
                        pass
                _send_json(conn, {"ok": True, "mode": self.mode})
                conn.settimeout(None)
                self.events.put({"type": "joined"})
                while not self.closed.is_set():
                    line = stream.readline()
                    if not line:
                        break
                    try:
                        self.events.put(json.loads(line.decode("utf-8")))
                    except (ValueError, UnicodeDecodeError):
                        continue
            except (OSError, ValueError, UnicodeDecodeError):
                pass
            finally:
                with self.connection_lock:
                    if self.connection is conn:
                        self.connection = None
                        self.events.put({"type": "disconnected"})
                try:
                    conn.close()
                except OSError:
                    pass

    def send(self, message):
        with self.connection_lock:
            conn = self.connection
        if conn is None:
            return False
        try:
            _send_json(conn, message, self.send_lock)
            return True
        except OSError:
            return False

    def close(self):
        self.closed.set()
        try:
            self.listener.close()
        except OSError:
            pass
        with self.connection_lock:
            conn = self.connection
            self.connection = None
        if conn is not None:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()
        try:
            os.remove(self.registry_path)
        except OSError:
            pass


class LocalRoomClient:
    def __init__(self, code, port):
        self.socket = socket.create_connection(("127.0.0.1", int(port)), timeout=3)
        self.socket.settimeout(3)
        _send_json(self.socket, {"type": "join", "code": code})
        stream = self.socket.makefile("rb")
        response = json.loads(stream.readline().decode("utf-8"))
        if not response.get("ok"):
            self.socket.close()
            raise RuntimeError(response.get("error", "Không thể vào phòng."))
        self.mode = response.get("mode", "local")
        self.socket.settimeout(None)
        self.send_lock = threading.Lock()
        self.events = queue.Queue()
        self.closed = threading.Event()
        self.reader = stream
        self.thread = threading.Thread(target=self._receive, name="xiangqi-local-client", daemon=True)
        self.thread.start()

    def _receive(self):
        try:
            while not self.closed.is_set():
                line = self.reader.readline()
                if not line:
                    break
                try:
                    self.events.put(json.loads(line.decode("utf-8")))
                except (ValueError, UnicodeDecodeError):
                    continue
        except OSError:
            pass
        self.events.put({"type": "disconnected"})

    def send(self, message):
        try:
            _send_json(self.socket, message, self.send_lock)
            return True
        except OSError:
            return False

    def close(self):
        self.closed.set()
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.socket.close()


class LocalRoom:
    def __init__(self, mode):
        self.code = "".join(random.SystemRandom().choice(ROOM_ALPHABET) for _ in range(6))
        self.mode = mode
        self.board = xiangqi.get_board()
        self.turn = "r"
        self.last_move = None
        self.selected = None
        self.joined_black = False
        self.over = False
        self.winner = None
        self.physical_sync = True
        self.camera_status = "Không robot." if mode == "local" else "Robot và camera đang khởi tạo."


class PlayerVsPlayerMode:
    """A small mode controller rendered inside the existing Pygame surface."""

    def __init__(self, renderer):
        self.renderer = renderer
        self.screen = renderer.screen
        self.page = "menu"
        self.room = None
        self.hardware = None
        self.room_host = None
        self.room_client = None
        self.remote_move_pending = False
        self.code_input = ""
        self.active_tab = "r"
        self.player_side = None
        self.status = "Tạo phòng trên máy này, sau đó nhập mã để người chơi thứ hai vào."
        self.camera_status = ""
        self.cell = 65
        self.board_left = 88
        self.board_top = 240
        self.menu_buttons = {
            "robot": pygame.Rect(460, 490, 520, 76),
            "local": pygame.Rect(460, 590, 520, 76),
            "join": pygame.Rect(460, 820, 520, 72),
            "back": pygame.Rect(28, 30, 170, 58),
        }

    def close(self):
        self._close_room_resources()

    def _close_room_resources(self):
        if self.room_client is not None:
            self.room_client.close()
            self.room_client = None
        if self.room_host is not None:
            self.room_host.close()
            self.room_host = None
        if self.hardware is not None:
            try:
                self.hardware.cleanup()
            except Exception as exc:
                print(f"[PVP] Cleanup hardware error: {exc}")
            self.hardware = None

    def poll_remote(self):
        """Apply socket events on the UI thread; robot operations stay on the host thread."""
        if self.room_host is not None:
            while True:
                try:
                    event = self.room_host.events.get_nowait()
                except queue.Empty:
                    break
                if event.get("type") == "joined":
                    self.room.joined_black = True
                    self.player_side = "r"
                    self.active_tab = "r"
                    self.page = "game"
                    self.status = "Người chơi thứ hai đã vào phòng. Bạn chơi quân ĐỎ."
                    self._publish_state()
                elif event.get("type") == "move":
                    try:
                        src = tuple(map(int, event["src"]))
                        dst = tuple(map(int, event["dst"]))
                        if not self.room.joined_black:
                            self.status = "Tab ĐEN chưa kết nối với phòng."
                            self._publish_state()
                        elif self.room.turn != "b":
                            # A delayed duplicate can arrive while FR3/camera is handling
                            # the previous move. Resync silently instead of blaming Black.
                            self._publish_state()
                        elif xiangqi.is_valid_move(src, dst, self.room.board, "b"):
                            self._perform_move("b", src, dst)
                        else:
                            self.status = "Nước đi của Đen không hợp lệ theo luật cờ."
                            self._publish_state()
                    except (KeyError, TypeError, ValueError, IndexError):
                        self.status = "Nhận được yêu cầu nước đi không hợp lệ từ máy kia."
                elif event.get("type") == "disconnected":
                    if self.room is not None:
                        self.room.joined_black = False
                        self.page = "host"
                        self.player_side = "r"
                        self.active_tab = "r"
                        self.status = "Người chơi ĐEN đã ngắt kết nối; đang chờ người tham gia lại bằng mã phòng."
                        self._publish_state()

        if self.room_client is not None:
            while True:
                try:
                    event = self.room_client.events.get_nowait()
                except queue.Empty:
                    break
                if event.get("type") == "state" and self.room is not None:
                    self.remote_move_pending = False
                    self.room.board = event.get("board", self.room.board)
                    self.room.turn = event.get("turn", self.room.turn)
                    self.room.last_move = event.get("last_move")
                    self.room.over = bool(event.get("over", False))
                    self.room.winner = event.get("winner")
                    self.room.joined_black = bool(event.get("joined", True))
                    self.room.physical_sync = bool(event.get("physical_sync", True))
                    self.room.camera_status = event.get("camera_status", self.room.camera_status)
                    self.status = event.get("status", self.status)
                elif event.get("type") == "disconnected":
                    self.status = "Mất kết nối với phòng chủ. Người chơi chủ có thể đã đóng phòng."
                    self.room_client.close()
                    self.room_client = None
                    break

    def _publish_state(self):
        if self.room_host is None or self.room is None:
            return
        room = self.room
        self.room_host.send({
            "type": "state", "board": room.board, "turn": room.turn,
            "last_move": room.last_move, "over": room.over, "winner": room.winner,
            "joined": room.joined_black, "physical_sync": room.physical_sync,
            "camera_status": room.camera_status, "status": self.status,
        })

    def draw(self):
        self.renderer._draw_ink_wash_background()
        if self.page == "menu":
            self._draw_menu()
        elif self.page == "host":
            self._draw_host()
        else:
            self._draw_game()

    def _text(self, value, center, font=None, color=INK):
        font = font or self.renderer.ui_font
        surface = font.render(value, True, color)
        self.screen.blit(surface, surface.get_rect(center=center))

    def _button(self, rect, label, color=JADE, font=None):
        self.renderer._draw_panel(rect.inflate(12, 12), fill=PAPER, border=GOLD, radius=14)
        pygame.draw.rect(self.screen, color, rect, border_radius=12)
        self._text(label, rect.center, font or self.renderer.ui_font, (255, 255, 255))

    def _draw_menu(self):
        self._text("VS NGƯỜI", (720, 340), self.renderer.title_font)
        self._text("Hai tab ĐỎ / ĐEN dùng chung một bàn cờ trên máy này.", (720, 418), self.renderer.ui_font, MUTED)
        self._button(self.menu_buttons["robot"], "TẠO PHÒNG 2 NGƯỜI + ROBOT", JADE)
        self._button(self.menu_buttons["local"], "THỬ 2 NGƯỜI (KHÔNG ROBOT)", (129, 120, 95))
        self._text("Người chơi thứ hai nhập mã phòng do chủ phòng cung cấp:", (720, 730), self.renderer.log_font, INK)
        entry = pygame.Rect(570, 760, 300, 54)
        self.renderer._draw_panel(entry, fill=(255, 252, 242), border=GOLD, radius=8)
        shown = self.code_input if self.code_input else "NHẬP MÃ PHÒNG"
        self._text(shown, entry.center, self.renderer.ui_font, INK if self.code_input else MUTED)
        self._button(self.menu_buttons["join"], "NHẬP MÃ ĐỂ VÀO PHÒNG", RED)
        self._button(self.menu_buttons["back"], "‹ HOME", JADE_DARK, self.renderer.log_font)
        self._draw_status(self.status, (720, 940), width=900)

    def _draw_host(self):
        self._text("BẠN LÀ CHỦ PHÒNG", (720, 330), self.renderer.title_font)
        self._text("Bạn sẽ chơi quân ĐỎ. Gửi mã này cho người chơi thứ hai:", (720, 420), self.renderer.ui_font, MUTED)
        self._text(self.room.code, (720, 500), self.renderer.title_font, RED)
        self._text("Đang chờ người chơi thứ hai nhập mã ở cửa sổ của họ…", (720, 630), self.renderer.ui_font, MUTED)
        self._text("Khi kết nối thành công, cả hai cửa sổ sẽ tự vào ván cờ.", (720, 690), self.renderer.log_font, MUTED)
        self._button(self.menu_buttons["back"], "‹ HOME", JADE_DARK, self.renderer.log_font)
        self._draw_status(self.status, (720, 790), width=900)

    def _draw_game(self):
        title = "PHÒNG 2 NGƯỜI + ROBOT" if self.room.mode == "robot" else "THỬ 2 NGƯỜI · KHÔNG ROBOT"
        self._text(f"{title}  ·  MÃ {self.room.code}", (720, 62), self.renderer.ui_font, MUTED)
        self._button(pygame.Rect(28, 30, 170, 58), "‹ HOME", JADE_DARK, self.renderer.log_font)

        for side, rect, label in (
            ("r", pygame.Rect(90, 142, 270, 62), "TAB ĐỎ · NGƯỜI CHƠI 1"),
            ("b", pygame.Rect(374, 142, 270, 62), "TAB ĐEN · NGƯỜI CHƠI 2"),
        ):
            active = self.active_tab == side
            color = JADE if side == self.player_side else (132, 123, 102)
            pygame.draw.rect(self.screen, color, rect, border_radius=9)
            self._text(label, rect.center, self.renderer.log_font, (255, 255, 255))

        self._draw_board()
        turn = "ĐỎ" if self.room.turn == "r" else "ĐEN"
        turn_text = "VÁN KẾT THÚC — " + ("ĐỎ" if self.room.winner == "r" else "ĐEN") + " THẮNG" if self.room.over else f"ĐẾN LƯỢT {turn}"
        self._text(turn_text, (1050, 180), self.renderer.game_font, RED if self.room.turn == "r" else INK)
        self._draw_status(self.status, (1050, 300), width=590)
        self._draw_status(self.room.camera_status, (1050, 440), width=590, color=RED if not self.room.physical_sync else MUTED)

        if self.room.mode == "robot" and not self.room.physical_sync and self.room_client is None:
            confirm_rect = pygame.Rect(790, 560, 520, 70)
            self._button(confirm_rect, "ĐÃ KIỂM TRA BÀN THẬT — TIẾP TỤC", RED, self.renderer.log_font)
        close_rect = pygame.Rect(790, 660, 520, 70)
        self._button(close_rect, "ĐÓNG VÁN · VỀ MENU VS NGƯỜI", (129, 120, 95), self.renderer.log_font)
        if not self.room.joined_black:
            self._draw_status(f"Đang chờ người chơi thứ hai nhập mã {self.room.code}.", (720, 920), width=1000)

    def _draw_board(self):
        left, top = self.board_left, self.board_top
        right, bottom = left + 8 * self.cell, top + 9 * self.cell
        board_rect = pygame.Rect(left - 34, top - 34, right - left + 68, bottom - top + 68)
        self.renderer._draw_panel(board_rect, fill=BOARD_WOOD, border=GOLD, radius=10)
        for row in range(10):
            y = top + row * self.cell
            pygame.draw.line(self.screen, (109, 78, 52), (left, y), (right, y), 2)
        for col in range(9):
            x = left + col * self.cell
            pygame.draw.line(self.screen, (109, 78, 52), (x, top), (x, bottom), 2)
        pygame.draw.line(self.screen, (109, 78, 52), (left + 3*self.cell, top), (left + 5*self.cell, top + 2*self.cell), 2)
        pygame.draw.line(self.screen, (109, 78, 52), (left + 5*self.cell, top), (left + 3*self.cell, top + 2*self.cell), 2)
        pygame.draw.line(self.screen, (109, 78, 52), (left + 3*self.cell, bottom - 2*self.cell), (left + 5*self.cell, bottom), 2)
        pygame.draw.line(self.screen, (109, 78, 52), (left + 5*self.cell, bottom - 2*self.cell), (left + 3*self.cell, bottom), 2)
        river = pygame.Rect(left + 1, top + 4*self.cell + 1, right - left - 2, self.cell - 2)
        pygame.draw.rect(self.screen, (236, 212, 169), river)
        self._text("楚 河       漢 界", river.center, self.renderer.log_font, (152, 119, 80))
        if self.room.last_move:
            for col, row in self.room.last_move:
                pygame.draw.circle(self.screen, (57, 132, 91), self._xy(col, row), 25, 3)
        if self.room.selected:
            pygame.draw.circle(self.screen, (25, 118, 184), self._xy(*self.room.selected), 30, 4)
        piece_font = pygame.font.SysFont("simsun", 30, bold=True)
        for row in range(10):
            for col in range(9):
                piece = self.room.board[row][col]
                if piece == ".":
                    continue
                x, y = self._xy(col, row)
                is_red = piece.startswith("r_")
                pygame.draw.circle(self.screen, (255, 244, 220), (x, y), 25)
                pygame.draw.circle(self.screen, (173, 48, 40) if is_red else (41, 45, 49), (x, y), 25, 2)
                self._text(PIECE_GLYPHS.get(piece, "?"), (x, y), piece_font,
                           (179, 45, 36) if is_red else (37, 42, 49))

    def _xy(self, col, row):
        return self.board_left + col*self.cell, self.board_top + row*self.cell

    def _draw_status(self, message, center, width, color=MUTED):
        words = str(message).split()
        lines, line = [], ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if self.renderer.log_font.size(candidate)[0] > width and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        if line:
            lines.append(line)
        for i, text in enumerate(lines[:4]):
            self._text(text, (center[0], center[1] + i*29), self.renderer.log_font, color)

    def handle_event(self, event, canvas_pos):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "home" if self.page == "menu" else self._back_to_menu()
            if self.page == "menu":
                if event.key == pygame.K_BACKSPACE:
                    self.code_input = self.code_input[:-1]
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._join(self.code_input)
                elif event.unicode and event.unicode.isalnum() and len(self.code_input) < 6:
                    self.code_input += event.unicode.upper()
            elif self.page == "game" and event.key == pygame.K_TAB:
                self.active_tab = "b" if self.active_tab == "r" else "r"

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None
        x, y = canvas_pos
        if self.page == "menu":
            if self.menu_buttons["back"].collidepoint(x, y):
                return "home"
            if self.menu_buttons["robot"].collidepoint(x, y):
                self._create_robot_room()
            elif self.menu_buttons["local"].collidepoint(x, y):
                if self.hardware is not None:
                    self.close()
                self.room = LocalRoom("local")
                self.player_side = "r"
                try:
                    self.room_host = LocalRoomHost(self.room.code, self.room.mode)
                except OSError as exc:
                    self.room = None
                    self.status = f"Không mở được phòng localhost: {exc}"
                    return None
                self.code_input = ""
                self.status = "Nhập lại mã vừa được cấp để người chơi thứ hai vào phòng."
                self.page = "host"
            elif self.menu_buttons["join"].collidepoint(x, y):
                self._join(self.code_input)
        elif self.page == "host":
            if self.menu_buttons["back"].collidepoint(x, y):
                return "home"
        elif self.page == "game":
            if pygame.Rect(28, 30, 170, 58).collidepoint(x, y):
                return "home"
            if pygame.Rect(790, 660, 520, 70).collidepoint(x, y):
                self.page = "menu"
                self._close_room_resources()
                self.code_input = ""
                return None
            if (self.room.mode == "robot" and not self.room.physical_sync and self.room_client is None
                    and pygame.Rect(790, 560, 520, 70).collidepoint(x, y)):
                self.room.physical_sync = True
                self.room.camera_status = "Chủ phòng xác nhận bàn thật khớp với bàn trên màn hình."
                return None
            if pygame.Rect(90, 142, 270, 62).collidepoint(x, y):
                if self.player_side != "r":
                    self.status = "Người tạo phòng chơi quân ĐỎ."
                    return None
                self.active_tab = "r"
                return None
            if pygame.Rect(374, 142, 270, 62).collidepoint(x, y):
                if self.player_side != "b":
                    self.status = "Người tham gia bằng mã chơi quân ĐEN."
                    return None
                self.active_tab = "b"
                return None
            self._on_board_click(x, y)
        return None

    def _create_robot_room(self):
        try:
            self.status = "Đang kết nối FR3 và khởi tạo camera…"
            pygame.event.pump()
            self._draw_menu()
            pygame.display.flip()
            if self.hardware is None:
                self.hardware = _initialize_robot_hardware()
            self.room = LocalRoom("robot")
            self.room_host = LocalRoomHost(self.room.code, self.room.mode)
            self.player_side = "r"
            self.active_tab = "r"
            self.room.camera_status = "FR3 và camera đã sẵn sàng."
            self.page = "host"
            self.code_input = ""
            self.status = "Đưa mã phòng cho người chơi thứ hai."
        except Exception as exc:
            self.close()
            self.status = f"Không tạo được phòng robot: {exc}"

    def _join(self, entered):
        entered = entered.strip().upper()
        if not self.room:
            if len(entered) != 6:
                self.status = "Nhập mã phòng gồm 6 ký tự do chủ phòng cung cấp."
                return
            registry_path = os.path.join(ROOM_REGISTRY, f"{entered}.json")
            try:
                with open(registry_path, "r", encoding="utf-8") as registry:
                    port = json.load(registry)["port"]
                self.room_client = LocalRoomClient(entered, port)
                self.room = LocalRoom(self.room_client.mode)
                self.room.code = entered
                self.room.joined_black = True
                self.player_side = "b"
                self.room.camera_status = "Đã kết nối phòng trên máy chủ local."
                self.active_tab = "b"
                self.status = "Đã vào phòng. Đang đồng bộ bàn cờ với chủ phòng…"
                self.page = "game"
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, socket.timeout) as exc:
                self.status = f"Không vào được phòng {entered}: {exc}"
            return
        if entered != self.room.code:
            self.status = "Mã không hợp lệ. Hãy nhập đúng mã chủ phòng vừa cung cấp."
            return
        self.room.joined_black = True
        self.active_tab = "r"
        self.status = "Chọn tab ĐỎ hoặc ĐEN. Chỉ tab đến lượt mới được đi quân."
        self.page = "game"

    def _back_to_menu(self):
        self._close_room_resources()
        self.page = "menu"
        self.code_input = ""
        return None

    def _on_board_click(self, x, y):
        if self.room.over or not self.room.joined_black:
            return
        if self.room_client is not None and self.remote_move_pending:
            self.status = "Đang chờ chủ phòng xử lý nước đi trước…"
            return
        if self.room.mode == "robot" and not self.room.physical_sync:
            self.status = "Chờ chủ phòng xác nhận bàn thật trước nước tiếp theo."
            return
        if self.active_tab != self.player_side:
            self.status = f"Cửa sổ này được gán quân {'ĐỎ' if self.player_side == 'r' else 'ĐEN'}."
            return
        if self.player_side != self.room.turn:
            self.status = f"Chưa đến lượt quân {'ĐỎ' if self.player_side == 'r' else 'ĐEN'}."
            return
        col = round((x - self.board_left) / self.cell)
        row = round((y - self.board_top) / self.cell)
        if not (0 <= col < 9 and 0 <= row < 10):
            return
        pos = (col, row)
        piece = self.room.board[row][col]
        if self.room.selected is None:
            if piece != "." and piece[0] == self.active_tab:
                self.room.selected = pos
            return
        src = self.room.selected
        if piece != "." and piece[0] == self.active_tab:
            self.room.selected = pos
            return
        if not xiangqi.is_valid_move(src, pos, self.room.board, self.active_tab):
            self.status = "Nước đi không hợp lệ."
            self.room.selected = None
            return
        self.room.selected = None
        self._perform_move(self.active_tab, src, pos)

    def _perform_move(self, side, src, dst):
        board = self.room.board
        moving_piece = board[src[1]][src[0]]
        captured_piece = board[dst[1]][dst[0]]
        expected_board, _captured = xiangqi.make_temp_move(board, (src, dst))
        if self.room_client is not None:
            self.remote_move_pending = True
            if not self.room_client.send({"type": "move", "src": src, "dst": dst}):
                self.remote_move_pending = False
                self.status = "Không gửi được nước đi tới máy chủ phòng."
            else:
                self.status = "Đã gửi nước đi cho chủ phòng; đang chờ FR3/bàn cờ xác nhận."
            return
        if self.room.mode == "robot":
            if self.hardware is None or not self.hardware.robot.connected:
                self.room.physical_sync = False
                self.room.camera_status = "Robot mất kết nối; kiểm tra bàn thật trước khi tiếp tục."
                self._publish_state()
                return
            try:
                expected_cells = {"moving": src}
                if captured_piece != ".":
                    expected_cells["captured"] = dst
                targets = self.hardware.get_visual_pick_targets(expected_cells)
                self.hardware.robot.move_piece(
                    src[0], src[1], dst[0], dst[1], captured_piece != ".",
                    moving_visual_target=targets.get("moving"),
                    captured_visual_target=targets.get("captured"),
                )
            except Exception as exc:
                self.room.physical_sync = False
                self.room.camera_status = f"Robot báo lỗi; kiểm tra bàn thật: {exc}"
                self.status = "Nước đi chưa được xác nhận; bàn cờ trên màn hình chưa đổi."
                self._publish_state()
                return

        self.room.board = expected_board
        self.room.last_move = (src, dst)
        opponent = "b" if side == "r" else "r"
        if xiangqi.get_king_pos(opponent, self.room.board) is None or not xiangqi.find_all_valid_moves(opponent, self.room.board):
            self.room.over = True
            self.room.winner = side
        else:
            self.room.turn = opponent
        self.status = f"{'ĐỎ' if side == 'r' else 'ĐEN'} đã đi {PIECE_GLYPHS.get(moving_piece, moving_piece)}" + (" và ăn quân." if captured_piece != "." else ".")

        if self.room.mode == "robot":
            try:
                if self.hardware.cam_monitor and self.hardware.yolo_detector:
                    self.hardware.capture_baseline_if_needed(force_delay=1.0)
                frame, _detections = self.hardware.cam_monitor.get_fresh_snapshot()
                vision = self.hardware.recognize_board_state(frame)
                if vision and vision.get("success") and vision.get("board") == expected_board:
                    self.room.physical_sync = True
                    self.room.camera_status = "Camera xác nhận bàn thật khớp với nước đi."
                else:
                    self.room.physical_sync = False
                    self.room.camera_status = "Camera chưa xác nhận bàn khớp. Kiểm tra bàn thật trước nước tiếp theo."
            except Exception as exc:
                self.room.physical_sync = False
                self.room.camera_status = f"Camera chưa xác nhận được bàn ({exc}). Kiểm tra bàn thật."
        self._publish_state()


def _initialize_robot_hardware():
    """Reuse the project's existing FR3, camera, and calibrated pick pipeline."""
    import config
    from src.hardware.hardware_manager import HardwareManager

    if config.DRY_RUN:
        raise RuntimeError("config.DRY_RUN đang bật; chọn không robot hoặc tắt DRY_RUN để dùng FR3.")
    hardware = HardwareManager(config, os.path.dirname(os.path.abspath(__file__)))
    hardware._init_robot()
    if not hardware.robot.connected:
        hardware.cleanup()
        raise RuntimeError("Không kết nối được FR3. Kiểm tra robot, IP và bộ điều khiển.")
    try:
        hardware._init_camera()
    except SystemExit as exc:
        hardware.cleanup()
        raise RuntimeError("Camera hoặc hiệu chỉnh camera chưa sẵn sàng.") from exc
    if hardware.cam_monitor is None:
        hardware.cleanup()
        raise RuntimeError("Camera bàn cờ chưa khởi tạo được.")
    return hardware
