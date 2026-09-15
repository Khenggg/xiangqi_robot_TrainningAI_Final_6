"""Optional read-only dashboard, isolated from the game's blocking operations."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time


class DebugDashboard:
    def __init__(self, dry_run):
        self.robot = None
        self.activity = "Initializing"
        self.mode = "DRY RUN" if dry_run else "REAL RUN"
        self._stop = threading.Event()
        self._packet = None
        self._packet_time = 0.0
        self._process = None
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
        data = {"mode": self.mode, "activity": self.activity,
                "connection": "Not connected", "live": "Unavailable",
                "planned": "No robot movement has been planned yet",
                "motion": "Unavailable", "tcp_speed": "Unavailable",
                "age": "No telemetry received"}
        robot = self.robot
        if robot is None:
            return data
        planned = robot.get_planned_command()
        if planned is not None:
            x, y, z, rx, ry, rz = planned["pose"]
            data["planned"] = (
                f"Next: {planned['command']} — {planned['label']}\n"
                f"X={x:.2f} mm  Y={y:.2f} mm  Z={z:.2f} mm\n"
                f"RX={rx:.2f}°  RY={ry:.2f}°  RZ={rz:.2f}°"
            )
        if robot.dry:
            data["connection"] = "Simulated (no physical telemetry)"
            return data
        sdk = robot.robot
        if not robot.connected or sdk is None:
            return data
        data["connection"] = "Connected; waiting for telemetry"
        packet = getattr(sdk, "robot_state_pkg", None)
        # SDK initializes this field to the ctypes class before receiving data.
        if packet is None or isinstance(packet, type):
            return data
        now = time.monotonic()
        # The SDK replaces the packet object whenever a new frame arrives.
        if packet is not self._packet:
            self._packet = packet
            self._packet_time = now
        age = now - self._packet_time
        data["age"] = f"{age:.1f} s since last received packet"
        if age > 2.0:
            data["connection"] = "Telemetry stale / disconnected"
            return data
        data["connection"] = "Connected"
        motion_names = {
            1: "Standby / stopped",
            2: "Moving",
            3: "Paused",
            4: "Teach / drag mode",
        }
        data["motion"] = motion_names.get(packet.robot_state, f"Unknown state ({packet.robot_state})")
        target_linear, target_angular = packet.target_TCP_CmpSpeed
        actual_linear, actual_angular = packet.actual_TCP_CmpSpeed
        data["tcp_speed"] = (
            f"Target: {target_linear:.1f} mm/s  |  {target_angular:.1f} deg/s\n"
            f"Actual: {actual_linear:.1f} mm/s  |  {actual_angular:.1f} deg/s"
        )
        pose = list(packet.tl_cur_pos)
        data["live"] = "\n".join(
            f"{axis:>2}: {value:10.2f} {unit}"
            for axis, value, unit in zip(
                ("X", "Y", "Z", "RX", "RY", "RZ"), pose,
                ("mm", "mm", "mm", "deg", "deg", "deg")))
        return data

    def _publish(self):
        while not self._stop.is_set() and self._process.poll() is None:
            try:
                data = self.snapshot()
                self._process.stdin.write(json.dumps(data) + "\n")
                self._process.stdin.flush()
            except (OSError, ValueError):
                break
            except Exception as exc:
                print(f"[DEBUG] Telemetry unavailable: {exc}")
                break
            self._stop.wait(0.2)

    def close(self):
        self._stop.set()
        try:
            if self._process is not None:
                if self._process.poll() is None:
                    self._process.terminate()
                self._process.wait(timeout=3)
                self._thread.join(timeout=1)
                if self._process.stdin:
                    self._process.stdin.close()
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass  # Debug UI cleanup must never prevent hardware cleanup.


def run_window():
    import os
    import queue

    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    import pygame

    pygame.display.init()
    pygame.font.init()
    screen = pygame.display.set_mode((620, 740))
    pygame.display.set_caption("Xiangqi - Debug dashboard")
    title_font = pygame.font.SysFont("Segoe UI", 25, bold=True)
    label_font = pygame.font.SysFont("Segoe UI", 15)
    value_font = pygame.font.SysFont("Consolas", 17)
    inbox = queue.Queue(maxsize=1)
    fields = {}
    disconnected = threading.Event()

    def receive():
        try:
            for line in sys.stdin:
                data = json.loads(line)
                try:
                    inbox.get_nowait()
                except queue.Empty:
                    pass
                inbox.put(data)
        finally:
            disconnected.set()

    threading.Thread(target=receive, daemon=True).start()
    clock = pygame.time.Clock()
    running = True
    while running and not disconnected.is_set():
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        try:
            fields = inbox.get_nowait()
        except queue.Empty:
            pass
        screen.fill((24, 28, 35))
        screen.blit(title_font.render("System monitor", True, (240, 244, 250)), (24, 20))
        y = 72
        for key, title in (("mode", "APP MODE"), ("activity", "APP STATUS"),
                           ("connection", "ROBOT CONNECTION"), ("motion", "ROBOT MOTION"),
                           ("tcp_speed", "TCP SPEED"), ("live", "LIVE TCP POSITION"),
                           ("planned", "PLANNED POSITION"), ("age", "TELEMETRY")):
            screen.blit(label_font.render(title, True, (148, 164, 182)), (24, y))
            y += 24
            value = fields.get(key, "Waiting...")
            for line in value.splitlines():
                # Wrap descriptive messages to fit the fixed-width dashboard.
                words = line.split(" ")
                row = ""
                for word in words:
                    candidate = row + " " + word if row else word
                    if value_font.size(candidate)[0] > 570 and row:
                        screen.blit(value_font.render(row, True, (228, 234, 242)), (24, y))
                        y += 22
                        row = word
                    else:
                        row = candidate
                screen.blit(value_font.render(row, True, (228, 234, 242)), (24, y))
                y += 22
            y += 12
        pygame.display.flip()
        clock.tick(10)
    pygame.quit()


if __name__ == "__main__":
    run_window()
