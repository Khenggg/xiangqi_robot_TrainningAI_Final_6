# Physical Robot-vs-Robot Self-Play — Implementation Plan

**Date:** 2026-09-25  
**Mode:** hard  
**Risk:** high-risk — this feature autonomously dispatches sequential commands to a physical robot arm and must preserve the physical board/FEN safety gate.  
**Source spec:** `plans/physical-robot-self-play/spec.md`

## Scope and outcome

Add a distinct **ROBOT VS ROBOT** launcher action that runs a real-board Xiangqi match with independently selected local-Moonfish profiles for Red and Black. The operator chooses **Continuous** or **Step-by-step** execution. Every turn uses mandatory full-board reconciliation immediately before dispatch, typed `FR5Robot.move_piece` completion, mandatory full-board reconciliation after placement, and only then commits the logical position.

The implementation keeps the current human-Red / AI-Black path intact. It adds a dedicated controller rather than adding a second state machine to `main.py`.

## Spec quality check

**PASS.** No `[NEEDS CLARIFICATION]` items remain; P1/P2 stories, accepted conditions, and safety bounds are testable. The only intentionally excluded behavior is mid-motion interruption.

## Safety invariants (non-negotiable)

1. A self-play run has at most one active turn: either an engine worker, pre-motion validation, robot command, or post-motion verification; the controller never starts another until that turn is terminal.
2. A candidate move is derived from a snapshot of the current state and tagged with a run/turn token. It may commit only if the token remains current, the run is active, typed motion returns `MotionResult.success`, and full-board reconciliation of expected-after succeeds.
3. A physical turn creates exactly one logical commit after success, or zero commits on engine, immediate pre-dispatch reconcile, robot, capture-removal reconcile, or final full-board reconcile failure. Failed moves retain the pre-move FEN/history/turn and set `physical_sync_fault`.
4. End Match is a **no-mid-motion-interrupt** operation: it immediately invalidates queued and engine work and prevents new dispatches. If `move_piece` is already in progress, it is allowed to finish; its result must not commit and no next turn may begin. Request normal safe/home only after that motion returns.
5. Self-play disables/gates `InputHandler` human actions, including manual move confirmation/recovery shortcuts that could alter the same game state. Normal input behavior resumes only after the run is ended/cleared and the state is safe to use.
6. Profile selection is an argument to each AI request. Do not mutate `HardwareManager.config.AI_DIFFICULTY` while alternately playing Red and Black.
7. Existing human-vs-robot semantics, including its Black-only pending commit compatibility and existing test behavior, remain unchanged.
8. Physical self-play fails closed: it cannot start in `DRY_RUN`, without a connected robot, or unless `hw.verify_physical_board(state.board)` confirms the initial full board. Immediately before **every** robot dispatch it must re-check `verify_physical_board(pre_turn_snapshot)`. A move may commit only after typed `MotionResult.success`, a still-current token, and `verify_physical_board(expected_after)` all succeed; geometry-only `verify_visual_move` is telemetry, never a fault or commit gate.
9. A capture has two mandatory full-board states: validate the pre-turn board immediately before dispatch, then validate the expected board with the destination cleared after capture disposal/refresh and before the moving-piece pick.
10. App exit, Home, New Game, and End Match share the controller ending transition. They retain the event loop and hardware until in-flight motion returns, then suppress commit, safe-home, and only then permit cleanup/navigation.

## Lifecycle and ownership

`SelfPlayController` owns run mode, selected profiles, run epoch, active-turn token, worker lifecycle, end/fault state, and scheduling decisions. `GameState` owns board/FEN/history and the color-neutral pending physical move. `HardwareManager` remains the adaptor for robot and camera routines. `main.py` only routes UI actions and calls `controller.tick()` once per frame; it must not duplicate move orchestration.

### Controller states

`IDLE → READY → THINKING → PREPARING → MOVING → VERIFYING → (READY | FINISHED | FAULTED | ENDING) → ENDED`

- In **step** mode, `READY` does nothing until `request_next_move()` accepts an idle active run.
- In **continuous** mode, a committed turn schedules the next turn on a later tick only after the controller is idle; it never recursively dispatches inside a commit callback.
- The active self-play UI may toggle between Step and Continuous only in `READY`; a request during thinking, motion, verification, ending, or fault is rejected without altering the pending turn.
- `end_match()` moves immediately to `ENDING`, increments/invalidate tokens, clears undispatched work, schedules remote end asynchronously, and records whether safe-home is pending after active motion. The UI/event loop remains live until ending finishes.
- A stale worker/result/motion completion is observational only: it may clean up thread bookkeeping but cannot mutate board state, send a move update, or schedule work.

## File map

| File | Change |
| --- | --- |
| `src/core/self_play_controller.py` | New color-neutral lifecycle/orchestration component with injected collaborators suitable for fake-based tests. |
| `src/hardware/robot_VIP.py` | Return typed `MotionResult` with a truthful stage/error from every robot turn; gate capture removal before the moving-piece pick. |
| `src/hardware/hardware_manager.py` | Expose full-board verification callbacks/helpers for the required physical gates. |
| `src/core/game_state.py` | Generalize pending physical-move payload and commit atomically for either side; retain legacy Black wrappers/behavior. |
| `src/ai/ai_controller.py` | Add explicit difficulty/profile override to `pick_move`, preserving old default callers and local-only guarantees. |
| `main.py` | Wire launcher/setup/run controls, create/tick/end controller, guard human input, and update dashboard activity. |
| `src/ui/board_renderer.py` | Render and hit-test Robot-vs-Robot home action, staged setup, active self-play controls, and run status. |
| `src/ui/debug_dashboard.py` | Surface active side, selected profile, and run style in existing activity telemetry. |
| `tests/test_self_play_controller.py` | New controller safety/lifecycle unit tests using fakes. |
| `tests/test_robot_motion_result.py` | Typed robot-outcome and capture-removal-reconcile tests. |
| `tests/test_game_state_physical_commit.py` | New/expanded color-neutral atomic commit tests. |
| `tests/test_policy_engine.py` | Explicit override and no-config-mutation regression tests. |
| `tests/test_difficulty_menu.py` | Home/setup/control hit-test and availability-gating coverage. |
| `tests/test_human_commit_ai_handoff.py` | Confirm existing human-vs-robot path still starts only Black AI work. |

## Phases

0. [Phase 00 — Motion result and safety contract](phase-00-motion-result-and-safety-contract.md) — typed physical outcome and capture-removal board gate.
1. [Phase 01 — State and profile contracts](phase-01-state-and-profile-contracts.md) — P1 physical-commit integrity and per-color AI selection.
2. [Phase 02 — Safe self-play controller](phase-02-safe-self-play-controller.md) — P1 sequencing, fault behavior, termination semantics, and asynchronous API calls.
3. [Phase 03 — Setup and runtime UI integration](phase-03-setup-and-runtime-ui.md) — P1 launcher/setup/run controls and P2 telemetry.
4. [Phase 04 — Verification and hardware readiness](phase-04-verification-and-hardware-readiness.md) — integrated regression, physical safety checklist, and manual real-arm validation.

## Cross-phase test strategy

- Unit-test the controller with deterministic fakes for AI, physical executor, verifier, safe-home callback, API client, and thread completion. Do not use a real camera or arm in automated tests.
- Assert a ten-turn step run sends exactly ten non-overlapping commands only after ten accepted Next actions; assert continuous sends the same sequentially with no operator action.
- Test End/QUIT/Home/New Game before engine dispatch, while engine is outstanding, and while fake `move_piece` is blocked. In all cases assert zero post-end commits/scheduling and no premature hardware cleanup/navigation; for in-flight motion assert safe-home is called only after the blocked call is released.
- Test a failure for both Red and Black at every physical stage, especially immediate pre-dispatch full-board reconcile, post-capture-removal reconcile, typed motion failure, and final full-board reconcile: state remains pre-move, `physical_sync_fault` is true, and further Next/tick calls cannot dispatch.
- Test cadence toggling: it is accepted only while READY, takes effect before the next dispatch, and cannot alter a thinking/moving/verifying turn.
- Run the full existing test suite after each phase and the project compile/import check before physical validation.

## Delivery gates

1. Code review of the controller and `main.py` ownership boundary, with explicit inspection of token checks on every asynchronous completion path.
2. Automated tests pass with no regressions to human-vs-robot.
3. Dry-run operator walkthrough confirms self-play is refused while normal VS ROBOT remains available; fake-driven controller tests validate both styles, safe idle cadence toggling, end behavior, and dashboard text.
4. Supervised real-arm validation may start in either selected cadence, but must use the emergency stop and stop on the first fault. Operator emergency-stop remains the only response for hazardous mid-motion conditions.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Stale engine result commits after End | Run/turn token checks before dispatch and before commit; `end_match()` increments epoch and clears queued candidate. |
| Second move begins while robot/camera is still active | Single controller active-turn state plus a tick-only dispatch gate. |
| Alternating difficulties mutate global config | `AIController.pick_move(..., difficulty=...)` uses a local profile lookup only. |
| A failed physical move silently changes FEN | Pending expected board is committed only after typed motion success and mandatory full-board reconciliation; all failures fault with zero commit. |
| Camera/calibration is absent or incorrect at start | Reject dry-run/disconnected setup and require full preflight `verify_physical_board(state.board)` before dispatching any engine job. |
| Capture disposal leaves board unexpected before second pick | Require a full reconcile of `expected_after_capture` between bin disposal and moving-piece pick. |
| Motion logs imply success after a partial/failed command | `MotionResult.success` and stage/error are mandatory controller inputs; `None`/exceptions fail closed. |
| End/exit blocks on a network call or tears down robot during motion | API sends/end run asynchronously; controller owns ending and only allows teardown after blocked motion returns and safe-home completes. |
| End is mistaken for an emergency stop | UI and code explicitly document no in-flight interruption; pending home occurs only after the dispatched motion returns. |
| Human handlers race self-play | `main.py` bypasses `InputHandler` while controller reports active/ending/faulted self-play. |

## Implementation order

Implement and test phases strictly in order. Phase 03 may not wire a controller until Phase 02 establishes its contracts and token behavior. Phase 04 is the final release gate; do not advertise unattended physical self-play until its real-hardware checklist is completed.
