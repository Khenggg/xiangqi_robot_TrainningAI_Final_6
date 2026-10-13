"""Production renderer proof; intentionally uses dummy SDL and no hardware."""
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import sys
from pathlib import Path
sys.path.insert(0, 'D:/OJT/_simple_launch_sync_20261005')
import pygame
from src.ui.board_renderer import BoardRenderer, SCREEN_WIDTH, SCREEN_HEIGHT
from src.core.game_state import GameState
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
renderer = BoardRenderer(screen)
state = GameState()
state.physical_sync_fault = True
state.move_sync_error = 'Camera did not confirm the complete expected board'
state.move_execution_status = 'FAILED'
state.pending_ai_move = {'move': ((1, 7), (1, 0)), 'expected_board': state.board}
renderer.draw_ui({**state.get_render_state(), 'robot_backend': 'PHYSICAL'})
renderer.draw_pieces(state.board)
pygame.image.save(screen, str(Path(__file__).with_name('recovery-gui.png')))
pygame.quit()
print('Rendered recovery panel: failure, pending capture, supervised recovery guidance')
