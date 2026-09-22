#!/usr/bin/env python3
"""
Regenerate shared/cell_reachability_dataset.json for all 90 Xiangqi board cells
under the authoritative 90° orientation.

Ensures:
- Single tool frame contract (flange_to_tcp = 150 mm [MEASURED_APPROXIMATE] along +Z)
- Authoritative BoardPose (+col -> -X_robot, +row -> -Y_robot, +Z_board -> +Z_robot)
- Canonical heights: grasp clearance = 4.715 mm (piece center), approach = H mm
- 100% collision-free validity via FR3CollisionGuard in PyBullet
- Verified LAND MoveL (Approach -> Grasp) and LIFT MoveL (Grasp -> Approach)
"""

import argparse
import json
import math
from pathlib import Path
import sys
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.domain.geometry import get_physical_geometry, get_canonical_tool_geometry
from src.simulation.placement import BoardPlacementState
from src.simulation.kinematics.fr3 import FR3Kinematics
from src.simulation.kinematics.urdf_chain import Pose3D, rpy_to_matrix
from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.virtual_fr3_backend import VirtualFR3Backend


def generate_dataset(
    forward_shift_mm: float = 25.0,
    safe_transit_height_mm: float = 40.0,
    board_height_offset_mm: float = 0.0,
    board_yaw_deg: float = 90.0,
    output_path: Path = _PROJECT_ROOT / "shared" / "cell_reachability_dataset.json",
):
    world = VirtualPhysicalWorld()
    world.relocate_board(forward_shift_m=forward_shift_mm / 1000.0, height_offset_m=board_height_offset_mm / 1000.0)
    guard = FR3CollisionGuard(world)
    backend = VirtualFR3Backend()
    backend.set_collision_guard(guard)
    kin = backend.kinematics
    geom = get_physical_geometry()
    tool_geom = get_canonical_tool_geometry()

    state = BoardPlacementState.compute(
        forward_shift_mm=forward_shift_mm,
        safe_transit_height_mm=safe_transit_height_mm,
        board_height_offset_mm=board_height_offset_mm,
        board_yaw_deg=board_yaw_deg,
    )

    z_board = state.board_surface_z_robot_m
    piece_h = geom.piece_height_mm / 1000.0
    z_grasp_rel = piece_h / 2.0  # 0.004715 m
    z_app_rel = safe_transit_height_mm / 1000.0  # 0.040 m
    tool_offset_z = tool_geom.flange_to_tcp_distance_m  # Canonical 0.150 m [MEASURED_APPROXIMATE]

    target_tool_rpy = [180.0, 0.0, 90.0]

    base_seeds = [
        np.array([-0.785, -1.0, 1.8, -2.2, -1.571, -0.785]),
        np.array([0.0, -0.785, 1.571, -0.785, -1.571, 0.0]),
        np.array([-1.57, -1.2, 1.8, -2.1, -1.571, -1.57]),
        np.array([-2.3, -1.0, 1.8, -2.2, -1.571, -2.3]),
        np.array([0.8, -1.0, 1.8, -2.2, -1.571, 0.8]),
        np.array([-0.8, -1.2, 1.5, -1.8, -1.571, -0.8]),
        np.array([-1.8, -1.2, 1.5, -1.8, -1.571, -1.8]),
        np.array([-0.5, -1.2, 1.8, -2.0, -1.571, -0.5]),
        np.array([-1.0, -1.2, 2.0, -2.2, -1.571, -1.0]),
        np.array([0.5, -1.2, 1.8, -2.0, -1.571, 0.5]),
        np.array([1.0, -1.2, 2.0, -2.2, -1.571, 1.0]),
        np.array([0.0, -1.0, 2.0, -2.2, -1.571, 0.0]),
    ]

    # Order cells from center outward for smooth neighbor propagation
    cells_order = [(r, c) for r in range(10) for c in range(9)]
    cells_order.sort(key=lambda rc: abs(rc[0] - 4.5) + abs(rc[1] - 4.0))

    solved_gr = {}
    solved_ap = {}
    target_service_q = np.deg2rad(backend.SERVICE_SAFE_JOINTS_DEG)

    for r, c in cells_order:
        p_gr = state.cell_to_robot_xyz(r, c, z_grasp_rel)
        p_ap = state.cell_to_robot_xyz(r, c, z_app_rel)
        pose_gr_mm = [p_gr[0] * 1000.0, p_gr[1] * 1000.0, p_gr[2] * 1000.0] + target_tool_rpy
        pose_ap_mm = [p_ap[0] * 1000.0, p_ap[1] * 1000.0, p_ap[2] * 1000.0] + target_tool_rpy

        cand_seeds = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            if (r + dr, c + dc) in solved_ap:
                cand_seeds.append(solved_ap[(r + dr, c + dc)])
        cand_seeds.extend(base_seeds)

        res_ap = None
        plan_land = None
        plan_lift = None

        for s in cand_seeds:
            cand_res = backend.solve_tcp_ik(pose_ap_mm, seed_joints=s, allow_multi_seed=False)
            if not cand_res.success:
                continue
            # Must maintain canonical downward wrist branch (J5 ~ -90 deg)
            if abs(cand_res.joints_rad[4] - (-1.570796)) > 0.3:
                continue
            if not guard.validate_configuration(cand_res.joints_rad).safe:
                continue
            land_test = backend.plan_cartesian(cand_res.joints_rad, pose_gr_mm, samples=20, allowed_grasp_piece_id="*")
            if not land_test.success:
                continue
            if not guard.validate_configuration(land_test.final_q, allowed_grasp_piece_id="*").safe:
                continue
            lift_test = backend.plan_cartesian(land_test.final_q, pose_ap_mm, samples=20, allowed_grasp_piece_id="*")
            if not lift_test.success:
                continue

            # Ensure retreat to SERVICE_SAFE is safe
            safe_retreat = True
            for s_step in range(1, 11):
                interp_q = cand_res.joints_rad + (target_service_q - cand_res.joints_rad) * (s_step / 10.0)
                if not guard.validate_configuration(interp_q).safe:
                    safe_retreat = False
                    break
            if not safe_retreat:
                continue

            res_ap = cand_res
            plan_land = land_test
            plan_lift = lift_test
            break

        assert res_ap is not None, f"Approach/Grasp IK failed or collided at ({r}, {c})"
        solved_ap[(r, c)] = res_ap.joints_rad
        solved_gr[(r, c)] = plan_land.final_q

    # Reorder sequentially by row, col for canonical dataset indexing
    cell_records = []
    for r in range(10):
        for c in range(9):
            p_gr = state.cell_to_robot_xyz(r, c, z_grasp_rel)
            q_gr = solved_gr[(r, c)]
            q_ap = solved_ap[(r, c)]
            q_gr_deg = [round(float(np.rad2deg(v)), 2) for v in q_gr]
            q_ap_deg = [round(float(np.rad2deg(v)), 2) for v in q_ap]

            cell_entry = {
                "row": r,
                "col": c,
                "x_m": round(float(p_gr[0]), 4),
                "y_m": round(float(p_gr[1]), 4),
                "reachable": True,
                "grasp_joints_deg": q_gr_deg,
                "approach_joints_deg": q_ap_deg,
                "j4_grasp_deg": q_gr_deg[3],
                "j4_approach_deg": q_ap_deg[3],
                "gripper_tip_grasp_clearance_mm": round(z_grasp_rel * 1000.0, 3),
                "gripper_tip_safe_clearance_mm": round(safe_transit_height_mm, 2),
                "flange_grasp_z_mm": round((z_board + z_grasp_rel + tool_offset_z) * 1000.0, 3),
                "flange_approach_z_mm": round((z_board + z_app_rel + tool_offset_z) * 1000.0, 3),
                "tilt_deg": 0.0,
                "penetrates_board": False,
                # Backward-compatibility fields
                "joints_deg": q_gr_deg,
                "j4_deg": q_gr_deg[3],
                "flange_z_mm": round((z_board + z_grasp_rel + tool_offset_z) * 1000.0, 3),
                "gripper_tip_clearance_mm": round(z_grasp_rel * 1000.0, 3),
            }
            cell_records.append(cell_entry)

    dataset = {
        "metadata": {
            "total_cells": 90,
            "gripper_length_m": round(tool_offset_z, 4),
            "piece_height_m": round(piece_h, 5),
            "clearance_grasp_m": round(z_grasp_rel, 6),
            "clearance_safe_lift_m": round(z_app_rel, 4),
            "flange_grasp_z_m": round(z_board + z_grasp_rel + tool_offset_z, 6),
            "flange_approach_z_m": round(z_board + z_app_rel + tool_offset_z, 6),
            "board_surface_z_m": round(z_board, 4),
            "board_thickness_m": round(geom.board_thickness_m, 4),
            "board_yaw_deg": round(board_yaw_deg, 2),
            "forward_shift_mm": round(forward_shift_mm, 2),
            "description": "Authoritative 90deg orientation 3-stage trajectory dataset: Lift -> Transit -> Land with zero collision",
        },
        "cells": cell_records,
    }

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)

    world.close()
    print(f"Successfully generated reachability dataset for 90/90 cells at {out_file}!", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Generate 90-cell reachability dataset for 90° board orientation.")
    parser.add_argument("--shift-mm", type=float, default=25.0, help="Forward shift along -X in mm (default 25.0)")
    parser.add_argument("--safe-transit-h-mm", type=float, default=40.0, help="Safe transit height H in mm (default 40.0)")
    parser.add_argument("--board-height-offset-mm", type=float, default=0.0, help="Z offset in mm (default 0.0)")
    parser.add_argument("--board-yaw-deg", type=float, default=90.0, help="Board yaw in degrees (default 90.0)")
    parser.add_argument("--output", type=Path, default=_PROJECT_ROOT / "shared" / "cell_reachability_dataset.json")

    args = parser.parse_args()
    generate_dataset(
        forward_shift_mm=args.shift_mm,
        safe_transit_height_mm=args.safe_transit_h_mm,
        board_height_offset_mm=args.board_height_offset_mm,
        board_yaw_deg=args.board_yaw_deg,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
