# =============================================================================
# === FILE: board_renderer.py (Tách từ main_VIP.py) ===
# === Hiển thị bàn cờ Tướng ảo trên Pygame ===
# =============================================================================
import time
import unicodedata
import pygame
from src.core import xiangqi

# ==========================================
# HẰNG SỐ HIỂN THỊ
# ==========================================
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SQUARE_SIZE = 40
NUM_COLS = xiangqi.NUM_COLS
NUM_ROWS = xiangqi.NUM_ROWS
BOARD_WIDTH = (NUM_COLS - 1) * SQUARE_SIZE
START_X = (SCREEN_WIDTH - BOARD_WIDTH) / 2
START_Y = (SCREEN_HEIGHT - ((NUM_ROWS - 1) * SQUARE_SIZE)) / 2 - 20
LINE_COLOR = (0, 0, 0)
BOARD_COLOR = (252, 230, 201)
PIECE_RADIUS = SQUARE_SIZE // 2 - 4

BTN_COLOR = (200, 50, 50)
BTN_NEW_GAME_COLOR = (50, 150, 200)
BTN_SURRENDER_RECT = pygame.Rect(SCREEN_WIDTH / 2 - 150, SCREEN_HEIGHT - 60, 120, 40)
BTN_NEW_GAME_RECT = pygame.Rect(SCREEN_WIDTH / 2 + 30, SCREEN_HEIGHT - 60, 120, 40)
BTN_VS_ROBOT_RECT = pygame.Rect(SCREEN_WIDTH // 2 - 110, 350, 220, 56)

PIECE_DISPLAY_NAMES = {
    "r_K": "帥", "r_A": "仕", "r_E": "相", "r_R": "俥",
    "r_N": "傌", "r_C": "炮", "r_P": "兵",
    "b_K": "將", "b_A": "士", "b_E": "象", "b_R": "車",
    "b_N": "馬", "b_C": "砲", "b_P": "卒",
}


def _ui_safe_text(text):
    """Return text that can be drawn consistently by a single Pygame font.

    Pygame/SDL_ttf does not perform the Windows font fallback used by normal
    desktop controls.  In particular, colour emoji such as ``⌨️`` and ``🤖``
    show up as an empty box when rendered with Arial.  UI messages should use
    words (and their colour) to convey state; retain letters, numbers and
    punctuation, but omit emoji/symbol glyphs Pygame cannot reliably render.
    """
    text = str(text).replace("⌨️", "[SPACE]")
    return "".join(
        char for char in text
        if not unicodedata.category(char).startswith("So")
        and char not in {"\ufe0e", "\ufe0f"}
    )


class BoardRenderer:
    """Quản lý hiển thị bàn cờ Tướng trên Pygame."""

    def __init__(self, screen):
        self.screen = screen
        # SimSun contains the Chinese Xiangqi characters; Segoe UI has solid
        # Vietnamese/Latin coverage on supported Windows installations.
        self.piece_font = pygame.font.SysFont("simsun", 20, bold=True)
        self.game_font = pygame.font.SysFont("times new roman", 36, bold=True)
        self.ui_font = pygame.font.SysFont("segoe ui", 16, bold=True)

    def _render_ui_text(self, text, color):
        """Render UI copy after removing glyphs without a reliable fallback."""
        return self.ui_font.render(_ui_safe_text(text), True, color)

    def draw_main_menu(self):
        """Draw the pre-game menu while the camera feed remains active."""
        self.screen.fill(BOARD_COLOR)

        title_font = pygame.font.SysFont("segoe ui", 36, bold=True)
        subtitle_font = pygame.font.SysFont("segoe ui", 18, bold=False)
        title = title_font.render("AI XIANGQI ROBOT ARM PROJECT", True, (0, 0, 0))
        subtitle = subtitle_font.render(
            "Prepare the physical board, then choose a game mode.",
            True, (0, 0, 0),
        )
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 155)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 215)))

        pygame.draw.rect(
            self.screen, BTN_NEW_GAME_COLOR, BTN_VS_ROBOT_RECT, border_radius=10
        )
        pygame.draw.rect(
            self.screen, (25, 105, 155), BTN_VS_ROBOT_RECT, width=2, border_radius=10
        )
        button_font = pygame.font.SysFont("segoe ui", 22, bold=True)
        button = button_font.render("VS ROBOT", True, (255, 255, 255))
        self.screen.blit(button, button.get_rect(center=BTN_VS_ROBOT_RECT.center))

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
        self.screen.fill(BOARD_COLOR)

        if not game_state.get("game_over"):
            # Nút SURRENDER
            pygame.draw.rect(self.screen, BTN_COLOR, BTN_SURRENDER_RECT, border_radius=8)
            txt = self._render_ui_text("SURRENDER", (255, 255, 255))
            self.screen.blit(txt, txt.get_rect(center=BTN_SURRENDER_RECT.center))

            # Nút NEW GAME
            pygame.draw.rect(self.screen, BTN_NEW_GAME_COLOR, BTN_NEW_GAME_RECT, border_radius=8)
            txt_new = self._render_ui_text("NEW GAME", (255, 255, 255))
            self.screen.blit(txt_new, txt_new.get_rect(center=BTN_NEW_GAME_RECT.center))

            # Mode indicator
            mode_str = "MOUSE (DRY RUN)" if game_state.get("allow_mouse") else "CAMERA AI"
            mode_txt = self._render_ui_text(f"MODE: {mode_str}", (0, 0, 255))
            self.screen.blit(mode_txt, (10, 10))

            # Hướng dẫn SPACE
            if game_state.get("turn") == "r" and not game_state.get("allow_mouse"):
                hint = self._render_ui_text("[SPACE] Bấm SPACE sau khi đi xong", (0, 100, 0))
                self.screen.blit(hint, (SCREEN_WIDTH - 280, 10))
        else:
            pygame.draw.rect(self.screen, BTN_NEW_GAME_COLOR, BTN_NEW_GAME_RECT, border_radius=8)
            txt_new = self._render_ui_text("NEW GAME", (255, 255, 255))
            self.screen.blit(txt_new, txt_new.get_rect(center=BTN_NEW_GAME_RECT.center))

        # --- Vẽ lưới bàn cờ ---
        for r in range(NUM_ROWS):
            pygame.draw.line(self.screen, LINE_COLOR,
                             self.grid_to_pixel(0, r), self.grid_to_pixel(NUM_COLS - 1, r), 1)
        for c in range(NUM_COLS):
            if c in [0, NUM_COLS - 1]:
                pygame.draw.line(self.screen, LINE_COLOR,
                                 self.grid_to_pixel(c, 0), self.grid_to_pixel(c, NUM_ROWS - 1), 1)
            else:
                pygame.draw.line(self.screen, LINE_COLOR,
                                 self.grid_to_pixel(c, 0), self.grid_to_pixel(c, 4), 1)
                pygame.draw.line(self.screen, LINE_COLOR,
                                 self.grid_to_pixel(c, 5), self.grid_to_pixel(c, 9), 1)

        # Cung tướng
        pygame.draw.line(self.screen, LINE_COLOR, self.grid_to_pixel(3, 0), self.grid_to_pixel(5, 2), 1)
        pygame.draw.line(self.screen, LINE_COLOR, self.grid_to_pixel(5, 0), self.grid_to_pixel(3, 2), 1)
        pygame.draw.line(self.screen, LINE_COLOR, self.grid_to_pixel(3, 7), self.grid_to_pixel(5, 9), 1)
        pygame.draw.line(self.screen, LINE_COLOR, self.grid_to_pixel(5, 7), self.grid_to_pixel(3, 9), 1)

        # --- Status message ---
        msg = game_state.get("status_message", "")
        # The winner banner owns the top area once a game has ended.
        if (not game_state.get("game_over") and msg
                and time.time() < game_state.get("status_expiry", 0)):
            color = game_state.get("status_color", (200, 0, 0))
            msg_surf = self._render_ui_text(msg, (255, 255, 255))
            padding = 8
            bg_rect = msg_surf.get_rect(centerx=SCREEN_WIDTH // 2, top=32)
            bg_rect.inflate_ip(padding * 2, padding * 2)
            bg_surf = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
            bg_surf.fill((*color, 200))
            self.screen.blit(bg_surf, bg_rect.topleft)
            self.screen.blit(msg_surf, msg_surf.get_rect(center=bg_rect.center))

        # --- AI thinking banner ---
        if game_state.get("ai_thinking"):
            start = game_state.get("ai_think_start", time.time())
            dots = "." * (int(time.time() - start) % 4)
            elapsed = time.time() - start
            think_msg = f"🤖  AI is thinking{dots}  ({elapsed:.1f}s)"
            think_surf = self._render_ui_text(think_msg, (255, 255, 255))
            padding = 10
            bg_rect = think_surf.get_rect(centerx=SCREEN_WIDTH // 2, top=8)
            bg_rect.inflate_ip(padding * 2, padding * 2)
            bg_surf = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
            bg_surf.fill((20, 100, 20, 210))
            self.screen.blit(bg_surf, bg_rect.topleft)
            self.screen.blit(think_surf, think_surf.get_rect(center=bg_rect.center))

    def draw_pieces(self, board):
        """Vẽ tất cả quân cờ trên bàn."""
        for r in range(NUM_ROWS):
            for c in range(NUM_COLS):
                name = board[r][c]
                if name == ".":
                    continue
                cx, cy = self.grid_to_pixel(c, r)
                color = (220, 20, 60) if name.startswith("r") else (0, 0, 0)
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
        """Draw the end-of-game banner above the board."""
        msg = "AI WINS" if winner == "b" else "HUMAN WINS"
        color = (0, 255, 0) if winner == "b" else (255, 0, 0)
        txt = self.game_font.render(msg, True, color)
        padding_x, padding_y = 16, 6
        banner = txt.get_rect(centerx=SCREEN_WIDTH // 2, top=30)
        background = banner.inflate(padding_x * 2, padding_y * 2)
        pygame.draw.rect(self.screen, (255, 255, 255), background, border_radius=8)
        pygame.draw.rect(self.screen, color, background, width=2, border_radius=8)
        self.screen.blit(txt, banner)
