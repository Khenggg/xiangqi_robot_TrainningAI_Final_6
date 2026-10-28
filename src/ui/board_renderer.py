# =============================================================================
# === FILE: board_renderer.py (Tách từ main_VIP.py) ===
# === Hiển thị bàn cờ Tướng ảo trên Pygame ===
# =============================================================================
import time
import os
import pygame
from src.core import xiangqi

# ==========================================
# HẰNG SỐ HIỂN THỊ
# ==========================================
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 1080
SQUARE_SIZE = 72
NUM_COLS = xiangqi.NUM_COLS
NUM_ROWS = xiangqi.NUM_ROWS
BOARD_WIDTH = (NUM_COLS - 1) * SQUARE_SIZE
START_X = (SCREEN_WIDTH - BOARD_WIDTH) / 2
START_Y = (SCREEN_HEIGHT - ((NUM_ROWS - 1) * SQUARE_SIZE)) / 2 + 14
LINE_COLOR = (69, 57, 38)
BOARD_COLOR = (246, 239, 220)
INK_COLOR = (33, 48, 43)
JADE_COLOR = (25, 111, 91)
JADE_DARK = (18, 75, 63)
GOLD_COLOR = (177, 142, 82)
VERMILION_COLOR = (177, 59, 47)
AMBER_COLOR = (184, 126, 45)
MENU_TEXT_COLOR = INK_COLOR
MENU_MUTED_TEXT_COLOR = (94, 101, 77)
MENU_ACCENT_COLOR = VERMILION_COLOR
MENU_BORDER_COLOR = GOLD_COLOR
RED_PIECE_COLOR = (192, 54, 46)
BLACK_PIECE_COLOR = (34, 40, 36)
# Keep the two side panels in the window gutters, clear of the board tray.
MOVE_LOG_RECT = pygame.Rect(20, 230, 340, 590)
MOVE_LOG_X = MOVE_LOG_RECT.x + 24
MOVE_LOG_Y = MOVE_LOG_RECT.y + 76
MOVE_LOG_LINE_HEIGHT = 48
AI_STATUS_RECT = pygame.Rect(420, 42, 600, 120)
PIECE_RADIUS = SQUARE_SIZE // 2 - 4

BTN_COLOR = (200, 50, 50)
BTN_NEW_GAME_COLOR = (50, 150, 200)
BTN_SURRENDER_RECT = pygame.Rect(540, 960, 160, 58)
BTN_NEW_GAME_RECT = pygame.Rect(740, 960, 160, 58)
# The control panel uses the right gutter: 38 px clear of the board tray and
# 20 px clear of the window edge.
CLIENT_ACTION_X = 1098
CLIENT_ACTION_WIDTH = 304
BTN_SCAN_FEN_RECT = pygame.Rect(CLIENT_ACTION_X, 342, CLIENT_ACTION_WIDTH, 64)
BTN_CONFIRM_MOVE_RECT = pygame.Rect(CLIENT_ACTION_X, 422, CLIENT_ACTION_WIDTH, 64)
BTN_EMERGENCY_RECT = pygame.Rect(CLIENT_ACTION_X, 502, CLIENT_ACTION_WIDTH, 64)
BTN_ROLLBACK_RECT = pygame.Rect(CLIENT_ACTION_X, 582, CLIENT_ACTION_WIDTH, 64)
BTN_CONTINUE_RECT = pygame.Rect(CLIENT_ACTION_X, 662, CLIENT_ACTION_WIDTH, 64)
BTN_PICK_RETRY_RECT = pygame.Rect(CLIENT_ACTION_X, 662, 148, 64)
BTN_PICK_CANCEL_RECT = pygame.Rect(CLIENT_ACTION_X + 156, 662, 148, 64)
BTN_PICK_TEST_RECT = pygame.Rect(CLIENT_ACTION_X, 742, CLIENT_ACTION_WIDTH, 64)
HOME_VS_ROBOT_RECT = pygame.Rect(SCREEN_WIDTH // 2 - 240, 650, 480, 104)
HOME_SETTINGS_RECT = pygame.Rect(SCREEN_WIDTH - 230, 42, 180, 58)
SETTINGS_BACK_RECT = pygame.Rect(48, 42, 168, 58)
DEBUG_STATUS_RECT = pygame.Rect(886, 330, 320, 70)
DIFFICULTY_OPTIONS = (
    ("easy", "EASY", pygame.Rect(120, 420, 560, 210), (62, 129, 91)),
    ("medium", "MEDIUM", pygame.Rect(760, 420, 560, 210), (33, 115, 96)),
    ("hard", "HARD", pygame.Rect(120, 680, 560, 210), (151, 79, 49)),
    ("impossible", "IMPOSSIBLE", pygame.Rect(760, 680, 560, 210), (109, 56, 51)),
)
DIFFICULTY_PRESENTATION = {
    "easy": ("兵", "TỐT", "Calm practice"),
    "medium": ("馬", "MÃ", "Balanced strategy"),
    "hard": ("車", "XE", "Tactical pressure"),
    "impossible": ("將", "TƯỚNG", "Master level"),
}

PIECE_DISPLAY_NAMES = {
    "r_K": "帥", "r_A": "仕", "r_E": "相", "r_R": "俥",
    "r_N": "傌", "r_C": "炮", "r_P": "兵",
    "b_K": "將", "b_A": "士", "b_E": "象", "b_R": "車",
    "b_N": "馬", "b_C": "砲", "b_P": "卒",
}

PIECE_LOG_NAMES = {
    "K": "Tướng", "A": "Sĩ", "E": "Tượng", "N": "Mã",
    "R": "Xe", "C": "Pháo", "P": "Tốt",
}

UNSUPPORTED_UI_GLYPHS = {
    "⌨": "", "️": "", "🤖": "AI ", "✅": "", "⚠": "", "❌": "",
    "📸": "", "↩": "", "✋": "",
}


def unicode_ui_font(size, bold=False):
    """Load Windows' Unicode UI font explicitly so Vietnamese glyphs are stable."""
    font_name = "segoeuib.ttf" if bold else "segoeui.ttf"
    font_path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", font_name)
    if os.path.isfile(font_path):
        return pygame.font.Font(font_path, size)
    return pygame.font.SysFont("Segoe UI", size, bold=bold)


def display_text(text):
    """Remove emoji-only glyphs that SDL_ttf cannot reliably fall back for."""
    for glyph, replacement in UNSUPPORTED_UI_GLYPHS.items():
        text = text.replace(glyph, replacement)
    return text


class BoardRenderer:
    """Quản lý hiển thị bàn cờ Tướng trên Pygame."""

    def __init__(self, screen):
        self.screen = screen
        self.piece_font = pygame.font.SysFont("simsun", 38, bold=True)
        self.game_font = pygame.font.SysFont("times new roman", 64, bold=True)
        self.title_font = pygame.font.SysFont("times new roman", 76, bold=True)
        self.ui_font = unicode_ui_font(26, bold=True)
        self.log_font = unicode_ui_font(19, bold=True)
        self.button_font = unicode_ui_font(22, bold=True)
        self._landscape = self._load_landscape()

    @staticmethod
    def _load_landscape():
        """Load the project-owned Ink & Jade art without affecting game logic."""
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, "assets", "ui", "ink-jade-landscape-1440x1080.png")
        try:
            image = pygame.image.load(path)
            return pygame.transform.smoothscale(image, (SCREEN_WIDTH, SCREEN_HEIGHT))
        except (pygame.error, OSError):
            return None

    def _draw_ink_wash_background(self):
        """Paint a layered ink-and-jade landscape behind the playable UI."""
        if self._landscape is not None:
            self.screen.blit(self._landscape, (0, 0))
            pygame.draw.rect(self.screen, GOLD_COLOR, (0, 0, SCREEN_WIDTH, 9))
            return

        self.screen.fill(BOARD_COLOR)
        wash = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        for cx, cy, radius, alpha in ((100, 930, 230, 22), (1320, 160, 196, 18), (1290, 920, 250, 16)):
            pygame.draw.circle(wash, (*JADE_DARK, alpha), (cx, cy), radius)
        # Pale morning sun and distant mist establish depth without competing
        # with the board or its controls.
        pygame.draw.circle(wash, (*GOLD_COLOR, 36), (700, 108), 54)
        pygame.draw.circle(wash, (*BOARD_COLOR, 115), (700, 108), 38)
        self._draw_mountain_ridge(wash, [(0, 600), (0, 548), (74, 486), (142, 544),
                                         (211, 495), (287, 558), (370, 515), (448, 574),
                                         (548, 504), (639, 554), (720, 475), (800, 528), (800, 600)],
                                  (*JADE_DARK, 31))
        self._draw_mountain_ridge(wash, [(0, 600), (0, 572), (102, 520), (181, 582),
                                         (272, 538), (362, 590), (463, 534), (559, 582),
                                         (660, 523), (746, 574), (800, 550), (800, 600)],
                                  (*JADE_COLOR, 42))
        for offset in range(-80, SCREEN_WIDTH + 80, 96):
            pygame.draw.line(wash, (*GOLD_COLOR, 11), (offset, 0), (offset + 168, SCREEN_HEIGHT), 1)
        self._draw_ink_branch(wash)
        self._draw_reeds(wash)
        self.screen.blit(wash, (0, 0))
        pygame.draw.rect(self.screen, GOLD_COLOR, (0, 0, SCREEN_WIDTH, 9))

    @staticmethod
    def _draw_mountain_ridge(surface, points, color):
        """Use a translucent polygon plus a thin brush contour for a mountain."""
        pygame.draw.polygon(surface, color, points)
        pygame.draw.lines(surface, (*JADE_DARK, max(color[3] + 22, 48)), False, points[1:-1], 2)

    @staticmethod
    def _draw_ink_branch(surface):
        """Place a restrained plum branch in a safe decorative corner."""
        branch = (*INK_COLOR, 78)
        twig = (*INK_COLOR, 54)
        pygame.draw.line(surface, branch, (-12, 72), (42, 50), 5)
        pygame.draw.line(surface, branch, (38, 51), (96, 25), 4)
        pygame.draw.line(surface, twig, (51, 46), (68, 10), 2)
        pygame.draw.line(surface, twig, (76, 34), (131, 35), 2)
        pygame.draw.line(surface, twig, (22, 58), (35, 16), 2)
        blossoms = ((66, 10), (69, 18), (101, 24), (121, 35), (36, 16), (41, 25), (91, 30))
        for x, y in blossoms:
            pygame.draw.circle(surface, (*VERMILION_COLOR, 82), (x, y), 4)
            pygame.draw.circle(surface, (*GOLD_COLOR, 105), (x, y), 1)

    @staticmethod
    def _draw_reeds(surface):
        """Add a small foreground reed cluster at the lower-right edge."""
        reed = (*JADE_DARK, 67)
        for base_x, lean, height in ((762, -18, 78), (778, 8, 62), (790, -10, 92)):
            base_y = 596
            tip = (base_x + lean, base_y - height)
            pygame.draw.line(surface, reed, (base_x, base_y), tip, 2)
            pygame.draw.line(surface, (*JADE_COLOR, 49),
                             (base_x + lean // 2, base_y - height // 2),
                             (base_x + lean // 2 - 12, base_y - height // 2 - 9), 1)

    def _draw_panel(self, rect, fill=(250, 245, 231), border=GOLD_COLOR, radius=10):
        outer = rect.inflate(8, 8)
        pygame.draw.rect(self.screen, (*border, 72), outer, width=2, border_radius=radius + 3)
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((*fill, 238))
        self.screen.blit(panel, rect.topleft)
        pygame.draw.rect(self.screen, border, rect, width=3, border_radius=radius)
        pygame.draw.rect(self.screen, (255, 253, 245), rect.inflate(-10, -10), width=1,
                         border_radius=max(radius - 3, 1))

    # --- Chuyển đổi tọa độ ---
    @staticmethod
    def grid_to_pixel(col, row):
        return int(START_X + col * SQUARE_SIZE), int(START_Y + row * SQUARE_SIZE)

    @staticmethod
    def pixel_to_grid(px, py):
        col = int(round((px - START_X) / SQUARE_SIZE))
        row = int(round((py - START_Y) / SQUARE_SIZE))
        return col, row

    # --- Vẽ giao diện ---
    def draw_ui(self, game_state):
        """Vẽ nền, bàn cờ, nút bấm, status bar.
        
        game_state: dict chứa các key:
            game_over, turn, allow_mouse, ai_thinking, ai_think_start,
            status_message, status_color, status_expiry
        """
        self._draw_ink_wash_background()

        self.draw_recent_moves(game_state.get("recent_moves", []))
        self._draw_ai_status(game_state)
        self._draw_board_backdrop()

        if not game_state.get("game_over"):
            # Nút SURRENDER
            pygame.draw.rect(self.screen, VERMILION_COLOR, BTN_SURRENDER_RECT, border_radius=14)
            txt = self.ui_font.render("SURRENDER", True, (255, 255, 255))
            self.screen.blit(txt, txt.get_rect(center=BTN_SURRENDER_RECT.center))

            # Nút NEW GAME
            pygame.draw.rect(self.screen, JADE_COLOR, BTN_NEW_GAME_RECT, border_radius=14)
            txt_new = self.ui_font.render("NEW GAME", True, (255, 255, 255))
            self.screen.blit(txt_new, txt_new.get_rect(center=BTN_NEW_GAME_RECT.center))

            self._draw_client_actions(game_state)
        else:
            pygame.draw.rect(self.screen, JADE_COLOR, BTN_NEW_GAME_RECT, border_radius=14)
            txt_new = self.ui_font.render("NEW GAME", True, (255, 255, 255))
            self.screen.blit(txt_new, txt_new.get_rect(center=BTN_NEW_GAME_RECT.center))

    def _draw_client_actions(self, game_state):
        """Draw the always-visible client control panel beside the board."""
        panel = pygame.Rect(CLIENT_ACTION_X - 18, 230, CLIENT_ACTION_WIDTH + 36, 620)
        self._draw_panel(panel, fill=(248, 242, 226), border=GOLD_COLOR)
        title = self.ui_font.render("CLIENT CONTROLS", True, JADE_DARK)
        self.screen.blit(title, title.get_rect(center=(panel.centerx, 274)))

        actions = (
            (BTN_SCAN_FEN_RECT, "V", ("QUÉT / ĐỐI SOÁT FEN",), JADE_COLOR),
            (BTN_CONFIRM_MOVE_RECT, "SPACE", ("XÁC NHẬN", "NƯỚC ĐỎ"), JADE_DARK),
            (BTN_EMERGENCY_RECT, "M", ("EMERGENCY MODE",), VERMILION_COLOR),
            (BTN_ROLLBACK_RECT, "Z", ("ROLLBACK",), AMBER_COLOR),
            (BTN_PICK_TEST_RECT, "T", ("TEST GẮP / THẢ",), JADE_COLOR),
        )
        emergency_active = game_state.get("emergency_mode", False)
        for rect, key, label_lines, color in actions:
            active = (key == "M" and emergency_active) or (key == "T" and game_state.get("pick_test_mode", False))
            button_color = (139, 48, 38) if active else color
            pygame.draw.rect(self.screen, button_color, rect, border_radius=12)
            key_surf = self.ui_font.render(key, True, (255, 255, 255))
            self.screen.blit(key_surf, (rect.x + 18, rect.y + 17))
            label_x = rect.x + 38 + key_surf.get_width()
            if len(label_lines) == 1:
                label_surf = self.button_font.render(label_lines[0], True, (255, 255, 255))
                self.screen.blit(label_surf, (label_x, rect.y + 20))
            else:
                for line_index, label in enumerate(label_lines):
                    label_surf = self.button_font.render(label, True, (255, 255, 255))
                    self.screen.blit(label_surf, (label_x, rect.y + 9 + line_index * 25))

        if game_state.get("visual_pick_retry"):
            for rect, label, color in ((BTN_PICK_RETRY_RECT, "R: THỬ LẠI", JADE_COLOR),
                                       (BTN_PICK_CANCEL_RECT, "X: HỦY", VERMILION_COLOR)):
                pygame.draw.rect(self.screen, color, rect, border_radius=12)
                text = self.button_font.render(label, True, (255, 255, 255))
                self.screen.blit(text, text.get_rect(center=rect.center))
        else:
            can_continue = game_state.get("snapshot_continue_required", False)
            continue_color = JADE_COLOR if can_continue else (121, 116, 100)
            pygame.draw.rect(self.screen, continue_color, BTN_CONTINUE_RECT, border_radius=12)
            continue_key = self.ui_font.render("▶", True, (255, 255, 255))
            continue_label = self.ui_font.render("CONTINUE", True, (255, 255, 255))
            self.screen.blit(continue_key, (BTN_CONTINUE_RECT.x + 18, BTN_CONTINUE_RECT.y + 17))
            self.screen.blit(continue_label, (BTN_CONTINUE_RECT.x + 66, BTN_CONTINUE_RECT.y + 17))

        note = ("T: chọn quân → chọn ô trống" if game_state.get("pick_test_mode", False)
                else "M đang bật: đi tay Đỏ / Đen" if emergency_active else "Chọn phím hoặc bấm nút")
        note_surf = self.log_font.render(note, True, MENU_MUTED_TEXT_COLOR)
        self.screen.blit(note_surf, note_surf.get_rect(center=(panel.centerx, 816)))

        # --- Vẽ lưới bàn cờ ---
        for r in range(NUM_ROWS):
            pygame.draw.line(self.screen, LINE_COLOR,
                             self.grid_to_pixel(0, r), self.grid_to_pixel(NUM_COLS - 1, r), 2)
        for c in range(NUM_COLS):
            if c in [0, NUM_COLS - 1]:
                pygame.draw.line(self.screen, LINE_COLOR,
                                 self.grid_to_pixel(c, 0), self.grid_to_pixel(c, NUM_ROWS - 1), 2)
            else:
                pygame.draw.line(self.screen, LINE_COLOR,
                                 self.grid_to_pixel(c, 0), self.grid_to_pixel(c, 4), 2)
                pygame.draw.line(self.screen, LINE_COLOR,
                                 self.grid_to_pixel(c, 5), self.grid_to_pixel(c, 9), 2)

        # Cung tướng
        pygame.draw.line(self.screen, LINE_COLOR, self.grid_to_pixel(3, 0), self.grid_to_pixel(5, 2), 2)
        pygame.draw.line(self.screen, LINE_COLOR, self.grid_to_pixel(5, 0), self.grid_to_pixel(3, 2), 2)
        pygame.draw.line(self.screen, LINE_COLOR, self.grid_to_pixel(3, 7), self.grid_to_pixel(5, 9), 2)
        pygame.draw.line(self.screen, LINE_COLOR, self.grid_to_pixel(5, 7), self.grid_to_pixel(3, 9), 2)
        self.draw_board_coordinates()

    def _draw_board_backdrop(self):
        """Give the enlarged board a parchment tray over the scenic landscape."""
        board_height = (NUM_ROWS - 1) * SQUARE_SIZE
        tray = pygame.Rect(int(START_X) - 34, int(START_Y) - 34,
                           BOARD_WIDTH + 68, board_height + 68)
        outer = tray.inflate(12, 12)
        pygame.draw.rect(self.screen, GOLD_COLOR, outer, border_radius=18)
        parchment = pygame.Surface(tray.size, pygame.SRCALPHA)
        parchment.fill((248, 238, 211, 222))
        self.screen.blit(parchment, tray.topleft)
        pygame.draw.rect(self.screen, JADE_DARK, tray, width=3, border_radius=14)
        pygame.draw.rect(self.screen, GOLD_COLOR, tray.inflate(-14, -14), width=2, border_radius=9)

    def _draw_ai_status(self, game_state):
        """Render one live status, never a historical activity feed."""
        now = time.time()
        if game_state.get("pick_test_mode"):
            message = display_text(game_state.get("status_message", "")) if now < game_state.get("status_expiry", 0) else "TEST: chọn quân Đỏ/Đen rồi chọn ô trống. T để thoát."
            accent = AMBER_COLOR
        elif game_state.get("ai_thinking"):
            elapsed = now - game_state.get("ai_think_start", now)
            dots = "." * (int(elapsed) % 4)
            message = f"AI is thinking{dots} ({elapsed:.1f}s)"
            accent = JADE_COLOR
        elif (message := display_text(game_state.get("status_message", ""))) and now < game_state.get("status_expiry", 0):
            raw_color = game_state.get("status_color", (180, 100, 0))
            accent = VERMILION_COLOR if raw_color[0] > raw_color[1] else JADE_COLOR
            if "CHECK" in message.upper():
                accent = VERMILION_COLOR
        else:
            message = "Your turn — move, then confirm with SPACE"
            accent = JADE_COLOR

        self._draw_panel(AI_STATUS_RECT, fill=(249, 245, 232), border=accent, radius=12)
        pulse = 10 + int((now * 2) % 4)
        pygame.draw.circle(self.screen, accent, (AI_STATUS_RECT.x + 37, AI_STATUS_RECT.centery), pulse)
        label = self.log_font.render("AI STATUS", True, JADE_DARK)
        self.screen.blit(label, (AI_STATUS_RECT.x + 67, AI_STATUS_RECT.y + 16))
        available = AI_STATUS_RECT.width - 95
        words, lines, current = message.split(), [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and self.log_font.size(candidate)[0] > available:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        if len(lines) > 2:
            lines = [lines[0], lines[1] + "..."]
        for index, line in enumerate(lines):
            text = self.log_font.render(line, True, INK_COLOR)
            self.screen.blit(text, (AI_STATUS_RECT.x + 67, AI_STATUS_RECT.y + 52 + index * 24))

    @staticmethod
    def _format_move(entry):
        piece = PIECE_LOG_NAMES.get(entry.get("piece", "")[-1:], "Piece")
        src_col, src_row = entry["src"]
        dst_col, dst_row = entry["dst"]
        src = f"{chr(ord('a') + src_col)}{src_row}"
        dst = f"{chr(ord('a') + dst_col)}{dst_row}"
        return f"{piece} {src} -> {dst}"

    def draw_recent_moves(self, moves):
        """Draw the latest eight moves in their moving side's color."""
        self._draw_panel(MOVE_LOG_RECT, fill=(249, 245, 232), border=GOLD_COLOR, radius=14)
        title = self.ui_font.render("RECENT MOVES", True, JADE_DARK)
        self.screen.blit(title, title.get_rect(center=(MOVE_LOG_RECT.centerx, MOVE_LOG_RECT.y + 38)))
        pygame.draw.line(self.screen, GOLD_COLOR, (MOVE_LOG_RECT.x + 24, MOVE_LOG_RECT.y + 61),
                         (MOVE_LOG_RECT.right - 24, MOVE_LOG_RECT.y + 61), 2)
        for index, entry in enumerate(moves[-8:]):
            color = RED_PIECE_COLOR if entry.get("turn") == "r" else BLACK_PIECE_COLOR
            text = self.log_font.render(self._format_move(entry), True, color)
            y = MOVE_LOG_Y + index * MOVE_LOG_LINE_HEIGHT
            if index == len(moves[-8:]) - 1:
                pygame.draw.rect(self.screen, (221, 235, 216),
                                 (MOVE_LOG_X - 8, y - 6, MOVE_LOG_RECT.width - 32, 36), border_radius=8)
            self.screen.blit(text, (MOVE_LOG_X, y))

    def draw_board_coordinates(self):
        """Label the board's compact internal a-i / 0-9 coordinate grid."""
        for col in range(NUM_COLS):
            label = self.log_font.render(chr(ord("a") + col), True, MENU_MUTED_TEXT_COLOR)
            x, _ = self.grid_to_pixel(col, 0)
            self.screen.blit(label, label.get_rect(
                center=(x, int(START_Y) - PIECE_RADIUS - 18)
            ))
        for row in range(NUM_ROWS):
            label = self.log_font.render(str(row), True, MENU_MUTED_TEXT_COLOR)
            _, y = self.grid_to_pixel(0, row)
            self.screen.blit(label, label.get_rect(center=(int(START_X) - PIECE_RADIUS - 17, y)))

    def draw_difficulty_menu(self, availability, message=""):
        """Overlay shown after camera calibration and before a game can begin."""
        self._draw_ink_wash_background()
        title = self.title_font.render("CHOOSE YOUR OPPONENT", True, INK_COLOR)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 170)))
        subtitle = self.ui_font.render("Pick a challenge that feels right", True, MENU_MUTED_TEXT_COLOR)
        self.screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 250)))
        pygame.draw.line(self.screen, GOLD_COLOR, (480, 290), (960, 290), 2)
        for key, label, rect, color in DIFFICULTY_OPTIONS:
            enabled = availability.get(key, False)
            border = color if enabled else (154, 145, 125)
            self._draw_panel(rect, fill=(249, 245, 232) if enabled else (229, 222, 205), border=border)
            piece, piece_name, description = DIFFICULTY_PRESENTATION[key]
            piece_color = RED_PIECE_COLOR if key in ("hard", "impossible") else JADE_DARK
            pygame.draw.circle(self.screen, (255, 252, 242), (rect.x + 98, rect.centery), 58)
            pygame.draw.circle(self.screen, border, (rect.x + 98, rect.centery), 58, 3)
            piece_surf = self.piece_font.render(piece, True, piece_color)
            self.screen.blit(piece_surf, piece_surf.get_rect(center=(rect.x + 98, rect.centery)))
            name = self.ui_font.render(f"{label} · {piece_name}", True, INK_COLOR if enabled else MENU_MUTED_TEXT_COLOR)
            self.screen.blit(name, (rect.x + 190, rect.y + 57))
            detail = self.log_font.render(description if enabled else "Moonfish not ready", True, MENU_MUTED_TEXT_COLOR)
            self.screen.blit(detail, (rect.x + 190, rect.y + 112))
        if message:
            note = self.log_font.render(message, True, VERMILION_COLOR)
            self.screen.blit(note, note.get_rect(center=(SCREEN_WIDTH // 2, 950)))

    def draw_home_screen(self):
        """Draw the launcher shown before the player chooses a game mode."""
        self._draw_ink_wash_background()

        title = self.title_font.render("XIANGQI ROBOT", True, INK_COLOR)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 352)))
        subtitle = self.ui_font.render("A thoughtful match, guided by a robot", True, MENU_MUTED_TEXT_COLOR)
        self.screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 430)))

        self._draw_panel(HOME_SETTINGS_RECT, fill=JADE_DARK, border=JADE_DARK, radius=8)
        settings = self.log_font.render("SETTINGS", True, (255, 255, 255))
        self.screen.blit(settings, settings.get_rect(center=HOME_SETTINGS_RECT.center))

        card = HOME_VS_ROBOT_RECT.inflate(48, 68)
        self._draw_panel(card, fill=(249, 245, 232), border=GOLD_COLOR, radius=20)
        pygame.draw.circle(self.screen, JADE_DARK, (SCREEN_WIDTH // 2, card.y + 52), 30)
        robot_mark = self.log_font.render("AI", True, (255, 255, 255))
        self.screen.blit(robot_mark, robot_mark.get_rect(center=(SCREEN_WIDTH // 2, card.y + 52)))
        pygame.draw.rect(self.screen, JADE_COLOR, HOME_VS_ROBOT_RECT, border_radius=18)
        button = self.game_font.render("VS ROBOT", True, (255, 255, 255))
        self.screen.blit(button, button.get_rect(center=(SCREEN_WIDTH // 2, HOME_VS_ROBOT_RECT.centery - 12)))
        detail = self.log_font.render("Choose the robot difficulty next", True, (227, 245, 237))
        self.screen.blit(detail, detail.get_rect(center=(SCREEN_WIDTH // 2, HOME_VS_ROBOT_RECT.centery + 32)))

        hint_rect = pygame.Rect(SCREEN_WIDTH // 2 - 190, 810, 380, 46)
        self._draw_panel(hint_rect, fill=(249, 245, 232), border=GOLD_COLOR, radius=18)
        hint = self.log_font.render("Click VS ROBOT or press Enter", True, MENU_MUTED_TEXT_COLOR)
        self.screen.blit(hint, hint.get_rect(center=hint_rect.center))

    @staticmethod
    def home_action_from_pixel(px, py):
        if HOME_VS_ROBOT_RECT.collidepoint(px, py):
            return "vs_robot"
        if HOME_SETTINGS_RECT.collidepoint(px, py):
            return "settings"
        return None

    def draw_settings_menu(self, debug_enabled):
        """Draw the pre-game settings restored from the previous menu flow."""
        self.screen.fill(BOARD_COLOR)
        pygame.draw.rect(self.screen, (61, 73, 82), SETTINGS_BACK_RECT, border_radius=8)
        back = self.ui_font.render("< HOME", True, (255, 255, 255))
        self.screen.blit(back, back.get_rect(center=SETTINGS_BACK_RECT.center))

        title = self.game_font.render("SETTINGS", True, MENU_TEXT_COLOR)
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 118)))
        label = self.ui_font.render("Debug dashboard", True, MENU_TEXT_COLOR)
        self.screen.blit(label, label.get_rect(midleft=(126, DEBUG_STATUS_RECT.centery)))

        status = "ENABLED" if debug_enabled else "DISABLED"
        color = (62, 129, 91) if debug_enabled else (159, 59, 55)
        pygame.draw.rect(self.screen, color, DEBUG_STATUS_RECT, border_radius=10)
        status_text = self.ui_font.render(status, True, (255, 255, 255))
        self.screen.blit(status_text, status_text.get_rect(center=DEBUG_STATUS_RECT.center))

        note = self.ui_font.render("Opens a separate read-only robot telemetry window", True, MENU_MUTED_TEXT_COLOR)
        self.screen.blit(note, note.get_rect(center=(SCREEN_WIDTH // 2, 284)))

    @staticmethod
    def settings_action_from_pixel(px, py):
        if SETTINGS_BACK_RECT.collidepoint(px, py):
            return "home"
        if DEBUG_STATUS_RECT.collidepoint(px, py):
            return "toggle_debug_dashboard"
        return None

    @staticmethod
    def difficulty_from_pixel(px, py):
        for key, _, rect, _ in DIFFICULTY_OPTIONS:
            if rect.collidepoint(px, py):
                return key
        return None

    def draw_pieces(self, board):
        """Vẽ tất cả quân cờ trên bàn."""
        for r in range(NUM_ROWS):
            for c in range(NUM_COLS):
                name = board[r][c]
                if name == ".":
                    continue
                cx, cy = self.grid_to_pixel(c, r)
                color = RED_PIECE_COLOR if name.startswith("r") else BLACK_PIECE_COLOR
                pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), PIECE_RADIUS)
                pygame.draw.circle(self.screen, color, (cx, cy), PIECE_RADIUS, 2)
                text_surf = self.piece_font.render(
                    PIECE_DISPLAY_NAMES.get(name, "?"), True, color)
                self.screen.blit(text_surf, text_surf.get_rect(center=(cx, cy)))

    def draw_highlight(self, last_move=None, selected_pos=None,
                       invalid_flash_pos=None, invalid_flash_expiry=0):
        """Vẽ highlight: nước đi cuối, ô chọn, invalid flash."""
        if last_move:
            s, d = last_move
            pygame.draw.circle(self.screen, (0, 255, 0, 100),
                               self.grid_to_pixel(s[0], s[1]), PIECE_RADIUS + 2, 2)
            pygame.draw.circle(self.screen, (0, 255, 0, 150),
                               self.grid_to_pixel(d[0], d[1]), PIECE_RADIUS + 2, 2)
        if selected_pos:
            c, r = selected_pos
            cx, cy = self.grid_to_pixel(c, r)
            pygame.draw.circle(self.screen, (0, 0, 255), (cx, cy), PIECE_RADIUS + 4, 2)
        if invalid_flash_pos and time.time() < invalid_flash_expiry:
            fc, fr = invalid_flash_pos
            fx, fy = self.grid_to_pixel(fc, fr)
            pygame.draw.circle(self.screen, (220, 0, 0), (fx, fy), PIECE_RADIUS + 6, 4)

    def draw_game_over(self, winner):
        """Vẽ thông báo kết thúc game."""
        msg = "AI WINS (SAVED)" if winner == "b" else "YOU WIN (NOT SAVED)"
        color = (0, 255, 0) if winner == "b" else (255, 0, 0)
        txt = self.game_font.render(msg, True, color)
        self.screen.blit(txt, txt.get_rect(center=(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2)))
