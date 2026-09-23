# Phase 03 — Capability-gated observation adapters in SHADOW mode

**Stories:** All P1 interaction/held-piece/clear-board scenarios.  
**Runtime mode:** `PLAYER_TURN_MODE=SHADOW`; legacy remains the sole commit owner.

## Goal

Prove that real hand, tool, sleeve, obstruction, motion, CChess, and YOLO producers can satisfy the observation contract. If the required obstruction capability does not exist, fail closed rather than pretending hand absence means clear.

## Capability gate

Before integration, inventory the actual runtime producer(s) and record a capability report:

- `AVAILABLE`: real hand **and generic obstruction/tool** evidence is wired, health-checked, timestamped, and corroborated with motion/coverage.
- `DEGRADED`: only some evidence exists (for example motion/coverage but no generic stationary obstruction producer).
- `UNAVAILABLE`: no reliable required producer.

Only `AVAILABLE` permits future UNIFIED startup and AUTO/SPACE/MOUSE. `DEGRADED`/`UNAVAILABLE` must remain SHADOW/LEGACY; there is no supervised input bypass for completing a unified turn. The operator exits by restart/reinitialization to LEGACY. A stationary hand/tool test is mandatory; zero motion must still be `OCCLUDED` while pixels/cells are obstructed.

## Changes

1. Add `src/vision/board_observation_adapter.py`:
   - Acquire one frame/recognition result per sample and share it across shadow/SPACE/auto consumers.
   - Normalize CChess identity, YOLO occupancy, hand/generic-obstruction evidence, motion, coverage, per-cell confidence, and timestamps.
   - Prefer structurally valid CChess identity; YOLO narrows/corroborates but cannot invent identity or arbitrarily break ties.
   - Produce `CLEAR` only with AVAILABLE capability, no hand/tool/obstruction, no motion, and sufficient coverage/confidence.
2. Modify `src/vision/snapshot_detector.py`:
   - Expose non-mutating evidence methods.
   - Unified matcher bypasses current first/Manhattan fallback and reports ambiguity.
   - Held-piece disappearance is incomplete/transient evidence, never a move.
3. Modify `src/vision/turn_completion_monitor.py` to emit timestamped interaction facts only; it cannot request completion. If no runtime producer wires it, capability must not report AVAILABLE.
4. Modify `src/vision/board_stability_monitor.py` to legacy-only use; unified stability lives in the arbiter.
5. Modify `src/hardware/hardware_manager.py` to expose producer health/capability and one normalized sample call tied to current session/baseline generation.
6. In `main.py`, SHADOW feeds lifecycle/interaction/observations to the arbiter and logs proposals with zero commit authority.

## Deterministic tests

Add `tests/test_board_observation_adapter.py`:

- valid CChess + consistent YOLO fuses once without duplicate recognition;
- malformed/contradictory/low-confidence evidence becomes unavailable/ambiguous;
- hand false negative plus motion/poor coverage blocks clear;
- stationary hand, sleeve, and stationary tool remain `OCCLUDED` despite no motion;
- capability DEGRADED/UNAVAILABLE blocks AUTO/SPACE readiness;
- lifted Red piece and missing-piece-after-clear produce incomplete/correction, not a move;
- between-square oscillation is unsettled and resets signature;
- old/out-of-order session observations are rejected.

Update interaction/snapshot tests:

- brief flash does not arm short path; long-held piece has no completion timeout;
- interaction fact timestamps/order are deterministic;
- no arbitrary successor choice from equal/near-equal evidence.

## Exit criteria

- A documented real runtime producer earns AVAILABLE in a stationary obstruction test, or the product remains SHADOW/LEGACY.
- No adapter mutates logical/detector baseline or calls human commit.
- Shadow decisions cover every P1 sequence without affecting legacy behavior.
- Phase 04 cutover is prohibited while capability is not AVAILABLE.
