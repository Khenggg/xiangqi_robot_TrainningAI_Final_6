"""Opt-in colored-ring picking; existing bbox and commissioned top-face paths stay intact."""
from contextlib import ExitStack
from pathlib import Path
import time

import cv2
import numpy as np

from src.vision.height_pick_geometry import geometry_from_board
from src.vision.pick_consensus import FreshPickTransientError, select_consensus
from src.vision.top_face_pick_estimator import TopFacePickEstimator


def ring_pick_enabled(config):
    return bool(getattr(config, "VISUAL_RING_PICK_ENABLED", False))


def current_pick_enabled(config):
    # Configs predating the two switches retain exactly their previous routing.
    return bool(getattr(config, "VISUAL_CURRENT_PICK_ENABLED", True))


def exclusive_pick_required(config):
    return ring_pick_enabled(config) or not current_pick_enabled(config)


class ColoredRingPickEstimator(TopFacePickEstimator):
    """Raw ROI edges -> undistorted rays -> top-plane points -> metric circle.

    Reuse the existing geometric fit, coverage, enclosing-body and ambiguity
    gates. Require actual red/purple/blue ink around the fitted circumference,
    with white surface on both sides. Character strokes and a white silhouette
    alone cannot provide that evidence. No ellipse or bbox center is mapped.
    """

    def _white_annuli(self, hsv, center, radius, left, top):
        angles = np.linspace(0, 2*np.pi, 180, endpoint=False)
        directions = np.column_stack((np.cos(angles), np.sin(angles)))
        for sample_radius, require_white in (
                (radius, False),
                (radius-self.annulus_offset_mm, True),
                (radius+self.annulus_offset_mm, True)):
            pixels = self.geometry.project(center + sample_radius*directions) - [left, top]
            if (not np.isfinite(pixels).all() or np.any(pixels < 0)
                    or np.any(pixels[:, 0] >= hsv.shape[1]-1)
                    or np.any(pixels[:, 1] >= hsv.shape[0]-1)):
                return False
            samples = cv2.remap(hsv, pixels[:, 0].astype(np.float32).reshape(1, -1),
                                pixels[:, 1].astype(np.float32).reshape(1, -1),
                                cv2.INTER_LINEAR)[0]
            hue, saturation, value = samples.T
            if require_white:
                supported = ((saturation <= self.max_white_saturation)
                             & (value >= self.min_white_value))
            else:
                # OpenCV hue is 0..179; include red's wrap-around and purple.
                supported = (((hue <= 10) | (hue >= 135)
                              | ((hue >= 80) & (hue <= 134)))
                             & (saturation >= 45) & (value >= 50))
            if np.mean(supported) < self.min_white_annulus_fraction:
                return False
        return True

    def _label(self, frame):
        cv2.putText(frame, f"COLORED RING PICK h={self.geometry.piece_height:g}mm",
                    (12, 25), 0, .6, (255, 255, 0), 2)
        cv2.putText(frame, self.last_reason, (12, 50), 0, .6, (0, 255, 255), 2)


def resolve_ring_pick_targets(hardware, expected_cells):
    """Bounded fresh sampling with current intrinsics/board pose, never fallback.

    Height and dimensions use the active VISUAL_HEIGHT_* settings. They are
    deliberately not replaced with the defaults of the older commissioned
    top-face profile. Intrinsics and perspective are reloaded each pick cycle.
    """
    targets = {name: None for name in expected_cells}
    resolution = dict(failure="hard", reason="Ring pick not measured", mode="ring",
                      attempts=0, elapsed_sec=0.0)
    hardware.last_pick_resolution = resolution
    if not hardware.cam_monitor or not expected_cells:
        resolution["reason"] = "Camera or expected pick cells unavailable"
        return targets
    config = hardware.config
    started = time.monotonic()
    try:
        minimum = getattr(config, "VISUAL_HEIGHT_MIN_SAMPLES", 2)
        initial = getattr(config, "VISUAL_PICK_CONSENSUS_INITIAL_SAMPLES", 3)
        maximum = getattr(config, "VISUAL_PICK_CONSENSUS_MAX_SAMPLES", 6)
        budget = float(getattr(config, "VISUAL_HEIGHT_SAMPLE_WINDOW_SEC", 3.6))
        radius = float(getattr(config, "VISUAL_PICK_CONSENSUS_RADIUS_MM", 3.75))
        if (any(isinstance(n, bool) or int(n) != n for n in (minimum, initial, maximum))
                or not 2 <= minimum <= initial <= maximum <= 6
                or not np.isfinite([budget, radius]).all() or budget <= 0 or radius <= 0):
            raise ValueError("Invalid ring sampling limits")
        deadline = started + budget
        matrix = np.load(hardware.perspective_path)
        samples = {name: [] for name in expected_cells}
        estimator = None

        def expired():
            resolution["elapsed_sec"] = max(0.0, time.monotonic()-started)
            if time.monotonic() < deadline:
                return False
            resolution.update(failure="deadline", reason="Ring sampling deadline; late results rejected")
            return True

        with ExitStack() as scan:
            factory = getattr(hardware.cam_monitor, "pick_scan_session", None)
            if callable(factory):
                scan.enter_context(factory())
            for attempt in range(int(maximum)):
                if expired():
                    return targets
                resolution["attempts"] = attempt+1
                try:
                    frame, detections = hardware.cam_monitor.get_fresh_pick_snapshot()
                except FreshPickTransientError as exc:
                    for values in samples.values():
                        values.append(None)
                    resolution.update(failure="consensus", reason=str(exc))
                    continue
                if expired():
                    return targets
                if frame is None:
                    for values in samples.values():
                        values.append(None)
                    resolution.update(failure="consensus", reason="No fresh ring frame")
                    continue
                if estimator is None:
                    geometry = geometry_from_board(
                        Path(hardware.project_dir) / config.VISUAL_CAMERA_INTRINSICS_PATH,
                        matrix, hardware.actual_camera_index, frame.shape[1::-1],
                        config.VISUAL_HEIGHT_BOARD_MM, config.VISUAL_HEIGHT_PIECE_MM,
                        config.VISUAL_HEIGHT_POSE_MAX_ERROR_PX)
                    if radius > min(geometry.width/8, geometry.height/9)*.25:
                        raise ValueError("Ring consensus radius exceeds quarter-cell pitch")
                    estimator = ColoredRingPickEstimator(
                        geometry, config.VISUAL_PICK_MIN_CONFIDENCE,
                        config.VISUAL_PICK_MAX_OFFSET_CELLS,
                        **{name: getattr(config, setting, default) for name, setting, default in (
                            ("max_residual", "VISUAL_TOP_MAX_RESIDUAL", .045),
                            ("min_coverage", "VISUAL_TOP_MIN_COVERAGE", .83),
                            ("min_box_fraction", "VISUAL_TOP_MIN_BOX_FRACTION", .55),
                            ("radius_mm", "VISUAL_TOP_RADIUS_MM", (5., 15.)),
                            ("ambiguity_mm", "VISUAL_TOP_AMBIGUITY_MM", 1.5),
                            ("max_enclosing_area_ratio", "VISUAL_TOP_MAX_ENCLOSING_AREA_RATIO", .80),
                            ("annulus_offset_mm", "VISUAL_TOP_ANNULUS_OFFSET_MM", 1.2),
                            ("min_white_annulus_fraction", "VISUAL_TOP_MIN_WHITE_ANNULUS_FRACTION", .75),
                            ("max_white_saturation", "VISUAL_TOP_MAX_WHITE_SATURATION", 80),
                            ("min_white_value", "VISUAL_TOP_MIN_WHITE_VALUE", 130))})
                if tuple(frame.shape[1::-1]) != estimator.geometry.frame_size:
                    raise ValueError("Camera resolution changed during ring sampling")
                reasons = []
                for name, cell in expected_cells.items():
                    samples[name].append(estimator.estimate_pick_target(frame, detections, *cell))
                    reasons.append(f"{name}: {estimator.last_reason}")
                    hardware.cam_monitor.publish_pick_diagnostic(estimator.diagnostic)
                if expired():
                    return targets
                if attempt+1 < initial:
                    continue
                results = {name: select_consensus(values,
                    (estimator.geometry.width/8, estimator.geometry.height/9), minimum, radius)
                    for name, values in samples.items()}
                resolution.update(failure="consensus", reason="; ".join(
                    f"{name}: {result.reason}" for name, result in results.items())
                    + "; " + "; ".join(reasons))
                if expired():
                    return targets
                if all(result.target is not None for result in results.values()):
                    selected = {name: result.target for name, result in results.items()}
                    if any(np.hypot(t.col-expected_cells[name][0], t.row-expected_cells[name][1])
                           > config.VISUAL_PICK_MAX_OFFSET_CELLS for name, t in selected.items()):
                        raise ValueError("Ring consensus exceeds expected-cell correction limit")
                    if expired():
                        return targets
                    resolution.update(failure="", reason="; ".join(reasons))
                    return selected
        if expired():
            return targets
        resolution.update(failure="consensus", reason=resolution["reason"] or "No supported ring consensus")
    except Exception as exc:
        resolution.update(failure="hard", reason=str(exc))
    finally:
        resolution["elapsed_sec"] = max(0.0, time.monotonic()-started)
        print(f"[RING PICK] {resolution}")
    return targets
