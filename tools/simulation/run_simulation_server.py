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

from src.hardware.telemetry_publisher import TelemetryPublisher
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.runtime import VirtualXiangqiSimulation
from src.simulation.virtual_fr3_backend import VirtualFR3Backend


def main():
    parser = argparse.ArgumentParser(description="Virtual FR3 Simulation Server")
    parser.add_argument("--host", default="127.0.0.1", help="WebSocket host")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket port")
    parser.add_argument("--speed-factor", type=float, default=25.0, help="Trajectory speed factor")
    args = parser.parse_args()

    print("=" * 65)
    print("   VIRTUAL FAIRINO FR3 SIMULATION SERVER")
    print(f"   WebSocket: ws://{args.host}:{args.port}")
    print(f"   Viewer:    http://127.0.0.1:8085/")
    print("   Authority: Single Authoritative Python Runtime")
    print("=" * 65)

    telemetry = TelemetryPublisher.get_instance(host=args.host, port=args.port, robot_model="FR3")
    telemetry.start()

    world = VirtualPhysicalWorld()
    backend = VirtualFR3Backend(default_speed_factor=args.speed_factor)
    sim = VirtualXiangqiSimulation(backend=backend, world=world, telemetry=telemetry, enable_collision_guard=True)
    sim.connect()

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
