from types import SimpleNamespace

from src.ui.debug_dashboard import DebugDashboard


def test_dashboard_reports_all_requested_robot_telemetry_fields():
    dashboard = DebugDashboard.__new__(DebugDashboard)
    dashboard.mode = "REAL RUN"
    dashboard.activity = "Game setup"
    dashboard._packet = None
    dashboard._packet_time = 0.0
    packet = SimpleNamespace(
        tl_cur_pos=(1, 2, 3, 4, 5, 6),
        robot_state=2,
        target_TCP_CmpSpeed=(100, 20),
        actual_TCP_CmpSpeed=(95, 18),
    )
    dashboard.robot = SimpleNamespace(
        dry=False,
        connected=True,
        robot=SimpleNamespace(robot_state_pkg=packet),
        get_planned_command=lambda: {
            "command": "MoveCart",
            "label": "Test move",
            "pose": (10, 20, 30, 40, 50, 60),
        },
    )

    snapshot = dashboard.snapshot()

    assert snapshot["connection"] == "Connected"
    assert snapshot["motion"] == "Moving"
    assert "Target: 100.0 mm/s" in snapshot["tcp_speed"]
    assert "X: 1.00 mm" in snapshot["live"]
    assert "MoveCart - Test move" in snapshot["planned"]
    assert snapshot["age"].endswith("since last received packet")
