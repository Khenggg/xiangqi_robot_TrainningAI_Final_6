"""Transactional session startup, executed outside the GUI thread."""
from src.core import launch_options
from src.hardware.hardware_manager import HardwareManager
from src.hardware.telemetry_publisher import TelemetryPublisher
from src.core.project_logging import event
import logging


def rollback_session(manager, telemetry, viewer, state):
    """Release an incomplete session, including GUI initialization failure."""
    state.set_board_observer(None)
    state.move_sync_error = None
    state.physical_sync_fault = False
    for resource, method in ((manager, 'cleanup'), (telemetry, 'stop'), (viewer, 'close')):
        if resource is not None:
            try:
                getattr(resource, method)()
            except Exception as exc:
                event('cleanup.failed', f'Startup rollback {method}: {exc}', level=logging.ERROR)


def build_session(config, options, root, state, cancelled=None):
    manager = telemetry = viewer = None
    try:
        manager = HardwareManager(config, root).initialize_all()
        if cancelled is not None and cancelled.is_set():
            raise RuntimeError('Startup cancelled')
        telemetry = TelemetryPublisher(host=config.TELEMETRY_HOST, port=config.TELEMETRY_PORT, robot_model='FR3')
        bridge = manager.setup_digital_twin(telemetry)
        board_ready = bridge is not None and getattr(bridge, 'board_sync_available', True)
        if board_ready:
            state.set_board_observer(manager.sync_committed_board)
            if not state.sync_current_board():
                raise RuntimeError('Initial board synchronization failed')
        if bridge is not None:
            telemetry.start()
        uncalibrated = getattr(bridge, 'uncalibrated_board', False) or not board_ready
        reason = None if not uncalibrated or config.GAME_ONLY else (
            'Bàn mô phỏng mặc định (đồng bộ quân cờ BẬT); tọa độ lệnh theo visual. ' + str(manager.simulation_error or 'mirror unavailable'))
        if not config.GAME_ONLY and not options.no_viewer:
            try:
                launch_options.check_viewer_assets(root)
                viewer = launch_options.ViewerServer(root, options.viewer_port)
                viewer.start(config.TELEMETRY_PORT, unavailable_reason=reason,
                             telemetry_available=bridge is not None)
            except (OSError, FileNotFoundError) as exc:
                reason = f'Viewer unavailable: {exc}; check assets or --viewer-port'
                if viewer is not None:
                    viewer.close()
                    viewer = None
        if cancelled is not None and cancelled.is_set():
            raise RuntimeError('Startup cancelled')
        return manager, telemetry, viewer, reason
    except Exception:
        rollback_session(manager, telemetry, viewer, state)
        raise
