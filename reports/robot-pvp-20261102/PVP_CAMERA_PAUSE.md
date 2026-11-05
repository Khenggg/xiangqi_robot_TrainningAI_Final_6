# Verified startup board but Red input remains locked

Session: `logs/20261102_181200_d93298cd`, HUMAN_VS_HUMAN_ROBOT / PHYSICAL.

## Evidence and cause

-18:12:07 +07 fresh session created; operator_inspection_required=false, opening
  FEN. No archived physical transaction restored.
-18:12:20 initial camera verification fails NO_FRESH_OBSERVATION. The startup
  callback sets manual_override_active and snapshot_continue_required.
-18:14:40 V verifies32 pieces and captures a32-cell YOLO baseline without cell
  differences. resume_automatic_scanning clears manual_override_active but the
  old implementation does not clear snapshot_continue_required.
-18:15:30 explicit operator activation succeeds (physical.enabled). No movement
  was issued by this investigation.
-RobotPvPController._blocked correctly checks snapshot_continue_required and
  therefore continues reporting a recovery-required session despite the good
  board and enabled backend. This is a new-mode pause-lifecycle integration bug,
  not evidence of a missing piece or a restored old FEN.

## Fix in isolated worktree

Only HUMAN_VS_HUMAN_ROBOT changes: resume_automatic_scanning requires the existing
exact board verifier, no unresolved transaction/test/retry/mode/turn-confirmation,
existing hardware recovery approval when needed, and a successful fresh baseline.
It then clears the camera pause flags and writes OPERATOR_RESUMED_ROBOT_PVP_CAMERA.
Persistence failure restores the prior flags. A newer stop generation or pending
session action cancels resume. No automatic enable, robot/gripper command or move
submission. Continue (without physical_sync_fault) uses the same path; existing
physical-fault reconciliation remains in place. Other modes retain their behavior.

The currently running process retains its old code. For this startup-only pause
with no pending move, its old CONTINUE path can clear the pause after confirming
the equal board and obtaining a baseline. Verified by executing the baseline's
actual Continue method offline with a fake camera: flags cleared, board_revision0,
pending_moveNone, no actuator calls. No live click or restart was performed.

## Validation

Windows / Python3.12.10 / pytest9.1.1; DRY_RUN=1, ROBOT_BACKEND=VIRTUAL,
PYTEST_ADDOPTS=-x; numerical thread caps from project runner.

```powershell
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_robot_pvp.py,tests/unit/test_recovery_block_diagnostics.py,tests/unit/test_robot_pvp_main_ui.py,tests/unit/test_retry_logging.py
```

PASS, exit0:51 tests (50parallel+1serial),17.27s. Covers V and Continue, persisted
resume phase, no movement on camera resume, rejection on camera/baseline/controller
failure, pending transaction, storage failure and a new stop request. Actual
main event loop with fake backend/real room sockets still passes. First run had
a missing MoveActor test import, corrected before final passing run.

Scoped read-only review: no blocker. git diff --check PASS. Graph search/trace/
detect_changes unavailable (Transport closed), exact-file/caller review used.
No full regression, physical movement/acceptance, live state mutation, fault clear
or restart performed. Original checkout unchanged. Software fix takes effect on
the next application launch; do not claim the live process was repaired remotely.
