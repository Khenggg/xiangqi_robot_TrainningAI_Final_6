# SDK connection / board calibration separation — 2026-10-13

## Live evidence (read-only)

Controller 192.168.58.2 answers GetControllerIP through the project BoundedRPCProxy on port 20003. Teaching points returned by the actual controller: R1/R2/R3 tool=0,user=1; R4 tool=0,user=0. No controller teaching points, offsets, enable, motion or gripper outputs were modified.

Session logs/20261013_104329_8fa68655/run.log records two startup attempts: 10:43:38 SDK_state unavailable; 10:44:13 SDK connected and R1–R4 loaded, then calibration raised inconsistent frame metadata. The adapter caught that exception as a connection failure, set connected=False and prevented raw arm telemetry initialization. Ping does not prove valid SDK state streaming. The first attempt's receiver failure cause is not proven; cleanup also reported an SDK receiver not stopped and camera contention.

## Correction

- src/hardware/robot_VIP.py: preserve a successful SDK connection on teaching-point failure; record teaching_points_error and clear partial/stale targets. Connection resets motion authorization. Calibration errors block explicit enable and every physical actuation entrypoint.
- src/hardware/hardware_manager.py: retain BorrowedPhysicalStateSource when calibration fails, skip unverified board provider and create PhysicalStateRelay. Board and pieces remain uncalibrated; their alignment is not claimed.
- SDK failure still rejects connect. No automatic enable, actuation retry or inferred conversion of R4 between user frames.

## Verification

Evidence reports/sdk-calibration-20261013/: baseline files/hashes, delta.patch, red.log (6 failed,1 passed), focused.log (64 passed), subsystem.log (105 passed); final-subsystem.log (105 parallel + 1 serial = 106 passed, exit 0). Nine new tests cover mixed/missing frames, missing points, SDK failure, dry-run geometry preservation, reconnection, manager relay, and real local WebSocket session transport with mocked controller measurements. WebSocket packet preserves measured joint values/source=PHYSICAL while board_sync_available=False; zero enable/Mode/IO commands.

Graph detect_changes reports 397 inherited paths and zero impacted symbols; it is incomplete for the dirty snapshot. Direct review traces connect → calibration → BorrowedPhysicalStateSource → PhysicalStateRelay → TelemetryPublisher.

## Remaining work / limits

The running process must restart to load this patch. Actual FR3 telemetry through the patched GUI has not yet been verified. R4 must be re-taught in the same verified work-object frame as the other points, or the coordinate transformation must be measured and verified before mixing them. Missing board contact calibration, visual-estimator dimensions error, previously observed flange Z mismatch and full physical pick/place remain separate unresolved gates. This is a scoped regression gate, not a whole-repository full suite or hardware-motion acceptance.
