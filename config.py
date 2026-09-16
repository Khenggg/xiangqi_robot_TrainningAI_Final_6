"""Defaults for the restored launcher. Real FR5 values must be measured locally."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
DRY_RUN = True
VISION_BACKEND = "cchess_qr"
VIDEO_SOURCE = int(os.getenv("VIDEO_INDEX", "0"))
QR_LAYOUT_PATH = ROOT / "config" / "qr_board.json"
ROBOT_CAMERA_REFERENCE_PATH = ROOT / "config" / "robot_reference.json"
CCHESS_MODEL_PATH = ROOT / "models" / "cchess_nano_v3.onnx"
CCHESS_MIN_CONFIDENCE = 0.80
ENGINE_TYPE = "LOCAL"
MOONFISH_EXE = str(ROOT / "moonfish" / "moonfish_ucci.py")
MOONFISH_NNUE = None
MOONFISH_THINK_MS = 1000
SIMULATION_API_URL = os.getenv("SIMULATION_API_URL", "https://tuongkydaisu.com")
SIMULATION_TOKEN = os.getenv("SIMULATION_TOKEN", "")

# Only used for object initialization in preview mode. The --robot launcher
# requires every physical value from a measured robot_motion.json profile.
ROBOT_IP = ""
MOVE_SPEED = 5.0
CELL_SIZE_X = CELL_SIZE_Y = 1.0
BOARD_ORIGIN_X = BOARD_ORIGIN_Y = OFFSET_X = OFFSET_Y = 0.0
# Preserve the legacy bilinear correction documented in its coordinate test.
# The measured QR camera-to-robot mapping does not apply this extra offset.
OFFSET_X = 5.0
RIVER_GAP_Y = 0.0
ROBOT_DIR_X = ROBOT_DIR_Y = 1
ROTATION = [0.0, 0.0, 0.0]
PICK_Z = PLACE_Z = SAFE_Z = IDLE_Z = 0.0
IDLE_X = IDLE_Y = CAPTURE_BIN_X = CAPTURE_BIN_Y = 0.0
GRIPPER_OPEN = 0
GRIPPER_CLOSE = 1
VISUAL_PICK_ENABLED = False
# The new QR backend uses circle-based correction in the rectified board image.
# Physical FR5 moves require a valid result; DRY_RUN may show/verify it only.
VISUAL_CORRECTION_PIXELS_PER_CELL = 120
VISUAL_CORRECTION_MIN_RADIUS_CELLS = .20
VISUAL_CORRECTION_MAX_RADIUS_CELLS = .58
VISUAL_CORRECTION_MAX_OFFSET_CELLS = .34
VISUAL_CORRECTION_MIN_CONFIDENCE = .60
VISUAL_CORRECTION_HOUGH_PARAM2 = 10
YOLO_VISUAL_CORRECTION_ENABLED = True
YOLO_PIECE_MODEL_PATH = ROOT / "models" / "best.pt"
YOLO_PIECE_CONFIDENCE = .45
YOLO_PIECE_IMAGE_SIZE = 640
