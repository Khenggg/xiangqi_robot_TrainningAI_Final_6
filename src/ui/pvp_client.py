"""Hardware-free Black player. Board updates arrive only from the room host."""
import argparse
import math
import os
import queue
import time

import pygame

from src.core.pvp_room import LocalRoomClient, ROOM_ALPHABET
from src.ui.board_renderer import (
    BLACK_PIECE_COLOR,
    BOARD_COLOR,
    GOLD_COLOR,
    JADE_DARK,
    LINE_COLOR,
    PIECE_DISPLAY_NAMES,
    RED_PIECE_COLOR,
    piece_symbol_font,
)

# Piece type letters used by the room protocol; the glyph shown on a token comes
# from PIECE_DISPLAY_NAMES so both windows draw the same characters per side.
NAMES = ('K', 'A', 'E', 'N', 'R', 'C', 'P')


def view_cell(cell):
    """Logical board_grid col,row <-> Black view_grid col,row (180 degrees)."""
    return 8-cell[0], 9-cell[1]


class ClientBoard:
    def __init__(self):
        self.session = None
        self.board = None
        self.snapshot = None
        self.seen_at = 0
        self.pending = None
        self.status = 'Enter the room code from the host to join as Black.'

    def receive(self, packet):
        kind = packet.get('type')
        if kind == 'welcome':
            self.session, self.board, self.snapshot, self.pending = packet['session'], None, None, None
        elif kind == 'state' and packet.get('session') == self.session:
            board = packet.get('board')
            if (not isinstance(board, list) or len(board) != 10
                    or any(not isinstance(row, list) or len(row) != 9 for row in board)
                    or any(not isinstance(p, str) or (p != '.' and p not in {s+'_'+t for s in ('r', 'b') for t in NAMES})
                           for row in board for p in row)
                    or packet.get('turn') not in ('r', 'b')
                    or type(packet.get('revision')) is not int or type(packet.get('epoch')) is not int):
                return
            if self.snapshot and (packet['epoch'], packet['revision']) < (self.snapshot['epoch'], self.snapshot['revision']):
                return
            if self.snapshot and (packet['epoch'], packet['revision']) != (self.snapshot['epoch'], self.snapshot['revision']):
                self.pending = None
            self.board, self.snapshot, self.seen_at = [row[:] for row in board], dict(packet), time.monotonic()
            self.status = packet.get('blocked') or packet.get('status') or 'Board synced from the host.'
        elif kind in ('move_result', 'move_finished') and packet.get('request_id') == self.pending:
            self.status = packet.get('reason') or 'Response received'
            if kind == 'move_finished' or not packet.get('accepted'):
                self.pending = None
        elif kind in ('disconnected', 'error', 'rejected'):
            self.board = self.snapshot = None
            self.pending = None
            self.status = packet.get('reason') or 'Disconnected. Reconnect and choose a new move; nothing is resent automatically.'

    def can_move(self, connected):
        s = self.snapshot
        return bool(connected and s and self.board and time.monotonic()-self.seen_at < 2
                    and s['turn'] == 'b' and not s.get('blocked') and not s.get('busy')
                    and not s.get('game_over') and self.pending is None)


class ClientApp:
    width, height, grid = 960, 900, 62
    origin = (230, 200)

    def __init__(self, room=None):
        pygame.init()
        pygame.display.set_caption('Xiangqi — Black player (host-driven robot)')
        self.screen = pygame.display.set_mode((self.width, self.height))
        self.background = self._load_background()
        self.font = pygame.font.SysFont('segoeui', 21)
        self.small = pygame.font.SysFont('segoeui', 18)
        self.piece_font = piece_symbol_font(27)
        self.model = ClientBoard()
        self.client = None
        self.code = room or ''
        self.selected = None
        self.join_rect = pygame.Rect(650, 35, 250, 48)
        self.code_rect = pygame.Rect(220, 35, 400, 48)
        if room:
            self.join()

    def _load_background(self):
        """Reuse the Ink & Jade art from the main window so both boards match."""
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, "assets", "ui", "ink-jade-landscape-1440x1080.png")
        try:
            image = pygame.image.load(path)
            return pygame.transform.smoothscale(image, (self.width, self.height))
        except (pygame.error, OSError):
            return None

    def join(self):
        if self.client:
            self.client.close()
        self.selected = None
        self.model.receive(dict(type='disconnected'))
        try:
            self.client = LocalRoomClient(self.code.strip().upper())
            self.model.status = 'Connecting...'
        except ValueError as exc:
            self.client = None
            self.model.status = str(exc)

    def pixel_cell(self, pixel):
        col = round((pixel[0]-self.origin[0])/self.grid)
        row = round((pixel[1]-self.origin[1])/self.grid)
        if (0 <= col < 9 and 0 <= row < 10
                and math.hypot(pixel[0]-self.origin[0]-col*self.grid,
                               pixel[1]-self.origin[1]-row*self.grid) <= self.grid*.48):
            return view_cell((col, row))
        return None

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self.join()
            elif event.key == pygame.K_BACKSPACE:
                self.code = self.code[:-1]
            elif event.unicode.upper() in ROOM_ALPHABET and len(event.unicode) == 1 and len(self.code) < 6:
                self.code += event.unicode.upper()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.join_rect.collidepoint(event.pos):
                self.join()
                return True
            cell = self.pixel_cell(event.pos)
            if cell is not None and self.client and self.model.can_move(self.client.connected):
                col, row = cell
                if self.model.board[row][col].startswith('b'):
                    self.selected = cell
                elif self.selected is not None:
                    s = self.model.snapshot
                    request = self.client.send_move(self.selected, cell, s['revision'], s['epoch'])
                    if request:
                        self.model.pending = request
                        self.model.status = 'Sent; waiting for the robot and host to confirm. Do not send again.'
                    self.selected = None
        return True

    def poll(self):
        if self.client:
            for _ in range(64):
                try:
                    packet = self.client.events.get_nowait()
                except queue.Empty:
                    break
                before = (self.model.session, (self.model.snapshot or {}).get('epoch'),
                          (self.model.snapshot or {}).get('revision'))
                self.model.receive(packet)
                after = (self.model.session, (self.model.snapshot or {}).get('epoch'),
                         (self.model.snapshot or {}).get('revision'))
                if before != after or packet.get('type') in ('disconnected', 'error') or not self.model.can_move(self.client.connected):
                    self.selected = None

    def draw(self):
        if self.background is not None:
            self.screen.blit(self.background, (0, 0))
        else:
            self.screen.fill(BOARD_COLOR)
        def label(text, pos, color=(29, 67, 58), font=None):
            self.screen.blit((font or self.font).render(text, True, color), pos)
        pygame.draw.rect(self.screen, (255,255,255), self.code_rect, border_radius=6)
        pygame.draw.rect(self.screen, JADE_DARK, self.join_rect, border_radius=6)
        label('Room code: '+self.code, (230,46))
        label('CONNECT / RECONNECT', (665,46), (255,255,255), self.small)
        intro_strip = pygame.Surface((720, 30), pygame.SRCALPHA)
        intro_strip.fill((248, 238, 211, 215))
        self.screen.blit(intro_strip, (144, 92))
        label('You: BLACK — pick a piece, then a destination. The host drives the robot.', (150, 96))
        x, y = self.origin
        board_w, board_h = self.grid * 8, self.grid * 9
        # Same parchment tray and jade/gold frame as the host window.
        # Wider top/left bands so the file letters and rank numbers clear the tokens.
        tray = pygame.Rect(x - 52, y - 56, board_w + 52 + 34, board_h + 56 + 34)
        pygame.draw.rect(self.screen, GOLD_COLOR, tray.inflate(12, 12), border_radius=18)
        parchment = pygame.Surface(tray.size, pygame.SRCALPHA)
        parchment.fill((248, 238, 211, 222))
        self.screen.blit(parchment, tray.topleft)
        pygame.draw.rect(self.screen, JADE_DARK, tray, width=3, border_radius=14)
        pygame.draw.rect(self.screen, GOLD_COLOR, tray.inflate(-14, -14), width=2, border_radius=9)
        for col in range(9):
            if col in (0,8):
                pygame.draw.line(self.screen, LINE_COLOR, (x+col*self.grid,y), (x+col*self.grid,y+9*self.grid), 2)
            else:
                pygame.draw.line(self.screen, LINE_COLOR, (x+col*self.grid,y), (x+col*self.grid,y+4*self.grid), 2)
                pygame.draw.line(self.screen, LINE_COLOR, (x+col*self.grid,y+5*self.grid), (x+col*self.grid,y+9*self.grid), 2)
            label(chr(ord('a')+8-col), (x+col*self.grid-5,y-46), font=self.small)
        for row in range(10):
            pygame.draw.line(self.screen, LINE_COLOR, (x,y+row*self.grid), (x+8*self.grid,y+row*self.grid), 2)
            label(str(9-row), (x-44,y+row*self.grid-10), font=self.small)
        for start in (0,7):
            for a,b in ((3,5),(5,3)):
                pygame.draw.line(self.screen, LINE_COLOR, (x+a*self.grid,y+start*self.grid),
                                 (x+b*self.grid,y+(start+2)*self.grid), 2)
        if self.model.snapshot:
            side = 'Red' if self.model.snapshot['turn'] == 'r' else 'Black'
            label('Turn: '+side, (30,180), font=self.small)
            if self.model.snapshot.get('busy'):
                label('Robot moving', (30,210), font=self.small)
        for row in range(10):
            for col in range(9):
                if not self.model.board:
                    continue
                piece = self.model.board[row][col]
                if piece == '.':
                    continue
                vc, vr = view_cell((col,row))
                center = (x+vc*self.grid, y+vr*self.grid)
                pygame.draw.circle(self.screen, (255,250,232), center, 26)
                color = RED_PIECE_COLOR if piece.startswith('r') else BLACK_PIECE_COLOR
                pygame.draw.circle(self.screen, color, center, 26, 2)
                glyph = PIECE_DISPLAY_NAMES.get(f'{piece[0]}_{piece[-1]}', '?')
                text = self.piece_font.render(glyph, True, color)
                self.screen.blit(text, text.get_rect(center=center))
                if self.selected == (col,row):
                    pygame.draw.circle(self.screen, (34,146,110), center, 30, 3)
        stale = self.model.snapshot and time.monotonic()-self.model.seen_at >= 2
        message = 'Host state is stale; move selection is locked.' if stale else self.model.status
        # Fit status without drawing over the board or outside the window.
        words, lines, line = str(message).split(), [], ''
        for word in words:
            candidate = (line+' '+word).strip()
            if self.small.size(candidate)[0] > 880 and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
        strip = pygame.Surface((880, 22 * min(len(lines), 2) + 12), pygame.SRCALPHA)
        strip.fill((248, 238, 211, 210))
        self.screen.blit(strip, (32, 840))
        for index, text in enumerate(lines[:2]):
            label(text, (40, 846 + index * 22), font=self.small)
        pygame.display.flip()

    def close(self):
        if self.client:
            self.client.close()
        pygame.quit()

    def run(self):
        clock = pygame.time.Clock()
        try:
            running = True
            while running:
                for event in pygame.event.get():
                    running = self.handle_event(event) and running
                self.poll()
                self.draw()
                clock.tick(30)
        finally:
            self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--room')
    ClientApp(parser.parse_args().room).run()


if __name__ == '__main__':
    main()
