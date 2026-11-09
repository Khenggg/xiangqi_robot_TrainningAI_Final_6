# =============================================================================
# === FILE: config.py (CẤU HÌNH TOÀN HỆ THỐNG) ===
# =============================================================================

# --- THÔNG SỐ ROBOT BÀN CỜ (HARDCODED TOẠ ĐỘ TOÁN HỌC) ---
# Tọa độ gốc (Điểm R1 - tương ứng Xe Đen Trái, ô col=0, row=0)
# Luồng robot thật dùng bộ điểm cố định PHYSICAL_TEACHING_POINTS_FILE bên dưới.
BOARD_ORIGIN_X = 200.0  
BOARD_ORIGIN_Y = -100.0 

# Offset điều chỉnh (mm) - Dùng để tinh chỉnh vị trí gắp
# Nếu robot gắp lệch, điều chỉnh các giá trị này:
# - OFFSET_X: Dương = dịch xuống dưới (về phía row=9), Âm = dịch lên trên (về phía row=0)
# - OFFSET_Y: Dương = dịch sang phải (về phía col=8), Âm = dịch sang trái (về phía col=0)
OFFSET_X = 5.0   # Robot gắp lệch lên trên 5mm → cần dịch xuống 5mm
OFFSET_Y = 0.0   # Không lệch ngang

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
# Nguồn: origin/feature/visual-correction-v2@fb0598d (2026-10-09).
# CHƯA đo lại trên robot hiện tại; phải kiểm tra clearance trước khi chạy.
SAFE_Z  = 220.0
PICK_Z  = 178.0   # Hạ xuống gắp (Đã nâng lên để tránh đập bàn, hạ từ từ)
PLACE_Z = 178.0   # Hạ xuống đặt

# Cấu hình kẹp: motor 2 chiều dùng Tool DO trên đầu robot.
# Sau đổi dây 2026-11-02, đã thử riêng từng DO: DO0 MỞ, DO1 ĐÓNG.
# Không bao giờ bật cả hai cùng lúc.
GRIPPER_ACTION_CLOSE = "close"
# There is no jaw-position sensor: each state below is established only by
# calibrated motor timing on the real gripper.
GRIPPER_ACTION_OPEN_MAX = "open_max"
GRIPPER_ACTION_RELEASE = "release"
GRIPPER_ACTION_CLOSE_TO_SAFE_GAP = "close_to_safe_gap"
GRIPPER_OPEN_DO_ID = 0
GRIPPER_CLOSE_DO_ID = 1
GRIPPER_IDLE_STATUS = 0
GRIPPER_ACTIVE_STATUS = 1

# Motor không có công tắc hành trình: chỉ cấp điện theo xung ngắn rồi tắt cả hai DO.
# Tinh chỉnh hai PULSE riêng sau khi thử với tay robot đứng yên và không có quân cờ.
GRIPPER_DIRECTION_DEADTIME_SEC = 0.10
# Open fully only when establishing the initial jaw opening or at the capture bin.
# Tune this to the shortest pulse that reaches the physical open limit.
GRIPPER_OPEN_MAX_PULSE_SEC = 0.3
# User-selected short opening when releasing a piece on the board.
GRIPPER_RELEASE_PULSE_SEC = 0.06
GRIPPER_CLOSE_PULSE_SEC = 0.8
# Starting from fully open, close only to the travelling/pre-pick safe gap.
# Increase to narrow the gap; decrease to widen it. Do not drive into hard stop.
GRIPPER_SAFE_GAP_CLOSE_PULSE_SEC = 0.06
GRIPPER_OPEN_SETTLE_SEC = 0.25
GRIPPER_CLOSE_SETTLE_SEC = 0.25
MOVE_SPEED = 50 #Percentage based; visual-correction-v2@fb0598d

# --- ROBOT FRAME POLICY ---
# Toàn bộ teaching point và lệnh chuyển động phải dùng robot base (user 0).
# R1-R4, HOMECHESS, R_Trash phải được dạy trong cùng một tool frame.
# ROBOT_TOOL_FRAME = None: chấp nhận tool duy nhất mà controller trả về.
# Đặt số cụ thể (ví dụ 0) để bắt buộc đúng tool đó.
ROBOT_USER_FRAME = 0
ROBOT_TOOL_FRAME = None
ROBOT_FRAME_POLICY = "BASE_ONLY"
# Frozen recorded poses/joints, normalized to robot_base / tool 0 / user 0.
# Runtime never rereads controller teaching points or WObj for this profile.
# None selects the legacy controller-reading path for explicit diagnostics.
PHYSICAL_TEACHING_POINTS_FILE = "calibration/physical_teaching_points_user0.json"
# If a teaching point was stored under the current WObj but that WObj's
# coordinate offset is exactly identity, its coordinates are numerically the
# same as robot base. Normalize that metadata to user 0 after verifying the
# offset read-only. Never normalizes a nonzero/unknown WObj transform.
ALLOW_IDENTITY_WOBJ_AS_BASE = True

# Góc xoay của đầu Robot (Rx, Ry, Rz)
# Nguồn: origin/feature/visual-correction-v2@fb0598d (a52c8e4, 2026-10-08).
# Đây là profile ứng viên, CHƯA đo trên robot hiện tại.
MOTION_PROFILE_SOURCE = "origin/feature/visual-correction-v2@fb0598d"
MOTION_PROFILE_VERIFIED = False
ROTATION = [180, 0, -73.2]

# --- PHYSICAL PICK / PLACE MOTION PROFILE ---
# Các pose Cartesian FR5 gồm [X, Y, Z, Rx, Ry, Rz]. XY được nội suy từ R1-R4;
# ba góc dưới đây là tư thế tool đã được dạy để ngàm kẹp hướng đúng xuống quân.
#
# Để đổi hướng ngàm thật: đưa robot đến một ô trống ở SAFE_Z bằng pendant,
# xoay wrist/tool tới hướng kẹp đúng và chép Rx/Ry/Rz hiển thị vào PICK_TOOL_ROTATION.
# Không sửa tool frame/TCP trong code. Khi chưa dạy lại, giữ nguyên ROTATION hiện tại.
# Lưu ý: visual-correction-v2 còn dùng pulse kẹp 0.25/0.20; KHÔNG tự lấy vì
# pulse thuộc cơ cấu kẹp và phải đo trên robot hiện tại.
PICK_TOOL_ROTATION = list(ROTATION)
# Thông thường đặt dùng cùng hướng với gắp; tách biến để có thể hiệu chỉnh sau này.
PLACE_TOOL_ROTATION = list(ROTATION)

# Kết nối Robot
ROBOT_IP = "192.168.58.2"
import os as _runtime_os
ROBOT_BACKEND = _runtime_os.environ.get("ROBOT_BACKEND", "VIRTUAL").upper()
if ROBOT_BACKEND not in ("VIRTUAL", "PHYSICAL"):
    raise ValueError("ROBOT_BACKEND must be VIRTUAL or PHYSICAL")
DRY_RUN = _runtime_os.environ.get("DRY_RUN", "1").strip().lower() not in ("0", "false", "no")
SIMULATION_SPEED_FACTOR = 0.2
SIMULATION_PROFILE = _runtime_os.environ.get("XIANGQI_SIMULATION_PROFILE", "detailed").strip().lower()
SIMULATION_FAST_SPEED_FACTOR = 1.0
TELEMETRY_HOST = "127.0.0.1"
TELEMETRY_PORT = 8765
# Physical teaching poses are not assumed to be board-surface contact points.
# Configure these from the recorded calibration before enabling a physical mirror.
BOARD_CALIBRATION_OFFSET_MM = None
BOARD_CALIBRATION_OFFSET_FRAME = "ROBOT_BASE"
BOARD_CALIBRATION_PROVENANCE = ""
# XY mirror calibration uses measured grid dimensions and an independent surface Z.
# Unconfigured values leave the optional board mirror unavailable; raw arm/Game run
# keep their own connection and donor command coordinates.
BOARD_CALIBRATION_MODEL = "XY_SE2"
BOARD_CALIBRATION_GRID_DIMENSIONS_MM = None
BOARD_CALIBRATION_SURFACE_Z_MM = None
BOARD_CALIBRATION_USER_TO_BASE_XY = None
BOARD_CALIBRATION_FRAME_PROVENANCE = ""
# Với BASE_ONLY, mirror bàn từ chối mọi teaching point có user khác 0.
BOARD_CALIBRATION_REQUIRE_BASE_FRAME = True
# Z mặt bàn cho mirror: "MEASURED" dùng BOARD_CALIBRATION_SURFACE_Z_MM,
# "R1_R4" lấy median Z của bốn điểm đã dạy. Chỉ bật R1_R4 sau khi xác nhận
# cả bốn điểm được dạy tại mặt bàn (không phải SAFE_Z).
BOARD_SURFACE_Z_SOURCE = "R1_R4"
R1_R4_TAUGHT_AT_BOARD_SURFACE = False
BOARD_CALIBRATION_Z_TOLERANCE_MM = 1.0

# Camera index (0 = built-in webcam, 1 = USB cam, 2 = DroidCam, etc.)
# VIDEO_INDEX overrides the first choice; startup then tries remaining indices 0-2.
VIDEO_SOURCE = 2
AUTO_ENABLE_PHYSICAL_ON_STARTUP = True  # Once per new session, with existing checks; no HOME/gripper.
# Mặc định dùng perspective.npy đã lưu; mở calibration tương tác khi
# chạy --recalibrate-camera, tick checkbox camera trên launcher, hoặc chưa có file.
RECALIBRATE_CAMERA = False
# Camera launcher checkbox: skip auto-detected corners and open the manual
# four-corner click window (CALIBRATE) during physical camera initialization.
CAMERA_CALIBRATION_MANUAL_ONLY = False

# --- VISUAL PICK CORRECTION ---
# Chỉ bù vị trí gắp khi snapshot mới từ camera xác nhận quân nằm gần ô logic.
# Tắt cờ này để trở lại hoàn toàn hành vi gắp tại tâm ô như trước đây.
VISUAL_PICK_ENABLED = True
VISUAL_PICK_MIN_CONFIDENCE = 0.45
# Physical radial limit from the expected intersection; old cell limit is fallback only.
VISUAL_PICK_MAX_OFFSET_MM = 6.0
VISUAL_PICK_MAX_OFFSET_CELLS = 0.25
# Permit measured piece centres just beyond the outermost grid intersection.
# Shared by the camera estimator and physical XY conversion; never clamp XY.
VISUAL_PICK_OUTSIDE_MARGIN_MM = 6.0
VISUAL_PICK_FOOT_RATIO = 0.85
VISUAL_PICK_SAMPLE_COUNT = 3
VISUAL_PICK_MIN_STABLE_SAMPLES = 2
VISUAL_CENTER_PICK_ATTEMPTS = 3
VISUAL_CENTER_PICK_MAX_JITTER_CELLS = 0.12
# Bounded retry around transient hand/arm/lighting occlusion before PICK_PAUSED.
VISUAL_PICK_RETRY_ATTEMPTS = 3
VISUAL_PICK_RETRY_INTERVAL_SEC = 0.4
# Occupancy checks use the whole calibrated square, not the narrower safe-pick radius.
VISUAL_OCCUPANCY_CELL_HALF_WIDTH = 0.50
# When enabled, physical robot moves require CChess layout identity checks to
# match the in-memory FEN before the gripper may pick.  Set False only for
# supervised fallback operation when the layout model is unavailable.
# This toggle applies to legacy/manual verification calls. Physical motion
# always requires fresh full-board identity verification before and after motion.
VISUAL_BOARD_SYNC_REQUIRED = True

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

# Physical full-board verification: bounded retry before failing. Exact board
# equality is never relaxed; this only waits for hands/arm/lighting to clear.
VERIFY_BOARD_RETRY_TIMEOUT_SEC = 2.0
VERIFY_BOARD_RETRY_POLL_SEC = 0.15
# Confidence gate for recovery/FEN scans. Applied only to occupied cells;
# empty-cell confidence is not evidence about the board. Lower only after
# confirming labels are correct; exact board equality is still required.
CCHESS_RECOVERY_MIN_CONFIDENCE = 0.5

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
SIMULATION_TOKEN = _runtime_os.environ.get("XIANGQI_SIMULATION_TOKEN", "")

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
VISION_DEVICE = _runtime_os.environ.get("VISION_DEVICE", "auto").lower()

# Gameplay remains owned by the visual application.
GAME_MODE = _os.environ.get("GAME_MODE", "HUMAN_VS_ROBOT").upper()
