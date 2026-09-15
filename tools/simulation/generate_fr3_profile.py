#!/usr/bin/env python3
"""
Generate or verify machine-readable FR3 simulation profile from canonical URDF.

URDF Source: robot-3d-viewer/assets/fr3_v6/fairino3_v6.urdf
Target Profile: shared/robot_profiles/fr3.json

Parses the 6 revolute joints (j1..j6), origins, rpy orientations, axes,
and limits directly using standard xml.etree.ElementTree.
"""

import argparse
import json
import math
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

SCHEMA_VERSION = 1


def get_repo_root() -> Path:
    """Resolve repository root."""
    return Path(__file__).resolve().parent.parent.parent


def parse_fr3_urdf(urdf_path: Path) -> dict:
    """Parse fairino3_v6.urdf and return structured kinematic profile."""
    if not urdf_path.is_file():
        raise FileNotFoundError(f"FR3 URDF file not found: {urdf_path}")

    tree = ET.parse(urdf_path)
    root = tree.getroot()

    robot_name = root.get("name", "fairino3_v6_robot")

    # Collect all links in order
    links = [link.get("name") for link in root.findall("link") if link.get("name")]

    # Parse 6 revolute joints in order
    joints = []
    revolute_joint_elements = [
        j for j in root.findall("joint") if j.get("type") == "revolute"
    ]

    for j_elem in revolute_joint_elements:
        name = j_elem.get("name")
        parent = j_elem.find("parent").get("link")
        child = j_elem.find("child").get("link")
        joint_type = j_elem.get("type")

        origin_elem = j_elem.find("origin")
        xyz_str = origin_elem.get("xyz", "0 0 0") if origin_elem is not None else "0 0 0"
        rpy_str = origin_elem.get("rpy", "0 0 0") if origin_elem is not None else "0 0 0"

        xyz = [round(float(v), 6) for v in xyz_str.split()]
        rpy = [round(float(v), 6) for v in rpy_str.split()]

        axis_elem = j_elem.find("axis")
        axis_str = axis_elem.get("xyz", "0 0 1") if axis_elem is not None else "0 0 1"
        axis = [round(float(v), 6) for v in axis_str.split()]

        limit_elem = j_elem.find("limit")
        if limit_elem is not None:
            lower = round(float(limit_elem.get("lower", -math.pi)), 6)
            upper = round(float(limit_elem.get("upper", math.pi)), 6)
            velocity = round(float(limit_elem.get("velocity", 3.14)), 6)
            effort = round(float(limit_elem.get("effort", 150.0)), 6)
        else:
            lower = -math.pi
            upper = math.pi
            velocity = 3.14
            effort = 150.0

        joints.append({
            "name": name,
            "parent": parent,
            "child": child,
            "type": joint_type,
            "origin_xyz_m": xyz,
            "origin_rpy_rad": rpy,
            "axis": axis,
            "lower_rad": lower,
            "upper_rad": upper,
            "velocity_rad_s": velocity,
            "effort_nm": effort,
        })

    base_link = "base_link"
    flange_link = "wrist3_link"

    repo_root = get_repo_root()
    try:
        rel_urdf = str(urdf_path.relative_to(repo_root)).replace("\\", "/")
    except ValueError:
        rel_urdf = str(urdf_path).replace("\\", "/")

    profile = {
        "schema_version": SCHEMA_VERSION,
        "robot_model": "FR3",
        "urdf_robot_name": robot_name,
        "source_urdf": rel_urdf,
        "base_link": base_link,
        "flange_link": flange_link,
        "links": links,
        "joints": joints,
    }

    return profile


def verify_profile_matches_urdf(profile: dict, urdf_path: Path, tol: float = 1e-5) -> bool:
    """Verify that a given profile matches parsed URDF within numerical tolerance."""
    expected = parse_fr3_urdf(urdf_path)

    if profile.get("robot_model") != expected.get("robot_model"):
        return False
    if profile.get("base_link") != expected.get("base_link"):
        return False
    if profile.get("flange_link") != expected.get("flange_link"):
        return False

    if len(profile.get("joints", [])) != len(expected.get("joints", [])):
        return False

    for j_actual, j_exp in zip(profile["joints"], expected["joints"]):
        if j_actual["name"] != j_exp["name"]:
            return False
        if j_actual["parent"] != j_exp["parent"] or j_actual["child"] != j_exp["child"]:
            return False
        for k in ["origin_xyz_m", "origin_rpy_rad", "axis"]:
            for v1, v2 in zip(j_actual[k], j_exp[k]):
                if abs(v1 - v2) > tol:
                    return False
        for k in ["lower_rad", "upper_rad", "velocity_rad_s"]:
            if abs(j_actual[k] - j_exp[k]) > tol:
                return False

    return True


def main():
    parser = argparse.ArgumentParser(description="Generate or verify FR3 robot profile JSON from URDF.")
    parser.add_argument(
        "--urdf",
        type=Path,
        default=get_repo_root() / "robot-3d-viewer" / "assets" / "fr3_v6" / "fairino3_v6.urdf",
        help="Path to source fairino3_v6.urdf",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=get_repo_root() / "shared" / "robot_profiles" / "fr3.json",
        help="Path to destination fr3.json",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify destination file matches URDF without overwriting",
    )

    args = parser.parse_args()
    urdf_path = args.urdf.resolve()
    output_path = args.output.resolve()

    if args.check:
        if not output_path.is_file():
            print(f"[CHECK FAILED] Output file does not exist: {output_path}")
            sys.exit(1)
        with open(output_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
        if verify_profile_matches_urdf(existing, urdf_path):
            print(f"[CHECK PASSED] {output_path} matches {urdf_path}")
            sys.exit(0)
        else:
            print(f"[CHECK FAILED] Discrepancy detected between {output_path} and {urdf_path}")
            sys.exit(1)

    profile = parse_fr3_urdf(urdf_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    print(f"[GENERATED] Successfully wrote FR3 profile with {len(profile['joints'])} joints to {output_path}")


if __name__ == "__main__":
    main()
