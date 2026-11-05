# Pending-pick V retry and taught physical-board display — 2026-11-02

## Observed failures

`logs/20261102_143619_fbee8c5b/run.log` shows pick target (col8,row4)
rejected at 6.7–7.0mm against the unchanged 6mm limit, then `vision.retry_paused`.
Later V scans verified the pre-move board and captured a baseline without retrying
the retained move. InputHandler routed V to resume_automatic_scanning, while Y
and Continue used _retry_visual_pick. Compact Continue also filtered mouse
coordinates using the fixed rather than rendered rectangle.

Read-only live WebSocket inspection before the fix showed PHYSICAL arm telemetry
but nominal board placement (yaw180, teaching_points=null, LEGACY space). Startup
logs report missing XY mirror dimensions/provenance. Nominal col0->8 decreases
robot Y (537->217mm); selected fixed R1->R2 increases Y (219->547mm).

## Changes

- V during a valid pick pause uses the existing guarded retry pipeline: same
  context/epochs, fresh full-board verification, fresh measured pick target and
  exactly the pending move. Invalid target/confidence does not grant motion.
- A failed pre-motion board check retains a PickTargetUnavailable checkpoint.
  Post-motion camera failure still requires recovery and cannot replay motion.
- Compact Continue hit testing uses the actual rendered rectangle. Robot-vs-robot
  keyboard V and scan/Continue clicks remain owned by SelfPlayController.
- The scan-button label explains retry behavior while a pick is pending.
- Missing calibrated mirror now has a separate read-only physical-board display
  using cached, validated user0 R1–R4 XY. No controller point read or motion is
  introduced. The display map is not installed as a motion/planning provider.
- Piece display positions and all 90 cell positions use the same bilinear map.
  Board mesh vertices preserve all four corners, either winding, and small
  non-rigid corner differences; rigid virtual/calibrated paths remain unchanged.
- Display-only attachment seeds the simulated payload at the current gripper
  estimate, removing the old nominal-cell offset. Released poses survive animation
  completion until board reconciliation; no source-cell jump before camera commit.
- Physical grasp remains unverified. Missing taught display is explicitly marked
  nominal rather than mislabeled as R1–R4 calibrated.

## Height and authority boundary

No independent measured board surface Z was supplied. Default display height is
retained only as a preview, `surface_z_verified=false`, with a visible warning.
Approach Z=220mm is not used as surface height. An explicitly configured
BOARD_CALIBRATION_SURFACE_Z_MM supplies independent Z when available.

No calibration artifacts, physical motion coordinates, confidence/offset limits,
servo/mode/safety settings or controller state were changed. No physical actuation
or runtime restart was performed. Existing pending game/session was not cleared.
The running Python process must be reopened to load new handlers/relay, and viewer
reloaded to load new JS. Launch may start a new game under existing fresh-session
policy; this patch does not promise resumption of an old process after restart.

## Verification

Windows, venv Python3.12.10, pytest9.1.1. Venv Scripts prepended to PATH;
PYTEST_ADDOPTS=-x, DRY_RUN=1, ROBOT_BACKEND=VIRTUAL. All controller/HTTP operations
in these tests are mocked; PyBullet regression is headless simulation.

Command:

```powershell
tools/test_fast.ps1 -Workers 2 -Tests @(
  'tests/unit/test_runtime_race_review.py',
  'tests/unit/test_retry_logging.py',
  'tests/unit/test_pick_target_retry.py',
  'tests/unit/test_physical_board_display.py',
  'tests/unit/test_fixed_user0_teaching_points.py',
  'tests/unit/test_client_mode_controls.py',
  'tests/unit/test_reliability_recheck.py',
  'tests/unit/test_live_twin_physical_mirror.py')
```

PASS: 86, exit0; pytest19.78s / runner28.27s, no serial tests selected.
After the final released-pose preservation change, reran:

`tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_physical_board_display.py`

PASS: 8, exit0; pytest2.57s / runner5.77s. Includes actual PyBullet attach->lift->
release->finish->publish->reconcile, zero spurious nominal offset and no source jump.

Node24.14.1, each command exit0:

```text
node tests/unit/test_viewer_physical_board_display.mjs
node tests/unit/test_viewer_board_mesh_transform.mjs
node tests/unit/test_viewer_placement_integrity.mjs
node --check robot-3d-viewer/main.mjs
```

PASS: taught four-corner/all90 mesh-cell parity, upward normals, nonaccumulating
warp, restore to virtual; existing rigid/yaw parity and calibration integrity.
`git diff --check` scoped touched tracked files: exit0 (line-ending warnings only).
Graph detect_changes: checkout-wide798 changed files, zero impacted symbols; not
an isolated task blast-radius estimate. Exact files/callers reviewed separately.

Review caught/fixed nominal attachment offset, compact Continue hit testing and
released-pose snapback. Final read-only re-review found no remaining blocker in
scope. Full regression, browser visual acceptance, physical release/clearance and
full-game hardware validation NOT RUN. Do not claim physical calibration/safety.
