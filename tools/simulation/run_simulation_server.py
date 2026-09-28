#!/usr/bin/env python3
"""
Interactive Virtual FAIRINO FR3 Simulation Server.
Runs TelemetryPublisher (WebSocket ws://127.0.0.1:8765) and VirtualXiangqiSimulation.
Accepts commands from 3D Viewer (EXECUTE_3STAGE, SET_GRIPPER, RESET, STOP).
"""

import argparse
from pathlib import Path
import sys
import time

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)

from src.hardware.telemetry_publisher import TelemetryPublisher
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.runtime import VirtualXiangqiSimulation
from src.simulation.virtual_fr3_backend import VirtualFR3Backend


def main():
    parser = argparse.ArgumentParser(description="Virtual FR3 Simulation Server")
    parser.add_argument("--host", default="127.0.0.1", help="WebSocket host")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket port")
    parser.add_argument("--speed-factor", type=float, default=0.25, help="Trajectory speed factor (default 0.25 for safe commissioning)")
    parser.add_argument("--disable-collision-guard", action="store_true", help="Disable collision guard (allow forced motion)")
    parser.add_argument("--robot-ip", default="192.168.58.2", help="Robot controller IP for hardware pose sync")
    parser.add_argument("--no-sync-physical", action="store_true", help="Do not sync initial pose from physical robot")
    args = parser.parse_args()

    print("=" * 65)
    print("   VIRTUAL FAIRINO FR3 SIMULATION SERVER")
    print(f"   WebSocket: ws://{args.host}:{args.port}")
    print(f"   Viewer:    http://127.0.0.1:8085/")
    print("   Authority: Single Authoritative Python Runtime")
    print(f"   Guard:     {'DISABLED (FORCED MOTION ALLOWED)' if args.disable_collision_guard else 'ACTIVE (FAIL-SAFE)'}")
    print("=" * 65)

    telemetry = TelemetryPublisher.get_instance(host=args.host, port=args.port, robot_model="FR3")
    telemetry.start()

    world = VirtualPhysicalWorld()
    backend = VirtualFR3Backend(telemetry_publisher=telemetry, default_speed_factor=args.speed_factor)
    sim = VirtualXiangqiSimulation(backend=backend, world=world, telemetry=telemetry, enable_collision_guard=not args.disable_collision_guard)
    sim.connect()

    # Sync initial joints from physical robot if reachable
    if not args.no_sync_physical:
        try:
            from src.hardware.backends.physical_fr3 import PhysicalFR3Backend
            phys = PhysicalFR3Backend(ip=args.robot_ip, dry_run=False)
            if phys.connect():
                snap = phys.get_state_snapshot()
                print(f"[SYNC] Đã kết nối FR3 thật tại {args.robot_ip}! Đồng bộ vị trí ban đầu: {[round(q, 1) for q in snap.joints_deg]}")
                backend.set_joints_direct(snap.joints_deg)
                telemetry.source = "VIRTUAL_SYNCED_FROM_PHYSICAL"
                telemetry.controller_ip = args.robot_ip
                phys.disconnect()
            else:
                telemetry.source = "VIRTUAL"
        except Exception as e:
            print(f"[SYNC] Bỏ qua đồng bộ robot thật: {e}")
            telemetry.source = "VIRTUAL"
    else:
        telemetry.source = "VIRTUAL"

    def command_logger(cmd):
        cmd_name = cmd.get("command") or cmd.get("action")
        print(f"[COMMAND] << Received viewer command: {cmd_name} | {cmd}", flush=True)
    telemetry.register_command_handler(command_logger)

    print("\n[READY] Server running. Listening for viewer commands...")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        sim.stop()
        telemetry.stop()
        print("Server stopped cleanly.")


if __name__ == "__main__":
    main()
