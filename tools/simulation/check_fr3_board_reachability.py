#!/usr/bin/env python3
"""
Xiangqi Board Reachability Evaluation Tool for Virtual FAIRINO FR3.

Evaluates kinematic reachability across all 90 intersections (9 cols x 10 rows)
of the Xiangqi board under the authoritative FR3 kinematics and virtual scene placement.

Scene config source: shared/virtual_fr3_scene.json
"""

import argparse
import json
import math
import os
from pathlib import Path
import sys
from typing import Dict, List, Optional, Tuple
import numpy as np

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.domain.geometry import get_physical_geometry
from src.simulation.kinematics.fr3 import FR3Kinematics, IKResult, IKStatus
from src.simulation.kinematics.urdf_chain import Pose3D
from src.domain.board_pose import BoardPlacementState
from src.simulation.tool_geometry import virtual_link_to_tcp_offset_m


def evaluate_board_reachability(
    scene_config_path: Optional[Path] = None,
    kinematics: Optional[FR3Kinematics] = None,
    height_offset_m: float = 0.0,
    pos_tol_mm: float = 1.0,
    rot_tol_deg: float = 1.0,
) -> dict:
    """
    Evaluate all board intersections for a candidate height offset.
    Returns evaluation summary dict.
    """
    if scene_config_path is None:
        scene_config_path = _PROJECT_ROOT / "shared" / "virtual_fr3_scene.json"

    with open(scene_config_path, "r", encoding="utf-8") as f:
        scene = json.load(f)

    kin = kinematics or FR3Kinematics()
    board_cfg = scene["virtual_board_placement"]

    center = board_cfg["board_center_in_robot_base_m"]
    state = BoardPlacementState.compute(0., board_yaw_deg=board_cfg["board_yaw_deg"],
        nominal_board_center_robot_m=center,
        nominal_board_surface_z_m=board_cfg["board_surface_height_m"])
    if "T_robot_from_board" in board_cfg:
        T_board = np.asarray(board_cfg["T_robot_from_board"], dtype=float)
        if (T_board.shape != (4, 4) or not np.isfinite(T_board).all()
                or not np.allclose(T_board[3], [0., 0., 0., 1.])
                or not np.allclose(T_board[:3,:3].T @ T_board[:3,:3], np.eye(3), atol=1e-6)
                or not np.isclose(np.linalg.det(T_board[:3,:3]), 1., atol=1e-6)):
            raise ValueError("Invalid authoritative board transform")
        state.rotation_matrix = T_board[:3,:3].tolist()
        state.board_center_robot_m[:2] = T_board[:2,3].tolist()
        state.board_surface_z_robot_m = float(T_board[2,3])
    z_target = state.board_surface_z_m + height_offset_m
    R_target = np.array(board_cfg["target_tool_orientation_matrix"], dtype=float)
    T_tcp_to_link = np.eye(4)
    T_tcp_to_link[:3,3] = -virtual_link_to_tcp_offset_m()

    geom = get_physical_geometry()
    col_spacing = geom.board.column_spacing / 1000.0  # Derived from canonical geometry
    row_spacing = geom.board.row_spacing / 1000.0     # Derived from canonical geometry
    num_rows = geom.board.rows
    num_cols = geom.board.columns

    reachable_count = 0
    unreachable_cells = []
    worst_pos_err = 0.0
    worst_rot_err = 0.0
    min_margin_rad = float("inf")
    worst_cond = 0.0

    # Seed for smooth continuation
    q_seed = np.array([0.0, -1.0, 1.5, -2.0, -1.57, 0.0], dtype=float)

    cell_results = []

    for r in range(num_rows):
        for c in range(num_cols):
            target_xyz = state.cell_to_robot_xyz(r, c, z_rel_m=height_offset_m)

            T_target = np.eye(4, dtype=float)
            T_target[:3, :3] = R_target
            T_target[:3, 3] = target_xyz
            # URDF IK ends at wrist3_link; the requested point is the actual TCP.
            T_tcp_target = T_target.copy()
            T_target = T_target @ T_tcp_to_link

            res = kin.inverse_kinematics(
                T_target,
                seed_joints=q_seed,
                max_iterations=80,
                pos_tol_mm=min(pos_tol_mm, 0.1),
                rot_tol_deg=min(rot_tol_deg, 0.1),
            )
            if not res.success:
                # Retry with unconstrained multi-seed exploration
                res = kin.inverse_kinematics(
                    T_target,
                    seed_joints=None,
                    allow_multi_seed=True,
                    max_iterations=100,
                    pos_tol_mm=min(pos_tol_mm, 0.1),
                    rot_tol_deg=min(rot_tol_deg, 0.1),
                )

            T_link_to_tcp = np.eye(4)
            T_link_to_tcp[:3, 3] = virtual_link_to_tcp_offset_m()
            actual = kin.forward_kinematics(res.joints_rad).as_matrix() @ T_link_to_tcp
            tcp_pos_error = float(np.linalg.norm(actual[:3, 3] - T_tcp_target[:3, 3]) * 1000.)
            rotation_delta = actual[:3, :3].T @ T_tcp_target[:3, :3]
            tcp_rot_error = math.degrees(math.acos(float(np.clip((np.trace(rotation_delta)-1.)/2., -1., 1.))))
            accepted = res.success and tcp_pos_error <= pos_tol_mm and tcp_rot_error <= rot_tol_deg
            cell_data = {
                "col": c,
                "row": r,
                "target_xyz_m": target_xyz.tolist(),
                "status": res.status.value,
                "success": accepted,
                "pos_err_mm": tcp_pos_error,
                "rot_err_deg": tcp_rot_error,
                "iterations": res.iterations,
                "condition_number": res.condition_number,
            }

            if accepted:
                reachable_count += 1
                q_seed = res.joints_rad.copy()
                worst_pos_err = max(worst_pos_err, tcp_pos_error)
                worst_rot_err = max(worst_rot_err, tcp_rot_error)
                worst_cond = max(worst_cond, res.condition_number)

                _, margins = kin.chain.check_joint_limits(res.joints_rad)
                min_margin_rad = min(min_margin_rad, min(margins))
            else:
                unreachable_cells.append(cell_data)

            cell_results.append(cell_data)

    return {
        "scene_status": scene.get("status"),
        "evaluation_scope": "TCP_KINEMATICS_ONLY_NOT_COLLISION_OR_GRASP_ACCEPTANCE",
        "cell_results": cell_results,
        "robot_model": scene.get("robot_model"),
        "target_height_m": z_target,
        "total_cells": num_rows * num_cols,
        "reachable_count": reachable_count,
        "unreachable_count": len(unreachable_cells),
        "unreachable_cells": unreachable_cells,
        "worst_pos_err_mm": worst_pos_err,
        "worst_rot_err_deg": worst_rot_err,
        "min_joint_margin_deg": math.degrees(min_margin_rad) if math.isfinite(min_margin_rad) else 0.0,
        "worst_condition_number": worst_cond,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate Xiangqi board reachability with Virtual FR3.")
    parser.add_argument(
        "--scene",
        type=Path,
        default=_PROJECT_ROOT / "shared" / "virtual_fr3_scene.json",
        help="Path to virtual_fr3_scene.json",
    )
    parser.add_argument(
        "--height-offset",
        type=float,
        default=0.0,
        help="Height offset from board surface in meters (e.g. 0.03 for hover)",
    )

    args = parser.parse_args()
    summary = evaluate_board_reachability(
        scene_config_path=args.scene,
        height_offset_m=args.height_offset,
    )

    print("=" * 60)
    print("XIANGQI VIRTUAL FR3 BOARD REACHABILITY REPORT")
    print("=" * 60)
    print(f"Robot Model:              {summary['robot_model']}")
    print(f"Simulation Status:        {summary['scene_status']}")
    print(f"Target Height:            {summary['target_height_m']:.3f} m")
    print(f"Total Targets:            {summary['total_cells']}")
    print(f"Reachable Targets:        {summary['reachable_count']}/{summary['total_cells']}")
    print(f"Worst Position Residual:  {summary['worst_pos_err_mm']:.4f} mm")
    print(f"Worst Orient. Residual:   {summary['worst_rot_err_deg']:.4f} deg")
    print(f"Min Joint Limit Margin:   {summary['min_joint_margin_deg']:.2f} deg")
    print(f"Worst Condition Number:   {summary['worst_condition_number']:.2f}")
    print("=" * 60)

    if summary["unreachable_cells"]:
        print(f"UNREACHABLE CELLS ({len(summary['unreachable_cells'])}):")
        for cell in summary["unreachable_cells"]:
            print(f"  Col {cell['col']}, Row {cell['row']} at {cell['target_xyz_m']}: {cell['status']}")
        sys.exit(1)
    else:
        print("ALL 90/90 BOARD INTERSECTIONS ARE KINEMATICALLY REACHABLE!")
        sys.exit(0)


if __name__ == "__main__":
    main()
