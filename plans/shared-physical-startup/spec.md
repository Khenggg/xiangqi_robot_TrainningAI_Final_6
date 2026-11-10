# Spec: Shared Physical Startup with Mode-Specific Gameplay

**Date:** 2026-11-09
**Status:** Ready

## Problem Statement

Operators report that physical connection startup in Human vs Robot is smoother and less error-prone than in other robot-capable modes. The project currently routes Human vs Robot through isolated `vsc-v3` hardware/camera startup and the other modes through the shared `HardwareManager`; startup behavior should be consistent without replacing each mode's gameplay/session logic.

## User Stories

- **[P1]** As an operator, I want all physical robot-capable modes to use one owned startup path so that connection, camera readiness, calibration, and enable feedback behave consistently.
  Accepted when: each physical-capable mode reports the same typed startup stages and failure reasons, and only one robot SDK/camera owner is active per session.

- **[P1]** As a player, I want startup changes to preserve the selected mode's gameplay so that move input, AI/PvP, FEN commit, and recovery behavior do not silently change.
  Accepted when: `HUMAN_VS_ROBOT` and `HUMAN_VS_HUMAN_ROBOT` continue to use their existing mode-specific controllers and state transitions; `ROBOT_VS_ROBOT` remains unchanged.

- **[P1]** As an operator, I want robot motion authority enabled only after the existing readiness and safety gates pass so that shared startup never causes unexpected physical motion.
  Accepted when: auto-enable is policy-controlled and guarded; otherwise the UI offers the existing F9→F10 confirmation flow, with no HOME/gripper command added by startup.

- **[P1]** As an operator, I want to verify the standard opening or scan and adopt a custom board position so that physical games can begin from the position arranged on the board.
  Accepted when: standard-opening verification leaves the current FEN unchanged; custom adoption requires a complete recognized board and explicit operator confirmation, including side to move; baseline capture alone never changes FEN.

## Functional Requirements

1. FR-01: Add/use a single physical startup owner for physical-capable modes, with explicit stages for robot connection, teaching/calibration load, camera open/calibration, expected-board verification, baseline capture, and enable readiness.
2. FR-02: Keep physical startup disabled for virtual simulation and board-only profiles; keep `HUMAN_VS_HUMAN` mouse-only mode hardware-free.
3. FR-03: Camera and calibration are mandatory for physical `HUMAN_VS_HUMAN_ROBOT`; missing camera/calibration blocks startup and gameplay admission.
4. FR-04: Inject mode policy into startup, including auto-enable eligibility, gameplay admission, and custom-position scan availability.
5. FR-05: Preserve each mode's current session factory, game state, input/controller, AI, FEN commit, journal, and recovery semantics.
6. FR-06: Report typed readiness and actionable failure reasons; do not treat a camera frame, occupancy baseline, SDK connection, or robot enable response as proof of the other stages.
7. FR-07: Keep explicit F9→F10 as a supervised fallback with expiry and all current controller, fresh telemetry, board verification, stop/recovery, and pending-transaction gates.
8. FR-08: Assign exactly one lifecycle owner for camera and robot resources; startup failure/cancellation must close partial resources or retain ownership for explicit recovery.
9. FR-09: Support standard-position verification and operator-confirmed custom FEN adoption. Occupancy-only detection must never mutate game state.
10. FR-10: No startup stage may issue physical motion, HOME, or gripper commands unless a separate current-task authorization explicitly allows it.

## Non-Functional Requirements

- Performance: Startup stage timings are observable; no new arbitrary sleep is introduced beyond camera/telemetry freshness requirements.
- Security: Configuration and machine-specific calibration remain external runtime data; no credentials or workstation paths are added to source artifacts.
- Availability: Failure of an optional viewer/simulation projection must not be misreported as robot/camera readiness; mode-specific degraded operation must be explicit.
- Safety: Default behavior remains no physical actuation during startup; auto-enable is permitted only under the existing explicit configuration and readiness guards.

## Success Criteria

- [ ] Both in-scope physical-capable modes (`HUMAN_VS_ROBOT`, `HUMAN_VS_HUMAN_ROBOT`) traverse the same startup-stage owner exactly once; `ROBOT_VS_ROBOT` remains unchanged.
- [ ] `HUMAN_VS_HUMAN`, virtual simulation, and board-only modes open no physical robot or camera resource.
- [ ] Startup failure/cancellation tests prove all partially opened resources are closed or retained under one explicit recovery owner.
- [ ] Mode-controller regression tests prove no changes to gameplay selection, FEN commit, self-play start, PvP admission, or recovery policy.
- [ ] Camera unavailable, stale telemetry, board/FEN mismatch, calibration unavailable, controller error, stop/recovery pending, and enable timeout each produce distinct blocked outcomes; no unsafe enable occurs.
- [ ] Physical acceptance per migrated mode: 30 attempts (15 cold starts, 15 application restarts), at least 27/30 reach readiness, p95 startup time ≤60 seconds, and zero unsafe enables.
- [ ] Custom-position adoption is exercised in at least 10 runs per migrated mode; every accepted FEN and side-to-move matches operator-confirmed setup.

## Out of Scope

- Replacing non-HvR gameplay/session stacks with `vsc-v3`.
- Changing `ROBOT_VS_ROBOT`, which remains an arm-testing mode and is explicitly out of scope.
- Changing robot motion, pick/place strategy, gripper wiring, HOME behavior, or calibration values.
- Enabling camera or robot for mouse-only Human vs Human mode.

## Assumptions

- In-scope “other modes” means physical `HUMAN_VS_HUMAN_ROBOT`; ordinary mouse-only `HUMAN_VS_HUMAN` remains hardware-free. `ROBOT_VS_ROBOT` is intentionally unchanged.
- The preferred architecture is shared physical startup with independent gameplay/session layers.
- Camera recognition and FEN initialization/commit remain separate concepts; custom-position adoption is an explicit confirmed transition, not a baseline side effect.
- Physical testing is separately authorized and will not be performed by normal automated tests.

## [NEEDS CLARIFICATION]

