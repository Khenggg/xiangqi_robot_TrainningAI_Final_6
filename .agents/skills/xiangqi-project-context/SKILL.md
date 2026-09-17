---
name: xiangqi-project-context
description: >-
  Provides rapid access to stable architectural facts, authority boundaries, geometry,
  and current repository state for the Xiangqi Robot project. Use this skill when beginning
  any new task, review, or debugging session in this repository to avoid rescanning files.
---

# Xiangqi Robot Project Context Skill

Use this skill at the beginning of any interaction within the `xiangqi_robot_TrainningAI_Final_6` repository.
Instead of using grep/glob to scan the entire workspace, load only the authoritative project documents.

## Step-by-Step Context Loading

1. **Read Repository Operating Rules:**
   * View [`AGENTS.md`](../../AGENTS.md) for mandatory safety boundaries, non-negotiable rules, and report format.

2. **Read System Architecture & Geometry:**
   * View [`PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md) for Fairino FR3 specs, coordinate frames (robot vs Three.js), and authority boundaries.

3. **Read Subsystem Directory & Task Routing:**
   * View [`REPO_MAP.md`](../../REPO_MAP.md) to locate the exact subsystem and target files relevant to your task.

4. **Read Current State & Verified Baseline:**
   * View [`CURRENT_STATE.md`](../../CURRENT_STATE.md) to check `LAST_REVIEWED_HEAD`, current `PHASE_STATUS`, and active blockers.

5. **Read Known Issues & Regressions:**
   * View [`KNOWN_ISSUES.md`](../../KNOWN_ISSUES.md) to avoid rediscovering solved bugs or re-investigating known edge cases.

## Core Directives

* **Never Rescan Entire Repository:** All architectural constants, authority contracts, and coordinate systems are already documented in the files above.
* **Diff First:** If starting a review or bug fix, proceed directly to the `xiangqi-incremental-review` skill.
