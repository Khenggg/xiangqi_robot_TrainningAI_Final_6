# Spec: Unified player-turn completion detection

**Date:** 2026-09-23
**Status:** Ready for planning

---

## Problem Statement

Player-turn completion is currently inferred through separate mechanisms: a hand-interaction gate and a board-stability poller. A temporary disappearance can mean that a Red piece is being held outside the board, while a stable board difference can be a completed move, an illegal/incomplete position, recognition noise, or a board obstruction. If either mechanism commits independently, the AI can start before the player has finished or the same move can be committed twice.

The system needs one authoritative turn-completion state machine. Hand/object/occlusion evidence may prevent confirmation or accelerate validation, but only a clear, stable final board that uniquely matches one legal Red successor of the committed board may complete the player's turn.

---

## User Stories

- **[P1]** As a player, I can touch the board without moving a piece and remain on my turn.
  Accepted when: hand/object entry and exit with a final board equivalent to the committed board produces no move and returns to the idle player-turn state.

- **[P1]** As a player, I can move a piece and return it to its original square without ending my turn.
  Accepted when: all intermediate observations remain transient and the restored final board produces no commit.

- **[P1]** As a player, I can lift a Red piece off the board and hold it while thinking without the piece being treated as captured, lost, or moved.
  Accepted when: disappearance of one or more pieces during occlusion never mutates the committed board and never starts the AI turn.

- **[P1]** As a player, I can return a held piece to its original square and continue my turn.
  Accepted when: after the board clears and settles, equivalence with the committed board returns the state machine to idle without a commit.

- **[P1]** As a player, I can place a held Red piece on a new legal square and complete my turn only after the board is clear and stable.
  Accepted when: exactly one legal Red successor remains stable for the configured window and is committed exactly once.

- **[P1]** As a player, my move is not confirmed while a hand, tool, sleeve, or other obstruction remains over the board.
  Accepted when: any active interaction/occlusion or insufficient board visibility has higher priority than candidate stability and blocks confirmation.

- **[P1]** As a player, a legal physical move made without a detected hand event can still complete my turn.
  Accepted when: a unique legal successor is accepted after the longer no-interaction stability window.

- **[P1]** As an operator, I want incomplete, illegal, missing-piece, and ambiguous boards to remain on the player's turn.
  Accepted when: none of those observations call `process_human_move`; they enter a recoverable waiting state with a diagnostic reason.

- **[P2]** As an operator, I want one commit owner so that the hand path, stability path, SPACE fallback, and UI override cannot commit the same physical move twice.
  Accepted when: all automatic evidence feeds one arbiter and the commit operation rejects stale turn/baseline tokens and repeated move tokens.

- **[P2]** As an operator, I want transition diagnostics so physical failures can be tuned and reproduced.
  Accepted when: logs expose state, event, candidate, confidence, baseline/turn token, timers, and rejection/recovery reason.

- **[P3]** As an operator, I retain manual SPACE and supervised correction as explicit fallback paths.
  Accepted when: manual confirmation uses the same validation and atomic commit gate; recovery never silently advances the turn.

---

## Functional Requirements

1. FR-01: Capture an immutable committed-board snapshot and a unique turn/baseline token when a Red turn becomes ready.
2. FR-02: Generate or validate candidate final boards against the committed board; a candidate is acceptable only when it corresponds to exactly one legal Red Xiangqi move.
3. FR-03: Treat piece disappearance, partial layouts, and all board changes observed during hand/object/occlusion activity as transient observations, not committed board mutations.
4. FR-04: Represent at least these states: `INACTIVE`, `PLAYER_IDLE`, `INTERACTING_OR_OCCLUDED`, `WAITING_FOR_CLEAR`, `VALIDATING_FINAL_BOARD`, `UNSETTLED_PLACEMENT`, `AMBIGUOUS_BOARD`, `WAITING_FOR_CORRECTION`, and `MOVE_CONFIRMED`.
5. FR-05: Apply conflict precedence in this order: lifecycle/safety blocks; stale baseline/turn; active occlusion or insufficient visibility; unstable observation; board equal to committed baseline; invalid/incomplete/ambiguous board; unique legal stable successor; commit.
6. FR-06: Reset candidate stability whenever the candidate, visibility classification, baseline token, turn token, or lifecycle state changes.
7. FR-07: Require a continuous clear-board debounce before validation. A hand-detector false negative must not by itself make the board clear when recognition coverage or motion evidence remains poor.
8. FR-08: Use separate settle windows for interaction-observed and no-interaction paths. Defaults must remain configurable and deterministic in tests.
9. FR-09: If the board becomes clear while a piece remains missing or the layout cannot represent one legal successor, enter `WAITING_FOR_CORRECTION`; do not auto-pass, auto-delete a piece, or start the AI.
10. FR-10: Returning to the committed board from any transient/recovery state returns to `PLAYER_IDLE` without completing the turn.
11. FR-11: Captures must validate the complete source/destination transformation, including replacement of the Black destination piece by the Red moving piece.
12. FR-12: Manual SPACE, mouse override, and automatic confirmation must converge on one validation result and one idempotent commit method.
13. FR-13: After a successful commit, invalidate the turn token before any further poll and reset all interaction/stability candidates.
14. FR-14: Preserve the committed board when camera frames are missing, malformed, low-confidence, or contradictory.
15. FR-15: Preserve CChess piece-layout recognition as preferred evidence and YOLO occupancy/visual-difference evidence as fallback, but normalize both into one observation contract before state transitions.

---

## Conflict Resolution Contract

The interaction stream and board-observation stream never commit independently. They publish facts to one arbiter:

- Interaction facts: entered, present, left, clear debounce elapsed, interaction seen this turn.
- Board facts: visibility/coverage, motion, normalized layout, candidate legal successors, confidence and ambiguity margin.
- Lifecycle facts: active Red turn, game over, manual override, physical sync fault, baseline token and turn token.

Higher-priority blocking facts win over lower-priority positive facts. In particular:

1. `game_over`, non-Red turn, physical sync fault, or manual override suspends/reset automatic confirmation.
2. Active or recently cleared occlusion blocks commit even if a legal candidate is visible.
3. Missing/low-confidence coverage blocks commit even if the hand detector reports clear.
4. Equality with the committed board cancels all candidates and keeps the Red turn.
5. Invalid, incomplete, or multiple legal candidates enter recovery/ambiguity states.
6. Only one clear, stable, unique legal successor may request an atomic commit.
7. Atomic commit succeeds only when its baseline/turn token still matches; success invalidates the token immediately.

---

## Non-Functional Requirements

- Safety: zero automatic turn transitions from incomplete, occluded, illegal, ambiguous, or stale observations in deterministic tests.
- Idempotency: at most one human-move commit per turn token across automatic, SPACE, and mouse paths.
- Responsiveness: with interaction observed, confirm a clear unique legal move within 1.0–1.5 seconds after the last meaningful board/occlusion change; the no-interaction fallback may use a configurable 2.0–4.0 second window.
- Availability: camera/model failure retains the current Red turn and manual/supervised recovery path.
- Observability: every state transition and rejected commit request is diagnosable without storing raw camera frames by default.

---

## Success Criteria

- [ ] Every scenario listed in the P1 stories has a deterministic sequence test.
- [ ] Zero commits occur while occlusion is active, clear debounce is incomplete, or board visibility is insufficient.
- [ ] Zero commits occur when the final layout equals the committed board.
- [ ] Zero commits occur for missing-piece-only, illegal, malformed, or ambiguous final layouts.
- [ ] A normal legal move and a legal capture each commit exactly once after the correct settle window.
- [ ] The same physical move observed concurrently by hand-exit and stability evidence commits exactly once.
- [ ] A stale candidate from a replaced baseline or previous turn commits zero times.
- [ ] Manual SPACE remains functional and cannot double-commit an automatic move.
- [ ] All existing player-move, emergency-mode, rollback, and board-stability tests remain passing or are deliberately migrated to the unified contract.

---

## Out of Scope

- Training a new hand/object detector.
- Changing Xiangqi move rules or AI policy.
- Automatically deciding that a physically removed piece is forfeited.
- Automatically repairing an unknown physical board state.
- Changing robot post-move physical synchronization except where lifecycle gating must suspend player-turn detection.

---

## Assumptions

- The logical game state before the Red turn is authoritative and can be copied as the committed board.
- Existing CChess/YOLO paths can provide enough evidence to score a settled board or resolve a legal move.
- A timeout is diagnostic only; it never transfers the turn by itself.
- The player controls Red and the AI controls Black in the physical game loop.
