# Phase 04 — Atomic commit coordinator and AUTO/SPACE/MOUSE cutover

**Stories:** P2 single owner/idempotency; P3 SPACE and emergency mouse.  
**Dependencies:** Phase 01 matcher/FSM, Phase 02 lifecycle/session tests, and Phase 03 AVAILABLE capability/shadow evidence must pass.

## Goal

Install one coordinator that prepares rollback before claim and routes all human intents through deterministic result handling. Then switch atomically to `PLAYER_TURN_MODE=UNIFIED`.

## Changes

1. Add `src/core/human_move_commit_coordinator.py`:
   - `HumanMoveCommitCoordinator.try_commit(request: CommitRequest) -> CommitResult` is the only public human mutation route.
   - Read the full version vector under `PlayerTurnTransactionBoundary`, release, then acquire/deep-copy/validate `RollbackBundle`. Preparation failure returns `INFRA_FAILURE` before claim.
   - Reacquire the shared boundary and reread the vector. Any mismatch (including reset/rollback/fault/baseline replace) discards the bundle and returns `STALE` before claim.
   - Map consumed -> `DUPLICATE`, invalid token -> `STALE`, Xiangqi failure -> `RULE_MISMATCH`, board/session/successor mismatch -> `FINGERPRINT_MISMATCH`.
   - Claim/invalidate token and apply local mutation within the boundary; return `ACCEPTED` before any remote API request.
2. Add `src/api/move_sync_queue.py` (or existing-client adapter):
   - Enqueue after ACCEPTED using `move_token`; emit `API_SYNCED`, `API_SYNC_PENDING`, or `API_SYNC_FAILED`.
   - API failure never rolls back local state. Retry never calls commit or increments human generation.
   - Use remote idempotency key if supported; otherwise document at-least-once delivery and reconciliation.
3. Modify `src/core/game_state.py`:
   - Move `process_human_move` internals to a private coordinator-only apply method.
   - Preserve one immutable rollback bundle and enforce rollback scope from Phase 02.
4. Modify `src/ui/input_handler.py`:
   - AUTO feeds arbiter requests to coordinator.
   - SPACE performs a bounded sample burst through the same arbiter; missing baseline/capability/visibility fails closed and never silently recaptures/clears baseline.
   - Implement manual sub-FSM: `MANUAL_OFF`, `MANUAL_SELECT_SOURCE`, `MANUAL_SELECT_DESTINATION`, `MANUAL_VALIDATING`; `M` enters/toggles cancel, `ESC`/right-click/lifecycle change cancels.
   - Manual mode blocks AUTO and SPACE but allows MOUSE validation. Real MOUSE intent requires a clear physical successor; dry-run may synthesize trusted observation. Rejections return deterministically to selection/correction.
5. Modify `main.py`:
   - `PLAYER_TURN_MODE` startup validation ensures exactly one owner.
   - UNIFIED polls only arbiter/coordinator; SHADOW has zero authority; LEGACY excludes unified commit.
   - Schedule AI once from accepted `human_commit_generation`; validate `ai_job_token` before consuming results.

## Deterministic tests

Add `tests/test_human_move_commit_coordinator.py`:

- rollback bundle acquisition/validation failure returns `INFRA_FAILURE` before claim/mutation;
- pre-mutation bundle/dependency failure produces no commit;
- local ACCEPTED mutates board/FEN/history/captured once and increments generation once before API;
- local ACCEPTED plus API failure remains committed with `API_SYNC_PENDING/FAILED`;
- move-token retry never creates a second human commit; if remote lacks idempotency, reconciliation reports at-least-once status;
- DUPLICATE, STALE, RULE_MISMATCH, FINGERPRINT_MISMATCH mutate nothing;
- reset, rollback, fault, and baseline replacement injected between bundle acquisition and claim return STALE before claim;
- concurrent AUTO/SPACE/MOUSE requests result in one ACCEPTED and deterministic loser results.

Add/update input tests:

- SPACE missing baseline does not capture changed board; all blocker reasons remain Red;
- manual substate entry/source/destination/validation/cancel transitions are exact;
- all six commit results map exactly to the manual/FSM states specified in `plan.md`;
- AUTO/SPACE blocked during manual mode while MOUSE validation proceeds;
- real mouse needs physical match; dry-run synthetic path still requires AVAILABLE capability; there is no logical-only UNIFIED recovery, so operator fallback closes the session and restarts/reinitializes LEGACY;
- direct `InputHandler`/vision references to human mutation are absent.

Add AI cutover tests:

- one accepted generation schedules one AI job;
- duplicate/rejected commits schedule none;
- stale AI token after rollback/reset/fault is ignored;
- mode startup rejects invalid mode/conflicting legacy wiring and hot-switch with open state.

## Exit criteria

- `HumanMoveCommitCoordinator.try_commit(CommitRequest)` is the sole human mutation owner with one signature everywhere.
- A complete validated rollback bundle always exists before token claim.
- Every CommitResult has its specified arbiter/manual transition and zero unintended side effects.
- UNIFIED cannot start unless Phase 02 lifecycle tests and Phase 03 AVAILABLE stationary-obstruction capability gate pass; SPACE/MOUSE cannot bypass it.
