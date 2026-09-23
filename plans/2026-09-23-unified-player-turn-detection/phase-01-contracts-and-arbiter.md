# Phase 01 — Contracts, legal-successor matcher, and pure arbiter

**Stories:** P1 core board semantics; P2 one authority and diagnostics.  
**Runtime behavior:** No routing change in this phase.

## Goal

Build a deterministic, side-effect-free domain layer that can classify observations and run the exact FSM without camera, Pygame, robot, sleeping, or `GameState` mutation.

## Changes

1. Add `src/vision/player_turn_types.py` with:
   - `PlayerTurnState`, `Visibility`, `RecognitionSource`, `InteractionCapability`, `InteractionEvent`, `LifecycleEvent`, `CommitSource`, `CommitStatus`, `ApiSyncEvent`, `MatchKind`, `RejectionReason`.
   - Frozen `PlayerTurnSession`, `DetectorBaselineSnapshot`, `RollbackBundle`, `BoardObservation`, `MatchResult`, `CommitRequest`, `CommitResult`, `ActivationResult`, and `TransitionDiagnostic` dataclasses.
   - Board deep-copy/fingerprint helpers that reject non-10x9 layouts.
2. Add `src/vision/legal_successor_matcher.py`:
   - `LegalSuccessorMatcher.build(committed_board)` enumerates legal Red moves through `xiangqi.find_all_valid_moves` and constructs immutable successors using `xiangqi.make_temp_move`.
   - `match(observation)` checks baseline equality before successor matching and produces `BASELINE_EQUAL`, `UNIQUE`, `AMBIGUOUS`, `INVALID`, or `UNAVAILABLE`.
   - Score full layouts; for YOLO occupancy-only observations, never claim uniqueness when distinct legal successors share the same evidence.
   - Verify captures by comparing the entire resulting board.
3. Add `src/vision/player_turn_arbiter.py`:
   - Constructor accepts config values and injected monotonic clock.
   - `activate`, `deactivate`, `ingest_lifecycle`, `ingest_interaction`, `ingest_observation`, `request_manual_validation`, `on_commit_result` implement the FSM and precedence from `plan.md`.
   - Automatic/SPACE requests are fail-closed for `DEGRADED` or `UNAVAILABLE` interaction capability.
   - Maintain continuous clear/candidate timers; reset on token, lifecycle, visibility, candidate/fingerprint, or window-class change.
   - Emit a `CommitRequest` only once per unchanged context/candidate; do not mutate `GameState`.
   - Return structured transition/rejection diagnostics.

## Deterministic tests

Add `tests/test_legal_successor_matcher.py`:

- unchanged full layout -> `BASELINE_EQUAL`;
- ordinary legal move -> one `UNIQUE` move;
- legal capture checks source empty, destination replacement, and captured Black disappearance;
- source-only disappearance -> `INVALID`, never capture/move;
- illegal Red transformation, multiple changes, malformed matrix -> `INVALID`/`UNAVAILABLE`;
- occupancy-only evidence matching multiple successors -> `AMBIGUOUS`;
- winner below score or margin threshold -> `AMBIGUOUS`.

Add `tests/test_player_turn_arbiter.py` with a fake clock:

- assert every state transition listed in `plan.md`;
- assert precedence table row-by-row (lifecycle > stale token > occlusion/coverage > stability > equality > invalid/ambiguous > unique > commit);
- interaction-observed candidate confirms at 1.2 s/3 samples; no-interaction confirms at 3.0 s/5 samples;
- any candidate, visibility, baseline token, turn token, lifecycle, or window-class change resets timing;
- out-of-order observations for the same session are rejected and cannot rewind/advance a timer;
- timeout in correction emits diagnostic only;
- `MOVE_CONFIRMED` emits once and waits for commit result.
- `ACCEPTED`, `DUPLICATE`, `STALE`, `RULE_MISMATCH`, `FINGERPRINT_MISMATCH`, and `INFRA_FAILURE` each produce the exact state transition specified in `plan.md`.
- API sync events are orthogonal to commit results: `API_SYNC_PENDING/FAILED` cannot move the player FSM backward or emit another commit.

## Exit criteria

- Domain tests use no real time or hardware.
- Matcher cannot return `UNIQUE` for incomplete evidence that also supports another legal successor.
- FSM has no call/import to `GameState.process_human_move`.
- All spec states and conflict priorities have direct assertions.
