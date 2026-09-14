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
SAFE_Z  = 290.0    # Độ cao an toàn khi di chuyển giữa các ô (tăng lên để tránh hất quân)
PICK_Z  = 190.0   # Hạ xuống gắp (Đã nâng lên để tránh đập bàn, hạ từ từ)
PLACE_Z = 195.0   # Hạ xuống đặt

# Cấu hình Kẹp (Gripper) - Tùy chỉnh theo loại van của bạn
GRIPPER_CLOSE = 1
GRIPPER_OPEN = 0
MOVE_SPEED = 50

# Góc xoay của đầu Robot (Rx, Ry, Rz)
ROTATION = [-179.164, -3.047, -26.304] 

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
VIDEO_SOURCE = 2

# --- VISUAL PICK CORRECTION ---
# Chỉ bù vị trí gắp khi snapshot mới từ camera xác nhận quân nằm gần ô logic.
# Tắt cờ này để trở lại hoàn toàn hành vi gắp tại tâm ô như trước đây.
VISUAL_PICK_ENABLED = True
VISUAL_PICK_MIN_CONFIDENCE = 0.45
VISUAL_PICK_MAX_OFFSET_CELLS = 0.25
VISUAL_PICK_FOOT_RATIO = 0.85

# --- THÔNG SỐ AI ---
AI_THINK_TIME = 10  # Time per move in seconds — AI gets 10s after subtracting TIME_BUFFER (0.5)
AI_DEPTH = 30          # Độ sâu mặc định (sẽ bị ghi đè bởi logic tự động)

# --- AI ENGINE CONFIGURATION ---
ENGINE_TYPE = "HYBRID" # "HYPrefixBRID" (Ưu tiên Cloud), "CLOUD" (Chỉ Cloud), "LOCAL" (Chỉ Local)
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

# Tọa độ về nhà (Home) để né Camera
IDLE_X = -72.027
IDLE_Y = 200.248
IDLE_Z = 278.586  
