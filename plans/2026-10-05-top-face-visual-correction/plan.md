# Top-face visual correction

Mode: HARD
Risk: high-risk — changing robot pick coordinates requires guarded physical commissioning.
Date: 2026-10-05
Status: awaiting_human_review

The user validation answers are recorded in `spec.md`. Phase 01 retains its human-review gate. The user confirmed the presented consensus/retry design; phase 02 extends this plan as one coherent implementation phase after HARD plan review.

## Confirmed outcome

Use fresh, frame-paired floating `best.pt` boxes to extract the top-face boundary. Undistort boundary rays with calibrated camera K/distortion, intersect them with the plane 10 mm above the board, fit the physical circle center, convert to floating grid coordinates, and use the existing robot XY mapping.

The camera and board stay fixed per session. The board is 250 × 281.25 mm: eight column intervals and nine row intervals, each 31.25 mm, including the river. Every piece is 10 mm high. No previous Downloads measurement-folder data may be used.

## Phase and stories

| Phase | P1 story IDs | Status |
| --- | --- | --- |
| [01 — top-face targets](phase-01-top-face-targets.md) | top-face-pick; height-aware-geometry; guarded-top-pick | software_verified; human review pending |
| [02 — pick consensus and safe retry](phase-02-consensus.md) | pick-consensus; safe-retry | software_verified; human review pending |

The phase includes a new camera-only commissioning wizard, `CALIBRATE_PICK_GEOMETRY.bat`, for missing K/distortion and a fresh metric board pose. It uses a printed checkerboard with operator-measured square size and board clicks. No lens values may be invented.

Phase 02 replaces blind averaging with bounded metric consensus: initially three fresh samples, at most six attempts within a soft three-second budget, unique maximum-support strict majority of valid observations, at least two members, and the latest attempt must be an actual member. Exhaustion before motion enables fresh R retry of the same pending move or X cancellation. After successful captured-piece placement and verified destination clearance, source-consensus exhaustion permits only a fresh source-only retry, rechecking clearance and never replaying capture. Other partial-motion faults require manual completion or restoration plus V verification. Robot failures, including 112/MoveCart exception paths, must never commit the logical move as successful.

## Gates and scope

- Missing, invalid, or mismatched geometry profile blocks the new mode. Its validity must bind camera/frame configuration and the fixed session setup; setup changes require recommissioning.
- Do not project a raw image ellipse center as an approximation. Map boundary samples to the elevated plane before circle fitting; resolve board-normal sign so the top plane is toward the camera.
- Use raw float YOLO observations paired with their frame, before the legacy 85%-height foot filter can discard ROI candidates. Keep occupancy evidence independent of top-face success.
- Failed top extraction, geometry validation, capture target, or source refresh returns rejection/None and stops before the affected pick; no stale target fallback.
- Top box is diagnostic only. No empirical fallback, radial bias, or midpoint correction. Preserve explicit visual-disabled behavior and all gripper, AI, TCP, Z, and offset-teaching behavior.

## Verification and handoff

## Accepted red-team requirements

- Save only after independent known-XY checks at height 10 mm (not pose-fitting data) meet the operator-entered mm tolerance and explicit approval. Store observations, errors and thresholds.
- Bind actual camera index, actual frame dimensions and geometry constants. At startup compare fresh board corner pixels with the calibrated board pose within a configured pixel tolerance; do not require identical perspective.npy hashes, which are regenerated at startup.
- Reject insufficient/diversity-poor checkerboard views, excessive calibration/pose residuals, invalid K/dist/pose, grazing/behind-camera rays and failed height checks. Require printed pattern dimensions and measured square size.
- Circle extraction must enforce angular coverage, relative size, finite positive radius, bounded normalized residual and competing-center rejection; thresholds are explicit and configurable, not proof of physical accuracy.

Use synthetic geometry/image fixtures and unit mocks, followed by independent review of extraction, calibration, normal direction, and every pick/refresh gate. Automation must not activate a camera or robot. Tests do not verify runtime commissioning or physical accuracy.

Run targeted suites and `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v`. After plan review, hand off to `$bb-cook --hard plans/2026-10-05-top-face-visual-correction/plan.md`. This plan authorizes no commit or push.

## Session Notes

Last active: 2026-10-05
Phase in progress: phase-02-consensus
Status: 46 targeted and 196 full-suite tests pass; compileall/diff-check pass; independent reviewer APPROVED 94/100. No camera/robot activated.
Decisions: exhaustive unique maximum-support strict majority in metric median radius; latest actual attempt must support it; 3 initial/6 maximum/soft 3s with late rejection. Retry binds immutable epochs/board/pending metadata; verified capture-removal checkpoint permits source-only retry. Every robot exception blocks FEN commit. Post-commit notification failure preserves FEN, pauses stale baseline scanning and requests V refresh. All mechanical and phase-01 contracts preserved.
Next immediate action: mandatory HARD human review of the implementation and the outstanding phase-01 tests/test_top_face_geometry.py keep/discard decision. New consensus tests are TDD retention. Physical commissioning requires new camera data; no commit/push/staging.

Phase 02 extension: HARD --tdd. User confirmed the presented sampling/consensus design. Research, plan review, TDD anchors, implementation and fresh independent verification are recorded in phase-02-consensus.md. Mandatory human approval remains the next gate before finalization; no commit/push authorized.
