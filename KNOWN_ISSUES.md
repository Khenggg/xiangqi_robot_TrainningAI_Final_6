## 2026-11-05 publication — whole-suite validation remains OPEN

115 focused cases pass. Expanded legacy checks expose a viewer test double
missing viewer_command_context; production code was not altered to bypass it.
Broad non-slow run was interrupted after failure markers (1123 parallel cases,
12% progress, exit1); no final failure trace/count, origins UNKNOWN. No whole-
suite green or physical acceptance claim. Evidence in publication report/logs.

## 2026-11-03 disconnected shutdown refusal — explicit exit replaced

The old recovery loop refused exit with cached motion ownership/pending work
after disconnection, even after operator confirmation. User-requested behavior:
one Exit/Stay prompt, Yes terminates immediately without device prerequisites.
12 focused mock/UI/subprocess tests PASS. Saved journal remains unfinished if
appropriate; exit is not a transaction commit or a controller reset. This change
is in the isolated worktree, with no hardware operation or automatic restart.

## 2026-11-03 session button fixes — physical acceptance OPEN

Busy/pick-paused surrender and cached ACKed-stop timeout cases repaired with
deferred end and read-only settling. Unknown stop/controller error remains gated;
pending physical moves must still be reconciled before new game/end. User's
specific real-world wait cause not fully established by logs. Mock/UI checks
PASS (73 scoped; final39 stop +14 UI), no physical operation or restart performed.
Captured pick context now names Red Knight b9; actual6.1–6.3mm offset remains
above unchanged6.0mm limit. See session-buttons/pick report dated20261103.

## 2026-11-02 robot PvP stale startup-pause flag — fixed in worktree, live pending

V resumed camera/baseline but failed to clear snapshot_continue_required after
an initial NO_FRESH_OBSERVATION; strict new-mode admission correctly stayed
locked. New-mode V/Continue now clears/persists pause with existing board/hardware
checks, unresolved-work and newer-stop guards.51 focused tests PASS. Running
process not changed/restarted; equal-board startup pause can use old CONTINUE.
Physical acceptance/full regression not claimed. See
reports/robot-pvp-20261102/PVP_CAMERA_PAUSE.md.

## 2026-11-02 YOLO baseline31 — detection/mapping cause OPEN

Current physical PvP log verifies ONNX opening32 (diff0) while YOLO T1 occupancy
has31 cells. Legacy message conflated counters; labels/structured missing-cell
diagnostics corrected in worktree, now with readable expected piece names and
square/row/col. Follow-up30 tests PASS, exit0. Actual dropped/filtered/
duplicate detection and which live cell remain UNKNOWN; no threshold/calibration
change or forced count32. No robot/camera command or process restart performed.
See reports/robot-pvp-20261102/YOLO_BASELINE_31.md.

## 2026-11-02 isolated robot PvP — acceptance and broad regression OPEN

New mode implemented only in sibling worktree codex/robot-pvp-20261102. Host Red,
client Black over localhost (same PC); no LAN/Internet room service. Physical
camera/FR3/full-game acceptance NOT RUN. Broad non-slow regression interrupted
after failure markers; failure origin UNKNOWN, no whole-suite PASS/merge-ready
claim. Focused116 PASS with final new-mode rerun documented separately. Physical
controller faults remain independent of room/FEN. See reports/robot-pvp-20261102.

## 2026-11-02 real controller main1/sub29 — OPEN

At 16:30:45+07, read-only GetRobotErrorCode returned [0,1,29] while camera had
confirmed the 32-piece opening. This correctly blocks fresh-idle/stop recovery;
V/F12 or a new application session cannot resolve a controller fault. Specific
hardware explanation now retained in status/log/recovery panel. 78 focused tests
PASS, exit0; unrelated legacy emergency fixtures still FAIL. Actual controller
recovery/root cause, loaded motion and running UI acceptance remain unverified.
No enable/reset/motion sent. See `reports/recovery-hardware-block-20261102/REPORT.md`.

## 2026-11-02 retry and physical board viewer — runtime acceptance pending

V-baseline-only and compact Continue dispatch repaired with guarded pick retry.
Nominal reversed-column physical viewer replaced by a separate read-only taught
R1–R4 XY display path; rig/attached/released payload projections covered offline.
86 focused tests PASS, final display8 rerun PASS, 3 Node geometry suites PASS.
Z surface remains unmeasured/unverified; loaded grasp/release and full-game motion
remain unverified. Running app/viewer must reload; no pending session was cleared.
Recorded 6.7–7mm target offset is still blocked by unchanged6mm policy; FEN success
alone does not bypass target verification. See
`reports/retry-board-display-20261102/REPORT.md`.

## 2026-11-02 short board release — physical verification OPEN

User requested 0.06s opening at board release after reporting full opening hits
neighbors. Separate release pulse/action implemented; post-release safe-gap close
removed because its full-open starting assumption no longer holds. Initial and
capture-bin OPEN_MAX unchanged. 29 targeted mock tests PASS, exit 0; no physical
test. Effective jaw travel/clearance and repeat picks remain unverified; no
position sensor. Restart required. See gripper report for command/evidence.

## 2026-11-02 gripper direction after rewiring — game release verification OPEN

After operator swapped control wires, separate observed pulses verify DO1 closes
and DO0 opens. Gameplay config corrected accordingly; app restart required to
load it. 33 focused mock tests PASS, exit 0. Isolated empty-jaw direction verified
physically; full stroke/loaded release during play NOT RUN. Original pre-rewire
electrical failure remains UNKNOWN. Separate legacy backend defaults unchanged.
Evidence: `reports/gripper-release-20261102/REPORT.md`.

## 2026-11-02 DO1 release produces no observed motor motion — PRE-REWIRE HISTORY

Game RELEASE command was not omitted: log has DO1/open_max 0.30s, but piece is
missing at destination. One user-authorized isolated open pulse with empty jaws
and stationary arm also produced no motor sound/motion per operator; controller
accepted ON/OFF and reported no fault. Driver/output electrical state is not
measured. Preserve mapping/timings; do not assume a longer pulse or channel swap
fixes it. No production fix or further pulse performed. Evidence:
`reports/gripper-release-20261102/REPORT.md`.

## 2026-11-02 PvP integration remains open

Remote donor SHAs unchanged; functional comparison and decision matrix added in
`reports/branch-reviews/PVP_FEATURE_COMPARISON_20261102.md`. player-vs-player tip
reverts PvP; nguoivsnguoifinal supplies localhost two-window roles and a legacy
two-human/one-FR3 path, with the previously reported F1–F7 still unresolved.
Focused recheck 58 PASS (exit 0), including 11 defect-reproduction probes; no
runtime fix or integration. Hvh remains virtual in current SessionProfile.

## 2026-10-31 controller fault and active-tool discrepancy — OPEN

12:04 confirmation: symptom occurs during the move. Three mock-only diagnostic
probes demonstrate no measured-arrival check between APPROACH and LAND/GRIP;
the trace can mark APPROACH complete solely on a fake successful return. Real
blendT=-1 is documented blocking, so actual premature return remains UNPROVEN.
Current controller 1/1 and tool/user 1/0 were freshly reconfirmed. No physical
motion or production repair was performed.

VERIFIED at 11:43 +07:00: controller main=1/sub=1 persists without the game app;
200 valid state packets show active tool/user=1/0 versus fixed profile 0/0.
Joints remain near yesterday's abnormal observation (max delta 0.001526 deg).
F12 clears application/FEN state, not this controller fault or an arm route.
Do not interpret the 260.649 mm change of reported TCP as arm travel:
current flange nearly matches yesterday's TCP; active tool context differs.
Historical collision causality and physical recovery remain UNVERIFIED. No
motion/reset/tool change was attempted. See
`reports/controller-check-20261031/REPORT.md` and its raw/JSON evidence.

## 2026-10-30 live pose / vertical-motion primitive — OPEN / HIGH

Read-only investigation after the user's new launch found current-reference IK
returns 112 for both source approach and land, while using saved HOME as the
reference gives endpoint solutions. Current measured pose is far from the target
and controller reports E-Stop active. This does not authorize a HOME move or prove
which historic IK branch caused contact. Both move_safe_pose and movel_pose use
MoveCart(config=-1); the latter does not guarantee the advertised vertical linear
path. No production fix or physical replay was performed. Current values, FK/IK
results and latest-session LAND/112 evidence: `reports/live-pose-20261030/REPORT.md`.

## 2026-10-30 physical collision / restart approach — OPEN / HIGH

User reports physical contact after restart/F12, not merely a controller collision
alarm. Logs show board checks passed then first AI approach failed with MoveCart
14 at 20:03:54. F12 and activation currently verify board/idle/stop, without a
separate verified post-interruption arm-start/route contract. move_safe_pose calls
MoveCart(config=-1) although its comment claims straight-line motion; vendor
defines MoveCart as point-to-point with current-joint-based solution. The exact
collision mechanism/changed joint solution is not proven by available logs.
No production fix, controller query or motion was performed. Preserve pending
command/receipts and require manual mechanical/route verification before motion.
Evidence and verification limits: `reports/powerloss-incident-20261030/REPORT.md`.

## 2026-10-30 PvP donor integration — OPEN / not merged

`feature/player-vs-player` tip `75c1bc9` has reverted the PvP feature.
`feature/nguoivsnguoifinal` tip `73af0f1` retains a separate PvP controller
with legacy auto-enable/HOME startup, direct robot dispatch with optional
targets, board commit before camera verification, weak sample acceptance,
synchronous UI work and room lifecycle defects. Its physical/test APIs also
conflict with current SessionProfile/move_context contracts. These findings
belong to donor/integration scope; they have not been applied to runtime here.
Keep fresh-start/FEN/F2/fixed-user-0 and current authority gates when porting.
Reports, exact refs, mock/loopback evidence and selective port recommendations:
`reports/branch-reviews/feature-nguoivsnguoifinal_vs_need-review_REVIEW_REPORT.md`.

## 2026-10-30 fixed-profile authority

Physical gameplay now uses the user-selected fixed tool 0/user 0 snapshot,
including HOMECHESS and R_Trash. The WObj selection/API compatibility requirement
below applies only to optional live-controller diagnostics, not the default game
path. Numeric poses/joints are preserved from the recorded snapshot; changing the
physical setup requires updating the selected profile explicitly. Profile errors
block activation without querying controller points as a fallback. Optional mirror
geometry/surface Z configuration is still required independently. Related tests:
92 passed (exit 0); physical robot/camera and full regression NOT RUN.

## 2026-10-30 F2/restart fix verification boundary

Follow-up logs verify that this controller rejects GetWObjCoordWithID with
Fault -506. Compatibility fallback is now tested; on this firmware the operator
must select User/WObj 1 for identity verification when R1–R4 contain user 0/1.
F9/F10 can then reload metadata without repeatedly restarting. Code does not
change the controller's active frame or infer frame 1 from frame 0. Mock-based
focused checks: 55 passed (exit 0); physical behavior remains unverified.

F2 no longer calls HighGUI destroyWindow on the device-disposal worker. Restart
verification now reads an identity WObj by its taught ID, independently of the
active frame; a genuinely different/unknown transform still blocks activation.
Focused regression and a real native window/fake camera probe passed. No live
controller query, physical enable or motion was performed; older controller API
availability and complete hardware behavior remain unverified. Restart the app
to load the patch. Evidence: `reports/f2-frame-restart-fix-20261030/REPORT.md`.

## 2026-10-30 gameplay continuity — OPEN

Physical enable does not preflight HOMECHESS/R_Trash for a complete game;
HOMECHESS frame mismatch already appears in a historical PHYSICAL move after
camera verification passed. Missing R_Trash can surface only on the first capture.
The FEN retry deadline does not bound a blocked camera call. After clearing a
pre-pick AI fault against the old board, F5 is still needed to restart the AI turn,
despite the resumed-scanning success message. These are audit findings, not fixes.
See `reports/physical-gameplay-audit-20261030/REPORT.md` for evidence and limits.

## 2026-10-30 physical flow — OPEN / P1

Mock-based audit reproduced three unresolved defects: a stop arriving during
activation does not prevent the subsequent controller enable; telemetry can
become moving/stale during camera verification without blocking enable; the
center sampler can accept earlier targets after its last camera read fails,
allowing dispatch. No production fixes were made in this audit. Hardware effects
have not been physically verified. Focused tests: 104 passed / 3 failed (exit 1),
with failures documented separately from the three reproduced defects.
See `reports/physical-flow-audit-20261030/REPORT.md` for evidence and recommendations.

## 2026-10-30 FEN diagnostic boundaries

New logs distinguish mismatch, confidence/quality/sanity failure, rejected frames,
exceptions and incomplete stable samples. Human text limits cell lists to 20;
JSON `diff_cells` retains the complete list. No image/video is captured, and old
logs are not rewritten. A model-provided `quality_ok=False` without an error
remains `QUALITY_REJECTED`; the logger cannot infer a missing model explanation.
Thresholds and physical gates are unchanged. Scoped tests: 114 passed (exit 0);
physical camera/FR3 and full regression NOT RUN.

## 2026-10-30 fresh-start verification boundaries

The launcher now creates a fresh opening game rather than restoring the previous
board/FEN. Prior sessions are retained in the journal's `session_archive`, with
their original command receipts. There is no automatic archive pruning or UI
for restoring an archived game. Invalid/corrupt saved snapshots still fail closed.
An unresolved physical recovery latch can still require pendant inspection,
Ctrl+F8 and V before enable; its camera target is the new opening board, not the
old FEN. Real camera/FR3 behavior was not exercised for this change. Fresh-start,
durability, stop-barrier and related startup tests: 102 passed (exit 0); full
repository regression NOT RUN.

## 2026-10-28 robot Ethernet cable is loose (intermittent 192.168.58.2 loss)

The physical controller link is known to drop intermittently because the
Ethernet cable/connector is loose. Expect transient `GetControllerIP: controller
reply unavailable` / `Robot SDK not connected` messages and stale telemetry.
This is a hardware/link condition, not automatically a software regression.
Check/reseat the cable, then verify with:

```powershell
ping -n 2 -S 192.168.58.3 192.168.58.2
```

Do not replay motion after an unknown RPC outcome and do not enable F9/F10 while
the link is unstable. Full checklist: [`ROBOT_CONNECTION.md`](ROBOT_CONNECTION.md).

## 2026-10-28 client-control and rollback notes

Mode-specific controls are driven by `SessionProfile` capabilities. Mock-based
tests that construct partial state objects without `get_render_state` retain the
legacy all-controls layout; they do not prove the physical UI path. Rollback
restores the game board and starts a fresh synchronization; in physical mode it
still requires a fresh board verification and latches the physical sync fault as
before. No physical or browser soak was run for this UI pass.

## 2026-10-26 captured tray limitations

Captured bodies are removed from physics and represented only by immutable
snapshots in `world_state.captured_pieces`. The snapshot pose is the simulated
capture slot, not a calibrated physical tray pose. The tray list is sent with
every world state; it is visual history, not grasp/force evidence. Reset is
required to respawn captured bodies. Three legacy camera-pipeline tests that
drive `HUMAN_VS_HUMAN` through `_handle_space_key` still fail because that path
intentionally rejects camera/SPACE for two-human games; they are test-fixture
mismatches, not captured-tray regressions.

## 2026-10-26 projection and gripper visual notes

The projection guard blocks stale board reconciliation during a pending semantic
move, but a direct bridge call outside `HardwareManager.sync_committed_board`
still bypasses that guard. Virtual jaw travel is intentionally exaggerated 12x
and must not be read as physical stroke/force evidence; physical mode uses the
exact CAD travel. The spectator log stops retrying archived entries when no
`XIANGQI_SIMULATION_TOKEN` is configured, but archived projections are not sent
later if a token is added mid-session. No physical/browser soak was run.

## 2026-10-26 vendored OCCT dependency

The 3D viewer now depends on the checked-in `occt-import-js` JS/WASM pair rather
than the jsDelivr CDN. The files are LGPL-2.1; see the vendored `LICENSE.md`.
They are not downloaded automatically. If the vendor directory is missing, the
FR3 CAD gripper cannot load and `connectLive()` remains disabled by design; the
viewer shows `VIEWER_FAILED` instead of connecting without a tool model. No
physical run was performed for this change.

## 2026-10-26 home mode selector limitations

The three home cards choose the session environment, but they do not perform a
preflight connection test. Selecting **Robot thật** without camera/FR3 opens the
normal startup error path and returns to the home screen; it does not silently
fall back to 2D. `HUMAN_VS_HUMAN` with the physical card still resolves to a
virtual simulation by the existing game rule. No physical/browser soak was run.

## 2026-10-26 replay and action-intent limitations

Reconnect replay sends the last physical `gripper_command` as a historical
animation hint; `robot_state` still arrives first and remains authoritative for
the jaw. The packet is not a grasp proof. Safe-gap is mapped to idle in the
twin, but the viewer jaw still follows the boolean `robot_state.gripper`, so a
partially closed safe-gap pose is not represented. The action-aware listener
signature is internal to the twin bridges; no physical/browser soak was run.

## 2026-10-26 gripper_command packet limitations

The packet is an animation command, not grasp evidence. It is physical-only and
gated in the viewer, but a disconnected/slow client can still miss it, and a
reconnect cannot reconstruct a grasp that happened entirely offline. Virtual
mode does not use it. No physical run or browser soak was performed.

## 2026-10-26 viewer gripper animation limitations

The web attachment is a command-edge estimate (`physical_grasp_verified=false`),
not jaw/force sensor evidence. It can show attached when the real gripper missed,
or show nothing when the WebSocket is disconnected, the viewer is slow, the
bridge uses `RawArmRelay` (no pieces), or the viewer rejects a stale context. A
stale telemetry poll no longer suppresses the attachment, but complete viewer
reconnect/slow-client/occlusion reconstruction remains unverified. No hardware
run.

## 2026-10-26 board surface Z source limitations

Using `BOARD_SURFACE_Z_SOURCE="R1_R4"` assumes all four R1-R4 points were taught
with the contact tip exactly on the board surface, not at SAFE_Z. The default
`R1_R4_TAUGHT_AT_BOARD_SURFACE=False` therefore keeps the mirror unavailable
until an operator confirms it. The derived Z affects only the viewer mirror;
robot commands still use absolute `PICK_Z`/`PLACE_Z`/`SAFE_Z`. No hardware
measurement was performed, and the current controller's R1-R4 provenance is
UNKNOWN.

## 2026-10-26 first-pick opening / pick retry limitations

Opening an unknown gripper at the first pick assumes no payload is held from a
previous session; if the gripper is known closed, the code refuses the pick but
the operator must inspect and clear it. Pick-target retry adds up to roughly
0.8s of extra sampling/waits before the existing pause; actual occlusion
recovery, latency and hardware behavior were not measured. Limits (6mm,
0.12 cell) are unchanged. No physical run.

## 2026-10-26 visual-correction-v2 motion profile limitations

The adopted motion profile (`SAFE_Z=220`, `ROTATION=[180,0,-73.2]`,
`MOVE_SPEED=50`) comes from the visual-correction-v2 donor branch, not from
measurements on this robot. The ~62° Rz change and +10 mm safe height are
unverified; a wrong jaw yaw can collide with neighbouring pieces. Gripper pulses
remain the project's 0.30/0.80, not the donor 0.25/0.20. `MOTION_PROFILE_VERIFIED`
stays false until the operator measures RPY and clearance on the pendant. No
physical run was performed. Rollback values are in
`docs/VISUAL_V2_MOTION_PROFILE.md`.

## 2026-10-26 camera recognition readiness / board retry limitations

Physical startup now refuses to continue without both CChess ONNX and YOLO
`best.pt`; a deployment that intentionally runs without one of them will fail
until the model is installed or the profile is changed. The new board-verify
retry waits up to 2 seconds by default and still requires exact 90-cell equality;
actual latency, transient-occlusion behavior and hand/arm clearance were not
measured on hardware. The known baseline test
`test_camera_startup_and_health.py::test_old_board_confirmation_does_not_automatically_retry_physical_robot`
remains failing because its fixture lacks `expected_board`/recovery methods; it is
not caused by the retry change. No camera or robot run for this section.

## 2026-10-26 camera calibration startup limitations

A saved `perspective.npy` is accepted when its shape, rank and finiteness pass;
it is not yet bound to camera index, resolution or a metadata hash. If the
camera or capture resolution changes without `--recalibrate-camera`, startup
can reuse a stale matrix. A missing file still opens the interactive window and
an invalid file fails startup. Remote/headless operation still needs a desktop
for Pygame; only the calibration window is skipped. No camera or hardware run
was performed for this change. See `docs/START_PROJECT.md` and
`docs/LOGGING.md`.

## 2026-10-26 base-only robot frame policy

The application now enforces robot-base teaching points (`user 0`) and one common
tool frame. It does **not** convert `user 1` coordinates to base: a controller
with R1-R3 user=1 or R4 user=0 will stay read-only and reject F10/motion until the
operator re-teaches R1-R4, HOMECHESS and R_Trash in user 0. The read-only audit is
`tools/diagnostics/read_teaching_points.py`; it never enables or moves the robot.
No hardware or camera run was performed for this policy change, and no existing
calibration artifact was rewritten. Pick/retry diagnostics now include measured
centres, offsets, valid-sample counts and jitter in structured events; a rejected
Y/Continue is logged with its mode and reason. See `docs/ROBOT_FRAME_BASE_ONLY.md`
and `docs/LOGGING.md`.

## 2026-10-19 executable QA: remaining regression and hardware gates

The user has now authorized virtual/mock execution; the no-test blocker below
is historical. Current results and source-backed fixes are recorded in
docs/USER_FLOW_QA_20261019.md. Main user flows passed with real virtual motion
and an independent headless viewer; the broad run still has 35 unresolved
failures requiring contract/fixture/source triage. Do not equate the passing
focused/serial suites with a clean full regression or physical acceptance.

## 2026-10-19 verification blocker

Current dirty-tree changes have whole-application syntax evidence only. The
pending clarification about lifting the earlier no-test instruction has not been
answered through multiple goal continuations. Integration/fault injection and
performance remain unexecuted; physical acceptance also needs explicit separate
authorization and measured inputs. Goal completion is unproven. Preserve this
worktree/checkpoint and resume with isolated tests when permitted; do not infer
approval or report the old passing tests as validation of these drafts.

## 2026-10-19 virtual playback profile limitations

Detailed/fast are playback presets using the same full physics/check path, not
different accuracy or collision policies. No runtime evidence yet for CLI/capability
combinations, speed binding invalidation, viewer controls or complete animation
visibility in continuous play. Actual speedup/FPS/latency are unmeasured. Physical
execution does not consume these presets. Earlier test results do not cover them.

## 2026-10-19 captured tray limitations

Captured-body retention, nominal rebuild and viewer rendering are implemented
drafts, not runtime-verified. Rebuild preserves logical captured identities but
uses labelled nominal slots when the prior simulated pose is unavailable. It does
not recover a measured physical trash/tray pose or persist the exact former release
pose. Captures, occupied/full tray, corrupted slots, collision behavior, reset and
reconnect still need tests. Physical execution/calibration coordinates are unchanged.

## 2026-10-19 world snapshot context limitations

World snapshot/business context linkage is implemented but unverified. A context
references the committed baseline applied to the simulated world; transient poses
remain predicted, not proof of a physical grip. Reconnect races, manual test mode,
scene/placement reset, captured tray and all identity/state reconstruction need
runtime coverage. Tests remain pending the no-test clarification.

## 2026-10-19 terminal commit limitations

Winning-move outcome/end intent are now part of the same durable commit draft.
No execution evidence yet for storage failure, crash/restore at the commit edge,
mirror failure, missing-king terminal positions or duplicate terminal callbacks.
Earlier tests predate this change. Integration verification permission is pending;
no tests or physical hardware were run in this slice.

## 2026-10-19 viewer command context limitations

Managed game/scene command binding and whole-operation ownership are implemented
but unverified. Runtime/fault injection still must cover queued commands across
reset/mode switch, command completion during shutdown, lock contention and virtual
continuous cadence. Standalone runtimes without a Game owner retain their legacy
command API; scene epoch is checked when supplied. Committed FEN/session metadata
is now carried with robot telemetry, but complete Twin reconstruction and linkage
between transient world snapshots and committed business revisions remain open.

## 2026-10-19 viewer stream ordering limitations

Publisher stream sequencing and reconnect subscription are implementation drafts
with syntax evidence only. A publisher stream is not a GameSession/scene epoch;
same-stream game reset, complete FEN/session metadata and queued scene-command
binding still need audit/implementation. Legacy unversioned servers remain usable
until a versioned stream is established. Live reconnect/slow client/concurrent
producer and stale command acceptance tests have not been run.

## 2026-10-19 projection concurrency limitations

Source guards now serialize local committed-board projection with reset/dispatch
and prevent virtual AI admission before its executor's board is synchronized.
No runtime evidence yet for lock contention, human-to-AI timing, continuous play,
reset races or scene rebuild. Reconnect/wire session-revision ordering and complete
Twin reconstruction still require implementation/acceptance audit under PR7.

## 2026-10-19 startup ownership / cancellation limitations

Startup lease ordering, stable journal root and calibration cancellation have
static evidence only. Duplicate launch, cancelled startup, camera loss/blocked
read and failed calibration-window close still need runtime/fault injection.
If an older absolute --log-dir stored a journal outside this repository's runtime
folder, startup reports both paths and refuses to ignore that session. No files
were moved; migration must preserve SQLite state/WAL and occur with all owners
closed. A blocked native camera read cannot be force-terminated safely here;
cleanup retains ownership and retries after the reader exits.

## 2026-10-14 physical XY / command binding limitations

Physical XY registration and command fingerprints have no runtime evidence.
Measured grid dimensions, robot-base surface Z and frame conversion provenance
remain required external inputs; no values were invented or controller rewritten.
Previously tolerated mixed R1–R4/HOME/Trash frames now fail explicitly.
Pending binding guards cover normal game dispatch and physical stage transitions.
Manual-test receipts and read-only reconciliation are implemented but unverified;
full reset/reconnect/version coverage and controller changes outside the cached
mapping still need work/evidence.

## 2026-10-14 XY calibration worktree limitations

XY simulation calibration/profile/UI have syntax evidence only. Rotation, all 90
targets, independent Z, malformed/reflected points and collision/rollback behavior
need runtime verification. Profile v1 is deliberately rejected for this workflow.
Controller XY integration with verified dimensions/frame conversion and independent
surface Z remains open, together with end-to-end transaction/version invalidation.

## 2026-10-14 spectator routing worktree limitations

Durable session/room routing and FEN/End acknowledgement records are implemented
drafts. Archived updates are scoped to their server and room, preserving normal
move order. No runtime evidence yet. A server reply lost before local recording
still requires protocol/readback support; no success is inferred from an HTTP
timeout. Old rows without room bindings remain pending. Archived rooms in another
environment journal are retried when that environment is opened. Remote custom
FEN, rollback/rescan, duplicate End and creation ambiguity remain acceptance gaps.

## 2026-10-14 retirement worktree limitations

Mode switch, partial-startup failure retention, shutdown retry and operator-only
disable confirmation are implemented drafts, not runtime-proven fixes. Pending
physical transactions prevent mode replacement. Shutdown preserves interrupted
transactions for recovery. Stop/disable ACK-loss, failed camera/web closes and
startup cancellation need execution/fault-injection evidence before acceptance.

## 2026-10-14 mode capability worktree limitations

New capability routing, PvP isolation, virtual input labels and raw-relay fallback
have syntax evidence only. The six combinations and resource failure paths need
runtime verification. Controlled in-app mode switching remains unfinished; restored
mode mismatches currently pause and require pending recovery/New Game.

## 2026-10-14 projection worktree limitations

Async outbox/ACK/terminal queue code has no execution evidence. Archived terminal
intents still lack durable routing to retired remote rooms after restart; queued
delivery is best-effort. Upstream duplicate/custom-FEN behavior needs actual service
evidence. No robot or Game command is replayed by the projection worker.

## 2026-10-14 persistence worktree limitations

SQLite journal/restore/command receipts and exception recovery UI are implemented
but have no execution evidence. Durable outbox now has a draft worker/ACK adapter;
legacy recovery consistency, three-mode routing and calibration remain open.
No earlier test pass validates this draft; see docs/BRD_IMPLEMENTATION_PROGRESS.md.

## 2026-10-14 controlled-stop worktree limitations

New stop/reset/end code is syntax-checked only; runtime/fault-injection evidence is
pending. Abrupt exceptions/KeyboardInterrupt and persistence have draft handlers
but still need runtime/fault-injection verification.
Pending real capture/motion is retained for operator reconciliation; unknown ACK
does not allow replay. See docs/BRD_IMPLEMENTATION_PROGRESS.md. Not commissioned.

## 2026-10-13 Camera Monitor / GPU correction

Continuous capture/inference start restored, atomic/pick snapshot APIs restored, stale boxes hidden, VISION_DEVICE=auto/cpu supported. Installed Torch2.14.1+cu126 + ORT-GPU1.20.2; actual camera2/DSHOW GPU preview retained32 named pieces through15s. Final scoped gate123passes. Full gate857passes/12baseline findings; UI accent fix resolves3,9findings remain. See docs/CAMERA_MONITOR_GPU_FIX_20261013.md. No robot actuation or calibration changes.

## 2026-10-13 raw arm reconnect QA

Failed SDK startup now retains the read-only state mirror/WebSocket so receiver recovery can reach the viewer independently of board calibration. No automatic actuation authorization. 98 scoped Python passes and three Node suites; actual FR3 + WebSocket + browser joint values matched with board uncalibrated. See docs/ARM_RECONNECT_QA_20261013.md.

## 2026-10-13 board-side orientation QA

Nominal red/black sides reversed: corrected through shared transform. Fixed default yaw0 discrepancy in provider/cell helpers. Calibration warning remains appropriate. Interrupted103-case sweep is not accepted; final scoped90 tests passed. Physical alignment and motion remain unresolved.

## 2026-10-13 raw arm viewer QA

Raw-arm SDK/WebSocket can be live while the old static PREVIEW OFFLINE notice persists; notice repaired. Operator screenshot omitted connection HUD, so its exact socket state remains unproven. R4 frame mismatch, board calibration, camera visual estimator and measured model/controller flange parity still unresolved; no physical motion tested.

## 2026-10-13 live QA / SDK shutdown

SDK cleanup when is_conect=False skipped CloseRPC and reconnect ignored shutdown; repaired. Current physical session still has no verified stream and no WebSocket8765; fresh network check required. R4 frame mismatch and visual-estimator dimensions remain unresolved. No motion performed.

## 2026-10-13 Live SDK / R1-R4 frame mismatch

Startup first reported SDK_state unavailable (receiver cause unproven); next attempt connected but rejected R1-R4 frames. The latter software connection/calibration coupling is repaired. Actual R4 user=0 while R1-R3 user=1 remains unresolved; no controller data changed. Restart required; real stream freshness, board contact calibration, visual-estimator dimensions and measured flange parity remain unverified.

## 2026-10-13 worker scheduling / retry corrections

The six reproduced failures in `docs/RUNTIME_RACE_REVIEW_20261013.md` are repaired within the recorded software boundary. QUIT prevents later dispatch; it does not stop SDK motion already sent. Worker ownership gates defer scheduler commands; they do not certify FR3 physical safety. Retry preserves confirmed commits and requires camera baseline repair when needed. Hardware, real camera recognition, trajectories and spectator remote ACK remain NOT RUN in this round. Full gate: 1052 passes (exit 0). Primary compile/parity passed; see delivery-manifest.json.

## 2026-10-13 game mode review

Repaired the UNIFIED Red-only/matcher lifecycle and confidence adapter gaps, interrupted sample window reuse, robot entrypoints ignoring terminal/unconfirmed turns, and Continuous surrender being gated by Step-only next-move permission. Matrix scope and exact limits: `docs/GAME_MODE_REVIEW_20261013.md`. The three-mode PyBullet board test mocks arm execution; it does not validate full pick/place paths, camera model accuracy or real hardware. WebSocket legacy warnings remain unchanged.

## 2026-10-12 lifecycle edge review

Repaired human checkmate/terminal spectator gaps, direct post-game and illegal Emergency mutations, rollback retaining cancelled undo snapshots, Emergency false baseline success after rejection/mirror failure, and camera Q still dispatching a ready AI move in the same frame. Evidence and scope: `docs/LIFECYCLE_EDGE_REVIEW_20261012.md`. Physical camera/FR3 and live HTTP remain unverified; camera acceptance of missing-king human terminal boards is not proven by the game-logic test.

## 2026-10-12 spectator lifecycle follow-up

Repaired restart after spectator close, duplicate room creation/end requests, post-end FEN enqueue, finished self-play restart and startup error-message overwrite. Current software evidence: `docs/SPECTATOR_LIFECYCLE_FIX_20261012.md`. The previous spectator-close correction introduced the F8/F6 reopening gap now repaired. Live HTTP acceptance of a midgame FEN in a newly reopened room remains NOT RUN, as do camera/FR3 hardware and measured scene parity.

## 2026-10-12 second review corrections

The seven reproduced software failures in `docs/RELIABILITY_RECHECK_20261012.md` were repaired. Physical board recognition normally requires both kings; known king-capture removal/post-board may declare exactly the captured king color while retaining complete expected-board/quality gates. Hardware alignment/recognition/latency and mechanical commissioning remain unverified. This is scoped regression evidence, not a claim of zero remaining repository bugs.

## 2026-10-12 current verification limits

- Current physical commands follow visual-correction-v2; simulator collisions do not decide physical execution, as explicitly requested. Simulator attachment is a command estimate, not measured jaw contact.
- Board contact offset/calibration still needs measurement to claim physical board/piece alignment. Raw-arm Connect live is available without that provider when controller telemetry is valid.
- Hardware grasp/place/capture, firmware completion and real camera/robot/browser latency have not been tested in this correction. SDK socket timeout/lost reply cannot prove the arm stopped; no actuation replay is performed.
- Historical failure notes below may be superseded; use `docs/RELIABILITY_FIXES_20261012.md` and the current run's evidence. WebSocket legacy API warnings remain; no dependency migration in this task.

## 2026-10-09 physical lag / unavailable mirror

- Continuous GUI polling no longer flushes the camera or reruns ONNX/YOLO; atomic cached observations retain age, uniqueness and baseline-boundary gates. 72 focused tests passed.
- Missing physical board contact offset still blocks live mirroring. HTTP now serves an explicitly labeled offline preview. Cold model initialization, explicit SPACE/scan/API latency and SDK state-receive failures remain unverified in the live hardware session.
- Restart the game and hard reload the viewer to use this patch. See reports/physical-ui-latency-20261009/REPORT.md.

## 2026-10-09 physical startup blockers

- Latest physical-session log (17:57:39) could not read camera index1; WindowsCamera was running when inspected. Device contention is plausible, not conclusively proven. Close competing camera apps and retry; the GUI now keeps the home screen with an error on startup failure.
- That session also refused physical mirroring because BOARD_CALIBRATION_OFFSET_MM was unset. This patch does not invent a contact offset or bypass calibration; physical viewer/motion readiness is not proven.

## 2026-10-09 Windows viewer startup scope

- Setup now includes the local Three.js dependency; missing modules produce an explicit setup error. Module MIME handling and RUN.bat argument forwarding/exit status were repaired and verified in isolation.
- The earlier browser main.mjs load failure was transient in the observed running session; exact historical cause is unconfirmed. Optional STEP loader still comes from CDN; an offline CAD-loader bundle is outside this patch. Camera/FR3 commissioning remains unverified.

## 2026-10-09 visual v2 limits

- Height/top-face/ring are opt-in and require measured dimensions plus a matching current camera profile. No donor camera0 intrinsics, gripper pulses or tool rotation were applied. Hardware optics/commissioning remain unverified.
- SDK failure is not sampling retry; retry exists only at a verified pending pre-pick/capture-removal checkpoint. SDK calls already executing cannot be cancelled by ending a UI thread; shutdown retains devices if workers still run.
- Local simulation and focused failure injection passed; fresh Windows/Python3.12 installation and long soak are not proven. See `reports/visual-integration-20261009/REPORT.md` for the exact full-run/final-focused scope.

# KNOWN_ISSUES.md — COMPACT ISSUE & REGRESSION TRACKER

## 2026-10-06 live viewer freeze follow-up

- Fixed synchronous callbacks blocking the network loop, unlimited state-send scheduling, stale virtual mirror overwrite and missing operation-state replay. Bounded snapshot transport and explicit overflow/slow-client disconnect replace unbounded send tasks.
- Final virtual ROBOT VS ROBOT GUI run completed 10 plies, two captures and surrender, with 0 twin faults/error events; final 30 piece identities/cells match and viewer reload returns IDLE. Six new liveness cases pass. Evidence: `reports/telemetry-fix-20261006/REPORT.md`.
- Earlier GUI attempt with the partial fix still froze; two diagnostic-wrapper sessions exited abnormally for an unconfirmed reason. They are not passes. Cancellation of to_thread does not terminate an executing runtime callback. Full regression, long soak and real camera/FR3 remain unverified.

## 2026-10-05 selective visual integration

- Resolved donor manual test continuation after SDK 112 and repeat commands after failed camera verification: common typed executor, separate identities, latched fault and explicit reset/reconciliation.
- Measurement no longer bypasses read-only startup/current calibration frame. Requires fresh idle TCP/actual safe Z; close/menu/restart disable only activation owned by the session and report failures. Manual physical test faults also revoke owned activation.
- Fixed carried-piece selection (`ATTACHED_TO_GRIPPER`) and rejected ambiguous/out-of-range/missing-distance cells. Removed stale 150mm initial UI readout. Updated fixed-placement/tool fixtures from canonical sources; replaced an obsolete reach-limit assertion with actual below-board rejection/invariance.
- Remaining limits: camera/SDK failure paths use mocks; live optics and hardware commissioning are unverified. Measurement requires verified physical calibration, explicit operator clearance and DRY_RUN=0; it is not a hardware collision planner. No changes to the physical tool length or gripper opening in this integration.
- Verification details and commands: `docs/VISUAL_LATEST_REVIEW_20261005.md`, `reports/visual-integration-20261005/`.

## 2026-10-04 oversized game window

- Fixed fixed-size display overflow with DPI-aware startup sizing, RESIZABLE display, aspect-preserving canvas scaling and matching mouse mapping. Added F11 fullscreen / Esc return.
- 22 scoped GUI/input tests passed. Native Windows fullscreen/restoration probe passed; the revised window is visible in full on desktop.
- Remaining verification: Computer Use has not successfully driven a game move or F11 through GUI input, despite working screen capture and responsive manual mouse input. Full-game verification remains open; this is separate from display sizing.

## 2026-10-04 gripper open inner clearance

- Applied user-selected 27.5 mm inner open clearance to CAD viewer and generated collision hulls. Direct PyBullet closest-surface query verifies 27.500 mm; closed CAD vertices, fixed body and tool frame/length are unchanged.
- Tapered surfaces differ from projected AABB gaps. `open_inner_surface_gap_m` describes the requested inner clearance; `open_width_m` remains the projected articulation envelope gap. This setting is user-selected, not a new hardware measurement.
- Actual capture cases and contact tests passed; corrected geometry-contract probe gate passes 9 cases after the preceding 39-pass / 1-fixture-failure gate. Viewer parity validation passes. Physical closed stroke/force remain unverified.

## 2026-10-04 adjacent capture orientation

- Actual e7→e8 rook capture rejected while descending over the advisor because the open gripper approached within 0.74 mm of the attacking rook (required margin 2.00 mm). Pick now chooses among existing alternate-yaw IK candidates using full descent preflight, rather than hover clearance alone. Neighbour collision checks remain active.
- Exact-board PyBullet capture and all-orientations-blocked rejection verified; focused capture/Phase 3/Home recovery gate passes 27 cases. Arbitrary positions can still be unreachable and must reject; this is not an all-moves or physical safety guarantee.

## 2026-10-04 elephant capture follow-up

- Reproduced a premature `PAYLOAD_UNSAFE_WORLD_NOT_SETTLED` rejection on the recorded g9→e7 / h2e2 board: an unrelated knight was still accumulating resting samples at the fixed 60-step limit. Payload clearance now waits up to the existing configured settling budget and still rejects persistent movement.
- Fixed independent borrowed-world polling ownership: the virtual bridge observes the runtime world without rewinding joints or stepping physics. Physical mirrors are unchanged.
- 29 focused tests passed, including actual pre-commit capture physics, persistent-disturbance rejection and retained GUI errors. Exact cause of the original live failure remains unconfirmed because its expired error was not logged; subsequent failures are now retained and logged.
- GUI checkpoint replay then confirmed `SERVICE_UNSAFE_WORLD_NOT_SETTLED` after victim disposal/retreat. Added the configured bounded settling wait before SERVICE_SAFE evaluation; expanded gate passes 31 cases, including Home and Service Safe starting poses and rejection of persistent disturbance.

## 2026-10-05 visual donor 652af26 (not in integrated source)

- OPEN P1 in new manual pick/place: legacy robot wrappers allow code 112 through, and test runner ignores execution failure. Mocked probe continues through seven failed MoveCart calls and three gripper calls.
- The donor's post-motion verification/retry gap is addressed in the current integrated path by a durable pending-test receipt and explicit V reconciliation. The new path has only static source checks so far; runtime fault-injection acceptance remains open.
- Do not replace integrated read-only startup or canonical frame/mapping with donor legacy startup/Tool 0 User 1 assumptions. Detailed review: `docs/VISUAL_LATEST_REVIEW_20261005.md`.

## 2026-10-05 cross-feature audit

- RESOLVED: game-only reset/rollback incorrectly demanded physical camera verification. Physical mock gates remain required. New game also discards stale SPACE rollback state from the preceding match.
- OPEN: fresh broad unit run has one shortened-tool reachability assertion failure; selected viewer Node tests have three failures (picker boundary, fixed coordinate expectation, tool-status expectation). All four reproduce on clean 7d8c5de; no collision parameters were relaxed to hide them.
- VERIFIED within scope: R1–R4 + actual capture + live polling + undo/reset keep piece cells and taught pose coherent; startup/cleanup and affected logging/game regression pass. This is not all-route or physical-hardware verification.
- Evidence: `docs/CROSS_FEATURE_AUDIT_20261005.md`.

## 2026-10-05 R1–R4 UI review

- VERIFIED: UI applies translated and rotated four-point poses to world/provider/twin/backend. Shifted version 2 passes 90/90 local cell trajectories; one actual simulated pawn move inspected before reconciliation succeeds. This does not establish all routes or hardware safety.
- RESOLVED UI ambiguity: H controls are disabled in four-point mode because backend preserves H and legacy placement apply is disabled. Editing H separately in this mode remains unsupported.
- OPEN: four-point apply is runtime-only; persistent save is not implemented by this button. Full 90-cell validation took roughly eight minutes with no per-cell progress. Existing `test_viewer_single_motion_authority.mjs` expects old tool-status metadata and fails on clean 7d8c5de too.
- OBSERVED during the long validation probe: one stale joint telemetry warning followed by recovery one second later. End-of-run placement and bridge state are consistent; investigate validation-time polling/freshness before treating the warning as a persistent device fault. Raw session events are preserved in the audit report artifacts.
- Evidence: `docs/R1_R4_SIMULATION_AUDIT_20261005.md`.

## 2026-10-04 simulated captures

- Implemented victim-first disposal using actual collision-checked PyBullet pick/place, followed by attacker movement and game commit. The scene contains provisional board-relative capture slots on the simulated floor. Missing/full/unreachable areas reject before picking; a blocked landing preserves the payload and stops the game without committing FEN.
- Verified the recorded Xe h0→h7 / UCCI h9h2 capture before world reconciliation; capture/placement cannot be hidden by teleporting to the expected square. Physical visual capture still uses R_Trash and has not been exercised here.
- OPEN: a partial capture requires reconciliation/reset, not a blind retry. Collision-free disposal routes for arbitrary placements are not guaranteed. Configure scene slots appropriately; neither the provisional area nor simulation thresholds establish physical calibration.

## 2026-10-04 offline AI approach

- RESOLVED for the reproduced first reply `h7e7`: the lifted joint interpolation swept within 1.37 mm of red_rook_0, below the unchanged 2.00 mm guard margin. SERVICE_SAFE fallback previously ran only for a J5 branch flip; it now also handles collision rejections without that flip, with every segment still validated.
- Actual PyBullet pick/place and pre-commit destination verification pass; blocking the service route stops the move without changing FEN/turn. Final targeted gate: 14 passed, exit 0. The older collision entries below are historical and do not establish current all-route coverage.
- OPEN: collision-free routes for every board placement and every legal chess move are not established. Virtual captures now have a checked disposal sequence as documented above; physical hardware remains unverified.

## 2026-09-29 camera twin remaining verification

- Full camera recognition has been exercised with synthetic quality-approved boards, but not verified against a live physical board. Camera quality and extrinsic calibration remain commissioning gates.
- Current yaw-0 virtual black-cannon approach is blocked by the active collision guard at a gripper/base penetration of 0.18 mm. Keep rejection; plan and verify a collision-free route before enabling this move.
- Re-scan infers the next turn only from one legal board transition. Multiple changes require operator confirmation with `1` (Red) or `2` (Black) before play resumes; an image alone cannot restore the exact move count in FEN.
- Whole `tests/unit` regression remains red/incomplete on this base. Historical yaw-90 fixtures require separate rebaselining against the current yaw-0 scene. Focused camera/Game/Twin tests are recorded in `docs/CAMERA_GAME_TWIN_SYNC_2026-09-29.md`.

## 2026-09-26 current collision milestone

- **OPEN - physical grip:** the declared closed CAD jaws remain roughly 2-7 mm from the nominal 22.5 mm rook in direct PyBullet queries. Simulator grasp now fails closed with NO_JAW_CONTACT; actual stroke, alignment, and force need measurement before a verified pick can be enabled.
- **VERIFIED — simulated static endpoints only:** the 90/90 and 18/18 acceptance-marked tests solve IK and query collision at individual poses. They do not test grasp contact, full trajectories, or physical FR3 safety.
- **VERIFIED — carried payload pairs:** the guard now checks payload-floor and payload-robot-link pairs in addition to payload-board and payload-piece pairs. Direct PyBullet penetrating fixtures must be rejected.
- **VERIFIED — direct PyBullet collision contacts:** Independent test suite test_direct_pybullet_contact_clearance.py proves direct PyBullet contactDistance < 0 for board, outer rim, floor, arm Link 2, carried piece, and closing jaw travel (5.2 mm each along X) across all 19 fixed component boxes + 2 moving finger hulls (total 21 shapes across 4 bodies). The 19th component (viewer_adapter_collar) is explicitly verified in PyBullet.
- **VERIFIED — dangerous command invariance:** test_dangerous_command_invariance_and_web.py proves 100% invariance of joints, TCP, and gripper state on command rejection, with non-optimistic 3D web viewer telemetry contract.
- **OPEN — reachability seeds:** shared/cell_reachability_dataset.json is marked STALE/UNVALIDATED and records historical yaw 90°/150 mm data. Runtime strictly ignores it.
- **OPEN — route planner:** move_joint_with_lift_recovery contains a reactive 65 mm lift fallback. Preplanned collision-free corridors for all 8010 ordered routes remain to be proven.
- **OPEN — hardware:** no physical FR3 motion, calibration parity, or physical clearance has been verified on physical hardware.
- **OPEN - regression baseline:** nine board-placement / stale-dataset tests still fail under the active yaw 0 degree scene. The targeted collision suite passed, but the wider suite is not green.
---

> **Purpose:** Persistent tracking of bugs, blockers, and edge cases. Prevents agents from rediscovering solved bugs or re-investigating known characteristics.

---

## B01 — `try_grasp` Target Piece Filtering Contract Mismatch
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/physics/world.py`, `src/simulation/runtime.py`
* **Evidence:** Previously, `try_grasp()` evaluated all candidates blindly. If adjacent pieces were nearby, ambiguous candidate selection occurred.
* **Fix Summary:** Updated `try_grasp(target_piece_id=...)` to strictly filter candidates to the requested piece ID, returning `GraspStatus.AMBIGUOUS` on mismatch.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_01_try_grasp_target_matching`, `test_02_try_grasp_target_mismatch_rejection`
* **Last Verified HEAD:** 7ce5e71

---

## B02 — Missing Typed `PlaceResult` and `GraspStatus.PARTIAL` Contract
* **Status:** FIXED
* **Severity:** HIGH
* **Affected Files:** `src/simulation/physics/state.py`, `src/simulation/runtime.py`
* **Evidence:** `place_piece()` returned raw booleans/dicts lacking unified typed attribute access (`.success`, `.status`, `.piece_id`).
* **Fix Summary:** Created `PlaceResult` dataclass with dictionary/boolean fallback protocol matching `PickResult`.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_03_pick_result_fail_fast_contract`
* **Last Verified HEAD:** 7ce5e71

---

## B03 — Articulated PyBullet FR3 Kinematic Synchronization
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/hardware/backends/base.py`, `src/simulation/physics/world.py`
* **Evidence:** `RobotStateSnapshot` lacked `.joints_rad` property, causing PyBullet link synchronization listeners to crash or leave the simulated arm as a stale ghost pose.
* **Fix Summary:** Added `@property def joints_rad` to `RobotStateSnapshot` and implemented `get_robot_joint_positions()` on `VirtualPhysicalWorld`.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_04_pybullet_fr3_tracking_interpolated`
* **Last Verified HEAD:** 7ce5e71

---

## B04 — Validation vs Motion Mutual Exclusion Atomicity & Single Authority
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/runtime.py`
* **Evidence:** Previously, `MOVE_JOINT` bypassed `RuntimeOperationState`, validation checked `is_busy` before acquiring `VALIDATING_*`, and re-entrant acquisition in `acquire_operation_state` yielded inside `with self._operation_lock:`, holding the lock across nested long-running operations and blocking concurrent callers. Furthermore, runtime motion wrappers acquired `_command_lock` before `RuntimeOperationState`, allowing competing commands to silently queue rather than failing fast.
* **Fix Summary:** Defined `RuntimeOperationBusy(RuntimeError)`, implemented authoritative `runtime_move_joint()`, routed `_handle_client_command(MOVE_JOINT)` and `RESET` through runtime wrappers, wrapped `validate_board_placement` and `validate_full_board_routes` in atomic outer `acquire_operation_state()`, resolved re-entrant lock yielding bug by strictly releasing `_operation_lock` before `yield`, implemented `_operation_depth` tracking, eliminated redundant inner validation acquisitions, inverted lock acquisition order across all runtime motion and service wrappers to prioritize `RuntimeOperationState` admission over `_command_lock`, enforced non-reentrancy on physical motion states (`MOTION`, `SERVICE_MOVE`), and added test hooks proving immediate fail-fast with `MOTION_REJECTED_BUSY` (no silent queueing).
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests` (`test_05_runtime_operation_state_transitions`, `test_06_runtime_operation_state_mutual_exclusion`, `test_a1_move_joint_command_uses_runtime_authority`, `test_a2_true_concurrent_acquisition`, `test_a3_1_real_validator_rejects_move_joint_before_release`, `test_a3_2_timing_handshake_proof`, `test_a3_3_full_route_validator_rejects_move_joint`, `test_a3_validation_vs_move_joint_race`, `test_a4_move_joint_owns_first`, `test_a5_validation_flag_consistency`, `test_a6_exception_cleanup`, `test_a6_nested_exception_cleanup`, `test_a7_service_jog_vs_validation`, `test_lock_not_held_across_yield`, `test_a2_1_move_joint_vs_move_joint_no_queue`, `test_a2_2_timing_handshake_proof`, `test_a2_3_move_joint_vs_jog`, `test_a2_4_service_move_vs_move_joint`, `test_a2_5_pick_vs_move_joint`, `test_a2_6_place_vs_jog`, `test_a2_7_3stage_trajectory_vs_move_joint`)
* **Last Verified Functional HEAD:** 5af7e3442519502c3028b476da126642cc8fa864

---

## B05 — Duplicate 3D Ruler Telemetry Update Listener
* **Status:** FIXED
* **Severity:** MEDIUM
* **Affected Files:** `robot-3d-viewer/ruler.mjs`, `robot-3d-viewer/main.mjs`
* **Evidence:** Duplicate `updateBoardPlacement` listener caused race conditions and out-of-sync distance measurements on dynamic board shifts.
* **Fix Summary:** Centralized 3D ruler update into a single authoritative `placement_state` telemetry handler.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_16_ruler_single_authoritative_update`, `tests/unit/test_viewer_coordinate_ruler.mjs`
* **Last Verified HEAD:** 7ce5e71

---

## B06 — Wildcard Protection in Collision Guard
* **Status:** FIXED
* **Severity:** HIGH
* **Affected Files:** `src/simulation/physics/collision_guard.py`, `src/simulation/virtual_fr3_backend.py`
* **Evidence:** Passing `allowed_grasp_piece_id="*"` effectively bypassed all piece collision checking.
* **Fix Summary:** Enforced explicit validation rejecting wildcard strings (`*`) with `ValueError`.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_07_collision_guard_explicit_candidate_no_wildcard`
* **Last Verified HEAD:** 7ce5e71

---

## B07 — Swept Volume Collision When Robot Arm Obstructs Relocation
* **Status:** FIXED
* **Severity:** HIGH
* **Affected Files:** `src/simulation/physics/world.py`, `src/simulation/runtime.py`
* **Evidence:** Changing board placement while robot arm was parked low over board caused unmonitored visual clipping / physical overlap.
* **Fix Summary:** Implemented `check_board_swept_volume_collision()` interpolating bounding boxes against arm links. Rejects relocation with `BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR` if path is blocked.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_11_swept_volume_collision_arm_obstruction`, `test_12_swept_volume_collision_clear_path`
* **Last Verified HEAD:** 7ce5e71

---

## B08 — Validation Cell Loop Indentation Scope
* **Status:** FIXED
* **Severity:** HIGH
* **Affected Files:** `src/simulation/runtime.py`
* **Evidence:** `if cell_passed:` in `validate_board_placement()` and `passed_routes += 1` in `validate_full_board_routes()` were indented outside inner column/route loops, leading to inaccurate failure counts.
* **Fix Summary:** Corrected block indentation so each cell and route increments and records failures within its respective loop.
* **Regression Test:** `tests/unit/test_phase3_dynamic_board_placement.py::DynamicBoardPlacementTests::test_recommended_placement_90_cells_pass`, `test_full_board_routes_validation`
* **Last Verified HEAD:** 7ce5e71

---

## B09 — `SERVICE_SAFE` Physical Safety Predicate & Board Relocation Collision Margin
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/physics/state.py`, `src/simulation/physics/world.py`, `src/simulation/runtime.py`, `src/simulation/virtual_fr3_backend.py`
* **Evidence:** Previously, Candidate 1 (`[0, -25, 40, -105, -90, 0]`) penetrated the board by 22.3mm on forward shifts due to the 218mm tool flange-to-TCP offset; Candidate 2 (`HOME: [0, -45, 90, -45, -90, 0]`) had only 14.8mm clearance to link 4 and penetrated by 15.2mm upon a 30mm board elevation; `is_service_safe()` was a simple joint angle threshold check lacking physical grounding (connection, idle, gripper state, attached pieces, and physical clearance); and `set_board_placement` did not enforce continuous 3D swept volume safety margins ($\ge 5.0\text{ mm}$) or authoritative readiness token consumption.
* **Fix Summary:** Audited both candidates and derived authoritative Upright Retracted configuration `[0.0, -70.0, 60.0, -80.0, -90.0, 0.0]°` ($> 129.9\text{ mm}$ moving link clearance, $> 216.3\text{ mm}$ gripper clearance, condition number $17.67$, joint margin $85.0^\circ$ across full $[-20, 60]\text{ mm}$ shift and $[-10, 30]\text{ mm}$ height envelope); implemented comprehensive `ServiceSafetyReport` and physical predicate `evaluate_service_safety()`; implemented dense 3D interpolated swept volume collision check `check_board_swept_volume_collision()` with positive clearance margin $\ge 5.0\text{ mm}$ and detailed diagnostics; implemented strict `BOARD_ADJUSTMENT_READY` lifecycle token invalidated by any motion/jogging/relocation; and enforced 100% state invariance on board relocation rejection.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests::test_b1_service_safe_physical_predicate_clear` through `test_b11_jog_invalidates_service_safe`, `test_08_is_service_safe_predicate`, `test_09_go_service_safe_motion`, `test_10_prepare_board_adjustment_flow`, `test_12_swept_volume_collision_clear_path`
* **Last Verified Functional HEAD:** 2b50063d446717abff5d89f44e219d270e369230

---

## B10 — Pass B Corrective: SERVICE_SAFE Physical Predicate, Settling State & Swept Exclusion Volume Gaps
* **Status:** FIXED
* **Severity:** HIGH
* **Affected Files:** `src/simulation/virtual_fr3_backend.py`, `src/simulation/physics/world.py`, `src/simulation/runtime.py`, `tests/unit/test_phase3_final_master.py`, `tests/unit/test_phase3_isolation_and_fail_fast.py`, `tests/unit/test_phase3_dynamic_board_placement.py`
* **Evidence:** 
  1. `backend.is_connected` was inspected as a boolean object rather than invoked as a method (`is_connected()`).
  2. `PiecePhysicalState.SETTLING` was missing from the transient piece state check in `evaluate_service_safety()`, allowing settling pieces to pass service safety.
  3. `set_board_placement()` did not strictly enforce the `_board_adjustment_ready` token and fresh physical `evaluate_service_safety()` check before execution.
  4. Missing behavioral test validating negative board lowering into an obstructing arm/gripper with 100% state invariance upon rejection.
  5. Service exclusion volume used static coordinates rather than canonical geometric derivations from `self.geom` and `self.placement_state`, and did not query all moving arm links (0..5) and gripper proxies via PyBullet collision detection.
* **Fix Summary:**
  1. Updated `virtual_fr3_backend.py` and `runtime.py` to strictly invoke `self.backend.is_connected()`.
  2. Included `PiecePhysicalState.SETTLING` alongside `FALLING` in `evaluate_service_safety()`.
  3. Added strict readiness token validation and fresh physical safety predicate check in `set_board_placement()`, with narrow `internal_reset: bool = False` bypass for reset routines, returning `BOARD_RELOCATION_REJECTED_NOT_READY` and `BOARD_RELOCATION_REJECTED_SERVICE_UNSAFE`.
  4. Added `test_bc7` and `test_bc8` using proven fixture configuration `[0.0, -60.0, 125.0, -135.0, -90.0, 0.0]°` with initial clearance $d_{\text{initial}} = 7.14\text{ mm} > 5.0\text{ mm}$ margin, verifying negative lowering collision triggers at step $k = 1 > 0$ with `BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR` and preserves 100% board, piece, and robot joint state invariance. Updated `test_bc9` to explicitly assert that TCP is $> 39\text{ mm}$ above the service exclusion ceiling while moving arm links encroaching the exclusion zone are detected and rejected.
  5. Implemented `check_service_exclusion_occupancy()` in `world.py` utilizing a temporary PyBullet collision shape box querying all FR3 moving links (0..5) and gripper proxies with deterministic cleanup. In `runtime.py`, dynamically computed bounding box dimensions from `self.geom.board_length_m`, `self.geom.board_width_m`, `self.geom.board_thickness_m`, `self.placement_state.board_height_offset_m`, `DEFAULT_SERVICE_XY_MARGIN_M` (0.030m), and `DEFAULT_SERVICE_VERTICAL_CLEARANCE_M` (0.050m).
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests` (`test_bc1_disconnected_backend_rejects_service_safe` through `test_bc12_supported_envelope_boundary_cases_remain_safe`)
* **Last Verified Functional HEAD:** 097490d1ce95ee3ea87f5caa4f2183b189dfeaf4

---

## B11 — Post-Operation Safe Retreat & Split Physical Manipulation from Service Safety (Pass C & Pass C Corrective)
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/physics/state.py`, `src/simulation/physics/collision_guard.py`, `src/simulation/virtual_fr3_backend.py`, `src/simulation/runtime.py`, `tests/unit/test_phase3_final_master.py`
* **Evidence:**
  1. Previously, `place_piece()` returned `success = True` if piece was released, even when post-release lift or service retreat failed with collision/error (`LIFT_FAILED_AFTER_RELEASE`), violating the physical safety contract.
  2. `pick_piece()` did not track trajectory stages (`PREPOSITION` -> `DESCEND` -> `GRASP` -> `LIFT` -> `PAYLOAD_CLEAR` -> `COMPLETE`) or ensure physical payload clearance over the board.
  3. No distinct `PayloadSafetyReport` existed to evaluate safe post-pick holding without demanding `SERVICE_SAFE` (which requires an empty gripper).
  4. Post-release retreat stages (`POST_RELEASE_LIFT` -> `CLEAR_BOARD` -> `SERVICE_RETREAT`) were not monitored in `place_piece()`, and were entirely bypassed in `execute_3stage_trajectory()` / WebSocket `EXECUTE_3STAGE`, leaving the robot at `LAND` or low altitude before reporting `success = True`.
  5. `place_piece()` set `piece_placed = True` without physical position and state verification after release and settle.
  6. `test_c9_retreat_collision` previously used a mock rather than a real physical PyBullet collision fixture.
  7. `execute_3stage_trajectory(..., grasp_piece=True)` on an empty source cell silently fell back to an arm-only transit (`should_grasp = False`) instead of rejecting fast at `PRECHECK`.
  8. `CLEAR_BOARD` motion failure in `_execute_3stage_trajectory_impl()` did not assign fallback `move_joint()` to `ok_clear` or check `ok_clear`, silently falling through to `SERVICE_RETREAT`.
  9. `_execute_3stage_trajectory_impl()` did not verify `try_grasp()` outcome or verify that the requested piece was attached before proceeding to `LIFT`.
  10. `goToCell()` / `EXECUTE_3STAGE` previously inferred grasp intention from board occupancy when `grasp_piece` was missing or `None` (`should_grasp = piece_at_src is not None and piece_at_dst is None`), causing unintended manipulation during diagnostic cell navigation.
* **Fix Summary:**
  1. Defined `PayloadSafetyReport` dataclass and `evaluate_payload_clearance()` runtime predicate ($z_{\text{piece}} > z_{\text{board}} + 20\text{ mm}$).
  2. Extended `PickResult` and `PlaceResult` with typed physical/safety outcome fields, recovery flags, and report objects while preserving dictionary/boolean fallback.
  3. Fixed collision guard palm penetration checks during grasp descent to specifically ignore currently carried pieces, preventing false collisions during retreat.
  4. Decoupled manipulation outcome from robot safety: if release succeeds but retreat fails, `success = False`, `piece_placed = True`, `piece_released = True`, `service_safe = False`, and `requires_recovery = True`.
  5. Enforced that post-operation unsafe state keeps board adjustment strictly locked (`is_board_adjustment_ready == False`).
  6. Integrated full Pass C retreat pipeline (`POST_RELEASE_LIFT` -> `CLEAR_BOARD` -> `SERVICE_RETREAT` -> `evaluate_service_safety()`) into `execute_3stage_trajectory()` and WebSocket `EXECUTE_3STAGE`, supporting both pick & place and arm-only transit without leaving the arm in an unretreated state.
  7. Implemented physical placement verification: verifies piece is in `ON_BOARD` or `RESTING` physical state, within $25\text{ mm}$ of target cell intersection and within $15\text{ mm}$ of board surface altitude. Returns `status = "PIECE_PLACEMENT_UNVERIFIED"` if piece tumbles or is lost.
  8. Converted `test_c9_retreat_collision` into a true physical PyBullet collision fixture with a zero-mass obstacle piece `black_cannon_0` at `[-0.434, -0.102, 0.227]`, halting safely with `PLACE_SERVICE_RETREAT_FAILED`, `requires_recovery = True`, `service_safe = False`.
  9. Enforced explicit grasp precheck in `execute_3stage_trajectory()`: if `grasp_piece is True` and `piece_at_src is None`, immediately returns `status = "PRECHECK_NO_SOURCE_PIECE"`, `failed_stage = "PRECHECK"`. If `piece_at_dst is not None`, returns `status = "PRECHECK_DESTINATION_OCCUPIED"`.
  10. Enforced strict fail-fast check on `CLEAR_BOARD`: validates both Cartesian and joint IK fallback, halting with `status = "CLEAR_BOARD_FAILED"`, `failed_stage = "CLEAR_BOARD"`, `requires_recovery = True`, `service_safe = False`.
  11. Added explicit `GRASP` stage verification in `_execute_3stage_trajectory_impl()`, checking `try_grasp` and physical attachment before `LIFT`, halting with `status = "GRASP_FAILED"`, `failed_stage = "GRASP"`, `requires_recovery = True`.
  12. Enforced explicit non-manipulation default contract: `goToCell()` in `robot-3d-viewer/main.mjs` explicitly dispatches `grasp_piece: false`. In `runtime.py`, `_handle_client_command` and trajectory implementations strictly default missing/None grasp flags to `False` (`should_grasp = False`), never guessing grasp intention based on board occupancy. Added regression tests `test_c19_execute_3stage_omitted_grasp_flag_defaults_to_arm_only` (verifying piece unmoved $< 1\text{ mm}$, $d_p < 0.025$, `piece_placed=False`) and `test_c20_execute_3stage_explicit_grasp_executes_pick_and_place`.
  13. Added `test_c13` through `test_c20`.
* **Regression Test:** `tests/unit/test_phase3_final_master.py::Phase3FinalMasterTests` (`test_c1_normal_pick_retreat` through `test_c20_execute_3stage_explicit_grasp_executes_pick_and_place`)
* **Last Verified Functional HEAD:** 88dc791ee8b409d6895746557264382f9957b067

---

## B12 — Phase 3 Board Orientation 90° Geometry Redesign (G90)
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/placement.py`, `src/simulation/physics/transforms.py`, `src/simulation/physics/piece.py`, `src/simulation/physics/world.py`, `src/simulation/runtime.py`, `robot-3d-viewer/board.mjs`, `shared/cell_reachability_dataset.json`, `shared/virtual_fr3_scene.json`
* **Evidence:**
  1. Under the nominal 0° orientation, the 10 rows (360 mm span) were oriented along $-X_{\text{robot}}$ and 9 columns (320 mm span) laterally.
  2. Near-side center cells ((4, 0) and (5, 0)) forced link 3 into collision with link 1 during LAND descent at nominal $d = 0$ (clearance $< 0.5\text{ mm}$ self-collision limit).
  3. Positive forward shifts ($d \ge 15\text{ mm}$) to clear link collision pushed far-side row 9 cells close to the robot kinematic reach limit ($650\text{ mm}$), leaving inadequate safety margins.
* **Fix Summary:**
  1. Rotated the Xiangqi board authoritatively by $+90.0^\circ$ around $+Z_{\text{robot}}$ ($R = \begin{bmatrix}-1&0&0\\0&-1&0\\0&0&1\end{bmatrix}$, quat `[0.0, 0.0, 1.0, 0.0]`).
  2. The 9-column axis (320 mm playable span) now maps along $-X_{\text{robot}}$, and the 10-row axis (360 mm playable span) maps along $-Y_{\text{robot}}$, substantially reducing the required reach depth along the arm extension axis.
  3. Conducted exhaustive candidate placement evaluation across $(d, H, Z)$ combinations and selected $d = 15.0\text{ mm}, H = 40.0\text{ mm}, Z = 0.0\text{ mm}$.
  4. Selected placement achieves:
     - Kinematic reach margin: $+24.9\text{ mm}$ ($625.1\text{ mm} < 650.0\text{ mm}$)
     - Collision clearance: $7.69\text{ mm}$ (link 1 <-> link 3, safely above $0.5\text{ mm}$ margin)
     - Jacobian condition number: $21.79$ (well conditioned across all 90 cells, $< 40.0$)
     - Joint limit margin: $9.23^\circ$ (above $5.0^\circ$ limit)
  5. Regenerated `shared/cell_reachability_dataset.json` with 90/90 cells solved and 0 collisions.
  6. Updated physics collision bodies, piece placement, PyBullet world relocation, runtime coordinate transforms, viewer 3D board geometry, canvas texture, and dimension tape.
  7. Implemented dedicated unit test suite G90-01 through G90-25 in `tests/unit/test_phase3_board_orientation_90.py`.
* **Regression Test:** `tests/unit/test_phase3_board_orientation_90.py` (25/25 tests), `tests/unit/test_phase3_dynamic_board_placement.py` (13/13 tests)
* **Last Verified Functional HEAD:** b0027e744ccacc3e4dd21f6150271c0fc6f7c2cf

---

## B13 — Phase 3 90° Board Migration Corrective: Browser Viewer Boot Recovery & Coordinate Contract Audit
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `robot-3d-viewer/board.mjs`, `robot-3d-viewer/main.mjs`, `robot-3d-viewer/ruler.mjs`, `tests/unit/test_viewer_canvas_api.mjs`, `tests/unit/test_viewer_coordinate_contract.mjs`, `tests/unit/test_viewer_browser_smoke.mjs`
* **Evidence:**
  1. Fatal boot defect in `createBoardTexture()`: 4 calls to `ctx.lineTo(x)` were missing the `y` parameter in `board.mjs`, causing an unhandled `TypeError` during startup and aborting `initApp()` before WebGL/Three.js rendering or model loading started.
  2. Stale 0° orientation geometry remained in `robot-3d-viewer/main.mjs`: `goToCell(row, col)` computed `robX = -0.180 - d/1000 - row*0.04`, `robY = -0.160 + col*0.04`; `computeGeometricPrecheck()` hardcoded $X_{\text{far}} = 540.0 + d$, $Y_{\text{far}} = 160.0$; and `updateGeometricPrecheckUI()` reported 0° extrema (180, 540, 155, 565 mm).
  3. Non-standardized `boardPointToXYZ(col, row)` parameter ordering inverted arguments vs backend `BoardCell(row, col)`, risking column/row transposition.
  4. Stale 0° markers in `robot-3d-viewer/ruler.mjs`: `specialZMarkers` listed H0: 180mm, H9: 540mm; and board edges hit proxies used length along Z and width along X.
* **Fix Summary:**
  1. Fixed `createBoardTexture()` Canvas API path calls by supplying required `y` arguments to `ctx.lineTo(...)`. Verified across all 45 Canvas path operations in `test_viewer_canvas_api.mjs`.
  2. Standardized `boardPointToXYZ(row, col)` signature and object overload `boardPointToXYZ({ row, col })`, deriving coordinates strictly from canonical 90° orientation math ($u = (col - 4) \times 0.040$, $v = (row - 4.5) \times 0.040$, $X_{\text{world}} = v$, $Z_{\text{world}} = 0.360 + d/1000 + u$).
  3. Updated piece construction (`buildPieces`) and piece relocation (`movePieceTo`) to consume standardized `(row, col)` coordinates.
  4. Refactored `goToCell()` and `applyAuthoritativeBoardPlacement()` in `main.mjs` with canonical 90° formulas ($robX = -0.360 - d/1000 - u$, $robY = -v$, $robZ = 0.0105 + z_{\text{off}}/1000$), standardized label formatting `(Hàng row, Cột col)`, and atomic `updateGeometricPrecheckUI()` dispatch.
  5. Refactored `computeGeometricPrecheck()` with 90° extrema ($X_{\text{far}} = 520.0 + d$, $Y_{\text{far}} = 180.0$) and updated precheck readouts (Col 0: 200 mm, Col 8: 520 mm, Near edge: 176.5 mm, Center: 360 mm, Far edge: 543.5 mm).
  6. Updated `ruler.mjs` special markers (Cột 0: 200mm, Tâm: 360mm, Cột 8: 520mm) and 4-edge hit proxies (Near: 176.5mm, Far: 543.5mm along Z; Left: -205mm, Right: +205mm along X).
  7. Created `test_viewer_coordinate_contract.mjs` verifying 90-cell parity, 32-piece placement, asymmetric cell (2, 7), and dynamic shift invariance.
  8. Created automated headless Chrome CDP smoke test `test_viewer_browser_smoke.mjs` verifying V90-01 through V90-05.
* **Regression Test:** `tests/unit/test_viewer_canvas_api.mjs`, `tests/unit/test_viewer_coordinate_contract.mjs`, `tests/unit/test_viewer_browser_smoke.mjs`
* **Last Verified Functional HEAD:** 1196f90d1f4b8cf65f02bc0f7e4dfbf6b3fcb590

---

## B14 — Phase 3 90° Coordinate Semantics & Backend Contract Corrective (S90)
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/placement.py`, `src/simulation/physics/transforms.py`, `src/simulation/physics/piece.py`, `src/simulation/runtime.py`, `robot-3d-viewer/board.mjs`, `robot-3d-viewer/main.mjs`, `robot-3d-viewer/index.html`, `tests/unit/test_phase3_coordinate_semantics_contract.py`, `tests/unit/test_viewer_coordinate_contract.mjs`
* **Evidence:**
  1. `runtime.py` had conflicting methods: `cell_to_robot_xyz(col, row)` vs `cell_to_robot_xyz_m(row, col)`, causing confusion and transposition bugs across callers.
  2. `robot_xyz_to_nearest_cell` returned `(c, r, dist)`, which forced all call sites across `runtime.py` and test files to manually perform a tuple swap `r, c = c, r`.
  3. UI DOM IDs `#readoutRow0Dist` and `#readoutRow9Dist` and select dropdown options still described `row 0 = near robot` and `row 9 = far robot`, which contradicts the canonical 90° rotation where column 0 is the near side and column 8 is the far side.
  4. Frontend `boardPointToXYZ` hardcoded axis swaps without directly consuming authoritative `BoardPose` (`TRobotFromBoard`, `board_yaw_deg`).
* **Fix Summary:**
  1. Introduced frozen dataclass `BoardCell` with bounds validation $[0..9] \times [0..8]$, sequence indexing, and unpackability.
  2. Standardized public API signature everywhere strictly as `(row, col)` with $row \in [0, 9]$ (0 = Black home side, 9 = Red home side - game meaning only) and $col \in [0, 8]$ (col 0 = near side of robot, col 8 = far side of robot).
  3. Aligned `robot_xyz_to_nearest_cell` to return `(nearest_r, nearest_c, dist_m)` in canonical order, eliminating manual swaps across `runtime.py` and tests.
  4. Added `T_robot_from_board` (4x4 SE(3) matrix) to `BoardPlacementState.to_dict()` and aliased `to_telemetry_dict`.
  5. Updated `robot-3d-viewer/board.mjs` (`boardPointToXYZ` and `setScenePlacement`) to directly consume authoritative `T_robot_from_board` and `board_yaw_deg`, eliminating hardcoded axis swaps.
  6. Renamed UI elements to `#readoutNearGridDepth` and `#readoutFarGridDepth`, and updated selection dropdowns to honest base/depth labels.
  7. Added comprehensive regression suite `tests/unit/test_phase3_coordinate_semantics_contract.py` (11/11 tests PASSED) and expanded `tests/unit/test_viewer_coordinate_contract.mjs` (8/8 tests PASSED).
* **Regression Test:** `tests/unit/test_phase3_coordinate_semantics_contract.py`, `tests/unit/test_viewer_coordinate_contract.mjs`, `tests/unit/test_phase3_board_orientation_90.py`, `tests/unit/test_phase3_final_master.py`, `tests/unit/test_viewer_browser_smoke.mjs`
* **Last Verified Functional HEAD:** 953b77d

---

## B15 — Full Chained Route Fail-Fast Integrity, Coverage Telemetry & Authoritative Placement Extrema (G90 Final Corrective)
* **Status:** FIXED
* **Severity:** BLOCKER
* **Affected Files:** `src/simulation/runtime.py`, `src/simulation/placement.py`, `robot-3d-viewer/main.mjs`, `robot-3d-viewer/index.html`, `tests/unit/test_phase3_final_g90_corrective.py`
* **Evidence:**
  1. `CLEAR_BOARD` Fail-Fast Violation: In `VirtualXiangqiSimulation.validate_full_board_routes()` (`src/simulation/runtime.py`), if `CLEAR_BOARD` stage failed, the validator silently fell back to `q_curr = q_after_post_lift` and proceeded to attempt `SERVICE_RETREAT`. If retreat succeeded, `passed_routes` was incremented, masking clear-board failures.
  2. Missing Coverage Telemetry & Dual Modes: Full board route validation only tested an ad-hoc 20-route sample without reporting validation mode (`SAMPLED` vs `EXHAUSTIVE`), total possible ordered routes (8010), coverage fraction, or enforcing the invariant `passed_routes + failed_routes == tested_routes`.
  3. Hardcoded Extrema in Viewer Diagnostics: Frontend `robot-3d-viewer/main.mjs` hardcoded extrema formulas (`520 + d`, `180`, `200 + d`, `176.5 + d`, `543.5 + d`) in `computeGeometricPrecheck()` instead of dynamically evaluating transformed `BoardCells` and physical corners via authoritative `BoardPose`.
  4. Metric Wording Imprecision: The 625.1 mm reach metric (which is flange-to-base approach distance) was colloquially described as "Max TCP distance".
* **Fix Summary:**
  1. Enforced strict fail-fast in `validate_full_board_routes()`: if `CLEAR_BOARD` fails, the route fails immediately with `route_passed = False`, `failed_routes += 1`, `worst_route` records stage `"CLEAR_BOARD"`, and `SERVICE_RETREAT` is never evaluated or executed.
  2. Implemented dual validation modes: `SAMPLED` (`exhaustive=False`, status `FULL_BOARD_ROUTES_SAMPLE_SAFE`) and `EXHAUSTIVE` (`exhaustive=True`, status `FULL_BOARD_ROUTES_EXHAUSTIVE_SAFE`). Added explicit telemetry fields (`validation_mode`, `possible_ordered_routes` = 8010, `tested_routes`, `passed_routes`, `failed_routes`, `coverage_fraction`, `exhaustive`, `all_routes_safe`) and enforced accounting invariant `passed_routes + failed_routes == tested_routes`.
  3. Refactored `computeGeometricPrecheck()` in `robot-3d-viewer/main.mjs` and `compute_geometric_precheck()` in `src/simulation/placement.py` to evaluate all 90 cells and 4 board corners dynamically via authoritative `BoardPose` transformations, computing dynamic $d_{\text{max}}$, $H_{\text{max}}$, `near_grid_depth_mm`, and `far_grid_depth_mm`.
  4. Corrected metric wording in `index.html` and documentation: labeled 625.1 mm strictly as "Max flange approach distance" ($D_{\text{flange\_app}} = 625.1\text{ mm} < 650.0\text{ mm}$), distinct from TCP distance ($550.3\text{ mm}$).
  5. Implemented comprehensive test suite `tests/unit/test_phase3_final_g90_corrective.py` covering G90F-01 through G90F-14 (14/14 tests PASSED).
* **Regression Test:** `tests/unit/test_phase3_final_g90_corrective.py` (14/14 tests PASSED), all 7 Node.js viewer tests PASSED.
* **Last Verified Functional HEAD:** e8ac273

---

## I01 — Deprecated `WebSocketServerProtocol` Import in Telemetry Publisher
* **Status:** OPEN (Benign warning)
* **Severity:** LOW
* **Affected Files:** `src/hardware/telemetry_publisher.py`
* **Evidence:** Warning during pytest: `DeprecationWarning: websockets.server.WebSocketServerProtocol is deprecated`.
* **Action:** Low impact, server functions normally. Can be migrated to `websockets.asyncio.server.ServerConnection` in a future dependency cleanup.
* **Last Verified HEAD:** 12ce7330393a9014b0ad5e9013e845c8a3bf525e


## 2026-11-05 need-review capsule r2 — acceptance boundary

Current need-review30649c4 mode/session/exit code is retained in the new capsule; 105 targeted tests and actual bundled models/virtual world/Black subprocess/menu checks pass after Unicode relocation. Clean second-Windows-PC, entire UI/browser game and event-kit physical motion/driver/camera calibration remain unverified. Capsule does not close prior controller or broader regression gaps. Main host exit asks consent; Black client closes directly. See reports/need-review-capsule-20261105/REPORT.md.



## 2026-11-05 capsule — separate-machine and physical acceptance remain OPEN

Dated Windows x64 CPU ZIP is built; 66 scoped tests and isolated/Unicode-relocated actual bundle checks pass. Native dependencies are included and observed loading from the capsule. Fresh second-PC/clean-Windows, full UI game/browser session and event-kit camera/controller/loaded motion acceptance are not proven by these local checks. Existing physical blockers/calibration requirements remain; software packaging does not retire them. See reports/windows-capsule-20261105/REPORT.md. No physical calls or source motion-policy changes.


## 2026-11-05 final r2 capsule boundary

Current need-review robot-PvP code is integrated into final r2, locally verified with105tests plus actual bundled runtime/Unicode relocation/Black child/socket/menu probes. Clean second-PC and actual event-kit camera/robot acceptance remain OPEN; prior hardware and broader regression gaps are not cleared by packaging. No hardware access. See reports/final-capsule-r2-20261105/REPORT.md.


## 2026-11-07 final — obsolete quickstart superseded; hardware gaps unchanged

The 2026-09-09 quickstart did not match current final: it described calibration at piece centres, a camera-based dry-run/disconnected path, and unsafe motion-error/exit recovery assumptions. README is now the current user handbook and the old quickstart redirects to it. Guidance is traced to `005f95539531c32601232cdeeec3cca4185f32d9`; validation in this change is static documentation checking only. No runtime, controller recovery, post-interruption trajectory, loaded gripper, clean-PC or full-game acceptance claim. Existing OPEN findings and the separate capsule release boundary remain unchanged.
