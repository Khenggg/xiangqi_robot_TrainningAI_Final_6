# Brainstorm: Manual camera-verified rollback

**Date:** 2026-10-30

## Ideas Explored
- Previous robot-executed physical reversal: removed in prior work; not selected.
- Manual restoration guided by arrows or move text: user rejected extra guidance.
- Manual restoration with matching pairs of side-colored circles: selected.
- Occupancy-only completion: insufficient for captures and wrong piece identities; use complete identity recognition.

## User's Direction
Undo the player move and AI reply. Show a pair of circles for each side, one highlighting the piece and one the return square. Watch the constant camera feed to automatically confirm completion and resume the player's turn.

## Open Questions
No design blockers. Planning must confirm camera acquisition freshness, recognition confidence coverage, baseline publication and stale worker rejection details against the current implementation.

## Risks
- Captures/recaptures can leave moved pieces off board and overlapping return squares; guidance must use checkpoint identity and history.
- Transient recognition/cached frames can falsely approve an incomplete board; require fresh complete stable matches.
- Resume must restore state and baseline together while rejecting stale AI/vision results.
