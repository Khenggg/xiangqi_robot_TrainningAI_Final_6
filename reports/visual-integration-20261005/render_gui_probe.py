"""Render production GUI to inspect manual-test controls; no robot/camera connection."""
import os
os.environ['SDL_VIDEODRIVER']='dummy'
os.environ['SDL_AUDIODRIVER']='dummy'
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root))
import pygame
from src.ui.board_renderer import BoardRenderer,SCREEN_WIDTH,SCREEN_HEIGHT
from src.core.game_state import GameState
pygame.init()
screen=pygame.display.set_mode((SCREEN_WIDTH,SCREEN_HEIGHT))
renderer=BoardRenderer(screen)
state=GameState(allow_mouse_move=True)
state.pick_test_mode=True
state.pick_test_resume_required=True
for name,fault in [('manual-test-gui',None),('manual-test-fault','SDK 112: dừng trước khi gắp; khôi phục bàn trước khi chạy tiếp')]:
    state.pick_test_fault=fault
    renderer.draw_ui(state.get_render_state())
    renderer.draw_pieces(state.board)
    pygame.image.save(screen,str(Path(__file__).parent/(name+'.png')))
pygame.quit()
print('GUI render: manual test controls and latched fault saved')
