# Brainstorm: Physical robot self-play

**Date:** 2026-09-25

## Ideas Explored

- **Dry-run self-play:** fastest to demonstrate engine-vs-engine, but does not validate robot motion, gripper behavior, or camera calibration.
- **Continuous physical self-play:** both engines alternate without operator input; useful for extended reliability and calibration runs.
- **Step-by-step physical self-play:** the operator explicitly advances each turn; useful for inspecting the board, gripper, and arm path after every move.
- **Shared single difficulty:** simpler configuration but cannot demonstrate a strength mismatch or independently tune both sides.
- **Independent Red/Black difficulties:** preserves the existing four engine profiles for each side and supports varied test matches.

## User's Direction

Implement physical Robot-vs-Robot play, not a simulation-only mode. Provide both continuous and step-by-step runs, with independently selected difficulty settings and an immediate end-match control. The primary purpose is visual validation of gripper, arm, and board calibration for operators who do not play full Xiangqi matches.

## Open Questions

- None blocking for the MVP. The initial plan will make end-match stop future move scheduling and return the arm to its normal safe/home position; it will not interrupt a robot command mid-motion.

## Risks

- The current game state has an AI commit path specialized for Black; self-play needs a color-neutral, camera-verified physical commit path.
- A failed camera check after either color's move must stop the run without mutating the FEN or scheduling another command.
- Continuous operation raises wear/collision risk, so the mode must retain the existing physical-sync fault gate and expose a clear operator stop action.
