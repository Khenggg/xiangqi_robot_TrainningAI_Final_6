"""Normal main entrypoint, real virtual runtime/HTTP/WS; no hardware."""
import os, sys, time, runpy, socket, json, atexit, urllib.request, webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
# Script lives reports/<run>/, so parents[2] is repository.
os.chdir(ROOT);sys.path.insert(0,str(ROOT))
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
import pygame
from src.ui.game_window import GameWindow
from src.ui.board_renderer import HOME_SELF_PLAY_RECT,HOME_HUMAN_RECT
from src.hardware.robot_VIP import FR5Robot
from src.hardware.telemetry_publisher import TelemetryPublisher
from websockets.sync.client import connect
mode=sys.argv[1]
def free_port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
http_port,ws_port=free_port(),free_port()
out=Path(__file__).resolve().parent
sys.argv=['main.py','--viewer-port',str(http_port),'--telemetry-port',str(ws_port),'--log-dir',str(out/'smoke-logs'/mode)]
webbrowser.open=lambda url:True
FR5Robot.connect=lambda *a:(_ for _ in ()).throw(AssertionError('Physical connect forbidden'))
GameWindow.map_event=lambda self,e:e
original_events=pygame.event.get
started=False;ready=False;deadline=time.monotonic()+60
record={}
def events():
 global started,ready
 app=sys._getframe(1).f_globals
 if time.monotonic()>deadline:raise TimeoutError('Normal-entrypoint virtual startup exceeded deadline')
 if not started:
  started=True
  if mode=='HUMAN_VS_ROBOT':return [pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN)]
  rect=HOME_SELF_PLAY_RECT if mode=='ROBOT_VS_ROBOT' else HOME_HUMAN_RECT
  return [pygame.event.Event(pygame.MOUSEBUTTONDOWN,pos=rect.center,button=1)]
 hw=app['hw']
 if app['startup_worker'].busy or hw is None or hw.motion_worker.busy:return []
 if app['difficulty_menu_active']:return [pygame.event.Event(pygame.KEYDOWN,key=pygame.K_1)]
 if not ready:
  ready=True
  assert hw.simulation_runtime is not None and hw.is_robot_ready
  assert hw.twin_bridge is not None and not app['state'].move_sync_error
  assert app['config'].GAME_MODE==mode
  with urllib.request.urlopen(f'http://127.0.0.1:{http_port}/robot-3d-viewer/main.mjs',timeout=3) as r:
   record['http_status']=r.status;record['content_type']=r.headers['Content-Type'];assert len(r.read())>1000
  with connect(f'ws://127.0.0.1:{ws_port}',open_timeout=3) as ws:
   types=[]
   for _ in range(10):
    packet=json.loads(ws.recv(timeout=3));types.append(packet.get('type'))
    if 'robot_state' in types and 'world_state' in types:break
   assert 'robot_state' in types and 'world_state' in types,types
   record['websocket_messages']=types
  pygame.image.save(app['screen'],str(out/(mode+'-gui.png')))
  record.update(mode=mode,backend='VIRTUAL',pieces=len(hw.twin_bridge.world.pieces),scene_synced=True)
  return [pygame.event.Event(pygame.QUIT)]
 return original_events()
pygame.event.get=events
app=runpy.run_path(str(ROOT/'main.py'),run_name='__main__')
try:
 assert ready
finally:
 app['_cleanup_all']()
 app['log_session'].close()
(out/(mode+'-smoke.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record))
