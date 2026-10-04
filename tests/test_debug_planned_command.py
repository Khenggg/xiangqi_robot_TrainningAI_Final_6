from src.hardware.robot_VIP import FR5Robot


def test_planned_command_is_copied_for_dashboard_readers():
    robot = FR5Robot.__new__(FR5Robot)
    import threading
    robot._planned_command_lock = threading.Lock()
    robot._planned_command = None

    robot._set_planned_command("MoveCart", [1, 2, 3, 4, 5, 6], "Approach grid (1, 2)")
    command = robot.get_planned_command()
    command["pose"][0] = 99

    assert robot.get_planned_command() == {
        "command": "MoveCart",
        "pose": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "label": "Approach grid (1, 2)",
    }
