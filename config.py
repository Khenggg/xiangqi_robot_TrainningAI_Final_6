# =============================================================================
# === FILE: config.py (CẤU HÌNH TOÀN HỆ THỐNG) ===
# =============================================================================

# --- THÔNG SỐ ROBOT BÀN CỜ (HARDCODED TOẠ ĐỘ TOÁN HỌC) ---
# Tọa độ gốc (Điểm R1 - tương ứng Xe Đen Trái, ô col=0, row=0)
# Tọa độ này sẽ được hệ thống Robot tự động ghi đè lúc khởi động bằng lệnh GetRobotTeachingPoint("R1")
BOARD_ORIGIN_X = 200.0  
BOARD_ORIGIN_Y = -100.0 

# Offset điều chỉnh (mm) - Dùng để tinh chỉnh vị trí gắp
# Nếu robot gắp lệch, điều chỉnh các giá trị này:
# - OFFSET_X: Dương = dịch xuống dưới (về phía row=9), Âm = dịch lên trên (về phía row=0)
# - OFFSET_Y: Dương = dịch sang phải (về phía col=8), Âm = dịch sang trái (về phía col=0)
OFFSET_X = 5.0   # Robot gắp lệch lên trên 5mm → cần dịch xuống 5mm
OFFSET_Y = 0.0   # Không lệch ngang

# Bù gắp RA XA tâm lưới thực tế (4, 4.5), theo các trục R1-R4.
# Tính từ ô nguồn logic; chỉ bù XY gắp, không bù vị trí đặt.
PICK_OUTWARD_COMPENSATION_ENABLED = False  # Height geometry replaces empirical cell offsets.
PICK_OUTWARD_COL_MM_PER_CELL = 0.6
PICK_OUTWARD_ROW_MM_PER_CELL = 0.7
PICK_OUTWARD_MAX_CELLS = 4.0

# Chiều hướng di chuyển so với gốc R1 (1 hoặc -1)
# LƯU Ý: Hệ tọa độ robot: X=dọc (row), Y=ngang (col)
# 1: row tăng thì X tăng, col tăng thì Y tăng
ROBOT_DIR_X = 1  
ROBOT_DIR_Y = 1  

# Kích thước vật lý từng ô bàn cờ (mm)
CELL_SIZE_X = 40.75  # 326mm chia cho 8 khoảng cột (ngang)
CELL_SIZE_Y = 41.00  # 370mm chia cho 9 khoảng hàng (dọc)
RIVER_GAP_Y = 1.00   # Bù thêm 1mm khe hở của con Sông (Nằm giữa row 4 và row 5)

# Tọa độ bãi chứa quân bị ăn (X, Y, Z)
CAPTURE_BIN_X = -226.123
CAPTURE_BIN_Y = 225.024
CAPTURE_BIN_Z = 291.68  # [QUAN TRỌNG] Độ cao khi thả quân vào thùng

# Độ cao an toàn (mm)
SAFE_Z  = 220.0    # User-requested approach/hover height for testing (robot Z, mm).
PICK_Z  = 178   # Hạ xuống gắp (Đã nâng lên để tránh đập bàn, hạ từ từ)
PLACE_Z = 178   # Hạ xuống đặt

# Cấu hình kẹp: motor 2 chiều dùng Tool DO trên đầu robot.
# Verified wiring: DO1 chạy hướng MỞ, DO0 chạy hướng ĐÓNG. Không bao giờ bật cả hai cùng lúc.
GRIPPER_ACTION_CLOSE = "close"
# There is no jaw-position sensor: each state below is established only by
# calibrated motor timing on the real gripper.
GRIPPER_ACTION_OPEN_MAX = "open_max"
GRIPPER_ACTION_CLOSE_TO_SAFE_GAP = "close_to_safe_gap"
GRIPPER_OPEN_DO_ID = 1
GRIPPER_CLOSE_DO_ID = 0
GRIPPER_IDLE_STATUS = 0
GRIPPER_ACTIVE_STATUS = 1

# Motor không có công tắc hành trình: chỉ cấp điện theo xung ngắn rồi tắt cả hai DO.
# Tinh chỉnh hai PULSE riêng sau khi thử với tay robot đứng yên và không có quân cờ.
GRIPPER_DIRECTION_DEADTIME_SEC = 0.10
# Open fully before a release or before establishing the safe travelling gap.
# Tune this to the shortest pulse that reaches the physical open limit.
GRIPPER_OPEN_MAX_PULSE_SEC = 0.2
GRIPPER_CLOSE_PULSE_SEC = 0.3
# Starting from fully open, close only to the travelling/pre-pick safe gap.
# Increase to narrow the gap; decrease to widen it. Do not drive into hard stop.
GRIPPER_SAFE_GAP_CLOSE_PULSE_SEC = 0.06
GRIPPER_OPEN_SETTLE_SEC = 0.25
GRIPPER_CLOSE_SETTLE_SEC = 0.25
MOVE_SPEED = 50 #Percentage based

# Góc xoay của đầu Robot (Rx, Ry, Rz)
ROTATION = [-179.4, -1.2, -73.2]

# --- PHYSICAL PICK / PLACE MOTION PROFILE ---
# Các pose Cartesian FR5 gồm [X, Y, Z, Rx, Ry, Rz]. XY được nội suy từ R1-R4;
# ba góc dưới đây là tư thế tool đã được dạy để ngàm kẹp hướng đúng xuống quân.
#
# Để đổi hướng ngàm thật: đưa robot đến một ô trống ở SAFE_Z bằng pendant,
# xoay wrist/tool tới hướng kẹp đúng và chép Rx/Ry/Rz hiển thị vào PICK_TOOL_ROTATION.
# Không sửa tool frame/TCP trong code. Khi chưa dạy lại, giữ nguyên ROTATION hiện tại.
PICK_TOOL_ROTATION = list(ROTATION)
# Thông thường đặt dùng cùng hướng với gắp; tách biến để có thể hiệu chỉnh sau này.
PLACE_TOOL_ROTATION = list(ROTATION)

# Kết nối Robot
ROBOT_IP = "192.168.58.2"
DRY_RUN = False # Đổi thành True nếu muốn test code mà không cần bật Robot

# Camera index (0 = built-in webcam, 1 = USB cam, 2 = DroidCam, etc.)
# main.py will auto-try configured index first, then others if it fails.
VIDEO_SOURCE = 0  # Camera used for the accepted intrinsics calibration.
VIDEO_BACKEND = "any"
VIDEO_FRAME_WIDTH = 640
VIDEO_FRAME_HEIGHT = 480

# --- VISUAL PICK CORRECTION ---
# Chỉ bù vị trí gắp khi snapshot mới từ camera xác nhận quân nằm gần ô logic.
# Tắt cờ này để trở lại hoàn toàn hành vi gắp tại tâm ô như trước đây.
VISUAL_PICK_ENABLED = True
VISUAL_RING_PICK_ENABLED = False  # New: colored top ring -> height plane -> metric circle center (takes priority).
VISUAL_CURRENT_PICK_ENABLED = True  # Preserve current picking logic; both switches False blocks picking.
VISUAL_PICK_MIN_CONFIDENCE = 0.45
VISUAL_PICK_MAX_OFFSET_CELLS = 0.25
VISUAL_PICK_FOOT_RATIO = 0.85
VISUAL_PICK_SAMPLE_COUNT = 3
VISUAL_PICK_MIN_STABLE_SAMPLES = 2
VISUAL_CENTER_PICK_ATTEMPTS = 3
VISUAL_CENTER_PICK_MAX_JITTER_CELLS = 0.12
# BBox -> piece-height plane; pose refreshed from current auto/manual board calibration.
VISUAL_HEIGHT_PICK_ENABLED = True
VISUAL_CAMERA_INTRINSICS_PATH = "calibration/camera_intrinsics.json"
VISUAL_HEIGHT_BOARD_MM = (324.0, 368.0)  # User-measured outer PLAYING intersections, mm.
VISUAL_HEIGHT_PIECE_MM = 7.0  # Trial compensation height; physical piece height was measured as 9 mm.
VISUAL_HEIGHT_POSE_MAX_ERROR_PX = 3.0
VISUAL_HEIGHT_SAMPLE_WINDOW_SEC = 3.6
VISUAL_HEIGHT_MIN_SAMPLES = 2
VISUAL_HEIGHT_MAX_SPREAD_CELLS = 0.12
VISUAL_MOTION_ASYNC_ENABLED = True
# Top-face temporal consensus only; legacy sampling settings remain unchanged.
VISUAL_PICK_CONSENSUS_INITIAL_SAMPLES = 3
VISUAL_PICK_CONSENSUS_MAX_SAMPLES = 6
VISUAL_PICK_CONSENSUS_TIMEOUT_SEC = 3.0  # soft budget: reject late blocking results
VISUAL_PICK_CONSENSUS_RADIUS_MM = 3.75  # median radius, NOT measured jaw tolerance
# Top-face mode requires a NEW commissioned camera profile. Missing profile
# blocks picking; it never silently reuses box/foot/logical centers.
VISUAL_TOP_FACE_ENABLED = False  # Restore box-center -> foot-point -> logical-cell correction.
VISUAL_PICK_GEOMETRY_PATH = "calibration/pick_geometry.json"
VISUAL_BOARD_WIDTH_MM = 250.0
VISUAL_BOARD_HEIGHT_MM = 281.25  # includes river: 9 intervals of 31.25mm
VISUAL_PIECE_HEIGHT_MM = 10.0  # BOARD -> piece TOP, NOT camera -> board
VISUAL_GEOMETRY_CORNER_TOLERANCE_PX = 4.0
VISUAL_TOP_MAX_RESIDUAL = 0.045
VISUAL_TOP_MIN_COVERAGE = 0.83
VISUAL_TOP_MIN_BOX_FRACTION = 0.55
VISUAL_TOP_RADIUS_MM = (5.0, 15.0)  # quality gate; measure/tune for actual pieces
VISUAL_TOP_AMBIGUITY_MM = 1.5
VISUAL_TOP_MAX_ENCLOSING_AREA_RATIO = 0.80
VISUAL_TOP_ANNULUS_OFFSET_MM = 1.2
VISUAL_TOP_MIN_WHITE_ANNULUS_FRACTION = 0.75
VISUAL_TOP_MAX_WHITE_SATURATION = 80
VISUAL_TOP_MIN_WHITE_VALUE = 130
# Occupancy checks use the whole calibrated square, not the narrower safe-pick radius.
VISUAL_OCCUPANCY_CELL_HALF_WIDTH = 0.50
# When enabled, physical robot moves require CChess layout identity checks to
# match the in-memory FEN before the gripper may pick.  Set False only for
# supervised fallback operation when the layout model is unavailable.
# Kept only for legacy/manual verification calls. Robot motion now uses CChess
# calibration plus best.pt ROI/top-face geometry, so identity is not the pick gate.
VISUAL_BOARD_SYNC_REQUIRED = False

# --- BOARD-STABILITY AUTO MOVE CONFIRMATION ---
# The board must show the same legal move in several observations before it is
# accepted. This works whether a piece is moved by hand or another object.
AUTO_MOVE_CONFIRM_ENABLED = True
BOARD_STABILITY_SECONDS = 1.2
BOARD_STABILITY_MIN_SAMPLES = 3
BOARD_STABILITY_SAMPLE_INTERVAL_SECONDS = 0.10
# Read-only full-board warning check. This never changes FEN, move history,
# AI scheduling, or robot control; it only surfaces unexplained camera layouts.
BOARD_WARNING_CHECK_INTERVAL_SECONDS = 2.0
BOARD_WARNING_MIN_STABLE_SAMPLES = 2

# --- UNIFIED PLAYER-TURN STATE MACHINE ---
# SHADOW is safe until a real detector can continuously see hands *and* other
# stationary obstructions over the board.  UNIFIED refuses to auto-commit
# without that producer; LEGACY preserves the old polling/SPACE flow.
PLAYER_TURN_MODE = "SHADOW"  # "LEGACY" | "SHADOW" | "UNIFIED"
PLAYER_TURN_CLEAR_SECONDS = 0.8
PLAYER_TURN_CLEAR_SAMPLES = 3
PLAYER_TURN_INTERACTION_SETTLE_SECONDS = 1.2
PLAYER_TURN_IDLE_SETTLE_SECONDS = 3.0
PLAYER_TURN_IDLE_SETTLE_SAMPLES = 5
# Hardware integration must override this to AVAILABLE only after it can see a
# stationary hand, sleeve, and non-hand object on the board continuously.
PLAYER_TURN_INTERACTION_CAPABILITY = "UNAVAILABLE"

# --- THÔNG SỐ AI ---
AI_THINK_TIME = 10  # Time per move in seconds — AI gets 10s after subtracting TIME_BUFFER (0.5)
AI_DEPTH = 30          # Độ sâu mặc định (sẽ bị ghi đè bởi logic tự động)

# --- AI ENGINE CONFIGURATION ---
ENGINE_TYPE = "LOCAL" # "HYPrefixBRID" (Ưu tiên Cloud), "CLOUD" (Chỉ Cloud), "LOCAL" (Chỉ Local)
CLOUD_API_URL = "https://tuongkydaisu.com/api/engine/bestmove"
CLOUD_TIMEOUT_SEC = 5

# --- SIMULATION API CONFIGURATION ---
SIMULATION_API_URL = "https://tuongkydaisu.com"
SIMULATION_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJzaW11bGF0aW9uMDAxIiwicm9sZSI6IlNJTVVMQVRJT04iLCJ0b2tlbklkIjoiMTlkYjRjMDEtNjk4My00MTU5LTllNzYtODk0NDU5YjJhMjM5IiwiaWF0IjoxNzczMTI3MTE5LCJleHAiOjE4MDQ2NjMxMTl9.cHQEzHS-SqrZqUZ9FRcJgUE_BzyxZ60iiy7xYzZPQOo" # Liên hệ admin để lấy Token cấp cho app. Điền vào đây.

# --- MOONFISH ENGINE ---
# Hướng dẫn cho người mới clone repo:
# 1. Clone Moonfish engine: git clone https://github.com/walker8088/moonfish.git moonfish
# 2. Moonfish không cần NNUE file, chạy trực tiếp bằng Python
import os as _os
_BASE_DIR      = _os.path.dirname(_os.path.abspath(__file__))
_MOONFISH_DIR = _os.path.join(_BASE_DIR, 'moonfish')
MOONFISH_EXE  = _os.path.join(_MOONFISH_DIR, 'moonfish_ucci.py')
MOONFISH_NNUE = None  # Moonfish doesn't use NNUE
MOONFISH_THINK_MS = 1000  # Thời gian suy nghĩ mỗi nước (milliseconds)

# --- PLAYER-SELECTABLE AI DIFFICULTY ---
# All difficulty levels use the same local Moonfish engine.  The first three
# profiles deliberately restrict its search; ``impossible`` preserves the
# project's original Moonfish invocation (MOONFISH_THINK_MS, no added limits).
AI_DIFFICULTY = "hard"  # "easy" | "medium" | "hard" | "impossible"
AI_DIFFICULTY_PROFILES = {
    "easy": {
        "label": "Easy",
        "depth": 3,
        "nodes": 2_000,
        "temperature": 1.35,
        "think_ms": 200,
    },
    "medium": {
        "label": "Medium",
        "depth": 8,
        "nodes": 20_000,
        "temperature": 0.9,
        "think_ms": 1_000,
    },
    "hard": {
        "label": "Hard",
        "depth": 11,
        "nodes": 150_000,
        "temperature": 0.4,
        "think_ms": 2_000,
    },
    "impossible": {
        "label": "Impossible",
        "depth": None,
        "nodes": None,
        "temperature": None,
        "think_ms": None,
    },
}
# Legacy policy checkpoints remain available for training tooling, but they are
# not required to choose a difficulty in the game UI.
EASY_POLICY_MODEL = _os.path.join(_BASE_DIR, "models", "xiangqi_easy_policy.pt")
MEDIUM_POLICY_MODEL = _os.path.join(_BASE_DIR, "models", "xiangqi_medium_policy.pt")

# Tọa độ về nhà (Home) để né Camera
# IDLE_X = -72.027
# IDLE_Y = 200.248
# IDLE_Z = 278.586  

IDLE_X = -104.274
IDLE_Y = 149.608
IDLE_Z = 348.199
# --- CCHESS RECOGNITION (ONNX) ---
CCHESS_RECOGNITION_ENABLED = True  # Bật/tắt CChess ONNX recognition bổ sung
