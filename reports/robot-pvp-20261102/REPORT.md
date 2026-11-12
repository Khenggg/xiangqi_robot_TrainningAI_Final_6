# Separate two-human robot mode — isolated candidate

Publication update2026-11-05: feature changes below have now been committed and
replayed on origin/need-review@eb69457, preserving newer remote documentation.
The original snapshot description and test results below are historical.
Fresh verification and publication details: `PUBLISH_20261105.md`.

Branch: `codex/robot-pvp-20261102`.
Worktree: sibling `xiangqi_robot_pvp_20261102`.
Local baseline snapshot: `8a4522328c74b38b5a9627837578eef39515a379`, parent
`18e67fc9006a91a2a32c4c861974760089a687de`. Snapshot preserves the source
checkout's dirty tracked/untracked files; original index/branch/source were not
reset or committed. Feature changes are currently uncommitted in this worktree.
Seven affected source files in the original checkout still match the snapshot's
normalized blobs: `source-preservation.json`.

Donor: `origin/feature/nguoivsnguoifinal@73af0f182d62f39d4e0f7ce66abe488e9b8782e8`.
User confirmed two GUI humans with one robot executing both sides. Selective port
of room code, localhost roles and Black view; no whole-branch merge/cherry-pick.

## Implemented behavior

- New `HUMAN_VS_HUMAN_ROBOT` profile: robot execution/camera when physical;
  AI/self-play disabled, mouse policy ROBOT_COMMANDS. Existing mouse-only PvP is
  unchanged. Board-only preset rejects this new robot mode.
- New menu buttons: **2 NGƯỜI + ROBOT**, **VÀO PHÒNG / NGƯỜI ĐEN**. No difficulty
  selection. Host header always shows room code. O opens the Black window.
- Host owns Red, GameState, journal and the only hardware connection. Client
  owns Black, shows a 180-degree view and only sends requests. No client board
  commit or SDK/controller import.
- Both colors use retained `execute_ai_move` execution (no AI engine query),
  physical/camera gates, pending identities, capture clearance and durable commit.
- Epoch/revision/session/generation/request-ID checks, legal-cell/move checks,
  bounded queues/frames, bounded peer threads, no retry/replay by network.
  Worker rechecks state, peer and stop generation before creating a transaction.
- Network disconnect blocks new requests; started work remains with the existing
  execution/recovery owner. Rejoin receives the authoritative current board.
- Slow post-commit baseline stays on MotionWorker. Baseline failure preserves
  the committed move and pauses subsequent GUI moves pending V recovery.
- Input suppresses SPACE/manual emergency/rollback/pick tests in this mode.
  Host surrender belongs to Red even during Black turn. Stale selections are
  invalidated on both host and client when board/session changes.
- Room closes after stop/worker retirement in HardwareManager cleanup. The
  companion window can remain disconnected for the user to close/rejoin.

## Verification

Windows, Python 3.12.10, pytest 9.1.1, DRY_RUN=1, ROBOT_BACKEND=VIRTUAL,
PYTEST_ADDOPTS=-x; project test_fast.ps1 with two workers and numerical thread caps.

Focused subsystem run: **PASS, exit0, 116 tests** (114 parallel + 2 serial), 23.4s.
Exact command/output: `focused-tests.txt`. Includes new mode, rooms, actual main
event loop, existing session modes/user flows/home/controls/retry, startup and
hardware recovery diagnostics. The final narrow post-commit/selection changes
were then rerun on the three new test files below.

```powershell
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_robot_pvp.py,tests/unit/test_robot_pvp_main_ui.py,tests/unit/test_pvp_room_and_client.py
```

Final narrow outcome: **PASS, exit0, 30 tests**, runner 10.8s;
see `final-new-mode-tests.txt` (28 parallel + 2 serial).
Tests use fake robot/camera and real localhost sockets;
no physical hardware. They cover both colors and capture with PHYSICAL journal,
no early FEN/turn commit, camera fail before/after motion, duplicate/stale/invalid
requests, cancellation before dispatch, reconnect, baseline failure, source
selection, Red resignation, bounded parser, peer/thread cleanup, Black Pygame
click coordinates and heartbeat behavior.

`test_robot_pvp_main_ui.py` runs actual main.py launcher/event loop headlessly:
select new menu -> host Red mouse source/destination -> Black socket request ->
two durable turns -> controlled virtual shutdown -> room registry deleted.
Backend motion alone is mocked. Host screenshot: `host-after-two-turns.png`.
Menu/client previews: `new-mode-menu.png`, `black-player-view.png`.

Broad regression command `.\tools\test_fast.ps1 -Workers 4`: **INTERRUPTED/NOT
PASS, exit1**. 1093 parallel items collected, progress reached 26% with failure
markers and long-running geometry tests. Stopped with Ctrl+C; no final failure
trace/count was produced. Failure origin remains UNKNOWN; do not infer all
failures pre-existed or declare a whole-suite pass. No remaining pytest process
was found afterward. Slow-marked tests and physical tests NOT RUN.

Python compileall and scoped git diff --check: PASS, exit0.
Graph project indexed before edits, architecture and execution call path read.
Final detect_changes attempted twice but returned `Transport closed`; graph blast
radius unavailable. Exact source/diff review and focused execution evidence used.
Read-only review found stale client selection and wrong host resignation winner;
both corrected with regression tests. Final follow-up review also found no
scoped blocker in worker post-commit handling or host selection-token checks.

## Local runtime preparation

Ignored venv and node_modules are local junctions to the existing installation;
not committed. Six ignored model/calibration files copied unchanged from source,
SHA256 checked in `runtime-assets.json`, including perspective.npy. No calibration
values changed, no new calibration, no `.env` or session database copied.
These machine-local assets must be provisioned separately on another workstation.

## Remaining limits

Not merged/pushed and no runtime switch in the original physical application.
Actual camera/FR3/gripper operation and full physical game NOT VERIFIED. A mock
motion result or GUI animation is not hardware proof. Only one physical host may
own the real FR3; never run physical hosts from both worktrees simultaneously.
Existing controller faults require their own recovery, not failed-session deletion.
Full regression needs terminal results and triage before a merge-ready claim.

Usage: `docs/architecture/TWO_HUMAN_ROBOT_MODE.md`.
