# Camera, robot and FEN recovery

The application keeps the live camera visible during a measured pick. The exact
measured image appears as an inset and expires eight seconds after first display.
The diagnostic no longer replaces the video. D in pick-test mode clears the inset.

Robot occupancy checks use fresh unfiltered best.pt boxes. In height/ring mode,
they rebuild the camera geometry from the current board and intrinsics and project
onto the piece-height plane. Unknown acquisition, inference or geometry cannot
authorize an empty capture square. Nonzero motion responses, including 112, stop
before further movement or gripper actions.

RPC requests have a real 10-second transport timeout and no automatic resend.
Reconnect waits are limited to five seconds. A lost response means command
completion is unknown, even when the arm has physically moved. The client retains
the pending FEN and releases the worker instead of sending the same command again.

After a communication fault, subsequent arm commands and energized gripper
outputs remain locked. Turning outputs LOW for cleanup is allowed. V/Continue
checks read-only communication and a fresh realtime state packet received after
the probe. The packet must show stopped motion, an empty queue, no errors/safety
stops and both gripper outputs LOW. A missing/stale packet keeps the lock. These
checks run off the UI thread so camera display remains live during recovery.

When the controller is ready, V/SPACE/Continue compares the physical board with
the old FEN and the expected pending position. A completed verified move commits
once. An uncompleted move can retry only after the old board is verified. With a
disconnected robot, the move remains pending until the operator moves it by hand
and confirms it; the client does not advance FEN just because AI found a move.

Rollback cancels the previous pending command and requires the restored physical
board to match before play resumes. New Game discards the previous rollback
snapshot. Epoch, base-board and intent guards reject stale commits/acquisitions.
Recognized human layouts must match exactly one legal complete Red successor;
several changed pieces or an unknown/missing unrelated piece cannot start AI.

Engine startup/search use bounded queues. Timeout, EOF and malformed output are
engine errors rather than checkmate. FEN remains unchanged and V/Continue retries
with a fresh engine session. Only a genuine position without legal Black moves
can end the match for that reason.

Remote synchronization runs in one background worker. It retains the latest FEN,
keeps each job tied to its room, retries transient errors and shows missing-room
or rejected updates. Closing a match waits for its final FEN acknowledgment.
Generic cleanup cannot overwrite a checkmate/resignation result.

Pending remote jobs are written atomically to `logs/simulation-outbox.json`.
The file stores protocol payloads and an account fingerprint, never the bearer
token. Startup loads it without making HTTP requests; the main loop schedules
remaining work. Shutdown waits at most two seconds for the worker and retains
unacknowledged work. A malformed file or a different account is left untouched
and surfaced as a persistence error. `XIANGQI_OUTBOX_PATH` can override the path.
Starting a deliberate new game discards a draft FEN that never had a room; jobs
already assigned to an old room keep that room's identity.

Offline verification:

```powershell
& .\.venv312\Scripts\python.exe -X utf8 scripts/run_offline_tests.py
& .\.venv312\Scripts\python.exe -X utf8 scripts/check_runtime.py
```

The test runner denies unmocked HTTP. The suite uses mocked camera/robot/provider
interfaces, synthetic projections and isolated UCCI subprocesses. Runtime
preflight loads local models and imports; it does not connect to camera or arm.
These checks do not establish physical camera, controller, grasp or provider
acceptance. Commissioning still needs the actual camera/controller and a known
board, including controller packet freshness and edge/corner placements.
