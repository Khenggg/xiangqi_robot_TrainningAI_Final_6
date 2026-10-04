# Phase 02 — Lifecycle, session controller, baseline, AI epoch, and rollback policy

**Stories:** P2 lifecycle safety/idempotency; P3 supervised recovery.  
**Cutover rule:** Unified commit remains disabled. Phase 04 cannot begin until this phase's activation/invalidation/reset/AI/fault/rollback tests pass.

## Goal

Establish one owner for session tokens and prove all invalidation races before any automatic or manual input is allowed to use unified commit.

## Changes

1. Add `src/core/player_turn_session_controller.py`:
   - `PlayerTurnSessionController` solely owns monotonically increasing `turn_token` and `baseline_token`.
   - `verify_and_activate_red_turn(expected_board) -> ActivationResult` checks Red lifecycle, no game-over/pending AI/fault/manual-AI-sync, `InteractionCapability.AVAILABLE`, physical-board equivalence, and successful baseline capture before creating `PlayerTurnSession`.
   - `invalidate(reason)` closes session before reset, game-over, rollback, baseline mutation, AI pending/execution, physical fault, calibration change, or mode reinitialization.
   - Baseline repository callbacks follow invalidate-first -> capture/clear/restore -> optional explicit reverify/reactivate ordering.
2. Add `src/core/player_turn_transaction.py`:
   - `PlayerTurnTransactionBoundary` guards session activation/invalidation, baseline publication, reset/rollback/game-over/fault, AI epoch/pending mutation, and later commit claim/local mutation.
   - Expose immutable `VersionVector(game_epoch, ai_epoch, turn_token, baseline_token, baseline_generation, board_fingerprint, lifecycle_generation)` snapshots.
   - Increment `lifecycle_generation` on every lifecycle transition; forbid direct relevant mutation outside the boundary.
3. Add frozen `DetectorBaselineSnapshot` storage in `src/hardware/hardware_manager.py`:
   - Deep-copy/read-only occupancy, normalized layout/evidence, confidence, calibration hash, detector/model version, capture metadata.
   - Restore validates checksum/shape/calibration/model compatibility and always installs a new monotonic generation.
   - Failed capture/restore leaves no active session.
4. Modify `src/core/game_state.py` and `main.py` lifecycle only:
   - Add `game_epoch`, `ai_epoch`, `human_commit_generation`, current `ai_job_token`, and result validation helpers.
   - Reset/game-over/rollback/fault increments `ai_epoch` and invalidates worker results.
   - Add `WAITING_FOR_MANUAL_AI_SYNC` for robot-disconnected/manual Black placement; default `V` reconciliation verifies expected Black board, captures baseline, then activates Red. Red SPACE is rejected in this state.
   - Pending AI move and robot execution invalidate Red session before physical work.
5. Define rollback behavior in `GameState.handle_rollback`:
   - Human undo allowed only before AI physical execution begins.
   - After robot execution begins or physical state is uncertain, refuse silent logical rollback and enter supervised physical correction.
   - Permitted rollback restores a validated immutable `RollbackBundle`, increments epochs, creates a new baseline generation, and requires physical verification before activation.
6. Modify `config.py` to define and startup-validate only `PLAYER_TURN_MODE=LEGACY|SHADOW|UNIFIED`; reject UNIFIED unless capability is AVAILABLE and reject invalid values/hot switching with open state.

## Deterministic tests

Add `tests/test_player_turn_session_controller.py`:

- activation succeeds only after physical match + valid baseline + AVAILABLE capability;
- DEGRADED/UNAVAILABLE capability returns `CAPABILITY_UNAVAILABLE` and no session;
- failed capture/mismatch/lifecycle fault returns explicit `ActivationResult` and no tokens;
- baseline replacement race invalidates session before snapshot mutation; concurrent old observation/request is stale;
- reset, rollback, fault, and baseline publish all mutate the shared version vector under the same boundary;
- restore of identical content produces a new generation/token; incompatible calibration/model restore fails closed;
- no component outside controller can mint session tokens.

Add `tests/test_player_turn_lifecycle.py`:

- reset/new game/game over/surrender/AI pending/physical fault invalidate first;
- AI physical commit does not activate Red until verification + capture succeed;
- robot disconnected enters `WAITING_FOR_MANUAL_AI_SYNC`; SPACE cannot reconcile; dedicated `V` command can;
- `ai_job_token=(game_epoch, ai_epoch, human_commit_generation)` starts once and stale worker results after reset/rollback/fault are ignored;
- rollback before AI physical execution succeeds through bundle restore; rollback after execution is refused and requests supervised physical correction;
- late pre-rollback observation/commit/AI result has zero effect.

## Exit criteria

- Activation, invalidation, reset, pending AI, physical fault, manual AI sync, rollback scope, and AI epoch races all pass deterministically.
- Baseline mutation cannot occur while an old session remains valid.
- Red detection cannot activate during `WAITING_FOR_MANUAL_AI_SYNC` or physical uncertainty.
- Unified commit/input cutover remains unavailable until these tests pass.
