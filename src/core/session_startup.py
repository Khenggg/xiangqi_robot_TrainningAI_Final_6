"""Transactional session startup, executed outside the GUI thread."""
from src.core import launch_options
from src.hardware.hardware_manager import HardwareManager
from src.hardware.telemetry_publisher import TelemetryPublisher
from src.core.project_logging import event
import errno
import logging


class StartupRollbackError(RuntimeError):
    """Keep ownership of partially opened resources until the UI retires them."""
    def __init__(self, manager, telemetry, viewer, cause):
        super().__init__(f"Startup recovery required: {cause}")
        self.manager, self.telemetry, self.viewer = manager, telemetry, viewer


def _address_in_use(error):
    return (isinstance(error, OSError)
            and (error.errno in (errno.EADDRINUSE, 10048)
                 or getattr(error, "winerror", None) == 10048))


def rollback_session(manager, telemetry, viewer, state):
    """Release an incomplete session, including GUI initialization failure."""
    if hasattr(state, "set_board_observer"):
        state.set_board_observer(None)
    try:
        if hasattr(state, "close_projection_worker"):
            state.close_projection_worker()
        for resource, method in ((manager, 'cleanup'), (telemetry, 'stop'), (viewer, 'close')):
            if resource is manager and getattr(manager, "_partial_cleanup_completed", False):
                continue
            if resource is not None and callable(getattr(resource, method, None)):
                getattr(resource, method)()
        api_client = getattr(state, "api_client", None)
        if callable(getattr(api_client, "close", None)):
            api_client.close()
        if hasattr(state, "close_journal"):
            state.close_journal(clean=False)
    except Exception as exc:
        event('cleanup.failed', f'Startup rollback retained resources: {exc}', level=logging.ERROR)
        raise StartupRollbackError(manager, telemetry, viewer, exc) from exc


def build_session(config, options, root, state, cancelled=None, mode=None):
    manager = telemetry = viewer = None
    try:
        if cancelled is not None and cancelled.is_set():
            raise RuntimeError('Startup cancelled')
        from pathlib import Path
        from src.core.session_profile import configure_session
        profile = configure_session(config, options, mode=mode)
        state.session_profile = profile
        state.allow_mouse_move = profile.mouse_input == "VIRTUAL_TEST_ADAPTER"
        event("session.capabilities", "Operating permission of the selected mode", game_mode=profile.game_mode,
              requested_environment=profile.requested_environment, environment=profile.execution_environment,
              camera=profile.camera_enabled, physical_robot=profile.physical_robot_enabled,
              robot_moves=profile.robot_moves_enabled, mouse_input=profile.mouse_input)
        # Acquire the environment lease and archive the previous game before
        # opening camera/SDK resources. A second instance must fail without touching them.
        # --log-dir changes diagnostics only, never the journal/ownership domain.
        log_dir = Path(getattr(options, "log_dir", "logs"))
        if log_dir.is_absolute():
            relative_journal = Path("data") / "runtime" / f"{profile.execution_environment.lower()}.sqlite3"
            legacy_journal = (log_dir.parent / relative_journal).resolve()
            canonical_journal = (Path(root) / relative_journal).resolve()
            if legacy_journal != canonical_journal and legacy_journal.exists():
                raise RuntimeError(
                    f"Session data found at the old location: {legacy_journal}. "
                    f"Camera/robot not opened. Migrate the closed session to {canonical_journal} "
                    "before continuing; no new game is created over the pending state.")
        if hasattr(state, "attach_journal"):
            state.attach_journal(root, profile.execution_environment, profile.game_mode, fresh_start=True)
        if cancelled is not None and cancelled.is_set():
            raise RuntimeError('Startup cancelled')
        # Retain the manager even when initialize_all cannot retire a partial open.
        manager = HardwareManager(config, root)
        manager.profile = profile
        manager.startup_cancelled = cancelled
        # Initialization is read-only. If it fails, retire only the resources
        # opened here; historical receipts remain in the journal for next launch.
        initialized = manager.initialize_all()
        if initialized is not None:
            manager = initialized
        state._execution_binding_provider = getattr(manager, "capture_execution_binding", None)
        profile = getattr(manager, "profile", None) or profile
        state.session_profile = profile
        manager.game_state = state
        if getattr(state, "recovery_required", False) and hasattr(manager, "request_controlled_stop"):
            manager.request_controlled_stop("Restored session: checking controller state")
        if cancelled is not None and cancelled.is_set():
            raise RuntimeError('Startup cancelled')
        telemetry = TelemetryPublisher(host=config.TELEMETRY_HOST, port=config.TELEMETRY_PORT, robot_model='FR3')
        telemetry.command_context_provider = manager.viewer_command_context
        try:
            bridge = manager.setup_digital_twin(telemetry)
        except Exception as mirror_error:
            if not profile.physical_robot_enabled:
                raise
            event("startup.projection_unavailable", "Simulation failed; real camera/FR3 sources kept",
                  level=logging.WARNING, reason=str(mirror_error))
            manager.simulation_error = str(mirror_error)
            manager.close_simulation()
            bridge = None
            if manager.backend is not None:
                from src.digital_twin.raw_arm_relay import RawArmRelay
                bridge = RawArmRelay(manager.backend, telemetry, mirror_error)
                manager.twin_bridge = bridge
                manager.robot.motion_listener = None
                bridge.start()
        board_ready = bridge is not None and getattr(bridge, 'board_sync_available', True)
        if board_ready:
            state.set_board_observer(manager.sync_committed_board)
        if hasattr(state, "start_projection_worker"):
            state.start_projection_worker()
        if board_ready:
            if not state.sync_current_board():
                event('startup.projection_pending', "Viewer has not received the board; saved game session kept", level=logging.WARNING)
        if bridge is not None:
            try:
                telemetry.start()
            except Exception as telemetry_error:
                if (profile.execution_environment == "VIRTUAL" and profile.simulation_enabled
                        and _address_in_use(telemetry_error.__cause__)):
                    # Keep this session's publisher, handlers and cached snapshots.
                    # Never connect to or stop the process occupying the old port.
                    telemetry.stop()
                    requested_port = telemetry.port
                    telemetry.port = 0
                    telemetry.start()  # One retry; failure rolls back virtual startup.
                    event("startup.telemetry_port_changed", "Simulation uses a free WebSocket port",
                          level=logging.WARNING, requested_port=requested_port,
                          port=telemetry.port, environment="VIRTUAL")
                else:
                    event("startup.telemetry_unavailable", "WebSocket not opened; the game does not use the server occupying the port",
                          level=logging.WARNING, reason=str(telemetry_error), port=config.TELEMETRY_PORT)
                    telemetry.stop()
                    telemetry = None
                    bridge.telemetry = None
                    manager.telemetry = None
                    if manager.simulation_runtime is not None:
                        manager.simulation_runtime.telemetry = None
                        manager.backend.telemetry_publisher = None
                    manager.simulation_error = f"WebSocket unavailable: {telemetry_error}"
        uncalibrated = getattr(bridge, 'uncalibrated_board', False) or not board_ready
        reason = None if not uncalibrated or config.GAME_ONLY else (
            "Default simulation board (piece sync ON); command coordinates follow visual. " + str(manager.simulation_error or 'mirror unavailable'))
        if bridge is not None and telemetry is None:
            reason = manager.simulation_error or "WebSocket unavailable; viewer is not synchronized"
        if profile.viewer_enabled:
            try:
                launch_options.check_viewer_assets(root)
                try:
                    viewer = launch_options.ViewerServer(root, options.viewer_port)
                except OSError as viewer_error:
                    if (profile.execution_environment != "VIRTUAL" or not profile.simulation_enabled
                            or not _address_in_use(viewer_error)):
                        raise
                    viewer = launch_options.ViewerServer(root, 0)
                    event("startup.viewer_port_changed", "Simulation uses a free viewer HTTP port",
                          level=logging.WARNING, requested_port=options.viewer_port,
                          port=viewer.server.server_port, environment="VIRTUAL")
                viewer.start(telemetry.port if telemetry is not None else config.TELEMETRY_PORT, unavailable_reason=reason,
                             telemetry_available=bridge is not None and telemetry is not None)
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
