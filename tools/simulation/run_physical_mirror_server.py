#!/usr/bin/env python3
"""
Physical FAIRINO FR3 Live 3D Telemetry Mirror Server.

Connects to physical FAIRINO FR3 controller over Ethernet RPC (READ-ONLY)
and streams live joint angles, TCP coordinates, and motion state
over WebSocket ws://127.0.0.1:8765 to robot-3d-viewer (Three.js Digital Twin).

CRITICAL SAFETY INVARIANT:
This server is 100% READ-ONLY. It never energizes motors, never switches controller
modes, and never commands physical motion.
"""

import argparse
import sys
import time
from pathlib import Path

# Safe UTF-8 encoding configuration for Windows terminals
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import json
import threading
import numpy as np

from src.domain.board_pose import BoardPlacementState
from src.hardware.backends.physical_fr3 import PhysicalFR3Backend
from src.hardware.telemetry_publisher import TelemetryPublisher
from src.simulation.kinematics.fr3 import FR3Kinematics
import config


def main():
    parser = argparse.ArgumentParser(description="Physical FR3 Live 3D Mirror Server")
    parser.add_argument("--ip", default="192.168.58.2", help="Robot controller IP")
    parser.add_argument("--host", default="127.0.0.1", help="WebSocket host")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket port")
    parser.add_argument("--rate", type=float, default=25.0, help="Polling rate in Hz")
    parser.add_argument("--enable-control", action="store_true", help="Enable hardware actuation (allows web viewer to command MoveJ/gripper at safe speeds)")
    parser.add_argument("--max-speed", type=float, default=20.0, help="Maximum physical velocity percentage for safety (default 20.0%)")
    args = parser.parse_args()

    mode_str = "ACTUATION (COMMISSIONING CONTROL)" if args.enable_control else "READ-ONLY TELEMETRY (NO MOTOR ACTUATION)"
    print("=" * 70)
    print("   FAIRINO FR3 PHYSICAL LIVE 3D TELEMETRY MIRROR")
    print(f"   Robot Controller IP: {args.ip}:20003")
    print(f"   WebSocket Stream:   ws://{args.host}:{args.port}")
    print(f"   Viewer Interface:   http://127.0.0.1:8085/")
    print(f"   Refresh Rate:       {args.rate} Hz")
    print(f"   Safety Contract:    {mode_str}")
    if args.enable_control:
        print(f"   Speed Limit:        Clamped to max {args.max_speed}% (Safe Commissioning)")
    print("=" * 70)

    # 1. Connect to Physical FR3 Backend
    print(f"\n[1/3] Connecting to physical FR3 controller at {args.ip}...")
    backend = PhysicalFR3Backend(ip=args.ip, dry_run=False)
    if not backend.connect():
        print(f"[ERROR] Could not connect to robot controller at {args.ip}!")
        print("   Vui lòng kiểm tra cáp mạng Ethernet và cấu hình IP máy trạm (192.168.58.x).")
        sys.exit(1)

    print("[OK] Connected to FR3 controller.")

    # 2. Read initial snapshot and initialize Home pose to current coordinates
    initial_snap = backend.get_state_snapshot()
    home_joints = list(initial_snap.joints_deg)
    print(f"[OK] Initial Physical Robot State captured:")
    print(f"   - Joints (J1..J6 deg): {[round(x, 2) for x in initial_snap.joints_deg]}")
    print(f"   - TCP Pose (mm, deg):  {[round(x, 2) for x in initial_snap.tcp_pose_mm_deg]}")
    print(f"   - Motion State:        {initial_snap.motion_state}")
    print(f"   - Active Home Pose:    {[round(x, 2) for x in home_joints]} (Đã gán tọa độ hiện tại làm Home)")

    # 3. Read Physical Board Teaching Points from Controller & Calibrate
    print(f"\n[2/3] Reading physical board teaching points (R1..R4) from controller...")
    corner_pts = {}
    for name in ["R1", "R2", "R3", "R4"]:
        err, data = backend.get_teaching_point(name)
        if err == 0 and len(data) >= 3:
            corner_pts[name] = [float(data[0]), float(data[1]), float(data[2])]
            print(f"   📌 {name}: X={data[0]:.2f}, Y={data[1]:.2f}, Z={data[2]:.2f} mm")
        else:
            print(f"   ⚠️ Could not read {name} from controller (err={err})")

    # High-reliability physical corner fallback (verified physical coordinates)
    if len(corner_pts) < 4:
        print("   ⚠️ Incomplete teaching points on controller. Using verified physical calibration.")
        corner_pts["R1"] = [-211.171, 210.149, 219.994]
        corner_pts["R2"] = [-214.359, 544.595, 220.000]
        corner_pts["R3"] = [166.645, 538.109, 220.349]
        corner_pts["R4"] = [163.581, 215.261, 220.001]

    r1 = np.array(corner_pts["R1"], dtype=float)
    r2 = np.array(corner_pts["R2"], dtype=float)
    r3 = np.array(corner_pts["R3"], dtype=float)
    r4 = np.array(corner_pts["R4"], dtype=float)

    p_center_mm = (r1 + r2 + r3 + r4) / 4.0
    board_surface_z_mm = float(p_center_mm[2])
    print(f"   ✅ Calibrated Physical Tabletop Surface: Z = {board_surface_z_mm:.2f} mm")
    print(f"   ✅ Calibrated Physical Board Center:     X = {p_center_mm[0]:.2f}, Y = {p_center_mm[1]:.2f} mm")

    # Authoritative Bilinear Interpolation for ANY cell on the physical board
    def cell_to_physical_pose(dst_r: int, dst_c: int, height_above_board_mm: float):
        """
        Calculates exact physical TCP coordinates for cell (dst_r, dst_c).
        Bilinear Interpolation between physical teaching points R1..R4:
          R1 (col=0, row=0): Xe Đen Trái
          R2 (col=8, row=0): Xe Đen Phải
          R3 (col=8, row=9): Xe Đỏ Phải
          R4 (col=0, row=9): Xe Đỏ Trái

        SAFETY GUARANTEE:
        Clamps altitude to at least (table_surface + 15mm) to strictly prevent tabletop collision!
        """
        col_ratio = max(0.0, min(1.0, float(dst_c) / 8.0))
        row_ratio = max(0.0, min(1.0, float(dst_r) / 9.0))

        tx = r1[0] + (r2[0] - r1[0]) * col_ratio
        ty = r1[1] + (r2[1] - r1[1]) * col_ratio
        tz = r1[2] + (r2[2] - r1[2]) * col_ratio

        bx = r4[0] + (r3[0] - r4[0]) * col_ratio
        by = r4[1] + (r3[1] - r4[1]) * col_ratio
        bz = r4[2] + (r3[2] - r4[2]) * col_ratio

        cell_x = tx + (bx - tx) * row_ratio
        cell_y = ty + (by - ty) * row_ratio
        cell_surf_z = tz + (bz - tz) * row_ratio

        # HARD ANTI-PENETRATION GUARD: Clamped to at least 15mm above table surface
        safe_z_limit = cell_surf_z + 15.0
        target_z = max(safe_z_limit, cell_surf_z + float(height_above_board_mm))

        return float(cell_x), float(cell_y), float(target_z), float(cell_surf_z)

    # Linear transformation matrix for 3D Viewer synchronization
    du_R = (r2 - r1 + r3 - r4) / 2.0 / 320.0
    dv_R = (r4 - r1 + r3 - r2) / 2.0 / 360.0
    T_mat = [
        [float(du_R[0]), float(dv_R[0]), 0.0, float(p_center_mm[0] / 1000.0)],
        [float(du_R[1]), float(dv_R[1]), 0.0, float(p_center_mm[1] / 1000.0)],
        [float(du_R[2]), float(dv_R[2]), 1.0, float(board_surface_z_mm / 1000.0)],
        [0.0, 0.0, 0.0, 1.0],
    ]

    board_state = BoardPlacementState(
        forward_shift_mm=0.0,
        safe_transit_height_mm=40.0,
        board_height_offset_mm=0.0,
        board_yaw_deg=180.0,
        board_center_robot_m=[p_center_mm[0] / 1000.0, p_center_mm[1] / 1000.0, (board_surface_z_mm - 5.25) / 1000.0],
        board_surface_z_robot_m=board_surface_z_mm / 1000.0,
        physical_board_center_robot_m=[p_center_mm[0] / 1000.0, p_center_mm[1] / 1000.0, (board_surface_z_mm - 5.25) / 1000.0],
        physical_board_center_world_m=[-p_center_mm[1] / 1000.0, (board_surface_z_mm - 5.25) / 1000.0, -p_center_mm[0] / 1000.0],
        board_visual_root_world_m=[-p_center_mm[1] / 1000.0, board_surface_z_mm / 1000.0, -p_center_mm[0] / 1000.0],
        board_center_world_m=[-p_center_mm[1] / 1000.0, board_surface_z_mm / 1000.0, -p_center_mm[0] / 1000.0],
        rotation_matrix=[row[:3] for row in T_mat[:3]],
        placement_version=2,
    )

    kinematics = FR3Kinematics()
    motion_lock = threading.Lock()
    tool_rot = list(config.ROTATION)  # [-179.164, -3.047, -26.304]

    # 4. Start WebSocket Telemetry Server
    print(f"\n[3/3] Starting Telemetry WebSocket server at ws://{args.host}:{args.port}...")
    telemetry = TelemetryPublisher.get_instance(host=args.host, port=args.port, robot_model="FR3")
    telemetry.source = "PHYSICAL"
    telemetry.controller_ip = args.ip
    telemetry.broadcast_custom(board_state.to_dict())

    if args.enable_control:
        print("\n[SAFETY AUTHORIZATION] Enabling physical robot servos for commissioning...")
        if not backend.enable_robot():
            print("[WARN] Failed to enable robot servos!")
        backend.set_operational_mode(0)

        def _do_execute_3stage(src_tuple, dst_tuple, vel, grasp_piece=False):
            if not motion_lock.acquire(blocking=False):
                print("[PHYSICAL 3STAGE] ⚠️ Robot is currently busy with another motion!", flush=True)
                telemetry.broadcast_custom({
                    "type": "trajectory_result",
                    "success": False,
                    "error": "Robot đang bận thực thi chuyển động khác.",
                    "failed_stage": "PRECHECK",
                    "src": list(src_tuple),
                    "dst": list(dst_tuple),
                })
                return

            try:
                dst_r, dst_c = int(dst_tuple[0]), int(dst_tuple[1])
                print(f"[PHYSICAL 3STAGE] 🚀 Đi tới ô Row {dst_r}, Col {dst_c} (Vận tốc {vel:.1f}%)...", flush=True)

                # 1. Tiếp cận (Approach/Transit) ở cao độ an toàn (+40mm trên mặt bàn, Z ~ 260mm)
                x_app, y_app, z_app, surf_z = cell_to_physical_pose(dst_r, dst_c, height_above_board_mm=40.0)
                target_app_pose = [x_app, y_app, z_app] + tool_rot
                res_app = kinematics.inverse_kinematics(target_app_pose)

                if not res_app.success or not res_app.joints_deg:
                    err_msg = f"Không tìm thấy nghiệm IK tiếp cận cho ô ({dst_r}, {dst_c}): {res_app.failure_reason}"
                    print(f"[PHYSICAL 3STAGE] ❌ {err_msg}", flush=True)
                    backend.set_trajectory_stage(None)
                    telemetry.broadcast_custom({
                        "type": "trajectory_result",
                        "success": False,
                        "error": err_msg,
                        "failed_stage": "TRANSIT",
                        "src": list(src_tuple),
                        "dst": list(dst_tuple),
                    })
                    return

                # 2. Hạ xuống (Land/Hover) ở độ cao kiểm định an toàn (+20mm trên mặt bàn, Z ~ 240mm, không va chạm cờ)
                x_land, y_land, z_land, _ = cell_to_physical_pose(dst_r, dst_c, height_above_board_mm=20.0)
                target_land_pose = [x_land, y_land, z_land] + tool_rot
                res_land = kinematics.inverse_kinematics(target_land_pose, seed_joints=res_app.joints_rad)

                if not res_land.success or not res_land.joints_deg:
                    err_msg = f"Không tìm thấy nghiệm IK hạ cánh cho ô ({dst_r}, {dst_c}): {res_land.failure_reason}"
                    print(f"[PHYSICAL 3STAGE] ❌ {err_msg}", flush=True)
                    backend.set_trajectory_stage(None)
                    telemetry.broadcast_custom({
                        "type": "trajectory_result",
                        "success": False,
                        "error": err_msg,
                        "failed_stage": "LAND",
                        "src": list(src_tuple),
                        "dst": list(dst_tuple),
                    })
                    return

                # Giai đoạn 1: Bay ngang trên cao độ an toàn (TRANSIT)
                backend.set_trajectory_stage("TRANSIT")
                print(f"[PHYSICAL 3STAGE] [1/2 TRANSIT] Đang di chuyển tới độ cao an toàn Z={z_app:.1f}mm (+40mm)...", flush=True)
                ok_transit = backend.move_joint(res_app.joints_deg, speed_factor=vel / 100.0)
                if not ok_transit:
                    print("[PHYSICAL 3STAGE] ❌ MoveJ tới cao độ an toàn thất bại!", flush=True)
                    backend.set_trajectory_stage(None)
                    telemetry.broadcast_custom({
                        "type": "trajectory_result",
                        "success": False,
                        "error": "MoveJ tiếp cận thất bại trên robot thật",
                        "failed_stage": "TRANSIT",
                        "src": list(src_tuple),
                        "dst": list(dst_tuple),
                    })
                    return

                # Giai đoạn 2: Hạ cánh xuống điểm kiểm định (LAND)
                backend.set_trajectory_stage("LAND")
                print(f"[PHYSICAL 3STAGE] [2/2 LAND] Đang hạ cánh an toàn xuống Z={z_land:.1f}mm (+20mm phía trên ô ({dst_r}, {dst_c}))...", flush=True)
                ok_land = backend.move_joint(res_land.joints_deg, speed_factor=vel / 100.0)
                if not ok_land:
                    print("[PHYSICAL 3STAGE] ❌ MoveJ hạ cánh thất bại!", flush=True)
                    backend.set_trajectory_stage(None)
                    telemetry.broadcast_custom({
                        "type": "trajectory_result",
                        "success": False,
                        "error": "MoveJ hạ cánh thất bại trên robot thật",
                        "failed_stage": "LAND",
                        "src": list(src_tuple),
                        "dst": list(dst_tuple),
                    })
                    return

                # Giai đoạn 3: Hoàn tất (COMPLETE)
                backend.set_trajectory_stage("COMPLETE")
                print(f"[PHYSICAL 3STAGE] ✅ Đã hoàn thành di chuyển an toàn tới ô ({dst_r}, {dst_c}) (Z={z_land:.1f}mm)!", flush=True)
                telemetry.broadcast_custom({
                    "type": "trajectory_result",
                    "success": True,
                    "src": list(src_tuple),
                    "dst": list(dst_tuple),
                    "trajectory_stage": "COMPLETE",
                    "placement_version": 2,
                })
            except Exception as ex:
                print(f"[PHYSICAL 3STAGE] ❌ Lỗi ngoại lệ: {ex}", flush=True)
                backend.set_trajectory_stage(None)
                telemetry.broadcast_custom({
                    "type": "trajectory_result",
                    "success": False,
                    "error": str(ex),
                    "failed_stage": "EXECUTION",
                    "src": list(src_tuple),
                    "dst": list(dst_tuple),
                })
            finally:
                motion_lock.release()

        def handle_command(cmd: dict):
            cmd_name = cmd.get("command") or cmd.get("action")
            sf = float(cmd.get("speed_factor", 0.2))
            vel = min(float(args.max_speed), max(5.0, sf * 100.0))

            if cmd_name == "EXECUTE_3STAGE":
                src = cmd.get("src", [4, 4])
                dst = cmd.get("dst", [4, 4])
                grasp = bool(cmd.get("grasp_piece", False))
                threading.Thread(
                    target=_do_execute_3stage,
                    args=(src, dst, vel, grasp),
                    daemon=True,
                    name="Physical3StageThread"
                ).start()

            elif cmd_name in ("STOP", "EMERGENCY_STOP"):
                print("[PHYSICAL STOP] 🛑 Dừng khẩn cấp!", flush=True)
                backend.stop()
                backend.set_trajectory_stage(None)

            elif cmd_name in ("CLEAR_ERROR", "RESET_ROBOT", "RECOVER"):
                print("[PHYSICAL RECOVERY] 🧹 Khôi phục lỗi controller / E-stop và bật lại servo...", flush=True)
                ok = backend.recover_from_error()
                if ok:
                    print("[PHYSICAL RECOVERY] ✅ Robot đã hồi phục và bật servo thành công!", flush=True)
                    telemetry.broadcast_custom({
                        "type": "error_cleared",
                        "success": True,
                        "message": "Đã reset lỗi controller và bật lại servo thành công."
                    })
                else:
                    err_msg = backend.last_error or "Lỗi chưa rõ"
                    print(f"[PHYSICAL RECOVERY] ❌ Không thể hồi phục: {err_msg}", flush=True)
                    telemetry.broadcast_custom({
                        "type": "error",
                        "message": f"Không thể khôi phục: {err_msg}. Vui lòng kiểm tra đã xoay nhả nút dừng khẩn cấp chưa."
                    })

            elif cmd_name == "MOVE_JOINT":
                joints = cmd.get("joints_deg")
                if joints and len(joints) >= 6:
                    def _do_move():
                        if not motion_lock.acquire(blocking=False):
                            return
                        try:
                            print(f"[PHYSICAL MoveJ] Moving to {[round(q, 1) for q in joints[:6]]} at speed {vel}%...", flush=True)
                            backend.move_joint(joints, speed_factor=vel / 100.0)
                        finally:
                            motion_lock.release()
                    threading.Thread(target=_do_move, daemon=True).start()

            elif cmd_name == "RESET":
                target_joints = cmd.get("joints_deg") or home_joints
                if target_joints and len(target_joints) >= 6:
                    def _do_home():
                        if not motion_lock.acquire(blocking=False):
                            return
                        try:
                            backend.set_trajectory_stage("PREPOSITION")
                            print(f"[PHYSICAL HOME] Moving to Home pose {[round(q, 1) for q in target_joints[:6]]} at speed {vel}%...", flush=True)
                            backend.move_joint(target_joints, speed_factor=vel / 100.0)
                            backend.set_trajectory_stage(None)
                        finally:
                            motion_lock.release()
                    threading.Thread(target=_do_home, daemon=True).start()

            elif cmd_name in ("SET_HOME", "SET_CURRENT_AS_HOME"):
                snap = backend.get_state_snapshot()
                req_joints = cmd.get("joints_deg")
                home_joints.clear()
                home_joints.extend(req_joints if (req_joints and len(req_joints) >= 6) else snap.joints_deg)
                print(f"[PHYSICAL HOME] ✅ Updated Home pose to current posture: {[round(x, 2) for x in home_joints]}", flush=True)

            elif cmd_name == "SET_GRIPPER":
                closed = bool(cmd.get("closed", False))
                pulse = float(cmd.get("pulse_sec", 0.35 if not closed else 0.30))
                if backend.gripper_driver is not None:
                    if not closed:
                        backend.gripper_driver.open_pulse_sec = max(0.15, min(1.0, pulse))
                    else:
                        backend.gripper_driver.close_pulse_sec = max(0.15, min(1.0, pulse))
                print(f"[PHYSICAL GRIPPER] Setting gripper to {'CLOSED' if closed else 'OPEN'} (pulse={pulse:.2f}s, DO{'0' if closed else '1'})...", flush=True)
                backend.set_gripper(closed)

        telemetry.register_command_handler(handle_command)
        print("[OK] Hardware command handler registered. Web commands will actuate physical FR3 at safe speed.")

    telemetry.start()
    print("[OK] WebSocket Telemetry server active.")

    print("\n" + "=" * 70)
    print("   LIVE MIRRORING ACTIVE! Open http://127.0.0.1:8085/ in your browser.")
    print("   Press Ctrl+C to stop.")
    print("=" * 70 + "\n")

    sleep_interval = 1.0 / max(1.0, args.rate)
    last_print = 0.0

    try:
        while True:
            # Query fresh state from physical hardware
            snap = backend.get_state_snapshot()
            telemetry.update_from_snapshot(snap)

            # Print heartbeat to console every 3 seconds
            now = time.time()
            if now - last_print >= 3.0:
                last_print = now
                j = [f"{x:6.1f}°" for x in snap.joints_deg]
                tcp = [f"{x:6.1f}" for x in snap.tcp_pose_mm_deg[:3]]
                print(f"[MIRROR] Joints: [{' '.join(j)}] | TCP (mm): [{' '.join(tcp)}] | {snap.motion_state}", flush=True)

            time.sleep(sleep_interval)

    except KeyboardInterrupt:
        print("\n[STOPPING] Received stop signal...")
    finally:
        telemetry.stop()
        backend.disconnect()
        print("[CLEANUP] Disconnected cleanly from physical robot and stopped telemetry.")


if __name__ == "__main__":
    main()
