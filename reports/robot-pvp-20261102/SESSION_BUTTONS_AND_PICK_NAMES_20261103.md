# Session buttons and named physical-pick errors

Scope: isolated robot-PvP worktree; original checkout preserved. No physical
commands, controller reset/enable, live application input or restart performed.

## Requested behavior and findings

User confirmed SURRENDER should end the game and NEW GAME should create a new
opening after the real board is arranged; current controls sometimes appeared
stuck waiting for stop until a robot power cycle.

VERIFIED source/test issues:

- Busy worker and visual-pick pause filters could drop SURRENDER clicks in
  non-self-play modes. Immediate legacy surrender also used the current turn,
  not the human host role, and could invalidate a still-running move.
- A controller-ACKed stop could time out while a camera/motion worker remained
  active. The unsafe result then remained cached even after the worker ended
  and fresh idle data became available. This case is deterministically reproduced
  with fake hardware; actual reported wait causality is not fully established
  from available logs.
- NEW GAME already preserved unresolved physical transactions. Waiting messages
  needed to distinguish actual stop uncertainty from a pending move requiring
  board reconciliation. V/Continue while ending must not retry a physical move.

## Changes

- SessionControl.request_surrender records a deferred end request. New commands
  are blocked, an already-running piece finishes, AI calculation can be retired,
  then the existing stop/idle barrier and any pending reconciliation must finish
  before saving the result. A checkmate already committed by that piece wins over
  a later attempted replacement with RESIGN. Duplicate requests do not repeat end.
- Main and InputHandler admit host surrender before busy/pick-paused filters.
  Host is Red in HvR/new robot-PvP; old mouse-only PvP uses the side to move.
- While reset/surrender is pending, V and Continue only reconcile after safe stop;
  Y and other retry controls cannot dispatch another physical move. Pending
  physical transactions are retained until old/expected full-board verification.
- ControlledStopCoordinator may recheck an acknowledged stop using two distinct
  fresh idle observations after worker/gripper quiescence. It never sends another
  StopMotion, clears an unknown/unacknowledged outcome, bypasses ERROR/stale data,
  or re-enables motion. Failures include a live settling diagnostic in the wait
  message. Existing manual confirmation remains available when proof is missing.
- NEW GAME retains stop/pending gates and camera verification of the new opening.
  Old RESIGN reason is preserved in the archived outcome and cleared for the new
  game. Physical reset remains paused pending opening-board verification and
  separate explicit operator enable; it does not rearrange real pieces.

## Named pick error

The user's 18:45:17–20 log rejects captured target col1,row9 at6.1–6.3mm offset,
over the6.0mm limit. Read-only PHYSICAL journal at PREPARED shows:

- Black cannon `black_cannon_0`, b2 -> b9.
- Captured `red_knight_0`, symbol r_N: Red Knight at b9.

Warnings and the pause/status now include expected piece name, logical square,
zero-based col/row and role (moving versus captured removal). Example:
`Quân bị ăn cần lấy ra: Mã Đỏ (r_N) tại ô b9 (cột=1, hàng=9)`.
Structured retry event includes expected_pick_cells and description. Names come
from the pending FEN/identity, not from an unvalidated YOLO class. The6.0mm
threshold, calibration, target positions, consensus and acceptance are unchanged.

## Validation

Windows, Python3.12.10, pytest9.1.1, DRY_RUN=1 / ROBOT_BACKEND=VIRTUAL,
PYTEST_ADDOPTS=-x, project runner with2workers and numerical caps.

1. PASS exit0:73 tests (72parallel+1serial),56.68s. Command/output:
   `session-buttons-tests.txt`; tests session_buttons, pick_target_retry,
   session_user_flows, robot_pvp, robot_pvp_main_ui and reliability_recheck.
2. Final stop/diagnostic follow-up PASS exit0:39tests,24.34s;
   `final-stop-checks.txt`, targeting session_buttons, fresh_session_startup,
   pick_target_retry and recovery_block_diagnostics.
3. Final actual UI follow-up PASS exit0:14tests (12parallel+2serial),18.1s;
   `final-buttons-ui-tests.txt`, targeting session_buttons + robot_pvp_main_ui.
   Actual main event loop, real localhost room and mock backend: two GUI moves,
   host SURRENDER, saved Black winner, NEW GAME, epoch change/opening Red turn,
   room cleanup. Motion/controller only mocked.

Tests also cover busy and pick-paused surrender, late ACK settling without stop
replay, unknown/error/stale/duplicate/gripper rejection, pending transaction
retention, no Y/Continue movement during deferred end, preserved terminal result,
and captured Knight name/role/square. Initial test-only log-capture level issue
was corrected before the passing run.

Scoped read-only code review reported no blocker in the latest implementation.
compileall and git diff --check PASS exit0. Graph discovery/trace/detect attempted,
unavailable (Transport closed); exact-file/caller review used. No full regression,
live button acceptance or physical recognition/motion validation is claimed.
Changes require a future normal application launch; the running process was not
modified. No recommendation to power-cycle a robot to bypass these gates.
