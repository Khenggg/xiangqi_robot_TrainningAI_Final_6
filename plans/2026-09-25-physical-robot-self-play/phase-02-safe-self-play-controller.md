# Phase 02 — Safe self-play controller

**Stories:** P1 self-play, both run styles, End Match, fault containment.  
**Goal:** introduce a testable lifecycle owner that serializes engine, robot, and verification work and enforces the no-mid-motion-interrupt policy.

## Files and changes

### `src/core/self_play_controller.py` (new)

1. Define a narrow dependency surface (game state, AI picker, physical-move executor/HardwareManager adapter, API client, clock/thread factory if needed) so tests can inject fakes. Avoid importing Pygame or reading UI globals.
2. Store immutable run configuration: `red_difficulty`, `black_difficulty`, `run_mode` (`continuous`/`step`), run epoch, active turn token, state/status, and whether home is pending after motion. Reject invalid profiles/modes before a run starts.
3. `start(...)` fails closed before a run exists: reject `DRY_RUN`, a missing/disconnected robot, either unavailable selected profile, or a false/exceptional `hw.verify_physical_board(state.board)` full-board preflight. Only after all gates pass may it configure self-play metadata, capture a baseline, create an appropriately labeled remote match if applicable, and enter `READY`. Do not schedule a Step-mode turn yet.
4. `request_next_move()` only accepts an active Step-mode controller in idle `READY`, with no fault/game-over/end. It creates one tokenized engine request for `state.turn` and the profile for that color.
5. `tick()` owns nonblocking progress: harvest worker output; discard stale/ended results; independently compute legal moves for the snapshot; treat an explicit engine failure/invalid candidate as `FAULTED`, while only an empty legal-move list may end the game; create a color-neutral pending move; and immediately before every `move_piece` dispatch require `hw.verify_physical_board(pre_turn_snapshot)`. For captures pass `expected_after_capture` into the Phase-00 capture-removal reconcile callback. After typed motion returns, optionally record `verify_visual_move` geometry telemetry, but only `MotionResult.success`, a still-current token, and `hw.verify_physical_board(expected_after)` permit commit.
6. Run engine, full-board vision checks, physical motion, and remote API calls behind nonblocking worker boundaries so the event loop can process End/QUIT/Home/New Game during a real `move_piece` or a slow endpoint. Keep all board commit/scheduling decisions on the main controller/tick thread after completion. API update/end workers are best-effort telemetry: failures are recorded, never authorize a move, and never block safety ending.
7. On success, enqueue one API board update, evaluate king/game-over, refresh the established baseline only when appropriate, update activity/status, and either return to `READY` (Step) or schedule exactly one later Continuous turn. Never recurse directly into the next dispatch.
8. On explicit engine failure/invalid result, immediate pre-dispatch reconcile failure, capture-removal reconcile failure, missing/failed `MotionResult`, or final full-board reconcile failure: clear only uncommitted pending state as required, preserve pre-move logical state, set `physical_sync_fault`, enter `FAULTED`, expose an operator-recovery status, and prevent automatic retries. Geometry telemetry failure alone must not fault or block a turn.
9. `end_match()` is idempotent. It immediately marks inactive/ENDING, increments run/token epoch, drops queued results, prevents current engine result dispatch, and enqueues remote end once if a room exists without waiting for that network call. **It must never call a robot stop/cancel API.** If physical motion is active, defer `go_to_home_chess()` until its worker reports completion; then call safe-home once without verifying/committing/sending that motion. If no physical motion is active, call safe-home once immediately and finish `ENDED`. Expose a `can_finalize_exit`/completion signal only after safe-home is finished and all safety-relevant worker bookkeeping is terminal.
10. Expose read-only properties for UI: active/accepts_next, mode, active color/profile, busy phase, ended/faulted, and human-input-disabled. Keep fault and user-end distinguishable.
11. Add `set_run_mode("step" | "continuous")` that accepts only an active controller in `READY`, with no engine/motion/verification task pending. Switching to Continuous schedules its next move on a later tick; switching to Step cancels only the not-yet-created successor intent. Rejecting a busy/faulted/ending request must leave the mode and active token unchanged.

### `src/core/game_state.py`

1. Add only minimal self-play metadata/reset hooks required by the controller; do not splice controller lifecycle into GameState.
2. Ensure controller cancellation has an authoritative epoch invalidation path compatible with existing AI token fields, without treating an in-flight physical command as cancelable.

## Tests to write first

### `tests/test_self_play_controller.py` (new)

Build fakes that record call order and hold/release engine or motion work deterministically.

- Setup rejects DRY_RUN, disconnected/missing robot, either unavailable selected difficulty, or failed/exceptional full-board preflight and makes no engine/motion/API start calls.
- Step mode has zero engine/motion calls before Next; ten accepted Next actions produce ten alternating color calls and exactly ten sequential physical calls/commits.
- Continuous mode commits a ten-turn scripted sequence without Next and asserts a maximum concurrent engine/motion count of one.
- Each turn calls AI with `state.turn` and the matching Red/Black difficulty override; alternate profiles are observed in the fake.
- Explicit engine failure/invalid move with legal moves faults; an engine `None` with no legal moves alone ends the game. Immediate pre-dispatch full-board reconcile, capture-removal reconcile, missing/failed typed motion result, and final `verify_physical_board(expected_after)` failures for both colors each produce zero commit, unchanged FEN/history/turn, `physical_sync_fault`, fault state, and no further dispatch. Include a fake where geometry fails but full-board verification and typed motion succeed to prove geometry is telemetry-only, and a geometry-pass/full-board-fail fake to prove it cannot commit.
- End before dispatch: no motion/commit occurs, queued candidate is ignored, API end is called once, safe-home is called once.
- End while engine worker is outstanding: releasing the engine later cannot dispatch or commit.
- End during blocked motion: End returns promptly; safe-home is not called while motion is blocked; after release, the move is not verified/committed/sent and safe-home is called exactly once.
- Slow API update/end worker never blocks `end_match()` or the UI tick; its eventual completion cannot schedule/commit a move.
- End after a successful idle commit prevents the continuous next dispatch and clears active self-play state.
- A legal game-over result ends the remote match once and cannot schedule a successor turn.
- An idle READY cadence toggle from Step to Continuous schedules exactly one later move; Continuous to Step prevents the next successor. Toggles during Thinking, Moving, Verifying, Ending, or Faulted are rejected without cancelling or changing the active turn.

## Verification

Run `pytest tests/test_self_play_controller.py tests/test_game_state_physical_commit.py tests/test_policy_engine.py`, then the full suite. Perform a manual code review of every token comparison and every path from End to worker completion.

## Exit criteria

There is one controller responsible for self-play scheduling, it never overlaps turns, and tests demonstrate that termination cannot generate a later command or commit—even when it is requested during a dispatched move.
