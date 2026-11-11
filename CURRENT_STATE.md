## 2026-11-05 need-review publication checks

Robot PvP and the subsequent camera/stop/pick/exit fixes prepared on top of
origin/need-review@eb69457; current remote README and four redacted donor-report
files preserved. Only the feature delta is replayed, not the local snapshot
commit.115 focused tests PASS (103 parallel +12 serial), exit0,27.89s. Expanded
legacy checks:175 PASS +1 FAIL (viewer mock lacks viewer_command_context).
Broad non-slow run collected1123 parallel cases, showed failure markers, then
was interrupted at12%, exit1; failure origins UNKNOWN, not a full-suite PASS.
Existing launcher tests now explicitly mock consent/process exit, while actual
exit behavior remains subprocess-tested. No physical operation or app restart.
LAST_REVIEWED_HEAD unchanged. See reports/robot-pvp-20261102/PUBLISH_20261105.md.

## 2026-11-03 one-confirmation application exit

Window X, Ctrl+C and camera-q now ask once: Exit or Stay. Confirmed exit uses
process termination without waiting for SDK/stop proof/pending transactions or
atexit cleanup, including RECOVERY REQUIRED. Cancel leaves normal gameplay
unchanged. Existing journal records are retained; no robot/gripper command is
sent by this exit path.12 focused tests PASS (1 parallel +11 serial), exit0,
9.78s. Terminal SIGINT cancellation also verified. No hardware operation/restart/
merge. LAST_REVIEWED_HEAD unchanged.
Graph search/detect_changes unavailable (Transport closed); scoped source review
used instead. Report: reports/robot-pvp-20261102/EXIT_CONFIRMATION_20261103.md.

## 2026-11-03 session buttons / named pick errors — scoped candidate

SURRENDER accepted while busy/pick-paused, deferred until current work/stop/pending
reconciliation settles. NEW GAME keeps stop/pending/opening-camera gates; V and
Continue during ending do not replay a move. Successful-ACK stop timeouts can
settle via two new idle observations after workers finish, without another stop
command or enable; unknown/error/stale/gripper states stay blocked. Pick warning
now names expected FEN piece/role/square (user's captured target: Red Knight b9).
73 focused PASS; final stop39 and actual mock-UI14 PASS; no physical acceptance,
restart, merge or original-checkout edit. LAST_REVIEWED_HEAD unchanged. Report:
reports/robot-pvp-20261102/SESSION_BUTTONS_AND_PICK_NAMES_20261103.md.

## 2026-11-02 robot PvP startup camera pause — scoped fix

Runtime18:12:20 camera not yet fresh sets startup pause; later V verified32 but
left snapshot_continue_required true, so Red remained locked even after explicit
physical enable18:15:30. New-mode V/Continue now clears camera pause only after
exact verification, fresh baseline, no unresolved work and existing recovery
approval; persists checkpoint with rollback, respects newer stop requests.
51 tests PASS, exit0,17.27s; no motion/live mutation/restart. Existing process can
use its Continue path for this equal-board startup pause. Original checkout and
hardware gates unchanged. LAST_REVIEWED_HEAD unchanged. Report:
reports/robot-pvp-20261102/PVP_CAMERA_PAUSE.md.

## 2026-11-02 named missing YOLO cells — scoped verification

YOLO baseline diagnostic now names expected FEN piece + square + zero-based
row/col for missing occupancy, and explicitly labels unexpected occupied cells.
Names describe expected FEN, not proof that a physical piece is absent.30 tests
PASS (23parallel+7serial), exit0,18.38s; no acceptance/motion changes or restart.
See reports/robot-pvp-20261102/YOLO_BASELINE_31.md. LAST_REVIEWED_HEAD unchanged.

## 2026-11-02 YOLO31 versus verified ONNX32 — diagnostic clarity

Physical PvP runtime17:55:14 verifies Red16/Black16, diff0 in two fresh samples,
then legacy T1 baseline prints31. That is YOLO occupied-cell count, not ONNX/FEN.
Message now names source; camera.yolo_baseline logs raw boxes/occupied/expected
counts and differing cells. No perception threshold, baseline or motion change.
46 focused mock tests PASS, exit0,31.48s. Actual YOLO missing/mapping cause/cell
UNKNOWN from old logs; not a recognition fix. No hardware actuation or restart.
Report: reports/robot-pvp-20261102/YOLO_BASELINE_31.md. LAST_REVIEWED_HEAD unchanged.

## 2026-11-02 isolated two-human robot candidate

Separate worktree/branch codex/robot-pvp-20261102 on preserved local baseline
8a45223. New HUMAN_VS_HUMAN_ROBOT mode: host Red, hardware-free Black client,
localhost six-character room, both GUI moves through retained execution/journal.
No AI/auto-enable/HOME. Existing mouse-only PvP preserved. Focused116 PASS, exit0;
final new-mode30 PASS, exit0, in reports/robot-pvp-20261102/final-new-mode-tests.txt.
Actual main loop + fake motion + real room sockets verifies two durable turns.
Broad suite INTERRUPTED with failure markers; full result/causality UNKNOWN.
Physical/full-game acceptance NOT RUN; no merge/push or original-source changes.
LAST_REVIEWED_HEAD unchanged. Report: reports/robot-pvp-20261102/REPORT.md.

## 2026-11-02 camera confirmed / controller recovery blocker

Fresh read-only controller query at 16:30:45+07 returned [0,1,29]; successful
camera/FEN32 does not clear this real fault. Recovery UI/log now preserves the
hardware reason instead of claiming camera mismatch; left panel exposes a
transient diagnostic. Enable reports snapshot blocker before generic pending
board error. Existing stop/idle/recovery gates unchanged. Final focused checks:
78 PASS, exit0; exploratory legacy emergency tests FAIL with incomplete old
fixtures, no whole-suite pass claim. Physical recovery/full-game/UI acceptance
NOT VERIFIED. No controller actuation/reset or session deletion. New physical
PvP work paused for this issue. LAST_REVIEWED_HEAD unchanged.
See `reports/recovery-hardware-block-20261102/REPORT.md`.

## 2026-11-02 V retry / physical board XY display — scoped checks passed

V while pick-paused now uses guarded same-move retry instead of refreshing only
the baseline. Pre-motion camera rejection retains retry; post-motion failure
still requires recovery. Compact Continue and RvR retry ownership corrected.
Uncalibrated physical viewer now uses cached validated R1–R4 XY for cells/pieces/
mesh; display-only, no motion authority. Independent surface Z still unavailable
and visibly unverified. Attachment offset and post-release source snapback fixed.
TEST_EVIDENCE: 86 focused PASS, exit0; final 8 display tests rerun PASS; 3 Node
geometry suites and JS syntax PASS. Physical/full-game/browser verification NOT
RUN. No controller actuation, calibration edits, restart or failed-session clear.
Report: `reports/retry-board-display-20261102/REPORT.md`. LAST_REVIEWED_HEAD is not
advanced; no whole-checkout or physical VERIFIED_FIXED claim.

## 2026-11-02 board release pulse — 0.06s requested, hardware pending

Added separate RELEASE action/pulse (0.06s) for FR5Robot.place_at; OPEN_MAX stays
0.30s for initial opening and capture-bin release. Removed post-board-release
safe-gap close, which assumes fully open jaws. Twin maps RELEASE to release intent.
Mock checks via test_fast.ps1, 2 workers, targeted gripper event and legacy gates:
29 PASS, exit 0, runner 9.75s (Python 3.12.10, DRY_RUN=1/ROBOT_BACKEND=VIRTUAL).
Verified short DO0 pulse/both OFF, place order/no reclose and failure blocks lift.
No physical actuation or full regression; physical clearance and actual release
remain unverified. Restart app required. LAST_REVIEWED_HEAD not advanced.

## 2026-11-02 gripper rewire mapping — game release pending

Operator swapped control wires, then observed isolated DO1 closing at 14:12:53
and DO0 opening at 14:16:11. Both tests: empty jaws, measured stationary FR3,
controller [0,0,0], single 0.30s pulse, both OFF acknowledged; no arm commands.
Gameplay config now OPEN=DO0 / CLOSE=DO1; timings unchanged. Restart app to load
cached mapping. Focused mocked checks PASS: 33, exit 0, runner 6.93s. Actual game
release and original pre-rewire electrical cause remain unverified. See report
below. This is scoped verification; LAST_REVIEWED_HEAD is not advanced.

## 2026-11-02 gripper release investigation — historical pre-rewire state

Game log confirms RELEASE calls DO1/open_max for 0.30s, followed by lifting and
only then a 0.06s close-to-gap; camera reports missing destination cannon.
User removed the piece and explicitly authorized one observed isolated open
test. Fresh stationary PHYSICAL FR3/HOME telemetry and controller [0,0,0] checked.
At 13:52:38 +07:00, one DO1 ON request and both final OFF requests returned 0;
operator observed no motor sound or jaw motion. No arm/mode/enable/reset commands.
Electrical output/driver/mechanical cause remains UNKNOWN; no production or
calibration fix claimed. Four mock diagnostic tests PASS, exit 0.
Evidence: `reports/gripper-release-20261102/REPORT.md`.

## 2026-11-02 PvP functional comparison — no integration

Remote tips still player-vs-player 75c1bc9 / nguoivsnguoifinal 73af0f1.
Added product/function comparison against current need-review plus dirty runtime:
`reports/branch-reviews/PVP_FEATURE_COMPARISON_20261102.md`.
Eight donor snapshot sources match Git; eight critical target sources match
the previous audit hashes. Focused recheck PASS, exit 0: 45 current mode/user-flow
tests + 13 donor probes = 58 (57 parallel / 1 serial), runner 24.69 seconds.
Eleven probes reproduce defects; this is not merge approval. No production
change, actual merge, hardware connection or actuation. Existing review baseline
and physical issue status remain unchanged; LAST_REVIEWED_HEAD not advanced.

## 2026-10-31 11:43 controller recheck — read-only

12:04 follow-up: user confirms abnormal posture occurs during a move. Fresh
read-only controller/state reads still show 1/1 and tool/user=1/0. Three explicit
mock-only execution-boundary probes pass (16.50s, runner exit 0): absent measured
arrival verification permits progression after fake MoveCart success, while a
LAND/112 failure correctly blocks grip. This is not proof of an early real
controller return or collision reproduction. Details and command in the report.

Game app not running; controller reachable. 200 checksum-valid state packets
and before/after GetRobotErrorCode show main=1/sub=1 (joint command point error).
Arm joints differ from yesterday's 20:40 observation by at most 0.001526 deg;
current active tool/user are 1/0, while fixed profile uses 0/0. Active TCP differs
from yesterday by 260.649 mm although current flange nearly matches old TCP.
FK validates the measured TCP under current tool context. No historical cause
is assigned to the new tool discrepancy. No actuation, error reset, frame change,
runtime/calibration edit or production fix. Evidence and limits:
`reports/controller-check-20261031/REPORT.md`. LAST_REVIEWED_HEAD not advanced.

## 2026-10-30 20:40 live pose / read-only kinematics

User reopened the application in session `20261030_202855_7a8a6252` after the
archived session reset. Authorized read-only telemetry/controller calculations:
fresh physical state shows E-Stop active/commands disabled, joints approximately
[39.336,-193.811,66.309,-74.556,-87.618,-46.047] deg. Controller FK independently
matches measured TCP [348.601,148.442,395.616,-59.304,-42.692,109.980] mm/deg.
Current-reference IK for failed approach/land returns 112; HOME-reference IK
returns solutions. This is endpoint mathematics, not a safe recovery route.
Saved HOME/R1-R4 FK matches stored XYZ within 0.005 mm, not physical commissioning.
New-session log records LAND/112 at 20:31:01; separate from old APPROACH/14.
movel_pose also calls MoveCart(config=-1), so its name is not a linear-path proof.

**VERIFICATION:** fresh telemetry + controller read-only FK/IK, no actuation,
servo/mode/error-reset writes or runtime/calibration edits. Actual collision path
and historic joint-solution choice remain unproven. Evidence:
`reports/live-pose-20261030/REPORT.md`. LAST_REVIEWED_HEAD is not advanced.

## 2026-10-30 physical collision after power interruption — investigation only

User reported a real collision during an AI move after restart and F12 recovery.
Live logs correlate 20:02:30 failed-session clearance, 20:02:57 activation and
20:03:54 MoveCart code 14 at APPROACH for black cannon (7,2)->(4,2). Camera/FEN
checks passed; no LAND/GRIP completed for that move. The same move/profile had
succeeded before the interruption. F12 is board/idle/stop recovery, not proof of
a safe starting arm configuration or physical route. Current approach dispatches
MoveCart(config=-1), whose joint solution depends on current joints, without a
verified post-restart start-pose/path contract. Exact physical cause remains
unconfirmed because actual joints/trajectory/controller subfault were not logged.

**TEST_EVIDENCE:** PASS (exit 0), 3 offline mocked probes via test_fast.ps1,
2 workers. Tests demonstrate current risk boundaries, not physical safety.
Source/calibration unchanged; no hardware calls, fixes or full regression.
Log/journal snapshots preserved under logs; incident report:
`reports/powerloss-incident-20261030/REPORT.md`.
Do not advance LAST_REVIEWED_HEAD/VERIFIED_FIXED for this scoped investigation.

## 2026-10-30 scoped PvP donor review — no runtime integration

Reviewed `origin/feature/player-vs-player` at `75c1bc9` and
`origin/feature/nguoivsnguoifinal` at `73af0f1` against committed `need-review`
`18e67fc` and the current dirty runtime source. The first tip reverts PvP;
the second retains it but has blocking legacy startup/direct-dispatch paths,
premature board commit, weak verification and lifecycle/API conflicts.
Verdict: DO NOT MERGE wholesale; port room transport/role views selectively.
No production source, calibration or hardware state changed. Existing
LAST_REVIEWED_HEAD and VERIFIED_FIXED claims are not advanced by this scoped review.

**TEST_EVIDENCE:** PASS (exit 0), 45 current mode/user-flow tests and 13 distinct
donor probes through `tools/test_fast.ps1` (2 workers + serial socket probe).
Eleven donor probes PASS by reproducing defects, not by proving merge safety.
Both committed-head merge simulations have 32 conflicted files. No merge,
full integration regression or physical FR3/camera test was performed.
Details: `reports/branch-reviews/feature-nguoivsnguoifinal_vs_need-review_REVIEW_REPORT.md`.

## 2026-10-30 user-selected fixed robot-base teaching profile

**VERIFIED_FIXED (software boundary):** Physical game sessions select
`calibration/physical_teaching_points_user0.json` through config. R1–R4,
HOMECHESS and R_Trash preserve recorded numeric poses/joints and use tool 0/user 0.
The source snapshot and identity normalization evidence are recorded in the file.
Startup, per-move HOME checks and capture routes resolve points from this fixed
source; the mirror adapter uses the same cache. Controller teaching/WObj queries
are not called in this runtime mode. No controller writes or physical motion.

**TEST_EVIDENCE:** Windows/Python 3.12.10, `.venv312`. PASS (exit 0):
`tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_fixed_user0_teaching_points.py,tests/unit/test_f2_camera_and_frame_restart.py,tests/unit/test_connection_calibration_split.py,tests/unit/test_legacy_physical_robot_gates.py,tests/unit/test_visual_simulation_adapter.py,tests/unit/test_visual_v2_adapter.py`
— 91 parallel + 1 serial = 92 passed. New tests reject missing/invalid fixed data
without live fallback, assert zero teaching/WObj reads through move/capture/HOME,
and preserve the recorded numbers exactly. Focused fixed-source tests: 10 passed.
Initial test-fixture failures assumed configured mirror geometry and used a
reflected synthetic grid; fixtures were corrected without changing geometry gates.
Real camera/FR3 and full regression NOT RUN; optional mirror geometry/Z readiness
remains independent. Legacy controller-reading diagnostics remain available.

## 2026-10-30 old-firmware WObj compatibility follow-up

Live-run logs (not agent hardware calls) confirm Fault -506: controller method
GetWObjCoordWithID is absent. The prior patch missed this firmware capability.
Normalization now falls back only on that explicit missing-method fault and
verifies the selected taught WObj through current-frame queries. If another
frame is active, the error asks the operator to select the required WObj; no
controller selection is changed by code. F9/F10 retries reload failed metadata
before telemetry/camera/stop gates instead of keeping the startup error forever.

**TEST_EVIDENCE:** PASS (exit 0), 54 parallel + 1 serial = 55, Windows/Python
3.12.10, SDK mocked. Commands and boundaries are recorded in
`reports/f2-frame-restart-fix-20261030/REPORT.md`. Hardware/full regression NOT RUN.

## 2026-10-30 F2 teardown and physical restart frame verification

**VERIFIED_FIXED (scoped mock/native-window evidence):** HighGUI window closure
stays on its GUI owner while F2 device disposal runs on a worker. Identity-WObj
normalization reads the taught frame by ID rather than the active controller
selection; invalid/nonidentity replies remain blocked. Reload drops stale proof.
Async F9/F10 failures now log their actual exception/traceback. No configuration,
calibration artifacts or controller state were changed.

**TEST_EVIDENCE:** Windows/Python 3.12.10. PASS (exit 0): focused runner 30 parallel
+ 1 serial; related regression 82 parallel (overlapping tests). A real Windows
HighGUI window with generated pixels/fake capture closed correctly after worker
stop, exit 0. Real camera/FR3 and full regression NOT RUN. Commands and bounds:
`reports/f2-frame-restart-fix-20261030/REPORT.md`. Prior unrelated OPEN findings
remain open.

## 2026-10-30 physical gameplay continuity audit

**AUDIT ONLY:** Historical PHYSICAL log confirms that a move passed full-board
and center checks, then stopped on HOMECHESS frame mismatch. Current fake-SDK
probes reproduce incomplete waypoint preflight (HOMECHESS/R_Trash), an unbounded
camera read beyond the verifier retry deadline, and recovery feedback that omits
the explicit F5 needed to restart a consumed AI turn. Existing stop/enable and
latest-center findings remain OPEN. No production/calibration/config edits.

**TEST_EVIDENCE:** Windows/Python 3.12.10; standalone gameplay probe PASS (exit 0).
240 legal plies / 120 robot moves / 12 robot captures / 240 durable commits, with
matching board/FEN and a capture-removed retry without repeated disposal. Replay
stopped at its ply limit, not game end. Physical hardware and full regression:
NOT RUN. `reports/physical-gameplay-audit-20261030/REPORT.md` contains boundaries,
source evidence, reproductions and the command. No skills/subagents used this turn.

## 2026-10-30 physical-flow audit (3 OPEN findings)

**AUDIT ONLY:** Three P1 defects reproduced with production methods and fake
SDK/camera: enable can follow a new stop during activation; the idle telemetry
gate is not refreshed after board verification; center picking accepts earlier
samples when the final camera read fails and can dispatch a move. Production
code/tests were not modified during this audit. These paths predate the recent
fresh-start/FEN-log edits; this is not a clean-HEAD attribution.

**TEST_EVIDENCE:** Windows/Python 3.12.10, `.venv312`: deterministic probes PASS
(exit 0, reproductions of defects); focused project runner FAIL (exit 1),
104 passed / 3 failed. The three failing cases reproduced on an isolated rerun.
Full regression and physical camera/FR3: NOT RUN. Findings, exact commands,
source locations and limits: `reports/physical-flow-audit-20261030/REPORT.md`.

## 2026-10-30 actionable FEN verification diagnostics

**VERIFIED_FIXED (scope):** Expected-board verification and full-board scans now
log explicit reason codes, human-readable per-cell expected/observed pieces,
confidence values/thresholds, sanity errors, frame-order/age rejection and stable
sample progress. A `verification_id` correlates each sample/retry/final result.
Latest rejected images no longer inherit earlier diagnostic board verdicts.
Existing acceptance thresholds, exact equality and robot gates are unchanged.
F4 instability compares its two scans, not the old game FEN.

**TEST_EVIDENCE:** Windows/Python 3.12.10, `.venv312`. PASS (exit 0):
`tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_fen_verification_diagnostics.py,tests/unit/test_board_verify_retry.py,tests/unit/test_brd_camera_contract.py,tests/unit/test_camera_observation_integrity.py,tests/unit/test_physical_camera_commit_gate.py,tests/unit/test_reliability_recheck.py,tests/unit/test_review_lifecycle_edges.py,tests/unit/test_game_modes_review.py,tests/unit/test_project_logging.py,tests/unit/test_fresh_session_startup.py`
— 99 parallel + 15 serial = 114 passed, including real `errors.log`/`events.jsonl`
output with mocked camera evidence and strict JSON parsing for NaN/Infinity
timestamps/observation IDs. Scoped review resolved non-standard numeric JSON;
no remaining introduced findings were reported. Focused initial gate: 27 parallel + 1 serial
passed after fixing a finite retry mock stream that exhausted instead of
representing a persistent wrong board. Production camera/robot and full
repository regression: NOT RUN. Details: `docs/LOGGING.md`.

## 2026-10-30 fresh game on launcher startup

**VERIFIED_FIXED (scoped working-tree change):** `build_session` requests a fresh
journal session before opening devices. The previous complete snapshot is copied
atomically into `session_archive`; committed moves, command receipts and existing
projection records are retained. The launcher does not restore the previous FEN,
turn, move history or pending commands. The new `GameState` keeps its opening FEN
and the existing physical startup callback requires fresh camera verification of
that opening board. Direct recovery callers can still use `attach_journal`
without `fresh_start=True`.

An uncertain previous physical session retains only the operator-recovery latch,
not its old board/command authority. `ControlledStopCoordinator` requires fresh
idle measurements for that latch even without pending commands. Startup remains
read-only; camera verification and explicit F9/F10 enable are still required.

**TEST_EVIDENCE:** Windows, `.venv312`, Python 3.12.10. PASS (exit 0):
`tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_fresh_session_startup.py,tests/unit/test_session_user_flows.py,tests/unit/test_brd_commit_projection.py,tests/unit/test_session_modes.py,tests/unit/test_startup_failure_recovery.py,tests/unit/test_simple_launch_sync.py,tests/unit/test_board_verify_retry.py,tests/unit/test_brd_camera_contract.py,tests/unit/test_home_mode_selector.py,tests/unit/test_spectator_lifecycle.py`
— 102 passed; no serial tests selected. All five changed/new Python files parse.
Scoped review resolved the missing stop-measurement requirement; no remaining
introduced findings were reported. Full regression, real camera and physical FR3:
NOT RUN. Geometry, calibration and physical motion profiles were not changed.

## 2026-10-28 stale pre-dispatch AI transaction is not re-armed

A restored `RECOVERY_REQUIRED` journal whose pending AI command failed at
HOMECHESS/frame verification is now retired on load. That failure occurs before
the first motion stage, so re-arming the same pending transaction only reproduced
the old error on every restart. The board/FEN recovery lock is still active; V,
F4, or the clear-failed-session button must verify the board before play. Other
failed AI transactions, especially after dispatch, remain loaded and require
operator reconciliation.

## 2026-10-28 clear failed session button

Physical recovery now exposes **XÓA PHIÊN LỖI** (`F12`) in the client controls
when `move_sync_error` or `physical_sync_fault` is active. It verifies the full
physical board against the current FEN before clearing the pending failed
transaction; a mismatch keeps the session locked. The button sends no robot or
gripper command. This is a one-click operator recovery without restarting the
app.

## 2026-10-28 robot Ethernet link caveat

The physical controller link is known to be intermittent because the Ethernet
cable/connector is loose. `GetControllerIP: controller reply unavailable` and
`Robot SDK not connected` are link symptoms, not automatically code regressions.
Re-seat the cable and verify with `ping -n 2 -S 192.168.58.3 192.168.58.2` before
restarting. Do not replay motion or enable F9/F10 on an unstable link. See
[`ROBOT_CONNECTION.md`](ROBOT_CONNECTION.md).

## 2026-10-28 identity-WObj frame normalization

The live controller stores R1-R3 with user frame 1 and R4 with user frame 0. A
read-only query showed the current WObj is ID 1 with offset
`[0,0,0,0,0,0]`, so the numeric XYZ values are already robot-base coordinates.
`FR5Robot` now normalizes those metadata labels to user 0 only when both the
current WObj ID and its identity offset are verified at connect time. A
non-identity or unknown WObj remains rejected. The raw snapshot is preserved in
`reports/r1_r4_current_20261028_192917/teaching_points.json`; the derived XY-only
file is `r1_r4_frame0_xy.json`. Z was omitted from the derived file and was not
used as board-surface Z. No motion or enable command was sent.

## 2026-10-28 physical camera 4-corner calibration and recovery exit

The physical home screen now shows a one-shot checkbox, **Chấm lại 4 góc bàn từ camera**,
after the operator selects **ROBOT THẬT**. Starting the session sets
`RECALIBRATE_CAMERA` and `CAMERA_CALIBRATION_MANUAL_ONLY`; camera initialization
opens the existing OpenCV `CALIBRATE` window so the operator can click the four
outer board intersections, optionally inspect the yellow grid, and press `S` to
save `perspective.npy`. This is camera-to-grid perspective calibration, not the
controller R1–R4 teaching points. The checkbox never moves the robot and does not
bypass F9/F10. `--physical --recalibrate-camera` preselects the checkbox; the
checked box forces manual four-corner mode, while unchecking it falls back to the
existing auto-first flow.
The recovery screen retries cleanup with F2 in both recovery phases and allows a
deliberate second Ctrl+C force-close only when robot motion ownership and pending
transactions are absent; otherwise it refuses and keeps the safety barrier. No
physical robot/camera run was performed. Focused home/startup/camera tests pass.
## 2026-10-26 obsolete documentation removed

Removed self-suspended or legacy documentation that no longer reflects the
current architecture: the Phase 4 runbook/audit/acceptance/checklist/template
cluster, the FR5 motion model, the suspended R1-R4 placement guide, the
2026-09-24/26 FR3 reviews, the 2026-09-25 handoff note and the 2026-09-09 branch
changelog. Active pointers now reference `docs/BRD_XY_CALIBRATION.md`,
`docs/ROBOT_FRAME_BASE_ONLY.md` and `docs/VISUAL_V2_MOTION_PROFILE.md`.
`PROJECT_CONTEXT.md`, `CURRENT_STATE.md` and `docs/PHYSICAL_GEOMETRY_CONTRACT.md`
were updated accordingly. Content remains in Git history; no code, tests,
calibration artifacts or hardware were changed.

## 2026-10-28 mode-specific client controls and rollback

The client panel now follows the active session capabilities:

- game-only: only ROLLBACK (after a saved move)
- virtual simulation: viewer sync when a viewer exists, GẮP/THẢ, HOVER, ROLLBACK
- physical: FEN scan, confirmation, emergency mode, GẮP/THẢ, HOVER, ROLLBACK
- human-vs-human: viewer sync when applicable and ROLLBACK; no camera/robot controls

Controls use a compact vertical layout for real profiles, so removed controls leave
no empty rows or overlapping note. CONTINUE appears only for visual/test retry or
snapshot recovery. Human moves now always save rollback state (preserving a
physical camera baseline), so game-only and virtual simulation can press Z without
camera. Keyboard shortcuts are gated by the same capabilities. The viewer HTTP
accept backlog is 128 to prevent intermittent ES-module connection refusals.

## 2026-10-26 hybrid captured-piece telemetry

Captured pieces are now removed from the PyBullet `world.pieces` dictionary and
their rigid bodies are deleted after the capture slot release. An immutable
`PieceSnapshot` is retained in `world.captured_pieces` and included as
`world_state.captured_pieces`; the viewer draws those meshes in the tray without
a physics body. Active `world_state.pieces` therefore drops from 32 to 31, then
30, while the tray list grows. `reset_pieces`/full reconciliation clear or re-add
captured identities correctly. Telemetry validation and viewer hydration accept
the optional list.

Tests: virtual capture execution, camera-twin capture, end-to-end capture,
reset/respawn, physical mirror capture, game-mode capture, and viewer tray
rendering pass. No hardware run.

## 2026-10-26 projection race, gripper visibility, spectator noise

Three follow-up fixes:

- `HardwareManager.sync_committed_board` refuses full-board reconciliation while
  `pending_move`, `pending_ai_move`, or `pending_test_motion` exists. This closes
  the window between virtual motion completion and the GameState commit that
  could teleport a captured piece back to its old square.
- The viewer now shows a `KẸP: ĐÓNG/MỞ` HUD badge and scales virtual jaw travel
  12x for visibility; physical mode keeps the exact CAD travel. The closed
  direction was corrected to move inward. This is explicitly a visual estimate.
- `ProjectionWorker` retires no-token spectator entries once instead of retrying
  archived terminal states every ~30 seconds. `spectator` remains an optional
  online service; it is not the 3D viewer.

Tests added/updated: projection guard, no-token retirement, gripper travel
scaling, viewer visual tests. No hardware run.

## 2026-10-26 local OCCT CAD importer

The viewer no longer loads `occt-import-js` from jsDelivr. Version `0.0.23`
(JS + WASM + LGPL-2.1 license) is vendored under
`robot-3d-viewer/vendor/occt-import-js/`; `index.html` points at the local
script and `check_viewer_assets` requires both files. The viewer HTTP server
also serves `.wasm` as `application/wasm` and answers `/favicon.ico` with 204.
Headless Chrome verified `window.occtimportjs` is a function,
`toolVisualValid=true`, WebSocket OPEN, and `liveSource=VIRTUAL`.

## 2026-10-26 RUN.bat launcher hardening

`RUN.bat` no longer forces a console color, validates the selected Python
environment's core modules before launch, reduces duplicate error pauses,
prints a generic exit hint (no camera-only wording), and supports
`XIANGQI_NO_PAUSE=1` for scripts. It preserves `main.py`'s exit code and still
forwards all arguments. Verified with `RUN.bat --help` and an invalid-argument
exit path; no hardware run.

## 2026-10-26 session presets and operator aliases

Added a non-invasive preset layer: `configure_session(..., mode="BOARD_ONLY" |
"SIMULATION" | "PHYSICAL")` maps the three customer modes onto the existing
`SessionProfile` safety model. CLI aliases are `--board-only`, `--sim`, `--robot`
and `--no-3d`; old flags remain. Physical still uses camera + FR3 read-only at
startup, F9/F10 for motion, and the same `SessionDisposal` path. `--no-3d`
changes only `viewer_enabled`, never simulation or physical robot capability.
The home screen now shows three environment cards (Chơi trên máy / Mô phỏng
3D / Robot thật); the selected card is passed positionally into
`build_session` after the game-mode card is chosen. CLI flags preselect the
card (`--robot` -> PHYSICAL, `--board-only` -> BOARD_ONLY, default/--sim ->
SIMULATION). 71 launch/startup/home/mode tests passed; no hardware run.

## 2026-10-26 gripper action intent + reconnect replay

`robot_VIP.gripper_ctrl` now passes the executed action (`close`, `open_max`,
`close_to_safe_gap`) to the twin listener. `gripper_events.gripper_intent`
maps it to attach/release/idle, so a safe-gap close can never release an
attached piece. The final physical `gripper_command` packet is retained by
`TelemetryPublisher` and replayed in the initial snapshot after viewer
reconnect. Tests cover action forwarding, safe-gap idempotence, and replay.
Related suite: 40 passed with the known capture-retention baseline failure
and one pre-existing telemetry coalescing test bug; no hardware run.

## 2026-10-26 physical gripper_command animation packet

Physical twin bridges now broadcast `gripper_command` on each CLOSE/OPEN command
edge with the GameState piece IDs (`source=PHYSICAL`, `physical_grasp_verified=false`).
The viewer applies it only when both the packet and live source are PHYSICAL and
updates the gripper jaw; virtual/game-only never emits the packet and the viewer
ignores stray copies. `world_state` remains the position source. Tests: physical
packet emission, virtual isolation, stale-poll attachment and Node viewer gating;
57 related tests passed with the known capture-retention baseline failure. No
hardware run. See `docs/LOGGING.md`.

## 2026-10-26 viewer gripper animation no longer depends on telemetry poll

The physical viewer now attaches/releases the estimated payload on the gripper
command edge, even if a telemetry poll at that instant is stale or out of order.
Previously `LiveTwinBridge.animate_command_gripper` returned early when
`poll_once()` failed, so a real pick could be missing from the web. The display
path logs `twin.animation_attached`/`released`, keeps
`physical_grasp_verified=false`, and `finish_command_animation` now clears the
command-animation flag. This changes display only; camera verification and game
commit remain authoritative. New test covers stale-poll attachment; 24 related
tests passed, with the known capture-retention baseline failure remaining. No
hardware run. See `docs/LOGGING.md`.

## 2026-10-26 board mirror surface Z from R1-R4 or measurement

`physical_board_provider` can now resolve the optional mirror surface Z from a
measured value (`BOARD_SURFACE_Z_SOURCE="MEASURED"`) or from R1-R4
(`BOARD_SURFACE_Z_SOURCE="R1_R4"`, median Z with a flatness tolerance). The
R1-R4 path is disabled until `R1_R4_TAUGHT_AT_BOARD_SURFACE=True`; otherwise the
mirror refuses and the default relay remains. `board.surface_z_resolved` records
the source/value/spread. This Z affects only the viewer mirror; command heights
remain `PICK_Z`/`PLACE_Z`/`SAFE_Z`. Tests: 4 new source-resolution tests plus
existing adapter/calibration suites; known baseline failures remain. No hardware
run. See `docs/BRD_XY_CALIBRATION.md` and `docs/LOGGING.md`.

## 2026-10-26 first-pick gripper opening and pick-target retry

`pick_at()` now opens the gripper before the first descent when
`gripper_command_known` is false, and refuses to pick when the gripper is known
to be closed (possible held payload). Existing pick/place sequences that already
ended in the safe gap do not add an extra open pulse. Pick-target acquisition
retries `VISUAL_PICK_RETRY_ATTEMPTS=3` times with a 0.4s interval before
`PICK_PAUSED`, logging `vision.pick_retry`; the 6mm/0.12-cell limits are
unchanged. Evidence: 23 physical-gate tests, 3 retry tests and 192 targeted
tests passed; one known baseline fixture failure remains. No physical run. See
`docs/LOGGING.md`.

## 2026-10-26 visual-correction-v2 motion profile adopted

`config.py` now uses the visual-correction-v2 candidate motion profile:
`SAFE_Z=220`, `PICK_Z=178`, `PLACE_Z=178`, `ROTATION=[180,0,-73.2]`,
`MOVE_SPEED=50`, with `PICK/PLACE_TOOL_ROTATION` following `ROTATION`. Source is
`origin/feature/visual-correction-v2@fb0598d`; `MOTION_PROFILE_VERIFIED=False`
and physical startup emits `motion.profile_unverified`. Gripper pulses
(0.30/0.80), `DRY_RUN`, camera index/resolution, height-pick and board-sync flags
were deliberately not copied. No hardware measurement or actuation. Tests:
profile-adoption test plus existing targeted suites; known baseline failures
remain. See `docs/VISUAL_V2_MOTION_PROFILE.md`.

## 2026-10-26 camera recognition readiness and board verification retry

Physical camera startup now fails closed when CChess ONNX, YOLO `best.pt`,
the YOLO snapshot detector, or CameraMonitor is missing (`camera.recognition_unavailable`,
`STARTUP_FAILED`). A session can no longer open as physical and only fail later at
F10 with a generic camera message. `verify_physical_board` now retries for a
bounded window (`VERIFY_BOARD_RETRY_TIMEOUT_SEC=2.0`, poll 0.15s) before failing,
while keeping exact 90-cell equality. It logs attempts and per-cell differences.
Evidence: 279 targeted tests plus new calibration/readiness/retry tests; one
known baseline fixture failure remains. No camera, robot or physical run. See
`docs/START_PROJECT.md` and `docs/LOGGING.md`.

## 2026-10-26 camera calibration startup

`--physical` now reuses a valid saved `perspective.npy` and does not open the
interactive calibration window. `--recalibrate-camera` forces the window; a
missing file opens it on first run; an invalid file fails startup with an
explicit instruction. The source is logged as `SAVED_CALIBRATION` or
`FRESH_CALIBRATION`, with path/hash/camera index. No camera-index or resolution
metadata is bound to the matrix yet. Evidence: 99 targeted tests plus 5 new
calibration-startup tests; the known baseline failure remains. No camera or
hardware run. See `docs/START_PROJECT.md` and `docs/LOGGING.md`.

## 2026-10-26 robot frame policy: robot base only (user 0)

Physical teaching points must now use robot base (`user 0`) and one common tool
frame. `config.ROBOT_USER_FRAME=0`, `ROBOT_TOOL_FRAME=None` (accept the single
tool returned by the controller), and `BOARD_CALIBRATION_REQUIRE_BASE_FRAME=True`.
`FR5Robot` rejects mixed or nonzero user frames while loading and re-validates
them before enable/motion; the optional board mirror rejects nonzero user too.
Read-only audit: `tools/diagnostics/read_teaching_points.py` (no Mode/RobotEnable/
motion/gripper). Pick measurement and Y/Continue retry now emit structured
events: `vision.pick_attempt`, `vision.pick_resolved`, `vision.pick_failed`,
`vision.retry_paused`, `vision.retry_started`, `ui.retry_pick_requested` and
`ui.retry_rejected` (including PvP rejection, HvR and RvR requests). Targeted
evidence: 68 + 88 + 54 + 175 tests passed; the previously known baseline
failures remain. No physical execution in this change. Re-teaching
R1-R4/HOMECHESS/R_Trash in user 0 on the pendant is still required. See
`docs/ROBOT_FRAME_BASE_ONLY.md` and `docs/LOGGING.md`.

## 2026-10-19 executable user-flow QA follow-up

The latest user request authorized mock/virtual execution. The earlier no-test
blocker below is historical. See docs/USER_FLOW_QA_20261019.md and
reports/user-flow-qa-20261019/ for the current source manifest and evidence.
Three real main-loop/PyBullet/headless-viewer flows completed 10 plies each,
surrender, New Game and mode switching. Final focused tests: 125 passed;
serial tests: 10 passed; Node viewer test files: 11 passed.
The broad run had 862 passed / 35 failed; these failures remain follow-up work.
Physical hardware and full BRD acceptance remain unverified. No completion claim.

## 2026-10-19 static checkpoint / verification blocked

Static checkpoint covers 53 changed application files: all 49 Python files parse,
all 3 changed JavaScript modules pass node --check, and git diff --check succeeds.
Hashes are saved in reports/brd-static-checkpoint-20261019/source_manifest.json.
This is not integration, acceptance or hardware evidence. The repeated blocker
is the earlier no-test instruction: the question permitting mock/simulation tests
remains unanswered across the subsequent implementation slices. Further changes
without executable evidence would be speculative. Full goal remains incomplete;
next step is approved isolated verification and repairs driven by those results.

## 2026-10-19 virtual playback profiles draft

--simulation-profile detailed/fast selects explicit virtual playback presets
(defaults 0.2/1.0) through the same full physics executor. The flag cannot be
combined with --physical or --virtual (simulation disabled). Physical speed and
enable are untouched. Telemetry/viewer receive the selected default; virtual
bindings include profile/backend speed. Source/syntax/diff only; playback timing,
all-animation visibility and T-10/T-21 are not verified. See docs/SIMULATION_PLAYBACK.md.

## 2026-10-19 captured tray draft

Full-board and human-capture reconciliation retain captured rigid bodies instead
of deleting them. Existing simulated outside-board poses are preserved; rebuilt
missing identities use explicitly labelled nominal scene capture slots. The same
slot geometry is used by the virtual executor. Viewer renders captured bodies
outside the board without giving them board cells; New Game/reset clears capture
flags. Python/JS syntax and diff only. Exact pre-restart release poses are not
persisted and no physical tray position is asserted or sent to FR3.

## 2026-10-19 world snapshot context draft

World snapshots now capture pieces/gripper and applied projection context under
one physics lock. Reconciliation records session/revision/game epoch/scene/FEN
with the applied board; simulated transient poses reference that baseline and do
not claim camera-verified grasp. Viewer rejects snapshots from another committed
baseline or scene. Syntax/diff only. Captured-tray reconstruction and full restart/
outage acceptance remain open; see the completion audit.

## 2026-10-19 terminal commit draft

Regular human/emergency/robot move commits now adjudicate king loss/no legal
replies before saving the committed snapshot/outbox. Winner, terminal reason and
durable end intent are written with the winning move. Repeated game-over handling
does not erase that reason or advance the AI epoch again. AST/diff only; crash
windows, observer failure and end-to-end terminal delivery remain unverified.

## 2026-10-19 viewer command ownership / context draft

Managed viewer commands echo committed session/revision/game epoch, scene epoch
and FEN from telemetry. Runtime revalidates context after acquiring its command
lock; the manager holds the piece-operation barrier throughout each command.
Telemetry's existing background caller now owns the whole operation, replacing
per-command daemon threads. Physical viewers remain read-only. Virtual RvR waits
while its connected scene is busy. Runtime stop retains resources during an
operation and rejects reuse of a closed world. Python/JS syntax and diff only;
no execution/acceptance evidence for these paths.

## 2026-10-19 viewer stream ordering draft

Telemetry packets carry publisher stream ID and packet sequence. The viewer pins
one stream per connection and ignores duplicate/out-of-order packets by type.
Reconnect subscribes before initial snapshot awaits; pending state coalescing
keeps the newer sequence. Closed sockets/stale stream commands are rejected after
the shared command wait. Python AST/JS syntax/diff only; no runtime tests. Game
session/scene command binding and full reconnect reconstruction remain open.

## 2026-10-19 projection / virtual admission draft

Twin outbox application now rechecks session/revision/pending work under the Game
transition lock. Production mirror reconciliation uses nonblocking poll/physics
locks and serializes against piece execution. Virtual admission waits for the
executor's committed-board session/revision/scene epoch; continuous RvR waits
without faulting. Physical execution has no such projection gate. AST/diff only;
runtime, reconnect packet ordering and full PR7/PR11 acceptance remain open.

## 2026-10-19 startup ownership / calibration cancellation draft

Session startup now acquires and validates the repository's environment journal
before constructing/opening hardware. --log-dir no longer changes session storage;
detected legacy journals outside the canonical root stop startup for migration.
Cancellation is checked before resources, between components, and in calibration
sampling/approval loops. Manual calibration keeps pumping close/Q events without
frames and retains its camera reader owner until join succeeds. Syntax/diff only;
no tests, GUI/camera/SDK execution or physical actuation. Runtime/fault injection
and legacy-journal migration acceptance remain open.

## 2026-10-14 physical XY / command binding draft

Physical mirror registration supports XY_SE2 with explicit measured dimensions,
surface Z and verified frame conversion. Mixed 0/1 frame fallbacks were removed
from command points/HOME/Trash; fractional/bool frame IDs are rejected. Pending
commands persist session/revision/coordinate fingerprints; physical stages and
virtual operation entry check them. Syntax/diff evidence only. Metrology, recovery
fault injection, all entry-point coverage and full BRD acceptance remain open.

## 2026-10-14 manual test transaction draft

Pick/place test writes a durable receipt before actuator dispatch, binds stages to
session/board/calibration and virtual scene epoch, and retains unresolved work
across restart. Physical V reconciliation is read-only and requires fresh idle
and stop evidence plus a full-board match to the before/after/restored layout.
Syntax/diff checks only; runtime and fault-injection acceptance remain open.

## 2026-10-14 BRD XY calibration draft

Simulation R1–R4 now fits XY SE(2); board height is a separate input. Apply requires
the current placement version; profile v2 records model/height and scene/geometry
digests. Shared cell mapping reads authoritative geometry spacing. Source/syntax
checks only, no execution evidence. Physical controller XY registration and full
transaction/scene version integration remain open; see docs/BRD_XY_CALIBRATION.md.

## 2026-10-14 BRD spectator routing draft

SQLite now records each local session's spectator server/room and positive FEN/End
receipts. Archived terminal delivery uses its recorded route; it cannot adopt the
live room. Spectator updates retain move order while Twin snapshots coalesce.
API callbacks finish before journal closure, including startup rollback. Source/
syntax checks only; no service, SQLite, fault-injection or hardware runtime evidence.
Unrecorded remote replies and upstream restore/custom-board behavior remain open.

## 2026-10-14 BRD session retirement draft

F2/Choose Mode now enters the controlled stop barrier and retires the old session
before returning to the launcher. Closing steps retain their owners on failure;
shutdown stays in recovery and retries only unfinished steps. Unknown disable ACK
blocks re-enable/replay; Ctrl+F9 records explicit pendant confirmation only.
Partial startup rollback failures retain camera/controller/journal ownership in the
UI. Source/syntax evidence only; no runtime or hardware verification for this draft.

## 2026-10-14 BRD mode capability draft

SessionProfile routes PvP to mouse-only without Camera/FR3/AI, including --physical
launches; robot modes separate virtual test input from physical Camera/FR3. Optional
physical mirror failure has a raw measured relay; optional WebSocket failure retains
the physical game. Compileall/diff check only: no runtime proof of the six combinations.
In-app mode switching, recovery/version integration and full BRD gates remain open.

## 2026-10-14 BRD asynchronous projection draft

Added a durable projection worker and response-ACK spectator adapter; committed
Game mutation no longer waits for viewer/network callbacks in journal-backed
sessions. Terminal queue order is FEN then End; old ACKs cannot erase a replaced
terminal payload. Compileall/diff check only, NO execution evidence. Retired-room
routing, fault injection and the full BRD gates remain open; see progress document.

## 2026-10-14 BRD persistence/recovery draft

Durable session journal and commit-before-projection hooks added. Reopened sessions
are paused for operator reconciliation; unknown command-stage receipts are not
replayed. Exception shutdown gains a recovery UI. Compileall/diff check only:
NO runtime/tests/hardware evidence. Async outbox delivery has a later draft;
full BRD gates remain open. See docs/BRD_IMPLEMENTATION_PROGRESS.md. Dirty worktree,
not commissioned.

## 2026-10-14 BRD controlled-stop draft

Controlled-stop/deferred-reset/RvR end ordering implemented in the dirty worktree.
Compileall and diff whitespace check succeeded; no tests, GUI or hardware execution.
Do not treat earlier test evidence as covering these changes. PR2/BRD full goal is
still active; see docs/BRD_IMPLEMENTATION_PROGRESS.md for scope and remaining gates.

## 2026-10-13 Camera Monitor / GPU correction

Continuous capture/inference start restored, atomic/pick snapshot APIs restored, stale boxes hidden, VISION_DEVICE=auto/cpu supported. Installed Torch2.14.1+cu126 + ORT-GPU1.20.2; actual camera2/DSHOW GPU preview retained32 named pieces through15s. Final scoped gate123passes. Full gate857passes/12baseline findings; UI accent fix resolves3,9findings remain. See docs/CAMERA_MONITOR_GPU_FIX_20261013.md. No robot actuation or calibration changes.

## 2026-10-13 raw arm reconnect QA

Failed SDK startup now retains the read-only state mirror/WebSocket so receiver recovery can reach the viewer independently of board calibration. No automatic actuation authorization. 98 scoped Python passes and three Node suites; actual FR3 + WebSocket + browser joint values matched with board uncalibrated. See docs/ARM_RECONNECT_QA_20261013.md.

## 2026-10-13 board-side orientation QA

Nominal board rotated180 around unchanged center/height to match requested physical red/black sides. Defaults/providers/cell helpers follow scene yaw; explicit rotations retained. Verified90 scoped Python tests, four Node suites, browser32 meshes and physical arm joint telemetry. Physical board calibration/motion still unverified. See docs/BOARD_SIDE_ORIENTATION_QA_20261013.md.

## 2026-10-13 raw arm viewer QA

Main-process FR3 raw telemetry and browser joint update verified read-only. Misleading PREVIEW OFFLINE launch warning repaired: arm-live status and uncalibrated board warning are separate. Four Node viewer suites passed; isolated browser Connect/disconnect against actual main WebSocket passed. Operator tab verification pending; see docs/RAW_ARM_VIEWER_QA_20261013.md.

## 2026-10-13 live QA / SDK shutdown

VS ROBOT/EASY live QA: current session lacks SDK measurements; ping subsequently failed. SDK shutdown/reconnect cancellation repaired, 58 scoped passes (real local socket/thread tests). Fresh physical telemetry/viewer and moves pending operator network check. See docs/LIVE_QA_SDK_SHUTDOWN_20261013.md.

## 2026-10-13 SDK connection / calibration separation

Live controller read: R1-R3 tool=0,user=1; R4 tool=0,user=0. Teaching-point validation no longer marks an established SDK connection disconnected. Raw arm telemetry/WebSocket remains available; invalid calibration blocks physical enable/actuation and board alignment. Focused gate: 106 passes, including actual local WebSocket with mocked measurements. Patched GUI/hardware motion NOT RUN. See docs/SDK_CONNECTION_CALIBRATION_SPLIT_20261013.md.

## 2026-10-13 worker scheduling / retry review

Six reproduced boundary failures repaired: QUIT remaining-event dispatch, F6 discarding unconsumed results or paused checkpoints, self-play overlapping UI worker jobs, retry baseline/mirror failures, and terminal retry publication. Final subsystem: 189 passes; independent before/after scheduling probe: 100/100 mock-executor replays. Full gate: 1044 parallel + 8 serial = 1052 passes (exit 0). Primary compile/parity passed; see delivery-manifest.json. See `docs/RUNTIME_RACE_REVIEW_20261013.md` and `reports/runtime-race-review-20261013/`. Hardware, firmware completion and real grasp remain unverified.

## 2026-10-13 game mode review

Repaired UNIFIED Black turns/rearming/recognition quality/sample gaps and post-mirror recovery, AI/self-play finished or unconfirmed entry guards, and Continuous surrender at a safe READY boundary. Final affected gate: 160 passes; full gate: 1029 parallel + 8 serial = 1037 passes. Each of three game modes completed a deterministic 10-ply/two-capture sequence, surrender and New Game with real PyBullet board reconciliation and mocked arm execution. Evidence: `docs/GAME_MODE_REVIEW_20261013.md`; latest hashes: `reports/mode-review-20261013/delivery-manifest.json`. Physical actuation/vision and trajectories remain unverified; no geometry/calibration change.

## 2026-10-12 lifecycle edge review

Additional fixes: human/Black Emergency terminal publication, entrypoint rejection for finished/unconfirmed/illegal moves, preservation of rejected Red Emergency recovery, rollback undo-stack restoration, Emergency mirror/result handling, and camera-Q same-frame dispatch prevention. Final subsystem gate: 142 passes; full gate: 1011 parallel + 8 serial = 1019 passes, including a real headless main.py camera-Q probe with mocked devices. Details: `docs/LIFECYCLE_EDGE_REVIEW_20261012.md`; latest hashes: `edge-delivery-manifest.json`. Hardware remains unverified.

## 2026-10-12 spectator lifecycle follow-up

F8 → F6 reopens spectator with the current FEN, startup reuses queued rooms, New Game explicitly rotates rooms, and finished games require New Game. Self-play startup failure messages remain visible. Final subsystem gate: 85 passes; full gate: 996 parallel + 8 serial = 1004 passes. Real headless main.py F8/F6 event routing passed with mocked devices/HTTP and zero robot commands. See `docs/SPECTATOR_LIFECYCLE_FIX_20261012.md` for delivery evidence; latest hashes: `session-lifecycle-delivery-manifest.json`. Hardware and live spectator service remain unverified.

## 2026-10-12 second reliability review

Seven additional failure groups reproduced and repaired: startup UI rollback, Continue confidence/current-color, recovery error lifecycle, spectator stop/terminal publication, and known king-capture board verification. Final affected gate 110 passes; full pre-terminal snapshot 978 parallel + 8 serial passes. Scope and exact evidence: `docs/RELIABILITY_RECHECK_20261012.md`. Hardware remains unverified; latest hashes are `recheck-delivery-manifest.json`.

## 2026-10-12 reliability corrections

- Physical target coordinates/heights follow fetched visual-correction-v2 `fb0598d`; explicit enable and fresh controller state remain required. Physical commands do not consult simulator collisions, per current user request. Virtual collision handling is retained.
- Startup/recovery/engine/RPC/API/lifecycle and command-animation fixes are documented in `docs/RELIABILITY_FIXES_20261012.md`. Exact verification results and delivery hashes: `reports/reliability-fixes-20261012/REPORT.md` and `delivery-manifest.json`.
- Missing board surface contact calibration permits read-only arm telemetry; it does not prove board/piece alignment. No camera/FR3 physical test in this change. Earlier dated entries below describe earlier snapshots.

## 2026-10-09 physical UI latency fix

- Automatic board polling consumes atomic camera-worker observations without camera reads/model inference on the UI thread; repeated/stale samples cannot satisfy stability gates. ONNX CPU pools are bounded; fresh command verification remains unchanged.
- HTTP viewer now starts even when physical calibration blocks the mirror, with an explicit offline preview warning and no telemetry/autoconnect. --virtual still disables simulation/viewer.
- 72 targeted tests passed; real Python3.12 model/UI smoke and browser preview verified in isolation. Physical camera/FR3 responsiveness after restart remains unverified; cold model setup can still be slow. Evidence: reports/physical-ui-latency-20261009/REPORT.md.

## 2026-10-09 startup device failure recovery

- main.py now catches initialization failures locally, retains the home screen and displays wrapped failure/retry guidance. initialize_all retains ownership of partial-startup cleanup; no implicit device substitution or calibration override.
- 25 targeted startup/camera/window tests passed; Python3.12 real-entrypoint probe retained the GUI through two mocked camera failures, with no controller connection or APP_UNHANDLED. Scoped Luna review: no blocker.
- Live log diagnosis: camera index1 supplied no frame while WindowsCamera process was present; physical mirror also refused an uncalibrated board contact offset. Camera readiness and physical calibration remain unresolved/untested. Evidence: reports/startup-camera-recovery-20261009/REPORT.md.

## 2026-10-09 Windows viewer startup repair

- Windows setup now installs pinned local Three.js modules, including dev dependencies; startup checks required assets and reports missing installation with actionable guidance.
- HTTP JS/MJS MIME types are deterministic across Windows associations. RUN.bat forwards CLI options, preserves the Python exit code, and checks the actual Python Moonfish entrypoint.
- Targeted launcher/HTTP/logging gate: 22 tests passed on Python3.11. Python3.12.10 actual HTTP probe verified incorrect OS MIME mappings before/after the patch; browser rendered the virtual robot/board and autoconnected to SIMULATION/IDLE.
- The user's earlier one-off main.mjs error did not reproduce on the already-running server; its exact original cause remains unverified. No physical hardware used. Evidence: `reports/viewer-startup-fix-20261009/REPORT.md`.

## 2026-10-09 selective visual v2 integration

- Selected source `fe3faa8` under all recommendations A; preserve current simulation/R1-R4/geometry/executor/identity/telemetry and defaults. New camera optics/calibration, strict target guard, same-move retry checkpoints, physical worker, and T/H/Y UI adapters. New camera modes off; measured dimensions unset; donor calibration not activated.
- Local evidence: full runner 727 parallel + 8 serial passed; after final guard/recovery refinements, 236 focused tests passed. Replay 10 plies each in three modes with actual PyBullet; 15 robot moves measured before FEN/reconcile, max XY error 0.173 mm in simulation. Rotated/translated R1-R4 hover and viewer reconnect observed.
- Integration remains a selective uncommitted patch, not a merge commit. Camera/FR3 and fresh Python3.12 install unverified. Guide: `docs/VISUAL_V2_INTEGRATION.md`; scope/evidence: `reports/visual-integration-20261009/REPORT.md`.

## 2026-10-06 telemetry liveness fix verified in virtual self-play

- Network callbacks now run outside the asyncio loop with serialized dispatch. Robot/world snapshots coalesce into bounded per-client writers; slow/overflow clients disconnect explicitly. Reconnect replays operation state; older mirror samples cannot rewind telemetry.
- Borrowed virtual snapshots delayed by planning locks are discarded without false stale faults. Physical freshness gates remain unchanged.
- Isolated normal-entrypoint GUI session: 10 total plies (5 each side), two captures, surrender; all 30 remaining identities/cells match, 0 twin.fault and 0 error events. Viewer follows motion and reloads to IDLE with matching final joints; reconnect probes 0.41–0.64s. Six final liveness tests pass; earlier affected gate 21 passes. Main/worktree hashes match for three changed source/test files.
- Changes remain uncommitted. Other game modes were not replayed after this transport fix; hardware and exhaustive trajectories remain unverified. Evidence: `reports/telemetry-fix-20261006/REPORT.md`.

## 2026-10-05 simulation board profile and recovery UI

- Added explicit save/restore of the active R1–R4 simulation pose across restarts, with frame/unit/provenance/calibration version, scene checksum and transit height. Restore uses existing SERVICE_SAFE, version, geometry and swept collision gates; no automatic startup relocation or physical calibration override.
- Recovery panel now shows required action, fault, pending move and execution state. Camera recovery guidance applies to physical mode; virtual mode and manual test have their own guidance. Existing recovery/activation gates remain authoritative.
- Isolated worktree: 70 subsystem checks passed; full unit runner 701 parallel + 8 serial passed (exit 0). After final UI/physical command guard refinements, 35 focused checks passed and viewer syntax check passed. Browser actual save/reset/stale rejection/preparation rejection/restore observed; GUI images retained. Mock physical ordinary/capture commits update real PyBullet/telemetry; failed camera confirmation retains board and blocks repeat motion.
- Luna independent static review: one misleading manual-test instruction corrected, no remaining blocker reported. Eight edited code files have matching main/worktree SHA256. No hardware used; changes remain uncommitted. Guide: `docs/BOARD_PROFILE_AND_RECOVERY.md`; evidence: `reports/profile-recovery-20261005/`.

## 2026-10-05 selective visual integration verified

- Integrated stable corner consensus/operator approval, strict centre pick, independent measurement client/CLI, correction debug, and reimplemented manual pick/place through the unified executor. Preserved simulation, geometry, launcher/logging, read-only physical connect, resize/fullscreen and MOVE_SPEED=70.
- Manual test owns a separate board/identity map; checked movement precedes scene reconciliation. SDK/camera/scene failures latch; game/AI/self-play stay paused until New Game/reconciliation. Physical faults revoke owned activation without gripper/HOME.
- Isolated worktree evidence: broad gate 731 parallel + 8 serial passed; subsequent focused gates 97, 51 and 30 passed. Nine Node contracts and both startup smokes exit 0. Actual manual GUI → PyBullet move after yaw 3 degrees/X +10mm: XY error 0.1504mm before reconciliation; reset preserves taught pose and restores 32 pieces.
- Main working changes retained, not committed/pushed. No real hardware exercised, no exhaustive 8010-route claim. Details: `docs/VISUAL_LATEST_REVIEW_20261005.md`, `reports/visual-integration-20261005/`.

## 2026-10-05 latest visual branch review (historical, before selective integration)

- Fetched `origin/feature/visual-correction-v2` at `652af26`, seven commits beyond donor `e6bb632`. Reviewed in detached worktree; 62 selected tests pass, but mocked SDK/camera probes reproduce two P1 issues in new manual pick/place: continuation after code 112 and repeat commands after failed post-motion verification.
- Stable-corner approval, strict center pick, independent geometry measurement and debug changes are useful candidates. Keep current integration launcher, physical gates, typed results, simulation/viewer and resizing when incorporating them. Visual legacy startup remains physically active by default and must not replace current read-only startup.
- Review only; source not merged or fixed on visual. Evidence: `docs/VISUAL_LATEST_REVIEW_20261005.md`, `reports/visual-review-652af26/`. This is not a whole-repository or hardware safety approval.

## 2026-10-05 cross-feature audit

- Fixed game-only new-game/rollback falsely requiring camera verification; undo uses the logical sync path. Reset now discards the previous SPACE rollback snapshot (an existing baseline bug).
- Broad unit gate: 658 passed / 1 known baseline failure; separate serial gate: 8 passed. Final affected gate: 51 passed; visual application regression: 45 passed. Six of nine selected Node modules pass; three assertion failures reproduce on clean HEAD. Whole regression remains red.
- Actual PyBullet capture after R1–R4 X +10 mm / yaw +3 degrees succeeds before reconciliation (XY error 0.152152 mm); undo restores victim and reset restores 32 pieces while retaining the taught pose. Both launcher startup probes exit 0. No physical hardware exercised.
- Evidence: `docs/CROSS_FEATURE_AUDIT_20261005.md`, `reports/cross-feature-audit-20261005/`. Historical whole-repository review baseline is unchanged.

## 2026-10-05 scoped R1–R4 simulation verification

- UI apply verified in isolated worktree: X +10 mm, then yaw +90 degrees; 32 PyBullet bodies, motion provider, twin and backend versions follow the transform. Actual black pawn pick/place reaches (4,4) before reconciliation, XY error 0.152137 mm.
- Shifted version 2 GUI validation: 90/90 LOCAL CELL TRAJECTORIES PASS. Not a claim for all 8010 routes or physical hardware. Four targeted Python modules: 31 passed; final logging gate: 8 passed; viewer placement integrity Node test passes.
- Disabled unsupported H edits in R1–R4 mode and prevented legacy preview recalculation there. Console encoding failure now fails without logging recursion. Node single-motion-authority test has an existing tool-status fixture failure, reproduced on clean 7d8c5de.
- Evidence: `docs/R1_R4_SIMULATION_AUDIT_20261005.md` and `reports/r1r4-audit-20261005/`. Historical LAST_REVIEWED_HEAD remains unchanged; this is a scoped review of working changes.

## 2026-10-04 game window sizing

- Added a resizable, aspect-preserving display around the existing 1440×1080 logical canvas, fit-to-desktop startup and SDL Windows DPI policy. F11 switches fullscreen; Esc restores the previous window size. Mouse positions are mapped before all menu/game handlers; letterbox margins are ignored.
- Scoped gate: 22 passed via `tools/test_fast.ps1` (window, offline mouse confirmation, difficulty menu), exit 0. Direct Windows SDL probe: 1152×864 → 1920×1080 fullscreen → 1152×864, exit 0. New GUI observed fully within screen bounds.
- Computer Use screen capture works but automated input remains unconfirmed; no complete GUI game was played. Details: `docs/GAME_WINDOW_DISPLAY.md`. Historical whole-repo review baseline remains unchanged.

## 2026-10-04 gripper opening correction

- User-selected open inner surface gap is 27.5 mm. Viewer CAD finger offsets and generated PyBullet hulls share the same offset helper. Direct hull query measures 27.500 mm; fixed shapes, closed CAD vertices and tool frame/length are unchanged.
- Focused verification: 39 passed / 1 fixture failure, then corrected tip-surface obstacle fixture gate 9 passed; the other 31 cases passed with final production geometry. Node viewer/telemetry and syntax checks passed. Evidence: `reports/integration-20261004/gripper-opening-verification.json`. Full regression and physical hardware were not exercised for this change.
- Historical LAST_REVIEWED_HEAD remains unchanged; this is a scoped geometry correction.

## 2026-10-04 simulation capture follow-up

- Baseline b0afeb2: visual physical R_Trash capture already existed; the simulation adapter had a deliberate blanket capture interlock. Replaced it with identity-checked victim pick → floor-slot place/settle → attacker pick/place → game commit.
- Scene capture slots follow the current board XY frame and use the simulated floor as support. A GAME_MOVE operation excludes concurrent mutations across the whole sequence. Existing checked trajectories, release fail-fast and service retreat remain mandatory.
- Exact recorded h9h2 capture succeeds with actual PyBullet positions inspected before reconciliation; blocked landing retains the victim in the gripper and leaves FEN/turn unchanged. Targeted capture 6 passed, adapter/approach 10 passed, combined capture/fail-fast 25 passed. Final full safe regression: 732 passed, exit 0, 470.09 s; slow/hardware tests excluded. Raw evidence is recorded in reports/integration-20261004/capture-full-regression.log. No hardware was operated; arbitrary placement/route coverage is still not claimed.

## 2026-10-04 scoped AI approach correction

- Baseline: `e5e3b74`. First human move `e6 -> e5` followed by AI UCCI `h7e7` reproduced an approach rejection: gripper/red_rook_0 clearance 1.37 mm versus the existing required 2.00 mm.
- `move_joint_with_lift_recovery` now tries the existing SERVICE_SAFE route after a collision-rejected elevated approach even when J5 does not flip. Every segment retains the full MoveJ collision guard; non-collision failures do not trigger this fallback.
- Final targeted gate: 14 passed, exit 0. Actual PyBullet pick/place verified the cannon at cell (2,4) BEFORE logical-board reconciliation. A blocked service route leaves the AI move uncommitted and recovery required. Prior broader run: 96 passed, 2 failed due only to the new test incorrectly expecting a truthy return from `process_human_move`; corrected tests pass. This is a scoped fix, not a whole-branch re-review or proof of every legal route.

# CURRENT_STATE.md — ACTIVE MACHINE-READABLE REPOSITORY STATE

> **R1–R4 placement:** See `docs/BRD_XY_CALIBRATION.md` and `docs/ROBOT_FRAME_BASE_ONLY.md`. Simulator-generated points are provisional; no physical four-point measurement has been entered. Fixed-axis formulas below are historical, not a general board transform.

## 2026-09-29 camera/GameState/PyBullet/Three.js worktree update

On `feature/unified-robot-vs-robot` at base `b6acba6`, camera-confirmed red/black moves, captures, full-board rescan, semantic robot contexts, and viewer world-state parity have been implemented in an isolated worktree. A one-move rescan infers the next turn; ambiguous multi-change rescans require operator confirmation (`1` Red, `2` Black) before play resumes. Focused Game/Twin regression: 115 passed; Three.js reconciliation: PASS. No physical robot actuation or live-camera accuracy test. Virtual collision guard rejects a black-cannon approach at yaw 0° with gripper/base contact (-0.18 mm); game state stays unchanged. The full `tests/unit` regression was stopped at 92% after multiple failures, many historical yaw-90 tests are stale. Details: `docs/CAMERA_GAME_TWIN_SYNC_2026-09-29.md`. The historical `LAST_REVIEWED_HEAD` below is unchanged until a complete review of the branch is performed.

## 2026-09-26 collision worktree update

This section describes **uncommitted, simulation-only work** on `integration/unified-fr3-system` at `fab750a918c1457ae14bfda900572fb16f846e26`. The historical G90 metrics and test counts below apply to an older checkout; they must not be used as evidence for the current yaw 0° scene. `LAST_REVIEWED_HEAD` below remains historical because the entire dirty worktree has not been reviewed.

### CONTACT-GATED CORRECTION (simulation only)

- The current 22.5 mm rook is **not gripped** by the declared CAD jaw stroke. Direct PyBullet queries at the nominal grasp leave roughly 2-7 mm separation at the two jaws. Closing now returns NO_JAW_CONTACT; no piece is attached and EXECUTE_3STAGE stops at GRASP rather than claiming placement success. Actual stroke, alignment, and grip force still require measurement.
- The carried piece is checked against the floor and every robot link as well as the board and other pieces. Deliberate PyBullet payload penetration into the floor or link 2 is rejected.
- The viewer resolves empty-board clicks through the same board placement transform used to render cells. Piece click metadata follows authoritative nearest_row/nearest_col telemetry. A Node helper test passed; a full browser click session has not been verified.
- The 90/90 and 18/18 acceptance-marked tests check **static simulator IK/collision endpoints only**. They do not verify grip contact, full paths, or hardware safety. Stage-machine tests that need a successful grasp use a documented synthetic bilateral-contact fixture; direct PyBullet contact tests remain unmocked.

### VERIFIED_FIXED (current scope)

- Canonical flange-to-fingertip TCP is 168.3 mm in the active profile; invalid profile data or scene/profile disagreement now fails closed. The collision proxy covers the full axial tool and uses the same transform.
- Adaptive tool yaw: four orthogonal IK candidates yield collision-checked static endpoint poses at 90/90 cells; this is not a successful grasp/contact result.
- Physical FR3 reach envelope: MAX_REACH_RADIUS_M updated from 0.65m to 0.78m in fr3.py, faithful to physical arm span (0.724m from shoulder, ~0.737m-0.864m from base origin), unlocking all 18 key hover & grasp poses.
- PyBullet compound collider 12+7 split ensures all 19 fixed component boxes + 2 moving finger hulls (including viewer_adapter_collar) are registered in physics engine.
- Carried piece payload checks: extended collision verification to floor and robot arm links.
- Pick descent preserves the collision-checked IK jaw orientation. Collision checks include out-of-bounds bodies and the moving attached piece against board and other pieces. Placement releases from 1 mm above the board so the attached piece maintains the 0.5 mm minimum guard clearance until release.
- Repeated board placement updates use the immutable scene surface height, so offsets do not accumulate.

### TEST_EVIDENCE (current scope)

- Direct PyBullet grasp/payload test: 3/3 passed. The nominal rook test asserts an honest NO_JAW_CONTACT failure; synthetic payload penetrations of floor and robot link 2 are rejected.
- Targeted collision and stage-machine fast suite: 99/99 passed. Stage-machine positive grasp cases use synthetic bilateral contact, not actual CAD jaw contact with the nominal rook.
- Viewer helper and existing viewer Node tests passed. The live browser click flow was not exercised.
- An extended fast suite initially returned 44 passed / 11 failed. Two tests in this change set were repaired and rerun (2/2 passed). Nine board-placement/stale-dataset tests remain failing under the active yaw 0 degree scene; the wider suite is not green.
- Historical 90/90 and 18/18 endpoint gates below are not proof of grasp, complete collision-free motion, or hardware safety. No physical robot command was sent.
---

> **Purpose:** Authoritative record of the currently reviewed codebase state. Agents MUST read this file to determine the delta between `LAST_REVIEWED_HEAD` and `HEAD` without rescanning the entire repository.

---

## METADATA
* **CURRENT_BRANCH:** `feature/virtual-robot-3d-simulator`
* **STARTING_REMOTE_HEAD:** `52ae176a6a0a72478693dd32a9b20256c42f6b86`
* **LAST_REVIEWED_HEAD:** `18e67fc9006a91a2a32c4c861974760089a687de`
* **LAST_REVIEW_SCOPE:** Fresh-session startup/persistence/stop-barrier working-tree delta only; earlier geometry evidence below remains historical.
* **LAST_REVIEWED_FUNCTIONAL_HEAD:** `e8ac273`
* **PASS_A_RUNTIME_AUTHORITY:** `PASS`
* **PASS_A1_REENTRANT_LOCK:** `PASS`
* **PASS_A2_NO_SILENT_QUEUE:** `PASS`
* **PASS_B_SERVICE_SAFE:** `PASS`
* **PASS_C_POST_OP_RETREAT:** `PASS`
* **CORRECTIVE_GEOMETRY_G90:** `PASS`
* **CORRECTIVE_VIEWER_BOOT_AND_COORDINATES:** `PASS`
* **CORRECTIVE_G90_SEMANTIC_CONTRACT:** `PASS`
* **CORRECTIVE_G90_FINAL:** `PASS`
* **SELECTED_PLACEMENT_CANDIDATE:** `d = 15.0 mm, H = 40.0 mm, Z = 0.0 mm`
* **PHASE:** `PHASE_3_SIMULATION_VIRTUAL_TWIN`
* **PHASE_STATUS:** `PARTIAL`
* **CI_STATUS:** `LOCAL_VERIFIED_GREEN`

---

## KEY_GEOMETRY_METRICS
* **Board Yaw:** `+90.0°` around `+Z_robot` ($R = \begin{bmatrix}-1&0&0\\0&-1&0\\0&0&1\end{bmatrix}$, quat `[0.0, 0.0, 1.0, 0.0]`)
* **Axis Alignment:** Column axis (span 320 mm) $\to -X_{\text{robot}}$; Row axis (span 360 mm) $\to -Y_{\text{robot}}$
* **Selected Placement:** Forward shift $d = 15.0\text{ mm}$, Safe transit height $H = 40.0\text{ mm}$, Height offset $Z = 0.0\text{ mm}$
* **Reach Margin:** `+24.9 mm` (Max flange approach distance $625.1\text{ mm} < 650.0\text{ mm}$ kinematic reach limit; Max TCP distance $550.3\text{ mm}$)
* **Link Collision Clearance:** `7.69 mm` (Link 1 <-> Link 3 distance at near cells, threshold $0.5\text{ mm}$; zero arm self-collisions)
* **Kinematic Conditioning:** Max Jacobian condition number `21.79` (Well conditioned across all 90 cells, threshold $< 40.0$)
* **Joint Limit Margin:** `9.23°` (Minimum clearance to any joint software limit, threshold $> 5.0^\circ$)
* **Reachability Dataset:** `shared/cell_reachability_dataset.json` (90/90 cells solved, 0 collisions)

---

## VERIFIED_FIXED
The delta between `5f2e84a` and current working tree has been fully reviewed and verified:
1. **[B01] try_grasp Candidate Matching:** Strict single-candidate matching and rejection of mismatched candidate IDs with `GraspStatus.AMBIGUOUS`. (Verified by `test_01_try_grasp_target_matching`, `test_02_try_grasp_target_mismatch_rejection`).
2. **[B02] PlaceResult & GraspStatus Contract:** Formal `PlaceResult` dataclass with backward-compatible dict/bool protocol. (Verified by `test_03_pick_result_fail_fast_contract`).
3. **[B03] PyBullet FR3 Articulated Tracking:** Added `@property def joints_rad` to `RobotStateSnapshot` and `get_robot_joint_positions()` in `VirtualPhysicalWorld`, ensuring real-time tracking of robot joints in PyBullet. (Verified by `test_04_pybullet_fr3_tracking_interpolated`).
4. **[B04] Runtime State Machine, Authority & Concurrency (Pass A, A.1, A.2):** Defined `RuntimeOperationBusy`, implemented `runtime_move_joint()`, routed all WebSocket motion commands through runtime wrappers, closed validation race window by acquiring `acquire_operation_state()` atomically at entry, resolved re-entrant operation lock yielding bug by strictly releasing `_operation_lock` before `yield`, implemented `_operation_depth` tracking, eliminated redundant inner acquisitions, inverted command lock ordering across all 8 runtime wrappers (`runtime_move_joint`, `runtime_go_service_safe`, `runtime_retract_from_board`, `runtime_jog_joint`, `runtime_jog_tcp`, `pick_piece`, `place_piece`, `execute_3stage_trajectory`) so `RuntimeOperationState` acts as the primary admission gate before `_command_lock`, enforced strict non-reentrancy on physical motion operations (`MOTION`, `SERVICE_MOVE`), synchronized validation-in-progress state checking in admission, added deterministic test hooks (`_test_hook_motion_owned`, `_test_hook_service_move_owned`), and proved with timing handshakes that concurrent motions fail fast immediately with `MOTION_REJECTED_BUSY` without silent queueing. (Verified by `test_05_runtime_operation_state_transitions`, `test_06_runtime_operation_state_mutual_exclusion`, `test_a1_move_joint_command_uses_runtime_authority`, `test_a2_true_concurrent_acquisition`, `test_a3_1_real_validator_rejects_move_joint_before_release`, `test_a3_2_timing_handshake_proof`, `test_a3_3_full_route_validator_rejects_move_joint`, `test_a3_validation_vs_move_joint_race`, `test_a4_move_joint_owns_first`, `test_a5_validation_flag_consistency`, `test_a6_exception_cleanup`, `test_a6_nested_exception_cleanup`, `test_a7_service_jog_vs_validation`, `test_lock_not_held_across_yield`, `test_a2_1_move_joint_vs_move_joint_no_queue`, `test_a2_2_timing_handshake_proof`, `test_a2_3_move_joint_vs_jog`, `test_a2_4_service_move_vs_move_joint`, `test_a2_5_pick_vs_move_joint`, `test_a2_6_place_vs_jog`, `test_a2_7_3stage_trajectory_vs_move_joint`).
5. **[B05] Ruler Listener De-duplication:** Consolidated 3D ruler update listener to a single authoritative telemetry event listener. (Verified by `test_16_ruler_single_authoritative_update`, `test_viewer_coordinate_ruler.mjs`).
6. **[B06] Wildcard Protection:** Prohibited wildcard `*` in `allowed_grasp_piece_id` across `CollisionGuard` and backend. (Verified by `test_07_collision_guard_explicit_candidate_no_wildcard`).
7. **[B07] Swept Volume Collision Detection & Margin:** Interpolated 3D collision check between current and candidate board pose against arm links with positive clearance margin $\ge 5.0\text{ mm}$ and detailed diagnostics. (Verified by `test_11_swept_volume_collision_arm_obstruction`, `test_12_swept_volume_collision_clear_path`, `test_b6_vertical_board_raise_rejected_when_arm_low`, `test_b7_board_lowering_swept_path`, `test_b8_forward_and_backward_shift_swept_path`, `test_b9_combined_diagonal_swept_path`).
8. **[B08] Validation Cell Loop Indentation Scope:** Corrected block indentation so each cell and route increments and records failures within its respective loop. (Verified by `test_recommended_placement_90_cells_pass`, `test_full_board_routes_validation`).
9. **[B09] SERVICE_SAFE Physical Safety Predicate & Board Adjustment Safety (Pass B):** Resolved candidate pose collision audit: established authoritative Upright Retracted configuration `[0.0, -70.0, 60.0, -80.0, -90.0, 0.0]°` providing $> 129.9\text{ mm}$ moving link clearance and $> 216.3\text{ mm}$ gripper clearance across the entire adjustment envelope ($[-20, 60]\text{ mm}$ shift, $[-10, 30]\text{ mm}$ height offset); implemented full physical safety predicate `evaluate_service_safety()` with `ServiceSafetyReport`; enforced strict `BOARD_ADJUSTMENT_READY` lifecycle token invalidated by any motion, jog, or completed adjustment; ensured 100% state invariance on adjustment rejection. (Verified by `test_b1_service_safe_physical_predicate_clear` through `test_b11_jog_invalidates_service_safe`).
10. **Manual Cartesian & Joint Jogging:** Incremental jog with step size selectors and collision prechecks. (Verified by `test_13_runtime_jog_tcp`, `test_14_runtime_jog_joint`).
11. **In-Process Recovery Actions:** Granular recovery (`clear_error`, `reset_robot`, `reset_board`, `reset_pieces`) and `full_reset` without process termination. (Verified by `test_15_granular_recovery_actions`, `test_17_full_system_reset_in_process`).
12. **[B10] Pass B Corrective: Predicate Methods, Settling Piece Guard, Mandatory Relocation Gate & Swept Exclusion Volume (Pass B Corrective):** Fixed `is_connected()` method invocation on backend; incorporated `PiecePhysicalState.SETTLING` into transient piece physical state check so settling pieces invalidate `is_service_safe()` and `is_board_adjustment_ready`; enforced mandatory `prepare_board_adjustment()` readiness token and fresh physical `evaluate_service_safety()` check before executing `set_board_placement()` (with narrow internal reset bypass); established behavioral regression test fixture (`[0, -60, 125, -135, -90, 0]°`) with proven initial clearance $d_{\text{initial}} = 7.14\text{ mm} > 5.0\text{ mm}$ margin, proving negative board lowering triggers collision at step $k = 1 > 0$ with `BOARD_RELOCATION_REJECTED_ARM_NOT_CLEAR` and 100% state invariance; implemented canonical service exclusion volume derived from `self.geom` and `self.placement_state` with PyBullet continuous collision detection across all moving links (0..5) and gripper proxies, and explicitly verified arm link detection inside exclusion volume while TCP is $> 39\text{ mm}$ outside the ceiling. (Verified by `test_bc1_disconnected_backend_rejects_service_safe` through `test_bc12_supported_envelope_boundary_cases_remain_safe`).
13. **[B11] Post-Operation Safe Retreat & Separation of Manipulation from Robot Safety (Pass C & Pass C Corrective):**
   - Defined `PayloadSafetyReport` dataclass and `evaluate_payload_clearance()` predicate in runtime ($z_{\text{piece}} > z_{\text{board}} + 20\text{ mm}$).
   - Extended `PickResult` (`piece_grasped`, `payload_clear`, `requires_recovery`, `payload_safety`) and `PlaceResult` (`piece_placed`, `piece_released`, `post_release_lift_complete`, `board_clear`, `service_safe`, `requires_recovery`, `service_safety`) preserving backward-compatible dict/bool fallback.
   - Enforced sequential trajectory stages on `pick_piece()` (`PREPOSITION` -> `DESCEND` -> `GRASP` -> `LIFT` -> `PAYLOAD_CLEAR` -> `COMPLETE`), reaching payload-safe clearance above board without requiring `SERVICE_SAFE` while piece is attached.
   - Enforced 3-stage post-release retreat on `place_piece()` (`APPROACH` -> `LAND` -> `RELEASE` -> `SETTLE` -> `POST_RELEASE_LIFT` -> `CLEAR_BOARD` -> `SERVICE_RETREAT` -> `COMPLETE`), evaluating physical predicate `evaluate_service_safety()`.
   - Decoupled physical piece placement success from post-operation retreat safety so that if piece release succeeds but post-release lift or service retreat fails, `success = False`, `piece_placed = True`, `piece_released = True`, `service_safe = False`, and `requires_recovery = True`.
   - Integrated full Pass C retreat pipeline into `execute_3stage_trajectory()` and WebSocket `EXECUTE_3STAGE`, guaranteeing that manipulation operations never terminate control at `LAND` or low altitude, enforcing `POST_RELEASE_LIFT` -> `CLEAR_BOARD` -> `SERVICE_RETREAT` -> `evaluate_service_safety()`.
   - Enforced explicit grasp precheck on `execute_3stage_trajectory(..., grasp_piece=True)`: strictly requires piece at source cell and empty destination cell; fails fast at `PRECHECK` with `status = "PRECHECK_NO_SOURCE_PIECE"` or `status = "PRECHECK_DESTINATION_OCCUPIED"`; never silently downgrades to arm-only transit.
   - Enforced strict fail-fast verification during `CLEAR_BOARD` in `_execute_3stage_trajectory_impl()`: checks return value of Cartesian elevation and joint IK fallback, halts immediately upon motion failure with `status = "CLEAR_BOARD_FAILED"`, `failed_stage = "CLEAR_BOARD"`, `requires_recovery = True`, `service_safe = False`.
   - Enforced strict `GRASP` stage verification in `_execute_3stage_trajectory_impl()`: evaluates grasp success, handles state-update attachment, verifies physical attachment of requested piece, and halts immediately with `status = "GRASP_FAILED"`, `failed_stage = "GRASP"`, `requires_recovery = True`, `service_safe = False` if grasp fails.
   - Enforced physical piece placement verification in both `place_piece()` and `execute_3stage_trajectory()`: piece must be in `ON_BOARD` or `RESTING` physical state, not in transient states (`OUT_OF_BOUNDS`, `FALLING`, `SETTLING`), nearest cell matches target destination within $25\text{ mm}$, and Z altitude matches board surface within $15\text{ mm}$ before declaring `piece_placed = True`. If piece tumbles or is lost during settle, returns `status = "PIECE_PLACEMENT_UNVERIFIED"`, `piece_placed = False`, `service_safe = True`, `requires_recovery = True`.
   - Converted `test_c9_retreat_collision` into a true PyBullet physical collision fixture with a zero-mass obstacle piece `black_cannon_0` positioned at `[-0.434, -0.102, 0.227]`, triggering physical contact detection in `CollisionGuard` during retreat and halting safely with `PLACE_SERVICE_RETREAT_FAILED`, `requires_recovery = True`, `service_safe = False`.
   - Enforced explicit non-manipulation default contract across `EXECUTE_3STAGE` and viewer `goToCell()`: missing/None grasp flags fail-safe strictly to `False` (`should_grasp = False`), preventing unintended piece manipulation when navigating diagnostic cells. Diagnostic `goToCell()` explicitly dispatches `grasp_piece: false`.
    - Added tests `test_c13` through `test_c20`. (Verified by `test_c1_normal_pick_retreat` through `test_c20_execute_3stage_explicit_grasp_executes_pick_and_place`).
14. **[B12] Phase 3 Board Orientation 90° Geometry Redesign (Corrective Geometry Gate):**
    - Authoritative 90° board rotation around $+Z_{\text{robot}}$ ($R = \begin{bmatrix}-1&0&0\\0&-1&0\\0&0&1\end{bmatrix}$, quat `[0.0, 0.0, 1.0, 0.0]`).
    - Aligned 9-column axis (320 mm) along $-X_{\text{robot}}$ and 10-row axis (360 mm) along $-Y_{\text{robot}}$.
    - Selected placement candidate $(d=15.0\text{ mm}, H=40.0\text{ mm}, Z=0.0\text{ mm})$ via exhaustive candidate evaluation: reach margin $+24.9\text{ mm}$ ($625.1\text{ mm} < 650.0\text{ mm}$), arm link clearance $7.69\text{ mm}$ (link 1 <-> link 3), condition number $21.79$, joint limit margin $9.23^\circ$.
    - Regenerated `shared/cell_reachability_dataset.json` with 90/90 cells solved and 0 collisions.
    - Updated physics transform engine, piece poses, world relocation, runtime cell mapping, viewer mesh, canvas texture, and dimension tape.
    - Implemented dedicated G90-01 through G90-25 test suite in `tests/unit/test_phase3_board_orientation_90.py`. (Verified by `test_phase3_board_orientation_90.py` 25/25 PASSED, `test_phase3_dynamic_board_placement.py` 13/13 PASSED).
15. **[B13] Phase 3 90° Board Migration Corrective: Browser Viewer Boot Recovery & Coordinate Contract Audit:**
    - Resolved fatal boot defect in `createBoardTexture()` where missing `y` coordinates in 4 `ctx.lineTo(x)` calls caused an unhandled `TypeError` during startup, aborting `initApp()` and leaving a blank canvas.
    - Unified coordinate contract `BoardCell(row, col)` with `row` $\in [0, 9]$ and `col` $\in [0, 8]$ across all frontend modules, standardizing `boardPointToXYZ(row, col)` and supporting object overloads `{ row, col }`.
    - Removed stale 0° geometry formulas from `goToCell()` and telemetry handlers in `robot-3d-viewer/main.mjs`, replacing them with canonical 90° formulas ($robX = -0.360 - d/1000 - u$, $robY = -v$, $robZ = 0.0105 + z_{\text{off}}/1000$).
    - Updated `computeGeometricPrecheck()` with canonical 90° extrema ($X_{\text{far}} = 520.0 + d\text{ mm}$, $Y_{\text{far}} = 180.0\text{ mm}$) and synchronized precheck UI readouts with dynamic board placement.
    - Updated `robot-3d-viewer/ruler.mjs` special Z markers (Cột 0: 200mm, Tâm: 360mm, Cột 8: 520mm) and 4-edge hit proxies (Near: 176.5mm, Far: 543.5mm along Z; Left: -205mm, Right: +205mm along X).
    - Verified complete 90-cell parity and 32-piece layout placement in `tests/unit/test_viewer_coordinate_contract.mjs`.
    - Verified live browser boot and WebGL render pipeline via automated headless Chrome CDP test in `tests/unit/test_viewer_browser_smoke.mjs`.
16. **[B14] Phase 3 90° Coordinate Semantics & Backend Contract Corrective (S90 Corrective Gate):**
    - Eliminated remaining legacy row/col semantic inversions across backend, frontend, physics, and telemetry.
    - Defined `BoardCell` frozen dataclass with strict Xiangqi bounds validation $[0..9] \times [0..8]$, sequence indexing, and unpackability.
    - Standardized public API signature everywhere strictly as `(row, col)` with $row \in [0, 9]$ (0 = Black home side, 9 = Red home side - game meaning only) and $col \in [0, 8]$ (col 0 = near side of robot, col 8 = far side of robot).
    - Normalized `robot_xyz_to_nearest_cell` to return canonical `(nearest_r, nearest_c, dist_m)`, eliminating manual coordinate swaps across `runtime.py` and unit tests.
    - Exported `T_robot_from_board` (4x4 SE(3) matrix) in `BoardPlacementState.to_dict()` and aliased `to_telemetry_dict`.
    - Updated `robot-3d-viewer/board.mjs` (`boardPointToXYZ` and `setScenePlacement`) to directly consume authoritative `T_robot_from_board` and `board_yaw_deg`, eliminating hardcoded axis swaps.
    - Renamed DOM readout IDs in `index.html` and `main.mjs` to `#readoutNearGridDepth` and `#readoutFarGridDepth`, and updated selection dropdowns to honest base/depth labels.
    - Created comprehensive regression suite `tests/unit/test_phase3_coordinate_semantics_contract.py` (11/11 tests PASSED) and expanded `tests/unit/test_viewer_coordinate_contract.mjs` (8/8 tests PASSED).
17. **[B15] Phase 3 Final G90 Corrective: Full Route Fail-Fast Integrity, Exhaustive Coverage Reporting & Authoritative Placement Extrema:**
    - Enforced strict fail-fast in `validate_full_board_routes()`: if `CLEAR_BOARD` stage fails, the route terminates immediately with `route_passed = False`, `failed_routes += 1`, `worst_route` records stage `"CLEAR_BOARD"`, and `SERVICE_RETREAT` is never evaluated or executed.
    - Implemented explicit validation modes in `validate_full_board_routes()`: `SAMPLED` (`exhaustive=False`, status `FULL_BOARD_ROUTES_SAMPLE_SAFE`) and `EXHAUSTIVE` (`exhaustive=True`, status `FULL_BOARD_ROUTES_EXHAUSTIVE_SAFE`).
    - Added full coverage telemetry fields: `validation_mode`, `possible_ordered_routes` (8010), `tested_routes`, `passed_routes`, `failed_routes`, `coverage_fraction`, `exhaustive`, `all_routes_safe`. Enforced accounting invariant `passed_routes + failed_routes == tested_routes`.
    - Eliminated hardcoded extrema (`520 + d`, `180`, `200 + d`, `176.5 + d`, `543.5 + d`) from `robot-3d-viewer/main.mjs`, dynamically computing extrema from transformed cell coordinates and board corners via authoritative `BoardPose`.
    - Added dynamic `d_max_for_current_h_mm`, `h_max_for_current_d_mm`, `near_grid_depth_mm`, and `far_grid_depth_mm` to `BoardPlacementAnalyzer.compute_geometric_precheck()`.
    - Corrected reach metric description in `index.html`, viewer, and documentation: strictly labeled 625.1 mm as "Max flange approach distance" ($D_{\text{flange\_app}} = 625.1\text{ mm} < 650.0\text{ mm}$), distinct from TCP distance ($550.3\text{ mm}$).
    - Added comprehensive test suite `tests/unit/test_phase3_final_g90_corrective.py` covering G90F-01 through G90F-14 (14/14 tests PASSED).

---

## OPEN_BLOCKERS
* **Total Count:** 3 (Passes D, E, F)
* **Pass D:** Reset transactionality (ensuring atomic cleanup during system/component resets).
* **Pass E:** Viewer safety UX (front-end safety state guards and error indicators).
* **Pass F:** Final closure (end-to-end integration and simulation phase sign-off).

---

## UNVERIFIED_CLAIMS
* **Real Camera Homography:** The homography transform in `perspective.npy` was calibrated for a physical camera and is unverified against the virtual 3D board scene. (Deferred to Phase 4 calibration).
* **Physical FR3 Robot Interfacing:** `RealFR3Backend` and Ethernet RPC communication with physical hardware remain unverified in the physical world. (Deferred to Phase 4).

---

## TEST_EVIDENCE
* **Python Unit Tests:** 165/165 Phase 3 specific tests PASSED (100% pass rate)
  * `tests/unit/test_phase3_final_g90_corrective.py`: 14 passed (G90F-01 to G90F-14)
  * `tests/unit/test_phase3_coordinate_semantics_contract.py`: 11 passed (S90-01 to S90-13)
  * `tests/unit/test_phase3_board_orientation_90.py`: 25 passed (G90-01 to G90-25)
  * `tests/unit/test_phase3_final_master.py`: 79 passed (including Pass A/A.1/A.2 tests, Pass B/B-Corr tests, and Pass C tests c1–c20)
  * `tests/unit/test_phase3_final_closure.py`: 11 passed
  * `tests/unit/test_phase3_isolation_and_fail_fast.py`: 12 passed
  * `tests/unit/test_phase3_dynamic_board_placement.py`: 13 passed
* **Node.js Viewer Tests:** 7/7 suites PASSED (100% pass rate)
  * `test_viewer_single_motion_authority.mjs`: PASSED
  * `test_viewer_profile_binding.mjs`: PASSED
  * `test_viewer_coordinate_ruler.mjs`: PASSED
  * `test_viewer_gripper_and_telemetry.mjs`: PASSED
  * `test_viewer_canvas_api.mjs`: PASSED
  * `test_viewer_coordinate_contract.mjs`: PASSED (8 tests)
  * `test_viewer_browser_smoke.mjs`: PASSED (V90-01 to V90-05)

---

## NEXT_ALLOWED_WORK
* Pass D — Reset transactionality (ensuring atomic cleanup during system/component resets).

---

## DO_NOT_ADVANCE_TO
* **PHASE 4:** Physical FAIRINO FR3 robot hardware connection, power-on, or physical actuation.


## 2026-11-05 need-review capsule r2 (scoped)

Ported portable capsule onto current origin/need-review30649c4, preserving newer two-human/robot and exit implementation. Built new NeedReview-r2 ZIP (386975679 bytes), SHA256 dc9bbc820b4e479c904c084c9619439d743dc4e8d037a0394bfd04fa327f1754. README first heading links this distinct release and describes all four modes, O/localhost Black client and main/host exit confirmation.

TEST_EVIDENCE: 105 focused tests PASS (93parallel+12serial), packaged CPU model/engine/render smoke PASS, untouched ZIP Unicode relocation PASS including actual 32-piece virtual world, JS/WASM, real bundled Black child room/state/render/request and main menu/exit dialog. No physical/clean-second-PC/full-suite claim. Historical LAST_REVIEWED_HEAD unchanged; full evidence reports/need-review-capsule-20261105/REPORT.md.



## 2026-11-05 Windows capsule — scoped packaging delivery

At need-review eb69457 plus local capsule changes, built dist/Xiangqi-Capsule-Windows-x64-20261105.zip, SHA256 c5d1a6570d41954ffbeb0dbc0fb7451b275fa943f2bc09fbd1f61606f1120f5e. One START.bat, isolated app-local CPython/CPU dependencies, supplied vision weights, local engine/viewer/font, source/asset manifest; no event-PC setup step. No original journals/credentials copied. Small font/native URDF path adaptations; motion/recovery/calibration behavior unchanged.

TEST_EVIDENCE: 66 focused tests PASS exit0; actual packaged --smoke PASS; untouched final ZIP extracted into Vietnamese/spaces path and real 32-piece virtual-world/local-engine/JS-WASM/app-menu-shutdown acceptance PASS; VC DLLs actually loaded app-locally. No physical or clean-second-PC acceptance, no entire-suite/whole-branch claim. See reports/windows-capsule-20261105/REPORT.md. Historical LAST_REVIEWED_HEAD unchanged; no commit/push.


## 2026-11-05 final capsule r2 — delivery branch corrected

User selected final. Merged need-review55c5fd5 into final, preserving current robot-PvP/session/exit code and capsule runtime. New final-r2 ZIP386748507bytes, SHA256 c0616011ef822978d269744516d1f99c0796e76419bb28cdab49374d4c227e15.105 tests rerun PASS; untouched final ZIP Unicode relocation/bundled models/world/Black child/menu-exit checks PASS. README first heading downloads final-r2. No physical/second-PC/full-suite claim; LAST_REVIEWED_HEAD unchanged. Evidence: reports/final-capsule-r2-20261105/REPORT.md.


## 2026-11-07 final — user handbook (documentation only)

Scope baseline: `005f95539531c32601232cdeeec3cca4185f32d9` on `final`. Replaced README's developer-oriented overview with a Vietnamese operator handbook covering capsule/source startup, three environments/four game modes, actual mouse/keyboard controls, camera calibration, physical enable, stop/session/end flows, pre-pick retry versus post-motion reconciliation, diagnostics and evidence collection. Replaced obsolete `docs/USER_MANUAL_QUICKSTART.md` with a pointer to the handbook, removing outdated centre-of-piece calibration, dry-run/disconnect and motion-error recovery advice. Download/video links retained; release ZIP is unchanged.

VERIFIED_FIXED (documentation scope only): stale quickstart instructions retired. No runtime/configuration/calibration changes or hardware calls.

TEST_EVIDENCE: `git diff --check` PASS (exit 0); static Markdown validation PASS (exit 0, 66 local file/explicit-anchor links, balanced code fences/table row endings). Download asset matched the GitHub release metadata. Controls and failure guidance checked against current launch/menu/input/session/hardware/camera/journal code. Application tests, Windows UI, clean second-PC, camera and FR3 physical acceptance NOT RUN for this documentation-only change. Existing physical and broader-regression gaps remain OPEN. Historical `LAST_REVIEWED_HEAD` is intentionally unchanged; this is not a whole-branch functional review.

## 2026-11-09 final — simulation placement view + telemetry ownership

Scope: uncommitted work from the 2026-11-09 session on `final` (baseline `9b4c515`), completed and verified here. Virtual/simulation paths only; no robot, camera or gripper access.

VERIFIED_FIXED
- Board placement is now computed once in Python and broadcast. `VirtualXiangqiSimulation` adds `placement_state` to the `board_placement` analysis packet (`src/simulation/runtime.py`), `BoardPlacementAnalyzer` exposes that same state (`src/simulation/placement.py`), and the viewer stopped re-deriving geometry: `robot-3d-viewer/main.mjs` loses 271 lines of local transform math and `ruler.mjs` 143, both consuming the new read-only `robot-3d-viewer/placement_metrics.mjs`. That module rejects non-rigid matrices (orthonormal rotation, determinant 1, unit scale) instead of drawing a skewed board.
- Busy viewer port on Windows: `ViewerHTTPServer.allow_reuse_address` is now False on `win32`. With `SO_REUSEADDR`, Windows reports a conflict with a listening socket as WSAEACCES (10013) instead of WSAEADDRINUSE, so the VIRTUAL startup fallback never picked an ephemeral port and the session returned "Viewer unavailable" while a free port existed.
- Telemetry coalescing raised AttributeError on non-object JSON payloads inside the dispatch path; sequence comparison now treats them as sequence 0 (`_packet_sequence`). This predates the session (introduced in `57aba7d1`).
- `TelemetryPublisher` start failure now chains the socket cause, which the virtual port-retry predicate inspects.

TEST_EVIDENCE
- Focused run exit 0: `test_virtual_telemetry_startup.py` 6 PASS (both viewer_busy cases), `test_telemetry_liveness.py`, `test_simulation_placement_metrics.py`, `test_simple_launch_sync.py`; 57 tests PASS via `tools/test_fast.ps1 -Workers 2`.
- Viewer JS: `node --test` over board-mesh, placement-integrity and placement-metrics files = 3/3 PASS. These `.mjs` tests spawn `python`, so the venv must be on PATH.
- Session evidence kept in `reports/simulation-final-20261109/`: one virtual move 23.5 s, joints `0,-45,90,-45,-90,0` -> `0,-70,60,-80,-90,0`, 117 distinct joint poses over the websocket, 353 accepted viewer robot packets and 0 rejected; browser probe 13 distinct rotator poses.
- Full suite `tools/test_fast.ps1 -Mode Balanced`: 22 failed / 1148 passed. A clean HEAD worktree (`9b4c515`) reproduces 21 of them exactly (15 camera/visual integration, 2 `test_physical_ui_latency`, 4 across arm-reconnect/viewer-startup/ai-home); the 22nd passes alone and only fails under full-suite load. No failure is introduced by this work.

NOT RUN: physical FR3/camera/gripper acceptance, clean second PC, full browser game session end to end.

OPEN: the 21 baseline failures above. `final` was already red before this session; a green focused run is not a green branch.

## 2026-11-10 fix/fix-capsule — VS ROBOT camera and viewer

Scope is the working tree at `3fd13f9`. The November 10 source logs showed missing ONNX and YOLO weights, manual calibration fallback, and physical VS ROBOT entering gameplay without a camera monitor. Restored the three Git-ignored model blobs from `18e67fc^` and verified their Git hashes.

VERIFIED_FIXED (offline): physical VS ROBOT validates the weights and gets grid approval before robot enable. The calibration checkbox selects manual mode, and the default path tries the automatic preview. The gameplay camera window closes on its UI thread before worker teardown. The viewer imports the virtual contact constant and uses semantic gripper labels.

TEST_EVIDENCE (Windows, .venv312 Python 3.12.10, DRY_RUN=1): `tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_vsc_v3_lifecycle.py,tests/unit/test_vsc_v3_namespace.py,tests/unit/test_vsc_v3_session.py,tests/unit/test_hvr_mode_dispatch.py,tests/unit/test_camera_calibration_startup.py,tests/unit/test_f2_camera_and_frame_restart.py` PASS, exit 0, 59 parallel + 1 serial. Eight gripper tests passed via Node. Recorded-frame camera workflow PASS, exit 0, in `logs/camera-workflow-offline-20261110.log` using the restored weights and mocked camera/HighGUI. Headless Edge reproduced the viewer error on HEAD and loaded both CAD fingers on the patched tree.

NOT RUN: live camera, controller, physical motion, full regression and packaged release validation. The existing perspective artifact was preserved. `LAST_REVIEWED_HEAD` remains the historical whole-branch baseline.

Local source runtime follow-up: `.venv312` uses PyTorch 2.14.0+cu132, torchvision 0.29.0+cu132 and ONNX Runtime GPU 1.30.0. `VISION_DEVICE=auto` is the existing default. Offline recorded-frame inference verified that VS ROBOT's YOLO predictor uses CUDA and both ONNX sessions retain CUDA as their first provider. Five warmed runs per model gave CPU → GPU median latency of 230.2 → 28.8 ms for YOLO, 287.3 → 26.3 ms for layout and 9.3 → 9.7 ms for pose. This checks local model execution only. Live game latency and physical hardware acceptance are still open.

Stash integration at `42877e9`: kept the incoming English viewer controls and removed obsolete tool-output labels. The stashed camera changes and gripper timings were preserved. Windows Python 3.12.10 in dry-run passed 24 tests (23 parallel + 1 serial, exit 0) via `tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_hvr_mode_dispatch.py,tests/unit/test_vsc_v3_lifecycle.py,tests/unit/test_camera_calibration_startup.py,tests/unit/test_offline_mouse_confirmation.py`. Nine focused Node viewer tests and the headless Edge CAD gripper probe also passed. Physical acceptance remains open.

VS ROBOT edge-pick follow-up: its camera filter and robot adapter read the same 10 mm margin per axis. The PvP resolver prechecks measured coordinates with the actual robot pose converter before handing them off. The other-mode adapter retains its 6 mm cap. VERIFIED_FIXED (offline): the logged rook target at grid (7.768, -0.201) passes the VS ROBOT bound, fails the shared 6 mm bound, and a target beyond 10 mm is rejected at handoff. TEST_EVIDENCE: Windows Python 3.12.10, DRY_RUN=1, `tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_vsc_v3_namespace.py,tests/unit/test_vsc_v3_session.py,tests/unit/test_visual_pick_estimator.py,tests/unit/test_connection_calibration_split.py,tests/unit/test_physical_placement_consistency.py` PASS (57 parallel + 1 serial, exit 0). Physical clearance for the expanded edge region is NOT RUN.

## 2026-11-11 fix/fix-capsule — HOMECHESS manual-reset recovery

Scoped implementation at baseline `4c0e6a2`: Ctrl+F8 bindings retired. Failed VS ROBOT moves/pick-place tests request measured vertical clearance then the frozen taught HOMECHESS waypoint, retaining pending move/FEN and gripper output. After fresh TCP/joint/frame/idle proof, the operator removes the piece, restores the full old board including captures, withdraws hands and presses R to retry exactly that move. H requests one deliberate HOME recheck if parking failed. Stale-operation identity, unknown RPC outcomes, active stop/gripper gates and post-commit errors cannot authorize automatic replay. Shared V/F2 replaces the removed shortcut's explicit read-only stop confirmation without weakening measured-stop requirements.

TEST_EVIDENCE: 253 focused tests PASS (252 parallel + 1 serial), exit 0; final recovery hardening run 144 tests PASS, exit 0 (overlapping scope, two additional driver-binding tests). Independent scoped review APPROVED, 9.5/10. Actual pygame normal/waiting-manual/HOME-failed renders PASS. Compilation, diff and scoped graph-impact checks PASS. Full-regression result and exact commands: `reports/home-chess-recovery-20261111/REPORT.md`; no whole-branch green claim. No calibration/configuration/kinematics changes and no physical actuation. Physical path/clearance/live camera/controller acceptance and packaged release validation NOT RUN. Historical `LAST_REVIEWED_HEAD` unchanged.

## 2026-11-11 fix/fix-capsule — README R/H operator guide

Documentation follow-up to `93fd21a`: README now provides numbered physical VS ROBOT HOMECHESS/manual reset/R retry steps, plain-language H/controller explanation, pre-pick R/X and F8 scope, and source-versus-old-capsule notice. Production code unchanged. Fresh `tools/test_fast.ps1 -Workers 2 -Tests tests/unit/test_home_chess_recovery.py,tests/unit/test_vsc_home_recovery.py,tests/unit/test_stop_recovery_controls.py`: 144 PASS, exit 0, 7.23 seconds. Static Markdown check: 63 local/explicit-anchor links PASS, balanced fences and unique HOME anchor; diff check PASS. Scoped documentation review completed. Physical acceptance and whole-suite green remain unverified as recorded above; historical `LAST_REVIEWED_HEAD` unchanged.

## 2026-11-11 fix/fix-capsule — automatic enable after startup inspection

At user baseline `973da04`, an interrupted physical journal sets recovery flags; AutomaticPhysicalStartup permanently cancelled before V could verify the board. Actual V later clears all four flags while auto-startup stays finished/cancelled. Frozen-source + temporary-journal reproduction VERIFIED this exact zero-attempt failure; live session `20261111_160259_6d147654` confirms physical PvP selection, inspection required, successful camera resume and no enable events. The cancellation clause predates HOME recovery (`4c0e6a2`). Original robot-stop cause remains UNKNOWN.

VERIFIED_FIXED offline: transient startup prerequisites now wait and resume through existing verification, while session cancellation stays terminal. Added deduplicated wait/start/cancel reasons, frozen stop generation and current guard checks. Unverified stop/unknown enable outcomes do not cause automatic replay; user global stop changes and stashes preserved. TEST_EVIDENCE: 77 focused tests PASS, exit 0, 19.45 seconds, plus frozen baseline probe PASS. Scoped review APPROVED. Exact evidence in `reports/auto-enable-20261111/REPORT.md`. No live robot/camera operation or app restart; active PID 24072 still had imported old code. Hardware acceptance/full suite/new capsule/push NOT RUN. Historical `LAST_REVIEWED_HEAD` unchanged.
## 2026-11-11 fix/fix-capsule — physical PvP V recovery

Scoped baseline `8255afd`: a camera-postcheck failure can leave no controlled-stop request, so V confirms the board but cannot satisfy the hardware approval gate. VERIFIED_FIXED offline by scoped operator-only fresh idle observation; no stop/HOME/gripper/enable command or implicit retry. Real stops supersede temporary observations, whose cleanup cannot erase a newer stop. PvP status/README distinguish missed pickup, completed move with failed perception and partial capture. TEST_EVIDENCE: 99 focused tests PASS, exit 0, 17.88 seconds, including 15 new integration cases; scoped independent review APPROVED. Expanded PvP run: 85 PASS, 2 pre-existing translated-name assertion failures. Report: `reports/pvp-move-recovery-20261111/REPORT.md`. Hardware acceptance/app reload/full suite/new capsule/push NOT RUN; calibration and user config change preserved. Historical `LAST_REVIEWED_HEAD` unchanged.
## 2026-11-11 fix/fix-capsule — automatic recovery state, no manual arm confirmation

Scoped baseline `cd01b66`: manual arm/gripper confirmation API and UI calls removed. V/Continue/F2 refresh state automatically without actuator commands; read-only startup stops may settle on fresh idle data, while unsuccessful dispatched stops, active pulses/workers and controller errors remain blocked with concrete diagnostics. Physical PvP old-board recovery now resumes in one V if the camera baseline succeeds; error flags are checkpointed atomically and restored on journal failure. TEST_EVIDENCE: 126 focused tests PASS, exit 0, runner 15.96 seconds; scoped review APPROVED. Separate legacy expanded-run failures and unmocked GUI-startup camera attempt are recorded in `reports/automatic-recovery-state-20261111/REPORT.md`. Physical actuation, live acceptance, user-app restart, full suite, capsule and push NOT RUN. Existing user config preserved; historical `LAST_REVIEWED_HEAD` unchanged.
## 2026-11-11 fix/fix-capsule — full-open pickup, sustained CLOSE signal

At baseline `3d50e27`, removed only the pre-pick safe-gap closure and retained DO1 CLOSE through lift/transport until release/cancellation. Post-release gap and numerical timings remain. Added held-output lifecycle tracking, bounded StopMotion-before-OFF cancellation and guarded cleanup/exit; unknown stop/OFF cannot be promoted to success or replay StopMotion. TEST_EVIDENCE: 282 related tests PASS (275 parallel +7 serial), exit 0, runner 19.55 seconds; independent review APPROVED, AST/diff checks PASS. Report: `reports/gripper-close-hold-20261111/REPORT.md`. Actual gripping force, continuous-duty/current-limit suitability and physical acceptance remain UNVERIFIED; no hardware actuation/user-app restart/full suite/capsule/push. Existing user config whitespace preserved; historical `LAST_REVIEWED_HEAD` unchanged.
