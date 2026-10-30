# Spec: Manual camera-verified rollback

**Date:** 2026-10-30
**Status:** Ready

## Problem Statement
Undo the latest completed Red player move and Black AI reply by manually restoring the physical pieces. The client guides placement with circles and resumes Red only after camera verification, without reverse robot motion.

## User Stories
- **[P1]** As a player, I want matching circles around each moved piece and its return square so I can restore the preceding position.
  Accepted when: Z/button starts only for the latest completed pair, shows one color per side, and produces zero arm/gripper commands.
- **[P1]** As a player, I want the camera to recognize completion automatically so I can resume my turn without pressing a confirmation key.
  Accepted when: three fresh full-board matches spanning at least one second restore the pre-pair state exactly once; missing, wrong, unknown or low-confidence pieces prevent completion.
- **[P1]** As a player, I want captures restored correctly so the next turn starts from the actual original position.
  Accepted when: both captured-piece lists, history, move number, FEN and baseline agree with the saved pre-player state; captured victims have marked return squares.
- **[P2]** As a player, I want to cancel an accidental request before moving pieces.
  Accepted when: cancellation requires the full current post-pair board to match again before play resumes.
- **[P3]** Out of scope: multi-cycle undo, redo, reverse robot execution, recovery journals, undo after process restart or after a terminal result is published.

## Functional Requirements
1. Save a deep logical checkpoint immediately before an accepted normal Red move. Complete eligibility only after its verified Black reply, on Red turn with no active motion, fault or pending transition. New accepted Red moves replace the latest candidate; reset/emergency/test invalidate eligibility. Failed AI searches and fallback moves obey the same completion boundary.
2. Render circles only as requested: one at the current piece position and one at its pre-pair source, using matching side colors. No arrows or move list. Recompute piece location from observed board; hide a source circle when absent or ambiguous. Distinct ring sizes handle overlapping squares. When Black captured the moved Red piece, show its destination restoration ring even though that piece is off board. Captured victims get restoration rings at their original cells.
3. While rollback is active, retain the committed post-pair board/FEN and block normal human commits, AI scheduling, emergency/test and conflicting controls. Keep camera video and event handling responsive. No robot motion or gripper commands may originate from rollback.
4. Continuously sample fresh camera frames off the UI thread using the camera locking policy. Recognize the complete 10x9 identity layout against the pre-pair checkpoint. Do not substitute occupancy-only matching, cached snapshots or unknown identity for proof. Use a confidence threshold strictly above 0.7, and require three consecutive matches spanning at least one second. Any mismatch, camera failure or uncertain result resets the matching streak. Failure remains paused with circles visible.
5. After matching, acquire a fresh next-turn baseline from a frame that also verifies the target position. Baseline failure leaves rollback paused. Atomically restore checkpoint board, FEN, Red turn, captures, move history/log, counters and last move; increment epochs/generations to reject stale work and invalidate old candidate/session state. Synchronize restored FEN once using the existing room; no result/end-match is sent. Clear the consumed checkpoint and resume ordinary player detection.
6. Cancel keeps post-pair logical state and requires fresh full-board post-pair matching and a new baseline before play resumes; partial physical restoration cannot silently unlock gameplay.
7. Disable rollback after game over, during thinking/motion/physical faults, before a complete pair, and while the player has started an uncommitted next move until the board is restored to the expected latest completed position. Startup ignores old rollback journal files.
8. DRY_RUN tests inject recognized boards and verification/baseline outcomes; real mode never completes without actual fresh evidence. Preserve 30-second AI budget, legal fallbacks, checkmate/stalemate rules and verified robot commit semantics.

## Non-Functional Requirements
- One verification worker maximum; stale results carry a session token and cannot commit after cancellation/reset/new game.
- At most one recognition attempt per 250ms; UI polling does not wait for inference or camera acquisition.
- Runtime memory only, one saved cycle. No new persistence format or SDK motion API.

## Success Criteria
- [ ] Noncapture, either-side capture, both-side capture, same-piece recapture and overlapping square scenarios restore exactly the checkpoint.
- [ ] Three fresh matches over >=1 second complete once; repeated cached frames, wrong identities, unrelated missing pieces and low confidence never complete.
- [ ] Zero arm/gripper calls from start, polling, completion and cancellation.
- [ ] AI/human commits remain blocked throughout partial restoration and failed baseline capture.
- [ ] Restored FEN sent once, correct history/captured lists, Red to move, next legal player move schedules one AI reply.
- [ ] Existing offline regressions plus new manual rollback tests pass; physical camera acceptance remains a workstation verification step.

## Assumptions
Only the latest completed nonterminal normal player/AI pair can be undone. A captured piece is retrieved and placed by the player. Circle guidance appears on the client board, not projected onto the real board. Exact automatic verification requires the existing full-board recognizer to be available.
