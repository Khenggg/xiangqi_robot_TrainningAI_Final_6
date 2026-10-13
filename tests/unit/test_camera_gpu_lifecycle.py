"""Startup wiring and actual camera threads, with mock devices/models only."""
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
import config
from src.hardware import hardware_manager as module
from src.vision.camera_monitor import CameraMonitor


class Capture:
    def __init__(self):
        self.reads = 0
        self.released = False
    def isOpened(self): return not self.released
    def read(self):
        self.reads += 1
        return True, np.zeros((40, 40, 3), dtype=np.uint8)
    def grab(self): return True
    def release(self): self.released = True


class Recognizer:
    def extract_rectified_board(self, image, points): return image, None
    def recognize_layout(self, image):
        board = [['.']*9 for _ in range(10)]
        board[0][0] = 'b_R'
        return board, board, np.ones((10, 9))


@pytest.mark.parametrize('preference,gpu', [('auto',True),('cpu',False)])
def test_real_manager_starts_capture_and_recognition_once(monkeypatch,tmp_path,preference,gpu):
    cfg = SimpleNamespace(**{k:getattr(config,k) for k in dir(config) if k.isupper()})
    cfg.DRY_RUN=False
    cfg.VISION_DEVICE=preference
    for k in ('VISUAL_PICK_ENABLED','VISUAL_RING_PICK_ENABLED','VISUAL_HEIGHT_PICK_ENABLED',
              'VISUAL_TOP_FACE_ENABLED','VISUAL_BOARD_SYNC_REQUIRED'):
        setattr(cfg,k,False)
    models=tmp_path/'models/cchess';models.mkdir(parents=True)
    for name in ('pose_4_v6.onnx','layout_nano_v3.onnx'):(models/name).touch()
    np.save(tmp_path/'perspective.npy',np.eye(3))
    recognizer_factory=Mock(return_value=Recognizer())
    monkeypatch.setattr('src.vision.cchess_recognizer.CChessRecognizer',recognizer_factory)
    model=SimpleNamespace(predict=lambda *a,**k:[SimpleNamespace(boxes=[])])
    monkeypatch.setattr(module,'YOLO',Mock(return_value=model))
    monkeypatch.setattr(module,'run_calibration_flow',lambda *a,**k:np.eye(3))
    cap=Capture()
    monkeypatch.setattr('src.vision.camera_startup.open_validated_camera',lambda _:cap)
    manager=module.HardwareManager(cfg,str(tmp_path))
    try:
        manager._init_camera()
        camera=manager.cam_monitor
        assert camera._thread is not None and camera._thread.is_alive()
        assert camera._detect_thread is not None and camera._detect_thread.is_alive()
        capture_thread,detect_thread=camera._thread,camera._detect_thread
        camera.start()
        assert (camera._thread,camera._detect_thread)==(capture_thread,detect_thread)
        deadline=time.monotonic()+1
        while camera.get_latest_cchess_result() is None and time.monotonic()<deadline:
            time.sleep(.01)
        assert camera.get_latest_cchess_result()['board'][0][0]=='b_R'
        stamp=camera.get_latest_observation()[0]
        while camera.get_latest_observation()[0]==stamp and time.monotonic()<deadline:
            time.sleep(.01)
        assert camera.get_latest_observation()[0]>stamp
        assert cap.reads>1
        assert recognizer_factory.call_args.kwargs['use_gpu'] is gpu
    finally:
        manager.cleanup()
    assert not capture_thread.is_alive() and not detect_thread.is_alive()
    assert cap.released


def test_explicit_cpu_preference_does_not_probe_cuda(monkeypatch):
    cuda=Mock(side_effect=AssertionError('CPU option probed CUDA'))
    monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(cuda=SimpleNamespace(is_available=cuda)))
    camera=CameraMonitor(None,device_preference='cpu')
    assert camera.device=='cpu'
    cuda.assert_not_called()


def test_preview_does_not_draw_cached_boxes_after_recognition_is_stale(monkeypatch):
    camera=CameraMonitor(None)
    camera._last_inference_at=time.monotonic()-10
    rectangle=Mock()
    monkeypatch.setattr('src.vision.camera_monitor.cv2.rectangle',rectangle)
    camera._draw_overlay(np.zeros((80,80,3),np.uint8),[(0,.9,(10,10,40,40))])
    rectangle.assert_not_called()
