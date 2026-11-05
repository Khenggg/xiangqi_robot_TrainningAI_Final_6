# 31-cell YOLO baseline after 32-piece ONNX verification

Session: `logs/20261102_175131_59466bba`, HUMAN_VS_HUMAN_ROBOT / PHYSICAL.
Read-only runtime/log investigation; no device/camera/robot commands issued.

## VERIFIED evidence

- At 17:53:41 +07, initial verifier reports NO_FRESH_OBSERVATION (no fresh
  recognized frame yet), not a missing-piece board mismatch.
- At 17:53:47, 17:54:07 and 17:55:14, camera.verified follows two matching
  observations of the complete opening. At 17:55:14 both samples report Red16,
  Black16, board_diff_count0, minimum piece confidence about0.907 (>0.5).
- Immediately after those verifications, T1 Baseline captured reports31.
- SnapshotDetector.capture_baseline computes that number from True cells in
  `_build_occupancy(detections)`: YOLO box occupancy, not CChess layout/FEN count.
  Filtering, intersection assignment, duplicate boxes sharing cells or detector
  dropout can reduce that count. The exact cause/cell is UNKNOWN from old logs.
- Same counter/message existed in the original checkout before the new mode.
  The new mode uses GUI moves and retained full-board verification, not the
  automatic physical-human occupancy turn detector (`is_human_turn` is false).

Therefore the logged31 is not evidence that this session's FEN contains31 pieces.
It also does not prove YOLO mapping is correct or that future visual picks will
succeed. Do not change thresholds or fabricate occupancy to reach32.

## Scoped change, worktree only

Snapshot message now explicitly labels YOLO occupied cells, not ONNX/FEN pieces.
HardwareManager emits camera.yolo_baseline with raw_detection_count,
yolo_occupied_count, expected_piece_count and occupancy_diff_cells containing
zero-based row/col, expected piece and YOLO occupancy. This is a diagnostic
warning on differences, not CAMERA_VERIFY_FAILED and not new execution authority.
FEN verifier, confidence/mapping thresholds, frames, baseline contents, move
admission and robot targets unchanged. Existing running process was not restarted;
new log applies on its next normal launch.

## Validation

```powershell
$env:PYTEST_ADDOPTS='-x'
$env:DRY_RUN='1'
$env:ROBOT_BACKEND='VIRTUAL'
.\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_yolo_baseline_diagnostics.py,tests/unit/test_robot_pvp.py,tests/unit/test_fresh_session_startup.py,tests/unit/test_camera_observation_integrity.py
```

PASS, exit0: 46 parallel tests, no serial selected; runner31.48s.
Windows / Python3.12.10 / pytest9.1.1. Deterministic calibration fixture and fake
camera/verifier; no hardware. Covered31 occupied cells with31 boxes and with32
boxes (duplicate), exact missing-cell diagnostics, no false FEN failure or board
mutation, and actual FEN mismatch still rejects before baseline capture.

Scoped read-only review: no blocker. git diff --check PASS, exit0. Graph discovery,
architecture, trace and detect_changes attempted but unavailable (Transport closed);
exact-file/caller inspection used. No full regression or physical recognition
acceptance performed. This improves diagnostic clarity; the actual YOLO count
discrepancy is not claimed fixed.

## Named-cell diagnostic follow-up

User requested the missing piece name. The human-readable YOLO diagnostic now
uses the expected FEN piece name plus board square and zero-based row/column.
An unexpected occupied cell is explicitly described as YOLO occupancy at an
expected empty square. Names come from the expected FEN, not YOLO classification;
the message states that physical absence has not been established. Both missing
and extra cells are shown even when the two total counts are equal.

Validation: test_fast.ps1 -Workers2 targeting test_yolo_baseline_diagnostics.py
and test_fen_verification_diagnostics.py: PASS, exit0, 30 tests (23 parallel +7
serial),18.38s. Includes same-count displaced occupancy, piece names/locations,
and existing verifier diagnostics. git diff --check PASS. No camera/controller
commands, process restart or change to acceptance decisions. Old31-only logs
cannot retroactively identify the missing cell.
