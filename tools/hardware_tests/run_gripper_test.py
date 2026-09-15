import time
import sys
import os

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(os.path.dirname(_THIS_DIR))
sys.path.insert(0, _PROJECT_DIR)

import config
from src.hardware import robot_sdk_core

def test_gripper_live():
    print(f"[TEST] Ket noi toi Robot {config.ROBOT_IP}...")
    robot = robot_sdk_core.RPC(config.ROBOT_IP)
    
    for t in range(5):
        time.sleep(1)
        if robot.SDK_state:
            print(f"[TEST] SDK ket noi thanh cong sau {t+1}s!")
            break
        print(f"[TEST] Dang doi SDK ket noi... ({t+1}/5)")

    # 1. Thử Tool DO0
    print("\n" + "="*50)
    print(">>> [BUOC 1] TEST TOOL DO0 (id=0 tren dau canh tay robot)")
    print("="*50)
    print(">>> Gui lenh: SetToolDO(id=0, status=1) - BAT DIEN (DONG KEP)")
    err1 = robot.SetToolDO(0, 1, block=1)
    print(f"    Ket qua: err={err1} (0 la thanh cong)")
    print("    Dang giu ON trong 3 giay... Hay quan sat kep!")
    time.sleep(3)

    print(">>> Gui lenh: SetToolDO(id=0, status=0) - TAT DIEN (MO KEP)")
    err0 = robot.SetToolDO(0, 0, block=1)
    print(f"    Ket qua: err={err0}")
    time.sleep(1)

    # 2. Thử Tool DO1
    print("\n" + "="*50)
    print(">>> [BUOC 2] TEST TOOL DO1 (id=1 tren dau canh tay robot)")
    print("="*50)
    print(">>> Gui lenh: SetToolDO(id=1, status=1) - BAT DIEN (DONG KEP)")
    err1 = robot.SetToolDO(1, 1, block=1)
    print(f"    Ket qua: err={err1} (0 la thanh cong)")
    print("    Dang giu ON trong 3 giay... Hay quan sat kep!")
    time.sleep(3)

    print(">>> Gui lenh: SetToolDO(id=1, status=0) - TAT DIEN (MO KEP)")
    err0 = robot.SetToolDO(1, 0, block=1)
    print(f"    Ket qua: err={err0}")
    time.sleep(1)

    # 3. Thử Controller DO0 và DO1 (trong tủ điều khiển)
    print("\n" + "="*50)
    print(">>> [BUOC 3] TEST CONTROLLER DO0 & DO1 (trong tu dien)")
    print("="*50)
    for c_id in [0, 1]:
        print(f">>> Gui lenh: SetDO(id={c_id}, status=1)")
        err = robot.SetDO(c_id, 1, block=1)
        print(f"    SetDO({c_id}, 1) err={err}")
        time.sleep(2)
        robot.SetDO(c_id, 0, block=1)
        print(f"    SetDO({c_id}, 0)")
        time.sleep(0.5)

    print("\n" + "="*50)
    print(">>> HOAN TAT TEST!")
    print("="*50)

if __name__ == "__main__":
    test_gripper_live()
