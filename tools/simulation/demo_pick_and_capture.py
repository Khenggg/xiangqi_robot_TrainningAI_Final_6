#!/usr/bin/env python3
"""
Interactive Demonstration of Virtual FR3 Arm:
- Di quân (Normal Pick & Place Move)
- Ăn quân (19-Step 2-Phase Capture Choreography with Capture Bin)

Executes 100% in simulation (DRY_RUN=True, ROBOT_BACKEND="VIRTUAL").
No physical camera or robot hardware required.
Live 3D motion streams to http://localhost:8085 (ws://127.0.0.1:8765).
"""

import os
import sys
import time
from pathlib import Path

# Ensure project root in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Ensure UTF-8 output on Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from src.hardware.hardware_manager import HardwareManager
from src.hardware.telemetry_publisher import TelemetryPublisher


def run_demonstration():
    print("=" * 70)
    print("   🤖 DEMO MÔ PHỎNG CÁNH TAY ROBOT FR3: DI QUÂN & ĂN QUÂN (DRY-RUN)")
    print("=" * 70)
    print("   🌐 3D Web Viewer:   http://localhost:8085")
    print("   📡 WebSocket Feed:  ws://127.0.0.1:8765")
    print("   🛡️ Safety Mode:     DRY_RUN = True, ROBOT_BACKEND = 'VIRTUAL'")
    print("=" * 70)
    print("\n👉 MẸO: Mở trình duyệt tại http://localhost:8085 để xem cánh tay robot 3D")
    print("       gắp, nhấc, di chuyển và bỏ quân vào khay ăn quân theo thời gian thực!\n")

    # 1. Khởi tạo HardwareManager ở chế độ ảo
    config.DRY_RUN = True
    config.ROBOT_BACKEND = "VIRTUAL"
    config.CAPTURE_BIN_VALIDATED = True  # Cho phép ăn quân trong mô phỏng

    print("[1/3] Đang khởi tạo HardwareManager (Virtual Simulation Mode)...")
    hw = HardwareManager(config, str(_PROJECT_ROOT)).initialize_all()

    # Kết nối TelemetryPublisher để truyền chuyển động tới 3D Viewer nếu có
    try:
        telemetry = TelemetryPublisher.get_instance(host="127.0.0.1", port=8765, robot_model="FR3")
        telemetry.start()
        if hw.backend:
            hw.backend.telemetry_publisher = telemetry
        print("  ✅ Đã kích hoạt Telemetry Publisher trên cổng 8765.")
    except Exception as e:
        print(f"  ℹ️ Telemetry server status: {e}")

    print(f"  ✅ Robot backend sẵn sàng: {hw.is_robot_ready} (Lifecycle: {hw.lifecycle_state})")
    time.sleep(1.0)

    # 2. DEMO 1: Di quân bình thường (Normal Move: Pick & Place)
    print("\n" + "=" * 70)
    print("📌 KỊCH BẢN 1: DI QUÂN (NORMAL MOVE)")
    print("   Quân cờ: Pháo đen tại ô (row=2, col=1) -> tiến lên ô (row=4, col=1)")
    print("=" * 70)
    print("  -> Đang tính toán nghịch đảo động học (IK) và lập quỹ đạo...")

    res_move = hw.execute_piece_move(
        s_col=1, s_row=2,
        d_col=1, d_row=4,
        is_capture=False,
    )

    if res_move.success:
        print("  🎉 [THÀNH CÔNG] Robot đã thực hiện xong nước di quân (4, 1)!")
        print(f"     Trạng thái kết thúc: {res_move.last_completed_stage}, Payload: {res_move.payload_state}")
    else:
        print(f"  ❌ [THẤT BẠI] Lỗi di quân: {res_move.message}")

    time.sleep(2.0)

    # 3. DEMO 2: Ăn quân (Capture Move: 19-Step Choreography với Capture Bin)
    print("\n" + "=" * 70)
    print("📌 KỊCH BẢN 2: ĂN QUÂN (CAPTURE MOVE)")
    print("   Tình huống: Pháo đen tại (row=2, col=4) ăn Tốt đỏ tại (row=6, col=4)")
    print("   Quy trình 19 bước (2 giai đoạn):")
    print("     • Giai đoạn 1: Robot tới ô (6, 4) gắp Tốt đỏ -> mang bỏ vào Khay ăn quân (Capture Bin) -> nhả kẹp")
    print("     • Giai đoạn 2: Robot quay lại ô (2, 4) gắp Pháo đen -> di chuyển tới ô (6, 4) -> đặt xuống -> rút về an toàn")
    print("=" * 70)
    print("  -> Đang kích hoạt MotionResolver.resolve_capture()...")

    res_capture = hw.execute_piece_move(
        s_col=4, s_row=2,
        d_col=4, d_row=6,
        is_capture=True,
    )

    if res_capture.success:
        print("  🎉 [THÀNH CÔNG] Robot đã hoàn tất 19 bước ăn quân vào khay Capture Bin!")
        print(f"     Trạng thái kết thúc: {res_capture.last_completed_stage}, Payload: {res_capture.payload_state}")
    else:
        print(f"  ❌ [THẤT BẠI] Lỗi ăn quân: {res_capture.message}")

    print("\n" + "=" * 70)
    print("✅ TOÀN BỘ DEMO ĐÃ HOÀN TẤT AN TOÀN TRÊN MÔ PHỎNG (ZERO HARDWARE RISK)!")
    print("=" * 70)

    hw.cleanup()


if __name__ == "__main__":
    run_demonstration()
