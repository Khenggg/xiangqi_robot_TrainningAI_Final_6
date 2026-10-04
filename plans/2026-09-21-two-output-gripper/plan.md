# Two-output tool-DO gripper update

Mode: hard (planning only; no production changes in this artifact)

Risk: high-risk — a wiring/IO-direction error can energize both motor directions or move the physical gripper unexpectedly.

## Goal and current state

Update the FR5 tool-output gripper control for the new wiring:

| Physical action | Tool output | Required electrical state |
| --- | --- | --- |
| Open motor | Tool DO1 | DO0=0, DO1=1 |
| Close motor | Tool DO0 | DO0=1, DO1=0 |
| Stop / safe idle | both | DO0=0, DO1=0 |

The current implementation has only one output, `self.gripper_do_id = 0`, and treats `GRIPPER_CLOSE=1` / `GRIPPER_OPEN=0` as its direction. `FR5Robot.gripper_ctrl()` in `src/hardware/robot_VIP.py` therefore cannot operate the new wiring. It is called by `pick_at()`, `place_at()`, and `place_in_capture_bin()`.

Existing fixed waits are `time.sleep(0.5)` after close/open in those three operations. The old standalone `tests/test_tool_do0.py` assumes DO0 ON=close and DO0 OFF=open, so it must not be used with the new arm.

## Safety contract

1. The software must never intentionally command DO0 and DO1 high at the same time.
2. Every direction change must first command both outputs low, wait a configurable deadtime, then energize exactly one output.
3. Any `SetToolDO` failure, exception, interrupt, startup initialization, and diagnostic-script exit must attempt to command both outputs low. The first error must still be surfaced to the caller/log.
4. The gripper helper must reject invalid action/configuration before energizing a direction (including identical DO IDs or negative durations).
5. Motion commands must not proceed after a gripper command fails. `pick_at`, `place_at`, and `place_in_capture_bin` must stop their sequence and raise/return failure rather than continue moving with unknown grip state.
6. Dry-run must simulate the same output sequence and timing without accessing hardware.
7. A failed attempt to set **either** output low is an activation failure: attempt both outputs low again, then raise `GripperCommandError`; never proceed to energize a direction from an unknown output state.
8. The application provides a software break-before-make sequence; the motor driver/wiring must also provide or be verified to provide an electrical interlock. Command ordering alone cannot prove the physical output state.

## Proposed configuration surface

Replace the ambiguous `GRIPPER_OPEN` / `GRIPPER_CLOSE` output-value constants in `config.py` with named direction/output and timing settings. Keep aliases temporarily only if other code still imports them; remove them after repository-wide references are migrated.

```python
# Tool-DO wiring (new arm)
GRIPPER_OPEN_DO_ID = 0
GRIPPER_CLOSE_DO_ID = 1
GRIPPER_IDLE_STATUS = 0
GRIPPER_ACTIVE_STATUS = 1

# Direction actuation policy
GRIPPER_ACTUATION_MODE = "pulse"  # fixed for this direct-drive, time-based motor
GRIPPER_DIRECTION_DEADTIME_SEC = 0.10
GRIPPER_OPEN_PULSE_SEC = 0.20
GRIPPER_CLOSE_PULSE_SEC = 0.20
GRIPPER_OPEN_SETTLE_SEC = 0.25
GRIPPER_CLOSE_SETTLE_SEC = 0.25
```

All values are initial conservative starting points, not validated hardware values. The motor moves only while its direction output is high, has no end-limit switches, and must be stopped by software timing. Start at 0.20 seconds and tune each direction independently to the minimum reliable travel plus a small margin. The existing 0.5-second waits become `OPEN_SETTLE_SEC` and `CLOSE_SETTLE_SEC` so the move sequence is tuneable without editing control logic.

### Actuation policy: pulse only

The new wiring directly drives motor direction: DO0 high moves open, DO1 high moves close, and neither direction is active when both are low. There are no end-limit switches. Therefore the first implementation supports **pulse mode only**: energize one direction for its configured pulse duration, then force both DOs low. A continuous/hold mode is deliberately excluded because it could overdrive the motor at a mechanical end stop.

## Implementation phases

### 1. Centralize safe two-output actuation

Files:

- `config.py`
- `src/hardware/robot_VIP.py` — `FR5Robot.__init__`, replace `gripper_ctrl()` around current lines 424–447

Implement a clear action API such as `gripper_ctrl(action: Literal["open", "close"])` (or an enum/string constants named `GRIPPER_ACTION_OPEN` and `GRIPPER_ACTION_CLOSE`) rather than passing raw 0/1 values. Store `self.gripper_open_do_id` and `self.gripper_close_do_id` from configuration.

Add focused private helpers:

- `_validate_gripper_config()` to ensure DO0/DO1 IDs differ, IDs are valid Tool DO IDs (SDK comment documents range 0–1), mode is `pulse`/`hold`, and all timing values are non-negative.
- `_set_tool_do(output_id, status)` as the only wrapper around `self.robot.SetToolDO(...)`; use `block=0` for ordered safety transitions because the bundled SDK documents `0` as blocking and `1` as non-blocking. Reconcile this with the controller manual during commissioning before enabling the robot.
- `_set_gripper_safe_idle()` to command both configured outputs low, trying both even if the first call fails.
- `_actuate_gripper_direction(action)` to: safe-idle (must succeed) → deadtime → set target direction high → pulse delay → safe-idle when mode is pulse. It must use `try/finally` so pulse mode de-energizes outputs if a delay/logging operation is interrupted.

Use an in-process lock (for example `threading.RLock`) around the entire transition so concurrent game/UI calls cannot interleave an open and close sequence. Log action, both output IDs, selected mode, pulse time, and returned SDK errors; never claim physical motion was successful merely because an output command was transmitted.

At `connect()`, validate configuration and establish gripper safe-idle before declaring actuation ready. Track gripper readiness separately from the SDK connection, and do not allow normal play to send gripper/motion commands when safe-idle initialization failed. Preserve the existing controller-enable order only after confirming it is required by `SetToolDO`.

### 2. Integrate timing into pick/place/capture flow

Files:

- `src/hardware/robot_VIP.py` — `pick_at()`, `place_at()`, `place_in_capture_bin()`

Replace raw constants with the new action API:

- `pick_at`: open and wait `GRIPPER_OPEN_SETTLE_SEC` before approaching/descent if the jaw must be confirmed open; close at `PICK_Z`, wait `GRIPPER_CLOSE_SETTLE_SEC`, then lift.
- `place_at`: open at `PLACE_Z`, wait `GRIPPER_OPEN_SETTLE_SEC`, then lift.
- `place_in_capture_bin`: open, wait `GRIPPER_OPEN_SETTLE_SEC`, then return home.

Remove all three hard-coded `time.sleep(0.5)` calls. Decide and document whether the pre-approach open-settle is required for the physical jaw; keeping it is safer for a first commissioning pass.

Ensure gripper failures prevent the next arm motion. For a failed close, do not lift/carry; leave the arm stationary and return an error for operator recovery. For a failed open at a destination/bin, do not automatically depart because the piece may still be held. Add best-effort all-low cleanup in `pick_at`, `place_at`, capture flow, shutdown/disconnect, and exception/interrupt paths; do not rely on `atexit` for physical safety.

Update stale comments/docstrings that currently say “Controller DO2” even though the code calls `SetToolDO`.

### 3. Automated test coverage (no robot required)

Files:

- Add `tests/test_gripper_control.py`
- Optionally extend an existing robot test fixture if one exists; otherwise use a fake SDK object assigned to `FR5Robot.robot`.

Fake `SetToolDO` must record `(id, status, smooth, block)` calls and permit deterministic failures. Patch `time.sleep` to avoid slow tests while asserting requested durations.

Required tests:

1. Open pulse call order: DO0=0, DO1=0, deadtime, DO0=1, open pulse, DO0=0, DO1=0.
2. Close pulse call order: DO0=0, DO1=0, deadtime, DO1=1, close pulse, DO0=0, DO1=0.
3. At no recorded point are both outputs high; switching close→open inserts an all-low deadtime.
4. Every completed command, interrupted pulse, and error cleanup ends with both outputs low.
5. A target-enable error and an idle/reset error are returned/raised and still cause the best-effort all-low cleanup.
6. Invalid same-ID wiring or negative times fail before any SDK call.
7. Dry run produces the same logical transition report without `SetToolDO`.
8. `pick_at`, `place_at`, and `place_in_capture_bin` use the new settle config instead of a literal 0.5 seconds, and no downstream move follows a failed gripper action.

Run the focused suite with the repository’s available runner (likely `python -m unittest tests.test_gripper_control`; confirm discovery layout during implementation), then run the full unit suite that does not command real hardware.

### 4. Replace the obsolete one-output hardware diagnostic

Files:

- Replace or clearly deprecate `tests/test_tool_do0.py`
- Add `tests/test_tool_gripper_two_output.py` as an explicit manual-only diagnostic (name and header must say it actuates the gripper but must not move or enable the arm)
- Update the README's stale Tool DO0 instructions and add a short commissioning note under `docs/`

The diagnostic must use the same configuration and a small gripper-only IO transport/helper shared with production code, but it must **not** call `FR5Robot.connect()`: that path enables the arm and requires R1–R4. It must establish only the minimum SDK session required to write Tool DO, without any `RobotEnable`, board teaching-point load, or motion call. It must:

1. Require an explicit typed acknowledgement such as `ARM CLEAR` after printing a warning that DO0=open and DO1=close.
2. Start by forcing both outputs low and print the result of each output command.
3. Perform **one** low-risk open pulse, stop/all-low, wait for operator observation, then one close pulse, stop/all-low. It must not default to five repeated cycles.
4. Provide a configurable/manual confirmation before each energized action; cancel/exception/`KeyboardInterrupt` always executes best-effort all-low cleanup.
5. Verify SDK connection/state and display current configured DO IDs, mode, pulse/deadtime/settle values before any signal.
6. Be run with the arm stationary, tool clear of hands/pieces/board, low robot speed, emergency stop accessible, and gripper supply/driver documentation verified.

Do **not** use `pick_at()` for the first wiring diagnostic: it adds arm motion and descent risk before direction behavior is proven.

### 5. Commissioning and acceptance gate

Before enabling `DRY_RUN = False` for a real pick:

1. Electrical owner confirms the two outputs are compatible with the motor driver, including common ground, voltage/current ratings, and that DO0/DO1 high simultaneously is prohibited.
2. With the gripper mechanically clear and robot stationary, run the manual diagnostic once with short pulses. Confirm DO0 physically opens and DO1 physically closes. If reversed, swap **configuration IDs**, not logic/wires without electrical approval.
3. Tune pulse duration and settle timing with no chess piece, then with a sacrificial/test piece. Confirm a pulse does not overdrive an end stop and that pulse mode holds a piece through a safe lift.
4. Test `pick_at` and `place_at` at reduced robot speed over an empty/low-risk target, with an operator ready to stop the robot. Verify every error/abort leaves both outputs low.
5. Record the validated configuration values and gripper model/driver behavior in the commissioning documentation.

## Files expected to change during implementation

| File | Change |
| --- | --- |
| `config.py` | Two output IDs, active/idle states, mode, deadtime, pulse, and settle configuration. |
| `src/hardware/robot_VIP.py` | Replace one-output `gripper_ctrl`; add interlocked helpers; update motion flows and comments. |
| `tests/test_gripper_control.py` | New mocked unit tests for ordering, interlock, failures, timing, and integration. |
| `tests/test_tool_do0.py` | Deprecate/remove its unsafe one-output assumption. |
| `tests/test_tool_gripper_two_output.py` | New guarded, manual-only real-hardware diagnostic. |
| `README.md` and `docs/...` | Replace stale Tool DO0 instructions with the new wiring/commissioning record. |

## Open questions to resolve before implementation

1. Confirm that DO0 high moves open and DO1 high moves close with both outputs low as the desired stopped state. The implementation will use a 0.20-second pulse for each direction initially.
2. Does the controller manual agree that `SetToolDO(..., block=0)` blocks until the output command is accepted, as the installed SDK wrapper documents? Commission using the documented ordered setting unless the controller manual contradicts it.
3. Should an IO command failure trigger only a software stop/alert, or is there an approved robot emergency-stop/fault API the project should invoke? Do not add an automatic physical stop without team approval and controlled testing.

## Session Notes
<!-- Updated by cook automatically — do not edit manually -->

**Last active:** 2026-09-21
**Phase in progress:** commissioning
**Status:** Software pulse/interlock implementation and mocked verification complete; physical test remains operator-controlled.

### Decisions made this session
- Direct-drive motor uses fixed pulse mode: DO0=open and DO1=close.
- Initial pulse duration is 0.20 seconds; both outputs are forced LOW after every action.

### Next immediate action
Run the guarded stationary manual diagnostic, then tune the two pulse durations before permitting a board move.
