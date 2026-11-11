# Full-open pickup and continuous closing signal — 2026-11-11

Baseline: `fix/fix-capsule` at `3d50e27`.

User requested removal of pre-pick safe-gap closure and continuous closing during transfer. The existing wiring remains DO0=open, DO1=close. No hardware command or physical test was performed. Motor/driver model, current limiting and continuous-duty rating are not established; user requested retaining the existing hardware arrangement. Software tests do not establish holding force, thermal suitability or freedom from dropped pieces.

## Resulting behavior

- Every pick, including both picks in a capture, opens fully and approaches/descends without the previous safe-gap pulse.
- CLOSE now keeps DO1 powered during closing dwell, settling, lifting and transport. `GRIPPER_CLOSE_PULSE_SEC` is the initial dwell, not an automatic OFF timer. Existing numerical timings are unchanged. The inherited driver applies the same behavior in physical PvP and private VS ROBOT.
- Opening/release first switches both outputs OFF, waits the direction deadtime, then pulses DO0. Post-release safe-gap closure remains unchanged.
- Hold, pulse and uncertain output state are tracked separately. Active/uncertain outputs retain their driver in a registry until both OFF replies succeed. No opposite-direction simultaneous ON is permitted.
- Owned physical stop/fault/cleanup/exit paths attempt bounded independent StopMotion before OFF, and still attempt OFF if StopMotion fails. A retained unknown/rejected stop blocks false recovery and prevents StopMotion replay. Explicit cleanup can retry idempotent OFF while preserving the unresolved arm-stop error.
- Shared/private cleanup and private hung-worker closure retain resources when stop/OFF is unresolved. Immediate exit now handles active registered outputs before process termination; it does not issue HOME/enable. Exit without active outputs needs no device call. New ON commands are rejected after the exit barrier begins.
- HOME/idle checks reject active hold or unresolved stop state. A known motion rejection with acknowledged stop/OFF preserves the existing guarded HOME recovery path.

Python cannot guarantee OFF after external process kill, power loss or disconnected controller transport. There is no jaw-position/force feedback. Physical acceptance remains required; this is a source-only change, not a new capsule release.

## Verification

Environment: Windows, `.venv312` Python 3.12.10, pytest 9.1.1; PATH prepended with `.venv312/Scripts`, DRY_RUN=1, ROBOT_BACKEND=VIRTUAL, PYTHONIOENCODING=utf-8. Device operations and independent transports are mocked; no live startup harness was used.

PASS, exit 0, **282 tests** (275 parallel, 7 serial), runner **19.55 seconds**:

```powershell
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_gripper_hold_close.py,tests/unit/test_gripper_hold_lifecycle.py,tests/unit/test_gripper_event_contract.py,tests/unit/test_legacy_physical_robot_gates.py,tests/unit/test_two_output_gripper.py,tests/unit/test_exit_confirmation.py,tests/unit/test_home_chess_recovery.py,tests/unit/test_vsc_home_recovery.py,tests/unit/test_stop_recovery_controls.py,tests/unit/test_pvp_failed_move_recovery.py,tests/unit/test_vsc_v3_lifecycle.py
```

The first aggregate run had 273 PASS / 2 FAIL: two unbound-method HOME tests used a SimpleNamespace without the newly required hold-cleanup method. Their fixture now delegates to the actual cleanup method with no active hold; transport-unknown metadata assertions are retained. A prior 38-case gripper run had one legacy test faking `Event.wait()` as True even though its event was not set; corrected to False to represent no cancellation. Stage tests now fail the actual CLOSE ON command rather than counting retired safe-gap pulses. Physical fixtures explicitly mock the independent bounded RPC transport.

Independent review initially found OFF-before-controller-stop ordering in exit/fault paths; corrected and re-reviewed APPROVED. Review also required OFF-only retry after a retained stop failure; focused tests verify this without StopMotion replay. AST, scoped diff and documentation checks PASS. Graph tools were unavailable to the root connection (`Transport closed`); the delegated driver inspection used graph/source discovery and impact detection where available. Exact source/callers and Git diff were inspected throughout.

Calibration, board geometry, controller configuration and numerical gripper timings are unchanged. The pre-existing user whitespace change in config.py is preserved separately. No live user-app restart, physical acceptance, full regression, capsule build or push was performed.
