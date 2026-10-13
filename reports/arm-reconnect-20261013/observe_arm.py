"""Temporary QA server: borrow the application's SDK; read state only."""
from pathlib import Path
import json
import sys
import time

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
import config
config.DRY_RUN = False
config.ROBOT_BACKEND = 'PHYSICAL'
from src.hardware import robot_sdk_core
from src.hardware.hardware_manager import HardwareManager
from src.hardware.telemetry_publisher import TelemetryPublisher
from src.core.launch_options import ViewerServer

report = Path(__file__).resolve().parent
stop = report / 'stop-observer'
for name in ('Mode', 'RobotEnable', 'MoveJ', 'MoveL', 'MoveCart', 'SetToolDO', 'SetDO', 'ServoJ', 'ResetAllError'):
    def reject(*args, _name=name, **kwargs):
        raise AssertionError('Actuation forbidden in read-only QA: ' + _name)
    setattr(robot_sdk_core.RPC, name, reject)

manager = HardwareManager(config, root)
publisher = viewer = None
observations = []
try:
    manager._init_robot()
    publisher = TelemetryPublisher(host='127.0.0.1', port=8765, robot_model='FR3')
    bridge = manager.setup_digital_twin(publisher)
    if bridge is None:
        raise RuntimeError('No retained SDK handle for the arm relay')
    publisher.start()
    viewer = ViewerServer(root, 8088)
    viewer.thread.start()
    begin = time.monotonic()
    while not stop.exists() and time.monotonic() - begin < 180:
        snapshot = manager.backend.get_state_snapshot()
        observations.append({'time': time.time(), 'connected': snapshot.connected,
            'joints_valid': snapshot.joints_valid, 'joints': snapshot.joints_deg,
            'measurement_timestamp': snapshot.measurement_timestamp,
            'error': snapshot.telemetry_error})
        (report / 'physical.json').write_text(json.dumps({'board_calibrated': manager.board_pose_provider is not None,
            'reason': manager.simulation_error, 'motion_authorized': manager.robot.physical_motion_authorized,
            'observations': observations[-20:]}, indent=2), encoding='utf-8')
        time.sleep(.2)
finally:
    manager.cleanup()
    if publisher:
        publisher.stop()
    if viewer:
        viewer.close()
    (report / 'observer-closed.json').write_text(json.dumps({'closed': True,
        'receiver_alive': bool(manager.robot.robot and manager.robot.robot.thread.is_alive())}), encoding='utf-8')
