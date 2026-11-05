"""Read-only audit of physical teaching points and their tool/user frames.

This script NEVER enables the robot, NEVER moves the arm and NEVER commands the
gripper. It only reads controller teaching points so an operator can confirm
that R1-R4, HOMECHESS and R_Trash all belong to robot base (user 0) and to one
tool frame before physical play is authorized.

Usage (PowerShell):
    .\\.venv312\\Scripts\\python.exe tools\\diagnostics\\read_teaching_points.py
    .\\.venv312\\Scripts\\python.exe tools\\diagnostics\\read_teaching_points.py --connect
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from src.domain.board_pose_provider import parse_frame_identifier  # noqa: E402

POINT_NAMES = ("R1", "R2", "R3", "R4", "HOMECHESS", "R_Trash")


def _expected_frames() -> tuple[object, int]:
    return getattr(config, "ROBOT_TOOL_FRAME", None), int(getattr(config, "ROBOT_USER_FRAME", 0))


def _print_header():
    tool, user = _expected_frames()
    print("Physical teaching-point audit (READ-ONLY)")
    print(f"Expected tool frame: {tool if tool is not None else 'single frame returned by controller'}")
    print(f"Expected user frame: {user} (robot base)")
    print("This script does not call Mode, RobotEnable, MoveCart, MoveJ or SetToolDO.")
    print()


def _read_points(ip: str | None) -> int:
    from src.hardware import robot_VIP

    if robot_VIP.robot_sdk_core is None:
        print("ERROR: robot_sdk_core is not available in this Python environment.")
        return 2

    robot = robot_VIP.FR5Robot(ip=ip, dry_run=False)
    try:
        robot.connect()  # read-only: loads telemetry and teaching points
    except Exception as exc:
        print(f"ERROR: controller connection failed: {exc}")
        return 2

    rpc = getattr(robot, "robot", None)
    if rpc is None:
        print("ERROR: SDK handle is unavailable after connect().")
        return 2

    expected_tool, expected_user = _expected_frames()
    frames = set()
    z_values = []
    failures = 0
    print(f"{'point':<10} {'len':>4} {'tool':>5} {'user':>5}  xyz(mm)")
    print("-" * 78)
    for name in POINT_NAMES:
        code, data = rpc.GetRobotTeachingPoint(name)
        if code != 0 or not data:
            failures += 1
            print(f"{name:<10} MISSING (code={code})")
            continue
        values = list(data)
        tool = parse_frame_identifier(values[12]) if len(values) >= 14 else None
        user = parse_frame_identifier(values[13]) if len(values) >= 14 else None
        xyz = ", ".join(str(values[i]) for i in range(min(3, len(values))))
        print(f"{name:<10} {len(values):>4} {str(tool):>5} {str(user):>5}  [{xyz}]")
        if name in ("R1", "R2", "R3", "R4"):
            frames.add((tool, user))
            try:
                z_values.append(float(values[2]))
            except (TypeError, ValueError, IndexError):
                pass

    if getattr(robot, "wobj_identity_as_base", False):
        source_wobj = getattr(robot, "identity_wobj_id", None)
        frames = {(tool, 0) if user == source_wobj else (tool, user)
                  for tool, user in frames}
        print(f"APP NORMALIZATION: identity WObj {source_wobj} -> user 0 for R1-R4")

    print()
    if robot.teaching_points_error:
        failures += 1
        print(f"FRAME ERROR: {robot.teaching_points_error}")
    if len(frames) != 1:
        failures += 1
        print(f"FRAME ERROR: R1-R4 use {len(frames)} different tool/user frames: {sorted(frames)}")
    else:
        common_tool, common_user = next(iter(frames))
        if common_user != expected_user:
            failures += 1
            print(
                f"FRAME ERROR: R1-R4 user={common_user}; expected user={expected_user} "
                f"(robot base). Re-teach R1-R4 with user 0 selected on the pendant."
            )
        if expected_tool is not None and common_tool != expected_tool:
            failures += 1
            print(
                f"FRAME ERROR: R1-R4 tool={common_tool}; expected tool={expected_tool}. "
                "Re-teach R1-R4 with the configured tool frame."
            )
        if failures == 0:
            print(f"OK: R1-R4 use tool={common_tool}, user={common_user} (robot base).")

    if len(z_values) == 4:
        spread = max(z_values) - min(z_values)
        tolerance = float(getattr(config, "BOARD_CALIBRATION_Z_TOLERANCE_MM", 1.0))
        ordered = sorted(z_values)
        median = (ordered[1] + ordered[2]) / 2.0
        z_text = ", ".join(f"{value:.3f}" for value in z_values)
        print(f"R1-R4 Z (mm): [{z_text}]; median={median:.3f}; "
              f"spread={spread:.3f}; tolerance={tolerance:.3f}")
        source = str(getattr(config, "BOARD_SURFACE_Z_SOURCE", "MEASURED")).upper()
        confirmed = bool(getattr(config, "R1_R4_TAUGHT_AT_BOARD_SURFACE", False))
        print(f"BOARD_SURFACE_Z_SOURCE={source}; R1_R4_TAUGHT_AT_BOARD_SURFACE={confirmed}")
        if source == "R1_R4" and not confirmed:
            print("INFO: set R1_R4_TAUGHT_AT_BOARD_SURFACE=True only after confirming all four "
                  "points were taught at the board surface (not SAFE_Z).")
        if spread > tolerance:
            print("WARNING: R1-R4 Z spread exceeds tolerance; the four points do not describe one flat surface.")

    print()
    print("No motion or enable command was sent.")
    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connect",
        action="store_true",
        help="open a read-only SDK connection and read teaching points from the controller",
    )
    parser.add_argument("--ip", default=None, help="controller IP (default: config.ROBOT_IP)")
    args = parser.parse_args()

    _print_header()
    if not args.connect:
        print("Dry audit only. Re-run with --connect to read the controller (read-only).")
        return 0
    return _read_points(args.ip)


if __name__ == "__main__":
    raise SystemExit(main())
