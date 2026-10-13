from pathlib import Path
import sys,os,atexit,runpy,json
from unittest.mock import patch,Mock
from contextlib import ExitStack
os.environ['SDL_VIDEODRIVER']='dummy'; os.environ['SDL_AUDIODRIVER']='dummy'
root=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(root))
import pygame
from src.hardware.hardware_manager import HardwareManager
from src.hardware.robot_VIP import FR5Robot
from src.api.simulation_client import TuongKyDaiSuClient
report=Path(__file__).resolve().parent
reason='Camera startup blocked: Cannot read camera index 1. Close Windows Camera, OBS/Teams; check index and camera permissions.'
callbacks=[]; cleanup=Mock(); connect=Mock(side_effect=AssertionError('Physical connect prohibited in probe'))
frames=iter([[pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN)],[pygame.event.Event(pygame.KEYDOWN,key=pygame.K_RETURN)],[pygame.event.Event(pygame.QUIT)]])
with ExitStack() as stack:
    stack.enter_context(patch.object(sys,'argv',['main.py','--physical','--log-dir',str(report/'python312-logs')]))
    stack.enter_context(patch.object(atexit,'register',lambda f,*a,**k:callbacks.append(f)))
    stack.enter_context(patch.object(HardwareManager,'_init_ai',Mock()))
    stack.enter_context(patch.object(HardwareManager,'_init_robot',Mock()))
    stack.enter_context(patch.object(HardwareManager,'_init_camera',Mock(side_effect=RuntimeError(reason))))
    stack.enter_context(patch.object(HardwareManager,'cleanup',cleanup))
    stack.enter_context(patch.object(FR5Robot,'connect',connect))
    stack.enter_context(patch.object(TuongKyDaiSuClient,'end_match',Mock()))
    stack.enter_context(patch.object(pygame.event,'get',lambda:next(frames)))
    try:
        app=runpy.run_path(str(root/'main.py'),run_name='__main__')
        assert app['home_screen_active'] and not app['difficulty_menu_active']
        assert app['hw'] is None and app['viewer_server'] is None
        assert cleanup.call_count==2 and connect.call_count==0
        assert reason in app['startup_message']
        pygame.image.save(app['screen'],str(report/'startup-error-python312.png'))
        result={'python':sys.version,'home_screen_active':True,'failed_attempts':cleanup.call_count,'physical_connect_calls':connect.call_count,'message':app['startup_message']}
    finally:
        for f in reversed(callbacks): f()
        pygame.quit()
logs=list((report/'python312-logs').glob('*/run.log'))
assert logs and 'APP_UNHANDLED' not in max(logs, key=lambda p:p.stat().st_mtime_ns).read_text(encoding='utf-8')
(report/'python312-result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
print('PASS: physical-mode GUI keeps home screen through two mocked camera failures; explicit retry available. No hardware connected.')

