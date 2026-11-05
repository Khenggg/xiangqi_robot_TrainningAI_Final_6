"""One operator decision closes the process without waiting for devices."""
import os

import pygame


def _confirm_without_window():
    import ctypes
    return ctypes.windll.user32.MessageBoxW(
        None, "Bạn có muốn thoát ứng dụng không?", "Thoát ứng dụng", 0x124) == 6


def confirm_exit():
    """Return True only for the explicit Exit button or Enter/Y."""
    if pygame.display.get_surface() is None:
        return _confirm_without_window()
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Segoe UI", 24)
    small = pygame.font.SysFont("Segoe UI", 18)
    while True:
        surface = pygame.display.get_surface()
        if surface is None:
            # A missing game window must not prevent a confirmation on Windows.
            return _confirm_without_window()
        width, height = surface.get_size()
        panel = pygame.Rect(0, 0, min(520, width), min(210, height))
        panel.center = (width // 2, height // 2)
        button_width = min(170, max(50, (panel.width - 36) // 2))
        yes = pygame.Rect(panel.centerx - button_width - 6, panel.bottom - 68, button_width, 44)
        no = pygame.Rect(panel.centerx + 6, panel.bottom - 68, button_width, 44)
        pygame.draw.rect(surface, (245, 240, 224), panel, border_radius=12)
        pygame.draw.rect(surface, (20, 105, 87), panel, width=2, border_radius=12)
        question = font.render("Bạn có muốn thoát ứng dụng?", True, (30, 44, 40))
        surface.blit(question, question.get_rect(center=(panel.centerx, panel.top + 52)))
        for rect, label, color in ((yes, "THOÁT (Enter)", (166, 51, 43)),
                                   (no, "Ở LẠI (Esc)", (20, 105, 87))):
            pygame.draw.rect(surface, color, rect, border_radius=6)
            text = small.render(label, True, (255, 255, 255))
            surface.blit(text, text.get_rect(center=rect.center))
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_y):
                    return True
                if event.key in (pygame.K_ESCAPE, pygame.K_n):
                    return False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if yes.collidepoint(event.pos):
                    return True
                if no.collidepoint(event.pos):
                    return False
            # Clicking X again leaves the question open; it is not consent.
        clock.tick(30)


def exit_application():
    """Exit after consent, bypassing blocking device cleanup and atexit hooks.

    Existing journal records are retained. This sends no robot/gripper commands
    and does not mark an unfinished physical transaction as completed.
    """
    os._exit(0)
