# Phase 00 — Typed motion result and safety contract

**Stories:** Foundation for all P1 physical-turn, fault, and end-match behavior.  
**Goal:** replace ambiguous robot completion (`None`, logs, or exceptions) with a typed outcome the controller can safely interpret before any logical commit.

## Files and changes

### `src/hardware/robot_VIP.py`

1. Define a small typed result contract near the robot interface, for example immutable `MotionResult(success: bool, stage: MotionStage, error: str | None = None)`, where `MotionStage` identifies at least preflight/pick-captured/capture-bin/capture-reconcile/pick-moving/place/home/completed. It must represent recoverable SDK conditions explicitly instead of treating a printed warning or `None` return as success.
2. Make `FR5Robot.move_piece(...) -> MotionResult` return `success=True, stage=COMPLETED` only after all commanded stages, including normal home return, complete. Convert expected failures and caught transport/SDK exceptions into `success=False` with the last safe/failed stage and stable diagnostic text; retain exception logging for operators.
3. Preserve existing callers by updating their handling to check `result.success`; do not infer success from absence of an exception. Add a compatibility decision for any legacy path whose caller presently ignores the return, then test that its behavior is unchanged.
4. For captures, split the motion flow at capture removal: after the captured piece reaches the bin and before picking the moving piece, call an injected/explicit verification callback that requires full-board reconciliation of `expected_after_capture` (destination empty, source still occupied). If it fails, return a failed `MotionResult(stage=CAPTURE_RECONCILE, ...)` and never pick the moving piece.
5. Keep `verify_visual_move` geometry information separate from the result’s success. Geometry may be emitted as telemetry/diagnostic metadata but may not independently fail a turn.

### `src/hardware/hardware_manager.py`

1. Provide explicit helpers/callback construction for full-board verification so callers can require `verify_physical_board(expected_board)` at pre-turn, post-capture-removal, and post-place stages without reaching into vision internals.
2. Fail closed on unavailable recognizer/camera or exceptions: `verify_physical_board` returns false/structured failure and does not turn an unavailable check into a pass.

## Tests to write first

### `tests/test_robot_motion_result.py` (new)

- Successful non-capture returns `MotionResult(success=True, stage=COMPLETED)`.
- Each simulated pick/place/home/SDK failure returns `success=False`, preserves its failed stage/error, and never reports success merely because no exception escapes.
- Capture invokes full-board capture-removal reconcile after bin placement and before moving-piece pick; a failure proves no moving-piece pick/place happens.
- Geometry callback/telemetry failure alone does not convert an otherwise successful motion result into failure.

### `tests/test_self_play_controller.py` (extend in Phase 02)

- Controller commits only `MotionResult.success` plus current run/turn token plus final full-board reconciliation. Test failed result and malformed/no result as zero-commit faults.

## Verification

Run the focused motion tests and inspect every `move_piece` call site for an explicit result check. This phase is a hard dependency: self-play controller implementation must not begin until the result contract is passing.

## Exit criteria

Physical orchestration has one typed success signal, capture removal has a mandatory full-board gate before the second pick, and neither logs nor optional geometry can accidentally authorize a commit.
