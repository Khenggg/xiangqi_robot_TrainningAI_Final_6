# Brainstorm: Unified player-turn completion detection

**Date:** 2026-09-22, updated 2026-09-23

## Ideas Explored

- Hand-exit confirmation: useful as a completion gate, but unreliable as the sole trigger and blind to tools or missed detections.
- Board-stability confirmation: supports any interaction method, but a stable missing/illegal/occluded board must not be mistaken for a completed move.
- Held-piece state: models a Red piece temporarily removed while the player thinks, without mutating the logical board.
- Unified arbiter: combines lifecycle, interaction/occlusion, visibility, stability, and legal-successor evidence; only the arbiter can request a commit.
- Legal-successor matching: preserves the committed board and compares settled observations against the baseline and all legal Red successor boards instead of reconstructing every intermediate gesture.

## User's Direction

Use a hybrid solution. Hand/object presence is a blocking/completion signal, while a clear and stable legal final board is authoritative. A lifted piece held outside the board remains transient for any duration. Returning it to its origin does not end the turn; placing it at a legal new destination does, but only after the board is unobstructed and settled.

## Resolved Questions

- Automatic confirmation must also support moves for which no hand interaction was detected.
- Timeout never ends the turn while a piece is held or missing.
- Both prior flows must be merged behind a single conflict-resolution and commit owner.
- Manual SPACE remains a fallback but must reuse the same validation/commit gate.

## Risks

- Hand false negatives can incorrectly report a clear board; visibility coverage and motion must also gate confirmation.
- CChess identity and YOLO occupancy can disagree; normalization and explicit ambiguity are required.
- Concurrent legacy paths currently call `process_human_move` directly, creating double-commit and stale-baseline risks.
- A missing piece after the board clears can deadlock without an explicit correction state and operator feedback.
