"""15-second camera-only GUI acceptance: no game or robot SDK imports."""
from pathlib import Path
import json
import sys
import time
import cv2

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from src.vision.camera_startup import open_validated_camera
from src.vision.camera_monitor import CameraMonitor
from src.vision.cchess_recognizer import CChessRecognizer
from ultralytics import YOLO

report = Path(__file__).resolve().parent
rec = CChessRecognizer(root/'models/cchess/pose_4_v6.onnx', root/'models/cchess/layout_nano_v3.onnx', use_gpu=True)
model = YOLO(str(root/'models/best.pt'))
cap = open_validated_camera(2)
monitor = CameraMonitor(cap, model=model,
    perspective_path=root/'reports/camera-gpu-review-20261013/perspective.npy',
    cchess_recognizer=rec, window_name='Camera Monitor QA - GPU')
samples = []
try:
    monitor.start()
    begin = time.monotonic()
    while time.monotonic()-begin < 15:
        key = monitor.update_display()
        result = monitor.get_latest_observation()
        samples.append({'elapsed_s':time.monotonic()-begin,
            'ready':monitor.get_health()['ready'],
            'frame_at':monitor._last_frame_at,
            'recognition_at':None if result is None else result[0],
            'names':None if result is None or result[3] is None else
                sum(v.startswith(('r_','b_')) for row in result[3]['board'] for v in row),
            'error':monitor.get_health()['error']})
        if result is not None and result[3] is not None:
            cv2.imwrite(str(report/'live-overlay.jpg'),monitor._draw_overlay(result[1],result[2]))
        if key in (27,ord('q')):
            break
        time.sleep(.03)
finally:
    monitor.stop()
    cv2.destroyAllWindows()
    data={'camera':2,'backend':cap.getBackendName() if cap.isOpened() else 'DSHOW',
        'pose_providers':rec.pose_session.get_providers(),'layout_providers':rec.layout_session.get_providers(),
        'yolo_device':str(model.predictor.device),'samples':samples,
        'capture_stopped':not monitor._thread.is_alive(),
        'detect_stopped':not monitor._detect_thread.is_alive(),'capture_released':not cap.isOpened()}
    (report/'live-camera.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k!='samples'}))
