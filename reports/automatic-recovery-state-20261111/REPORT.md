# Remove manual arm/gripper confirmation — 2026-11-11

Baseline: `cd01b66` on `fix/fix-capsule` (same committed tree as `f6406df`).

## Evidence and change

The screenshot's manual confirmation gate masks a real fault in the latest session. `logs/20261111_175319_73d63862/events.jsonl:43` records a read-only restored-session stop timing out; line 56 at 17:53:57 local time records successful board verification followed by `Controller error: main=1, sub=29`. The literal code is known; its hardware cause is not established here.

Removed the manual `confirm_operator_stop` API and its V/F2/mode-cleanup callers. V/Continue now observes current controller state automatically. A restored-session read-only stop can settle on two distinct new idle packets, finished workers and an inactive gripper pulse. Observation runs outside the stop lock; request identity and generation are checked before publication. Real stop requests supersede temporary observations. Cleanup removes only its own temporary receipt, including the manager refresh race where an older request disappears during observation.

Actual StopMotion dispatch is tracked separately: a dispatched stop without a successful acknowledgment remains unresolved and is not resent. This change does not clear a gripper pulse flag, reset/enable a controller, issue HOME or replay a move. Controller alarms, stale/disconnected/invalid telemetry, active workers and active gripper pulses still block continuation, with their concrete reason replacing the generic request to confirm arm safety.

For physical PvP, a verified old board now retires the failed pending move, preserves the turn and installs a fresh camera baseline in the same V action. Successful resume removes error fields in the same durable checkpoint; persistence failure restores them and keeps play paused. An expected-board match still commits once without motion replay. This does not extend VS ROBOT HOME/R/H to PvP or change vision/grasp thresholds.

README and recovery/startup messages describe this contract. Existing user config.py whitespace and unrelated untracked files are preserved.

## Validation

Environment: Windows, Python 3.12.10 in `.venv312`, pytest 9.1.1; PATH prepended with `.venv312/Scripts`, DRY_RUN=1, ROBOT_BACKEND=VIRTUAL, PYTHONIOENCODING=utf-8.

PASS, exit 0, 126 tests (9.42 seconds parallel, 15.96 seconds total runner):

```powershell
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_stop_recovery_controls.py,tests/unit/test_pvp_failed_move_recovery.py,tests/unit/test_recovery_block_diagnostics.py,tests/unit/test_fresh_session_startup.py,tests/unit/test_automatic_physical_startup.py,tests/unit/test_auto_enable_resume_integration.py,tests/unit/test_sdk_shutdown_qa.py
```

The focused recovery tests include exact controller alarms despite an IDLE label, read-only startup settling without manual approval, blocked unknown dispatched stops, active gripper preservation, repeated samples from a slower stream, new-stop races, old-board single-V resume, baseline failure and journal rollback. Scoped independent source review APPROVED. Production AST and scoped diff checks PASS. No hardware actuation or restart of the user's running app was performed.

After the final manager receipt-cleanup race correction, `tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_stop_recovery_controls.py` passed 31 tests, exit 0, runner 13.39 seconds, including both temporary/no-receipt manager cases. This overlaps the aggregate run; the counts are not additive. The final two-line source delta received separate review approval.

An earlier expanded run FAILED: 81 passed, 14 failed, exit 1, 26.63 seconds total. Exact targets were `test_session_buttons.py`, `test_recovery_block_diagnostics.py`, `test_fresh_session_startup.py`, `test_automatic_physical_startup.py`, `test_auto_enable_resume_integration.py`, `test_startup_failure_recovery.py`, `test_sdk_shutdown_qa.py` via the same runner with 2 workers.

- Two session-button assertions still expect Vietnamese fragments from messages already English at the frozen baseline. Those production statements and tests were left unchanged.
- Nine diagnostic expectations used old case/language or the retired manual-confirmation fallback. Assertions were updated to current English/controller semantics and all diagnostic cases pass in the final focused run.
- Three legacy GUI startup-failure tests patch the shared manager but the default HUMAN_VS_ROBOT entrypoint routes to the private VSC manager. Their five-second harness timed out and attempted camera startup through the unmocked private path. They are not physical acceptance tests and were not rerun. Logs show camera startup failure/cancellation; private initialization orders camera before robot. This harness needs its own mocked boundary correction before reuse. Do not report it as a passing isolated-device check.

Graph architecture access succeeded initially; search/trace/impact refresh subsequently returned `Transport closed`. Exact files, callers and Git diff were used as the documented fallback. Whole-suite green, live fault clearance, physical recovery acceptance, a new capsule and push are NOT RUN.
