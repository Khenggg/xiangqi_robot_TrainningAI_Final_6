# Phase 03 — Setup and runtime UI integration

**Stories:** P1 Robot-vs-Robot setup, Continuous/Step controls, End Match; P2 debug activity.  
**Goal:** expose the safe controller through a clear operator flow without changing the existing VS ROBOT flow.

## Files and changes

### `src/ui/board_renderer.py`

1. Add a separate `HOME_ROBOT_VS_ROBOT_RECT`, visually differentiated from VS ROBOT; expand `home_action_from_pixel` and home rendering with an explicit physical/self-play label.
2. Add renderer constants, draw methods, and hit-test helpers for the staged self-play setup: Red difficulty → Black difficulty → run style. Reuse the current four difficulty cards and availability visual language, but show the current side/stage and selection summary.
3. Add active-match controls: `NEXT MOVE` only when controller reports step/idle/ready; `CONTINUOUS` / `STEP MODE` cadence toggle only when the controller reports idle/ready; and `END MATCH` throughout active, ending, or faulted self-play. Render active side/profile/mode and clear messages that End stops future commands but does not interrupt a move already under way.
4. Keep normal game board controls visually/functionally unchanged outside self-play. Do not expose Surrender/New Game shortcuts that could race an active self-play controller; either suppress them in self-play or route them through the same safe end flow.

### `main.py`

1. Instantiate hardware only when a selected game mode begins, preserving startup launcher behavior. Import/construct `SelfPlayController` only after required hardware is available.
2. Add a dedicated setup state object/local fields for selected Red profile, Black profile, and run mode. Validate each card with `hw.difficulty_availability()`; do not call `hw.select_difficulty` for self-play because it mutates global configuration.
3. On final setup confirmation, call controller start. Let the controller execute its real-arm connection and full-board preflight gate, then baseline capture and remote-match initialization exactly once; surface rejection (including dry-run, disconnected robot, or failed board verification) without entering board-play state.
4. In the game loop, call `controller.tick()` once per frame while it is active/ending. Route Next, cadence-toggle, and End button/key events solely to controller methods. Never retain the old Black-only main-loop AI path for self-play.
5. Gate all `InputHandler` event/update calls while self-play owns the match. Explicitly block mouse/human-confirmation/rollback/reconciliation interactions from changing state while controller status is active, ending, or faulted; retain full behavior for normal VS ROBOT.
6. Route Pygame `QUIT`, Home, New Game, and End Match through the same controller ending request. While it reports not `can_finalize_exit`, retain the event loop, controller, dashboard, and hardware; render an ending state, suppress navigation/cleanup, and keep ticking. Once blocked/in-flight motion returns and safe-home finishes, finalize the requested quit/navigation/new-game action. Do not tear down hardware ahead of a known in-flight command.
7. Keep the legacy difficulty menu and Black AI scheduling conditioned on normal VS ROBOT mode, preventing changes to its launcher, availability validation, or `human_commit_generation` semantics.

### `src/ui/debug_dashboard.py` and `main.py`

1. Assign dashboard activity from controller state each tick, e.g. `SELF-PLAY | CONTINUOUS | RED | HARD | MOVING`; include selected Red/Black profiles in setup/idle text.
2. Preserve dashboard’s read-only process and robot telemetry behavior; never let dashboard actions command the robot.

### `tests/test_difficulty_menu.py`

- Assert distinct home action mapping for VS ROBOT and ROBOT VS ROBOT.
- Assert staged selection hit tests, initial cadence selection, Next visibility gate, ready-only cadence-toggle visibility/action, and End action mapping.
- Assert unavailable Red or Black selection cannot progress to run confirmation; controller-level tests own the dry-run/disconnected/full-board preflight gate rather than allowing UI state to bypass it.

### `tests/test_human_commit_ai_handoff.py`

- Retain/extend a regression that normal mode begins only the existing Black AI work after a human Red commit; self-play controller is not constructed or ticked for it.

### `tests/test_self_play_shutdown_routing.py` (new)

- With a controller fake reporting in-flight motion, QUIT/Home/New Game/End all request the same ending state, keep the loop/hardware alive, and do not navigate/cleanup.
- Releasing the fake motion makes the controller safe-home once; only then does each pending action finalize. Assert the blocked move has no commit/API board update/successor dispatch.

## Verification

Run the targeted UI/input tests and the complete suite. In DRY_RUN, manually confirm that normal VS ROBOT still works and self-play is explicitly refused. Exercise both self-play modes and safe READY-only cadence switching, including End from Ready, Thinking, and a simulated Motion state, only through controller fakes or a supervised real-hardware session. Inspect dashboard strings for both colors and profiles.

## Exit criteria

Operators can configure independent profiles and either cadence, advance step turns safely, end at every self-play state, and still launch/use the normal human-vs-robot match as before.
