# Separate two-human / one-robot mode

Mode: selective donor port
Risk: high-risk — physical command entry boundary; verification uses mocks/simulation only
Donor: origin/feature/nguoivsnguoifinal@73af0f182d62f39d4e0f7ce66abe488e9b8782e8
Target: need-review@18e67fc plus preserved dirty worktree

User selected two people choosing GUI moves, one robot executing both colors.
Existing HUMAN_VS_HUMAN remains mouse-only; new HUMAN_VS_HUMAN_ROBOT is separate.
No full merge, controller actuation, calibration changes or automatic enable/HOME.

- [ ] Dedicated profile, host input/controller, reuse existing execution/retry/journal.
- [ ] Selective donor loopback rooms/roles/Black 180deg view; host sole truth.
- [ ] Main menu, host room status/open-client button, hardware-free join client.
- [ ] Tests: both colors/capture, no premature commit, failures/retry, stale/duplicate
      requests, disconnect/rejoin, single physical owner, existing modes/regression.
- [ ] Read-only review, running UI with mocked hardware, documentation and evidence.

Room messages carry a fresh room session, peer generation, request ID and board
revision. UI snapshots mirror GameState; client never commits or opens hardware.
Network threads only enqueue, bounded frames/queues; physical jobs run on the
existing MotionWorker. Pre-dispatch disconnect cancels admission, post-dispatch
failure requires camera/controller recovery and is never replayed by the network.

## Session Notes

Initial: runtime closed at user's request. Donor refs confirmed; no new hardware
testing authorized. Planned companion Black UI can be opened from the host or
the home menu and joins by six-character code on localhost only.
