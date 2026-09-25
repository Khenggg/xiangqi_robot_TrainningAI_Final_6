# Phase 01 — State and profile contracts

**Stories:** P1 independent Red/Black difficulties; P1 camera-verified commits for both colors.  
**Goal:** make the AI selection and physical state transition color-neutral without changing the current human-vs-robot caller behavior.

## Files and changes

### `src/ai/ai_controller.py`

1. Extend `pick_move(board_snapshot, color="b", difficulty=None)` (or an equivalent keyword-only override) so omitted difficulty preserves `config.AI_DIFFICULTY` exactly.
2. Validate an override against the four advertised local profiles and resolve its profile into local variables. Continue using the original unbounded Moonfish signature for `impossible`.
3. Keep profile-selected requests local-only; failed local requests return `None` and must not fall back to cloud.
4. Do not assign to config or mutate a shared profile dictionary. Document that the override exists for alternating self-play colors.

### `src/core/game_state.py`

1. Replace/extend the Black-specialized pending payload with a color-neutral `set_pending_physical_move(move, expected_board, captured_piece, moving_color)` that defensively copies expected board data and records the source turn.
2. Add `commit_pending_physical_move()` that atomically appends history with `moving_color`, puts a captured piece in the opponent capture list, replaces board, records last move, flips turn to the opponent, advances move number according to existing FEN convention, updates FEN, clears pending/fault, and returns success/failure.
3. Preserve `set_pending_ai_move` and `commit_pending_ai_move` as compatibility wrappers for the existing Black route, with unchanged externally observable Black result (history turn `b`, resulting turn `r`, capture bookkeeping, FEN behavior).
4. Ensure reset, rollback, game-over, and pending-clear paths continue to invalidate/clear physical pending state safely.

## Tests to write first

### `tests/test_policy_engine.py`

- A Red request with explicit `easy` invokes local Moonfish with easy profile settings even when config says hard.
- A Black request with explicit `impossible` retains the legacy original call signature.
- Two sequential calls with different explicit profiles prove config’s `AI_DIFFICULTY` has not changed and profile arguments do not leak.
- Existing calls with no override retain existing tests and results.

### `tests/test_game_state_physical_commit.py`

- Red non-capture and capture commits have exactly one history entry, correct captures, expected next turn, and updated FEN.
- Equivalent Black tests prove the compatibility wrapper output remains unchanged.
- A missing pending move returns false and changes no board/FEN/history.
- A copied expected board cannot be mutated by the caller after it is stored.

## Verification

Run targeted tests, then `pytest tests`. Review the diff specifically for accidental global difficulty mutation and for a mismatched turn/move-number update between Red and Black.

## Exit criteria

The controller can request either color with an explicit profile and has a single atomic commit API that represents either color’s verified physical move, while all current human-vs-robot tests remain green.
