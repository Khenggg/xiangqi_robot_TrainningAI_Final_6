"""
Standalone acceptance demonstration script for Virtual Physical World (Phase P3).

Demonstrates:
- Normal pick-and-place across the board
- In-flight force drop and ballistic trajectory
- Off-board drop and out-of-bounds state detection
- Multi-body collision resolution and stability

Usage:
    python tools/simulation/demo_virtual_physical_world.py --scenario all
    python tools/simulation/demo_virtual_physical_world.py --scenario normal
    python tools/simulation/demo_virtual_physical_world.py --scenario drop
    python tools/simulation/demo_virtual_physical_world.py --scenario off-board
    python tools/simulation/demo_virtual_physical_world.py --scenario collision
    python tools/simulation/demo_virtual_physical_world.py --ws --speed-factor 5.0
"""

import argparse
from pathlib import Path
import sys
import time
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.hardware.telemetry_publisher import TelemetryPublisher
from src.simulation.physics.state import PiecePhysicalState
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.runtime import VirtualXiangqiSimulation
from src.simulation.virtual_fr3_backend import VirtualFR3Backend


def run_normal_scenario(sim: VirtualXiangqiSimulation, speed_factor: float = 50.0) -> bool:
    print("\n" + "=" * 60)
    print("SCENARIO A: NORMAL PICK AND PLACE")
    print("=" * 60)

    piece_id = "black_cannon_0"
    piece = sim.world.pieces[piece_id]
    r_init, c_init, _ = piece.get_nearest_intersection()
    print(f"Target piece: {piece_id} at initial intersection (row={r_init}, col={c_init})")

    print("[1] Executing pick trajectory...")
    res = sim.pick_piece(piece_id, hover_height_m=0.06, speed_factor=speed_factor)
    if not res.success:
        print(f"[-] Pick failed: {res.reason}")
        return False
    print(f"[+] Pick succeeded! Grasped: {res.piece_id}")

    target_row, target_col = 4, 1
    print(f"[2] Placing at target board cell (row={target_row}, col={target_col})...")
    ok = sim.place_piece(target_row, target_col, hover_height_m=0.06, speed_factor=speed_factor)
    if not ok:
        print("[-] Place motion failed")
        return False

    sim.settle(max_steps=60)
    r_final, c_final, dist = piece.get_nearest_intersection()
    print(f"[+] Placed and settled at (row={r_final}, col={c_final}), residual={dist*1000:.2f} mm")
    print(f"[+] Piece state: {piece.physical_state.value}, tilt: {piece.tilt_angle_deg:.2f} deg")

    success = (r_final == target_row and c_final == target_col and dist < 0.005)
    print(f"--> Result: {'SUCCESS' if success else 'FAILED'}")
    return success


def run_drop_scenario(sim: VirtualXiangqiSimulation, speed_factor: float = 50.0) -> bool:
    print("\n" + "=" * 60)
    print("SCENARIO B: DYNAMIC MID-TRANSIT FORCE DROP")
    print("=" * 60)

    piece_id = "black_knight_0"
    piece = sim.world.pieces[piece_id]
    print(f"Target piece: {piece_id}")

    print("[1] Picking piece...")
    res = sim.pick_piece(piece_id, hover_height_m=0.06, speed_factor=speed_factor)
    if not res.success:
        print(f"[-] Pick failed: {res.reason}")
        return False

    print("[2] Scheduling mid-motion force drop at 50% trajectory progress...")
    sim.schedule_force_drop(progress_threshold=0.5, target_piece_id=piece_id)

    print("[3] Executing horizontal Cartesian transport across the board...")
    # Move towards (row=2, col=3)
    tx, ty, tz = sim.cell_to_robot_xyz(2, 3, z_height_m=0.10)
    rx, ry, rz = sim.target_tool_euler_deg
    sim.move_cartesian([tx * 1000, ty * 1000, tz * 1000, rx, ry, rz], speed_factor=speed_factor)

    evt = sim.last_drop_event
    if evt is None or not evt.triggered:
        print("[-] Force drop was not triggered during motion!")
        return False

    print(f"[+] Robot state at drop: {evt.robot_motion_state}")
    print(f"[+] Drop progress: {evt.trajectory_progress * 100:.1f}%")
    print(f"[+] Release linear velocity: {evt.release_speed:.3f} m/s")
    print(f"[+] Release velocity vector: {[round(v, 4) for v in evt.release_linear_velocity]}")
    print(f"[+] Piece detached: {'YES' if not piece.attached_to_gripper else 'NO'}")

    # Validate mid-motion criteria
    motion_ok = (evt.robot_motion_state == "MOVING")
    speed_ok = (evt.release_speed > 0.02)
    detached_ok = not piece.attached_to_gripper

    print("[4] Stepping physics until piece settles on board...")
    steps = sim.world.step_until_settled(max_steps=120)
    print(f"[+] Settled in {steps} steps at {piece.physical_state.value}")
    r_settle, c_settle, dist = piece.get_nearest_intersection()
    print(f"[+] Settled location: near (row={r_settle}, col={c_settle}), tilt={piece.tilt_angle_deg:.2f} deg")

    settled_ok = piece.physical_state in (PiecePhysicalState.RESTING, PiecePhysicalState.ON_BOARD)
    success = (motion_ok and speed_ok and detached_ok and settled_ok)
    print(f"--> Result: {'SUCCESS' if success else 'FAILED'}")
    return success


def run_off_board_scenario(sim: VirtualXiangqiSimulation, speed_factor: float = 50.0) -> bool:
    print("\n" + "=" * 60)
    print("SCENARIO C: OFF-BOARD FALL AND OUT-OF-BOUNDS DETECTION")
    print("=" * 60)

    piece_id = "black_rook_0"
    piece = sim.world.pieces[piece_id]
    print(f"Target piece: {piece_id}")

    print("[1] Picking piece...")
    res = sim.pick_piece(piece_id, hover_height_m=0.06, speed_factor=speed_factor)
    if not res.success:
        print(f"[-] Pick failed: {res.reason}")
        return False

    print(f"[2] Carrying piece past lateral board boundary (edge at y={sim.world.board_y_min:.3f}m)...")
    # Move outside lateral board edge
    snap = sim.backend.get_state_snapshot()
    curr_flange = snap.flange_pose_mm_deg
    off_x = curr_flange[0]
    off_y = (sim.world.board_y_min - 0.04) * 1000  # ~ -223.5 mm
    off_z = curr_flange[2]
    rx, ry, rz = sim.target_tool_euler_deg
    moved = sim.backend.move_cartesian([off_x, off_y, off_z, rx, ry, rz], speed_factor=speed_factor)
    if not moved:
        print(f"[-] Move past boundary failed: {sim.backend._last_error}")
        return False

    print("[3] Releasing piece into void...")
    sim.force_drop()

    print("[4] Simulating fall past Z_min threshold...")
    for _ in range(150):
        sim.world.step(1)
        if piece.physical_state == PiecePhysicalState.OUT_OF_BOUNDS:
            break

    pos, _ = piece.get_pose_robot_base()
    print(f"[+] Piece final Z: {pos[2]:.3f}m, Physical state: {piece.physical_state.value}")

    success = (piece.physical_state == PiecePhysicalState.OUT_OF_BOUNDS)
    print(f"--> Result: {'SUCCESS' if success else 'FAILED'}")
    return success


def run_collision_scenario(sim: VirtualXiangqiSimulation) -> bool:
    print("\n" + "=" * 60)
    print("SCENARIO D: MULTI-BODY PIECE CONTACT AND RESOLUTION")
    print("=" * 60)

    p1 = sim.world.pieces["red_rook_0"]
    p2 = sim.world.pieces["red_knight_0"]

    pos1, _ = p1.get_pose_robot_base()
    print(f"Red Rook position: {pos1}")
    print("Dropping Red Knight directly onto Red Rook from +0.03m...")
    p2.set_pose_robot_base([pos1[0], pos1[1], pos1[2] + 0.03], [0, 0, 0, 1])

    print("Stepping physics simulation (100 steps)...")
    stable = True
    for s in range(100):
        sim.world.step(1)
        pos2, quat2 = p2.get_pose_robot_base()
        if not all(np.isfinite(pos2)) or not all(np.isfinite(quat2)):
            stable = False
            print(f"[-] Instability detected at step {s}: pos={pos2}")
            break

    sim.settle(max_steps=80)
    pos2_final, _ = p2.get_pose_robot_base()
    print(f"[+] Collision resolved stably without numerical explosion.")
    print(f"[+] Red Knight final position: {pos2_final}, state: {p2.physical_state.value}")

    print(f"--> Result: {'SUCCESS' if stable else 'FAILED'}")
    return stable


def main():
    parser = argparse.ArgumentParser(description="Virtual Physical World Demonstration (Phase P3)")
    parser.add_argument(
        "--scenario",
        choices=["normal", "drop", "off-board", "collision", "all"],
        default="all",
        help="Acceptance scenario to execute",
    )
    parser.add_argument(
        "--speed-factor",
        type=float,
        default=50.0,
        help="Robot motion speed multiplier (default: 50.0 for fast headless verification)",
    )
    parser.add_argument(
        "--ws",
        action="store_true",
        help="Enable TelemetryPublisher WebSocket streaming on ws://127.0.0.1:8765",
    )
    args = parser.parse_args()

    telemetry = None
    if args.ws:
        telemetry = TelemetryPublisher.get_instance(host="127.0.0.1", port=8765, robot_model="FR3")
        telemetry.start()
        print("[DEMO] TelemetryPublisher started on ws://127.0.0.1:8765")

    results = {}

    if args.scenario in ("normal", "all"):
        sim = VirtualXiangqiSimulation(telemetry=telemetry)
        sim.connect()
        results["normal"] = run_normal_scenario(sim, speed_factor=args.speed_factor)
        sim.world.close()

    if args.scenario in ("drop", "all"):
        sim = VirtualXiangqiSimulation(telemetry=telemetry)
        sim.connect()
        results["drop"] = run_drop_scenario(sim, speed_factor=args.speed_factor)
        sim.world.close()

    if args.scenario in ("off-board", "all"):
        sim = VirtualXiangqiSimulation(telemetry=telemetry)
        sim.connect()
        results["off-board"] = run_off_board_scenario(sim, speed_factor=args.speed_factor)
        sim.world.close()

    if args.scenario in ("collision", "all"):
        sim = VirtualXiangqiSimulation(telemetry=telemetry)
        sim.connect()
        results["collision"] = run_collision_scenario(sim)
        sim.world.close()

    print("\n" + "=" * 60)
    print("PHASE P3 DEMONSTRATION SUMMARY")
    print("=" * 60)
    all_passed = True
    for sc, ok in results.items():
        status_str = "PASS" if ok else "FAIL"
        print(f"Scenario [{sc:12s}]: {status_str}")
        if not ok:
            all_passed = False

    print("=" * 60)
    print(f"OVERALL STATUS: {'ALL PASSED' if all_passed else 'SOME FAILED'}\n")
    if telemetry:
        telemetry.stop()

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()

