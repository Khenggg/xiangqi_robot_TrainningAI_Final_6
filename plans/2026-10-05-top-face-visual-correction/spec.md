# Top-face pick geometry specification

Status: software_verified; awaiting_human_review | Validation answers: confirmed | Plan review: APPROVED

## Geometry and commissioning contract

Fixed camera/board per session; board 250 × 281.25 mm; 8 column and 9 row intervals of 31.25 mm, including river; all pieces 10 mm high. A fresh calibrated K/distortion and metric board pose define the top plane. Resolve the board normal toward the camera, then offset the board plane by +10 mm in that direction.

`CALIBRATE_PICK_GEOMETRY.bat` launches a new camera-only wizard: capture printed checkerboard views, require measured square size, calibrate K/distortion, collect board clicks against known metric board coordinates, solve/validate pose, and save a setup-bound profile. Missing, invalid, stale-session, or mismatched profile blocks the new mode. Never invent lens parameters or use old Downloads measurement-folder data.

## P1 stories and acceptance

### top-face-pick

As an operator, I want the physical top-face center to determine picking. Fresh raw floating `best.pt` boxes and their exact frame provide ROIs before the 85%-foot filter. Extract supported top-face boundary samples; reject clipping, occlusion, side-wall/shadow/character contours, or ambiguity. A box center/top box remains diagnostic only; occupancy keeps independent detection evidence.

### height-aware-geometry

As an operator, I want lens distortion and known piece height accounted for geometrically. Undistort boundary rays, intersect each with the calibrated plane 10 mm aboveboard, fit a metric circle, and transform its center to floating grid coordinates and existing robot XY. No raw ellipse-center projection approximation, empirical fallback, radial bias, or midpoint correction is allowed. Validate finite geometry, normal sign, fit quality, coverage, expected-cell association, and temporal consistency.

### guarded-top-pick

As an operator, I want missing evidence to stop the affected pick. Top failure, absent/mismatched profile, failed captured-piece target, or None source refresh must reject before that pick's approach/close. Never reuse a stale source or silently select a foot/logical/box target. Preserve the explicitly visual-disabled legacy path; preserve gripper sequencing, AI, TCP, Z, and offset teaching.

## Evidence limits

Commissioning accepts only diverse checkerboard views and bounded intrinsic/pose residuals. Independent 10 mm known-XY validation points must meet an operator-entered maximum mm error before explicit save approval. Runtime uses fresh startup-corner agreement and actual camera/frame/geometry compatibility, not exact H hash equality. Invalid/grazing/behind-camera rays and insufficient/ambiguous circle support reject picking.

Synthetic/unit tests cover geometry, extraction, provenance, and mocked motion guards; independent review covers integration and regression boundaries. Automation activates no camera or robot. Runtime commissioning quality and physical grasp accuracy require later supervised validation and are not verified by tests.

## Phase 02 — confirmed consensus and retry extension

Design validation: confirmed by the user; HARD --tdd plan review APPROVED. Phase 01's software evidence and outstanding human-review gate remain unchanged. Missing/invalid geometry, configuration, camera availability, or model validity is a hard failure. Only explicitly typed transient frame/read/inference acquisition failures may consume soft retry attempts; each remains a failed latest observation, never stale evidence.

### P1 — pick-consensus

As an operator, I want a fresh, spatially consistent majority to determine the pick so that an isolated plausible observation cannot bias the target.

Accepted when the estimator starts with three fresh attempts and uses at most six within a soft three-second deadline. Enumerate all subsets of at most six valid metric targets (at most 64); each accepted subset has every member within 3.75 mm of its coordinate-wise median, contains at least two observations, and is a strict majority of all valid observations collected. Choose the unique maximum-support subset before checking latest-attempt membership; never substitute a smaller subset to include the latest sample. A latest None, tied support, no majority, or spatial inconsistency rejects. Confidence weighting and single-linkage extension outside the median radius are forbidden; a chain entirely within that radius remains valid. Invalid geometry/configuration, missing/closed camera, or missing/invalid model invalidate immediately; absent/weak extraction and explicitly typed transient read/inference failures may consume fresh attempts. Check the deadline after inference, ROI extraction, and aggregation; a result finishing late cannot authorize motion. The soft deadline cannot interrupt a blocking dependency, but still rejects its late result.

### P1 — safe-retry

As an operator, I want retry behavior to depend on whether motion already changed the board so that a failed observation cannot replay a capture or silently advance the game.

Accepted when pre-motion consensus exhaustion preserves the same pending move/FEN and shows R/X in the existing CONTINUE area only while retry waits. R starts a new bounded sampling operation for that pending move; X cancels the retry and retains the FEN/fault without advancing AI/game state. Hard errors do not enter the soft retry path. T mode retries the same selected source/destination only on a typed pre-motion consensus exception; errors after motion remain nonretryable. A `capture_removed` retry checkpoint exists only after captured-piece placement succeeds and `verify_capture_cleared=True`, followed by source-consensus exhaustion. R rechecks destination clearance, obtains fresh source consensus, and resumes via existing `move_piece(..., is_capture=False)` while preserving the original pending metadata/FEN for one eventual commit; it never picks the destination again. Generic motion, clearance, or post-verification errors prohibit automatic retry and require manual completion/restoration plus V verification. Every robot exception branch, including 112/MoveCart, marks execution unsuccessful and forbids blind FEN commitment.

Tests must cover outliers, competing subsets, transitive chains, latest None/outlier, late inference/extraction/aggregation, hard errors, fresh retry budgets, R/X visibility, pending/FEN preservation, partial-capture restrictions, T-mode typed exceptions, and all failed robot-success paths. All mechanics, teaching/TCP/Z, top-face evidence, calibration safeguards, and occupancy behavior remain unchanged. Unit/mocked evidence does not establish physical recovery correctness; independent review and human approval remain required.

Retry ownership is immutable: bind `(game_epoch, ai_epoch, human_commit_generation)`, owner, source/destination, and copied T-test board to each request. Reset/rollback/emergency/T exit invalidate it; a stale request cannot move or commit. Retry wait blocks normal AI/polling/selection, and routes R/X before the T keyboard guard. Missing/closed camera, missing/invalid model, invalid profile/configuration are hard failures; only explicitly typed transient read/inference failures are soft. Test invalidation and stale requests at acquisition, motion, and finalization gates.
