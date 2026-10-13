import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import cv2, torch
from src.vision.cchess_recognizer import CChessRecognizer
from ultralytics import YOLO
frame=cv2.imread(r'C:/Users/Ken/AppData/Local/Temp/codex-clipboard-b9194599-2a3c-4d07-9fb8-42ffc9d65624.png')
r=CChessRecognizer('models/cchess/pose_4_v6.onnx','models/cchess/layout_nano_v3.onnx')
m=YOLO('models/best.pt')
if len(sys.argv)>1 and sys.argv[1]=='fixed':
    torch.set_num_threads(2)
    cv2.setNumThreads(1)
rect=cv2.resize(frame,(450,500))
results=[]
for i in range(4):
    start=time.perf_counter(); cpu=time.process_time()
    r.recognize_layout(rect)
    m.predict(frame,device='cpu',verbose=False,imgsz=640)
    if len(sys.argv)>1 and sys.argv[1]=='fixed': torch.set_num_threads(2)
    results.append({'wall_ms':round((time.perf_counter()-start)*1000,1), 'cpu_ms':round((time.process_time()-cpu)*1000,1)})
print(json.dumps({'torch_threads':torch.get_num_threads(),'cv_threads':cv2.getNumThreads(),'ort_threads':r.layout_session.get_session_options().intra_op_num_threads,'samples':results}))
