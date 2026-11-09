"""Bounded virtual-only reproduction: game reply -> real Bullet -> local WS.

No engine/API request, camera, SDK, or physical backend is initialized.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.update(DRY_RUN="1", ROBOT_BACKEND="VIRTUAL", SDL_VIDEODRIVER="dummy")

import config
from src.core.ai_execution import execute_ai_move
from src.core.game_state import GameState
from src.core.session_profile import make_profile
from src.hardware.hardware_manager import HardwareManager
from src.hardware.telemetry_publisher import TelemetryPublisher
from websockets.sync.client import connect


def main():
    config.DRY_RUN = True
    config.ROBOT_BACKEND = "VIRTUAL"
    config.GAME_ONLY = False
    config.GAME_MODE = "HUMAN_VS_ROBOT"
    profile = make_profile("HUMAN_VS_ROBOT", "VIRTUAL")
    config.SESSION_PROFILE = profile
    cfg = SimpleNamespace(DRY_RUN=True, ROBOT_BACKEND="VIRTUAL", GAME_ONLY=False,
                          GAME_MODE="HUMAN_VS_ROBOT", SESSION_PROFILE=profile,
                          SIMULATION_PROFILE="fast")
    hw = HardwareManager(cfg, ROOT)
    telemetry = TelemetryPublisher(port=0, robot_model="FR3")
    frames, snapshots, errors = [], [], []
    ready, done = threading.Event(), threading.Event()
    receiver = None
    report = {"scope": "VIRTUAL_ONLY", "physical_actuation": "NOT RUN"}
    try:
        hw._init_robot()
        hw.backend.add_state_listener(lambda snap: snapshots.append({
            "joints": list(snap.joints_deg), "stage": snap.trajectory_stage,
            "motion_state": snap.motion_state, "timestamp": snap.timestamp}))
        state = GameState(allow_mouse_move=True)
        state.session_profile = profile
        state.api_client.send_move_update_board = Mock()
        hw.game_state = state
        state._execution_binding_provider = hw.capture_execution_binding
        telemetry.command_context_provider = hw.viewer_command_context
        telemetry.start()
        hw.setup_digital_twin(telemetry=telemetry, start=False)
        state.set_board_observer(hw.sync_committed_board)
        assert state.sync_current_board()
        hw.twin_bridge.start()

        def receive():
            try:
                with connect(f"ws://127.0.0.1:{telemetry.port}", open_timeout=5) as socket:
                    ready.set()
                    deadline = time.monotonic() + 90
                    while not done.is_set() and time.monotonic() < deadline:
                        try:
                            frames.append(json.loads(socket.recv(timeout=.25)))
                        except TimeoutError:
                            continue
            except Exception as exc:
                errors.append(repr(exc))
                ready.set()

        receiver = threading.Thread(target=receive, daemon=True)
        receiver.start()
        assert ready.wait(6) and not errors, errors
        time.sleep(.2)
        initial = list(hw.backend.get_state_snapshot().joints_deg)
        assert state.process_human_move((4, 6), (4, 5), "r_P")
        started = time.monotonic()
        reply = execute_ai_move(state, hw, ((7, 2), (4, 2)), dry_run=True)
        report.update(reply_success=reply, reply_error=state.move_sync_error,
                      duration_s=round(time.monotonic()-started, 3),
                      initial_joints=initial,
                      final_joints=list(hw.backend.get_state_snapshot().joints_deg),
                      final_fen=state.current_fen,
                      placement=hw.simulation_runtime.placement_state.to_dict())
        time.sleep(.25)
    finally:
        done.set()
        if receiver is not None:
            receiver.join(3)
        hw.close_simulation()
        telemetry.stop()
        hw.motion_worker.close()
    robot_frames = [frame for frame in frames if frame.get("type") == "robot_state"]
    distinct = lambda rows: len({tuple(round(float(v), 3) for v in row["joints"]) for row in rows})
    report.update(backend_samples=len(snapshots), backend_distinct_joints=distinct(snapshots),
                  websocket_packets=len(frames), websocket_robot_packets=len(robot_frames),
                  websocket_distinct_joints=distinct(robot_frames), receiver_errors=errors,
                  source_values=sorted({frame.get("source", "") for frame in robot_frames}))
    output = Path(__file__).parent
    (output / "motion-telemetry.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (output / "motion-frames.json").write_text(json.dumps(frames), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("reply_success") and report["websocket_distinct_joints"] > 2 and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
