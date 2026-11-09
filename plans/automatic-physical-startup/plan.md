# Automatic physical startup

Mode: fast, scoped implementation with tests and review
Risk: high-risk — grants physical control automatically; existing calibration, telemetry, board and recovery checks remain authoritative.

Confirmed scope: automatic connect/enable, no automatic HOME or gripper commands, no board-threshold relaxation. Preserve telemetry/viewer construction and committed-board projection. Initial camera fallback from the preceding change remains included.

- [x] Add one-attempt startup enable through MotionWorker after initial baseline completes. Wait for board reconciliation if baseline failed. Never rearm after stop, recovery, manual F9, mode disposal or enable failure.
- [x] Integrate into the game loop without changing viewer/session startup.
- [x] Verify with mocked controller, camera startup and viewer tests; review and document limits. No physical device calls during verification.

## Verification

2026-11-09: focused test_fast run passed 80 tests (76 parallel + 4 serial): automatic startup, legacy physical adapter guards, live digital twin mirror, actual two-player GUI and camera recognition/lifecycle. Syntax parsing and git diff --check pass. Initial expanded run exposed three stale viewer/UI fixtures; original HEAD main/tests reproduced all three failures (missing OCCT assets in fixture and missing viewer_command_context in mocked manager). No claim of full-suite or physical hardware acceptance.

Review found queued-stop/manual-cancel races. Fixed with expected startup stop generation and a cancellation guard, both rechecked inside activate_physical_game immediately before activation. Delayed-operation and mid-verification tests exercise the real entry method without controller calls. Robot-vs-robot retains F6 start; no automatic HOME or gripper command. Capsule has not been rebuilt.
