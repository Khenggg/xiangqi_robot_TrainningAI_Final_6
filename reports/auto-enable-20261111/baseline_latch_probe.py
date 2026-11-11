"""Reproduce 973da04 using only a temp journal and mocked physical IO.

Run from the repository root with its venv and PYTHONPATH set to the root.
No application process, live journal, camera or controller is opened.
"""
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.core.game_state import GameState
from src.ui.input_handler import InputHandler


def main():
    scope = {}
    code = subprocess.check_output(['git', 'show', '973da04:src/core/automatic_physical_startup.py'])
    exec(compile(code.decode('utf-8-sig'), '973da04:automatic_physical_startup.py', 'exec'), scope)
    flags = ('recovery_required', 'physical_sync_fault',
             'manual_override_active', 'snapshot_continue_required')
    results = {'source_commit': '973da04', 'physical_io': 'MOCKED'}
    with patch('src.core.game_state.TuongKyDaiSuClient', lambda *a, **k: Mock(room_id=None)), \
            TemporaryDirectory(prefix='xiangqi-auto-enable-baseline-') as folder:
        old = GameState()
        old.attach_journal(Path(folder), 'PHYSICAL', 'HUMAN_VS_HUMAN_ROBOT', fresh_start=True)
        old.recovery_required = old.physical_sync_fault = True
        old.persist_checkpoint('RECOVERY_REQUIRED')
        old.close_journal()
        state = GameState()
        try:
            state.attach_journal(Path(folder), 'PHYSICAL', 'HUMAN_VS_HUMAN_ROBOT', fresh_start=True)
            results['fresh_start'] = {name: getattr(state, name) for name in flags}
            hw = SimpleNamespace(
                profile=SimpleNamespace(physical_robot_enabled=True, game_mode='HUMAN_VS_HUMAN_ROBOT'),
                dry_run=False, config=SimpleNamespace(AUTO_ENABLE_PHYSICAL_ON_STARTUP=True,
                                                       ROBOT_BACKEND='PHYSICAL'),
                motion_worker=SimpleNamespace(busy=False, start=Mock()), is_robot_ready=False,
                stop_coordinator=SimpleNamespace(blocked=False, generation=0,
                                                  safe_for_release=Mock(return_value=True)),
                session_control=SimpleNamespace(action=None), simulation_runtime=None,
                physical_telemetry_ready=Mock(return_value=True), yolo_detector=Mock(),
                cam_monitor=Mock(), board_reconciler=object(),
                verify_physical_board=Mock(return_value=True),
                capture_baseline_if_needed=Mock(return_value=True))
            startup = scope['AutomaticPhysicalStartup'](state, hw)
            startup.baseline_checked = True
            hw.automatic_startup = startup
            startup.tick()
            results['first_tick'] = dict(finished=startup.finished, cancelled=startup.cancelled,
                                         worker_starts=hw.motion_worker.start.call_count)
            handler = InputHandler.__new__(InputHandler)
            handler.state, handler.hw = state, hw
            handler._board_stability_monitor = Mock()
            assert handler.resume_automatic_scanning() is True
            results['verified_resume'] = {name: getattr(state, name) for name in flags}
            startup.tick()
            results['second_tick'] = dict(finished=startup.finished, cancelled=startup.cancelled,
                                          worker_starts=hw.motion_worker.start.call_count)
            assert startup.finished and startup.cancelled and hw.motion_worker.start.call_count == 0
        finally:
            state.close_journal()
    destination = Path(__file__).with_suffix('.json')
    destination.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
