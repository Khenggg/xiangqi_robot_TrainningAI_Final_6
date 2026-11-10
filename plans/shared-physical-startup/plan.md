# Plan: Shared Physical Startup with Mode-Specific Gameplay

**Date:** 2026-11-09
**Mode:** Hard (auto-detected: cross-cutting startup and hardware lifecycle)
**Risk: high-risk — changes the startup path that establishes physical robot authority and camera/board readiness.**
**Test:** default (focused tests followed by repository fast runner; physical acceptance remains separately authorized)
**Tasks:** default
**Spec:** `plans/shared-physical-startup/spec.md`
**Status:** PHASE 1 COMPLETE — awaiting approval at the `--hard` review gate.

## Scope Challenge

- **Exists?** Partially. Physical camera/robot startup is shared for non-HvR modes; HvR has an isolated `vsc-v3` stack. An `AutomaticPhysicalStartup` class exists in the shared path, but mode coverage/parity and invocation need explicit verification during implementation.
- **Minimum?** Extract/adapt only physical device startup and typed readiness; inject mode policy; preserve all gameplay controllers and FEN transaction semantics.
- **Complexity?** Hard / cross-cutting; risk high due to physical enable gates, calibration ownership, camera lifecycle, and distinct HvR state model.
- **In scope modes:** physical `HUMAN_VS_ROBOT` and `HUMAN_VS_HUMAN_ROBOT`. `ROBOT_VS_ROBOT` remains unchanged as an arm-testing mode. Ordinary mouse-only `HUMAN_VS_HUMAN`, simulation, and board-only remain device-free.

## Spec Quality Check

- **[NEEDS CLARIFICATION] remaining?** None.
- **Success criteria measurable?** Yes; software behavior and physical acceptance thresholds are stated.
- **User stories P1/P2/P3?** P1 and P2 are present.
- **Acceptance criteria testable?** Mostly; physical UX improvement requires target metrics.
- **Verdict:** PASS — user confirmed custom-FEN support, left Robot-vs-Robot unchanged, requires camera/calibration for robot PvP, and accepted proposed physical thresholds.

## Proposed Architecture

```text
Mode selection
  → existing SessionProfile / capabilities
  → one shared physical device startup owner (physical profiles only)
      connect/read-only handshake → canonical teaching/calibration
      → camera open/calibration → verify current opening OR scan/confirm custom FEN → fresh baseline
      → guarded auto-enable or supervised F9→F10 fallback
  → existing mode-specific session/gameplay/controller
```

Readiness must be represented as separate typed facts (robot connected, fresh idle telemetry, camera ready, calibration valid, expected board verified, occupancy baseline captured, motion authorized). A successful earlier stage must not imply a later stage. Keep exactly one owner for each SDK/camera resource and preserve rollback/retained-owner behavior.

### Ownership boundary (required before refactor)

Do not construct the shared `HardwareManager` inside `VscV3Session` as a second owner. Instead extract a narrow `PhysicalStartupOwner` that owns one FR5 driver and one raw camera capture for the selected session. Each gameplay stack receives those handles through an adapter; adapters may create their own recognizers/monitors over the same capture but may not open another camera or robot connection. The owner does not own FEN, move rules, journal, or gameplay.

#### Enable authority decision

Physical connection/readiness and servo enable are separate stages. The owner may connect and report readiness, but it must not issue `activate_physical_control`, HOME, gripper, or motion commands. HvR's current implicit enable in `vsc-v3 HardwareManager._init_robot` must be removed from that startup stage and routed through the same explicit, guarded enable policy used by the shared session (configured auto-enable after all gates, or F9→F10). The UI must clearly report read-only/ready/enabled states. No mode becomes motion-ready merely because connect succeeded.

#### Resource transfer and cleanup contract

The startup owner retains resources until all consumers have stopped. On successful startup it lends references, not duplicate ownership; the session coordinator remains the sole lifecycle authority. On failure/cancel, stop camera readers first, release the camera capture once, then close the robot SDK once. If a close step fails, retain the owner and remaining handles for explicit retry; do not discard references or report teardown success. Camera calibration/recognizer errors must not trigger a second device open.

#### Calibration and vision contract

Use one camera index and one capture object for the session. Keep mode-specific perception adapters. The common camera startup validates that a fresh BGR frame can be read; calibration is then supplied/validated per mode against that same camera. Saved calibration must be keyed/validated against camera identity and image dimensions before use. Never silently substitute a different camera after a calibration-bound index has been selected.

#### Required tests before production integration

1. Two mode adapters receive the exact same mocked robot and capture identities; connect/open/release/close call counts are each one.
2. Startup failure at every stage closes only acquired resources in reverse dependency order; cleanup failure retains owner state and reports the failed stage.
3. Connect success does not enable; no HOME/gripper/motion call occurs during startup. Auto-enable and F9→F10 invoke the same guarded activation gate only after required readiness.
4. Required camera/calibration failure blocks robot PvP admission. Virtual, board-only and mouse-only profiles acquire no physical resources.
5. Opening FEN verification, custom-position adoption, and occupancy baseline are distinct outcomes; only explicitly confirmed complete board + side-to-move can update FEN.
6. Session routing and gameplay/FEN commit behavior remain mode-specific; `ROBOT_VS_ROBOT` is unchanged.

## Phases

### Phase 1 — Startup parity contract and characterization — COMPLETE

**Stories:** P1 shared startup; P1 preserve gameplay.

- Trace launcher routing and lifecycle for each physical-capable mode and `vsc-v3`.
- Verify whether `AutomaticPhysicalStartup.tick()` is polled in each mode; record actual F9/F10 and admission behavior from code/tests.
- Define mode-policy matrix for HvR and robot PvP: camera requirement, opening/custom FEN handling, auto-enable eligibility, and gameplay admission. Leave Robot-vs-Robot untouched.
- Define one readiness/result contract and resource ownership/rollback invariants before moving implementation.
- Add characterization tests for current route and mode behavior before refactor.
- Record that HvR bypasses `build_session` and constructs `VscV3Session` in `main.py`; the shared `AutomaticPhysicalStartup.tick()` currently runs only in the shared-session main loop. `HUMAN_VS_HUMAN_ROBOT` camera is profile-required and common path fails startup if it cannot open/calibrate it.

**Exit criteria:** characterization covers physical profile capabilities, HvR/robot-PvP session routing, separate current FEN owners, baseline-not-FEN behavior, manual F9/F10 placement, and one robot/camera initializer call per manager. Focused suite: 54 passed.

**Resolved decisions:** camera/calibration is mandatory for physical `HUMAN_VS_HUMAN_ROBOT`; failure blocks startup/gameplay. Acceptance target confirmed: 30 attempts/mode (15 cold starts + 15 restarts), ≥27/30 ready, p95 ≤60 seconds, zero unsafe enables, and ≥10 custom-position scans/mode.

### Phase 2 — Shared physical startup service

**Stories:** P1 shared startup; P1 guarded motion authority.

- Extract/reuse robot connection, teaching/calibration loading, camera open/calibration, expected-board verification, baseline capture, and enable readiness behind a single startup owner.
- First make `PhysicalStartupOwner` hold one real device/resource set and support injected ownership; do not begin by nesting either existing manager inside the other.
- Make auto-enable a per-mode policy and retain F9→F10 fallback, expiry, readiness checks, stop/recovery gates, and cancellation behavior.
- Ensure no startup path adds HOME, gripper, or other physical motion commands.
- Add failure-injection tests for connect failure, camera unavailable, stale telemetry, calibration unavailable, board mismatch, enable failure/timeout, cancellation, and teardown.

**Exit criteria:** exactly one startup owner per physical session; no physical resources opened by virtual/mouse-only profiles; each failed stage gives a distinct reason and safe cleanup/retained recovery ownership.

### Phase 3 — Migrate robot-capable modes incrementally

**Stories:** P1 preserve gameplay; P2 clear camera/FEN reporting.

- First integrate shared startup into physical `HUMAN_VS_HUMAN_ROBOT` while keeping `RobotPvPController`, game state, journal, FEN commit, and admission rules unchanged.
- Do not modify `ROBOT_VS_ROBOT`; it remains dedicated to arm testing.
- Only after parity evidence, optionally adapt HvR to consume the same startup owner while retaining `VscV3Session` gameplay and its private game state/move pipeline.
- Emit distinct user-visible outcomes for opening-FEN verification, occupancy baseline, and operator-confirmed custom-FEN adoption.

**Exit criteria:** mode-specific controllers and FEN commit semantics are unchanged by tests; each mode traverses startup once; F6/PvP admission behavior remains mode-correct.

### Phase 4 — Verification and physical acceptance

- Run focused startup/profile/session/camera/FEN tests, then the repository-approved fast regression runner per `.agents/skills/fast-testing/SKILL.md`.
- Audit diffs for calibration, coordinate-frame, journal, and hardware-authority regressions.
- Perform operator-approved physical acceptance for each migrated mode: 30 attempts (15 cold starts, 15 restarts), ≥27/30 ready, p95 ≤60 seconds, zero unsafe enables, and ≥10 custom-position adoption attempts. Do not equate mock tests with physical acceptance.

**Exit criteria:** all software criteria in spec pass; physical criteria meet the user-defined target and are documented; modes without authorization remain unactuated.

## Validation Strategy

- Profile matrix tests cover supported modes/environments and explicitly assert that `ROBOT_VS_ROBOT` remains unchanged.
- Startup state-machine tests with mocked camera/SDK and explicit call-count assertions (single connection/capture owner, no duplicate enable attempt).
- Session routing tests assert that gameplay class/controller per mode is unchanged.
- FEN tests assert opening verification leaves `INITIAL_FEN` intact; custom adoption requires full board recognition and operator confirmation; baseline capture alone never mutates FEN.
- Failure/cleanup tests assert no false-ready state and no resource leak after each partial-startup failure.
- Physical acceptance only with explicit operator authorization; never run hardware tests as ordinary CI.

## Risks

- Duplicate SDK or camera ownership during migration can cause lockups, dangling reader threads, or competing control sessions.
- HvR donor startup has mode-local calibration/config and a separate state model; sharing its whole manager would violate the chosen gameplay boundary.
- Auto-enable applied to Robot-vs-Robot or Robot PvP may grant motion authority earlier than expected. Readiness must remain distinct from mode admission/start controls.
- Calibration/board-origin sources differ; no values or coordinate assumptions may be copied without provenance and frame/unit validation.
- Camera-derived custom FEN adoption is in scope only after complete board recognition and explicit operator confirmation, including side-to-move.

## Needs User Decision

No blocking product decisions remain.

## Handoff

Recommended implementation mode: `$bb-cook --hard --tdd plans/shared-physical-startup/plan.md`.
