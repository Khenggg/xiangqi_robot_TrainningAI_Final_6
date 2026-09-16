#!/usr/bin/env python3
"""
Regenerate shared/cell_reachability_dataset.json for all 90 Xiangqi board cells.
Ensures single tool frame contract, canonical heights, and 100% collision-free validity
via FR3CollisionGuard in PyBullet.
"""

import json
import math
from pathlib import Path
import sys
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.domain.geometry import get_physical_geometry
from src.simulation.kinematics.fr3 import FR3Kinematics
from src.simulation.kinematics.urdf_chain import Pose3D, rpy_to_matrix
from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.physics.world import VirtualPhysicalWorld


def generate_dataset():
    world = VirtualPhysicalWorld()
    guard = FR3CollisionGuard(world)
    kin = FR3Kinematics()
    geom = get_physical_geometry()

    scene_path = _PROJECT_ROOT / "shared" / "virtual_fr3_scene.json"
    with open(scene_path, "r", encoding="utf-8") as f:
        scene = json.load(f)

    b_cfg = scene["virtual_board_placement"]
    x0, y0, z_board = b_cfg["grid_origin_in_robot_base_m"]
    col_spacing = geom.board.column_spacing / 1000.0
    row_spacing = geom.board.row_spacing / 1000.0

    tool_offset = np.array(scene["tool_transform"]["flange_to_tcp_xyz_m"])
    T_flange_tcp = np.eye(4)
    T_flange_tcp[:3, 3] = tool_offset
    T_tcp_flange = np.linalg.inv(T_flange_tcp)

    R_down = np.array(b_cfg["target_tool_orientation_matrix"], dtype=float)

    piece_h = geom.piece_height_mm / 1000.0
    z_grasp = z_board + (piece_h / 2.0)  # Piece center: 0.015215 m
    z_approach = z_board + 0.070        # Safe transit: 0.0805 m

    # Existing dataset for reference seeds
    old_dataset_path = _PROJECT_ROOT / "shared" / "cell_reachability_dataset.json"
    with open(old_dataset_path, "r", encoding="utf-8") as f:
        old_data = json.load(f)
    old_cells_map = {(c["row"], c["col"]): c for c in old_data.get("cells", [])}

    cells = []
    total = 90
    processed = 0

    # Special seeds for row 0 cells that prevent link 0 <-> link 2 self-collision
    row0_seeds = {
        2: [-7.28, -69.25, 113.89, 45.35, 90.0, 172.72],
        3: [-21.11, -71.58, 117.51, 44.07, 90.0, 158.89],
        4: [-34.54, -72.4, 118.76, 43.65, 90.0, 145.46],
        5: [-46.19, -71.67, 117.65, 44.02, 90.0, 133.82],
        6: [-55.22, -69.21, 113.84, 45.37, 90.0, 124.79],
    }

    for r in range(10):
        x = x0 - r * row_spacing
        for c in range(9):
            y = y0 + c * col_spacing
            old_c = old_cells_map.get((r, c), {})

            # 1. Approach Configuration
            T_tcp_app = np.eye(4)
            T_tcp_app[:3, :3] = R_down
            T_tcp_app[:3, 3] = [x, y, z_approach]
            T_fl_app = T_tcp_app @ T_tcp_flange

            q_app_seed = np.deg2rad(old_c.get("approach_joints_deg", [0.0, -45.0, 90.0, -45.0, -90.0, 0.0]))
            ik_app = kin.inverse_kinematics(
                Pose3D.from_matrix(T_fl_app),
                seed_joints=q_app_seed,
                allow_multi_seed=False,
            )
            if not ik_app.success:
                ik_app = kin.inverse_kinematics(
                    Pose3D.from_matrix(T_fl_app),
                    seed_joints=q_app_seed,
                    allow_multi_seed=True,
                )
            assert ik_app.success, f"Approach IK failed at ({r}, {c})"
            col_app = guard.validate_configuration(ik_app.joints_rad)
            assert col_app.safe, f"Approach collision at ({r}, {c}): {col_app.failure_reason}"

            # 2. Grasp Configuration
            T_tcp_gr = np.eye(4)
            T_tcp_gr[:3, :3] = R_down
            T_tcp_gr[:3, 3] = [x, y, z_grasp]
            T_fl_gr = T_tcp_gr @ T_tcp_flange

            if r == 0 and c in row0_seeds:
                q_gr_seed = np.deg2rad(row0_seeds[c])
            else:
                q_gr_seed = np.deg2rad(old_c.get("grasp_joints_deg", ik_app.joints_rad))

            ik_gr = kin.inverse_kinematics(
                Pose3D.from_matrix(T_fl_gr),
                seed_joints=q_gr_seed,
                allow_multi_seed=False,
            )
            if not ik_gr.success:
                ik_gr = kin.inverse_kinematics(
                    Pose3D.from_matrix(T_fl_gr),
                    seed_joints=q_gr_seed,
                    allow_multi_seed=True,
                )
            assert ik_gr.success, f"Grasp IK failed at ({r}, {c})"
            col_gr = guard.validate_configuration(ik_gr.joints_rad, allowed_grasp_piece_id="*")
            assert col_gr.safe, f"Grasp collision at ({r}, {c}): {col_gr.failure_reason}"

            q_app_deg = [round(float(np.rad2deg(v)), 2) for v in ik_app.joints_rad]
            q_gr_deg = [round(float(np.rad2deg(v)), 2) for v in ik_gr.joints_rad]

            cell_entry = {
                "row": r,
                "col": c,
                "x_m": round(x, 4),
                "y_m": round(y, 4),
                "reachable": True,
                "grasp_joints_deg": q_gr_deg,
                "approach_joints_deg": q_app_deg,
                "j4_grasp_deg": q_gr_deg[3],
                "j4_approach_deg": q_app_deg[3],
                "gripper_tip_grasp_clearance_mm": round((z_grasp - z_board) * 1000.0, 3),
                "gripper_tip_safe_clearance_mm": 70.0,
                "flange_grasp_z_mm": round((z_grasp + tool_offset[2]) * 1000.0, 3),
                "flange_approach_z_mm": round((z_approach + tool_offset[2]) * 1000.0, 3),
                "tilt_deg": 0.0,
                "penetrates_board": False,
                # Backward-compatibility fields
                "joints_deg": q_gr_deg,
                "j4_deg": q_gr_deg[3],
                "flange_z_mm": round((z_grasp + tool_offset[2]) * 1000.0, 3),
                "gripper_tip_clearance_mm": round((z_grasp - z_board) * 1000.0, 3),
            }
            cells.append(cell_entry)
            processed += 1

    dataset = {
        "metadata": {
            "total_cells": 90,
            "gripper_length_m": round(float(tool_offset[2]), 4),
            "piece_height_m": round(piece_h, 5),
            "clearance_grasp_m": round(piece_h / 2.0, 6),
            "clearance_safe_lift_m": 0.070,
            "flange_grasp_z_m": round(z_grasp + tool_offset[2], 6),
            "flange_approach_z_m": round(z_approach + tool_offset[2], 6),
            "board_surface_z_m": round(z_board, 4),
            "board_thickness_m": round(geom.board_thickness_m, 4),
            "description": "Authoritative 3-stage trajectory dataset: Lift (+70mm) -> Transit -> Land (+4.715mm piece center) with zero collision",
        },
        "cells": cells,
    }

    out_path = _PROJECT_ROOT / "shared" / "cell_reachability_dataset.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)

    world.close()
    print(f"Successfully generated reachability dataset for {processed}/90 cells!")


if __name__ == "__main__":
    generate_dataset()
