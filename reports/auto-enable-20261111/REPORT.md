# Auto-enable after verified startup recovery

Date: 2026-11-11. Branch `fix/fix-capsule`, baseline `973da048c409d1196caf1f30b78b5db401f2f13b`.

## Cause

The software cancellation latch is **VERIFIED offline**, with strong corroborating live-session logs. A restarted physical session with unresolved previous work sets `recovery_required`, `physical_sync_fault`, `manual_override_active` and `snapshot_continue_required`. Before the camera can finish recovery, the old `AutomaticPhysicalStartup.tick()` sees the first two flags and permanently calls `cancel()`. Later V reconciliation clears the game flags but cannot clear `automatic_startup.finished/cancelled`. Consequently no enable worker is ever submitted. Raising the retry cap does not reach a cancelled startup.

Exact boundaries on the inspected baseline:

- `src/core/game_persistence.py:254-266`: `attach_journal(fresh_start=True)` produces the four inspection flags from the interrupted physical journal.
- Baseline `src/core/automatic_physical_startup.py:39-48`: recovery flags permanently cancel automatic startup.
- `src/ui/input_handler.py:769-812`, `src/core/game_persistence.py:531`: actual V resume verifies the board, clears recovery/pause flags and persists the camera resume, without recreating auto-startup.
- `main.py:148` sets `baseline_checked=True` even when the first baseline capture fails; this field is not the missing step in this incident.

This cancellation condition also exists at `4c0e6a2`, before HOME recovery commit `93fd21a`: **PRE-EXISTING** for that change. The initiating cause of the original robot stop is **UNKNOWN**; this investigation explains the subsequent failure to auto-enable, not every earlier motion failure.

## Current runtime evidence

Read-only inspection of `logs/20261111_160259_6d147654/events.jsonl`:

| Line | Observation |
|---|---|
| 2 | `app.code_version`: exact HEAD `973da04`, tracked changes false at launch |
| 10 | `HUMAN_VS_HUMAN_ROBOT`, environment `PHYSICAL` |
| 11 | `session.started_fresh`, `operator_inspection_required=true` |
| 109–111 | 16:03:58 Asia/Saigon: first baseline rejected, `NO_FRESH_OBSERVATION` |
| 115, 118 | 16:04:13–14: camera verified the board |
| 121 | 16:04:15: `pvp.camera_resumed` |

The inspected log contains zero `physical.auto_enable_failed` or `physical.auto_enabled` events. The physical selection is established by the session event; boot-time `dry_run=true` is not evidence that this selected session was virtual. The active real Python process was PID 24072, started 16:02:58, behind the venv launcher; it retains imported old code. It was not restarted, terminated, attached to, or commanded during this work.

## Change

Only the automatic-startup implementation changes:

- Initial recovery, camera pause, pending work and temporary test/emergency flags **wait** for their existing verification/clear paths instead of permanently cancelling startup. Baseline and fresh physical checks remain required.
- Closing, session-control actions, mode changes, game over and explicit cancellation remain terminal. A delayed worker callback cannot revive a cancelled startup.
- `physical.auto_enable_waiting` logs the actual reason/flags once per reason change. `physical.auto_enable_started` records accepted worker submission, and `physical.auto_enable_cancelled` records terminal cancellation.
- The submitted stop generation is frozen, and current prerequisites are checked again by the existing activation guard immediately before enable.
- Automatic startup refuses an unverified or stale completed stop even if the user's changed `blocked` property is false. Known enable failures retain the user's ten-attempt limit; uncertain RPC/socket outcomes do not automatically replay enable.

The user's `973da04` and global stop/force-release changes were preserved. No controller enable/reset, stop, HOME, gripper command or camera capture was sent to hardware. No calibration, motion geometry, thresholds or journal data were overwritten. Existing stashes and untracked verification artifacts were not changed.

## Execution evidence

Environment: Windows, repository `.venv312` Python 3.12.10, pytest 9.1.1, `DRY_RUN=1`, `ROBOT_BACKEND=VIRTUAL`. All physical interfaces are mocks; the integration test uses the actual GameState journal producer and actual `InputHandler.resume_automatic_scanning()` with a temporary SQLite journal and a real local MotionWorker.

**Baseline reproduction PASS**, exit 0:

```powershell
$env:PYTHONPATH="$PWD"
$env:DRY_RUN='1'
$env:ROBOT_BACKEND='VIRTUAL'
.\.venv312\Scripts\python.exe reports/auto-enable-20261111/baseline_latch_probe.py
```

The script executes the frozen class from git `973da04`, produces all four real startup flags, then executes actual successful V resume. Both before and after resume it observes `finished=true`, `cancelled=true`, worker submissions 0. See `baseline_latch_probe.json`.

**Focused tests PASS**, exit 0: 77 tests in 19.45 seconds (77 parallel, no serial cases selected). Exact command:

```powershell
$env:PATH="$PWD/.venv312/Scripts;$env:PATH"
$env:DRY_RUN='1'
$env:ROBOT_BACKEND='VIRTUAL'
$env:PYTHONIOENCODING='utf-8'
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_automatic_physical_startup.py,tests/unit/test_auto_enable_resume_integration.py,tests/unit/test_fresh_session_startup.py,tests/unit/test_f2_camera_and_frame_restart.py
```

The fixed integration submits exactly one mocked enable after actual verified V resume; failed identity verification, checkpoint rollback, unresolved pending work, unsafe stop, mode/game end, stop races, explicit cancellation and unknown enable outcomes remain blocked. New logging is deduplicated. No test reports a real controller as successfully enabled.

Independent scoped code review: **APPROVED**, including the in-flight cancellation callback correction. No whole-branch or hardware acceptance claim. Broad historical failures were not re-run or relabelled as fixed.

**NOT RUN:** live enable, controller/physical acceptance, camera performance tuning, new capsule build, full-suite regression. The running application still uses its imported old code; the source fix takes effect only after a controlled application restart. Push is not part of this investigation.
