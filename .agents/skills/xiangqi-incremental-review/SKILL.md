---
name: xiangqi-incremental-review
description: >-
  Standardized protocol for incremental code review, targeted bug fixing, and diff-first
  investigation in the Xiangqi Robot repository. Use when receiving a new review request,
  fixing an issue, or extending features without reading the whole repository.
---

# Xiangqi Incremental Review Protocol

This skill enforces a **diff-first, evidence-driven workflow** that restricts file reads strictly to modified subsystems and their immediate dependencies.

---

## The 6-Step Workflow Protocol

### Step A — Establish Baseline & Git Delta
1. Read `LAST_REVIEWED_HEAD` from [`CURRENT_STATE.md`](../../CURRENT_STATE.md).
2. Check current repository `HEAD` via `git rev-parse HEAD`.
3. If `CURRENT_HEAD == LAST_REVIEWED_HEAD` and working tree is clean:
   * Do NOT reread previously reviewed files unless explicitly assigned to inspect them.
4. If `CURRENT_HEAD != LAST_REVIEWED_HEAD` or working tree is dirty:
   * Run:
     ```powershell
     git log <LAST_REVIEWED_HEAD>..HEAD --oneline
     git diff --stat <LAST_REVIEWED_HEAD>..HEAD
     git status --short
     ```

### Step B — Scope Modified Files via REPO_MAP
1. Match the changed files against the **Task → Files Routing Table** in [`REPO_MAP.md`](../../REPO_MAP.md).
2. Identify the primary affected subsystems:
   * e.g., If only `src/simulation/placement.py` changed, open ONLY `placement.py` and directly mapped files (`runtime.py`, `board.mjs`).
3. **DO NOT** expand file search to unrelated subsystems (e.g., do not read `src/vision/` or `src/ai/` when reviewing simulation collision).

### Step C — Expand Only on Evidence
Open additional files ONLY IF:
* A direct `import` or function call crosses a subsystem boundary.
* A shared invariant contract (e.g. `placement_version`) is touched.
* A unit test fails and the stack trace explicitly points to an external file.
* Safety authority tracing (robot motion / collision guard) requires checking the caller/callee.

### Step D — Run Focused Tests First
Execute the smallest unit test suite covering the modified subsystem first:
* **Placement & Routes:** `pytest tests/unit/test_phase3_dynamic_board_placement.py`
* **Pick, Place & Fail-Fast:** `pytest tests/unit/test_phase3_isolation_and_fail_fast.py`
* **Collision Guard & Kinematics:** `pytest tests/unit/test_phase3_final_closure.py`
* **Master Runtime & Recovery:** `pytest tests/unit/test_phase3_final_master.py`
* **Viewer UI & Ruler:** `node tests/unit/test_viewer_single_motion_authority.mjs`

### Step E — Execute Broader Regression
Only after focused tests pass cleanly:
* Run the combined Phase 3 regression suite (53 tests):
  ```powershell
  pytest tests/unit/test_phase3_final_master.py tests/unit/test_phase3_final_closure.py tests/unit/test_phase3_isolation_and_fail_fast.py tests/unit/test_phase3_dynamic_board_placement.py -v
  ```

### Step F — Update Persistent State
Before concluding:
1. Update [`CURRENT_STATE.md`](../../CURRENT_STATE.md):
   * Set `LAST_REVIEWED_HEAD` to the new verified commit.
   * Update `VERIFIED_FIXED`, `OPEN_BLOCKERS`, and `TEST_EVIDENCE`.
2. Update [`KNOWN_ISSUES.md`](../../KNOWN_ISSUES.md) if bugs were resolved or new issues discovered.
3. Deliver the report strictly adhering to the Section 79 / Evidence-First standard in [`AGENTS.md`](../../AGENTS.md).
