# Phase 04 — Verification and hardware readiness

**Stories:** All P1 stories and P2 dashboard observability.  
**Goal:** prove automated correctness and perform controlled physical readiness checks before allowing a longer unattended run.

## Automated release checks

1. Run the focused controller/state/profile/UI tests and `pytest tests`; record the exact passing output.
2. Run the project’s standard import/compile check (identify from current project tooling; use `python -m compileall main.py src` if no narrower documented command exists).
3. Review changed files against [plan.md](plan.md) safety invariants, especially:
   - no `config.AI_DIFFICULTY` mutation on a self-play turn;
   - all worker completions compare the run/turn token before dispatch and before commit;
   - exactly one owner triggers `move_piece`;
   - every dispatch has an immediate full pre-turn reconcile and captures have a full expected-after-capture reconcile before the moving-piece pick;
   - final commit checks typed `MotionResult.success`, current token, and full expected-after reconcile; geometry telemetry never independently faults;
   - post-End motion completion has no API update, verification commit, or successor scheduling;
   - safe-home is deferred until a dispatched motion completes.
4. Request a focused code review of controller threading/token paths and the main-loop input gate. Resolve blocking findings and rerun checks after changes.

## Dry-run acceptance walkthrough

1. Launch to Home; confirm normal VS ROBOT is unchanged.
2. Select Robot vs Robot and prove it refuses to start in DRY_RUN; then use real-hardware fakes to show a disconnected arm or failed full-board preflight refuses before any engine/motion/API work. Choose distinct available profiles and prove a disabled profile cannot start.
3. Start Step mode; confirm no action precedes Next. Execute a scripted sequence of ten Next requests and inspect one-at-a-time fake/simulated motion log and alternating dashboard activity.
4. Start Continuous mode; inspect serialization for a short scripted run. Toggle cadence only while READY and prove a toggle during simulated motion is rejected without changing the active turn.
5. In each relevant phase (Ready, Thinking, simulated moving, post-commit idle), invoke End Match. Confirm the status text describes deferred stop during motion and no successor appears.
6. Inject/enable a fake full-board post-move verification failure for Red and Black (including geometry-pass/full-board-fail) and verify fault blocks further turns without a FEN/history change.
7. Simulate slow API update/end calls plus QUIT/Home/New Game during blocked motion; confirm the app remains responsive, does not clean up hardware early, and only finalizes after safe-home.

## Real-hardware readiness checklist

The operator must remain at the emergency stop and must approve each progression; this checklist does not authorize unattended first-run motion.

1. Confirm this is not DRY_RUN; robot is connected; HOMECHESS is taught/verified; gripper safe-idle routine is healthy; camera calibration is current; initial pieces match the standard layout; and the controller's full `verify_physical_board(state.board)` preflight plus baseline capture succeeds.
2. Select either cadence for the first supervised run. Run one verified non-capture for Red, inspect source/destination and gripper/clearance, then one verified Black non-capture. Change cadence only while READY.
3. Run a controlled capture and confirm full pre-turn reconcile, full `expected_after_capture` reconcile after disposal and before moving-piece pick, then full post-move `verify_physical_board(expected_after)` before the FEN changes. Geometry verification is telemetry only.
4. Press End while idle and verify no following move begins and the robot goes to normal home.
5. With the operator ready to use hardware emergency stop if needed, request End during an intentionally observable motion. Verify the application queues no follow-up/commit and homes only after the robot reports the command returned. Do not attempt software force interruption.
6. Run a short supervised Continuous sequence once the prior checks pass. Stop on the first mismatch/fault; do not use automatic retry.

## Exit criteria

Automated checks and a supervised real-arm sequence support the safety claims, with physical fault/termination behavior understood by the operator. Longer continuous calibration runs remain an operator decision, not a replacement for emergency-stop procedures.
