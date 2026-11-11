# Physical PvP failed-move reconciliation — 2026-11-11

Baseline: `fix/fix-capsule` at `8255afd`. Scoped source correction; no controller, camera, gripper or motion command executed, and no running app restarted.

## Observed cases

- `logs/20261111_164127_1fab0963/events.jsonl`: code version `8255afd`, physical HUMAN_VS_HUMAN_ROBOT. Move `(col,row) (4,6) -> (4,5)` failed post-motion full-board verification at approximately 16:42:19 local time. The camera still recognized the red pawn at its old square. This is consistent with missed pickup, but does not independently prove the physical cause.
- In that session, camera verification later succeeded during V recovery, followed twice by `recovery.hardware_blocked`: arm/gripper stop not confirmed. Camera confirmation alone could not resume the game.
- `logs/20261111_163542_bfc9440a/events.jsonl`: separate earlier move `(4,4) -> (4,3)` produced BOARD_SANITY_FAILED (17 recognized red pieces), then LOW_PIECE_CONFIDENCE near 0.44–0.47. Recognition failure and missed grasp require different physical investigation.

## Root cause and scoped correction

HIGH confidence from source; VERIFIED with deterministic mocks: a finished move can fail only its camera postcheck without ever creating a controlled-stop request. `_confirm_stopped_for_operator()` accepts the absence of a request, but `approve_recovery_after_verification()` requires `safe_for_release()`, which rejects that absence. Repeating V cannot produce the missing evidence.

Explicit V/Continue now gathers two distinct fresh idle telemetry samples with finished workers and no active gripper pulse. It publishes a temporary observation receipt for that operator action, without issuing StopMotion, HOME, gripper or enable, and removes only its own receipt afterward. Observation runs outside the coordinator lock. A real stop supersedes it; generation/request checks prevent cleanup from deleting a newer stop. Existing real-stop confirmation remains unchanged. Direct reconciliation without an explicit operator action cannot manufacture this proof.

Board recovery contracts are preserved: verified old board retires the failed move and retains the turn, leaving a second V inspection/resume before reselection; verified expected board commits once without motion replay; unmatched/partial boards stay paused. Status messages now describe those PvP cases and restore captured pieces without assuming their color. README documents the workflow and the separate VS ROBOT R/H scope.

## Validation

Environment: Windows, Python 3.12.10 from `.venv312`, pytest 9.1.1; PATH prepended with `.venv312/Scripts`, DRY_RUN=1, ROBOT_BACKEND=VIRTUAL, PYTHONIOENCODING=utf-8. All device interfaces in the new physical-profile cases are mocks.

PASS, exit 0, 99 tests, 17.88 seconds runner total:

```powershell
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_pvp_failed_move_recovery.py,tests/unit/test_stop_recovery_controls.py,tests/unit/test_fresh_session_startup.py,tests/unit/test_automatic_physical_startup.py,tests/unit/test_auto_enable_resume_integration.py
```

The 15 new integration regressions exercise actual V keyboard handling, MotionWorker, GameState/journal and ControlledStopCoordinator. They cover old/expected boards, no pending move, blocked stale/duplicate/moving/faulted/disconnected/invalid telemetry, active gripper/workers, no implicit approval, receipt cleanup and urgent-stop races. Scoped independent code review APPROVED, including the final status-message changes.

Expanded check FAIL, exit 1: 85 passed, 2 failed in 17.02 seconds:

```powershell
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_pvp_failed_move_recovery.py,tests/unit/test_stop_recovery_controls.py,tests/unit/test_robot_pvp.py,tests/unit/test_fresh_session_startup.py,tests/unit/test_auto_enable_resume_integration.py
```

Both failures are PRE-EXISTING translation assertions at `tests/unit/test_robot_pvp.py:189`, expecting Vietnamese player names while untouched `src/core/session_profile.py` returns English names. Frozen HEAD source independently returns the same English names in both PHYSICAL and VIRTUAL. These assertions were not changed for this recovery correction.

Graph detect_changes reports the two production files plus an existing user whitespace change in config.py; no impacted symbols are returned by the current index. Exact callers and recovery/stop consumers were reviewed directly. User config.py and unrelated untracked files remain preserved.

## Remaining limits

Physical acceptance NOT RUN. This does not repair grasp calibration or recognition quality, clear controller faults, auto-enable/replay a failed move, or add HOME recovery to PvP. The observed running session loaded `8255afd`; source edits require a future controlled app reload. Restart is not a way to retain/replay the pending transaction: startup archives interrupted work and requires inspection of a fresh board under the existing contract. Full regression, a new capsule and push NOT RUN.
