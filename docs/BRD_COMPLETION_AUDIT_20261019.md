# BRD completion audit — 2026-10-19

Runtime follow-up: the latest user request authorized virtual/mock verification.
See USER_FLOW_QA_20261019.md for executed flows, fixes and remaining failures.
The no-test statements below describe the earlier static checkpoint. Overall
BRD completion and physical acceptance are still not established.

Baseline HEAD: `18e67fc9006a91a2a32c4c861974760089a687de` (dirty worktree).
Requirements: `D:/OJT/brd-review-20261014/BRD_CHANGE_BASELINE_v1.0.md`.
Implementation history: `docs/BRD_IMPLEMENTATION_PROGRESS.md`.

**Conclusion: NOT COMPLETE.** This is a source/coverage audit, not an executed
acceptance report. No tests, application imports, GUI, SQL experiments, network,
camera or FR3 operations were run. The earlier no-test instruction still applies;
the question about mock/simulation verification has not been answered.

## Current acceptance evidence

Every row below remains unverified against the current dirty tree. A source path
identifies the implementation to exercise; its presence does not establish success.

| Gate | Current implementation to exercise | Missing authoritative evidence |
|---|---|---|
| T-01 | `session_profile.py`, `session_startup.py`, human input | Complete PvP startup/input with camera/RPC constructors forbidden |
| T-02 | `input_handler.py`, `ai_execution.py`, manager, journal | Physical HvR lifecycle using fake controller/camera, then authorized lab |
| T-03 | `self_play_controller.py`, piece-operation barrier | Continuous RvR execution, one motion at a time, no next AI before commit |
| T-04 | `verify_physical_board`, immutable observations | Current production-config wrong-board/stale/quality rejection |
| T-05 | durable commit/outbox, projection worker, relay | Mirror loss after commit plus reconnect/reconstruction without replay |
| T-06 | RPC transport, stop coordinator, command receipts | Lost replies at dispatch/stop/disable, operator recovery, no blind retry |
| T-07 | capture checkpoint, visual coordinator, input recovery | Failure at each capture stage, restart and manual completion |
| T-08 | `session_control.py`, controlled stop, disposal | Pause/reset/quit during motion; failed joins and fresh idle requirements |
| T-09 | `board_xy_calibration.py`, physical provider, binding | Measured grid/frame inputs; old plan rejection after recalibration |
| T-10 | virtual backend/runtime; explicit detailed/fast playback presets | Isolation/playback/complete animation proof missing; syntax evidence only |
| T-11 | physical execution and raw relay fallback | Optional simulation/renderer failure without losing camera/FR3 game authority |
| T-12 | independent CChess/YOLO statuses and strict verifier | Current model-failure matrix; board evidence cannot authorize an unsafe grip |
| T-13 | physical choreography and post-motion verification | Observation only after clearance, including camera occlusion/recovery |
| T-14 | atomic terminal move snapshot/end intent | Winning commit with mirror failure and crash/restore around the durable write |
| T-15 | game profile and self-play start guard | F6 through UI and direct coordinator entry in PvP/HvR |
| T-16 | game/AI epochs, scene epoch, stream/command context | Late callbacks/packets/commands across reset, mode switch and world rebuild |
| T-17 | XY-only fit and independent surface Z | Executed 90-point/Z-invariance matrix |
| T-18 | XY dimensions/winding/residual validity | Swapped/reflected/noisy/incomplete input rejection without state mutation |
| T-19 | engine-specific fault paths | Illegal/None/exception before dispatch in both HvR and RvR |
| T-20 | independent camera/SDK/derived-view faults | Combined outages, durable retry and exactly one business commit |
| T-21 | session ownership, worker/disposal lifecycle | Multiple complete games with captures, wins/draws and no resource/session leak |
| T-22 | required virtual collision authority and trace | Rejected required plan, allowed contacts and replanning; no false safe result |

## Coverage inspected

- `tests/unit/test_brd_camera_contract.py`: wrong board/quality, independent model
  capabilities and observation reuse. Tests use fake camera/recognizer objects.
- `tests/unit/test_brd_actor_credentials.py`: mode/actor checks, continuous default,
  pre-dispatch engine faults and environment credential source.
- `tests/unit/test_brd_commit_projection.py`: in-memory move/terminal behavior with
  failing observers. Its `GameState` fixture does not attach a `SessionJournal`;
  it cannot establish durable recovery or atomic terminal/outbox behavior.
- Existing lifecycle, scene teaching, three-mode and spectator suites are candidates
  for regression. Test names were inventoried; no current passing result is claimed.

Source search found no references to the new `SessionJournal`, `SessionControl`,
`ControlledStopCoordinator`, `ProjectionWorker`, `SessionProfile` or
`calibrate_board_xy` symbols in the unit-test tree. This is a coverage warning,
not proof that every possible indirect execution path lacks coverage.

## Remaining work and boundaries

1. Detailed/fast virtual playback presets are implemented through the same full
   physics executor. Execute isolation, CLI/GUI, timing and complete-animation
   acceptance; no benchmark or proof of T-10/T-21 is claimed yet.
2. Transient-world/business-revision linkage and logical captured-tray reconstruction
   now have implementation drafts; audit/execute race and restore coverage. Retained
   simulated release poses are not persisted across world rebuild: fallback slots
   are explicitly nominal. Complete pose/evidence/error reconstruction remains open.
3. Add/refresh focused durable journal/stop/context/XY fault-injection coverage and
   run current integration/regression only after the pending no-test clarification.
4. Measure actual performance; no p50/p95, FPS, latency or leak values are invented.
5. Physical commissioning and measured geometry/frame/height/stop behavior require
   explicit authorization and external equipment. Credential rotation is an owner
   action; code/environment injection does not establish that it occurred.

AST/JavaScript syntax/diff checks already recorded in the progress log establish
syntax and whitespace only. They do not satisfy T-01–T-22. Goal is not complete.

## Static checkpoint and current blocker

`reports/brd-static-checkpoint-20261019/source_manifest.json` records hashes for
53 changed application files at the HEAD above. All 49 changed Python files were
AST-parsed without application imports; all three changed JavaScript modules were
checked with node --check; git diff --check succeeded. The HTML entry is hashed,
not rendered or claimed validated. No tests/application execution occurred.

The no-test constraint has persisted since the pending verification question and
through the terminal, world-context, captured-tray and playback slices. No answer
has authorized execution. Further code changes cannot be selected reliably from
syntax alone; the next necessary action is isolated integration/fault injection
followed by corrections based on actual failures. External acceptance requirements
above remain unchanged. This records a verification blocker, not completion or a
reduction of the original scope.
