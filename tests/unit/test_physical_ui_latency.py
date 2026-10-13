import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
import pytest
from src.vision.camera_monitor import CameraMonitor
from src.ui.input_handler import InputHandler
from src.core import xiangqi
from src.core.launch_options import ViewerServer


def cached_camera():
    c=CameraMonitor.__new__(CameraMonitor)
    c._lock=threading.Lock()
    c._inference_lock=threading.Lock()
    c._inference_error=None
    c._max_result_age_s=1.5
    c._last_inference_at=time.monotonic()
    c._recognized_frame=np.full((8,12,3),17,np.uint8)
    c._last_frame=np.full((8,12,3),99,np.uint8)
    c._last_detections=[(0,.9,(1,2,3,4))]
    c._last_cchess_result={'success':True,'board':xiangqi.get_board()}
    return c


def test_cached_observation_atomic_and_nonblocking_during_inference():
    c=cached_camera()
    with c._inference_lock:  # model is busy; UI must not wait for it
        start=time.perf_counter()
        stamp,frame,boxes,layout=c.get_latest_observation()
        assert time.perf_counter()-start < .1
    assert stamp==c._last_inference_at and np.all(frame==17)
    frame[:]=0; boxes.clear(); layout['board'][0][0]='.'
    assert np.all(c._recognized_frame==17)
    assert c._last_detections and c._last_cchess_result['board'][0][0]=='b_R'
    c._last_inference_at=time.monotonic()-2
    assert c.get_latest_observation() is None
    c._last_inference_at=time.monotonic(); c._inference_error='capture failed'
    assert c.get_latest_observation() is None


def make_handler():
    clock=[100.0]
    observed=[100.0]
    camera=SimpleNamespace(get_latest_observation=lambda: (observed[0],object(),[],None),
                           get_fresh_snapshot=Mock(side_effect=AssertionError('UI touched camera')))
    detector=SimpleNamespace(_baseline_time=1.0,_baseline_occ=[[False]*9 for _ in range(10)],
                              has_baseline=lambda:True,
                              detect_move=lambda *a,**k:((0,6),(0,5),'r_P'))
    state=SimpleNamespace(turn='r',game_over=False,board=xiangqi.get_board(),
                          save_rollback_state=Mock(),set_status=Mock())
    hw=SimpleNamespace(cam_monitor=camera,yolo_detector=detector,
                       recognize_board_state=Mock(side_effect=AssertionError('UI reran model')))
    handler=InputHandler(state,hw)
    handler._observed_baseline_time=1.0
    handler._commit_human_move=Mock(return_value=True)
    return handler,clock,observed


def test_gui_repeated_result_cannot_satisfy_stability_gate(monkeypatch):
    handler,clock,observed=make_handler()
    monkeypatch.setattr('src.ui.input_handler.time.monotonic',lambda:clock[0])
    assert not handler.poll_board_stability()
    for t in (100.2,101.0,102.0):
        clock[0]=t
        assert not handler.poll_board_stability()
    assert handler._board_stability_monitor.sample_count==1
    observed[0]=101.0; clock[0]=102.2
    assert not handler.poll_board_stability()
    observed[0]=102.0; clock[0]=102.4
    assert handler.poll_board_stability()
    handler._commit_human_move.assert_called_once_with((0,6),(0,5),'r_P',source='AUTO')
    handler.hw.cam_monitor.get_fresh_snapshot.assert_not_called()
    handler.hw.recognize_board_state.assert_not_called()


def test_changed_baseline_and_missing_camera_reset_candidate(monkeypatch):
    handler,clock,observed=make_handler()
    monkeypatch.setattr('src.ui.input_handler.time.monotonic',lambda:clock[0])
    handler.poll_board_stability()
    clock[0]=101; handler.hw.yolo_detector._baseline_time=2
    assert not handler.poll_board_stability()  # sample predates baseline boundary
    assert handler._board_stability_monitor.sample_count==0
    clock[0]=101.2; observed[0]=101.1
    assert not handler.poll_board_stability()
    assert handler._board_stability_monitor.sample_count==1
    clock[0]=101.4; handler.hw.cam_monitor.get_latest_observation=lambda:None
    assert not handler.poll_board_stability()
    assert handler._board_stability_monitor.sample_count==0
    handler._commit_human_move.assert_not_called()


def test_unavailable_mirror_still_serves_http_without_autoconnect(tmp_path,monkeypatch):
    from urllib.parse import urlsplit,parse_qs
    from urllib.request import urlopen
    index=tmp_path/'robot-3d-viewer'/'index.html';index.parent.mkdir()
    index.write_text('offline preview')
    opened=[]
    monkeypatch.setattr('src.core.launch_options.webbrowser.open',opened.append)
    server=ViewerServer(tmp_path,0)
    try:
        server.start(8765,unavailable_reason='Chưa đo mặt bàn & TCP')
        with urlopen(server.url,timeout=2) as response:
            assert response.read()==b'offline preview'
        query=parse_qs(urlsplit(opened[0]).query)
        assert query['autoconnect']==['0']
        assert query['mirror_error']==['Chưa đo mặt bàn & TCP']
    finally: server.close()

@pytest.mark.parametrize('flag,expect_http', [('--physical',True),('--virtual',False)])
def test_real_entrypoint_missing_mirror_keeps_ui_and_respects_game_only(tmp_path,monkeypatch,flag,expect_http):
    import atexit, runpy,sys,os
    from pathlib import Path
    import pygame, config
    from src.hardware.hardware_manager import HardwareManager
    from src.core import launch_options
    from src.api.simulation_client import TuongKyDaiSuClient
    from src.hardware.telemetry_publisher import TelemetryPublisher
    for name in ('DRY_RUN','ROBOT_BACKEND','GAME_ONLY','TELEMETRY_PORT','GAME_MODE'):
        monkeypatch.setattr(config,name,getattr(config,name,None),raising=False)
    monkeypatch.setenv('SDL_VIDEODRIVER','dummy')
    monkeypatch.setenv('SDL_AUDIODRIVER','dummy')
    monkeypatch.setattr(sys,'argv',['main.py',flag,'--log-dir',str(tmp_path/'logs')])
    monkeypatch.setattr(sys,'path',list(sys.path))
    callbacks=[]
    monkeypatch.setattr(atexit,'register',lambda cb,*a,**k:callbacks.append(cb))
    hw=SimpleNamespace(setup_digital_twin=lambda telemetry:None,simulation_error='contact offset missing',
                        config=config,motion_worker=SimpleNamespace(busy=False,poll=lambda:None),
                        cam_monitor=None,robot=None,backend=None,
                        difficulty_availability=lambda:{'easy':True},cleanup=Mock(),is_robot_ready=False)
    monkeypatch.setattr(HardwareManager,'initialize_all',lambda self:hw)
    server=Mock()
    factory=Mock(return_value=server)
    monkeypatch.setattr(launch_options,'ViewerServer',factory)
    monkeypatch.setattr(launch_options,'check_viewer_assets',lambda _:None)
    telemetry_start=Mock(side_effect=AssertionError('Uncalibrated mirror published'))
    monkeypatch.setattr(TelemetryPublisher,'start',telemetry_start)
    monkeypatch.setattr(TuongKyDaiSuClient,'end_match',Mock())
    started = [False]
    deadline = time.monotonic() + 10
    def events():
        assert time.monotonic() < deadline, 'Viewer startup did not finish'
        if not started[0]:
            started[0] = True
            return [pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN)]
        app = sys._getframe(1).f_globals
        if app['hw'] is hw and not app['home_screen_active']:
            return [pygame.event.Event(pygame.QUIT)]
        return []
    monkeypatch.setattr(pygame.event,'get',events)
    try:
        app=runpy.run_path(str(Path(__file__).resolve().parents[2]/'main.py'),run_name='__main__')
        assert app['hw'] is hw and not app['home_screen_active']
        assert factory.called is expect_http
        if expect_http:
            server.start.assert_called_once_with(config.TELEMETRY_PORT, unavailable_reason=app['mirror_error'], telemetry_available=False)
            assert 'contact offset missing' in app['mirror_error']
        telemetry_start.assert_not_called()
    finally:
        for cb in reversed(callbacks): cb()
        pygame.quit()
