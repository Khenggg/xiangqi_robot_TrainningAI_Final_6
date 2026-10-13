"""Local simulation profiles. These records never authorize physical motion."""
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone


class SimulationBoardProfileStore:
    def __init__(self, path, scene_path):
        self.path = Path(path)
        self.scene_path = Path(scene_path)

    def _scene_digest(self):
        return hashlib.sha256(self.scene_path.read_bytes()).hexdigest()

    def save(self, teaching, safe_transit_height_mm):
        record = {
            "schema_version": 1, "source": "R1_R4_SIMULATION",
            "frame": "robot_base", "unit": "mm",
            "calibration_version": teaching["placement_version"],
            "provenance": "SIMULATOR_BOARD_SURFACE_POINT",
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "scene_sha256": self._scene_digest(),
            "safe_transit_height_mm": safe_transit_height_mm,
            "points": teaching["points"],
        }
        self._validate(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".board-profile-", suffix=".tmp", delete=False) as stream:
                temp_path = stream.name
                json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
        return record

    @staticmethod
    def _validate(record):
        if not isinstance(record, dict):
            raise ValueError("Profile phải là JSON object")
        expected = {"schema_version": 1, "source": "R1_R4_SIMULATION", "frame": "robot_base",
                    "unit": "mm", "provenance": "SIMULATOR_BOARD_SURFACE_POINT"}
        for key, value in expected.items():
            if type(record.get(key)) is not type(value) or record[key] != value:
                raise ValueError(f"Profile không hợp lệ: {key}")
        version = record.get("calibration_version")
        if type(version) is not int or version < 0:
            raise ValueError("Thiếu phiên bản calibration hợp lệ")
        points = record.get("points")
        if not isinstance(points, dict) or set(points) != {"R1", "R2", "R3", "R4"}:
            raise ValueError("Profile cần đúng bốn điểm R1–R4")
        for xyz in points.values():
            if (not isinstance(xyz, list) or len(xyz) != 3 or
                    any(type(v) not in (int, float) or not math.isfinite(v) for v in xyz)):
                raise ValueError("R1–R4 cần XYZ hữu hạn theo mm")
        height = record.get("safe_transit_height_mm")
        if type(height) not in (int, float) or not math.isfinite(height) or height <= 0:
            raise ValueError("Chiều cao di chuyển trong profile không hợp lệ")

    def load(self, safe_transit_height_mm):
        record = json.loads(self.path.read_text(encoding="utf-8"))
        self._validate(record)
        if record.get("scene_sha256") != self._scene_digest():
            raise ValueError("Cấu hình hình học đã đổi; cần nhập và kiểm định lại R1–R4")
        if record["safe_transit_height_mm"] != safe_transit_height_mm:
            raise ValueError("Chiều cao di chuyển đã đổi; cần kiểm định lại profile")
        return record
