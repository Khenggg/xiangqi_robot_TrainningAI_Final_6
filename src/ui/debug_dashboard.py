"""Optional, read-only robot telemetry window."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time


class DebugDashboard:
    def __init__(self, dry_run):
        self.robot = None
        self.activity = "Home screen"
        self.mode = "DRY RUN" if dry_run else "REAL RUN"
        self._stop = threading.Event()
        self._process = None
        self._thread = None
        self._packet = None
        self._packet_time = 0.0
        try:
            self._process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve())],
                stdin=subprocess.PIPE, text=True, encoding="utf-8",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            print(f"[DEBUG] Could not open dashboard: {exc}")
            return
        self._thread = threading.Thread(target=self._publish, daemon=True)
        self._thread.start()

    def snapshot(self):
        data = {
            "mode": self.mode,
            "activity": self.activity,
            "connection": "Not connected",
            "live": "Unavailable",
            "planned": "No robot movement has been planned yet",
            "motion": "Unavailable",
            "tcp_speed": "Unavailable",
            "age": "No telemetry received",
        }
        robot = self.robot
        if robot is None:
            return data
        planned_command = getattr(robot, "get_planned_command", lambda: None)()
        if planned_command is not None:
            x, y, z, rx, ry, rz = planned_command["pose"]
            data["planned"] = (
                f"Next: {planned_command['command']} - {planned_command['label']}\n"
                f"X={x:.2f} mm  Y={y:.2f} mm  Z={z:.2f} mm\n"
                f"RX={rx:.2f} deg  RY={ry:.2f} deg  RZ={rz:.2f} deg"
            )
        if getattr(robot, "dry", False):
            data["connection"] = "Simulated (no physical telemetry)"
            return data
        if not getattr(robot, "connected", False) or getattr(robot, "robot", None) is None:
            return data
        data["connection"] = "Connected; waiting for telemetry"
        packet = getattr(robot.robot, "robot_state_pkg", None)
        if packet is None or isinstance(packet, type):
            return data
        now = time.monotonic()
        if packet is not self._packet:
            self._packet = packet
            self._packet_time = now
        age = now - self._packet_time
        data["age"] = f"{age:.1f} s since last received packet"
        if age > 2.0:
            data["connection"] = "Telemetry stale / disconnected"
            return data
        data["connection"] = "Connected"
        motion_names = {1: "Standby / stopped", 2: "Moving", 3: "Paused", 4: "Teach / drag mode"}
        data["motion"] = motion_names.get(getattr(packet, "robot_state", None), "Unknown state")
        target_speed = getattr(packet, "target_TCP_CmpSpeed", (0.0, 0.0))
        actual_speed = getattr(packet, "actual_TCP_CmpSpeed", (0.0, 0.0))
        data["tcp_speed"] = (
            f"Target: {target_speed[0]:.1f} mm/s | {target_speed[1]:.1f} deg/s\n"
            f"Actual: {actual_speed[0]:.1f} mm/s | {actual_speed[1]:.1f} deg/s"
        )
        pose = list(packet.tl_cur_pos)
        data["live"] = "\n".join(
            f"{axis}: {value:.2f} {unit}"
            for axis, value, unit in zip(
                ("X", "Y", "Z", "RX", "RY", "RZ"), pose,
                ("mm", "mm", "mm", "deg", "deg", "deg"),
            )
        )
        return data

    def _publish(self):
        while not self._stop.is_set() and self._process is not None and self._process.poll() is None:
            try:
                self._process.stdin.write(json.dumps(self.snapshot()) + "\n")
                self._process.stdin.flush()
            except (OSError, ValueError):
                break
            self._stop.wait(0.2)

    def close(self):
        self._stop.set()
        if self._process is None:
            return
        try:
            if self._process.poll() is None:
                self._process.terminate()
            self._process.wait(timeout=3)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        if self._thread is not None:
            self._thread.join(timeout=1)


def run_window():
    import queue
    import pygame

    pygame.init()
    screen = pygame.display.set_mode((620, 740))
    pygame.display.set_caption("Xiangqi Robot - Debug Dashboard")
    title_font = pygame.font.SysFont("Segoe UI", 24, bold=True)
    label_font = pygame.font.SysFont("Segoe UI", 14, bold=True)
    value_font = pygame.font.SysFont("Consolas", 16)
    inbox, fields = queue.Queue(maxsize=1), {}

    def receive():
        for line in sys.stdin:
            try:
                while not inbox.empty():
                    inbox.get_nowait()
                inbox.put(json.loads(line))
            except (json.JSONDecodeError, queue.Empty):
                continue

    threading.Thread(target=receive, daemon=True).start()
    clock, running = pygame.time.Clock(), True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        try:
            fields = inbox.get_nowait()
        except queue.Empty:
            pass
        screen.fill((24, 28, 35))
        screen.blit(title_font.render("System Monitor", True, (240, 244, 250)), (24, 20))
        y = 72
        for key, label in (("mode", "APP MODE"), ("activity", "APP STATUS"),
                           ("connection", "ROBOT CONNECTION"), ("motion", "ROBOT MOTION"),
                           ("tcp_speed", "TCP SPEED"), ("live", "LIVE TCP POSITION"),
                           ("planned", "PLANNED POSITION"), ("age", "TELEMETRY")):
            screen.blit(label_font.render(label, True, (148, 164, 182)), (24, y))
            y += 24
            for line in fields.get(key, "Waiting...").splitlines():
                screen.blit(value_font.render(line, True, (228, 234, 242)), (24, y))
                y += 21
            y += 12
        pygame.display.flip()
        clock.tick(10)
    pygame.quit()


if __name__ == "__main__":
    run_window()
