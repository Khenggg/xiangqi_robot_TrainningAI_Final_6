# =============================================================================
# === FILE: board_renderer.py (Tách từ main_VIP.py) ===
# === Hiển thị bàn cờ Tướng ảo trên Pygame ===
# =============================================================================
import time
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
HOME_VS_ROBOT_RECT = pygame.Rect(SCREEN_WIDTH // 2 - 165, 330, 330, 68)
HOME_ROBOT_VS_ROBOT_RECT = pygame.Rect(SCREEN_WIDTH // 2 - 165, 414, 330, 68)
HOME_SETTINGS_RECT = pygame.Rect(SCREEN_WIDTH - 142, 22, 120, 38)
SETTINGS_BACK_RECT = pygame.Rect(28, 22, 112, 38)
DEBUG_STATUS_RECT = pygame.Rect(492, 190, 180, 48)
DIFFICULTY_OPTIONS = (
    ("easy", "1 · EASY", pygame.Rect(105, 330, 275, 64), (62, 129, 91)),
    ("medium", "2 · MEDIUM", pygame.Rect(420, 330, 275, 64), (197, 132, 48)),
    ("hard", "3 · HARD", pygame.Rect(105, 414, 275, 64), (159, 59, 55)),
    ("impossible", "4 · IMPOSSIBLE", pygame.Rect(420, 414, 275, 64), (103, 61, 152)),
)

PIECE_DISPLAY_NAMES = {
    "r_K": "帥", "r_A": "仕", "r_E": "相", "r_R": "俥",
    "r_N": "傌", "r_C": "炮", "r_P": "兵",
    "b_K": "將", "b_A": "士", "b_E": "象", "b_R": "車",
    "b_N": "馬", "b_C": "砲", "b_P": "卒",
}


class BoardRenderer:
    """Quản lý hiển thị bàn cờ Tướng trên Pygame."""

    def __init__(self, screen):
        self.screen = screen
        self.piece_font = pygame.font.SysFont("simsun", 20, bold=True)
        self.game_font = pygame.font.SysFont("times new roman", 36, bold=True)
        self.ui_font = pygame.font.SysFont("arial", 16, bold=True)

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
            txt = self.ui_font.render("SURRENDER", True, (255, 255, 255))
            self.screen.blit(txt, txt.get_rect(center=BTN_SURRENDER_RECT.center))

            # Nút NEW GAME
            pygame.draw.rect(self.screen, BTN_NEW_GAME_COLOR, BTN_NEW_GAME_RECT, border_radius=8)
            txt_new = self.ui_font.render("NEW GAME", True, (255, 255, 255))
            self.screen.blit(txt_new, txt_new.get_rect(center=BTN_NEW_GAME_RECT.center))

            # Mode indicator
            mode_str = "MOUSE (DRY RUN)" if game_state.get("allow_mouse") else "CAMERA AI"
            mode_txt = self.ui_font.render(f"MODE: {mode_str}", True, (0, 0, 255))
            self.screen.blit(mode_txt, (10, 10))

            # Hướng dẫn SPACE
            if game_state.get("turn") == "r" and not game_state.get("allow_mouse"):
                hint = self.ui_font.render("⌨️ Bấm SPACE sau khi đi xong", True, (0, 100, 0))
                self.screen.blit(hint, (SCREEN_WIDTH - 280, 10))
        else:
            pygame.draw.rect(self.screen, BTN_NEW_GAME_COLOR, BTN_NEW_GAME_RECT, border_radius=8)
            txt_new = self.ui_font.render("NEW GAME", True, (255, 255, 255))
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
        if msg and time.time() < game_state.get("status_expiry", 0):
            color = game_state.get("status_color", (200, 0, 0))
            msg_surf = self.ui_font.render(msg, True, (255, 255, 255))
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
            think_surf = self.ui_font.render(think_msg, True, (255, 255, 255))
            padding = 10
            bg_rect = think_surf.get_rect(centerx=SCREEN_WIDTH // 2, top=8)
            bg_rect.inflate_ip(padding * 2, padding * 2)
            bg_surf = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
            bg_surf.fill((20, 100, 20, 210))
            self.screen.blit(bg_surf, bg_rect.topleft)
            self.screen.blit(think_surf, think_surf.get_rect(center=bg_rect.center))

    def draw_difficulty_menu(self, availability, message=""):
        """Overlay shown after camera calibration and before a game can begin."""
        shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        shade.fill((25, 20, 16, 218))
        self.screen.blit(shade, (0, 0))
        title = self.game_font.render("CHOOSE YOUR OPPONENT", True, (246, 225, 184))
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 208)))
        subtitle = self.ui_font.render("Select a difficulty to start after board calibration", True, (228, 214, 190))
        self.screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 246)))
        for key, label, rect, color in DIFFICULTY_OPTIONS:
            enabled = availability.get(key, False)
            card_color = color if enabled else (78, 72, 65)
            pygame.draw.rect(self.screen, card_color, rect, border_radius=10)
            pygame.draw.rect(self.screen, (239, 218, 177) if enabled else (125, 118, 107), rect, 2, border_radius=10)
            text = self.ui_font.render(label, True, (255, 255, 255) if enabled else (185, 178, 166))
            self.screen.blit(text, text.get_rect(center=(rect.centerx, rect.centery - 10)))
            detail = "READY" if enabled else "MOONFISH NOT READY"
            detail_surf = self.ui_font.render(detail, True, (246, 227, 193) if enabled else (190, 181, 166))
            self.screen.blit(detail_surf, detail_surf.get_rect(center=(rect.centerx, rect.centery + 16)))
        if message:
            note = self.ui_font.render(message, True, (255, 204, 112))
            self.screen.blit(note, note.get_rect(center=(SCREEN_WIDTH // 2, 500)))

    def draw_home_screen(self):
        """Draw the launcher shown before the player chooses a game mode."""
        self.screen.fill((25, 20, 16))
        accent = pygame.Rect(0, 0, SCREEN_WIDTH, 8)
        pygame.draw.rect(self.screen, (194, 46, 46), accent)

        title = self.game_font.render("XIANGQI ROBOT", True, (246, 225, 184))
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 190)))
        subtitle = self.ui_font.render("Choose a game mode to begin", True, (228, 214, 190))
        self.screen.blit(subtitle, subtitle.get_rect(center=(SCREEN_WIDTH // 2, 235)))

        pygame.draw.rect(self.screen, (61, 73, 82), HOME_SETTINGS_RECT, border_radius=8)
        settings = self.ui_font.render("SETTINGS", True, (255, 255, 255))
        self.screen.blit(settings, settings.get_rect(center=HOME_SETTINGS_RECT.center))

        pygame.draw.rect(self.screen, (159, 59, 55), HOME_VS_ROBOT_RECT, border_radius=12)
        pygame.draw.rect(self.screen, (239, 218, 177), HOME_VS_ROBOT_RECT, 2, border_radius=12)
        button = self.game_font.render("VS ROBOT", True, (255, 255, 255))
        self.screen.blit(button, button.get_rect(center=(SCREEN_WIDTH // 2, HOME_VS_ROBOT_RECT.centery - 6)))
        detail = self.ui_font.render("Choose the robot difficulty next", True, (255, 224, 205))
        self.screen.blit(detail, detail.get_rect(center=(SCREEN_WIDTH // 2, HOME_VS_ROBOT_RECT.centery + 22)))

        pygame.draw.rect(self.screen, (103, 61, 152), HOME_ROBOT_VS_ROBOT_RECT, border_radius=12)
        pygame.draw.rect(self.screen, (239, 218, 177), HOME_ROBOT_VS_ROBOT_RECT, 2, border_radius=12)
        robot_match = self.ui_font.render("ROBOT VS ROBOT", True, (255, 255, 255))
        self.screen.blit(robot_match, robot_match.get_rect(center=(SCREEN_WIDTH // 2, HOME_ROBOT_VS_ROBOT_RECT.centery - 8)))
        self_play_detail = self.ui_font.render("Physical calibration self-play", True, (238, 220, 250))
        self.screen.blit(self_play_detail, self_play_detail.get_rect(center=(SCREEN_WIDTH // 2, HOME_ROBOT_VS_ROBOT_RECT.centery + 16)))

        hint = self.ui_font.render("Click VS ROBOT or press Enter", True, (190, 181, 166))
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, 465)))

    @staticmethod
    def home_action_from_pixel(px, py):
        if HOME_VS_ROBOT_RECT.collidepoint(px, py):
            return "vs_robot"
        if HOME_SETTINGS_RECT.collidepoint(px, py):
            return "settings"
        if HOME_ROBOT_VS_ROBOT_RECT.collidepoint(px, py):
            return "robot_vs_robot"
        return None

    def draw_self_play_controls(self, controller):
        """Overlay controls for the autonomous physical match."""
        if not controller.active and controller.status.value not in {"faulted", "ended"}:
            return
        end_rect = pygame.Rect(SCREEN_WIDTH - 145, SCREEN_HEIGHT - 58, 125, 40)
        pygame.draw.rect(self.screen, (180, 50, 50), end_rect, border_radius=8)
        end = self.ui_font.render("END MATCH", True, (255, 255, 255))
        self.screen.blit(end, end.get_rect(center=end_rect.center))
        if controller.accepts_next:
            next_rect = pygame.Rect(20, SCREEN_HEIGHT - 58, 125, 40)
            pygame.draw.rect(self.screen, (50, 150, 200), next_rect, border_radius=8)
            nxt = self.ui_font.render("NEXT MOVE", True, (255, 255, 255))
            self.screen.blit(nxt, nxt.get_rect(center=next_rect.center))
        if controller.status.value == "ready":
            toggle_rect = pygame.Rect(SCREEN_WIDTH // 2 - 90, SCREEN_HEIGHT - 58, 180, 40)
            pygame.draw.rect(self.screen, (103, 61, 152), toggle_rect, border_radius=8)
            target = "CONTINUOUS" if controller.run_mode == "step" else "STEP MODE"
            toggle = self.ui_font.render(target, True, (255, 255, 255))
            self.screen.blit(toggle, toggle.get_rect(center=toggle_rect.center))
        mode = self.ui_font.render(f"SELF-PLAY: {controller.status.value.upper()} | {controller.run_mode.upper()}", True, (30, 30, 100))
        self.screen.blit(mode, (12, 34))
        return end_rect

    def draw_settings_menu(self, debug_enabled):
        """Draw the pre-game settings restored from the previous menu flow."""
        self.screen.fill((25, 20, 16))
        pygame.draw.rect(self.screen, (61, 73, 82), SETTINGS_BACK_RECT, border_radius=8)
        back = self.ui_font.render("< HOME", True, (255, 255, 255))
        self.screen.blit(back, back.get_rect(center=SETTINGS_BACK_RECT.center))

        title = self.game_font.render("SETTINGS", True, (246, 225, 184))
        self.screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, 118)))
        label = self.ui_font.render("Debug dashboard", True, (235, 224, 205))
        self.screen.blit(label, label.get_rect(midleft=(126, DEBUG_STATUS_RECT.centery)))

        status = "ENABLED" if debug_enabled else "DISABLED"
        color = (62, 129, 91) if debug_enabled else (159, 59, 55)
        pygame.draw.rect(self.screen, color, DEBUG_STATUS_RECT, border_radius=10)
        status_text = self.ui_font.render(status, True, (255, 255, 255))
        self.screen.blit(status_text, status_text.get_rect(center=DEBUG_STATUS_RECT.center))

        note = self.ui_font.render("Opens a separate read-only robot telemetry window", True, (190, 181, 166))
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
        """Vẽ thông báo kết thúc game."""
        msg = "AI WINS (SAVED)" if winner == "b" else "YOU WIN (NOT SAVED)"
        color = (0, 255, 0) if winner == "b" else (255, 0, 0)
        txt = self.game_font.render(msg, True, color)
        self.screen.blit(txt, txt.get_rect(center=(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2)))
