"""Manual-only diagnostic for the direct-drive two-output gripper.

This script actuates the gripper but never enables or moves the robot arm.
Keep hands, pieces, and the board clear; use one short pulse at a time.
"""
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from src.hardware import robot_sdk_core


def set_low(robot):
    """Try both outputs even if the first command fails."""
    errors = []
    for output_id in (config.GRIPPER_OPEN_DO_ID, config.GRIPPER_CLOSE_DO_ID):
        err = robot.SetToolDO(id=output_id, status=config.GRIPPER_IDLE_STATUS, block=0)
        if err != 0:
            errors.append((output_id, err))
    if errors:
        raise RuntimeError(f"Could not set gripper outputs LOW: {errors}")


def pulse(robot, label, output_id, seconds):
    set_low(robot)
    time.sleep(config.GRIPPER_DIRECTION_DEADTIME_SEC)
    print(f"{label}: DO{output_id} ON for {seconds:.2f}s")
    err = robot.SetToolDO(id=output_id, status=config.GRIPPER_ACTIVE_STATUS, block=0)
    if err != 0:
        set_low(robot)
        raise RuntimeError(f"Could not start {label}: error {err}")
    try:
        time.sleep(seconds)
    finally:
        set_low(robot)


def main():
    print("MANUAL HARDWARE TEST — Tool DO1=open, Tool DO0=close")
    print("No RobotEnable or motion commands are issued by this script.")
    print(f"Open pulse: {config.GRIPPER_OPEN_PULSE_SEC:.2f}s; "
          f"close pulse: {config.GRIPPER_CLOSE_PULSE_SEC:.2f}s")
    if input("Type ARM CLEAR to continue: ").strip() != "ARM CLEAR":
        print("Cancelled; no output was energized.")
        return

    robot = robot_sdk_core.RPC(config.ROBOT_IP)
    time.sleep(2)
    if not robot.SDK_state:
        raise RuntimeError("Robot SDK connection failed")
    try:
        set_low(robot)
        if input("Press ENTER to pulse OPEN, or type anything to skip: ") == "":
            pulse(robot, "OPEN", config.GRIPPER_OPEN_DO_ID, config.GRIPPER_OPEN_PULSE_SEC)
        if input("Press ENTER to pulse CLOSE, or type anything to skip: ") == "":
            pulse(robot, "CLOSE", config.GRIPPER_CLOSE_DO_ID, config.GRIPPER_CLOSE_PULSE_SEC)
    finally:
        set_low(robot)
        print("Both gripper outputs set LOW.")


if __name__ == "__main__":
    main()
