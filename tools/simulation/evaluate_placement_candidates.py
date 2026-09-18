#!/usr/bin/env python3
"""
Evaluate Board Placement Candidates under 90° orientation.
Tests candidates across d in [0, 25] mm and H in [25, 50] mm.
Collects metrics for the engineering report.
"""

import json
import math
from pathlib import Path
import sys
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.simulation.placement import BoardPlacementState, BoardPlacementAnalyzer
from src.simulation.kinematics.fr3 import FR3Kinematics
from src.simulation.kinematics.urdf_chain import Pose3D, rpy_to_matrix
from src.simulation.physics.collision_guard import FR3CollisionGuard
from src.simulation.physics.world import VirtualPhysicalWorld
from src.simulation.virtual_fr3_backend import VirtualFR3Backend

import pybullet as p_bullet


def get_min_clearance_mm(guard, joints_rad):
    client = guard.world.client_id
    robot_id = guard.world.robot_body_id
    board_id = guard.world.board_body_id
    sync_fn = getattr(guard.world, "sync_robot_collision_configuration", getattr(guard.world, "sync_robot_configuration", None))
    if sync_fn:
        sync_fn(joints_rad)
    p_bullet.performCollisionDetection(physicsClientId=client)
    min_dist_m = float("inf")
    pts = p_bullet.getClosestPoints(robot_id, board_id, distance=0.1, physicsClientId=client)
    for pt in pts:
        min_dist_m = min(min_dist_m, float(pt[8]))
    for l1 in range(-1, 6):
        for l2 in range(l1 + 1, 6):
            if (l1, l2) in guard.IGNORED_ADJACENT_PAIRS:
                continue
            pts = p_bullet.getClosestPoints(robot_id, robot_id, distance=0.1, linkIndexA=l1, linkIndexB=l2, physicsClientId=client)
            for pt in pts:
                min_dist_m = min(min_dist_m, float(pt[8]))
    return min_dist_m * 1000.0 if math.isfinite(min_dist_m) else 100.0


def solve_candidate(backend, guard, d_mm, H_mm, z_off_mm=0.0):
    state = BoardPlacementState.compute(
        forward_shift_mm=d_mm,
        safe_transit_height_mm=H_mm,
        board_height_offset_mm=z_off_mm,
        board_yaw_deg=90.0,
    )
    z_surf = state.board_surface_z_robot_m
    z_gr = z_surf + 0.004715
    z_ap = z_surf + (H_mm / 1000.0)
    target_tool_rpy = [180.0, 0.0, 90.0]

    analyzer = BoardPlacementAnalyzer(kinematics=backend.kinematics)
    geo_metrics = analyzer.compute_geometric_precheck(
        forward_shift_mm=d_mm,
        safe_transit_height_mm=H_mm,
        board_height_offset_mm=z_off_mm,
        board_yaw_deg=90.0,
    )
    reach_margin_mm = min(geo_metrics["grasp_reach_margin_mm"], geo_metrics["approach_reach_margin_mm"])
    farthest_flange_reach_mm = max(geo_metrics["far_grasp_distance_mm"], geo_metrics["far_approach_distance_mm"])

    cells = [(r, c) for r in range(10) for c in range(9)]
    cells.sort(key=lambda rc: abs(rc[0] - 4.5) + abs(rc[1] - 4.0))

    solved_gr = {}
    solved_ap = {}
    worst_cond = 0.0
    min_joint_margin_rad = float("inf")
    min_col_clearance_mm = float("inf")

    kin = backend.kinematics
    base_seeds = [
        np.array([-0.785, -1.0, 1.8, -2.2, -1.571, -0.785]),
        np.array([0.0, -0.785, 1.571, -0.785, -1.571, 0.0]),
        np.array([-1.57, -1.2, 1.8, -2.1, -1.571, -1.57]),
        np.array([-2.3, -1.0, 1.8, -2.2, -1.571, -2.3]),
        np.array([0.8, -1.0, 1.8, -2.2, -1.571, 0.8]),
    ]

    land_passed = 0
    lift_passed = 0
    failed_cells = []

    for r, c in cells:
        p_gr = state.cell_to_robot_xyz(r, c, 0.004715)
        p_ap = state.cell_to_robot_xyz(r, c, H_mm / 1000.0)
        pose_gr_mm = [p_gr[0] * 1000.0, p_gr[1] * 1000.0, p_gr[2] * 1000.0] + target_tool_rpy
        pose_ap_mm = [p_ap[0] * 1000.0, p_ap[1] * 1000.0, p_ap[2] * 1000.0] + target_tool_rpy

        cand_seeds = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            if (r + dr, c + dc) in solved_gr:
                cand_seeds.append(solved_gr[(r + dr, c + dc)])
        cand_seeds.extend(base_seeds)

        # Approach IK
        res_ap = backend.solve_tcp_ik(pose_ap_mm, seed_joints=cand_seeds[0] if cand_seeds else None, allow_multi_seed=True)
        if not res_ap.success:
            for s in cand_seeds:
                res_ap = backend.solve_tcp_ik(pose_ap_mm, seed_joints=s, allow_multi_seed=False)
                if res_ap.success:
                    break
        if not res_ap.success:
            failed_cells.append((r, c, "Approach IK failed"))
            continue

        col_ap = guard.validate_configuration(res_ap.joints_rad)
        if not col_ap.safe:
            failed_cells.append((r, c, f"Approach collision: {col_ap.failure_reason}"))
            continue
        solved_ap[(r, c)] = res_ap.joints_rad

        # Grasp IK
        res_gr = backend.solve_tcp_ik(pose_gr_mm, seed_joints=res_ap.joints_rad, allow_multi_seed=False)
        if not res_gr.success:
            for s in cand_seeds:
                res_gr = backend.solve_tcp_ik(pose_gr_mm, seed_joints=s, allow_multi_seed=False)
                if res_gr.success:
                    break
        if not res_gr.success:
            failed_cells.append((r, c, "Grasp IK failed"))
            continue

        col_gr = guard.validate_configuration(res_gr.joints_rad, allowed_grasp_piece_id="*")
        if not col_gr.safe:
            failed_cells.append((r, c, f"Grasp collision: {col_gr.failure_reason}"))
            continue
        solved_gr[(r, c)] = res_gr.joints_rad

        worst_cond = max(worst_cond, res_ap.condition_number, res_gr.condition_number)
        _, m_ap = kin.chain.check_joint_limits(res_ap.joints_rad)
        _, m_gr = kin.chain.check_joint_limits(res_gr.joints_rad)
        min_joint_margin_rad = min(min_joint_margin_rad, min(m_ap), min(m_gr))

        # LAND MoveL
        land_plan = backend.plan_cartesian(res_ap.joints_rad, pose_gr_mm, samples=15, allowed_grasp_piece_id="*")
        if not land_plan.success:
            failed_cells.append((r, c, f"LAND MoveL failed: {land_plan.failure_reason}"))
            continue
        land_passed += 1

        # LIFT MoveL
        start_lift = land_plan.final_q if land_plan.final_q is not None else res_gr.joints_rad
        lift_plan = backend.plan_cartesian(start_lift, pose_ap_mm, samples=15, allowed_grasp_piece_id="*")
        if not lift_plan.success:
            failed_cells.append((r, c, f"LIFT MoveL failed: {lift_plan.failure_reason}"))
            continue
        lift_passed += 1

    local_pass_count = min(len(solved_gr), land_passed, lift_passed)
    all_local_passed = (local_pass_count == 90)

    if all_local_passed:
        for rc in [(0, 0), (0, 8), (9, 0), (9, 8), (4, 0), (5, 0), (4, 4)]:
            min_col_clearance_mm = min(min_col_clearance_mm, get_min_clearance_mm(guard, solved_gr[rc]))
            min_col_clearance_mm = min(min_col_clearance_mm, get_min_clearance_mm(guard, solved_ap[rc]))

    # Chained Route Validation across corners and cross-board
    chained_route_passed = 0
    total_chained_routes = 0
    if all_local_passed:
        test_pairs = [
            ((0, 0), (9, 8)),
            ((9, 8), (0, 0)),
            ((0, 8), (9, 0)),
            ((9, 0), (0, 8)),
            ((0, 4), (9, 4)),
            ((9, 4), (0, 4)),
            ((4, 0), (4, 8)),
            ((4, 8), (4, 0)),
        ]
        total_chained_routes = len(test_pairs)
        for src, dst in test_pairs:
            q_src_app = solved_ap[src]
            p_dst_ap = state.cell_to_robot_xyz(dst[0], dst[1], H_mm / 1000.0)
            pose_dst_ap_mm = [p_dst_ap[0] * 1000.0, p_dst_ap[1] * 1000.0, p_dst_ap[2] * 1000.0] + target_tool_rpy
            p_dst_gr = state.cell_to_robot_xyz(dst[0], dst[1], 0.004715)
            pose_dst_gr_mm = [p_dst_gr[0] * 1000.0, p_dst_gr[1] * 1000.0, p_dst_gr[2] * 1000.0] + target_tool_rpy

            transit_plan = backend.plan_cartesian(q_src_app, pose_dst_ap_mm, samples=15, check_collision=True)
            if not transit_plan.success:
                continue

            land_dst = backend.plan_cartesian(transit_plan.final_q, pose_dst_gr_mm, samples=15, check_collision=True)
            if not land_dst.success:
                continue

            lift_dst = backend.plan_cartesian(land_dst.final_q, pose_dst_ap_mm, samples=15, check_collision=True)
            if not lift_dst.success:
                continue

            chained_route_passed += 1

    return {
        "d_mm": d_mm,
        "H_mm": H_mm,
        "z_off_mm": z_off_mm,
        "local_passed": local_pass_count,
        "all_local_passed": all_local_passed,
        "failed_cells_sample": failed_cells[:3],
        "chained_passed": chained_route_passed,
        "total_chained": total_chained_routes,
        "worst_reach_margin_mm": round(reach_margin_mm, 2),
        "farthest_flange_reach_mm": round(farthest_flange_reach_mm, 2),
        "min_col_clearance_mm": round(min_col_clearance_mm, 2) if math.isfinite(min_col_clearance_mm) else 0.0,
        "min_joint_margin_deg": round(math.degrees(min_joint_margin_rad), 2) if math.isfinite(min_joint_margin_rad) else 0.0,
        "worst_cond": round(worst_cond, 2),
        "solved_gr": solved_gr,
        "solved_ap": solved_ap,
    }


def main():
    world = VirtualPhysicalWorld()
    guard = FR3CollisionGuard(world)
    backend = VirtualFR3Backend()

    candidates = [
        (0.0, 30.0), (0.0, 40.0), (0.0, 50.0),
        (5.0, 30.0), (5.0, 40.0), (5.0, 50.0),
        (10.0, 30.0), (10.0, 35.0), (10.0, 40.0), (10.0, 45.0),
        (15.0, 30.0), (15.0, 35.0), (15.0, 40.0), (15.0, 45.0),
        (20.0, 30.0), (20.0, 35.0), (20.0, 40.0), (20.0, 45.0),
        (25.0, 35.0), (25.0, 40.0),
    ]

    header = f"{'d(mm)':>6} {'H(mm)':>6} {'Z(mm)':>6} {'Local(90)':>10} {'Chained':>9} {'ReachMarg':>10} {'MinCol(mm)':>11} {'MinJt(deg)':>11} {'WorstCond':>10}"
    print("=" * 88, flush=True)
    print("BOARD ORIENTATION 90° PLACEMENT CANDIDATE EVALUATION", flush=True)
    print(header, flush=True)
    print("=" * 88, flush=True)

    results = []
    best_candidate = None
    best_score = -1e9

    for d, H in candidates:
        res = solve_candidate(backend, guard, d, H, 0.0)
        results.append(res)
        chained_str = f"{res['chained_passed']}/{res['total_chained']}" if res['total_chained'] > 0 else "N/A"
        row_str = f"{res['d_mm']:6.1f} {res['H_mm']:6.1f} {res['z_off_mm']:6.1f} {res['local_passed']:7d}/90 {chained_str:>9} {res['worst_reach_margin_mm']:9.1f}mm {res['min_col_clearance_mm']:10.2f} {res['min_joint_margin_deg']:10.2f} {res['worst_cond']:10.2f}"
        print(row_str, flush=True)

        if not res['all_local_passed'] and res['failed_cells_sample']:
            print(f"       -> Sample failures: {res['failed_cells_sample']}", flush=True)

        if res['all_local_passed'] and res['chained_passed'] == res['total_chained'] and res['total_chained'] > 0:
            score = (
                res['worst_reach_margin_mm'] * 2.0 +
                res['min_col_clearance_mm'] * 5.0 +
                res['min_joint_margin_deg'] * 1.0 -
                res['worst_cond'] * 0.5
            )
            if score > best_score:
                best_score = score
                best_candidate = res

    print("=" * 88, flush=True)
    if best_candidate:
        print(f"SELECTED ROBUST CANDIDATE: d = {best_candidate['d_mm']:.1f} mm, H = {best_candidate['H_mm']:.1f} mm, Z = {best_candidate['z_off_mm']:.1f} mm", flush=True)
        print(f"Worst Reach Margin: {best_candidate['worst_reach_margin_mm']:.1f} mm", flush=True)
        print(f"Min Collision Clearance: {best_candidate['min_col_clearance_mm']:.2f} mm", flush=True)
        print(f"Min Joint Margin: {best_candidate['min_joint_margin_deg']:.2f} deg", flush=True)
        print(f"Worst Condition Number: {best_candidate['worst_cond']:.2f}", flush=True)
    else:
        print("NO CANDIDATE ACHIEVED FULL LOCAL + CHAINED PASS!", flush=True)

    world.close()


if __name__ == "__main__":
    main()
