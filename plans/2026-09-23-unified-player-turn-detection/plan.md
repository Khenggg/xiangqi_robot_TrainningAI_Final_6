# Plan: Unified player-turn detection and idempotent commit

Mode: Hard
Risk: normal — multi-file behavior refactor with deterministic rollback and no schema/infra risk.

**Spec:** `plans/board-stability-turn-confirmation/spec.md`  
**Source design:** `plans/reports/260922-board-stability-turn-confirmation-brainstorm.md`  
**Date:** 2026-09-23

## Scope challenge and spec quality

- **Exists?** Partially. `InputHandler._handle_space_key`, `InputHandler.try_auto_confirm_move`, `InputHandler.poll_board_stability`, and the emergency mouse path can independently reach `GameState.process_human_move`; `BoardStabilityMonitor` and `TurnCompletionMonitor` are separate temporal mechanisms rather than one authority.
- **Minimum?** Add one observation contract, one authoritative player-turn arbiter, and one tokenized commit gate; adapt existing CChess/YOLO and input paths instead of replacing recognition models or Xiangqi rules.
- **Complexity:** Hard. Behavior spans vision, UI input, lifecycle, rollback, AI handoff, baseline capture, physical synchronization, config, and deterministic tests.
- **Spec quality:** PASS. P1/P2/P3 stories and measurable acceptance criteria are present. Timing and ambiguity thresholds remain configuration choices, not behavioral ambiguity.

## Outcome

During a Red turn, the logical board is immutable until a clear and continuously stable physical observation uniquely matches exactly one legal Red successor of that immutable board. Hand/object evidence can block or choose a shorter settle window, but never commits. Automatic polling, SPACE, and supervised mouse correction all submit to one arbiter and one tokenized, idempotent commit gate. A missing, illegal, incomplete, ambiguous, stale, or physically unsynchronized board never advances to AI.

## Chosen architecture

Use a **legal-successor arbiter** rather than reconstructing gestures. At Red-turn activation, capture `committed_board` and generate every legal Red `(src, dst)` successor from `xiangqi.find_all_valid_moves("r", committed_board)` plus `xiangqi.make_temp_move`. Every camera sample is normalized into a board observation and compared against baseline/successors. Intermediate changes, including a lifted piece, are transient.

This combines the two research directions:

1. Interaction-first evidence remains valuable as a safety gate and allows the normal 1.2 s response after interaction.
2. Board-first evidence remains authoritative and supports undetected-hand/tool moves through a longer default 3.0 s stable window.
3. Neither stream owns commit; both publish facts to the same arbiter.

## Authoritative contracts

### Turn context

`PlayerTurnSession` (the implementation may keep `PlayerTurnContext` as a type alias during migration) is created only when the lifecycle declares a physically synchronized Red turn ready:

```text
turn_token: monotonically increasing opaque token
baseline_token: opaque token tied to committed board + physical baseline generation
committed_board: immutable deep copy of GameState.board
legal_successors: move -> immutable resulting board
interaction_seen: bool, false initially
commit_status: OPEN | CLAIMED | COMMITTED | INVALIDATED
committed_move_token: optional deterministic (turn_token, baseline_token, src, dst)
```

The logical `committed_board`, not YOLO occupancy, is the rules baseline. The physical baseline token changes whenever camera baseline identity is replaced, restored, cleared, or invalidated.

### Normalized observation

`BoardObservation` is immutable and has:

```text
observed_at; source_frame_id
layout: optional normalized 10x9 piece matrix
occupancy: optional normalized 10x9 occupied/empty/unknown matrix
visibility: CLEAR | OCCLUDED | INSUFFICIENT | UNAVAILABLE
coverage_ratio; motion_active; hand_or_object_present
recognition_source: CCHESS | YOLO_FALLBACK | FUSED | NONE
cell_confidence; aggregate_confidence
baseline_token; turn_token
```

Normalization rules:

- Prefer a structurally valid CChess piece layout.
- Use YOLO occupancy/visual-difference only as fallback or corroboration; it may narrow candidates but must not invent piece identity.
- Mark disagreements that leave multiple successors plausible as ambiguous.
- Missing/malformed frames produce `UNAVAILABLE`; unknown/low-coverage cells produce `INSUFFICIENT`; motion or detected hand/object produces `OCCLUDED`.
- A hand false negative cannot yield `CLEAR` while motion is active or recognition coverage/confidence is below threshold.

### Interaction facts

`InteractionFact` carries `ENTERED`, `PRESENT`, `LEFT`, or `CLEAR_DEBOUNCED`, its timestamp, detector confidence, and the current tokens. `LEFT` starts, but does not satisfy, clear debounce. Any new `ENTERED/PRESENT`, motion, poor coverage, or token/lifecycle change cancels clear debounce and candidate stability.

### Lifecycle facts

`LifecycleFact` carries Red-turn readiness, game-over, AI turn/thinking, manual correction mode, physical sync fault, reset/new game, rollback, pending AI move, and baseline replacement. Lifecycle is the only authority allowed to activate/invalidate a context.

### Interaction capability

`InteractionCapability = AVAILABLE | DEGRADED | UNAVAILABLE` is a lifecycle fact, not an inferred boolean. `AVAILABLE` requires a real producer capable of detecting hands **and non-hand obstructions/tools**, plus motion/coverage corroboration. `DEGRADED` means only partial producers are live (for example hand detection absent but motion/coverage available). `UNAVAILABLE` means the required blocking evidence cannot be produced.

- Automatic commit is fail-closed unless capability is `AVAILABLE`.
- `PLAYER_TURN_MODE=UNIFIED` is forbidden unless capability is `AVAILABLE`. `DEGRADED` and `UNAVAILABLE` may run only in `SHADOW` or `LEGACY`; they cannot complete a unified turn through AUTO, SPACE, or MOUSE. The operator exits this fail-closed state by restarting/reinitializing in `LEGACY` after the current session is closed.
- A stationary hand/tool covering the board remains `OCCLUDED`; absence of motion is never equivalent to absence of obstruction.

### Session controller

`PlayerTurnSessionController` is the sole owner of `turn_token`, `baseline_token`, session activation, and invalidation. No detector, UI handler, or `GameState` method may mint or replace these tokens directly.

- `verify_and_activate_red_turn(expected_board) -> ActivationResult` verifies lifecycle eligibility, physical-board equivalence, interaction capability, and a successfully captured `DetectorBaselineSnapshot`; only then does it mint both tokens and an immutable `PlayerTurnSession`.
- Every baseline clear/replace/restore operation first publishes session invalidation, then mutates the baseline repository, then may explicitly reactivate after verification. There is no token-preserving baseline mutation.
- Activation results are explicit: `ACTIVATED`, `LIFECYCLE_BLOCKED`, `CAPABILITY_UNAVAILABLE`, `PHYSICAL_MISMATCH`, `BASELINE_CAPTURE_FAILED`, `STALE_REQUEST`.

### Shared transaction boundary and version vector

`PlayerTurnTransactionBoundary` is shared by every correctness-relevant mutation: session activation/invalidation, baseline publish/clear/restore, `GameState` reset/rollback/game-over/fault, AI epoch/pending changes, and human commit claim/local mutation.

```text
VersionVector = (game_epoch, ai_epoch, turn_token, baseline_token,
                 baseline_generation, board_fingerprint,
                 lifecycle_generation)
```

The human commit uses an optimistic prepare/validate protocol:

1. Acquire the boundary, read the complete vector, then release it.
2. Build and validate `RollbackBundle` from that versioned snapshot outside the boundary.
3. Reacquire the same boundary used by invalidation, baseline publication, reset, rollback, and fault transitions.
4. Reread the complete vector. Any mismatch discards the bundle and returns `STALE` before token claim or mutation.
5. If unchanged, perform rule/fingerprint checks, claim/invalidate the token, install the rollback bundle, and apply the local move within the boundary.

`lifecycle_generation` increments on every lifecycle transition even if other values later equal their prior values. No relevant mutation may bypass this boundary.

### Frozen detector baseline

`DetectorBaselineSnapshot` is immutable and deep-copied at capture:

```text
generation; captured_at; calibrated_transform_id/hash
source_frame_id; frame_evidence_copy (or immutable derived evidence)
occupancy 10x9; normalized_layout if available
per_cell_confidence; aggregate_confidence; detector/model versions
```

Copy policy: arrays/matrices are copied and made read-only; mutable detector-owned references are forbidden. Restore policy: validate shape, calibration identity, model compatibility, and checksum; invalidate the active session first; install the snapshot as a **new generation** even when restoring identical content. Calibration change makes old snapshots unrestorable and requires recapture. Generation is monotonic and never rewound by rollback.

## Exact unified FSM

States required by the spec are retained; recovery reasons are data, not extra commit paths.

```text
INACTIVE
  RED_TURN_READY(valid synchronized baseline) -> PLAYER_IDLE [new context/tokens]

PLAYER_IDLE
  interaction/occlusion/motion -> INTERACTING_OR_OCCLUDED
  clear observable board -> VALIDATING_FINAL_BOARD
  lifecycle block/token invalidation -> INACTIVE

INTERACTING_OR_OCCLUDED
  interaction still present OR motion/coverage poor -> INTERACTING_OR_OCCLUDED
  apparent disappearance/partial/change -> INTERACTING_OR_OCCLUDED [transient only]
  interaction leaves -> WAITING_FOR_CLEAR [start clear debounce]
  lifecycle block/token invalidation -> INACTIVE

WAITING_FOR_CLEAR
  interaction/motion/poor coverage returns -> INTERACTING_OR_OCCLUDED [reset timers]
  clear debounce incomplete -> WAITING_FOR_CLEAR
  clear debounce complete -> VALIDATING_FINAL_BOARD
  lifecycle block/token invalidation -> INACTIVE

VALIDATING_FINAL_BOARD
  unavailable/poor coverage/occlusion -> INTERACTING_OR_OCCLUDED or WAITING_FOR_CLEAR
  unstable cell placement/candidate changes -> UNSETTLED_PLACEMENT
  observed board == committed_board -> PLAYER_IDLE [cancel candidate; no commit]
  missing/partial/illegal/no legal match -> WAITING_FOR_CORRECTION(reason)
  >1 legal successor within ambiguity margin -> AMBIGUOUS_BOARD
  exactly 1 legal successor -> VALIDATING_FINAL_BOARD [start/continue appropriate settle timer]
  unique candidate reaches continuous window -> MOVE_CONFIRMED [emit commit request]

UNSETTLED_PLACEMENT
  occlusion/motion -> INTERACTING_OR_OCCLUDED
  candidate/layout changes -> UNSETTLED_PLACEMENT [restart timer]
  clear stable sample -> VALIDATING_FINAL_BOARD
  lifecycle block/token invalidation -> INACTIVE

AMBIGUOUS_BOARD
  occlusion/motion -> INTERACTING_OR_OCCLUDED
  committed-board equality -> PLAYER_IDLE
  exactly 1 candidate -> VALIDATING_FINAL_BOARD [new timer]
  invalid/incomplete -> WAITING_FOR_CORRECTION
  lifecycle block/token invalidation -> INACTIVE

WAITING_FOR_CORRECTION
  occlusion/interaction -> INTERACTING_OR_OCCLUDED
  committed-board equality -> PLAYER_IDLE
  clear changed observation -> VALIDATING_FINAL_BOARD [new timer]
  timeout -> WAITING_FOR_CORRECTION [diagnostic only]
  lifecycle block/token invalidation -> INACTIVE

MOVE_CONFIRMED
  ACCEPTED -> INACTIVE [token invalidated before next poll; GameState turn becomes Black]
  DUPLICATE -> INACTIVE [already consumed; no side effect]
  STALE -> INACTIVE [session already invalidated/replaced]
  RULE_MISMATCH | FINGERPRINT_MISMATCH -> WAITING_FOR_CORRECTION [invalidate candidate]
  INFRA_FAILURE -> WAITING_FOR_CORRECTION [turn remains Red; no mutation]
```

`MOVE_CONFIRMED` means a request is ready, not that `GameState` has already mutated. Only successful atomic commit completes the turn.

## Strict conflict precedence

Every event is reduced in this exact order; the first applicable outcome wins:

1. **Lifecycle/safety:** game over, non-Red turn, reset, rollback in progress, AI/pending AI lifecycle, physical sync fault, `WAITING_FOR_MANUAL_AI_SYNC`, unavailable/degraded interaction capability, manual correction suspension, or disabled feature -> invalidate/suspend automatic context; zero commit.
2. **Token freshness/order:** absent/mismatched/invalidated `turn_token` or `baseline_token`, or an observation older than the last accepted observation for the same session -> discard observation/request and reset candidate; zero commit.
3. **Occlusion/visibility:** hand/object present, motion active, clear debounce incomplete, unavailable/malformed frame, insufficient coverage/confidence -> block validation/commit.
4. **Stability:** layout/candidate/visibility/source changes before the continuous window -> restart candidate timer.
5. **Baseline equality:** observation equivalent to `committed_board` -> cancel candidate and return `PLAYER_IDLE`; zero commit.
6. **Invalid/incomplete/ambiguous:** missing-piece-only, illegal transform, zero matches, or multiple matches/insufficient winner margin -> recoverable state; zero commit.
7. **Unique legal successor:** exactly one full-board successor above threshold and margin may accumulate stability.
8. **Commit:** only the same unique candidate with unchanged tokens and lifecycle may call the atomic gate.

Manual intent never skips precedence 1–6. In UNIFIED, SPACE and MOUSE exist only while capability is AVAILABLE. SPACE requests a bounded burst through the same arbiter and obeys clear debounce, visibility, legality, uniqueness, and token checks. Missing baseline is never silently replaced. If capability becomes DEGRADED/UNAVAILABLE, invalidate the unified session; the operator must restart/reinitialize in LEGACY rather than bypass through SPACE or MOUSE.

## Unique legal-successor matching

For each immutable successor, score all 90 cells using piece identity where available and occupancy where identity is unavailable. Return one of:

- `BASELINE_EQUAL`: committed board matches within strict equivalence thresholds.
- `UNIQUE(move, successor, score, margin)`: one candidate passes minimum score and `best - second_best >= ambiguity_margin`.
- `AMBIGUOUS(candidates)`: multiple plausible successors or inadequate margin.
- `INVALID(reason)`: no successor, missing-piece-only, illegal/full-layout mismatch, malformed input.
- `UNAVAILABLE(reason)`: not enough evidence to decide.

Captures compare the complete successor (`src: Red -> empty`, `dst: Black -> moving Red`) rather than a source/destination occupancy shortcut. Candidate timing key is `(turn_token, baseline_token, move, normalized-layout fingerprint, visibility class, interaction-window class)`; changing any component resets elapsed time and sample count.

Defaults:

- clear debounce: `0.8 s`, minimum 3 clear samples;
- interaction-observed settle: `1.2 s`, minimum 3 matching samples;
- no-interaction settle: `3.0 s`, minimum 5 matching samples;
- observation sample interval: `0.10 s`;
- coverage threshold: `0.95`; aggregate confidence: `0.70`; ambiguity margin: `0.10`.

Tests inject a fake monotonic clock; no test sleeps.

## Tokenized idempotent commit

Add `HumanMoveCommitCoordinator.try_commit(request: CommitRequest) -> CommitResult` as the only route to `GameState` human-move mutation. `CommitRequest` contains the current session tokens, committed-board fingerprint, candidate move/successor fingerprint, and source. The coordinator alone creates the immutable `RollbackBundle` from current authoritative state before token claim.

`RollbackBundle` contains deep copies of logical board/FEN/turn/move number/history/captured lists/UI move metadata, `DetectorBaselineSnapshot`, session identity, and AI epoch. It is built and validated **before** token claim. If the complete bundle cannot be acquired or validated, return `INFRA_FAILURE`; do not claim/invalidate the token and do not mutate anything.

Using `PlayerTurnTransactionBoundary`:

1. Read the complete version vector under the shared boundary, then build/validate the rollback bundle; preparation failure -> `INFRA_FAILURE` with the session open.
2. Reacquire the boundary and compare the full vector; mismatch -> discard bundle and `STALE` before claim.
3. Verify Red lifecycle/tokens; consumed move -> `DUPLICATE`, invalid token -> `STALE`.
4. Revalidate rules; failure -> `RULE_MISMATCH`. Verify board/session/successor fingerprints; failure -> `FINGERPRINT_MISMATCH`.
5. Claim/invalidate the token, install rollback bundle, apply local move, switch to Black, increment `human_commit_generation`, record consumed token, and clear candidates within the same boundary.
6. Return `ACCEPTED` after local mutation. External API synchronization is outside this transaction.

`CommitResult` is exactly one of `ACCEPTED`, `DUPLICATE`, `STALE`, `RULE_MISMATCH`, `FINGERPRINT_MISMATCH`, `INFRA_FAILURE`; every result has the deterministic FSM transitions above.

### Post-commit API synchronization

`ACCEPTED` is final after local board/FEN/history/turn/rollback/token mutation and before remote simulation API work. Then enqueue one sync operation keyed by `move_token`.

- Success emits `API_SYNCED(move_token)`.
- Failure emits `API_SYNC_PENDING(move_token, attempt, reason)` and retries; exhausted policy emits `API_SYNC_FAILED` but never rolls back the local move.
- Retry reuses the same payload/token and never calls the commit coordinator or increments `human_commit_generation`.
- If the API accepts an idempotency key, use `move_token`. Otherwise document **at-least-once** remote delivery and provide reconciliation for duplicate/unknown remote state; local commit remains exactly-once.

Keep `process_human_move` temporarily as a compatibility wrapper that requires an internal validated request, emits a deprecation diagnostic, and cannot be called by input/stability paths after migration.

## Lifecycle and physical synchronization

- **Red-turn activation:** after game start or committed AI move, do not create context until physical board verification/baseline capture succeeds and matches `GameState.board`. Failed capture keeps FSM `INACTIVE` with `baseline_unavailable` diagnostic.
- **Baseline replacement:** `capture_baseline_if_needed`, `clear_yolo_baseline`, and `restore_yolo_baseline` publish a new generation/token. Replacement invalidates candidates; restoration after rollback creates a new token even if occupancy/time values equal old ones.
- **AI generation:** accepted human commit increments `human_commit_generation`. AI scheduling mints `ai_job_token=(game_epoch, ai_epoch, human_commit_generation)` exactly once. Worker result carries this token and may be consumed only if it still equals the current token, the turn is Black, and no reset/rollback/fault occurred. Reset, rollback, game over, physical fault, and supervised correction increment `ai_epoch` and invalidate pending job/results. A rejected/duplicate request never changes the generation or schedules AI.
- **AI physical move:** `pending_ai_move` or `physical_sync_fault` keeps the player arbiter `INACTIVE`. Only `commit_pending_ai_move` plus successful physical baseline readiness opens a new Red context.
- **SPACE:** submits `MANUAL_VALIDATE` and requests a bounded validation burst from the same observation pipeline. It never clears or silently creates a baseline on ordinary/missing-baseline rejection and never forces `manual_override_active`; it reports the arbiter reason.
- **Emergency mouse sub-FSM:** available in UNIFIED only while capability remains AVAILABLE. `MANUAL_OFF --M--> MANUAL_SELECT_SOURCE --valid Red source--> MANUAL_SELECT_DESTINATION --valid destination--> MANUAL_VALIDATING`. Invalid source/destination remains in the relevant selection state with a reason. `ESC`, right-click, reset, turn/lifecycle/capability change, or a second `M` cancels to `MANUAL_OFF`, clears selection, and invalidates/re-derives the session. While manual state is active, AUTO and SPACE are blocked; MOUSE still requires the full clear physical observation. Result mapping is exact: `ACCEPTED -> MANUAL_OFF/INACTIVE`; `DUPLICATE|STALE -> MANUAL_OFF`; `RULE_MISMATCH -> MANUAL_SELECT_DESTINATION`; `FINGERPRINT_MISMATCH -> MANUAL_OFF + WAITING_FOR_CORRECTION`; `INFRA_FAILURE -> MANUAL_VALIDATING + WAITING_FOR_CORRECTION`. There is no capability-bypassing unified mouse override.
- **Rollback (`Z`):** invalidate session and increment `ai_epoch` first. A human move may be undone only before any AI physical execution begins. Once robot execution has started or the physical board may have changed, `Z` must refuse silent logical rollback and enter supervised physical correction. A permitted rollback restores logical state and validated baseline bundle, installs a new baseline generation/token, and remains inactive until physical verification. Late observations, AI results, and commits from before rollback are rejected.
- **Robot disconnected/manual AI placement:** enter explicit `WAITING_FOR_MANUAL_AI_SYNC`. The Red arbiter stays inactive. A dedicated reconcile command (default `V`, not Red-turn SPACE) validates the expected Black successor and captures/activates the Red baseline; SPACE cannot reconcile this state.
- **New game/game over/surrender:** invalidate context and pending candidates immediately.

## Diagnostics

Emit one structured transition/rejection record without raw frames:

```text
timestamp, fsm_from, event, fsm_to, reason,
turn_token, baseline_token, observation_id,
visibility, coverage, motion, interaction_seen,
candidate_move, best_score, second_score, ambiguity_margin,
stable_samples, stable_elapsed, required_elapsed,
commit_source(AUTO|SPACE|MOUSE), commit_result
```

Rate-limit repeated same-state diagnostics while keeping transitions and commit rejections unthrottled. Expose a concise operator status for `WAITING_FOR_CLEAR`, `WAITING_FOR_CORRECTION`, `AMBIGUOUS_BOARD`, physical sync, and camera unavailable.

## Runtime mode

Replace overlapping booleans with one enum:

```text
PLAYER_TURN_MODE = LEGACY | SHADOW | UNIFIED
```

Startup validates the enum, thresholds, and capability. `LEGACY` alone owns legacy commit; `SHADOW` runs unified logic with zero commit authority while legacy owns commit; `UNIFIED` disables legacy commit and is rejected unless `InteractionCapability.AVAILABLE` passed the stationary hand/tool health check. Mode changes require restart/reinitialization. If capability drops at runtime, invalidate the session and require recovery of the producer before fresh UNIFIED activation, or restart/reinitialize in LEGACY.

## Phased migration

| Phase | Stories | Result |
|---|---|---|
| [Phase 01](phase-01-contracts-and-arbiter.md) | P1 core, P2 diagnostics | Pure types, matcher, FSM, deterministic result transitions; no runtime routing change. |
| [Phase 02](phase-02-lifecycle-session-and-baseline.md) | P2 lifecycle safety, P3 recovery | Session controller, immutable baseline, activation/invalidation, AI epoch, rollback scope, manual AI sync are proven before cutover. |
| [Phase 03](phase-03-observation-adapters-shadow.md) | P1 all physical scenarios | Capability-gated interaction/obstruction and CChess/YOLO normalization run in SHADOW; no unified commit authority. |
| [Phase 04](phase-04-atomic-commit-and-input-cutover.md) | P2 single commit owner, P3 SPACE/mouse | Coordinator, rollback bundle, manual sub-FSM, SPACE/AUTO/MOUSE cut over only after prior lifecycle tests pass. |
| [Phase 05](phase-05-scenario-regression-and-rollout.md) | All P1/P2/P3 | Full race/scenario matrix, compatibility cleanup, staged rollout and rollback evidence. |

## Files and symbol map

Planned additions:

- `src/vision/player_turn_types.py`: enums/dataclasses including immutable `PlayerTurnSession`, states, facts, observations, match and commit requests/results.
- `src/vision/legal_successor_matcher.py`: `LegalSuccessorMatcher.build`, `match`, board fingerprints and full capture matching.
- `src/vision/player_turn_arbiter.py`: `PlayerTurnArbiter.activate`, `deactivate`, `ingest_interaction`, `ingest_observation`, `request_manual_validation`, `on_commit_result`, `snapshot`.
- `src/vision/board_observation_adapter.py`: `BoardObservationAdapter.observe/normalize_cchess/normalize_yolo/fuse`.
- `src/core/player_turn_session_controller.py`: `PlayerTurnSessionController.verify_and_activate_red_turn`, `invalidate`, baseline-generation callbacks, activation results.
- `src/core/human_move_commit_coordinator.py`: `HumanMoveCommitCoordinator.try_commit`, rollback-bundle acquisition/validation, result mapping.
- `src/core/player_turn_transaction.py`: `PlayerTurnTransactionBoundary`, full version-vector snapshot/compare, and shared mutation guard.
- `src/api/move_sync_queue.py`: move-token-keyed `API_SYNC_PENDING/SYNCED/FAILED` retry and reconciliation state (or equivalent adapter around the existing client).
- `tests/test_legal_successor_matcher.py`, `tests/test_player_turn_arbiter.py`, `tests/test_player_turn_session_controller.py`, `tests/test_human_move_commit_coordinator.py`, `tests/test_player_turn_scenarios.py`, `tests/test_player_turn_races.py`.

Planned modifications:

- `src/ui/input_handler.py`: replace `_handle_space_key`, dead `try_auto_confirm_move`, and `poll_board_stability` commit logic with arbiter/coordinator submission; implement manual mouse sub-FSM and dedicated manual-AI reconcile command; reset old monitors only as adapters during migration.
- `src/core/game_state.py`: private validated move application, `human_commit_generation`, `ai_epoch`/job token state; integrate reset/game-over/rollback/pending AI without owning session tokens.
- `src/hardware/hardware_manager.py`: make `capture_baseline_if_needed`, `clear_yolo_baseline`, and `restore_yolo_baseline` invalidate through the session controller and return frozen baseline generations; expose interaction capability and normalized observation acquisition.
- `src/vision/snapshot_detector.py`: expose evidence/layout/occupancy without committing or conflating changed-board with valid-move; remove first-match/Manhattan fallback from unified matching so ambiguity is never resolved arbitrarily.
- `src/vision/board_stability_monitor.py`: deprecate standalone emission; optionally reuse as pure candidate timer until removed.
- `src/vision/turn_completion_monitor.py`: deprecate standalone completion request; emit interaction facts only.
- `main.py`: poll one arbiter, publish lifecycle transitions around game start/AI/pending physical move, and gate AI generation on successful turn mutation.
- `config.py`: add the single `PLAYER_TURN_MODE` enum plus timing, coverage, confidence, ambiguity and diagnostics settings; legacy timing aliases remain read-only compatibility in LEGACY only.
- `src/ui/board_renderer.py`: optionally display concise arbiter/recovery status from render state.
- Existing tests `tests/test_board_stability_monitor.py`, `tests/test_turn_completion_monitor.py`, `tests/test_human_move_confirmation.py`, `tests/test_emergency_client_move.py`, and `tests/test_visual_pick_estimator.py`: migrate assertions to the unified contract while preserving compatibility expectations.

## Rollout, compatibility, and rollback

1. Start with `PLAYER_TURN_MODE=SHADOW`; run matcher/FSM and log proposed transitions without unified commit authority while legacy remains authoritative.
2. Compare shadow decisions against SPACE/stability outcomes in deterministic tests and supervised physical sessions. No raw frames are stored by default.
3. Set `PLAYER_TURN_MODE=UNIFIED` only after capability is AVAILABLE and the stationary hand/tool gate passes. Otherwise remain SHADOW/LEGACY.
4. Retain `PLAYER_TURN_MODE=LEGACY` for one release as rollback. Change mode only on restart/reinitialization with no open session.
5. Rollback is config-only: set LEGACY and restart. No schema/data migration exists.
6. Remove `try_auto_confirm_move`/standalone stability commit and legacy aliases only after the full suite and a physical soak checklist pass.

## Validation questions (non-blocking defaults)

1. Which runtime producer detects a stationary hand, sleeve, and generic tool obstruction? This producer is mandatory for UNIFIED. If none passes the stationary-obstruction test, deployment remains SHADOW/LEGACY; there is no SPACE/MOUSE bypass.
2. Can CChess provide calibrated per-cell confidence for all 90 cells? Default: accept aggregate plus available cell confidence; unknown cells reduce coverage and cannot directly produce a unique full-layout match.
3. Should an operator-only logical mouse override exist in UNIFIED? Default: no. A failed physical verification cannot commit; operator recovery requires closing the unified session and restarting/reinitializing in LEGACY. Dry-run is a separate non-physical configuration and still requires AVAILABLE capability to enter UNIFIED.
4. Should SPACE shorten the no-interaction settle window? Default: no; SPACE requests sampling immediately but uses the same window class determined by observed interaction.
5. Should board-equivalence tolerate low-confidence piece identity if occupancy is exact? Default: baseline equality must be conservative; uncertain identity returns unavailable/ambiguous rather than falsely canceling or committing.

## Definition of done

- `HumanMoveCommitCoordinator.try_commit(CommitRequest)` is the one runtime human commit owner; direct mutation calls from hand, stability, SPACE, and mouse paths are absent.
- All specified states and precedence rules are represented by deterministic unit tests with an injected clock.
- Every P1 scenario, legal capture, no-hand fallback, ambiguity, malformed frame, and correction recovery has a sequence test.
- Concurrent hand-exit, stability, SPACE, and mouse requests commit at most once for a turn token.
- Stale baseline/turn observations, rollback races, reset/game-over races, physical sync faults, and AI-start races commit zero times.
- Reset, rollback, fault, or baseline replacement between bundle preparation and claim changes the shared version vector and yields STALE before claim.
- Local ACCEPTED remains committed if API sync fails; move-token retry cannot create a second human commit.
- Successful human commit invalidates its token before AI can observe Black turn; AI starts once.
- Baseline capture/clear/restore and AI physical reconciliation explicitly activate or invalidate the arbiter.
- Existing player move, emergency, rollback, stability, and physical sync tests pass or are deliberately replaced with equivalent unified-contract tests.
- Structured diagnostics contain state/event/reason/tokens/timing/candidate/confidence without raw-frame persistence.
- `PLAYER_TURN_MODE` restart-based rollback to legacy behavior is documented and tested.
- No cutover is allowed until Phase 02 activation/invalidation/reset/AI-pending/fault/rollback and AI-epoch tests pass.
