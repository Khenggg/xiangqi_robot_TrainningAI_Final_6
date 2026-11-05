# BRD v1.0 implementation progress

Current requirement/coverage audit: `docs/BRD_COMPLETION_AUDIT_20261019.md`.
All T-01–T-22 remain unverified on the current dirty tree. Virtual fast/detailed
playback, world/business context linkage and logical captured-tray rebuild now
have implementation drafts. Integration, full reconstruction and external
acceptance remain open.

Baseline: need-review / 18e67fc9006a91a2a32c4c861974760089a687de.
Requirements: D:/OJT/brd-review-20261014/BRD_CHANGE_BASELINE_v1.0.md.
Audited plan: D:/OJT/brd-review-20261014/AUDIT_AND_CHANGE_PLAN.md.

User authorized code changes after the read-only audit. Work sequentially;
verification uses fake hardware/virtual execution. No physical actuation authorized.

## Full scope

- [x] PR1 software boundary: strict physical Camera verification (A-01); lab acceptance remains pending.
- [ ] PR2: controlled stop/shutdown/deferred reset/operator recovery (A-02, RESET-01, TX-01).
- [x] PR3 code: environment credential configuration and redacted tracked config archives (A-12); service-owner rotation remains external.
- [ ] PR4: committed truth, terminal processing, durable state, asynchronous projection/outbox (A-04, A-05, A-11).
- [ ] PR5: actor/mode authorization, continuous RvR, nonphysical engine faults (A-03, A-08, A-09, A-10).
- [ ] PR6: game-mode/environment capabilities and virtual isolation (SIM-01).
- [ ] PR7: Twin/sandbox/planner separation and resynchronization (SIM-02, TWIN-01).
- [ ] PR8: XY-only four-grid-corner calibration, 90 points, validity/version, docs (CAL-01–03).
- [ ] PR9: capture checkpoint/manual recovery and uncertain-motion approval (TX-01).
- [ ] PR10: independent model capabilities, inference reuse and UI responsiveness (A-06, A-07, PERF-01).
- [ ] PR11: T-01–T-22 software fault-injection/integration acceptance and measured performance.

Lab measurements/FR3 acceptance, secret rotation, and unresolved virtual HvR input
semantics are not claimed complete by mock tests.

## Historical session notes (2026-10-14; superseded by later slices)

Verified software slices: A-01; A-03 engine faults; A-04/A-05 committed truth and
terminal processing despite mirror failure; A-06 layout reuse; A-07 independent
model capabilities; A-08 mode guard; A-10 default Continuous; A-12 config credentials.
Projection is still synchronous and durable commit/recovery is not implemented yet:
PR4/PR10 must not be marked complete on the strength of these slices.

Evidence: reports/brd-implementation-20261014/
- camera-red.log: 7 regressions reproduced before patch.
- camera-green2.log: 20 related tests passed.
- actor-red.log: 8 regressions reproduced; actor-green2.log: 15 tests passed.
- commit-red.log: 5 regressions reproduced; commit-green.log: 20 tests passed.
- subsystem3.log: 96 passed, including existing three-mode PyBullet piece-state
  scenarios with mocked arm execution; not physical trajectory/grasp evidence.
- compileall src/main/config and git diff --check passed.

Windows monotonic timestamps can coincide for different fresh samples; the actual
CameraMonitor now adds monotonic observation IDs. Reused IDs/timestamps cannot
satisfy verification. Legacy mock adapters remain supported without redundant
inference in the actual CameraMonitor path.

Tests migrated to the new BRD contract: self-play fixtures explicitly declare RvR,
manual-step tests explicitly request Step, mirror-only failures are projection
errors rather than physical faults. GUI Continuous surrender test holds a Ready
boundary in the event driver; it does not prove complete continuous-play timing.
Tracked archived config artifacts were credential-redacted; their historical
config fingerprints must not be claimed current. No Git history rewrite occurred.

Phase at the time of these historical notes: PR2, then PR4 and PR5–PR11.
Current draft implementation and outstanding verification are recorded below.

## Controlled-stop implementation slice (2026-10-14; execution unverified)

- Added ControlledStopCoordinator and SessionControl. Stop requests latch new
  commands, use a separate single-attempt XML-RPC channel, wait for workers and
  two fresh idle observations, and retain RECOVERY_REQUIRED on uncertainty.
- F8/Quit/New Game are accepted before busy-input filtering. Physical reset
  retains pending/capture checkpoints until operator reconciliation; virtual
  reset may discard a settled virtual transaction. Old self-play callbacks are
  retired before replacing the session.
- RvR End no longer publishes an outcome before its motion/commit barrier.
  Motion/think threads are non-daemon. Stop never opens a held payload; interrupted
  gripper pulses become uncertain and their owned outputs must be idle before cleanup.
- Ctrl+F8 is explicit operator approval after inspecting/stopping arm and gripper
  on the pendant. It only reads idle evidence; it does not resend movement/stop.
  V remains the separate full-board reconciliation step; F9/F10 is a new enable.
- Physical enable now uses physical idle telemetry and Camera truth; a missing
  viewer/board projection is not an enable gate. Enable checks stop generation.
- Preserved the requested 6 mm outside-grid limit in robot_VIP.py.

Verification this slice: compileall of the ten affected Python files and
git diff --check succeeded. NO pytest/GUI/FR3 execution was run at the user's
request. Earlier 96-pass results predate this slice and do not validate it.
Graph snippets had shifted source locations; current files/diff were authoritative.

PR2 remains incomplete: execute controlled-stop/reset fault-injection coverage
and prove the exception/persistence integration below before claiming crash-safe
shutdown. This slice is not a physical commissioning result. Full PR4–PR11 scope
remains outstanding.

## Durable-session implementation slice (2026-10-14; execution unverified)

- Added session_journal.py: SQLite WAL/FULL, kernel file lease per environment,
  typed JSON snapshots, unique command-stage receipts and committed move IDs,
  atomic committed snapshot plus durable twin/spectator outbox rows.
- Actual session startup attaches data/runtime/<environment>.sqlite3 before
  opening hardware. Restore verifies FEN/board/identity/revision consistency,
  retains pending and capture-removed checkpoints, invalidates old observations,
  and requires explicit operator recovery. No movement is replayed on restore.
- Current gameplay command/stage is recorded before execute_piece_move. Physical
  pending commits require fresh strict Camera verification persisted first.
  Known capture-removed continuation has a distinct receipt; uncertain dispatch
  cannot reuse the same command-stage key.
- Business commits now save before observers. On a failed durable write, the
  local transition is restored and the session is paused. Emergency Black,
  full-board rescan, turn confirmation, rollback/undo and Reset gained persistence
  hooks. Viewer failure after a committed Emergency/rescan cannot reject truth.
- Exception/KeyboardInterrupt shutdown now enters a minimal recovery UI and
  waits for the same controlled stop. Journal close follows stopped workers and
  hardware cleanup. Added readable persistence/stop/engine error guidance.

Verification: scoped compileall (13 affected files including new modules) and
git diff --check succeeded. NO tests, GUI sessions, SQLite runtime experiments or
physical hardware were run. Existing test results are not evidence for this slice.

At this slice's checkpoint, asynchronous outbox delivery was not implemented.
The following slice adds that draft; neither slice has runtime evidence. Remaining:
exhaustive recovery path consistency (including existing legacy pending-move APIs), actor /
environment capability routing, XY calibration and the remaining full BRD gates.
Outbox rows record intent; they are not proof of successful delivery.
The recovery UI and journal atomicity/lease behavior still require fault injection.

## Asynchronous projection implementation slice (2026-10-14; execution unverified)

- Added ProjectionWorker for committed full identity maps and spectator FENs.
  Latest complete states coalesce by channel; failures retain durable rows and
  use bounded retry backoff. Pending motion prevents whole-board reconciliation.
  This worker never sends FR3/gripper commands or changes physical fault flags.
- Spectator callback success requires a response ACK, not queue acceptance.
  Cached positive FEN ACKs avoid redundant posts within the same room. Optional
  disabled channels are explicitly logged as disabled, not delivered.
- Same-revision terminal payloads cannot be deleted by an older board ACK:
  acknowledgement compares the exact payload as well as session/revision/channel.
  Terminal jobs send the final FEN before End on the same API queue. Reset/close
  enqueue retiring-room final projection before a subsequent room creation.
- Durable match-end intent blocks further actor dispatch until New Game. End
  metadata write failure keeps RvR recovery ownership; optional network failure
  does not undo local termination. Scene/journal close waits for projection callbacks.
- Startup uses the asynchronous observer. Normal human/robot/emergency commits
  enqueue projections after their durable write. Missing viewer no longer decides
  whether full-board Camera reconciliation is accepted.
- Undo history serialization now shares move/log prefixes instead of duplicating
  them in every historical snapshot; the complete undo history is retained.

Verification: compileall of eleven directly affected files and git diff --check.
NO tests, HTTP delivery, GUI, SQLite experiments or physical robot execution.

PR4 remains open: prove race/fault-injection behavior, handle upstream spectator
protocol limitations and durable routing of terminal intents for retired rooms.
Current retired-room delivery is queued best-effort; an unacknowledged archived
intent is retained but not automatically routed to a retired server room after restart.
Cache ACKs are only evidence of prior acknowledgements, not a fresh server read.
The remaining PR5–PR11 scope, mode/environment routing and XY calibration are active.

## Mode/environment capability slice (2026-10-14; execution unverified)

- Added immutable SessionProfile separating requested launch environment, effective
  execution environment and game capabilities. PvP uses mouse input for both colors,
  creates no FR3 controller/camera/AI engine even when --physical was requested,
  and rejects game robot movement/enable/hover/test commands.
- Virtual robot modes initialize only their virtual executor/engine. Camera/model
  initialization is skipped. --virtual retains the user-selected meaning: simulation
  is disabled. Virtual HvR mouse input is labeled a test adapter in caption/status.
- Physical robot modes keep Camera/one FR3. Robot IP and dry-run policy are passed
  explicitly into the controller constructor; unsupported/stale mode profiles fail
  before opening resources. Mouse correction requires explicit Emergency mode;
  a paused camera/baseline no longer silently grants physical mouse input.
- Failed optional PvP scene falls back to explicitly game-only PvP. Failed physical
  mirror falls back to RawArmRelay, a measured read-only stream without PyBullet.
  WebSocket bind failure does not reuse another application's server or tear down
  the physical game; the viewer is labeled unavailable/unsynchronized.
- Restored snapshots from another game mode require New Game after pending recovery.
  The old board cannot authorize new-mode actors. Recovery/test-state fields are
  persisted, with conservative compatibility for older v1 test snapshots.
- Restored uncertain physical commands/tests require fresh idle evidence even when
  the newly connected application has no current actuation authorization. It does
  not send StopMotion to an externally controlled/read-only robot.

Verification: scoped compileall (15 touched files) and git diff --check succeeded.
NO tests, GUI launches, sockets, camera opens, SDK probes or physical motion were run.
This does not prove the six mode/environment combinations work at runtime.

PR6 remains open: validate the controlled in-app mode-switch draft below and all
six combinations and repair any legacy entry-point/recovery inconsistencies. Also
outstanding: retired spectator routing, complete transaction metadata, Twin scene /
calibration versions, XY fit/UI integration and full fault-injection/acceptance gates.

## Controlled mode-switch and retirement slice (2026-10-14; execution unverified)

- F2/Choose Mode now requests controlled stop ahead of the input busy filter,
  waits for old actors and physical recovery, and uses an ordered SessionDisposal.
  A replacement GameState/session starts only after resource retirement succeeds.
- Retirement caches each successful close and its frozen stop proof. A failed
  camera/web close after SDK closure can retry without another telemetry proof,
  StopMotion replay or controller-disable replay. Closing hardware rejects dispatch
  and readiness/enable. All old actors and automatic camera checks are held.
- Quit retains a recovery UI if retirement fails; F2 retries unfinished closes.
  An independent operator worker remains usable after startup/motion workers close.
  Ctrl+F8 is read-only stop confirmation; Ctrl+F9 requires explicit pendant disable
  confirmation after a lost disable reply. Unknown disable blocks re-enabling.
- Startup rollback failures raise a resource-carrying error instead of dropping
  controller/camera/journal references. The UI retains those owners and blocks
  another launch until retirement succeeds. Initialization stores its manager
  before opening resources and binds restored state before partial cleanup.
- Shutdown preserves pending/capture/test recovery checkpoints without publishing
  a finished match. A physical test must be reconciled before switching modes;
  settled virtual test sessions may retire without claiming physical evidence.

Verification: AST parsed five affected Python files without imports; git diff
--check succeeded. NO tests, runtime GUI, sockets, Camera, SQLite experiment or
physical motion. This is code progress, not execution or commissioning evidence.
PR2/PR6 remain open for fault injection, six-combination execution and resource
leak/race verification. Archived spectator routing, complete TX/calibration/scene
versions, XY calibration and the full PR7–PR11 acceptance scope remain outstanding.

## Spectator routing/receipt slice (2026-10-14; execution unverified)

- Added additive SQLite spectator_rooms and spectator_end_receipts tables. The
  room-creation response records session/server/room ownership before publishing.
  A positive FEN ACK and End ACK are recorded separately before removing outbox
  intent. A saved ACK is historical delivery evidence, not a fresh server read.
- Active and archived delivery use immutable room routes. A server mismatch or
  missing archived binding retains the row; it cannot send an old FEN/End to the
  current room. Session ownership is captured with each queued room creation.
- Spectator delivery now selects the oldest remaining revision for each match,
  preserving the endpoint's normal legal-move order. Twin still uses the newest
  full map. A retiring match's final End cannot be attached to an older FEN.
  New-room creation no longer implicitly closes journal-owned old matches early.
- FEN/End receipts are refreshed when a queued room job executes, preventing a
  duplicate callback or stale queued copy from ignoring an already saved ACK.
  Failed receipt writes retain their callback/response ownership for local retry;
  retrying a local save does not resend the acknowledged network operation.
- API workers are joined before journal closure, both on retirement and startup
  rollback. A successful startup rollback creates fresh local owners for retry.
  PvP/virtual/physical starts and Reset bind the spectator to the actual session
  and use the profile's player names; optional service failure does not reject a
  committed Game move or authorize robot replay.

Verification: AST parsing of affected files plus git diff --check only. NO tests,
SQLite experiments, HTTP delivery, GUI, Camera or physical motion were executed.
PR4 remains open: unrecorded/lost service replies, idempotent readback/creation,
custom-FEN/rescan/rollback semantics and fault injection need actual evidence.
Legacy archived rows without bindings cannot be assigned a guessed room. Different
environment journals retain their own archived rows until opened. Full TX/scene/
calibration versions, XY fit/UI and PR7–PR11 acceptance scope remain outstanding.

## XY calibration/profile/UI slice (2026-10-14; execution unverified)

- Added calibrate_board_xy: four explicit outer grid intersections, proper rigid
  SE(2) SVD fit without scale/warp, independent surface Z, dimension/residual and
  degeneracy checks. Controller-input API requires consistent tool/user metadata;
  non-base inputs require an explicit proven rigid user-to-base XY conversion.
- Simulator Apply R1–R4 now uses the XY path, retains relocation safety gates and
  rejects missing/stale placement versions. Successful apply increments version
  and publishes the same transform to world, provider, backend and viewer.
- Viewer exposes separate surface-Z input; point Z fields are display-only. The
  live board packet includes calibration-space/height metadata. Shared board-cell
  mapping now derives row/column spacing and thickness from authoritative geometry.
- Profile v2 records XY model, independent height and scene/geometry hashes.
  Legacy v1 profiles require re-entry instead of silent reinterpretation. The
  current guide makes R4 mandatory and labels old hybrid/fallback text historical.

Verification: AST parse of four Python files, node --check main.mjs and git diff
--check. NO tests, GUI, SQLite, Camera/SDK reads, physical motion or artifact
recalibration were executed. This does not prove 90-cell or yaw/Z behavior.
PR8 remains open: controller XY registration with measured geometry and surface Z,
full transaction/scene/calibration-version fences and all runtime/metrology gates.
The physical visual command mapping and existing SE(3) API remain separate paths.
Full PR7–PR11 acceptance, performance and remaining recovery scope stay active.

## Physical XY / execution binding slice (2026-10-14; execution unverified)

- Registered physical mirror XY calibration from four controller points with
  measured dimensions, independent surface Z and provenance. Nonzero user frame
  requires proven SE(2) conversion. A second controller read must match the loaded
  command mapping; the optional mirror never rewrites command tool/user IDs.
  SE3_LEGACY remains an explicit adapter choice, requiring base-frame observations.
- Removed unsafe user-0/user-1 equivalence fallbacks from R1–R4, HOMECHESS and
  R_Trash. Frame parser rejects fractional, boolean, negative/nonfinite IDs.
  Reload revokes command authority, clears stale cached points, increments its
  successful version and requires operator enable again. Cached frames are checked.
- Added execution binding snapshots: semantic move/session/board revision and
  immutable fingerprints for physical mapping, pose/Z/rotations, speed, gripper,
  visual config and perspective artifact; virtual placement/version/scene owner
  are recorded separately. Pending/last bindings are durable additive v1 fields.
- Normal motion asserts the binding before its dispatch receipt and before/after
  physical stages. Virtual validates inside its operation lock. Pick/hover tests
  check authority around target acquisition; pick tests retain a stage guard.
  Capture/vision retries include the binding in their immutable request signature.
- Old snapshots without a binding cannot dispatch blindly. Restore validates
  move/revision/session linkage. Logical camera/operator resolution remains
  separate from authorizing further motion. Clearing an old-board pending move
  now also clears its semantic context/binding. Stage logs carry move/session/
  revision/calibration correlation metadata.

Verification: AST parse of eleven Python files and git diff --check only.
NO tests, GUI, SQL experiment, SDK/camera reads, recalibration or physical motion.
This is implementation progress, not physical or transaction acceptance.
Still open: measured inputs/commissioning, manual-test receipt/reconciliation
fault-injection acceptance, full scene reset/reconnect/version coverage, controller
changes beyond cached points, operator recovery/fault-injection paths and all
remaining PR7–PR11 gates.

## Manual test recovery slice (2026-10-14; unverified)

- Test pick/place writes its own command receipt and expected board before calling
  the executor. Pending receipts block retry/toggle and survive session restore.
- Physical recovery key V is observation-only: it requires fresh idle telemetry,
  stop proof, and a full-board camera match to the pre-move, post-move, or initial
  layout before resolving the transaction. It never replays motion.
- Virtual scene epoch is included in command bindings and advances on robot,
  piece, and full-scene reset so stale staged work is rejected.
- Snapshot validation checks test move identity, source/destination, board shape,
  expected board and piece identities before restoring a pending test.

Verification: source inspection, Python AST parsing and git diff --check only.
No tests, GUI, SQLite experiment, SDK/camera reads or physical motion. PR2/PR9
recovery and fault-injection acceptance remain open.

PR2 historical scout evidence before the implemented drafts above:
- MotionWorker.close waits/join but issues no controller stop.
- Self-play motion thread is still daemon and end_match publishes remote before
  live motion ends; these paths have not yet been repaired.
- Main drops KEYDOWN/MOUSEBUTTONDOWN during worker busy: urgent Pause/Reset/End
  must be handled before that filter, without dispatching through the busy worker.
- SDK StopMotion (robot_sdk_core.py:1919) has a vendor socket-error loop. Use a
  bounded single-attempt stop path and preserve uncertainty; never blind retry.
- SDK GetRobotMotionDone reads robot_state_pkg.motion_done (0 moving, 1 done).
  PhysicalFR3Backend uses fresh packet timestamps/status validation and exposes
  IDLE/MOVING; manager.physical_telemetry_ready(require_idle=True) checks .5s age.
- A stop needs a separate control RPC channel because an in-flight MoveCart can
  hold BoundedRPCProxy's lock. Do not construct another SDK receiver/enable robot.
- Add cooperative stop latch checked before every subsequent actuation stage;
  Reset must keep pending/checkpoints until stop is acknowledged and fresh idle
  evidence exists, and keep RECOVERY_REQUIRED on unknown outcome. Operator must
  approve uncertain recovery; no motion replay on Reset/Resume/close.
- Quit must keep resources/session alive if stop/join safety cannot be verified;
  epoch invalidation alone does not cancel controller motion.

Two accidentally named pytest temporary directories remain ignored: cleanup via
Remove-Item was rejected by tool policy. No alternate deletion was attempted.
Goal remains active until the full authorized code scope is verified.

## Stop/reset/recovery hardening (2026-10-19; static verification only)

- Camera recovery may ignore its own observation-only UI worker when checking
  stop readiness. The coordinator still checks the piece-operation lock, other
  workers, gripper uncertainty and fresh physical idle telemetry. Previously the
  recovery job could wait for itself and reject every recovery attempt.
- Virtual reset discards pending game/manual-test work in one durable transition;
  a failed write restores the saved pending transaction. This path rejects
  physical profiles/journals and remains behind the verified-stop barrier.
- Resume and self-play recovery retain pending manual-test/capture checkpoints.
  Manual-test receipts now also require measured idle evidence for stop/cleanup.
- Releasing a stop latch and executing reset recheck current stop evidence,
  rather than accepting an old successful stop result alone.
- Full-board reconciliation clears the pending execution binding with its move.
  Leaving the binding after clearing the move made the next saved-session restore
  fail its own linkage validation.
- Both history-undo paths reject unresolved moves/tests/recovery, active motion,
  and ended-room intent; undo must not erase a command receipt or reopen an ended
  spectator match.
- Reset queues the previous match's terminal projection and writes the new session
  in the same SQLite transaction. Storage failure cannot leave a network-visible
  terminal intent from a reset that never created its replacement session.
- Physical reset saves its camera-verification pause before writing the new
  session. Baseline exceptions after that write retain the new session and pause
  play. A failed reset can be retried by an explicit New Game request; polling
  never repeats the reset automatically.

Evidence: AST parsing of game_state.py, game_persistence.py, session_control.py,
session_journal.py, self_play_controller.py, controlled_stop.py and
hardware_manager.py; git diff --check. No application imports/execution, tests,
GUI, SQLite experiments, SDK/camera reads or physical actuation were performed.
The graph impact query included 752 dirty/untracked/archived entries and had no
indexed impact symbols for the new draft files; it does not establish isolation.

PR2/PR4/PR9 software integration and fault-injection acceptance remain open,
along with the other unchecked scope above. Historical passing tests predate
these edits and are not evidence for this slice. Goal is not complete.

## Startup lease / camera cancellation hardening (2026-10-19; static only)

- Journal lease acquisition and saved-state validation precede hardware
  construction/initialization. A second launch or corrupt journal cannot first
  claim the camera/SDK and only later discover that startup is forbidden.
- --log-dir controls diagnostics only; runtime truth remains under the repository
  data/runtime directory. Detection of a legacy journal at the former log-derived
  path blocks startup and names both paths. No migration or deletion was attempted.
- Incomplete read-only initialization retires only its newly opened resources;
  saved pending transactions remain durable for the next successful launch.
- Cancel checks precede startup/resource creation, each initialization component,
  camera open, calibration sampling, preview/manual approval and calibration save.
- Manual calibration handles Q/window-close even when its frame queue is empty.
  Window errors still stop/join its reader via finally. That reader is non-daemon,
  has an explicit owner, and prevents camera release/session disposal while alive.
  Auto-calibration preview also destroys its window through a finally block.

Evidence: source/call-path inspection, AST parsing of session_startup.py,
hardware_manager.py, auto_calibrate.py and calibrate_camera.py, git diff --check.
Graph discovery used the existing index; new draft functions are not indexed and
the dirty-tree impact query provides no precise impact symbols. No tests, GUI,
SQLite experiments, camera/SDK reads or physical actuation were performed.
Native camera reads and inference already in progress are cooperative boundaries,
not forcibly cancellable operations. Duplicate launch, cancellation, reader/close
failure and legacy-journal migration still require acceptance evidence. Goal active.

## Projection / virtual admission race hardening (2026-10-19; static only)

- Twin outbox checks session/revision and pending work again under the Game
  transition lock before applying its snapshot, so a queued old snapshot cannot
  pass validation and then run across a concurrent reset/commit.
- Manager reconciliation acquires the piece-operation lock atomically, replacing
  check-then-act. Production bridges acquire poll/physics locks nonblocking on
  this path; busy scene work defers projection instead of holding up a commit.
- The virtual executor shares the projected world. Its admission now waits for
  the current committed session/revision/scene epoch, avoiding an AI move against
  the board from before an asynchronous human commit. Continuous RvR waits in
  READY while that projection is pending; it does not classify the wait as a fault.
  Physical execution remains independent of the optional mirror.

Evidence: exact source/call-path inspection, AST parsing of projection_worker.py,
self_play_controller.py, hardware_manager.py, live_twin_bridge.py and
physical_state_relay.py; git diff --check. No tests, imports/application execution,
GUI, SQLite experiment, SDK/camera reads or physical actuation. Latency/lock races,
wire packet session ordering, reconnect reconstruction and PR7/PR11 acceptance
remain open. Goal active.

## Viewer stream ordering slice (2026-10-19; static only)

- Robot/world/custom packets receive a publisher stream ID and increasing
  sequence under the state lock. Viewer pins that stream per socket and drops
  duplicate/out-of-order packets per type, preserving older cached snapshots of
  other types sent during initial connection. Versioned streams reject subsequent
  unversioned packets. Sequence does not replace measurement freshness checks.
- New clients subscribe before initial snapshot sends, retaining updates produced
  during those awaits. Coalescing cannot overwrite a pending newer snapshot with
  an older packet delayed by another producer thread.
- Viewer echoes its stream ID on commands. Server rechecks stream/socket liveness
  after the shared command wait, before dispatching queued commands.

Evidence: AST parse of telemetry_publisher.py, node --check of live_state.mjs and
main.mjs, git diff --check; graph impact query remains imprecise for this dirty
tree. No tests, imports/application execution, browser/server/socket sessions,
camera/SDK reads or physical actuation. Publisher identity is not GameSession or
scene identity: full committed FEN/session metadata, same-stream reset/command
versioning, reconnect reconstruction and PR7/PR11 acceptance remain open.

## Viewer command context / ownership slice (2026-10-19; static only)

- Managed telemetry reads committed session/revision/game epoch/FEN and current
  scene epoch without waiting behind a Game transition. Viewer echoes the context;
  physical sessions advertise read-only capability. Busy contexts cannot authorize
  commands. Versioned identity remains separate from measured robot freshness.
- Runtime revalidates managed context after its command lock is acquired. Manager
  retains the piece-operation lock for the complete viewer command, so game
  execution, deferred reset and disposal observe the work at their existing barrier.
- Viewer commands run on TelemetryPublisher's existing background handler until
  completion. Per-command daemon threads were removed from the runtime dispatcher;
  the WebSocket command queue no longer mistakes thread creation for completion.
- Connected virtual RvR waits for scene availability without raising a readiness
  fault. Simulation shutdown rejects active operations and retains its resources;
  stop is idempotent, and a closed world cannot be started/connected again.

Evidence: exact source/call-path inspection; AST parsing of hardware_manager.py,
telemetry_publisher.py, session_startup.py, self_play_controller.py and runtime.py;
node --check main.mjs; git diff --check. No tests, application/server/browser
execution, SQLite experiments, camera/SDK reads or physical actuation. Standalone
runtime commands keep their legacy contract and validate scene epoch when supplied.
Lock/cadence/shutdown fault injection, full transient-world/business-revision
linkage, reconnect reconstruction and remaining PR7/PR11 acceptance remain open.

## Atomic terminal move slice (2026-10-19; static only)

Source audit found that commit_move could persist a winning board while game_over,
winner and the end intent were only written later by a caller. A failure/crash in
between left a durable terminal board without its business outcome.

_record_commit_result now adjudicates king loss/no legal replies before the single
move snapshot/outbox write for normal human, emergency and robot moves. The journal
therefore records the terminal winner/reason/end intent with the winning revision.
Post-commit callbacks still publish as appropriate; repeated handle_game_over calls
preserve the recorded reason and do not advance AI invalidation again. A conflicting
winner is rejected rather than replacing a recorded result.

Evidence: exact commit/caller/journal source inspection, AST parse game_state.py,
git diff --check, graph impact query. No tests or application execution. A question
was sent to clarify whether mock/simulation integration tests may now be run despite
the earlier no-test instruction; no approval has been inferred. Crash/restore,
storage failure, mirror outage and terminal-delivery acceptance remain open.

## World snapshot context slice (2026-10-19; static only)

WorldStateSnapshot carries the applied projection baseline. get_snapshot now holds
the physics lock while collecting pieces, gripper and baseline metadata, avoiding
torn dictionaries or revision/pose association from a separate later read. Both
bridges record context under their reconciliation/physics locks only after applying
the board. Manager captures that context under the Game transition lock; manual
test projections are labelled separately. Physical grasp remains unverified.

Managed viewer checks world snapshots against the current session, revision, game
epoch, scene identity/epoch, FEN and virtual placement version. A busy context read
retains the last known rendering identity while withholding command permission;
initial managed connections without context wait for a valid baseline. Legacy
standalone streams keep their previous contract. This links simulated transient
poses to an applied baseline; it does not declare them camera-verified positions.

Evidence: AST parsing state.py/world.py, live_twin_bridge.py, physical_state_relay.py
and hardware_manager.py; node --check live_state.mjs/main.mjs; git diff --check.
No tests, application/browser/server execution, camera/SDK calls or physical motion.
Captured-tray reconstruction, manual-test/scene/reconnect races and full acceptance
remain open. The pending verification question has not been treated as approval.

## Captured-body / tray slice (2026-10-19; static only)

Source audit confirmed both full-board reconciliation and human-capture projection
deleted captured bodies. This erased tray occupancy before the next virtual capture
and made captured meshes disappear after reconciliation/reconnect.

- Both paths now retain the complete canonical identities. Captured bodies stay
  outside the board, preserving existing simulated poses and colliders. Missing
  bodies/inside-board initial bodies are reconstructed into configured nominal
  virtual floor slots; insufficient or overlapping slots reject projection before
  mutation. No physical teaching point is substituted.
- Shared capture_layout.py is used by reconstruction and the virtual capture
  executor. Executor IK/collision/grasp checks remain in their original path.
- Piece snapshots carry captured state and pose evidence; nominal positions never
  become measured/release evidence merely by being read again. Viewer renders
  captured bodies without assigning them board cells. Board/reset placement clears
  captured flags. Uncaptured out-of-bounds bodies keep the original hidden behavior.

Evidence: source inspection; AST parse capture_layout.py, simulation_adapter.py,
state.py, piece.py, world.py; node --check live_state.mjs/board.mjs; git diff --check.
No tests, application/browser/physics execution or hardware operations. Exact
pre-restart simulated release poses are not persisted; nominal rebuild is labelled
as such and is not a claim of physical tray alignment. Occupied/full tray, scene
movement, collision behavior, reset/reconnect and all T-01–T-22 gates remain unverified.

## Explicit virtual playback presets (2026-10-19; static only)

Added --simulation-profile detailed/fast with environment/config fallback and
finite speed validation in the existing viewer range. Detailed retains the old
0.2 default; fast uses 1.0 by default. Both enter the same physics/trajectory/grasp/
collision/commit code paths; no motion samples or checks are skipped by the preset.
This is playback pacing, not a reduced-accuracy physics engine or measured speedup.

CLI/programmatic session setup rejects the preset when simulation is off or physical
execution is active. Only virtual backend creation consumes it; FR3 MOVE_SPEED,
tool/Z mapping and enable are untouched. Virtual bindings include backend speed and
profile identity. Telemetry informs the viewer of the default, and speed-control
initialization retains its current value rather than silently restoring 20%.

Evidence: AST parse config.py, simulation_playback.py, launch_options.py,
session_profile.py, execution_binding.py, hardware_manager.py, telemetry_publisher.py;
node --check main.mjs; git diff --check; source inspection of virtual timing and
normal collision guard behavior. No tests/application execution, physics, browser,
hardware or benchmark. T-10/T-21 and measured animation/latency gates remain open.
Usage and the precise policy are documented in docs/SIMULATION_PLAYBACK.md.

## Static checkpoint / blocked verification (2026-10-19)

Saved reports/brd-static-checkpoint-20261019/source_manifest.json with SHA-256 and
byte counts for all 53 changed application files (49 Python, 3 JavaScript, 1 HTML).
Every changed application Python file passed AST parsing; node --check succeeded
for board.mjs, live_state.mjs and main.mjs; git diff --check succeeded. Application
modules were not imported/executed and the HTML was not rendered.

The pending request to permit mock/simulation tests has no answer. The same no-test
blocker recurred through more than three goal continuations. Source changes and
static inspection progressed meanwhile, but the remaining proof requires runtime
integration/fault injection/performance and separately authorized external gates.
No further specific code edit is justified by the current static evidence alone.
Goal remains incomplete; verification is blocked pending that user decision.
