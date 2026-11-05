"""Authorized isolated open test; no joint/mode/enable/gripper-close commands.

Default execution is disabled. --execute requires the operator's explicit
authorization in the active conversation, empty jaws and direct observation.
"""
import argparse
import asyncio
from datetime import datetime
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def pulse_channel_once(controller, channel, records, sleep=time.sleep, check=lambda: None):
    if type(channel) is not int or channel not in (0, 1):
        raise ValueError("Only Tool DO0 or DO1 may be tested")
    def set_output(channel, value):
        row = {"channel": channel, "value": value, "started": time.time()}
        records.append(row)
        try:
            result = controller.SetToolDO(channel, value, 0, 0)
            row.update(result=result, finished=time.time())
            if result != 0:
                raise RuntimeError(f"SetToolDO({channel},{value}) failed: {result}")
        except Exception as exc:
            row["error"] = str(exc)
            raise

    # No ON command if either initial OFF fails.
    initial_errors = []
    for output_channel in (0, 1):
        try:
            set_output(output_channel, 0)
        except Exception as exc:
            initial_errors.append(str(exc))
    if initial_errors:
        raise RuntimeError("Initial OFF not confirmed; no ON: " + "; ".join(initial_errors))
    sleep(.10)
    try:
        check()
        set_output(channel, 1)  # Exactly one ON attempt, never replayed.
        sleep(.30)
    finally:
        errors = []
        for output_channel in (0, 1):
            try:
                set_output(output_channel, 0)
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError("OFF not confirmed; operator must stop gripper power: " + "; ".join(errors))


def pulse_open_once(controller, records, sleep=time.sleep, check=lambda: None):
    return pulse_channel_once(controller, 1, records, sleep=sleep, check=check)


async def fresh_idle_samples():
    import websockets
    samples = []
    async with websockets.connect("ws://127.0.0.1:8765", open_timeout=2) as ws:
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline and len(samples) < 3:
            s = json.loads(await asyncio.wait_for(ws.recv(), timeout=1))
            if s.get("type") != "robot_state":
                continue
            stamp = s.get("measurement_timestamp")
            if not isinstance(stamp, (int, float)) or not 0 <= time.time()-stamp < .3:
                continue
            if samples and stamp <= samples[-1]["measurement_timestamp"]:
                continue
            if not (s.get("source") == "PHYSICAL" and s.get("robot_model") == "FR3"
                    and s.get("controller_ip") == "192.168.58.2"
                    and s.get("connected") and s.get("joints_valid") and s.get("tcp_valid")
                    and s.get("motion_state") == "IDLE" and s.get("trajectory_stage") == "IDLE"
                    and not s.get("last_error")
                    and s.get("command_context", {}).get("commands_allowed") is False):
                raise RuntimeError("Robot/app not in isolated idle diagnostic state")
            samples.append(s)
    if len(samples) < 3:
        raise RuntimeError("Missing three distinct fresh measured states")
    if max(max(s["joints"][j] for s in samples)-min(s["joints"][j] for s in samples)
           for j in range(6)) > .01:
        raise RuntimeError("Arm is not stationary")
    return samples


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--channel", type=int, choices=(0, 1), default=1)
    args = parser.parse_args()
    if not args.execute:
        parser.error("No physical command without --execute and current user authorization")
    from src.hardware.rpc_transport import BoundedRPCProxy
    evidence = {"started_at": datetime.now().astimezone().isoformat(), "calls": [],
                "authorization": "User swapped gripper control wires, confirmed empty jaws and direct observation, requested close/open test",
                "scope": f"One DO{args.channel} pulse .30s; both OFF before/after; no arm/mode/enable/reset command",
                "tested_channel": args.channel, "direction_after_rewire": "UNVERIFIED"}
    out = Path(__file__).parent / (f"rewire-channel{args.channel}-result-" + datetime.now().strftime("%H%M%S") + ".json")
    controller = BoundedRPCProxy("http://192.168.58.2:20003", timeout_s=.5)
    try:
        evidence["samples"] = asyncio.run(fresh_idle_samples())
        def check():
            if time.time() - evidence["samples"][-1]["measurement_timestamp"] > .5:
                raise RuntimeError("Measured preflight expired")
            fault = controller.GetRobotErrorCode()
            evidence["fault_before"] = fault
            if fault != [0, 0, 0]:
                raise RuntimeError("Controller fault; no open pulse")
        pulse_channel_once(controller, args.channel, evidence["calls"], check=check)
        evidence["fault_after"] = controller.GetRobotErrorCode()
        evidence["result"] = "ONE_CHANNEL_PULSE_ACKNOWLEDGED_AND_BOTH_OFF_ACKNOWLEDGED"
        evidence["physical_jaw_result"] = "AWAITING_OPERATOR_OBSERVATION"
    except Exception as exc:
        evidence["result"] = "FAILED_OR_NOT_DISPATCHED"
        evidence["error"] = str(exc)
    finally:
        evidence["finished_at"] = datetime.now().astimezone().isoformat()
        out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in evidence.items() if k != "samples"}, indent=2))
    if "error" in evidence:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
