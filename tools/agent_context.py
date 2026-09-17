#!/usr/bin/env python3
"""
tools/agent_context.py — Lightweight, Deterministic Agent Context & Delta Inspector.

Outputs current repository state, git delta since LAST_REVIEWED_HEAD,
uncommitted files, and suggested inspection scope based on REPO_MAP.
Read-only, fast, standard library only.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Task Routing Table: File patterns -> Subsystem focus & suggested files to inspect
ROUTING_MAP = [
    (
        re.compile(r"src/simulation/placement\.py|robot-3d-viewer/board\.mjs"),
        "Dynamic Board Placement & Grid Geometry",
        [
            "src/simulation/placement.py",
            "src/simulation/runtime.py",
            "robot-3d-viewer/board.mjs",
            "tests/unit/test_phase3_dynamic_board_placement.py",
        ],
    ),
    (
        re.compile(r"src/simulation/physics/collision_guard\.py"),
        "Collision Guard & Self-Collision Oracle",
        [
            "src/simulation/physics/collision_guard.py",
            "src/simulation/virtual_fr3_backend.py",
            "tests/unit/test_phase3_final_closure.py",
        ],
    ),
    (
        re.compile(r"src/simulation/physics/gripper\.py|src/simulation/physics/piece\.py|src/simulation/physics/state\.py"),
        "Grasp Physics & Typed Result Contracts",
        [
            "src/simulation/physics/world.py",
            "src/simulation/physics/gripper.py",
            "src/simulation/physics/state.py",
            "tests/unit/test_phase3_isolation_and_fail_fast.py",
        ],
    ),
    (
        re.compile(r"src/simulation/virtual_fr3_backend\.py|src/kinematics/fr3\.py"),
        "FR3 Kinematics & Cartesian/Joint Motion Authority",
        [
            "src/simulation/virtual_fr3_backend.py",
            "src/kinematics/fr3.py",
            "src/simulation/physics/collision_guard.py",
            "tests/unit/test_phase3_final_master.py",
        ],
    ),
    (
        re.compile(r"src/simulation/runtime\.py"),
        "Master Runtime Coordinator & Operation State Machine",
        [
            "src/simulation/runtime.py",
            "src/simulation/virtual_fr3_backend.py",
            "src/simulation/physics/world.py",
            "tests/unit/test_phase3_final_master.py",
        ],
    ),
    (
        re.compile(r"robot-3d-viewer/ruler\.mjs"),
        "3D Measurement Tape & Ruler Telemetry",
        [
            "robot-3d-viewer/ruler.mjs",
            "robot-3d-viewer/main.mjs",
            "tests/unit/test_viewer_coordinate_ruler.mjs",
        ],
    ),
    (
        re.compile(r"robot-3d-viewer/.*"),
        "Three.js Digital Twin Viewer & Controls",
        [
            "robot-3d-viewer/index.html",
            "robot-3d-viewer/main.mjs",
            "robot-3d-viewer/styles.css",
            "tests/unit/test_viewer_single_motion_authority.mjs",
        ],
    ),
]


def run_git(args):
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception as e:
        return ""


def parse_current_state():
    state_file = REPO_ROOT / "CURRENT_STATE.md"
    last_head = "UNKNOWN"
    blockers = 0
    phase = "UNKNOWN"
    status = "UNKNOWN"

    if state_file.is_file():
        text = state_file.read_text(encoding="utf-8")
        m_head = re.search(r"LAST_REVIEWED_HEAD[\*:]+\s*`?([a-f0-9]+)`?", text, re.IGNORECASE)
        if m_head:
            last_head = m_head.group(1)
        m_blockers = re.search(r"(?:Open Blockers|Total Count)[\*:]+\s*(\d+)", text, re.IGNORECASE)
        if m_blockers:
            blockers = int(m_blockers.group(1))
        m_phase = re.search(r"(?:^|[^\w])PHASE[\*:]+\s*`?([A-Za-z0-9_]+)`?", text)
        if m_phase:
            phase = m_phase.group(1)
        m_status = re.search(r"(?:^|[^\w])PHASE_STATUS[\*:]+\s*`?([A-Za-z0-9_]+)`?", text)
        if m_status:
            status = m_status.group(1)

    return {
        "last_reviewed_head": last_head,
        "open_blockers": blockers,
        "phase": phase,
        "phase_status": status,
    }


def main():
    branch = run_git(["branch", "--show-current"]) or "detached"
    head = run_git(["rev-parse", "HEAD"]) or "UNKNOWN"
    head_short = run_git(["rev-parse", "--short", "HEAD"]) or "UNKNOWN"
    current_state = parse_current_state()
    last_head = current_state["last_reviewed_head"]

    print("=" * 65)
    print("   XIANGQI ROBOT — AGENT WORKSPACE CONTEXT & DELTA INSPECTOR")
    print("=" * 65)
    print(f"Repository:         {REPO_ROOT.name}")
    print(f"Current Branch:     {branch}")
    print(f"Current HEAD:       {head_short} ({head})")
    print(f"Last Reviewed HEAD: {last_head[:7] if len(last_head) >= 7 else last_head} ({last_head})")
    print(f"Phase:              {current_state['phase']} [STATUS: {current_state['phase_status']}]")
    print(f"Open Blockers:      {current_state['open_blockers']}")

    # Check ahead commits
    ahead_commits = []
    if last_head != "UNKNOWN" and last_head != head:
        log_out = run_git(["log", f"{last_head}..HEAD", "--oneline"])
        if log_out:
            ahead_commits = log_out.splitlines()

    print("\n--- GIT REVISION DELTA ---")
    if ahead_commits:
        print(f"Commits ahead of LAST_REVIEWED_HEAD ({len(ahead_commits)}):")
        for c in ahead_commits:
            print(f"  + {c}")
    else:
        print("HEAD matches LAST_REVIEWED_HEAD (No new commits).")

    # Check uncommitted working tree changes
    status_out = run_git(["status", "--short"])
    dirty_files = []
    if status_out:
        print("\n--- UNCOMMITTED WORKING TREE CHANGES ---")
        for line in status_out.splitlines():
            print(f"  {line}")
            parts = line.strip().split()
            if len(parts) >= 2:
                dirty_files.append(parts[-1])
    else:
        print("\nWorking tree is clean.")

    # Changed files pool
    all_changed_files = set(dirty_files)
    if last_head != "UNKNOWN" and last_head != head:
        diff_files_out = run_git(["diff", "--name-only", f"{last_head}..HEAD"])
        if diff_files_out:
            for f in diff_files_out.splitlines():
                all_changed_files.add(f.strip())

    # Map to suggested inspection files
    print("\n--- SUGGESTED INSPECTION SCOPE (FROM REPO_MAP) ---")
    suggested_files = set()
    matched_subsystems = set()

    for f_path in all_changed_files:
        for pat, sub_name, rec_files in ROUTING_MAP:
            if pat.search(f_path):
                matched_subsystems.add(sub_name)
                suggested_files.update(rec_files)

    if matched_subsystems:
        print("Affected Subsystems:")
        for s in sorted(matched_subsystems):
            print(f"  * {s}")
        print("\nFiles to Inspect (DO NOT read other subsystems):")
        for sf in sorted(suggested_files):
            print(f"  -> {sf}")
    else:
        if all_changed_files:
            print("Modified files not mapped to standard subsystems. Inspect only:")
            for f in sorted(all_changed_files):
                print(f"  -> {f}")
        else:
            print("No files modified. Read PROJECT_CONTEXT.md and CURRENT_STATE.md only.")

    print("=" * 65)


if __name__ == "__main__":
    main()
