# Spec: Board-stability player-turn confirmation

**Date:** 2026-09-22
**Status:** Ready

---

## Problem Statement

Automatic move confirmation currently depends on detecting a human hand entering and leaving the board. Players using a tool or another object need the system to confirm a completed physical move from the board state itself.

---

## User Stories

- **[P1]** As a player, I want a move made with any object to be detected so that I do not need to press SPACE after every turn.
  Accepted when: a changed, legal Red move is auto-confirmed without any hand-detection event.

- **[P1]** As a player, I want the system to wait until the board settles so that a piece being moved is not confirmed prematurely.
  Accepted when: confirmation occurs only after the changed board state remains stable for a configured 1.0–1.5 seconds.

- **[P1]** As an operator, I want invalid or incomplete positions rejected so that the AI never responds to a false move.
  Accepted when: the candidate move passes existing Xiangqi validation before game state is changed.

- **[P2]** As an operator, I want stable-state diagnostics so that I can tune camera thresholds.
  Accepted when: logs report candidate, stability duration, samples, and rejection reason.

- **[P3]** _(out of scope — noted for future)_ UI controls for changing stability settings during a match.

---

## Functional Requirements

1. FR-01: While it is Red's turn and a valid T1 baseline exists, sample board observations continuously without requiring a hand event.
2. FR-02: Start a candidate only when the observed board differs from T1 with sufficient Red-move evidence.
3. FR-03: Confirm only a candidate that represents one legal Red Xiangqi move and remains equivalent across the configured stability window.
4. FR-04: Set the default stability window to 1.2 seconds, configurable only within 1.0–1.5 seconds, and require at least three matching legal observations distributed across that window.
5. FR-05: Reset the candidate when the observation changes, becomes invalid, or the turn/baseline changes.
6. FR-06: Preserve manual SPACE confirmation as a fallback.
7. FR-07: Preserve CChess recognition as the preferred source and YOLO/visual capture evidence as the fallback.

---

## Non-Functional Requirements

- Performance: confirm a stable legal move no earlier than 1.0 seconds and no later than 1.5 seconds after the final candidate-state change, excluding camera/model failures.
- Security: not applicable; this is an offline physical-board control path.
- Availability: a missing CChess or object-detection result must retain the current manual fallback instead of changing game state.

---

## Success Criteria

- [ ] Legal move confirmation: 100% of deterministic unit-test candidate sequences with at least three matching legal observations distributed across 1.2 seconds are accepted exactly once.
- [ ] Premature confirmation: 0 deterministic unit-test sequences with an observation change inside the stability window are accepted.
- [ ] Response time: accepted stable candidates are committed between 1.0 and 1.5 seconds after their final state change.
- [ ] Compatibility: hand detector is no longer required for automatic confirmation; SPACE remains functional.

---

## Out of Scope

- Training a detector for the player's moving object.
- Modifying Xiangqi move rules.
- Changing robot post-move board synchronization.

---

## Assumptions

- The camera can produce a fresh board observation frequently enough to obtain multiple samples in 1.2 seconds.
- Existing CChess/YOLO recognition can generate a candidate move from a settled board.
- The player moves Red pieces and the AI moves Black pieces, as in the existing game loop.

---
