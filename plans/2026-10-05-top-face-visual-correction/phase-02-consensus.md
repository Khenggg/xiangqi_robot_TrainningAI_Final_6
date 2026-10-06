# Phase 02 — metric consensus and motion-aware retry

Status: software_verified; awaiting_human_review | Plan/code review: APPROVED
Mode: HARD --tdd
Stories: P1 pick-consensus; P1 safe-retry
Dependencies: preserve phase-01 behavior/evidence and pending human-review gate; no camera/robot activation or Git publication.

## Implementation sequence

1. Recheck current sampling, aggregation, T picks, production capture/source refresh, UI CONTINUE handlers, robot-result exceptions, and pending/FEN transitions. Preserve unrelated changes and all gripper, movement, AI-selection, teaching/TCP/Z, calibration, and extraction contracts.
2. Add one shared metric consensus selector. From at most six valid fresh targets enumerate at most 64 subsets; coordinate-wise median defines each center, and every member must lie within 3.75 mm. Require at least two members and strict majority of all valid targets. Choose unique maximum support first, then require latest-attempt membership; never select a smaller subset to include latest. A None latest attempt blocks acceptance even if earlier samples agree. Reject ties/latest outliers; forbid single-linkage expansion outside the median radius, while chains wholly within that radius remain valid. Never confidence-weight. Convert the selected metric median back through the existing grid mapping.
3. Add bounded fresh acquisition: initially three attempts, at most six total, soft three-second monotonic budget per operation. Preserve actual attempt order, including None observations. Soft extraction absence/weakness and explicitly typed transient frame/read/inference failures permit further attempts; invalid geometry/profile/config or unavailable camera/invalid model abort immediately. Check deadline before further work and after inference, ROI processing, and aggregation; discard late candidates and never authorize late motion. No thread timeout may pretend it cancelled an already running inference.
4. Extract shared `execute_pending_ai_motion(state, hw, config, stage='pre_pick')` into `src/core/visual_move_coordinator.py`; it coordinates motion without FEN writes or AI jobs. Main and R call this same helper for the original pending move. Carry typed consensus exhaustion through `state.pause_visual_pick`, distinct from hard/post-motion errors. Bind immutable `(game_epoch, ai_epoch, human_commit_generation)` plus owner/source/destination and copied T board; require matching ownership before acquisition, motion, and finalization. Reset/rollback/emergency/T exit invalidate the request. Pre-motion failure preserves pending/FEN and shows R/X only during retry wait in CONTINUE. Block normal AI/polling/selection during wait; route R/X before the T keyboard guard. R uses a fresh budget; X retains FEN/fault. Successful verified completion uses existing `_finalize_pending_ai_move` for one commit/API/baseline update. Add no AI-thread retry flag or broad stage-machine rewrite.
5. Explicitly record capture progress in the shared helper. Enter `capture_removed` retry only after captured-piece placement succeeds and destination clearance verification returns True, followed by source-consensus exhaustion. Preserve original pending metadata/FEN; R rechecks destination clearance, collects fresh source consensus, and invokes existing `move_piece(..., is_capture=False)` for source-only completion and one eventual logical commit. Never replay captured-piece pickup. Generic motion/clearance/post-verification errors remain nonretryable faults requiring manual finish or restoration plus V verification. X retains FEN/fault. T mode retains its hardware test function and retries the same selected source/destination only for typed pre-motion exhaustion; post-motion errors stop automatic retry.
6. Audit every robot exception branch, including messages containing 112/MoveCart: set execution failure and prevent logical move/FEN commitment. Unknown or partially completed motion remains a fault requiring board verification. Add concise UI/diagnostic reasons for consensus support, latest attempt, deadline, retry state, and partial-capture restriction.

## Acceptance and verification

### Tests to Write First

After plan review, the independent tester owns new consensus/retry tests and demonstrates relevant failures before the primary agent implements production changes. Derive tests from every acceptance group below; do not activate hardware or alter phase-01 evidence.

- Consensus: coherent two-of-three and strict-majority recovery; isolated confident outliers; equal maximum-support subsets; separated groups; transitive chains; newest member versus newest outlier/None; metric threshold boundaries and nonfinite observations.
- Acquisition: three initial/six maximum attempts, fresh frame order and budgets, soft missing/weak extraction retries, immediate hard-error invalidation, and deadline rejection after separately delayed inference, extraction, and aggregation.
- Pre-motion game: zero motion on exhaustion; unchanged pending move/FEN; R uses the same move and fresh samples; X retains FEN/fault; R/X visible only during retry wait and original CONTINUE behavior otherwise.
- Partial capture: `capture_removed` requires successful captured placement plus verified clearance; rejected source produces no source approach. R rechecks clearance and samples fresh source, resumes without capture, never repicks destination, and preserves original pending metadata/FEN for exactly one successful commit. Generic motion/clearance/post-verification failures offer no automatic retry; manual finish/restoration require V verification.
- T mode: only typed pre-motion exhaustion retries the same selected cells; unrelated/hard/post-motion exceptions cannot restart the move.
- Retry ownership: reset/rollback/emergency/T exit invalidate immutable epoch/owner/cell/test-board binding; stale requests cannot acquire, move, or commit. Retry wait blocks normal AI/poll/selection and R/X routes ahead of the T keyboard guard.
- Robot faults: 112/MoveCart and every other exception mark execution unsuccessful; no blind logical commitment, AI advancement, or stale visual fallback. Review unaffected occupancy, geometry, extraction, and mechanical settings.

Use synthetic targets, fake monotonic clocks, and mocked inference/UI/robot interfaces. Test the shared coordinator directly without importing main or starting AI jobs. Run targeted consensus/retry suites and `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v`, then compile/import checks and diff review. Independent tester/reviewer must inspect all failure/commit branches. No automated camera/robot operation; unit success is not physical recovery evidence.

## Review and handoff

Resolve HARD plan-review findings before coding. After implementation and verified tests, preserve mandatory human approval and test keep/discard review before finalization; no commit/push. Exact handoff: `$bb-cook --hard --tdd plans/2026-10-05-top-face-visual-correction/plan.md` (phase 02 scope).

## Software evidence and remaining gate

- Initial 31 tester-written TDD anchors reproduced missing selector/coordinator and unbounded/late-result behavior before implementation. Root added further cases after the tester hit its usage limit; the independent reviewer remained available.
- Fingerprint regression reproduced acceptance after in-place pending metadata edits, then passed with immutable signatures. Real `FR5Robot.move_piece` orchestration uses only mocked robot actions; captured removal is performed once and source-only Retry never repeats it.
- `python -X utf8 -m unittest discover -s tests -p 'test_pick_consensus.py' -v`: 46 tests, OK.
- Fresh root full suite: `python -X utf8 -m unittest discover -s tests -p 'test_*.py'`: 196 tests, 1.728s, OK, exit 0. Independent reviewer also ran 46/46 and 196/196, exit 0.
- `python -X utf8 -m compileall -q src scripts main.py config.py`: exit 0; `git diff --check`: exit 0. Pygame offscreen rendering confirms R/X labels fit the existing slot; no real window/camera/robot opened.
- Independent code review APPROVED, 94/100. No blocking findings. Metric radius is not jaw tolerance; 3s budget remains soft. No physical pick/recovery, camera commissioning, or external API evidence is claimed.
- P1 coverage: 2/2 software stories covered. Mandatory HARD human approval remains pending; phase-01 scratch-test keep/discard remains pending. No commit/push/staging performed.
