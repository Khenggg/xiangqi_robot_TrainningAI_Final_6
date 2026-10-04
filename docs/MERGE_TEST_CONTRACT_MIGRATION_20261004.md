# Test ownership after visual + unified integration

Simulation/domain/motion component tests remain. Non-simulation application tests follow visual branch, plus new typed/commissioning/camera/twin boundary regressions. No collision clearance, trajectory sampling, or robot geometry checks were disabled to obtain a pass.

- `test_physical_board_calibration.py::test_physical_startup_incomplete_known_offset_rejected`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_physical_board_calibration.py::test_physical_startup_explicit_known_offset_allowed`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_physical_board_calibration.py::test_physical_startup_explicit_pointer_contact_allowed`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_physical_board_calibration.py::test_physical_startup_missing_calibration_mode_fails_closed`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_physical_board_calibration.py::test_no_motion_command_occurs_before_calibration_success`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_physical_board_calibration.py::test_physical_calibration_failure_disables_motion`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_phase3b_wiring.py::test_capture_continuous_visual_pick_offsets`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_phase3b_wiring.py::test_ai_execution_dry_run_no_bypass_on_failure`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_phase3b_wiring.py::test_continuous_visual_pick_offsets_in_production_pipeline`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_phase3b_wiring.py::test_virtual_capture_succeeds_independent_of_physical_validation`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_phase3b_wiring.py::test_physical_capture_rejected_when_capture_bin_unvalidated`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_phase3b_wiring.py::test_physical_readiness_requires_enabled_backend`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_phase3b_wiring.py::test_legacy_double_connection_eliminated`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_phase3b_safety_guards.py::test_bare_virtual_backend_retains_unconfirmed_expected_payload_state`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_phase3b_safety_guards.py::test_virtual_payload_verifier_with_world_confirms_attachment`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_phase3b_safety_guards.py::test_operational_mode_lifecycle_physical_mode`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_phase3b_safety_guards.py::test_production_stale_board_pose_protection_physical_composition`: replaced non-simulation HardwareManager composition; see current boundary suites.
- `test_phase3b_safety_guards.py::test_production_stale_board_pose_protection_virtual_composition`: replaced non-simulation HardwareManager composition; see current boundary suites.

Pikafish/ELO tests removed with the explicitly replaced engine; Moonfish difficulty tests and rules/undo remain.

## Simulation fixture corrections during integration

- Historical yaw-90 suites use an explicit frozen scene; current master recovery uses the retained yaw-0 scene. Mutable operator defaults are not numerical golden fixtures.
- Missing stale 150 mm reachability seeds are replaced by on-demand IK. Queries preserve authoritative state whether the target is feasible or rejected.
- A nominal self-collision at old geometry is not asserted as a permanent invariant. A real fixed obstacle now verifies cell validation rejection and pose preservation. Anti-tunneling still requires safe endpoints and an unsafe intermediate configuration.
- Pick/place destination `(0,1)` was occupied by a knight. A positive transport test uses an empty cell; occupied-cell collision rejection remains covered independently.
- The jaw-contact negative test moves one actual collider away, rather than incorrectly declaring the current CAD stroke incapable of every grasp.
- PyBullet displacement injection names its physics client explicitly, preventing mutation of a different test world.
- LAND failure injection follows a successful approach; held-payload preconditions are explicitly installed for that isolated failure test.
- Board lowering uses -0.2 mm for a supported positive case. A -10 mm lowering crosses the floor and must not be treated as a valid supported pose.
- Unsafe unprepared relocation is rejected at NOT_READY; independent swept-volume checks still demonstrate the actual obstruction and state preservation.
- Reset rejection is propagated before any board reset, with the error retained. Empty test selection now exits 5 instead of claiming success.

## Camera and application contract corrections

- Phase-2 physical execution mocks now return `MotionExecutionResult` through `execute_piece_move`; camera verification is explicitly mocked before/after motion. Booleans no longer prove completed robot motion.
- Camera startup tests patch the imported calibration entry point and supply an actual BGR frame. Cancelled calibration raises RuntimeError and leaves `camera_calibration_ready=False`; an old saved matrix cannot authorize startup.
- CChess tiebreaker fixtures supply the full successor board, not an empty board with one surviving cannon. Multiple candidates, weak pixel differences, inconsistent moved identities, unrelated opponent changes and malformed/nonfinite confidence must not commit a move.
- Reachability evaluates the authoritative board transform and actual link-to-TCP offset, then computes residuals at the TCP using forward kinematics. It is a kinematics check, not collision or hardware acceptance.

- Donor FEN capture fixture now has a cannon screen, non-facing kings and reconciled stable IDs before the tested transition. Setup's FEN publication is separated from the one move publication.
- Donor physical sequence tests mock all actuators and explicitly install fake commissioning/bin preconditions. Capture failure is asserted via the current typed result rather than an obsolete escaping exception.
- Donor partial-constructor fixtures now initialize GameState fully and declare the dashboard's backend field.
- Duplicate hand-written CChess recovery/tiebreaker algorithms in integration tests were replaced with calls to SnapshotDetector itself.
- Concurrent A2.5 retains the immediate BUSY assertion and requires the worker to finish before IDLE assertion. A bounded 30-second join avoids a false failure from a 3-second scheduling assumption under the full 8-worker regression.
