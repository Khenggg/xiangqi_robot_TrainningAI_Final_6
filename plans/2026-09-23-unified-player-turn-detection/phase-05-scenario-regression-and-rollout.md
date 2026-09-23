# Phase 05 — Full scenario matrix, diagnostics, compatibility, and rollout

**Stories:** All P1/P2/P3 stories.

## Goal

Prove the full behavior and races deterministically, verify compatibility, then stage deployment with a config-only rollback path.

## Scenario matrix

Add `tests/test_player_turn_scenarios.py` table-driven sequences with fake clock and scripted facts/observations:

| Scenario | Expected result |
|---|---|
| Hand/tool enters and leaves, no board change | Return `PLAYER_IDLE`; 0 commits. |
| Piece moved then returned to origin before clear | Intermediate transient; final equality; 0 commits. |
| Red piece lifted off-board and held indefinitely | Stay interaction/occlusion; committed board unchanged; 0 commits. |
| Held piece returned to origin, then board clears | `PLAYER_IDLE`; 0 commits. |
| Held piece placed on legal new square, hand remains | Blocked; 0 commits until clear debounce + short settle. |
| Held piece placed legally and clears | Exactly 1 commit after interaction window. |
| Legal move without detected interaction | Exactly 1 commit after longer no-interaction window. |
| Hand enters but no move, then re-enters during debounce | Timer resets; 0 commits. |
| Hand false negative while motion/coverage poor | Not clear; 0 commits. |
| Piece removed and hand leaves ROI without replacement | `WAITING_FOR_CORRECTION`; 0 commits/no timeout pass. |
| Illegal move or multiple pieces rearranged | `WAITING_FOR_CORRECTION`; 0 commits. |
| Multiple legal candidates under weak identity | `AMBIGUOUS_BOARD`; 0 commits. |
| Piece between squares/candidate oscillates | `UNSETTLED_PLACEMENT`; timer repeatedly resets. |
| Normal legal move | Exactly 1 commit with correct source/destination. |
| Legal capture | Exactly 1 commit; Black piece captured; complete successor match. |
| Stable object false positive | Invalid/insufficient; 0 commits. |
| Camera missing/malformed/contradictory | Red turn retained; baseline unchanged. |
| SPACE during occlusion/ambiguity | Reason shown; 0 commits. |
| SPACE + auto + hand-exit same move | Exactly 1 local commit, API-sync enqueue, and rollback snapshot; retry may send remotely without recommit. |
| Emergency mouse + automatic candidate race | At most 1 commit; real-mode physical verification and physical sync policy enforced. |
| Baseline replaced during settle | Candidate resets; old request rejected. |
| Baseline replacement races activation | Invalidation is published first; no old-token observation/commit survives. |
| Turn changes/game over/reset during settle | Context invalidated; 0 stale commits. |
| Rollback concurrent with ready request | Rollback invalidation wins; 0 stale commits. |
| Rollback before AI physical execution | Restore allowed with new epoch/generation and required re-verification. |
| Rollback after AI physical execution starts | Silent logical rollback refused; supervised physical correction required. |
| Human commit followed by main-loop AI polling | AI worker starts exactly once. |
| Stale AI worker result after reset/rollback/fault | `ai_job_token` mismatch; result ignored. |
| AI physical sync fault while candidate exists | Safety block wins; candidate discarded. |
| Robot disconnected/manual Black placement | `WAITING_FOR_MANUAL_AI_SYNC`; SPACE rejected; dedicated reconcile command activates Red only after match. |
| Interaction producer unavailable/degraded | UNIFIED startup/activation refused; remain SHADOW/LEGACY; no SPACE/MOUSE bypass. |
| Stationary hand/tool with zero motion | Visibility remains occluded; 0 commits. |
| Manual substate active | AUTO/SPACE blocked; MOUSE validation or explicit cancel only. |
| Rollback bundle cannot be acquired | `INFRA_FAILURE` before claim; logical/physical state unchanged. |
| Reset between bundle acquisition and claim | Version mismatch; bundle discarded; STALE before claim. |
| Rollback between bundle acquisition and claim | Version mismatch; bundle discarded; STALE before claim. |
| Baseline replace/fault between acquisition and claim | Version mismatch; bundle discarded; STALE before claim. |
| Pre-mutation bundle/dependency failure | No local commit and no API-sync enqueue. |
| Local commit succeeds, API send fails | Move remains committed; `API_SYNC_PENDING/FAILED`; no rollback. |
| API retry | Same move token/payload; no second human commit/generation increment. |

## Regression and compatibility

1. Migrate or retain assertions in:
   - `tests/test_board_stability_monitor.py`
   - `tests/test_turn_completion_monitor.py`
   - `tests/test_human_move_confirmation.py`
   - `tests/test_emergency_client_move.py`
   - `tests/test_visual_pick_estimator.py`
2. Run focused suite, then full repository suite. Record deliberately changed expectations: rejection no longer clears baseline or automatically enters mouse override; timeouts never advance turn.
3. Add source-level guard assertions that only `HumanMoveCommitCoordinator.try_commit(CommitRequest)` reaches private human mutation and every reset/rollback/fault/baseline publish/session invalidation uses `PlayerTurnTransactionBoundary`.
4. Verify configuration rejects nonsensical values (invalid `PLAYER_TURN_MODE`, negative windows, min samples <1, thresholds outside 0..1, no-interaction window shorter than interaction window unless explicitly allowed) and rejects mode changes with open session/manual/commit/AI/recovery state.

## Diagnostics verification

- Assert transitions include state/event/reason/tokens/timing/candidate/confidence.
- Assert repeated same-state frames are rate-limited while rejections/commits are not lost.
- Assert logs never contain raw image data, auth tokens, or full frame serialization.
- Verify operator statuses distinguish: clear wait, correction required, ambiguity, unavailable camera, stale baseline, and physical sync fault.

## Rollout checklist

1. Ship pure tests with `PLAYER_TURN_MODE=SHADOW`; unified commit has zero authority.
2. Run supervised recorded/scripted scenarios and compare shadow decisions to expected matrix.
3. Run physical soak: normal move, capture, return-to-origin, long-held piece, tool occlusion, no-hand-detected move, bad placement, SPACE race, rollback, AI physical fault.
4. After Phase 02 lifecycle tests and Phase 03 AVAILABLE capability proof pass, restart with `PLAYER_TURN_MODE=UNIFIED`; force fresh synchronized baseline/context.
5. Monitor rejection reasons, settle latency, ambiguity rate, duplicate/stale rejections, and correction dwell time.
6. Roll back by restarting with `PLAYER_TURN_MODE=LEGACY`; never hot-switch modes.
7. After one stable release/soak period, remove legacy commit shims and old config aliases in a separate cleanup change.

## Commands to define during implementation

Use the project's current test runner; expected focused form:

```text
python -m unittest tests.test_legal_successor_matcher
python -m unittest tests.test_player_turn_arbiter
python -m unittest tests.test_player_turn_session_controller
python -m unittest tests.test_board_observation_adapter
python -m unittest tests.test_human_move_commit_coordinator
python -m unittest tests.test_player_turn_lifecycle
python -m unittest tests.test_player_turn_scenarios
python -m unittest tests.test_player_turn_races
python -m unittest discover -s tests
```

## Definition of done

- Every matrix row passes deterministically without sleeping.
- Focused and full regression suites pass.
- LEGACY, SHADOW, and UNIFIED have startup-validated, mutually exclusive authority.
- AVAILABLE real interaction/obstruction capability is proven, including stationary hand/tool, before UNIFIED automatic commit is allowed.
- UNIFIED startup is impossible for DEGRADED/UNAVAILABLE capability; operator rollback is restart/reinitialize to LEGACY.
- Lifecycle/session activation and invalidation tests pass before input cutover.
- Shared version-vector races for reset/rollback/fault/baseline replacement return STALE before claim.
- Local commit and API sync tests prove API failure never rolls back or duplicates the human move; non-idempotent remote delivery is marked at-least-once with reconciliation.
- Physical supervised checklist has recorded pass/fail evidence and tuned thresholds remain config-only.
- Config-only rollback has a deterministic test and operator instructions.
- All P1/P2/P3 acceptance criteria and the top-level definition of done in `plan.md` are satisfied.
