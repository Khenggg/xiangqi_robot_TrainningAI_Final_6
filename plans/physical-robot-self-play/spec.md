# Spec: Physical robot self-play

**Date:** 2026-09-25
**Status:** Draft

---

## Problem Statement

Operators need a physical, repeatable way to validate the Xiangqi robot's gripper, arm motion, board calibration, and camera verification without personally playing a full match. The current application only supports a human Red side against an AI Black side.

---

## User Stories

- **[P1]** As an operator, I want to start a Robot vs Robot match and choose a difficulty independently for Red and Black so that I can exercise different available engine profiles on the physical board.
  Accepted when: the home screen opens a Robot vs Robot setup flow that accepts one of easy, medium, hard, or impossible for each color, and the selected profile is used when that color requests a move.

- **[P1]** As an operator, I want continuous and step-by-step self-play modes, plus an in-match cadence toggle, so that I can either run an unattended calibration match or inspect every physical move.
  Accepted when: continuous mode schedules the next verified engine move automatically, step-by-step mode schedules no move until the operator presses Next move, and the active match can switch cadence only while no turn is running.

- **[P1]** As an operator, I want an End match button available during self-play so that I can safely stop the run at any time.
  Accepted when: pressing End match prevents any further move from being scheduled, invalidates an outstanding engine result, ends the API match if present, and sends the arm to its normal safe/home position after any already-dispatched motion completes.

- **[P1]** As an operator, I want each Red and Black robot move camera-verified before the game state advances so that a calibration or gripper error cannot silently corrupt the match state.
  Accepted when: for both colors, a motion or visual-verification failure stops self-play, preserves the pre-move FEN, sets the existing physical-sync fault, and requires operator recovery.

- **[P2]** As an operator, I want the debug dashboard to identify the active side and selected profiles so that I can correlate physical telemetry with the self-play sequence.
  Accepted when: dashboard activity text includes the active Red/Black side and selected difficulty while a self-play match is running.

---

## Functional Requirements

1. FR-01: Add a Robot vs Robot home-screen action separate from VS ROBOT.
2. FR-02: Present a setup flow that selects Red difficulty, Black difficulty, then run style (Continuous or Step-by-step) before a match begins.
3. FR-03: Reuse the existing local Moonfish availability validation for both selected profiles; setup cannot start if either selected difficulty is unavailable.
4. FR-04: Add a color-neutral AI turn controller that requests a move for `state.turn`, physically executes it with `FR5Robot.move_piece`, visually verifies it, and atomically commits the board/FEN only on success.
5. FR-05: Preserve the existing human-vs-robot turn path unchanged.
6. FR-06: In Step-by-step mode, show a Next move control only when the robot is idle and a verified prior move has committed.
7. FR-07: In Continuous mode, schedule exactly one next turn after the prior move commits and the robot is idle; expose an active-match cadence toggle that only changes mode in the idle READY state.
8. FR-08: Show End match throughout self-play. It must cancel queued/not-yet-dispatched work, invalidate outstanding AI results using the existing epoch/token model, stop the remote match, and request the normal safe/home pose without force-stopping an in-flight robot command.
9. FR-09: On any engine, robot, or camera verification failure, transition to a stopped fault state; do not retry automatically and do not update FEN, turn, or move history for the failed move.
10. FR-10: Update debug-dashboard activity with mode, active color, and profile while self-play is operating.

---

## Non-Functional Requirements

- Safety: no self-play action may issue a second robot command while a prior command or AI worker for that turn is active.
- State integrity: each successful physical move creates exactly one FEN/move-history commit; each failed move creates zero commits.
- Responsiveness: continuous mode must wait for the previous robot command and visual verification to finish before scheduling the next engine request.
- Compatibility: the existing human-vs-robot flow and its 67-test suite must continue to pass.

---

## Success Criteria

- [ ] Setup correctness: both Red and Black accept only available easy/medium/hard/impossible profiles and preserve the selections through the match.
- [ ] Step control: 10 mocked alternating turns produce exactly 10 robot-motion calls only after 10 explicit Next move actions.
- [ ] Continuous control: 10 mocked alternating turns produce exactly 10 sequential robot-motion calls without user input and never overlap calls; an idle cadence toggle safely switches to Step before an eleventh move dispatches.
- [ ] Safe termination: ending a match before the next dispatch produces zero additional robot-motion calls and clears the active self-play state.
- [ ] Fault containment: a mocked visual-verification failure for either Red or Black yields zero FEN/history commits for that move and blocks further scheduling.
- [ ] Regression: all existing tests and new self-play tests pass.

---

## Out of Scope

- Interrupting a robot command already dispatched to the arm mid-motion.
- New chess engines, training, or difficulty algorithms beyond the existing four profiles.
- Automatic physical board reset/re-racking after a match ends.
- Cloud-engine self-play fallback for selected difficulty profiles.

---

## Assumptions

- The physical board is set to the standard initial position and passes the existing calibration/baseline process before match start.
- The robot's current pick/place and vision verification routines are color-agnostic and remain the sole motion/verification path for both sides.
- The operator retains responsibility for emergency-stop hardware and for resolving a physical-sync fault before another match.

---

## [NEEDS CLARIFICATION]

<!-- No blocking ambiguities for the planned MVP. -->
