from pathlib import Path
import sys,json,threading,mimetypes,importlib.util
from urllib.request import urlopen
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root))
from src.core.launch_options import ViewerServer,check_viewer_assets
report=Path(__file__).resolve().parent
if '--serve' not in sys.argv:
    spec=importlib.util.spec_from_file_location('baseline_launch',report/'baseline/src/core/launch_options.py')
    baseline=importlib.util.module_from_spec(spec); spec.loader.exec_module(baseline)
    mimetypes.init()
    mimetypes.types_map['.mjs']='application/octet-stream'
    mimetypes.types_map['.js']='text/plain'
    result={'python':sys.version,'fixture':'non-JavaScript OS MIME mapping','servers':{}}
    for name,cls in [('baseline',baseline.ViewerServer),('fixed',ViewerServer)]:
        s=cls(root,0); s.thread.start()
        try:
            data={}
            for path in ['robot-3d-viewer/main.mjs','vendor/three/build/three.module.js']:
                with urlopen(s.url.removesuffix('robot-3d-viewer/')+path,timeout=3) as response:
                    data[path]={'status':response.status,'content_type':response.headers.get_content_type(),'bytes':len(response.read())}
            result['servers'][name]=data
        finally: s.close()
    assert result['servers']['baseline']['robot-3d-viewer/main.mjs']['content_type']=='application/octet-stream'
    assert all(v['content_type']=='text/javascript' for v in result['servers']['fixed'].values())
    check_viewer_assets(root)
    (report/'python312-http.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
else:
    import config
    from src.core.launch_options import configure_runtime,parse_options
    configure_runtime(config,parse_options(['--viewer-port','8098','--telemetry-port','8898']))
    assert config.DRY_RUN and config.ROBOT_BACKEND=='VIRTUAL'
    from src.hardware.hardware_manager import HardwareManager
    from src.hardware.telemetry_publisher import TelemetryPublisher
    from src.core.game_state import GameState
    hw=HardwareManager(config,str(root)); hw._init_robot()
    assert hw.simulation_runtime is not None and hw.cap is None
    telemetry=TelemetryPublisher(host='127.0.0.1',port=8898,robot_model='FR3')
    bridge=hw.setup_digital_twin(telemetry)
    state=GameState(); state.set_board_observer(hw.sync_committed_board)
    assert state.sync_current_board()
    check_viewer_assets(root)
    server=ViewerServer(root,8098)
    try:
        telemetry.start(); server.thread.start()
        print('READY http://127.0.0.1:8098/robot-3d-viewer/?ws=ws://127.0.0.1:8898&autoconnect=1',flush=True)
        input('Press ENTER to stop isolated virtual servers: ')
    finally:
        server.close(); hw.cleanup(); telemetry.stop()
        print('CLOSED',flush=True)
