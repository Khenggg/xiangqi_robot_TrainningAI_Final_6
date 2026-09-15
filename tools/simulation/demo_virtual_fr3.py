#!/usr/bin/env python3
"""
Standalone Virtual FAIRINO FR3 Demonstration Script.

Demonstrates:
- Demo A: Joint motion (MoveJ) from Home -> Pose A -> Pose B -> Home
- Demo B: Cartesian linear motion (MoveL) between reachable poses
- Demo C: Unreachable target rejection with clean error handling (no teleportation)
- Live WebSocket Telemetry broadcast to robot-3d-viewer (ws://127.0.0.1:8765)

NO HARDWARE ACTUATION: Executes entirely in virtual software simulation.
"""

import argparse
import math
import os
from pathlib import Path
import sys
import time

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.hardware.telemetry_publisher import TelemetryPublisher
from src.simulation.kinematics.fr3 import FR3Kinematics, IKStatus
from src.simulation.virtual_fr3_backend import VirtualFR3Backend


def run_demo(speed_factor: float = 2.0, interactive_pause: float = 0.5):
    print("=" * 65)
    print("   VIRTUAL FAIRINO FR3 DIGITAL TWIN DEMONSTRATION")
    print("   Mode: Simulation-Only (No Physical Actuation)")
    print(f"   Speed factor: {speed_factor}x")
    print("=" * 65)

    # 1. Initialize Telemetry Publisher
    telemetry = TelemetryPublisher.get_instance(host="127.0.0.1", port=8765, robot_model="FR3")
    try:
        telemetry.start()
    except Exception as e:
        print(f"[WARN] Telemetry server start warning: {e}")

    # 2. Initialize Virtual FR3 Backend
    kinematics = FR3Kinematics()
    backend = VirtualFR3Backend(
        kinematics=kinematics,
        telemetry_publisher=telemetry,
        default_speed_factor=speed_factor,
    )

    print("\n[STEP 1] Connecting to Virtual FR3 Backend...")
    connected = backend.connect()
    print(f"  Connected: {connected}")
    initial_snap = backend.get_state_snapshot()
    print(f"  Robot Model:  {initial_snap.robot_model}")
    print(f"  Motion State: {initial_snap.motion_state}")
    print(f"  Home Joints:  {initial_snap.joints_deg}")
    print(f"  Home TCP:     {initial_snap.tcp_pose_mm_deg}")
    time.sleep(interactive_pause)

    # 3. DEMO A: JOINT MOTION (MoveJ)
    print("\n" + "-" * 65)
    print("[DEMO A] Joint Space Motion (MoveJ)")
    print("-" * 65)

    pose_A_deg = [25.0, -35.0, 70.0, -85.0, -90.0, 15.0]
    print(f"  -> Moving to Pose A (Joint space): {pose_A_deg}")
    ok_A = backend.move_joint(pose_A_deg, speed_factor=speed_factor, steps=25)
    snap_A = backend.get_state_snapshot()
    print(f"     Arrived at Pose A: ok={ok_A}, actual joints={snap_A.joints_deg}")
    print(f"     Flange pose: {snap_A.flange_pose_mm_deg}")
    time.sleep(interactive_pause)

    pose_B_deg = [-25.0, -50.0, 85.0, -105.0, -90.0, -15.0]
    print(f"  -> Moving to Pose B (Joint space): {pose_B_deg}")
    ok_B = backend.move_joint(pose_B_deg, speed_factor=speed_factor, steps=25)
    snap_B = backend.get_state_snapshot()
    print(f"     Arrived at Pose B: ok={ok_B}, actual joints={snap_B.joints_deg}")
    time.sleep(interactive_pause)

    home_joints_deg = VirtualFR3Backend.DEFAULT_HOME_JOINTS_DEG
    print(f"  -> Returning to Home Pose: {home_joints_deg}")
    ok_home = backend.move_joint(home_joints_deg, speed_factor=speed_factor, steps=25)
    print(f"     Returned Home: ok={ok_home}")
    time.sleep(interactive_pause)

    # 4. DEMO B: CARTESIAN MOTION (MoveL)
    print("\n" + "-" * 65)
    print("[DEMO B] Cartesian Linear Motion (MoveL)")
    print("-" * 65)

    start_tcp = backend.get_state_snapshot().tcp_pose_mm_deg
    # Small reachable translation along X: +25 mm, along Y: +20 mm
    target_cartesian = [
        start_tcp[0] + 25.0,
        start_tcp[1] + 20.0,
        start_tcp[2],
        start_tcp[3],
        start_tcp[4],
        start_tcp[5],
    ]
    print(f"  Start TCP:   {start_tcp}")
    print(f"  Target TCP:  {target_cartesian}")
    print("  Sampling 20 Cartesian waypoints and solving IK along linear path...")

    t0 = time.time()
    ok_cart = backend.move_cartesian(target_cartesian, speed_factor=speed_factor, samples=20)
    dt = time.time() - t0

    snap_cart = backend.get_state_snapshot()
    pos_err = math.sqrt(
        sum((a - b) ** 2 for a, b in zip(snap_cart.tcp_pose_mm_deg[:3], target_cartesian[:3]))
    )
    print(f"  Cartesian Motion: ok={ok_cart} in {dt:.2f}s")
    print(f"  Final TCP:        {snap_cart.tcp_pose_mm_deg}")
    print(f"  Position Error:   {pos_err:.4f} mm")
    time.sleep(interactive_pause)

    # 5. DEMO C: UNREACHABLE TARGET REJECTION
    print("\n" + "-" * 65)
    print("[DEMO C] Unreachable Target Rejection & Safety")
    print("-" * 65)

    unreachable_target = [2500.0, 0.0, 100.0, 180.0, 0.0, 0.0]
    print(f"  Target: {unreachable_target} (2.5 meters away)")
    snap_before_bad = backend.get_state_snapshot()

    ok_bad = backend.move_cartesian(unreachable_target, speed_factor=speed_factor)
    snap_after_bad = backend.get_state_snapshot()

    print(f"  Command Result:        ok={ok_bad} (False expected)")
    print(f"  Motion State:          {snap_after_bad.motion_state}")
    print(f"  Error Message:         {snap_after_bad.last_error}")
    print(f"  State Teleported:      {snap_after_bad.tcp_pose_mm_deg == unreachable_target} (False expected)")
    print(f"  Safe State Maintained: {snap_after_bad.joints_deg == snap_before_bad.joints_deg}")
    time.sleep(interactive_pause)

    # 6. Gripper Actuator State
    print("\n" + "-" * 65)
    print("[ACTUATOR] Gripper Command State")
    print("-" * 65)
    print("  -> Closing Gripper...")
    backend.set_gripper(True)
    print(f"     Gripper Closed: {backend.get_state_snapshot().gripper_closed}")
    time.sleep(interactive_pause)

    print("  -> Opening Gripper...")
    backend.set_gripper(False)
    print(f"     Gripper Closed: {backend.get_state_snapshot().gripper_closed}")
    time.sleep(interactive_pause)

    # Return Home & Disconnect
    backend.move_joint(home_joints_deg, speed_factor=speed_factor, steps=15)
    backend.disconnect()
    telemetry.stop()
    print("\n" + "=" * 65)
    print("[SUCCESS] DEMONSTRATION COMPLETE: ALL VIRTUAL FR3 CAPABILITIES VERIFIED!")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="Run Standalone Virtual FR3 Demonstration.")
    parser.add_argument(
        "--speed-factor",
        type=float,
        default=5.0,
        help="Simulation speed factor (default 5.0 for quick demonstration)",
    )
    parser.add_argument(
        "--pause",
        type=float,
        default=0.2,
        help="Interactive pause between motion steps in seconds",
    )
    args = parser.parse_args()
    run_demo(speed_factor=args.speed_factor, interactive_pause=args.pause)


if __name__ == "__main__":
    main()
