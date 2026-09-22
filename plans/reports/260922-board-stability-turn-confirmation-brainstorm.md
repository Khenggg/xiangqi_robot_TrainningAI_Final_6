# Brainstorm: Board-stability player-turn confirmation

**Date:** 2026-09-22

## Ideas Explored

- Hand-aware confirmation: waits for a detected hand to enter and leave the board. It does not work when a player moves pieces with another object.
- Object-specific detection: train or configure a detector for each possible moving object. It adds operational and dataset overhead.
- Board-stability confirmation: observe a changed board state, then accept it only after it remains stable. This is independent of the object used to move a piece.

## User's Direction

Use board stability rather than hand detection. The desired response time after the object leaves the board is 1.0–1.5 seconds.

## Open Questions

- [NEEDS CLARIFICATION] Exact sampling rule within the 1.0–1.5 second window (for example: three identical valid observations over 1.2 seconds).
- [NEEDS CLARIFICATION] Whether automatic confirmation should remain enabled for every physical game or be selectable in the UI.

## Risks

- Camera flicker or intermittent piece detections can make a moved board appear unstable.
- A stable but incorrectly recognized layout must never bypass Xiangqi legality validation.
- Capture moves can retain destination occupancy and require CChess identity or visual-difference evidence.
