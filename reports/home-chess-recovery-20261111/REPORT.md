# HOMECHESS recovery — 2026-11-11

Branch: `fix/fix-capsule`; implementation baseline `4c0e6a22fd28a8fa4b57dd44fca0ef08675fa82d`.

## Delivered source behavior

The user requested automatic return to the taught HOMECHESS after a failed pickup, manual removal of any held piece, restoration of the position before pickup, and retry of the unfinished move. Ctrl+F8 is retired.

- VS ROBOT keeps the exact pending AI move, FEN, board and history uncommitted when physical execution fails. It freezes the operation identity **before** execution; a stale failure cannot authorize HOME for a newer move.
- An owned recovery worker checks measured robot-base TCP, joints, active tool/user frame, controller idle/fault state, driver authorization and stop/gripper gates. It lifts vertically at measured XY/tool orientation to at least existing SAFE_Z, then requests the exact frozen taught HOMECHESS joints/pose once. It neither opens the gripper nor enables/resets the controller while parking.
- Both two fresh distinct idle packets and HOME TCP/joint agreement are required before the UI shows **R / RETRY MOVE**. The operator removes the held piece, restores the old board including any captured piece, withdraws their hands and explicitly presses R. The program checks the entire old board and current HOME again, establishes the acknowledged empty gripper's open state, reacquires visual targets and executes the **same pending move**. It does not ask the AI to select a replacement move.
- Capture-removal checkpoints are cleared only after that full old-board proof. A failed retry parks again and waits for another deliberate acknowledgment; there is no automatic move-retry loop. FEN commits once after successful verified execution; post-commit API/baseline errors do not replay movement.
- Physical pick/place test mode has an equivalent owner-bound HOME/manual-reset/retry flow and retains its separate test board. Pre-pick vision acquisition failures that dispatched no motion retain the existing visual R/X retry. Post-capture visual failures enter HOME recovery.
- If parking fails, the UI displays **H / HOMECHESS** for one deliberate recheck after controller repair. An uncertain RPC outcome blocks automatic follow-up movement. Stale/missing telemetry, wrong frames, active gripper pulses, revoked authorization and latched stops stay blocked.
- Ctrl+F8 event bindings and active runtime hints were removed. Shared non-VSC V reconciliation now includes explicit operator stop confirmation, preserving the fresh measured-stop gates. F2 cleanup/mode-switch retries perform the same read-only confirmation on a live startup/operator worker; closed motion workers do not make recovery unreachable. Ordinary cleanup does not implicitly approve it.

## Main implementation boundaries

- `src/hardware/home_chess_recovery.py`: bounded, measured HOME recovery and read-only HOME verification. TCP position 1 mm, orientation 1 degree, and absolute joint difference 1 degree are named acceptance thresholds, **not measured physical-clearance certification**. Measured TCP/joints and active frames must belong to the exact SDK packet pinned by the physical reader. The target pose/joints/frame are frozen before any movement.
- `src/hardware/robot_VIP.py`: preserves uncertain transport outcomes in MotionResult metadata across the VSC adapter's exception wrapping.
- `src/modes/vsc_v3/core/home_recovery.py`: immutable-operation identity contract plus recovery status/ownership. No game-state mutation or motion authority.
- `src/modes/vsc_v3/ui/input_handler.py`, `src/modes/vsc_v3_session.py`: async/sync failure entry, manual acknowledgment, same-move replay and post-commit protection.
- `src/modes/vsc_v3/core/game_state.py`, `src/modes/vsc_v3/ui/board_renderer.py`: prevent reset/rollback/bypass while recovery owns the move and display R/H state.
- `main.py`, `src/ui/input_handler.py`: remove the shortcut while keeping non-VSC operator recovery reachable through V/F2.

No change to existing calibration artifacts, shared board geometry, kinematics, collision margins, gripper timings or executable hardware configuration. No dependency added. Existing local notes and verification tools were preserved.

## Verification

Environment: Windows; repository Python 3.12.10; pytest 9.1.1; `DRY_RUN=1`, `ROBOT_BACKEND=VIRTUAL`; worker numerical-thread caps applied by the project runner. Robot IO/camera are mocked or deterministic SDK packets. **No physical robot command was executed.**

Focused verification **PASS**, exit 0: **252 parallel + 1 serial = 253 tests**, 31.16 seconds. Full command and output are in `focused-tests.log`:

```powershell
$env:PATH="$PWD/.venv312/Scripts;$env:PATH"
$env:DRY_RUN='1'
$env:ROBOT_BACKEND='VIRTUAL'
$env:PYTHONIOENCODING='utf-8'
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_home_chess_recovery.py,tests/unit/test_vsc_home_recovery.py,tests/unit/test_stop_recovery_controls.py,tests/unit/test_legacy_physical_robot_gates.py,tests/unit/test_vsc_v3_session.py,tests/unit/test_vsc_v3_lifecycle.py,tests/unit/test_vsc_v3_namespace.py,tests/unit/test_hvr_mode_dispatch.py,tests/unit/test_session_buttons.py,tests/unit/test_fresh_session_startup.py,tests/unit/test_session_user_flows.py,tests/unit/test_recovery_block_diagnostics.py
```

The new tests exercise real event/state/recovery code with fake physical IO: same pending identity, capture restoration, test-mode ownership, board/epoch/request replacement, unknown command outcomes, tool/user mismatch, SDK packet races, taught-point mutation, equivalent TCP with wrong joints/winding, transient post-command MOVING packets, failed gripper-open result, stop/worker gates and removed Ctrl+F8 dispatch. An actual borrowed physical reader is exercised against deterministic SDK packets. Three diagnostic assertions were aligned with the current English panel and the newly replaced V instruction; no safety assertion was removed.

Independent scoped code review: **APPROVED**, 9.5/10, no remaining P1/P2 identified after corrections. Independently reproduced stale-entry and deferred-reset bugs are covered by regression tests; patched stale-entry sends zero HOME commands.

Additional checks **PASS**, exit 0: Python compilation of changed production modules, `git diff --check`, graph impact inspection (`scope=unstaged`, base/since HEAD), and real pygame dummy-display rendering of normal, waiting-manual and HOME-failed screens at 1440x1080. `waiting_manual.png` and `home_failed.png` preserve the UI render checks. These are not physical or live keyboard acceptance.

Final guard hardening **PASS**, exit 0: 144 recovery/control tests, 12.21 seconds, using `tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_home_chess_recovery.py,tests/unit/test_vsc_home_recovery.py,tests/unit/test_stop_recovery_controls.py`. This overlaps the 253-test run above and adds two driver-dispatch-binding regressions. Output: `final-recovery-tests.log`. The existing driver dispatch predicate is preserved before each recovery command and while polling.

Full non-slow regression: **INCOMPLETE / interrupted**, exit -1 after 1045.49 seconds. Command: `tools/test_fast.ps1 -Mode Concurrent` (2 workers; 1348 cases collected in the parallel phase). It emitted failure markers, reached 96%, then continued long-running cases; only this run's verified pytest process tree was terminated. No final failure traces/counts were produced, and the serial phase was **NOT RUN**. Failure origins are **UNKNOWN** for this run; do not label all markers baseline failures or report a green whole branch. Output: `full-regression.log`. The last two guard tests were added after full-suite collection and are covered by the final 144-test run instead.

## Physical acceptance and remaining limits

**NOT RUN:** live FR3 movement, real held-piece intervention, real recovery path/clearance, camera-under-recovery acceptance, complete real-game trial, and new capsule packaging. Source changes require restarting the application to load them.

A point named HOMECHESS does not certify an arbitrary path from every fault pose. Controller faults that prohibit motion, unknown transport outcomes, latched stops and unresolved gripper-output failures may block parking. The code reports this rather than resetting the controller or falsifying stopped/empty-gripper state. If a safe-idle gripper output write failed, H alone cannot clear the uncertain pulse flag; operator/controller intervention remains required. Do not infer physical acceptance from the offline tests.

The VSC donor's existing gameplay state remains in memory; this feature does not add durable recovery across process exit. Shared non-VSC recovery remains its own transaction/reconciliation flow and does not gain automatic move replay.
