"""Standalone before/after lifecycle replay; no pytest or physical SDK used."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.core import game_state
from src.core.self_play_controller import SelfPlayController
from src.motion.result import MotionExecutionResult


class OfflineAPI:
    room_id = None
    pending = False

    def ensure_match(self, **kwargs): pass
    def send_move_update_board(self, fen): pass
    def end_match(self, **kwargs): pass


def replay(controller_class, phase):
    # Replace transport before constructing GameState: no HTTP worker/network.
    game_state.TuongKyDaiSuClient = lambda *args: OfflineAPI()
    state = game_state.GameState()
    calls = []
    def execute(**kwargs):
        calls.append({key: kwargs[key] for key in ('s_col', 's_row', 'd_col', 'd_row')})
        return MotionExecutionResult.ok()
    hw = SimpleNamespace(config=SimpleNamespace(ROBOT_BACKEND='VIRTUAL'), dry_run=True,
        simulation_runtime=object(), is_robot_ready=True, execute_piece_move=execute,
        ai_ctrl=SimpleNamespace(pick_move=lambda *args, **kwargs: ((4,6),(4,5))))
    ctrl = controller_class(state, hw)
    transitions = []
    def record(label):
        transitions.append(dict(event=label, status=ctrl.status.value, fen=state.current_fen,
            pending=state.pending_ai_move is not None, motion_calls=len(calls),
            committed_moves=len(state.move_history), worker_alive=bool(ctrl._thread and ctrl._thread.is_alive())))
    assert ctrl.start() and ctrl.request_next_move()
    ctrl._thread.join(2)
    assert not ctrl._thread.is_alive()
    if phase == 'moving':
        ctrl.tick(); ctrl._thread.join(2); assert not ctrl._thread.is_alive()
    record('worker finished, tick has not consumed result')
    restarted = ctrl.start()
    record('F6 start requested')
    ctrl.tick()
    if ctrl._thread and ctrl._thread.is_alive(): ctrl._thread.join(2)
    ctrl.tick()
    record('tick consumed any remaining result')
    return dict(phase=phase, restarted=restarted, transitions=transitions,
        retained_and_committed=not restarted and len(state.move_history)==1 and len(calls)==1)


if __name__ == '__main__':
    out = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location('baseline_selfplay', out/'baseline/src/core/self_play_controller.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    before = [replay(module.SelfPlayController, phase) for phase in ('thinking', 'moving')]
    after = [replay(SelfPlayController, phase) for phase in ('thinking', 'moving')]
    stress = [replay(SelfPlayController, ('thinking', 'moving')[i%2]) for i in range(100)]
    result = dict(hardware='mock executor; no camera, SDK, HTTP, sockets or physics',
        before=before, after=after, stress_runs=len(stress),
        stress_passed=sum(item['retained_and_committed'] for item in stress))
    (out/'worker-schedule.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    assert all(item['restarted'] and not item['retained_and_committed'] for item in before)
    assert all(item['retained_and_committed'] for item in after+stress)
    print('Baseline loses unpolled result in both phases; fixed retains and commits exactly once: 100/100 replays')
