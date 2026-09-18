# Phase 1 — Hand Detection Data Preparation & Training Pipeline

## 1. Objective

### Primary Goal

Train a YOLO11 object detection model capable of detecting the **human player's hand** in the real Xiangqi Robot environment.

The output model will be:

```text
models/hand_best.pt
```

The model must detect:

```text
class 0: hand
```

The model does **not** need to:

* recognize chess pieces;
* identify which chess piece the hand is holding;
* identify left/right hand;
* recognize gestures;
* estimate hand keypoints;
* determine the player's move;
* replace the existing Occupancy YOLO model.

Those features belong to later phases.

---

# 2. Existing Project Context

The current system uses:

```text
Camera
  ↓
YOLO11 Occupancy
  ↓
10 × 9 board occupancy
  ↓
T1 / T2 comparison
  ↓
Move detection
```

The existing model is:

```text
models/best.pt
```

It is a **1-class Occupancy detector**.

The proposed Phase 1 model is independent:

```text
Camera Frame
     │
     ├── YOLO11 Occupancy
     │       └── models/best.pt
     │
     └── YOLO11 Hand
             └── models/hand_best.pt
```

The two models must not be merged during Phase 1.

---

# 3. Why Hand Detection Is Needed

The current system detects a player's move using:

```text
T1 = board before move
T2 = board after move

T1 → T2
     ↓
disappeared cells
appeared cells
     ↓
source → destination
```

The player may still have their hand over the board when T2 is captured.

This can cause:

```text
hand occlusion
false occupancy
unstable detection
incorrect snapshot timing
```

The future objective is therefore:

```text
Player starts moving
       ↓
Hand detected
       ↓
Player finishes moving
       ↓
Hand leaves board
       ↓
Capture clean T2
       ↓
Run Occupancy detection
```

Phase 1 only builds the model required for this future pipeline.

---

# 4. Model Specification

## 4.1 Model

Recommended initial model:

```text
YOLO11n
```

Task:

```text
Object Detection
```

Classes:

```yaml
names:
  0: hand
```

No separate:

```text
left_hand
right_hand
hand_holding_piece
```

classes are required.

---

# 5. Dataset Strategy

## 5.1 Dataset Sources

The dataset should contain two types of data:

### A. Generic hand data

Used to provide general hand-detection knowledge.

Possible source:

* Ultralytics hand/keypoint dataset or another permissively licensed hand dataset.
* Verify the dataset license before using it in the project.

### B. Project-specific Xiangqi data

This is the most important dataset.

Images should be collected using the **same USB webcam and approximately the same camera position used by the robot**.

The real environment contains:

```text
Xiangqi board
Xiangqi pieces
human hand
player arm
background
camera perspective
lighting conditions
```

The project-specific dataset should therefore dominate the final training dataset.

---

# 6. Data Collection

## 6.1 Initial Target

Start with approximately:

```text
2,000–5,000 labeled frames
```

Do not treat this as a hard requirement.

The final dataset size should be determined by:

```text
model performance
validation errors
scene diversity
duplicate/redundant frames
```

Quality and diversity are more important than simply increasing frame count.

---

# 7. Video Recording Strategy

If collecting data from video, do not label every frame blindly.

A video may contain:

```text
30 FPS
10 seconds
= 300 frames
```

but consecutive frames can be almost identical.

Instead:

```text
Video
 ↓
Frame extraction
 ↓
Temporal sampling
 ↓
Candidate frames
 ↓
Manual quality filtering
 ↓
Annotation
```

Start with approximately:

```text
5–10 FPS
```

for candidate extraction.

Adjust this depending on the amount of motion and scene diversity.

---

# 8. Required Scenarios

The dataset should cover the actual situations expected during Xiangqi gameplay.

## 8.1 Hand Without Chess Piece

Examples:

```text
hand above board
hand touching board
hand near pieces
hand between pieces
```

---

## 8.2 Hand Holding Chess Pieces

Examples:

```text
hand holding pawn
hand holding rook
hand holding cannon
hand holding knight
hand holding elephant
hand holding advisor
hand holding king
```

The model does not need to distinguish the pieces.

The label remains:

```text
hand
```

---

## 8.3 Hand Occluding Chess Pieces

This is particularly important.

Examples:

```text
hand partially covering a piece
hand completely covering part of a piece
hand between multiple pieces
```

---

## 8.4 Different Hand Positions

Collect:

```text
left side of board
center of board
right side of board
top side
bottom side
corners
near board boundaries
```

---

## 8.5 Different Hand Orientations

Examples:

```text
palm facing camera
back of hand facing camera
side of hand
fingers extended
fingers curled
hand holding a piece
```

---

## 8.6 Different Players / Hand Shapes

If possible, collect samples from multiple people.

This prevents the model from overfitting to:

```text
one person's hand shape
one skin appearance
one sleeve
one playing style
```

---

## 8.7 Negative Images

Include images containing:

```text
chess pieces only
empty board
robot arm
background objects
chairs
tables
```

with **no hand**.

For YOLO detection datasets, these images can be used as negative/background examples.

They are especially useful for reducing false positives.

---

# 9. Important Dataset Rule: Avoid Frame Leakage

Do NOT randomly split individual video frames into train/validation/test.

Bad:

```text
Video A
 ├── frame 001 → train
 ├── frame 002 → validation
 ├── frame 003 → train
 └── frame 004 → test
```

These frames are highly correlated.

This can produce artificially high validation performance.

Instead split by:

```text
video/session/recording
```

For example:

```text
Recording 01 → train
Recording 02 → train
Recording 03 → train
Recording 04 → validation
Recording 05 → test
```

Recommended initial split:

```text
Train      70%
Validation 20%
Test       10%
```

The exact ratio may be adjusted according to dataset size.

---

# 10. Dataset Directory

Recommended structure:

```text
data/
└── hand_detection/
    ├── raw/
    │   ├── videos/
    │   └── images/
    │
    ├── extracted/
    │
    ├── annotated/
    │
    └── yolo/
        ├── images/
        │   ├── train/
        │   ├── val/
        │   └── test/
        │
        ├── labels/
        │   ├── train/
        │   ├── val/
        │   └── test/
        │
        └── data.yaml
```

---

# 11. YOLO Annotation Format

Each image has a corresponding `.txt` file.

Example:

```text
images/train/frame_000123.jpg
labels/train/frame_000123.txt
```

YOLO format:

```text
class_id x_center y_center width height
```

All coordinates are normalized to `[0, 1]`.

Example:

```text
0 0.521 0.483 0.312 0.421
```

This means:

```text
class = hand
```

with the corresponding normalized bounding box.

---

# 12. Annotation Rules

## 12.1 Bounding Box

The bounding box should cover the visible hand.

Example:

```text
┌─────────────────────────┐
│                         │
│       HAND              │
│     ┌──────────┐        │
│     │          │        │
│     │          │        │
│     └──────────┘        │
│                         │
└─────────────────────────┘
```

Do not intentionally include a large amount of:

```text
arm
background
table
chess pieces
```

unless they are physically inseparable from the visible hand.

---

## 12.2 Partially Occluded Hand

If only part of the hand is visible:

```text
label the visible hand region
```

Do not invent the invisible portion.

---

## 12.3 Multiple Hands

If multiple hands can appear in the scene:

```text
hand A → class 0
hand B → class 0
```

Each hand receives its own bounding box.

---

# 13. Data Quality Control

Before training, inspect:

```text
random training images
random validation images
random test images
```

Check:

* bounding box accuracy;
* missing annotations;
* incorrect annotations;
* duplicate images;
* corrupted images;
* extremely similar frames;
* incorrect train/val/test split;
* class ID consistency.

A dataset validation script should check:

```text
image exists
label exists
image readable
label format valid
class ID valid
coordinates in range [0,1]
width > 0
height > 0
```

---

# 14. data.yaml

Example:

```yaml
path: /path/to/data/hand_detection/yolo

train: images/train
val: images/val
test: images/test

names:
  0: hand
```

Do not hard-code a machine-specific path if the project is expected to be shared.

Prefer a configurable path when possible.

---

# 15. Phase 1 Training Pipeline

## Stage 1 — Environment Setup

Install:

```bash
pip install ultralytics
```

Verify:

```bash
yolo checks
```

or verify through Python:

```python
from ultralytics import YOLO

print("Ultralytics imported successfully")
```

---

# 16. Stage 2 — Baseline Training

Start with pretrained YOLO11n.

Conceptually:

```text
YOLO11n pretrained weights
          ↓
hand dataset
          ↓
fine-tuning
          ↓
hand_best.pt
```

Do not train from random initialization unless there is a specific reason.

Example:

```python
from ultralytics import YOLO

model = YOLO("yolo11n.pt")

results = model.train(
    data="data/hand_detection/yolo/data.yaml",
    epochs=50,
    imgsz=640,
    batch=-1,
    patience=15,
    project="runs/hand_detection",
    name="yolo11n_baseline"
)
```

These are **initial baseline values**, not final hyperparameters.

---

# 17. Stage 3 — Validation

Run validation after training.

Evaluate:

```text
Precision
Recall
mAP50
mAP50-95
```

More importantly, inspect:

```text
false positives
false negatives
small/partial hands
hands holding pieces
hands near board boundaries
```

A high mAP alone is not sufficient.

---

# 18. Stage 4 — Test Set Evaluation

The test set must not be used during hyperparameter tuning.

Recommended workflow:

```text
Train
 ↓
Validation
 ↓
Tune
 ↓
Retrain
 ↓
Final Test
```

Do not repeatedly optimize against the test set.

---

# 19. Stage 5 — Real Camera Test

After obtaining a promising model:

```text
hand_best.pt
      ↓
USB Webcam
      ↓
1280 × 720
      ↓
real Xiangqi board
      ↓
visual inspection
```

Test scenarios:

```text
1. Empty board
2. Hand enters board
3. Hand moves across board
4. Hand picks up piece
5. Hand places piece
6. Hand covers piece
7. Hand leaves board
8. Multiple hands
9. Robot arm visible
10. Different lighting
```

---

# 20. Phase 1 Success Criteria

The model should satisfy:

### Functional

```text
✓ Detects player's hand
✓ Works with actual project camera
✓ Works while holding chess pieces
✓ Works when hand partially occludes pieces
✓ Produces no obvious false positives on empty board
```

### Engineering

```text
✓ Dataset is reproducible
✓ Train/val/test split has no video leakage
✓ data.yaml is valid
✓ Training configuration is documented
✓ Best checkpoint is saved
✓ Validation metrics are recorded
✓ Test results are recorded
```

### Deployment artifact

Final artifact:

```text
models/hand_best.pt
```

Training metadata should also be retained:

```text
runs/hand_detection/
├── results.csv
├── results.png
├── confusion_matrix.png
├── PR_curve.png
└── weights/
    ├── best.pt
    └── last.pt
```

---

# 21. Recommended Experiment Tracking

Each experiment should record:

```text
experiment_name
dataset_version
model
epochs
image_size
batch_size
learning_rate
augmentation
optimizer
precision
recall
mAP50
mAP50-95
inference_speed
notes
```

Example:

```yaml
experiment:
  name: hand_yolo11n_v01

model:
  architecture: YOLO11n
  task: detection

dataset:
  version: hand_v01
  classes:
    - hand

training:
  epochs: 50
  imgsz: 640

results:
  precision: ...
  recall: ...
  map50: ...
  map50_95: ...

notes:
  - baseline experiment
```

---

# 22. Recommended Iteration Strategy

Do not immediately spend a large amount of GPU money.

Use:

```text
Small dataset
    ↓
Colab
    ↓
Baseline training
    ↓
Evaluate
    ↓
Identify problems
    ↓
Improve dataset
    ↓
Repeat
```

Only after the pipeline becomes stable:

```text
Final dataset
      ↓
Cloud GPU
      ↓
Full training
      ↓
Final hand_best.pt
```

---

# 23. Error-Driven Dataset Improvement

After the first model, collect failure cases.

For example:

```text
False Positive:
chess piece detected as hand
        ↓
add similar negative examples

False Negative:
hand holding chess piece not detected
        ↓
add more hand-with-piece examples

False Negative:
hand near board boundary
        ↓
add boundary examples
```

The second dataset version should therefore be:

```text
Dataset v1
   +
failure cases
   ↓
Dataset v2
   ↓
retrain
```

This is preferable to blindly adding thousands of random images.

---

# 24. Phase 1 Scope Boundary

Phase 1 MUST NOT modify the core game logic.

Do not change:

```text
src/core/
src/hardware/
src/ai/
FEN logic
robot coordinates
robot movement
```

Avoid integrating the model into:

```text
camera_monitor.py
snapshot_detector.py
main.py
```

until the standalone model has passed Phase 1 evaluation.

The only expected model artifact is:

```text
models/hand_best.pt
```

---

# 25. Future Phase

After Phase 1:

```text
Phase 1
Hand Detection
     ↓
Phase 2
CameraMonitor integration
     ↓
Phase 3
Hand presence / hand removal gate
     ↓
Phase 4
Hand position → board coordinate
     ↓
Phase 5
Hand trajectory + T1/T2 fusion
     ↓
Phase 6
Human move verification
```

The final intended architecture is:

```text
                    USB CAMERA
                        │
                        ↓
                CameraMonitor
                        │
             ┌──────────┴──────────┐
             ↓                     ↓
      YOLO Occupancy          YOLO11 Hand
        best.pt               hand_best.pt
             │                     │
             ↓                     ↓
       Board Occupancy        Hand State
             │                     │
             └──────────┬──────────┘
                        ↓
                Hand-aware Vision
                        ↓
                    T1 → T2
                        ↓
                  Move Detection
                        ↓
                    FEN Update
                        ↓
                  Xiangqi Engine
                        ↓
                    Robot FR5
```

---

# 26. Final Deliverables

At the end of Phase 1, the project should contain:

```text
data/
└── hand_detection/
    └── yolo/
        ├── images/
        ├── labels/
        └── data.yaml

models/
└── hand_best.pt

runs/
└── hand_detection/
    └── <experiments>

docs/
└── phase1_hand_detection.md
```

And a reproducible training procedure:

```text
Raw video/images
      ↓
Frame extraction
      ↓
Quality filtering
      ↓
Annotation
      ↓
Dataset validation
      ↓
Train/Val/Test split
      ↓
YOLO11n training
      ↓
Validation
      ↓
Failure analysis
      ↓
Dataset improvement
      ↓
Final training
      ↓
hand_best.pt
```
