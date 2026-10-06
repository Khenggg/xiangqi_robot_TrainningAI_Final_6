# Phase 01 — top-face targets and guarded geometry

Status: software_verified; awaiting_human_review | Mode: HARD | Dependency: plan review APPROVED
P1 stories: top-face-pick; height-aware-geometry; guarded-top-pick

## Implementation work

1. Recheck instructions, Git status, active detection/pick/refresh call paths, and tests; preserve unrelated changes. Do not access old Downloads measurement folders.
2. Add the camera-only `CALIBRATE_PICK_GEOMETRY.bat` wizard with measured checkerboard square input and fresh board clicks. Estimate K/distortion and metric board pose for the confirmed 250 × 281.25 mm board, with 31.25 mm spacing across all 8 × 9 intervals. Validate and bind profile to camera, frame configuration, and session setup; absent/mismatch blocks new mode.
3. Carry raw float `best.pt` observations and the exact fresh frame into ROI extraction before legacy 85%-foot filtering. Extract supported top-face contours with explicit quality/rejection evidence; keep box occupancy independent and box/top box diagnostic only.
4. Undistort boundary rays, choose the board-normal sign toward camera, intersect the boundary with the +10 mm plane, fit its metric circle center, then convert to float grid and existing robot XY. Reject bad fits, rays, geometry, bounds, expected-cell association, or unstable samples; never approximate by projecting the image ellipse center.
5. Integrate rejection through T/production picks, captured-piece targeting, and moving-source refresh. Failure/None stops before the affected pick; no foot/box/logical/stale fallback. Preserve explicit visual-disabled legacy operation and all gripper, AI, TCP, Z, and offset-teaching behavior.
6. Add paired-frame diagnostics for boundary, physical center, float grid, profile, and rejection cause; document commissioning, fixed-session validity, and physical-validation limits. No empirical fallback, radial bias, or midpoint correction.

## Verification and review

Commissioning must reject insufficient/duplicate views, high intrinsic/pose residuals and degeneracy. Require independent known-XY target observations at height 10 mm and operator-entered maximum mm error plus explicit save approval. Compare startup fresh board corners against calibrated pose with bounded pixel tolerance rather than exact H hash. Validate angular circle coverage, radius/size, normalized residual, competing centers and positive finite ray intersections.

- Synthetic calibrated projections: distorted/oblique top boundaries recover known metric centers at 10 mm height; wrong normal and raw-ellipse-center approximation are caught.
- Generated ROI cases: ambiguity, characters, side walls, shadows, occlusion, clipping, and insufficient support reject; float coordinates/frame pairing and edge candidates survive correct routing.
- Profile cases: missing K/distortion, invalid calibration, bad pose, camera/frame/session mismatch, nonfinite geometry, and invalid intersections block targets.
- Motion mocks: rejected source/capture target and None post-capture refresh issue no affected pick approach/close or stale fallback; explicit visual-disabled behavior remains; top rejection retains occupancy evidence.
- Run targeted tests plus `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v`; independent reviewer checks all target/refresh paths and unchanged mechanical/game behavior.

Automation must not activate cameras or robots. Review completion and passing synthetic/unit tests do not verify runtime commissioning or physical accuracy. No code before plan review; no commit/push without separate authorization.

## Software evidence

- `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v`: 150 tests, OK, exit 0; 34 new tests in tests/test_top_face_geometry.py.
- `python -X utf8 -m compileall -q src scripts main.py config.py`: exit 0.
- Camera-only wizard `--help`: exit 0; no capture opened.
- `git diff --check`: exit 0 (Windows line-ending warnings only).
- Reviewer reproduced a 1.198mm mixed-height silhouette bias; raster red/green regressions now reject silhouette-only and recover printed top rims at corners/center. Review approved 93/100.
- Scratch-test keep/discard and mandatory HARD human approval remain pending. Physical commissioning and actual grasp accuracy remain unverified.
