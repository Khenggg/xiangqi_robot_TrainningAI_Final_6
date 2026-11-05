"""Read-only physical-flow audit using fake SDK/camera only. Never constructs RPC."""
import ast
import argparse
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.core import xiangqi
from src.core.game_state import GameState
from src.core.motion_worker import MotionWorker
from src.domain.game_move import MoveActor
from src.hardware.hardware_manager import HardwareManager
from src.hardware.robot_VIP import FR5Robot
from src.hardware.controlled_stop import ControlledStopCoordinator
from src.motion.result import MotionExecutionResult
from src.vision.visual_pick_estimator import GridTarget, VisualPickEstimator


def activation_after_camera_change(change):
    current = dict(connected=True, joints_valid=True, measurement_timestamp=time.time(), motion_state="IDLE")
    calls = []
    sdk = SimpleNamespace(
        Mode=Mock(side_effect=lambda value: calls.append(["Mode", value, current["motion_state"]]) or 0),
        RobotEnable=Mock(side_effect=lambda value: calls.append(["RobotEnable", value, current["motion_state"]]) or 0))
    robot = FR5Robot.__new__(FR5Robot)
    robot.dry, robot.connected, robot.robot = False, True, sdk
    robot._disable_outcome_unknown = robot._activation_owned = False
    robot._motion_stop = threading.Event()
    robot._validated_corners = Mock()
    robot._validate_gripper_config = Mock()
    hw = HardwareManager.__new__(HardwareManager)
    hw.config = SimpleNamespace(ROBOT_BACKEND="PHYSICAL")
    hw.dry_run, hw.simulation_runtime, hw.stop_coordinator = False, None, None
    hw.profile = SimpleNamespace(physical_robot_enabled=True)
    hw.robot, hw._piece_move_lock = robot, threading.Lock()
    hw.backend = SimpleNamespace(get_state_snapshot=Mock(side_effect=lambda: SimpleNamespace(**current)))
    robot.telemetry_readiness = hw.physical_telemetry_ready
    def verify(_):
        if change == "moving":
            current["motion_state"] = "MOVING"
        elif change == "stale":
            current["measurement_timestamp"] = time.time() - 3
        return True
    hw.verify_physical_board = verify
    state = SimpleNamespace(ai_thinking=False, pending_move=None, physical_sync_fault=False,
        pending_test_motion=None, recovery_required=False, mode_change_pending=False,
        pending_ai_move=None, pick_test_resume_required=False,
        move_sync_error=None, board=xiangqi.get_board(), sync_current_board=Mock(return_value=True))
    hw.game_state = state
    if change == "stop_during_mode":
        hw.stop_coordinator = ControlledStopCoordinator(hw)
        hw.motion_worker = MotionWorker()
        entered, release = threading.Event(), threading.Event()
        def mode(value):
            calls.append(["Mode", value, current["motion_state"]])
            entered.set()
            assert release.wait(2)
            return 0
        sdk.Mode.side_effect = mode
    error = None
    if change == "stop_during_mode":
        outcome = []
        hw.motion_worker.start(lambda: hw.activate_physical_game(state, commissioned=True),
                               lambda value, problem: outcome.extend((value, problem)))
        assert entered.wait(1)
        stopped = hw.stop_coordinator.begin("Operator F8 while enabling", timeout=2)
        calls.append(["operator_stop_requested", robot._motion_stop.is_set()])
        release.set()
        hw.motion_worker._thread.join(2)
        assert hw.motion_worker.poll()
        assert stopped.done.wait(2)
        stopped.thread.join(2)
        enabled, problem = outcome
        error = str(problem) if problem else None
        enabled = bool(enabled)
        hw.motion_worker.close()
    else:
        try:
            enabled = hw.activate_physical_game(state, commissioned=True)
        except RuntimeError as exc:
            enabled, error = False, str(exc)
    return dict(enabled=enabled, final_motion_state=current["motion_state"],
                final_measurement_age_s=round(time.time() - current["measurement_timestamp"], 3),
                snapshot_reads=hw.backend.get_state_snapshot.call_count, fake_sdk_calls=calls,
                error=error, final_stop_latched=robot._motion_stop.is_set(),
                final_authorized=robot.physical_motion_authorized)


def center_after_camera_loss():
    target = GridTarget(4., 6., .99, 0.)
    frames = [(object(), [(0, .99, (0, 0, 10, 10))])] * 2
    camera = SimpleNamespace(get_fresh_pick_snapshot=Mock(side_effect=[
        *frames, RuntimeError("camera disconnected on latest sample")]),
        get_health=Mock(return_value={"ready": False, "error": "camera disconnected"}))
    hw = HardwareManager.__new__(HardwareManager)
    hw.config = SimpleNamespace(GAME_ONLY=False, VISUAL_PICK_ENABLED=True,
        VISUAL_CURRENT_PICK_ENABLED=True, VISUAL_CENTER_PICK_ATTEMPTS=3,
        VISUAL_PICK_MIN_STABLE_SAMPLES=2, VISUAL_CENTER_PICK_MAX_JITTER_CELLS=.12,
        VISUAL_PICK_MAX_OFFSET_MM=6., VISUAL_PICK_OUTSIDE_MARGIN_MM=6.)
    hw.cam_monitor = camera
    hw.center_pick_estimator = SimpleNamespace(
        estimate_pick_target=Mock(return_value=target),
        aggregate_targets=VisualPickEstimator.aggregate_targets,
        last_reason="accepted", last_measurement={})
    targets = hw.get_robot_center_pick_targets({"moving": (4, 6)})
    hw.profile = SimpleNamespace(robot_moves_enabled=True)
    hw.dry_run, hw.simulation_runtime, hw.stop_coordinator, hw.twin_bridge = False, None, None, None
    hw._piece_move_lock = threading.Lock()
    hw.backend = SimpleNamespace(get_state_snapshot=lambda: SimpleNamespace(
        connected=True, joints_valid=True, measurement_timestamp=time.time(), motion_state="IDLE"))
    hw.robot = SimpleNamespace(connected=True, physical_motion_authorized=True,
                               move_piece=Mock(return_value=MotionExecutionResult.ok()))
    with patch("src.core.game_state.TuongKyDaiSuClient", return_value=Mock(token="", room_id=None)):
        state = GameState()
    state._execution_binding_provider = lambda: {"environment": "PHYSICAL", "calibration_token": "unchanged"}
    context = state.create_move_context((4, 6), (4, 5), MoveActor.ROBOT)
    state.mark_move_pending(context)
    expected, _ = xiangqi.make_temp_move(state.board, ((4, 6), (4, 5)))
    state.set_pending_physical_move(((4, 6), (4, 5)), expected, ".", "r")
    hw.game_state = state
    result = hw.execute_piece_move(s_col=4, s_row=6, d_col=4, d_row=5,
                                  is_capture=False, moving_visual_target=targets["moving"], move_context=context)
    return dict(camera_reads=camera.get_fresh_pick_snapshot.call_count,
                latest_sample=hw.last_pick_resolution["attempts_detail"][-1],
                resolution_failure=hw.last_pick_resolution["failure"],
                target_returned=targets["moving"] is not None,
                fake_motion_dispatches=hw.robot.move_piece.call_count,
                motion_reported_success=result.success, camera_health_checks=camera.get_health.call_count,
                semantic_move_guard_passed=state.pending_move is context)


def unchanged_since_previous_work(file, function, baseline):
    if baseline is None:
        return None
    def source(path):
        text = path.read_text(encoding="utf-8-sig")
        node = next(n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.FunctionDef) and n.name == function)
        return ast.get_source_segment(text, node)
    return source(Path(file)) == source(Path(baseline))


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--baseline-hardware", type=Path, help="Optional pre-task hardware_manager.py snapshot")
args = parser.parse_args()
evidence = {
    "environment": "Windows / Python " + sys.version.split()[0],
    "physical_sdk_connections": 0,
    "real_robot_or_camera_calls": 0,
    "enable_control": activation_after_camera_change("unchanged"),
    "enable_after_motion_starts": activation_after_camera_change("moving"),
    "enable_after_telemetry_expires": activation_after_camera_change("stale"),
    "stop_during_mode_with_real_coordinator_and_manager": activation_after_camera_change("stop_during_mode"),
    "center_after_camera_loss": center_after_camera_loss(),
    "pre_existing_to_recent_fresh_start_and_log_work": {
        "activate_physical_game": unchanged_since_previous_work("src/hardware/hardware_manager.py", "activate_physical_game", args.baseline_hardware),
        "get_robot_center_pick_targets": unchanged_since_previous_work("src/hardware/hardware_manager.py", "get_robot_center_pick_targets", args.baseline_hardware),
    },
}
assert evidence["enable_after_motion_starts"]["enabled"]
assert evidence["enable_after_telemetry_expires"]["enabled"]
assert evidence["enable_control"]["enabled"]
stop = evidence["stop_during_mode_with_real_coordinator_and_manager"]
assert not stop["enabled"] and stop["final_stop_latched"]
assert [call[0] for call in stop["fake_sdk_calls"]] == ["Mode", "operator_stop_requested", "RobotEnable"]
assert evidence["center_after_camera_loss"]["fake_motion_dispatches"] == 1
path = Path(__file__).with_name("parent-evidence.json")
path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
print(json.dumps(evidence, ensure_ascii=False, indent=2))
