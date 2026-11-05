"""Pure-mock activation cancellation probe; constructing a real SDK is forbidden."""
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.hardware.robot_VIP import FR5Robot


def run():
    entered, release = threading.Event(), threading.Event()
    trace, outcome = [], {}

    def mode(value):
        trace.append(["Mode", value])
        entered.set()
        if not release.wait(2):
            raise RuntimeError("Probe handshake timed out")
        return 0

    def enable(value):
        trace.append(["RobotEnable", value])
        return 0

    with patch("src.hardware.robot_VIP.robot_sdk_core.RPC",
               side_effect=AssertionError("Real SDK construction forbidden")):
        arm = FR5Robot(dry_run=False)
        arm.connected = True
        arm.robot = SimpleNamespace(Mode=mode, RobotEnable=enable)
        arm._validated_corners = Mock()
        arm._validate_gripper_config = Mock()

        def activate():
            try:
                outcome["activation_returned"] = arm.activate_physical_control(commissioned=True)
            except Exception as exc:
                outcome["activation_error"] = str(exc)

        worker = threading.Thread(target=activate)
        worker.start()
        try:
            if not entered.wait(1):
                raise RuntimeError("Activation did not reach Mode handshake")
            arm.latch_motion_stop()
            trace.append(["stop_latched", True])
        finally:
            release.set()
            worker.join(2)
        if worker.is_alive():
            raise RuntimeError("Probe worker did not finish")
        outcome.update(trace=trace, physical_motion_authorized=arm.physical_motion_authorized,
                       stop_latched=arm._motion_stop.is_set(), actual_hardware_calls=0)
        return outcome


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(run(), indent=2))
