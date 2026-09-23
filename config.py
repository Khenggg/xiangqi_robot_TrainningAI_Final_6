# =============================================================================
# === FILE: config.py (CẤU HÌNH TOÀN HỆ THỐNG) ===
# =============================================================================
import os as _os

# --- [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH] ---
# Các biến dưới đây chỉ phục vụ tương thích ngược với robot_VIP.py cũ.
# Luồng di chuyển mới (MotionCoordinator -> BoardPlacementState) hoàn toàn KHÔNG phụ thuộc vào chúng.
BOARD_ORIGIN_X = 200.0   # [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]
BOARD_ORIGIN_Y = -100.0  # [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]

# Offset điều chỉnh (mm) - [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]
OFFSET_X = 5.0   # [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]
OFFSET_Y = 0.0   # [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]

# Chiều hướng di chuyển so với gốc R1 - [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]
ROBOT_DIR_X = 1  # [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]
ROBOT_DIR_Y = 1  # [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]

# Kích thước vật lý bàn cờ & quân cờ (nguồn chuẩn hóa từ shared/physical_geometry.json)
from src.domain.geometry import get_physical_geometry as _get_physical_geometry
_geo = _get_physical_geometry()

CELL_SIZE_X = _geo.board.column_spacing   # [LEGACY ALIAS] Cạnh ô cờ 40.0mm (ngang)
CELL_SIZE_Y = _geo.board.row_spacing      # [LEGACY ALIAS] Cạnh ô cờ 40.0mm (dọc)
RIVER_GAP_Y = 0.00                        # [LEGACY ALIAS] Bù sông (0mm khi dùng cạnh ô 40mm đều)

BOARD_WIDTH_MM = _geo.board.outer_width   # Chiều ngang bàn cờ: 367.0 mm
BOARD_LENGTH_MM = _geo.board.outer_length # Chiều dài bàn cờ: 410.0 mm
PIECE_DIAMETER_MM = _geo.piece.diameter   # Đường kính quân cờ: 22.5 mm
PIECE_HEIGHT_MM = _geo.piece.height       # Chiều cao quân cờ: 9.43 mm
PLAYABLE_WIDTH_MM = _geo.board.playable_grid_width_mm   # Chiều ngang vùng chơi: 320.0 mm
PLAYABLE_LENGTH_MM = _geo.board.playable_grid_length_mm # Chiều dài vùng chơi: 360.0 mm
BOARD_MARGIN_X_MM = _geo.board.margin_horizontal_mm     # Lề trái/phải: 23.5 mm
BOARD_MARGIN_Y_MM = _geo.board.margin_vertical_mm       # Lề trên/dưới: 25.0 mm

# --- CAPTURE BIN PHYSICAL PROVENANCE & POSE ---
# Physical capture bin pose [X, Y, Z (mm), Rx, Ry, Rz (deg)].
# Gated by CAPTURE_BIN_VALIDATED: must remain False until Phase 4 physical validation.
CAPTURE_BIN_POSE_MM_DEG = [-226.123, 225.024, 291.68, -179.164, -3.047, -26.304]
CAPTURE_BIN_PROVENANCE = "LEGACY_UNVERIFIED"
CAPTURE_BIN_VALIDATED = False

# Legacy aliases for backward compatibility
CAPTURE_BIN_X = CAPTURE_BIN_POSE_MM_DEG[0]
CAPTURE_BIN_Y = CAPTURE_BIN_POSE_MM_DEG[1]
CAPTURE_BIN_Z = CAPTURE_BIN_POSE_MM_DEG[2]

# Độ cao an toàn (mm) - [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]
# Unified Motion Coordinator sử dụng độ cao tương đối so với mặt bàn (PICK_TCP_HEIGHT_MM, SAFE_CLEARANCE_Z_MM)
SAFE_Z  = 290.0    # [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]
PICK_Z  = 190.0    # [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]
PLACE_Z = 195.0    # [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]

# --- UNIFIED PHYSICAL MOTION PROFILE (RELATIVE TO BOARD SURFACE) ---
# Tọa độ gắp/thả và clearance được tính tương đối so với mặt phẳng bàn cờ (BoardPlacementState)
PICK_TCP_HEIGHT_MM = 4.715      # piece_height / 2 (PROVISIONAL_SIMULATION)
PLACE_TCP_HEIGHT_MM = 4.715
SAFE_CLEARANCE_Z_MM = 40.0
PICK_HEIGHT_PROVENANCE = "PROVISIONAL_SIMULATION"  # Đánh dấu nguồn gốc chưa qua kiểm chứng vật lý

# Cấu hình Kẹp (Gripper) - Tùy chỉnh theo loại van của bạn
GRIPPER_CLOSE = 1
GRIPPER_OPEN = 0
MOVE_SPEED = 50

# Cổng điều khiển Tool DO cho TwoOutputGripperDriver
TOOL_DO_OPEN = 1
TOOL_DO_CLOSE = 0
TOOL_DO_OPEN_PULSE_SEC = 0.30
TOOL_DO_CLOSE_PULSE_SEC = 0.30
TOOL_DO_DEADTIME_SEC = 0.10

# Góc xoay của đầu Robot (Rx, Ry, Rz) - Historical taught orientation
ROTATION = [-179.164, -3.047, -26.304] 

# --- PHYSICAL PICK / PLACE MOTION PROFILE ---
PICK_TOOL_ROTATION = list(ROTATION)
PLACE_TOOL_ROTATION = list(ROTATION)

# --- ROBOT BACKEND EXECUTION SELECTION ---
# Explicit backend selection: "PHYSICAL" or "VIRTUAL".
# Rejects any unlisted backend type to prevent accidental execution fallbacks.
ROBOT_BACKEND = _os.environ.get("ROBOT_BACKEND", "PHYSICAL").upper()
if ROBOT_BACKEND not in ("PHYSICAL", "VIRTUAL"):
    raise ValueError(f"Invalid ROBOT_BACKEND='{ROBOT_BACKEND}'. Must be 'PHYSICAL' or 'VIRTUAL'.")

# Kết nối Robot
ROBOT_IP = "192.168.58.2"
# DRY_RUN prevents real hardware actuation (mock/dry-run backend), NEVER bypasses motion architecture.
DRY_RUN = _os.environ.get("DRY_RUN", "False").lower() in ("true", "1", "yes")

# --- PHYSICAL BOARD CALIBRATION CONFIGURATION ---
# Chế độ hiệu chuẩn bàn cờ thực tế từ điểm dạy R1-R4:
# "POINTER_CONTACT": Dạy bằng bút đo/pointer tiếp xúc trực tiếp mặt bàn tại R1-R4 (offset = [0, 0, 0]).
# "KNOWN_OFFSET": Dạy bằng TCP có khoảng cách xác định tới mặt bàn. Yêu cầu khai báo OFFSET_MM, OFFSET_FRAME, PROVENANCE.
#
# CHẾ ĐỘ MẶC ĐỊNH: None (FAIL-CLOSED)
# Bắt buộc người vận hành phải cấu hình rõ ràng trước khi robot được phép chuyển động.
BOARD_CALIBRATION_MODE = None  # None / "UNCONFIGURED" / "POINTER_CONTACT" / "KNOWN_OFFSET"
BOARD_CALIBRATION_OFFSET_MM = [0.0, 0.0, 0.0]
BOARD_CALIBRATION_OFFSET_FRAME = "ROBOT_BASE"  # "ROBOT_BASE" hoặc "TOOL"
BOARD_CALIBRATION_PROVENANCE = "CALIBRATED_POINTER_CONTACT"

# Giới hạn độ nghiêng mặt bàn cờ cho phép (Physical Board Tilt Policy):
# Bàn cờ Xiangqi thực tế yêu cầu mặt phẳng gần như nằm ngang.
BOARD_MAX_TILT_WARNING_DEG = 2.5    # Cảnh báo khi độ nghiêng vượt quá 2.5°
BOARD_MAX_TILT_HARD_FAIL_DEG = 5.0   # Từ chối hiệu chuẩn & khóa chuyển động khi độ nghiêng >= 5.0°

# Camera index (0 = built-in webcam, 1 = USB cam, 2 = DroidCam, etc.)
# main.py will auto-try configured index first, then others if it fails.
VIDEO_SOURCE = 2

# --- VISUAL PICK CORRECTION ---
# Chỉ bù vị trí gắp khi snapshot mới từ camera xác nhận quân nằm gần ô logic.
# Tắt cờ này để trở lại hoàn toàn hành vi gắp tại tâm ô như trước đây.
VISUAL_PICK_ENABLED = True
VISUAL_PICK_MIN_CONFIDENCE = 0.45
VISUAL_PICK_MAX_OFFSET_CELLS = 0.25
VISUAL_PICK_FOOT_RATIO = 0.85

# --- HAND-AWARE AUTO MOVE CONFIRMATION ---
AUTO_MOVE_CONFIRM_ENABLED = False
HAND_MODEL_PATH = "models/hand_best_egohands.pt"
HAND_CONFIDENCE = 0.45
HAND_ABSENCE_SECONDS = 0.8
HAND_MIN_PRESENT_SECONDS = 0.25
AUTO_MOVE_CONFIRM_RETRIES = 10
AUTO_MOVE_CONFIRM_RETRY_SECONDS = 0.20

# --- THÔNG SỐ AI ---
AI_THINK_TIME = 10  # Time per move in seconds — AI gets 10s after subtracting TIME_BUFFER (0.5)
AI_DEPTH = 30          # Độ sâu mặc định (sẽ bị ghi đè bởi logic tự động)

# --- AI ENGINE CONFIGURATION ---
ENGINE_TYPE = "HYBRID" # "HYBRID" (Ưu tiên Cloud), "CLOUD" (Chỉ Cloud), "LOCAL" (Chỉ Local)
CLOUD_API_URL = "https://tuongkydaisu.com/api/engine/bestmove"
CLOUD_TIMEOUT_SEC = 5

# --- SIMULATION API CONFIGURATION ---
SIMULATION_API_URL = "https://tuongkydaisu.com"
# Secret token read securely from environment variable, avoiding hardcoded secrets in source control
SIMULATION_TOKEN = _os.environ.get("SIMULATION_TOKEN", "")

# --- MOONFISH ENGINE ---
_BASE_DIR      = _os.path.dirname(_os.path.abspath(__file__))
_MOONFISH_DIR = _os.path.join(_BASE_DIR, 'moonfish')
MOONFISH_EXE  = _os.path.join(_MOONFISH_DIR, 'moonfish_ucci.py')
MOONFISH_NNUE = None  # Moonfish doesn't use NNUE
MOONFISH_THINK_MS = 1000  # Thời gian suy nghĩ mỗi nước (milliseconds)

# Tọa độ về nhà (Home) để né Camera - [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]
IDLE_X = -72.027  # [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]
IDLE_Y = 200.248  # [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]
IDLE_Z = 278.586  # [LEGACY ONLY - DEPRECATED FOR UNIFIED MOTION PATH]

# --- OPTIONAL DEBUG DASHBOARD ---
ENABLE_DEBUG_DASHBOARD = False

