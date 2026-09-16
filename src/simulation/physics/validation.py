"""
Strict fail-fast validation for canonical simulation configurations:
- virtual_physics.json
- virtual_gripper_profile.json
- xiangqi_start_layout.json
"""

import math
from typing import Any, Dict, List, Set, Tuple


def _is_finite_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(float(v)) and not isinstance(v, bool)


def validate_physics_config(cfg: Dict[str, Any]) -> None:
    """
    Validate shared/virtual_physics.json strictly without silent fallbacks.
    Raises ValueError on any missing or invalid field.
    """
    if not isinstance(cfg, dict):
        raise ValueError("Physics config must be a JSON object")

    if cfg.get("schema_version") != 1:
        raise ValueError(f"Unsupported physics schema_version: {cfg.get('schema_version')} (expected 1)")

    if "status" not in cfg or not isinstance(cfg["status"], str):
        raise ValueError("Physics config missing required 'status' metadata")

    grav = cfg.get("gravity_m_s2")
    if not isinstance(grav, (list, tuple)) or len(grav) != 3 or not all(_is_finite_num(x) for x in grav):
        raise ValueError(f"Invalid 'gravity_m_s2': {grav} (must be 3 finite numbers)")

    ts = cfg.get("fixed_timestep_s")
    if not _is_finite_num(ts) or float(ts) <= 0.0:
        raise ValueError(f"Invalid 'fixed_timestep_s': {ts} (must be positive number)")

    iters = cfg.get("solver_iterations")
    if not isinstance(iters, int) or isinstance(iters, bool) or iters < 1:
        raise ValueError(f"Invalid 'solver_iterations': {iters} (must be integer >= 1)")

    # Board physics
    board = cfg.get("board")
    if not isinstance(board, dict):
        raise ValueError("Missing 'board' physics block")
    thick = board.get("collision_thickness_m")
    if not _is_finite_num(thick) or float(thick) <= 0.0:
        raise ValueError(f"Invalid board 'collision_thickness_m': {thick}")
    if not _is_finite_num(board.get("lateral_friction")) or float(board["lateral_friction"]) < 0.0:
        raise ValueError(f"Invalid board 'lateral_friction': {board.get('lateral_friction')}")
    if not _is_finite_num(board.get("spinning_friction")) or float(board["spinning_friction"]) < 0.0:
        raise ValueError(f"Invalid board 'spinning_friction': {board.get('spinning_friction')}")
    restitution_b = board.get("restitution")
    if not _is_finite_num(restitution_b) or not (0.0 <= float(restitution_b) <= 1.0):
        raise ValueError(f"Invalid board 'restitution': {restitution_b} (must be in [0, 1])")

    # Piece physics
    piece = cfg.get("piece")
    if not isinstance(piece, dict):
        raise ValueError("Missing 'piece' physics block")
    mass = piece.get("mass_kg")
    if not _is_finite_num(mass) or float(mass) <= 0.0:
        raise ValueError(f"Invalid piece 'mass_kg': {mass} (must be > 0)")
    for f_key in ("lateral_friction", "rolling_friction", "spinning_friction"):
        val = piece.get(f_key)
        if not _is_finite_num(val) or float(val) < 0.0:
            raise ValueError(f"Invalid piece '{f_key}': {val} (must be >= 0)")
    restitution_p = piece.get("restitution")
    if not _is_finite_num(restitution_p) or not (0.0 <= float(restitution_p) <= 1.0):
        raise ValueError(f"Invalid piece 'restitution': {restitution_p} (must be in [0, 1])")

    # Settling parameters
    settle = cfg.get("settling")
    if not isinstance(settle, dict):
        raise ValueError("Missing 'settling' physics block")
    max_steps = settle.get("max_settle_steps")
    if not isinstance(max_steps, int) or isinstance(max_steps, bool) or max_steps < 1:
        raise ValueError(f"Invalid 'max_settle_steps': {max_steps} (must be int >= 1)")
    if not _is_finite_num(settle.get("linear_velocity_threshold_m_s")) or float(settle["linear_velocity_threshold_m_s"]) <= 0.0:
        raise ValueError(f"Invalid 'linear_velocity_threshold_m_s': {settle.get('linear_velocity_threshold_m_s')}")
    if not _is_finite_num(settle.get("angular_velocity_threshold_rad_s")) or float(settle["angular_velocity_threshold_rad_s"]) <= 0.0:
        raise ValueError(f"Invalid 'angular_velocity_threshold_rad_s': {settle.get('angular_velocity_threshold_rad_s')}")
    consec = settle.get("consecutive_settled_steps")
    if not isinstance(consec, int) or isinstance(consec, bool) or consec < 1:
        raise ValueError(f"Invalid 'consecutive_settled_steps': {consec} (must be int >= 1)")

    # Out of bounds
    oob = cfg.get("out_of_bounds")
    if not isinstance(oob, dict):
        raise ValueError("Missing 'out_of_bounds' physics block")
    if not _is_finite_num(oob.get("z_min_m")):
        raise ValueError(f"Invalid out_of_bounds 'z_min_m': {oob.get('z_min_m')}")
    if not _is_finite_num(oob.get("xy_boundary_margin_m")) or float(oob["xy_boundary_margin_m"]) <= 0.0:
        raise ValueError(f"Invalid out_of_bounds 'xy_boundary_margin_m': {oob.get('xy_boundary_margin_m')}")


def validate_gripper_profile(cfg: Dict[str, Any]) -> None:
    """
    Validate shared/virtual_gripper_profile.json strictly.
    Raises ValueError on any missing or invalid field.
    """
    if not isinstance(cfg, dict):
        raise ValueError("Gripper profile must be a JSON object")

    if cfg.get("schema_version") != 1:
        raise ValueError(f"Unsupported gripper profile schema_version: {cfg.get('schema_version')} (expected 1)")

    if "status" not in cfg or not isinstance(cfg["status"], str):
        raise ValueError("Gripper profile missing required 'status' metadata")

    model = cfg.get("gripper_model")
    if not model or not isinstance(model, str):
        raise ValueError("Gripper profile missing non-empty 'gripper_model'")

    # Palm
    palm = cfg.get("palm")
    if not isinstance(palm, dict):
        raise ValueError("Gripper profile missing 'palm' block")
    palm_dims = palm.get("dimensions_m")
    if not isinstance(palm_dims, (list, tuple)) or len(palm_dims) != 3 or not all(_is_finite_num(v) and float(v) > 0.0 for v in palm_dims):
        raise ValueError(f"Invalid palm 'dimensions_m': {palm_dims} (must be 3 positive numbers)")

    # Jaw
    jaw = cfg.get("jaw")
    if not isinstance(jaw, dict):
        raise ValueError("Gripper profile missing 'jaw' block")
    jaw_dims = jaw.get("dimensions_m")
    if not isinstance(jaw_dims, (list, tuple)) or len(jaw_dims) != 3 or not all(_is_finite_num(v) and float(v) > 0.0 for v in jaw_dims):
        raise ValueError(f"Invalid jaw 'dimensions_m': {jaw_dims} (must be 3 positive numbers)")

    # Stroke
    stroke = cfg.get("stroke")
    if not isinstance(stroke, dict):
        raise ValueError("Gripper profile missing 'stroke' block")
    open_w = stroke.get("open_width_m")
    closed_w = stroke.get("closed_width_m")
    if not _is_finite_num(open_w) or float(open_w) <= 0.0:
        raise ValueError(f"Invalid stroke 'open_width_m': {open_w} (must be > 0)")
    if not _is_finite_num(closed_w) or float(closed_w) <= 0.0:
        raise ValueError(f"Invalid stroke 'closed_width_m': {closed_w} (must be > 0)")
    if float(open_w) <= float(closed_w):
        raise ValueError(f"Gripper stroke requires open_width_m ({open_w}) > closed_width_m ({closed_w})")

    axis = stroke.get("travel_axis")
    if axis not in ("X", "Y", "Z"):
        raise ValueError(f"Unsupported travel_axis: {axis} (must be 'X', 'Y', or 'Z')")

    # TCP to grasp center
    t2g = cfg.get("tcp_to_grasp_center_m")
    if not isinstance(t2g, (list, tuple)) or len(t2g) != 3 or not all(_is_finite_num(v) for v in t2g):
        raise ValueError(f"Invalid 'tcp_to_grasp_center_m': {t2g} (must be 3 finite numbers)")

    # Capture volume
    cap = cfg.get("capture_volume")
    if not isinstance(cap, dict):
        raise ValueError("Gripper profile missing 'capture_volume' block")
    r_xy = cap.get("xy_radius_m")
    h_z = cap.get("z_half_height_m")
    if not _is_finite_num(r_xy) or float(r_xy) <= 0.0:
        raise ValueError(f"Invalid capture_volume 'xy_radius_m': {r_xy} (must be > 0)")
    if not _is_finite_num(h_z) or float(h_z) <= 0.0:
        raise ValueError(f"Invalid capture_volume 'z_half_height_m': {h_z} (must be > 0)")


def validate_start_layout(cfg: Dict[str, Any]) -> None:
    """
    Validate shared/xiangqi_start_layout.json strictly.
    Enforces 32 unique pieces, 16 red, 16 black, canonical piece counts and valid cells.
    """
    if not isinstance(cfg, dict):
        raise ValueError("Start layout must be a JSON object")

    if cfg.get("schema_version") != 1:
        raise ValueError(f"Unsupported start layout schema_version: {cfg.get('schema_version')} (expected 1)")

    pieces = cfg.get("pieces")
    if not isinstance(pieces, list):
        raise ValueError("Start layout missing 'pieces' array")

    if len(pieces) != 32:
        raise ValueError(f"Start layout piece count {len(pieces)} != 32")

    seen_ids: Set[str] = set()
    seen_cells: Set[Tuple[int, int]] = set()

    counts = {
        "b": {"k": 0, "a": 0, "b": 0, "n": 0, "r": 0, "c": 0, "p": 0},
        "r": {"k": 0, "a": 0, "b": 0, "n": 0, "r": 0, "c": 0, "p": 0},
    }

    expected_per_side = {
        "k": 1, "a": 2, "b": 2, "n": 2, "r": 2, "c": 2, "p": 5
    }

    for idx, p in enumerate(pieces):
        if not isinstance(p, dict):
            raise ValueError(f"Piece entry #{idx} is not a dictionary")

        p_id = p.get("id")
        if not p_id or not isinstance(p_id, str):
            raise ValueError(f"Piece #{idx} missing valid 'id'")
        if p_id in seen_ids:
            raise ValueError(f"Duplicate piece ID found: {p_id}")
        seen_ids.add(p_id)

        side = p.get("side")
        if side not in ("b", "r"):
            raise ValueError(f"Piece '{p_id}' has invalid side: {side} (must be 'b' or 'r')")

        ptype = p.get("type")
        if ptype not in expected_per_side:
            raise ValueError(f"Piece '{p_id}' has invalid type: {ptype}")

        col = p.get("col")
        row = p.get("row")
        if not isinstance(col, int) or isinstance(col, bool) or col < 0 or col > 8:
            raise ValueError(f"Piece '{p_id}' col out of range [0..8]: {col}")
        if not isinstance(row, int) or isinstance(row, bool) or row < 0 or row > 9:
            raise ValueError(f"Piece '{p_id}' row out of range [0..9]: {row}")

        cell = (col, row)
        if cell in seen_cells:
            raise ValueError(f"Multiple pieces occupying cell {cell} (conflict with '{p_id}')")
        seen_cells.add(cell)

        counts[side][ptype] += 1

    # Verify canonical counts
    for side in ("b", "r"):
        side_name = "Black" if side == "b" else "Red"
        for ptype, exp in expected_per_side.items():
            act = counts[side][ptype]
            if act != exp:
                raise ValueError(f"{side_name} piece type '{ptype}' count {act} != expected {exp}")


def validate_gripper_visual_asset(cfg: Dict[str, Any]) -> None:
    """
    Validate shared/gripper_visual_asset.json strictly.
    Raises ValueError on missing or malformed configuration fields.
    """
    if not isinstance(cfg, dict):
        raise ValueError("Gripper visual asset config must be a JSON object")

    if cfg.get("schema_version") != 1:
        raise ValueError(f"Unsupported schema_version: {cfg.get('schema_version')} (expected 1)")

    if "status" not in cfg or not isinstance(cfg["status"], str) or not cfg["status"].strip():
        raise ValueError("Gripper visual asset config missing required non-empty 'status'")

    if "asset_file" not in cfg or not isinstance(cfg["asset_file"], str) or not cfg["asset_file"].strip():
        raise ValueError("Gripper visual asset config missing required non-empty 'asset_file'")

    scale = cfg.get("scale_to_m")
    if not _is_finite_num(scale) or float(scale) <= 0.0:
        raise ValueError(f"Invalid 'scale_to_m': {scale} (must be positive finite number)")

    flange_orig = cfg.get("cad_flange_origin")
    if not isinstance(flange_orig, (list, tuple)) or len(flange_orig) != 3 or not all(_is_finite_num(v) for v in flange_orig):
        raise ValueError(f"Invalid 'cad_flange_origin': {flange_orig} (must be 3 finite numbers)")

    profiles = cfg.get("profiles")
    if not isinstance(profiles, dict) or "fr3" not in profiles:
        raise ValueError("Gripper visual asset config missing required 'profiles.fr3' mapping")

    for pid, pdata in profiles.items():
        if not isinstance(pdata, dict):
            raise ValueError(f"Profile '{pid}' entry must be a dictionary")
        for vec_key in ("mount_offset_m", "mount_rotation_euler_rad", "flange_target_offset_m"):
            vec = pdata.get(vec_key)
            if not isinstance(vec, (list, tuple)) or len(vec) != 3 or not all(_is_finite_num(v) for v in vec):
                raise ValueError(f"Profile '{pid}' invalid '{vec_key}': {vec} (must be 3 finite numbers)")
        roll = pdata.get("mount_roll_rad")
        if not _is_finite_num(roll):
            raise ValueError(f"Profile '{pid}' invalid 'mount_roll_rad': {roll} (must be finite number)")

