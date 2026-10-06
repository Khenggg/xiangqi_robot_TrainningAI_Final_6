"""Optional, read-only robot telemetry window."""
import json
import math
from functools import lru_cache
from pathlib import Path
import subprocess
import sys
import threading
import time


@lru_cache(maxsize=1)
def _camera_inverse(path, modified):
    import numpy as np
    return np.linalg.inv(np.load(path))


def camera_correction(correction):
    """Project the final nominal/corrected grid points into camera pixels."""
    import cv2
    import numpy as np
    path = Path(__file__).resolve().parents[2] / "perspective.npy"
    points = np.array([[correction["cell"], correction["target"]]], dtype=np.float64)
    pixels = cv2.perspectiveTransform(points, _camera_inverse(str(path), path.stat().st_mtime_ns))[0]
    delta = pixels[1] - pixels[0]
    if not np.isfinite(delta).all():
        raise ValueError("Invalid camera projection")
    return float(delta[0]), float(delta[1])


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
            "correction": None,
        }
        robot = self.robot
        if robot is None:
            return data
        correction = getattr(robot, "visual_pick_correction", None)
        if correction is not None:
            data["correction"] = dict(correction)
            try:
                dx, dy = camera_correction(correction)
                data["correction"].update(dx_px=dx, dy_px=dy)
            except (OSError, ValueError, KeyError):
                data["correction"].update(dx_px=None, dy_px=None)
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


def dial_vector(x, y, rotation):
    """Robot +X points right, +Y up; rotation is clockwise on screen."""
    angle = math.radians(rotation)
    return (x * math.cos(angle) + y * math.sin(angle),
            x * math.sin(angle) - y * math.cos(angle))


def draw_correction_dial(screen, pygame, font, correction, rotation):
    center, radius = (800, 250), 120
    muted, white, red = (148, 164, 182), (228, 234, 242), (255, 100, 100)
    pygame.draw.circle(screen, muted, center, radius, 2)
    for x, y, label in ((1, 0, "X"), (0, 1, "Y")):
        vx, vy = dial_vector(x, y, rotation)
        start = (center[0] - vx * 145, center[1] - vy * 145)
        end = (center[0] + vx * 145, center[1] + vy * 145)
        pygame.draw.line(screen, muted, start, end, 2)
        pygame.draw.polygon(screen, muted, [end,
            (end[0] - vx * 12 - vy * 5, end[1] - vy * 12 + vx * 5),
            (end[0] - vx * 12 + vy * 5, end[1] - vy * 12 - vx * 5)])
        text = font.render("+" + label, True, white)
        screen.blit(text, text.get_rect(center=(center[0] + vx * 170, center[1] + vy * 170)))
    lines = ["Waiting for a pick", "Length: -- px"]
    if correction is not None and correction.get("dx_px") is None:
        lines = ["Camera calibration unavailable", "Length: -- px"]
    elif correction is not None:
        dx, dy = correction["dx_px"], correction["dy_px"]
        length = math.hypot(dx, dy)
        if length > 1e-6:
            vx, vy = dial_vector(dx / length, -dy / length, rotation)
            end = (center[0] + vx * 105, center[1] + vy * 105)
            pygame.draw.line(screen, red, center, end, 4)
            pygame.draw.polygon(screen, red, [end,
                (end[0] - vx * 17 - vy * 8, end[1] - vy * 17 + vx * 8),
                (end[0] - vx * 17 + vy * 8, end[1] - vy * 17 - vx * 8)])
        else:
            pygame.draw.circle(screen, red, center, 5)
        status = "Picking now" if correction["active"] else "Last pick"
        lines = [status + f" - cell {tuple(correction['cell'])}",
                 f"Length: {length:.2f} px",
                 f"X: {dx:+.2f} px   Y: {-dy:+.2f} px (up)",
                 "Camera correction" if correction["visual"] else "Nominal pick (no correction)"]
    for index, line in enumerate(lines):
        text = font.render(line, True, white)
        screen.blit(text, text.get_rect(center=(800, 445 + index * 26)))
    text = font.render("Arrow shows direction; length shown above", True, muted)
    screen.blit(text, text.get_rect(center=(800, 570)))


def run_window():
    import queue
    import pygame

    pygame.init()
    screen = pygame.display.set_mode((1000, 780))
    pygame.display.set_caption("Xiangqi Robot - Debug Dashboard")
    title_font = pygame.font.SysFont("Segoe UI", 24, bold=True)
    label_font = pygame.font.SysFont("Segoe UI", 14, bold=True)
    value_font = pygame.font.SysFont("Segoe UI", 16)
    inbox, fields = queue.Queue(maxsize=1), {}
    rotation = 0
    rotate_left = pygame.Rect(665, 610, 120, 42)
    rotate_right = pygame.Rect(815, 610, 120, 42)

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
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if rotate_left.collidepoint(event.pos):
                    rotation = (rotation - 90) % 360
                elif rotate_right.collidepoint(event.pos):
                    rotation = (rotation + 90) % 360
        try:
            fields = inbox.get_nowait()
        except queue.Empty:
            pass
        screen.fill((24, 28, 35))
        screen.blit(title_font.render("System Monitor", True, (240, 244, 250)), (24, 20))
        screen.blit(label_font.render("VISUAL PICK CORRECTION (CAMERA X/Y)", True, (148, 164, 182)), (640, 72))
        draw_correction_dial(screen, pygame, value_font, fields.get("correction"), rotation)
        for rect, label in ((rotate_left, "Rotate -90"), (rotate_right, "Rotate +90")):
            pygame.draw.rect(screen, (55, 67, 84), rect, border_radius=6)
            text = value_font.render(label, True, (228, 234, 242))
            screen.blit(text, text.get_rect(center=rect.center))
        text = value_font.render(f"Display rotation: {rotation} deg", True, (148, 164, 182))
        screen.blit(text, text.get_rect(center=(800, 680)))
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
