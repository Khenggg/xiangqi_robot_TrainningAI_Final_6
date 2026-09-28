# =============================================================================
# === FILE: board_renderer.py ===
# === Giao diện Bàn cờ Tướng & Bảng điều khiển chuyên nghiệp (ZingPlay / Xiangqi.com style) ===
# =============================================================================
import time
import math
import pygame
from typing import Dict, Tuple, List, Optional, Any
from src.core import xiangqi

# ==========================================
# 1. HẰNG SỐ KÍCH THƯỚC & TỌA ĐỘ BỐ CỤC
# ==========================================
SCREEN_WIDTH = 1040
SCREEN_HEIGHT = 640

NUM_COLS = xiangqi.NUM_COLS  # 9
NUM_ROWS = xiangqi.NUM_ROWS  # 10

# Bàn cờ (Bên trái)
SQUARE_SIZE = 52
START_X = 60
START_Y = 86
BOARD_GRID_WIDTH = (NUM_COLS - 1) * SQUARE_SIZE   # 8 * 52 = 416
BOARD_GRID_HEIGHT = (NUM_ROWS - 1) * SQUARE_SIZE  # 9 * 52 = 468
BOARD_BG_RECT = pygame.Rect(22, 46, 492, 548)
PIECE_RADIUS = 23

# Bảng điều khiển Sidebar (Bên phải)
PANEL_X = 534
PANEL_Y = 16
PANEL_WIDTH = 484
PANEL_HEIGHT = 608
PANEL_RECT = pygame.Rect(PANEL_X, PANEL_Y, PANEL_WIDTH, PANEL_HEIGHT)

# Nút tăng giảm nấc ELO (nằm ngang hàng với tiêu đề ELO, về phía bên phải)
BTN_ELO_PREV_RECT = pygame.Rect(PANEL_X + PANEL_WIDTH - 146, 138, 60, 24)
BTN_ELO_NEXT_RECT = pygame.Rect(PANEL_X + PANEL_WIDTH - 80, 138, 60, 24)

# Bảng nút chọn ELO 8 nấc (Lưới 4x2)
ELO_BUTTONS = [800, 1100, 1400, 1700, 2000, 2300, 2600, 3000]
ELO_LABELS = {
    800: "800 Tập sự",
    1100: "1100 Nhập môn",
    1400: "1400 Quán cóc",
    1700: "1700 CLB",
    2000: "2000 Tỉnh",
    2300: "2300 Kiện tướng",
    2600: "2600 Đại KT",
    3000: "3000 Max AI",
}

ELO_BUTTON_RECTS: Dict[int, pygame.Rect] = {}
_elo_start_y = 168
for i, elo in enumerate(ELO_BUTTONS):
    col = i % 4
    row = i // 4
    bx = PANEL_X + 16 + col * 114
    by = _elo_start_y + row * 34
    ELO_BUTTON_RECTS[elo] = pygame.Rect(bx, by, 110, 30)

# Bảng 4 nút chức năng hành động (Hoàn tác, Gợi ý, Ván mới, Xin thua)
BTN_UNDO_RECT = pygame.Rect(PANEL_X + 16, 308, 108, 40)
BTN_HINT_RECT = pygame.Rect(PANEL_X + 130, 308, 108, 40)
BTN_NEW_GAME_RECT = pygame.Rect(PANEL_X + 244, 308, 108, 40)
BTN_SURRENDER_RECT = pygame.Rect(PANEL_X + 358, 308, 108, 40)

# Bảng ký tự quân cờ thư pháp truyền thống
PIECE_DISPLAY_NAMES = {
    "r_K": "帥", "r_A": "仕", "r_E": "相", "r_R": "俥",
    "r_N": "傌", "r_C": "炮", "r_P": "兵",
    "b_K": "將", "b_A": "士", "b_E": "象", "b_R": "車",
    "b_N": "馬", "b_C": "砲", "b_P": "卒",
}

# Bảng màu sắc đồ họa
COLOR_BG = (17, 24, 39)                 # Nền app xám tối cao cấp
COLOR_BOARD_WOOD = (243, 222, 187)      # Màu vân gỗ mặt bàn cờ
COLOR_BOARD_BORDER = (107, 68, 35)      # Màu viền gỗ ngoài
COLOR_BOARD_LINE = (92, 58, 33)         # Màu chỉ mực bàn cờ
COLOR_RIVER_TEXT = (180, 142, 105)      # Chữ Sở Hà Hán Giới

COLOR_PANEL_BG = (27, 36, 50)           # Nền bảng điều khiển
COLOR_PANEL_BORDER = (45, 58, 78)       # Viền bảng điều khiển
COLOR_CARD_BG = (35, 46, 64)            # Nền thẻ đấu thủ

COLOR_RED_PIECE = (195, 25, 25)         # Màu mực quân Đỏ
COLOR_BLACK_PIECE = (28, 28, 28)        # Màu mực quân Đen
COLOR_PIECE_BG = (255, 249, 238)        # Nền gỗ quân cờ ngà
COLOR_PIECE_RIM = (196, 162, 126)       # Vành gỗ quân cờ

COLOR_GOLD = (245, 158, 11)             # Vàng kim
COLOR_ORANGE = (234, 88, 12)            # Cam rực rỡ
COLOR_GREEN = (34, 197, 94)             # Xanh lá ngọc
COLOR_BLUE = (37, 99, 235)              # Xanh dương
COLOR_RED = (220, 38, 38)               # Đỏ tươi
COLOR_PURPLE = (168, 85, 247)           # Tím gợi ý


class BoardRenderer:
    """Quản lý hiển thị toàn diện giao diện bàn cờ và bảng điều khiển chuyên nghiệp."""

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self._init_fonts()

    def _init_fonts(self):
        """Khởi tạo font hỗ trợ cả tiếng Việt và chữ Hán triện thư."""
        chinese_fonts = ["simsun", "kaiti", "mingliu", "arialunicodems", "microsoftyahei", "simhei"]
        self.piece_font = pygame.font.SysFont(chinese_fonts, 24, bold=True)
        self.river_font = pygame.font.SysFont(chinese_fonts, 20, bold=True)

        ui_fonts = ["segoeui", "arial", "tahoma", "calibri"]
        self.title_font = pygame.font.SysFont(ui_fonts, 20, bold=True)
        self.sub_font = pygame.font.SysFont(ui_fonts, 12)
        self.badge_font = pygame.font.SysFont(ui_fonts, 13, bold=True)
        self.btn_font = pygame.font.SysFont(ui_fonts, 12, bold=True)
        self.log_font = pygame.font.SysFont(ui_fonts, 12)
        self.status_font = pygame.font.SysFont(ui_fonts, 13, bold=True)
        self.big_font = pygame.font.SysFont(ui_fonts, 32, bold=True)

    # --- CHUYỂN ĐỔI TỌA ĐỘ ---
    @staticmethod
    def grid_to_pixel(col: int, row: int) -> Tuple[int, int]:
        return int(START_X + col * SQUARE_SIZE), int(START_Y + row * SQUARE_SIZE)

    @staticmethod
    def pixel_to_grid(px: int, py: int) -> Tuple[int, int]:
        col = int(round((px - START_X) / SQUARE_SIZE))
        row = int(round((py - START_Y) / SQUARE_SIZE))
        return col, row

    # =========================================================================
    # 2. VẼ TOÀN BỘ GIAO DIỆN CHÍNH
    # =========================================================================
    def draw_ui(self, game_state: Dict[str, Any]):
        """Vẽ bàn cờ, các thẻ thông tin người chơi, các nút bấm ELO và thanh hành động."""
        self.screen.fill(COLOR_BG)
        self._draw_board_surface()
        self._draw_sidebar(game_state)

    def _draw_board_surface(self):
        """Vẽ mặt bàn cờ gỗ sang trọng với viền đôi và các đường chỉ cờ."""
        pygame.draw.rect(self.screen, COLOR_BOARD_BORDER, BOARD_BG_RECT, border_radius=12)
        inner_rect = BOARD_BG_RECT.inflate(-10, -10)
        pygame.draw.rect(self.screen, COLOR_BOARD_WOOD, inner_rect, border_radius=8)

        # Khung viền chỉ cờ bao quanh
        outer_grid = pygame.Rect(START_X - 6, START_Y - 6, BOARD_GRID_WIDTH + 12, BOARD_GRID_HEIGHT + 12)
        pygame.draw.rect(self.screen, COLOR_BOARD_LINE, outer_grid, width=2)

        # Các đường ngang (10 đường)
        for r in range(NUM_ROWS):
            p1 = self.grid_to_pixel(0, r)
            p2 = self.grid_to_pixel(NUM_COLS - 1, r)
            pygame.draw.line(self.screen, COLOR_BOARD_LINE, p1, p2, 1)

        # Các đường dọc (9 đường, ngắt ở sông)
        for c in range(NUM_COLS):
            if c in (0, NUM_COLS - 1):
                p1 = self.grid_to_pixel(c, 0)
                p2 = self.grid_to_pixel(c, NUM_ROWS - 1)
                pygame.draw.line(self.screen, COLOR_BOARD_LINE, p1, p2, 1)
            else:
                pygame.draw.line(self.screen, COLOR_BOARD_LINE,
                                 self.grid_to_pixel(c, 0), self.grid_to_pixel(c, 4), 1)
                pygame.draw.line(self.screen, COLOR_BOARD_LINE,
                                 self.grid_to_pixel(c, 5), self.grid_to_pixel(c, 9), 1)

        # Cung tướng (Cửu cung) Đen và Đỏ
        pygame.draw.line(self.screen, COLOR_BOARD_LINE, self.grid_to_pixel(3, 0), self.grid_to_pixel(5, 2), 1)
        pygame.draw.line(self.screen, COLOR_BOARD_LINE, self.grid_to_pixel(5, 0), self.grid_to_pixel(3, 2), 1)
        pygame.draw.line(self.screen, COLOR_BOARD_LINE, self.grid_to_pixel(3, 7), self.grid_to_pixel(5, 9), 1)
        pygame.draw.line(self.screen, COLOR_BOARD_LINE, self.grid_to_pixel(5, 7), self.grid_to_pixel(3, 9), 1)

        # Dòng sông (Sở Hà - Hán Giới)
        txt_so_ha = self.river_font.render("楚  河", True, COLOR_RIVER_TEXT)
        txt_han_gioi = self.river_font.render("漢  界", True, COLOR_RIVER_TEXT)
        cy_river = int((self.grid_to_pixel(0, 4)[1] + self.grid_to_pixel(0, 5)[1]) / 2)
        cx_left = int(START_X + 1.5 * SQUARE_SIZE)
        cx_right = int(START_X + 6.5 * SQUARE_SIZE)
        self.screen.blit(txt_so_ha, txt_so_ha.get_rect(center=(cx_left, cy_river)))
        self.screen.blit(txt_han_gioi, txt_han_gioi.get_rect(center=(cx_right, cy_river)))

        # Dấu chữ thập định vị Pháo và Tốt truyền thống
        cross_cells = [
            (1, 2), (7, 2),  # Pháo đen
            (0, 3), (2, 3), (4, 3), (6, 3), (8, 3),  # Tốt đen
            (1, 7), (7, 7),  # Pháo đỏ
            (0, 6), (2, 6), (4, 6), (6, 6), (8, 6),  # Tốt đỏ
        ]
        for c, r in cross_cells:
            self._draw_star_point(c, r)

    def _draw_star_point(self, col: int, row: int):
        """Vẽ góc căn vị trí quân cờ truyền thống."""
        cx, cy = self.grid_to_pixel(col, row)
        d = 4
        gap = 3
        if col > 0:
            pygame.draw.line(self.screen, COLOR_BOARD_LINE, (cx - gap, cy - gap), (cx - gap - d, cy - gap), 1)
            pygame.draw.line(self.screen, COLOR_BOARD_LINE, (cx - gap, cy - gap), (cx - gap, cy - gap - d), 1)
            pygame.draw.line(self.screen, COLOR_BOARD_LINE, (cx - gap, cy + gap), (cx - gap - d, cy + gap), 1)
            pygame.draw.line(self.screen, COLOR_BOARD_LINE, (cx - gap, cy + gap), (cx - gap, cy + gap + d), 1)
        if col < NUM_COLS - 1:
            pygame.draw.line(self.screen, COLOR_BOARD_LINE, (cx + gap, cy - gap), (cx + gap + d, cy - gap), 1)
            pygame.draw.line(self.screen, COLOR_BOARD_LINE, (cx + gap, cy - gap), (cx + gap, cy - gap - d), 1)
            pygame.draw.line(self.screen, COLOR_BOARD_LINE, (cx + gap, cy + gap), (cx + gap + d, cy + gap), 1)
            pygame.draw.line(self.screen, COLOR_BOARD_LINE, (cx + gap, cy + gap), (cx + gap, cy + gap + d), 1)

    # =========================================================================
    # 3. SIDEBAR BẢNG ĐIỀU KHIỂN CHUYÊN NGHIỆP (ĐÃ CĂN CHỈNH TỌA ĐỘ CHUẨN XÁC)
    # =========================================================================
    def _draw_sidebar(self, game_state: Dict[str, Any]):
        """Vẽ Sidebar với layout phân tầng rõ ràng, tuyệt đối không chồng lấn."""
        # 1. Nền Panel chính
        pygame.draw.rect(self.screen, COLOR_PANEL_BG, PANEL_RECT, border_radius=12)
        pygame.draw.rect(self.screen, COLOR_PANEL_BORDER, PANEL_RECT, width=2, border_radius=12)

        # Header Title (Y: 28 -> 60)
        title = self.title_font.render("XIANGQI ROBOT PRO", True, COLOR_GOLD)
        self.screen.blit(title, (PANEL_X + 18, 28))

        mode_str = "MÔ PHỎNG (DRY RUN)" if game_state.get("allow_mouse") else "CAMERA THỰC TẾ"
        sub = self.sub_font.render(f"Pikafish NNUE AI  •  Chế độ: {mode_str}", True, (156, 163, 175))
        self.screen.blit(sub, (PANEL_X + 18, 52))

        # -------------------------------------------------------------
        # KHỐI 1: THẺ ĐỐI THỦ AI (PIKAFISH) (Y: 72 -> 126, Cao 54)
        # -------------------------------------------------------------
        ai_card_rect = pygame.Rect(PANEL_X + 16, 72, PANEL_WIDTH - 32, 54)
        is_ai_turn = game_state.get("turn") == "b"
        card_border = COLOR_GOLD if is_ai_turn else COLOR_PANEL_BORDER
        pygame.draw.rect(self.screen, COLOR_CARD_BG, ai_card_rect, border_radius=8)
        pygame.draw.rect(self.screen, card_border, ai_card_rect, width=2 if is_ai_turn else 1, border_radius=8)

        ai_name = self.badge_font.render("[AI] Pikafish NNUE", True, (255, 255, 255))
        self.screen.blit(ai_name, (PANEL_X + 28, 80))

        # Badge ELO
        current_elo = game_state.get("ai_elo", 1400)
        elo_title = game_state.get("ai_elo_title", f"ELO {current_elo}")
        elo_badge_surf = self.badge_font.render(f" {elo_title} ", True, (255, 255, 255))
        elo_badge_rect = elo_badge_surf.get_rect(topright=(PANEL_X + PANEL_WIDTH - 28, 80))
        badge_bg = elo_badge_rect.inflate(8, 4)
        pygame.draw.rect(self.screen, COLOR_ORANGE, badge_bg, border_radius=6)
        self.screen.blit(elo_badge_surf, elo_badge_rect)

        # Trạng thái suy nghĩ AI
        if game_state.get("ai_thinking"):
            start = game_state.get("ai_think_start", time.time())
            elapsed = time.time() - start
            dots = "." * (int(elapsed * 2) % 4)
            ai_stat = self.sub_font.render(f"Đang tính toán nước đi{dots} ({elapsed:.1f}s)", True, (52, 211, 153))
        else:
            ai_stat_text = "Đang đến lượt AI..." if is_ai_turn else "Đợi lượt bạn đi..."
            ai_stat = self.sub_font.render(ai_stat_text, True, (156, 163, 175))
        self.screen.blit(ai_stat, (PANEL_X + 28, 102))

        # -------------------------------------------------------------
        # KHỐI 2: BỘ CHỌN ĐỘ KHÓ ELO (Y: 138 -> 232)
        # Tiêu đề bên trái, nút < Giảm và Tăng > bên phải (KHÔNG CHỒNG NHAU)
        # -------------------------------------------------------------
        lbl_elo = self.badge_font.render("ĐỘ KHÓ AI (ELO)", True, COLOR_GOLD)
        self.screen.blit(lbl_elo, (PANEL_X + 18, 142))

        # Nút giảm ELO [< Giảm] và tăng ELO [Tăng >] nằm bên phải
        pygame.draw.rect(self.screen, (45, 55, 75), BTN_ELO_PREV_RECT, border_radius=5)
        pygame.draw.rect(self.screen, COLOR_PANEL_BORDER, BTN_ELO_PREV_RECT, width=1, border_radius=5)
        txt_prev = self.btn_font.render("< Giảm", True, (209, 213, 219))
        self.screen.blit(txt_prev, txt_prev.get_rect(center=BTN_ELO_PREV_RECT.center))

        pygame.draw.rect(self.screen, (45, 55, 75), BTN_ELO_NEXT_RECT, border_radius=5)
        pygame.draw.rect(self.screen, COLOR_PANEL_BORDER, BTN_ELO_NEXT_RECT, width=1, border_radius=5)
        txt_next = self.btn_font.render("Tăng >", True, (209, 213, 219))
        self.screen.blit(txt_next, txt_next.get_rect(center=BTN_ELO_NEXT_RECT.center))

        # Vẽ 8 nút ELO (Lưới 4 cột x 2 hàng: Y = 168 và Y = 202)
        for elo_val, b_rect in ELO_BUTTON_RECTS.items():
            is_active = (current_elo == elo_val)
            bg_c = COLOR_ORANGE if is_active else (38, 48, 65)
            border_c = COLOR_GOLD if is_active else (55, 68, 90)
            text_c = (255, 255, 255) if is_active else (209, 213, 219)

            pygame.draw.rect(self.screen, bg_c, b_rect, border_radius=6)
            pygame.draw.rect(self.screen, border_c, b_rect, width=2 if is_active else 1, border_radius=6)

            txt_btn = self.btn_font.render(ELO_LABELS[elo_val], True, text_c)
            self.screen.blit(txt_btn, txt_btn.get_rect(center=b_rect.center))

        # -------------------------------------------------------------
        # KHỐI 3: THẺ NGƯỜI CHƠI (BẠN - ĐỎ) (Y: 244 -> 296, Cao 52)
        # -------------------------------------------------------------
        player_card_rect = pygame.Rect(PANEL_X + 16, 244, PANEL_WIDTH - 32, 52)
        is_my_turn = (game_state.get("turn") == "r" and not game_state.get("game_over"))
        p_border = COLOR_GREEN if is_my_turn else COLOR_PANEL_BORDER
        pygame.draw.rect(self.screen, COLOR_CARD_BG, player_card_rect, border_radius=8)
        pygame.draw.rect(self.screen, p_border, player_card_rect, width=2 if is_my_turn else 1, border_radius=8)

        p_name = self.badge_font.render("[Người chơi] Bạn (Tiên thủ Đỏ)", True, (255, 255, 255))
        self.screen.blit(p_name, (PANEL_X + 28, 252))

        if is_my_turn:
            turn_msg = "LƯỢT CỦA BẠN (Click quân cờ để đi)"
            turn_col = COLOR_GREEN
        else:
            turn_msg = "Đang đợi AI đi nước..."
            turn_col = (156, 163, 175)
        txt_turn = self.sub_font.render(turn_msg, True, turn_col)
        self.screen.blit(txt_turn, (PANEL_X + 28, 274))

        # -------------------------------------------------------------
        # KHỐI 4: 4 NÚT HÀNH ĐỘNG CHUẨN APP CỜ (Y: 308 -> 348, Cao 40)
        # NẰM HOÀN TOÀN TÁCH BIỆT PHÍA DƯỚI THẺ NGƯỜI CHƠI
        # -------------------------------------------------------------
        buttons_config = [
            (BTN_UNDO_RECT, COLOR_BLUE, "Hoàn tác (U)"),
            (BTN_HINT_RECT, COLOR_GOLD, "Gợi ý (H)"),
            (BTN_NEW_GAME_RECT, COLOR_GREEN, "Ván mới (N)"),
            (BTN_SURRENDER_RECT, COLOR_RED, "Xin thua"),
        ]
        for b_rect, color, label in buttons_config:
            pygame.draw.rect(self.screen, color, b_rect, border_radius=8)
            pygame.draw.rect(self.screen, (255, 255, 255, 80), b_rect, width=1, border_radius=8)
            b_txt = self.btn_font.render(label, True, (255, 255, 255))
            self.screen.blit(b_txt, b_txt.get_rect(center=b_rect.center))

        # -------------------------------------------------------------
        # KHỐI 5: BẢNG LỊCH SỬ NƯỚC ĐI (Y: 362 -> 552)
        # -------------------------------------------------------------
        lbl_hist = self.badge_font.render("LỊCH SỬ NƯỚC CỜ", True, (209, 213, 219))
        self.screen.blit(lbl_hist, (PANEL_X + 18, 362))

        log_rect = pygame.Rect(PANEL_X + 16, 384, PANEL_WIDTH - 32, 166)
        pygame.draw.rect(self.screen, (17, 24, 39), log_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLOR_PANEL_BORDER, log_rect, width=1, border_radius=8)

        history = game_state.get("move_history", [])
        if not history:
            no_move_txt = self.sub_font.render("Chưa có nước cờ nào. Hãy chọn quân Đỏ để bắt đầu!", True, (107, 114, 128))
            self.screen.blit(no_move_txt, (PANEL_X + 26, 396))
        else:
            display_moves = history[-7:]
            for idx, m in enumerate(display_moves):
                turn_str = "Đỏ" if m.get("turn") == "r" else "Đen"
                s = m.get("src")
                d = m.get("dst")
                move_txt = f"{idx+1}. {turn_str}: ({s[0]},{s[1]}) -> ({d[0]},{d[1]})"
                t_surf = self.log_font.render(move_txt, True, (229, 231, 235))
                self.screen.blit(t_surf, (PANEL_X + 26, 394 + idx * 22))

        # -------------------------------------------------------------
        # KHỐI 6: THANH THÔNG BÁO / MẸO CHƠI (Y: 562 -> 598, Cao 36)
        # -------------------------------------------------------------
        status_rect = pygame.Rect(PANEL_X + 16, 562, PANEL_WIDTH - 32, 36)
        pygame.draw.rect(self.screen, (22, 29, 41), status_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLOR_PANEL_BORDER, status_rect, width=1, border_radius=8)

        msg = game_state.get("status_message", "")
        if msg and time.time() < game_state.get("status_expiry", 0):
            msg_color = game_state.get("status_color", COLOR_GOLD)
            msg_surf = self.status_font.render(msg, True, msg_color)
            self.screen.blit(msg_surf, msg_surf.get_rect(center=status_rect.center))
        else:
            hint_default = self.sub_font.render("Mẹo: Bấm quân cờ để xem gợi ý các ô đi hợp lệ!", True, (156, 163, 175))
            self.screen.blit(hint_default, hint_default.get_rect(center=status_rect.center))

    # =========================================================================
    # 4. VẼ QUÂN CỜ TRUYỀN THỐNG (AUTHENTIC CHINESE CHESS TOKENS)
    # =========================================================================
    def draw_pieces(self, board: List[List[str]]):
        """Vẽ toàn bộ quân cờ nổi 3D với vành gỗ ngà và chữ Hán thư pháp."""
        for r in range(NUM_ROWS):
            for c in range(NUM_COLS):
                name = board[r][c]
                if name == ".":
                    continue
                cx, cy = self.grid_to_pixel(c, r)

                # Đổ bóng quân cờ
                pygame.draw.circle(self.screen, (40, 25, 15, 90), (cx + 2, cy + 3), PIECE_RADIUS)
                # Thân gỗ quân cờ
                pygame.draw.circle(self.screen, COLOR_PIECE_BG, (cx, cy), PIECE_RADIUS)
                # Vành gỗ ngoài
                pygame.draw.circle(self.screen, COLOR_PIECE_RIM, (cx, cy), PIECE_RADIUS, 2)
                # Vành chỉ tròn trong
                pygame.draw.circle(self.screen, (225, 200, 165), (cx, cy), PIECE_RADIUS - 3, 1)

                # Ký tự thư pháp
                is_red = name.startswith("r")
                color = COLOR_RED_PIECE if is_red else COLOR_BLACK_PIECE
                char_str = PIECE_DISPLAY_NAMES.get(name, "?")
                text_surf = self.piece_font.render(char_str, True, color)
                self.screen.blit(text_surf, text_surf.get_rect(center=(cx, cy - 1)))

    # =========================================================================
    # 5. VẼ HIGHLIGHT & CHẤM TRÒN GỢI Ý NƯỚC ĐI (LEGAL MOVE DOTS)
    # =========================================================================
    def draw_highlight(
        self,
        last_move: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None,
        selected_pos: Optional[Tuple[int, int]] = None,
        invalid_flash_pos: Optional[Tuple[int, int]] = None,
        invalid_flash_expiry: float = 0.0,
        legal_moves: Optional[List[Tuple[int, int]]] = None,
        board: Optional[List[List[str]]] = None,
        is_check: bool = False,
        turn: str = "r",
        hint_move: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None,
    ):
        """Vẽ các chỉ dấu thị giác: ô chọn, chấm gợi ý đi được, nước đi trước, chiếu tướng."""
        # 1. Nước đi gần nhất (Last Move): Vẽ 4 góc L màu vàng kim ở ô xuất phát và ô đến
        if last_move:
            s, d = last_move
            self._draw_corner_brackets(s[0], s[1], COLOR_GOLD)
            self._draw_corner_brackets(d[0], d[1], COLOR_GOLD)

        # 2. Quân cờ đang được chọn: Viền phát sáng màu vàng cam
        if selected_pos:
            sc, sr = selected_pos
            cx, cy = self.grid_to_pixel(sc, sr)
            pygame.draw.circle(self.screen, COLOR_GOLD, (cx, cy), PIECE_RADIUS + 4, 3)

        # 3. GỢI Ý CÁC Ô ĐI HỢP LỆ (LEGAL MOVE MARKERS)
        if selected_pos and legal_moves:
            for dc, dr in legal_moves:
                px, py = self.grid_to_pixel(dc, dr)
                is_capture = (board is not None and board[dr][dc] != ".")
                if is_capture:
                    # Vòng tròn đỏ nhắm bắn quân địch
                    pygame.draw.circle(self.screen, COLOR_RED, (px, py), PIECE_RADIUS + 3, 3)
                    d_len = 6
                    pygame.draw.line(self.screen, COLOR_RED, (px - PIECE_RADIUS - 4, py), (px - PIECE_RADIUS + d_len, py), 2)
                    pygame.draw.line(self.screen, COLOR_RED, (px + PIECE_RADIUS + 4, py), (px + PIECE_RADIUS - d_len, py), 2)
                    pygame.draw.line(self.screen, COLOR_RED, (px, py - PIECE_RADIUS - 4), (px, py - PIECE_RADIUS + d_len), 2)
                    pygame.draw.line(self.screen, COLOR_RED, (px, py + PIECE_RADIUS + 4), (px, py + PIECE_RADIUS - d_len), 2)
                else:
                    # Chấm tròn xanh ngọc trên ô trống
                    pygame.draw.circle(self.screen, COLOR_GREEN, (px, py), 7)
                    pygame.draw.circle(self.screen, (255, 255, 255), (px, py), 8, 1)

        # 4. Gợi ý nước đi từ AI (Hint Move): Viền tím phát sáng
        if hint_move:
            hs, hd = hint_move
            self._draw_corner_brackets(hs[0], hs[1], COLOR_PURPLE)
            self._draw_corner_brackets(hd[0], hd[1], COLOR_PURPLE)
            p1 = self.grid_to_pixel(hs[0], hs[1])
            p2 = self.grid_to_pixel(hd[0], hd[1])
            pygame.draw.line(self.screen, COLOR_PURPLE, p1, p2, 3)

        # 5. Chiếu tướng (Check Alert): Vòng đỏ nhấp nháy quanh Tướng + Badge "CHIẾU TƯỚNG"
        if is_check and board:
            king_pos = xiangqi.get_king_pos(turn, board)
            if king_pos:
                kx, ky = self.grid_to_pixel(king_pos[0], king_pos[1])
                pulse = int(180 + 75 * math.sin(time.time() * 8))
                pygame.draw.circle(self.screen, (pulse, 0, 0), (kx, ky), PIECE_RADIUS + 6, 4)

                # Badge "CHIẾU TƯỚNG" nổi bật
                badge_text = "CHIẾU TƯỚNG!"
                b_surf = self.badge_font.render(badge_text, True, (255, 255, 255))
                bw, bh = b_surf.get_width() + 14, b_surf.get_height() + 6
                # Nếu tướng ở hàng trên thì badge đặt phía dưới, nếu ở hàng dưới thì badge đặt phía trên
                by = (ky + PIECE_RADIUS + 6) if ky < 200 else (ky - PIECE_RADIUS - bh - 6)
                bx = kx - bw // 2
                badge_rect = pygame.Rect(bx, by, bw, bh)
                pygame.draw.rect(self.screen, (185, 28, 28), badge_rect, border_radius=6)
                pygame.draw.rect(self.screen, (254, 202, 202), badge_rect, width=1, border_radius=6)
                self.screen.blit(b_surf, b_surf.get_rect(center=badge_rect.center))

        # 6. Invalid Move Flash (Báo đỏ ô không hợp lệ)
        if invalid_flash_pos and time.time() < invalid_flash_expiry:
            fc, fr = invalid_flash_pos
            fx, fy = self.grid_to_pixel(fc, fr)
            pygame.draw.circle(self.screen, COLOR_RED, (fx, fy), PIECE_RADIUS + 6, 4)

    def _draw_corner_brackets(self, col: int, row: int, color: Tuple[int, int, int]):
        """Vẽ 4 góc vuông L đặc trưng quanh một ô cờ."""
        cx, cy = self.grid_to_pixel(col, row)
        r = PIECE_RADIUS + 4
        arm = 8
        # Trên trái
        pygame.draw.line(self.screen, color, (cx - r, cy - r), (cx - r + arm, cy - r), 2)
        pygame.draw.line(self.screen, color, (cx - r, cy - r), (cx - r, cy - r + arm), 2)
        # Trên phải
        pygame.draw.line(self.screen, color, (cx + r, cy - r), (cx + r - arm, cy - r), 2)
        pygame.draw.line(self.screen, color, (cx + r, cy - r), (cx + r, cy - r + arm), 2)
        # Dưới trái
        pygame.draw.line(self.screen, color, (cx - r, cy + r), (cx - r + arm, cy + r), 2)
        pygame.draw.line(self.screen, color, (cx - r, cy + r), (cx - r, cy + r - arm), 2)
        # Dưới phải
        pygame.draw.line(self.screen, color, (cx + r, cy + r), (cx + r - arm, cy + r), 2)
        pygame.draw.line(self.screen, color, (cx + r, cy + r), (cx + r, cy + r - arm), 2)

    # =========================================================================
    # 6. HIỂN THỊ KẾT THÚC GAME
    # =========================================================================
    def draw_game_over(self, winner: Optional[str], reason: str = "CHIẾU BÍ"):
        """Vẽ thông báo kết thúc ván cờ với modal backdrop sang trọng chuẩn chess app."""
        # 1. Dimming Backdrop che mờ bàn cờ
        dim_surf = pygame.Surface((536, SCREEN_HEIGHT), pygame.SRCALPHA)
        dim_surf.fill((10, 15, 25, 185))
        self.screen.blit(dim_surf, (0, 0))

        # 2. Modal Box ở trung tâm bàn cờ
        modal_w, modal_h = 420, 160
        modal_x = (536 - modal_w) // 2
        modal_y = (SCREEN_HEIGHT - modal_h) // 2
        modal_rect = pygame.Rect(modal_x, modal_y, modal_w, modal_h)

        pygame.draw.rect(self.screen, (23, 30, 44), modal_rect, border_radius=14)
        is_win = (winner == "r")
        b_color = COLOR_GREEN if is_win else COLOR_RED
        if winner not in ("r", "b"):
            b_color = COLOR_GOLD

        pygame.draw.rect(self.screen, b_color, modal_rect, width=3, border_radius=14)

        # 3. Tiêu đề chính
        if is_win:
            msg_title = "🏆 CHIẾN THẮNG!"
        elif winner == "b":
            msg_title = "💀 BẠN ĐÃ THUA!"
        else:
            msg_title = "🤝 HÒA CỜ!"

        t_surf = self.big_font.render(msg_title, True, b_color)
        self.screen.blit(t_surf, t_surf.get_rect(center=(modal_rect.centerx, modal_rect.top + 34)))

        # 4. Phụ đề nêu rõ nguyên nhân (Chiếu bí / Tuyệt sát / Xin thua)
        if reason:
            if is_win:
                sub_detail = f"Đối thủ đã bị {reason}!"
            elif winner == "b":
                sub_detail = f"Bạn đã bị {reason}!"
            else:
                sub_detail = "Hai bên thỏa thuận hòa cuộc."
        else:
            sub_detail = "Ván đấu đã kết thúc."

        d_surf = self.title_font.render(sub_detail, True, (254, 240, 138))  # Vàng sáng nổi bật
        self.screen.blit(d_surf, d_surf.get_rect(center=(modal_rect.centerx, modal_rect.top + 76)))

        # Đường gạch phân cách
        pygame.draw.line(self.screen, (45, 58, 78), (modal_rect.left + 30, modal_rect.top + 104), (modal_rect.right - 30, modal_rect.top + 104), 1)

        # 5. Hướng dẫn hành động
        guide_msg = "Bấm [Ván mới (N)] để chơi lại  •  [Hoàn tác (U)] để đi lại"
        g_surf = self.sub_font.render(guide_msg, True, (209, 213, 219))
        self.screen.blit(g_surf, g_surf.get_rect(center=(modal_rect.centerx, modal_rect.top + 128)))

