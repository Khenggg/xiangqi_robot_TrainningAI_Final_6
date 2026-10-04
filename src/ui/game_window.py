"""Fit the fixed game canvas to a resizable, DPI-aware display window."""
import pygame


def fitted_rect(canvas_size, window_size):
    cw, ch = canvas_size
    ww, wh = window_size
    scale = min(ww / cw, wh / ch)
    width = max(1, min(ww, round(cw * scale)))
    height = max(1, min(wh, round(ch * scale)))
    return pygame.Rect((ww - width) // 2, (wh - height) // 2, width, height)


def initial_window_size(canvas_size, desktop_size):
    # Leave room for the title bar, taskbar and desktop DPI scaling.
    available = tuple(max(1, int(value * 0.80)) for value in desktop_size)
    bounded = tuple(min(a, c) for a, c in zip(available, canvas_size))
    return fitted_rect(canvas_size, bounded).size


class GameWindow:
    def __init__(self, canvas_size):
        self.canvas_size = canvas_size
        self.fullscreen = False
        self.windowed_size = initial_window_size(
            canvas_size, pygame.display.get_desktop_sizes()[0])
        self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.canvas = pygame.Surface(canvas_size).convert()
        self.hint_font = pygame.font.SysFont("Segoe UI", 18)

    def toggle_fullscreen(self):
        if self.fullscreen:
            self.display = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        else:
            self.windowed_size = self.display.get_size()
            self.display = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.fullscreen = not self.fullscreen

    def canvas_position(self, position):
        rect = fitted_rect(self.canvas_size, self.display.get_size())
        if not rect.collidepoint(position):
            return None  # Letterbox margins are not game controls.
        return (int((position[0] - rect.x) * self.canvas_size[0] / rect.width),
                int((position[1] - rect.y) * self.canvas_size[1] / rect.height))

    def map_event(self, event):
        """Consume window controls; convert mouse positions to canvas pixels."""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11:
                if not getattr(event, "repeat", False):
                    self.toggle_fullscreen()
                return None
            if event.key == pygame.K_ESCAPE and self.fullscreen:
                self.toggle_fullscreen()
                return None
        if event.type in (pygame.VIDEORESIZE, pygame.WINDOWSIZECHANGED):
            # Pygame 2 updates the display Surface automatically on resize.
            return None
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            position = self.canvas_position(event.pos)
            if position is None:
                return None
            data = dict(event.dict, pos=position)
            if event.type == pygame.MOUSEMOTION:
                rect = fitted_rect(self.canvas_size, self.display.get_size())
                data["rel"] = (event.rel[0] * self.canvas_size[0] / rect.width,
                               event.rel[1] * self.canvas_size[1] / rect.height)
            return pygame.event.Event(event.type, data)
        return event

    def present(self):
        hint = self.hint_font.render(
            "F11: Fullscreen / Window   |   Esc: Exit fullscreen   |   Drag window edges to resize",
            True, (33, 48, 43))
        self.canvas.blit(hint, hint.get_rect(midbottom=(self.canvas_size[0] // 2,
                                                       self.canvas_size[1] - 12)))
        rect = fitted_rect(self.canvas_size, self.display.get_size())
        self.display.fill((20, 27, 31))
        pygame.transform.smoothscale(self.canvas, rect.size,
                                     self.display.subsurface(rect))
        pygame.display.flip()
