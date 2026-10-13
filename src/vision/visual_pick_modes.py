"""Camera geometry adapters; no robot ownership or FEN commit authority."""
import time
import logging
from pathlib import Path
import numpy as np
from src.core.project_logging import event
from src.vision.pick_geometry import PickGeometry
from src.vision.height_pick_geometry import geometry_from_board, HeightPickEstimator, aggregate_height_targets
from src.vision.top_face_pick_estimator import TopFacePickEstimator
from src.vision.ring_pick_estimator import ring_pick_enabled, current_pick_enabled, resolve_ring_pick_targets
from src.vision.pick_consensus import select_consensus, FreshPickTransientError, require_pick_target

class VisualPickModes:
    def _top_face_enabled(self):
        return bool(getattr(getattr(self, "config", None), "VISUAL_TOP_FACE_ENABLED", False))

    def _occupancy_snapshot(self):
        if ring_pick_enabled(getattr(self, "config", None)):
            return self.cam_monitor.get_fresh_pick_snapshot()
        if (self._top_face_enabled() or getattr(self.config, "VISUAL_HEIGHT_PICK_ENABLED", False)
                or getattr(self.config, "VISUAL_PICK_OUTSIDE_MARGIN_MM", 0.0) > 0):
            return self.cam_monitor.get_fresh_pick_snapshot()
        return self.cam_monitor.get_fresh_snapshot()

    def _get_top_face_targets(self, expected_cells):
        targets = {name: None for name in expected_cells}
        self.last_pick_resolution = {"failure": "hard", "reason": "not measured", "attempts": 0, "elapsed_sec": 0.0}
        estimator = getattr(self, "top_face_pick_estimator", None)
        if estimator is None or not self.cam_monitor:
            self.last_pick_resolution["reason"] = "Missing commissioned geometry/camera"
            print("[TOP PICK] Missing commissioned geometry/camera; no fallback.")
            return targets
        samples = {name: [] for name in expected_cells}
        try:
            initial = getattr(self.config, "VISUAL_PICK_CONSENSUS_INITIAL_SAMPLES", 3)
            maximum = getattr(self.config, "VISUAL_PICK_CONSENSUS_MAX_SAMPLES", 6)
            minimum = getattr(self.config, "VISUAL_PICK_MIN_STABLE_SAMPLES", 2)
            budget = float(getattr(self.config, "VISUAL_PICK_CONSENSUS_TIMEOUT_SEC", 3.0))
            radius = float(getattr(self.config, "VISUAL_PICK_CONSENSUS_RADIUS_MM", 3.75))
            pitch = np.array([self.config.VISUAL_BOARD_WIDTH_MM / 8,
                              self.config.VISUAL_BOARD_HEIGHT_MM / 9], dtype=float)
            if (any(isinstance(v, bool) or int(v) != v for v in (initial, maximum, minimum))
                    or not 3 <= initial <= maximum <= 6 or not 2 <= minimum <= maximum
                    or not np.isfinite([budget, radius, *pitch]).all() or budget <= 0
                    or np.any(pitch <= 0) or not 0 < radius <= min(pitch) * .25):
                raise ValueError("Invalid consensus sampling configuration")
        except Exception as exc:
            self.last_pick_resolution["reason"] = str(exc)
            return targets
        started = time.monotonic()
        deadline = started + budget

        def expired():
            now = time.monotonic()
            self.last_pick_resolution["elapsed_sec"] = max(0.0, now - started)
            if now < deadline:
                return False
            self.last_pick_resolution.update(failure="deadline", reason="Pick sampling budget exhausted; late results rejected")
            print("[TOP PICK] Sampling deadline; no fallback.")
            return True

        for attempt in range(int(maximum)):
            if expired():
                return targets
            self.last_pick_resolution["attempts"] = attempt + 1
            try:
                frame, detections = self.cam_monitor.get_fresh_pick_snapshot()
                if expired():
                    return targets
                estimator.geometry.validate_context(
                    self.actual_camera_index, frame.shape[1::-1],
                    (self.config.VISUAL_BOARD_WIDTH_MM, self.config.VISUAL_BOARD_HEIGHT_MM),
                    self.config.VISUAL_PIECE_HEIGHT_MM, np.load(self.perspective_path),
                    self.config.VISUAL_GEOMETRY_CORNER_TOLERANCE_PX)
                for name, (col, row) in expected_cells.items():
                    samples[name].append(estimator.estimate_pick_target(frame, detections, col, row))
                    print(f"[TOP PICK] {name}: {estimator.last_reason}; profile={estimator.geometry.profile_id}")
                    self.cam_monitor.publish_pick_diagnostic(estimator.diagnostic)
                if expired():
                    return targets
            except FreshPickTransientError as exc:
                for values in samples.values():
                    values.append(None)
                print(f"[TOP PICK] Transient attempt {attempt + 1}: {exc}")
            except Exception as exc:
                self.last_pick_resolution.update(failure="hard", reason=str(exc))
                print(f"[TOP PICK] Snapshot rejected: {exc}")
                return targets
            if expired():
                return targets
            if attempt + 1 < initial:
                continue
            try:
                results = {name: select_consensus(values, pitch, minimum, radius)
                           for name, values in samples.items()}
                if expired():
                    return targets
                for name, result in results.items():
                    print(f"[TOP PICK] attempt={attempt + 1}/{maximum} {name}: {result.reason}; support={result.support}")
                    if result.target is not None:
                        col, row = expected_cells[name]
                        offset = np.hypot(result.target.col - col, result.target.row - row)
                        if offset > getattr(self.config, "VISUAL_PICK_MAX_OFFSET_CELLS", .25):
                            raise ValueError("Consensus center outside expected-cell correction limit")
                if all(result.target is not None for result in results.values()):
                    for name, result in results.items():
                        print(f"[TOP PICK] selected {name} grid=({result.target.col:.4f},{result.target.row:.4f}) "
                              f"support={result.support} valid={result.valid_count}")
                    if expired():
                        return targets
                    self.last_pick_resolution.update(failure="", reason="; ".join(r.reason for r in results.values()))
                    print(f"[TOP PICK] sampling={self.last_pick_resolution['elapsed_sec']:.3f}s")
                    if expired():
                        return targets
                    return {name: result.target for name, result in results.items()}
                self.last_pick_resolution.update(failure="consensus", reason="; ".join(
                    f"{name}: {result.reason}" for name, result in results.items()))
            except Exception as exc:
                self.last_pick_resolution.update(failure="hard", reason=str(exc))
                return targets
        return targets

    def _get_height_pick_targets(self, expected_cells):
        """Raw measured bbox -> height plane, without rim/profile commissioning gates.

        Invalid geometry or unstable observation blocks the pick. It never mixes
        foot points or logical-cell substitutes with the top-plane calibration.
        """
        targets = {name: None for name in expected_cells}
        self.last_height_pick_resolution = {"mode": "blocked", "reason": ""}
        self.last_pick_resolution = {"failure": "hard", "reason": ""}
        if not self.cam_monitor:
            self.last_height_pick_resolution["reason"] = "Camera unavailable"
            self.last_pick_resolution["reason"] = "Camera unavailable"
            return targets
        samples = {name: [] for name in expected_cells}
        diagnostics = {}
        self.cam_monitor.pick_debug_frame = None
        estimator = None
        try:
            # Reload each pick cycle: moving camera/recalibrating board must not reuse old pose.
            matrix = np.load(self.perspective_path)
            window = float(getattr(self.config, "VISUAL_HEIGHT_SAMPLE_WINDOW_SEC", 3.6))
            if not np.isfinite(window) or window <= 0:
                raise ValueError("Invalid height scan limits")
            started = time.monotonic()
            deadline = started + window
            attempts = 0
            from contextlib import ExitStack
            with ExitStack() as scan_session:
                session_factory = getattr(self.cam_monitor, "pick_scan_session", None)
                if callable(session_factory):
                    scan_session.enter_context(session_factory())
                while time.monotonic() < deadline:
                    attempts += 1
                    try:
                        frame, detections = self.cam_monitor.get_fresh_pick_snapshot()
                    except FreshPickTransientError as exc:
                        print(f"[HEIGHT PICK] Retrying snapshot: {exc}")
                        continue
                    # A late blocking call cannot contribute an out-of-window sample.
                    if time.monotonic() > deadline:
                        break
                    if frame is None:
                        continue
                    if estimator is None:
                        geometry = geometry_from_board(
                            Path(self.project_dir) / self.config.VISUAL_CAMERA_INTRINSICS_PATH,
                            matrix, self.actual_camera_index, frame.shape[1::-1],
                            self.config.VISUAL_HEIGHT_BOARD_MM, self.config.VISUAL_HEIGHT_PIECE_MM,
                            self.config.VISUAL_HEIGHT_POSE_MAX_ERROR_PX)
                        estimator = HeightPickEstimator(geometry, self.config.VISUAL_PICK_MIN_CONFIDENCE,
                                                        self.config.VISUAL_PICK_MAX_OFFSET_CELLS,
                                                        outside_margin_mm=getattr(
                                                            self.config, "VISUAL_PICK_OUTSIDE_MARGIN_MM", None))
                    elif tuple(frame.shape[1::-1]) != estimator.geometry.frame_size:
                        raise ValueError("Camera resolution changed during pick sampling")
                    for name, cell in expected_cells.items():
                        observation = estimator.estimate_pick_target(detections, *cell)
                        samples[name].append(observation)
                        if observation is not None and estimator.last_box is not None:
                            diagnostics[name] = (frame.copy(), estimator.last_box, observation)
            methods = {}
            for name, values in samples.items():
                targets[name], methods[name] = aggregate_height_targets(
                    values, expected_cells[name],
                    getattr(self.config, "VISUAL_HEIGHT_MIN_SAMPLES", 2),
                    getattr(self.config, "VISUAL_HEIGHT_MAX_SPREAD_CELLS", .12))
            if estimator is not None:
                from src.vision.pick_debug import draw_pick_debug
                for name, (frame, box, observation) in diagnostics.items():
                    self.cam_monitor.pick_debug_frame = draw_pick_debug(
                        frame, box, expected_cells[name], observation, targets[name], estimator.geometry)
            elapsed = time.monotonic()-started
            self.last_height_pick_resolution = {
                "mode": "height" if all(t is not None for t in targets.values()) else "blocked",
                "reason": "; ".join(f"{name}: {methods[name]}" for name in targets if targets[name] is None),
                "attempts": attempts, "elapsed_sec": elapsed,
                "valid_samples": {name: sum(t is not None for t in values) for name, values in samples.items()},
                "methods": methods,
            }
            self.last_pick_resolution = {
                "failure": "" if all(t is not None for t in targets.values()) else "consensus",
                "reason": self.last_height_pick_resolution["reason"],
            }
            print(f"[HEIGHT PICK] {self.last_height_pick_resolution}; targets={targets}")
        except Exception as exc:
            targets = {name: None for name in expected_cells}
            self.last_height_pick_resolution["reason"] = str(exc)
            self.last_pick_resolution = {"failure": "hard", "reason": str(exc)}
            print(f"[HEIGHT PICK] BLOCKED: {exc}; no foot/logical fallback.")
        return targets
