import threading
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
from src.vision.camera_monitor import CameraMonitor
from src.vision.pick_consensus import FreshPickTransientError


def camera():
    monitor=CameraMonitor.__new__(CameraMonitor)
    monitor.cap=Mock()
    monitor.cap.isOpened.return_value=True
    frame=np.zeros((4,6,3),np.uint8)
    frame[0,0]=[1,2,3]
    monitor.cap.read.return_value=(True,frame)
    monitor.model=Mock()
    monitor.model.predict.return_value=[SimpleNamespace(boxes=[SimpleNamespace(cls=[0],conf=[.9],xyxy=[[.25,.5,2.75,3.25]])])]
    monitor._cam_lock=threading.Lock()
    monitor._inference_lock=threading.Lock()
    monitor._stop_event=threading.Event()
    monitor._pick_scan_active=threading.Event()
    monitor._pick_scan_lock=threading.Lock()
    monitor.conf=.25
    monitor.device='cpu'
    return monitor,frame


def test_raw_pick_bgr_float_boxes_are_from_exact_frame():
    monitor,frame=camera()
    image,boxes=monitor.get_fresh_pick_snapshot()
    assert image is frame and boxes[0][2]==(.25,.5,2.75,3.25)
    assert monitor.model.predict.call_args.args[0] is frame
    assert image[0,0].tolist()==[1,2,3]


@pytest.mark.parametrize('failure',['read','inference'])
def test_raw_pick_failures_are_never_empty_occupancy(failure):
    monitor,_=camera()
    if failure=='read': monitor.cap.read.return_value=(False,None)
    else: monitor.model.predict.side_effect=RuntimeError('inference failed')
    with pytest.raises(FreshPickTransientError): monitor.get_fresh_pick_snapshot()


def test_scan_session_clears_pause_after_exception():
    monitor,_=camera()
    with pytest.raises(ValueError):
        with monitor.pick_scan_session():
            assert monitor._pick_scan_active.is_set()
            raise ValueError('bad geometry')
    assert not monitor._pick_scan_active.is_set()


def test_stop_cannot_release_device_under_live_worker():
    monitor,_=camera()
    monitor._thread=Mock()
    monitor._thread.is_alive.return_value=True
    monitor._detect_thread=None
    with pytest.raises(RuntimeError,match='kept open'):
        monitor.stop()
    assert monitor._stop_event.is_set()
    monitor.cap.release.assert_not_called()
