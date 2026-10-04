"""Headless visual GUI launch with real virtual runtime; never physical hardware."""
import os, sys, threading, time, runpy, argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["ROBOT_BACKEND"] = "VIRTUAL"; os.environ["DRY_RUN"] = "1"
parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=("HUMAN_VS_ROBOT", "HUMAN_VS_HUMAN", "ROBOT_VS_ROBOT"), default="HUMAN_VS_ROBOT")
args = parser.parse_args()
import config
config.ROBOT_BACKEND = "VIRTUAL"; config.DRY_RUN = True
config.TELEMETRY_PORT = 8878
import pygame
out = ROOT / "reports" / "integration-20261004"
if args.mode != "HUMAN_VS_ROBOT":
    out = out / args.mode.lower()
out.mkdir(parents=True, exist_ok=True)
def pump():
    deadline = time.monotonic() + 30
    while not pygame.display.get_init() or pygame.display.get_surface() is None:
        if time.monotonic() > deadline: return
        time.sleep(.1)
    time.sleep(.5)
    pygame.image.save(pygame.display.get_surface(), str(out / "gui-home.png"))
    if args.mode == "HUMAN_VS_ROBOT":
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    else:
        from src.ui.board_renderer import HOME_SELF_PLAY_RECT, HOME_HUMAN_RECT
        rect = HOME_SELF_PLAY_RECT if args.mode == "ROBOT_VS_ROBOT" else HOME_HUMAN_RECT
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
    time.sleep(9)
    pygame.image.save(pygame.display.get_surface(), str(out / "gui-difficulty.png"))
    if args.mode != "HUMAN_VS_HUMAN":
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1))
    time.sleep(3)
    pygame.image.save(pygame.display.get_surface(), str(out / "gui-game.png"))
    pygame.event.post(pygame.event.Event(pygame.QUIT))
threading.Thread(target=pump, daemon=True).start()
result = runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
hw = result["hw"]
try:
    assert hw is not None and hw.simulation_runtime is not None
    assert hw.is_robot_ready
    assert hw.twin_bridge is not None
    assert result["state"]._board_observer is not None
    assert not result["difficulty_menu_active"], "Difficulty selection failed"
    assert config.GAME_MODE == args.mode
    if args.mode == "ROBOT_VS_ROBOT":
        assert result["self_play"].human_input_disabled
    print("MERGED_GUI_SMOKE_OK: visual game, virtual runtime, twin and telemetry initialized")
finally:
    result["_cleanup_all"]()
