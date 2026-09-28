# Game / Physical FR3 / Digital Twin integration

Mode: implementation authorized by the supplied user specification
Risk: high-risk — physical execution boundary; verification uses fake RPC and PyBullet only
Baseline: integration/unified-fr3-system @ 0702ce0; clean working tree before edits

- [ ] Preserve actor and deterministic piece identity through game commit and capture plans.
- [ ] Share robot snapshot consumption between virtual execution and read-only live mirroring.
- [ ] Instantiate PyBullet from the existing physical BoardPoseProvider, including full rotation.
- [ ] Reconcile human moves in PyBullet; mirror robot payload command events without claiming sensed grasp.
- [ ] Reject stale/missing joint telemetry, preserve actual pose on errors, protect read-only lifecycle.
- [ ] Verify focused acceptance cases and existing subsystem regressions in an isolated worktree.
- [ ] Independently review the changes, repair regressions, and update current documentation last.

Implementation ownership: game/motion contracts and backend telemetry are independent bounded phases; root owns world/bridge, manager wiring, viewer, and integration verification.

The current code already has capture choreography and commit-on-execution-success. Reuse these. Historical documentation and PASS counts are not current evidence. No real robot connection or actuation is part of this task.
