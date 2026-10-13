from pathlib import Path
import os,sys,time,threading,json
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
sys.path.insert(0,str(Path.cwd()))
import cv2,pygame,numpy as np
from ultralytics import YOLO
from src.vision.cchess_recognizer import CChessRecognizer
from src.vision.camera_monitor import CameraMonitor
from src.ui.input_handler import InputHandler
from src.ui.board_renderer import BoardRenderer,SCREEN_WIDTH,SCREEN_HEIGHT
from src.core.game_state import GameState
from types import SimpleNamespace
pygame.init()
screen=pygame.display.set_mode((SCREEN_WIDTH,SCREEN_HEIGHT));renderer=BoardRenderer(screen)
r=CChessRecognizer('models/cchess/pose_4_v6.onnx','models/cchess/layout_nano_v3.onnx')
c=CameraMonitor(None,YOLO('models/best.pt'),'perspective.npy',cchess_recognizer=r)
raw=cv2.imread(r'C:/Users/Ken/AppData/Local/Temp/codex-clipboard-b9194599-2a3c-4d07-9fb8-42ffc9d65624.png')
state=GameState();detector=SimpleNamespace(_baseline_time=1.0,has_baseline=lambda:True,detect_move=lambda *a,**k:(None,None,None),has_new_human_move=lambda *a,**k:False)
hw=SimpleNamespace(cam_monitor=c,yolo_detector=detector,cchess_recognizer=r)
handler=InputHandler(state,hw);stop=threading.Event();samples=[]
def infer():
    while not stop.is_set():
        before=time.perf_counter();c._infer_frame(raw,time.monotonic());samples.append({'duration_ms':round((time.perf_counter()-before)*1000,1),'worker_torch_threads':__import__('torch').get_num_threads(),'health':c.get_health()});stop.wait(.2)
worker=threading.Thread(target=infer);worker.start();latencies=[];poll_ms=[];end=time.monotonic()+8
while time.monotonic()<end:
    before=time.perf_counter();pygame.event.get()
    poll_start=time.perf_counter();handler.poll_board_stability();poll_ms.append((time.perf_counter()-poll_start)*1000)
    screen.fill((20,20,20));renderer.draw_home_screen('Performance smoke: model inference in background, no camera or robot connection.')
    pygame.display.flip();latencies.append((time.perf_counter()-before)*1000);time.sleep(.016)
stop.set();worker.join(15)
pygame.image.save(screen,'reports/physical-ui-latency-20261009/ui-python312.png');pygame.quit()
print(json.dumps({'frames':len(latencies),'ui_p95_ms':round(float(np.percentile(latencies,95)),2),'ui_max_ms':round(max(latencies),2),'poll_max_ms':round(max(poll_ms),2),'inference_ms':samples,'torch_threads':__import__('torch').get_num_threads(),'ort_threads':r.layout_session.get_session_options().intra_op_num_threads,'hardware_connected':False}))
