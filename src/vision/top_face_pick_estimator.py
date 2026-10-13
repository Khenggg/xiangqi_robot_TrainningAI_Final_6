"""best.pt locates an ROI; physical top-rim points determine the pick center."""
import math
import cv2
import numpy as np

from src.vision.visual_pick_estimator import GridTarget, VisualPickEstimator


def fit_metric_circle(points):
    points = np.asarray(points, dtype=float).reshape(-1, 2)
    if len(points) < 24 or not np.isfinite(points).all():
        raise ValueError("Insufficient finite rim support")
    origin = points.mean(axis=0)
    local = points - origin
    design = np.column_stack((2 * local, np.ones(len(local))))
    solution, _, rank, _ = np.linalg.lstsq(design, (local ** 2).sum(axis=1), rcond=None)
    if rank != 3:
        raise ValueError("Degenerate circle")
    center = solution[:2] + origin
    radii = np.linalg.norm(points - center, axis=1)
    radius = float(np.mean(radii))
    if radius <= 0:
        raise ValueError("Zero radius")
    residual = float(np.sqrt(np.mean((radii - radius) ** 2)) / radius)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    coverage = len(np.unique(np.floor((angles + np.pi) / (2 * np.pi) * 12).astype(int) % 12)) / 12
    return center, radius, residual, coverage


class TopFacePickEstimator:
    # Compatibility helper only; production temporal selection is metric
    # pick_consensus.select_consensus in HardwareManager, not this legacy gate.
    aggregate_targets = staticmethod(VisualPickEstimator.aggregate_targets)

    def __init__(self, geometry, min_confidence=.45, max_offset_cells=.25,
                 max_residual=.045, min_coverage=.83, min_box_fraction=.55,
                 radius_mm=(5.0, 15.0), ambiguity_mm=1.5,
                 max_enclosing_area_ratio=.80, annulus_offset_mm=1.2,
                 min_white_annulus_fraction=.75, max_white_saturation=80,
                 min_white_value=130):
        self.geometry = geometry
        self.min_confidence = min_confidence
        self.max_offset_cells = max_offset_cells
        self.max_residual = max_residual
        self.min_coverage = min_coverage
        self.min_box_fraction = min_box_fraction
        self.radius_mm = radius_mm
        self.ambiguity_mm = ambiguity_mm
        self.max_enclosing_area_ratio = max_enclosing_area_ratio
        self.annulus_offset_mm = annulus_offset_mm
        self.min_white_annulus_fraction = min_white_annulus_fraction
        self.max_white_saturation = max_white_saturation
        self.min_white_value = min_white_value
        thresholds = [min_confidence, max_offset_cells, max_residual, min_coverage,
                      min_box_fraction, *radius_mm, ambiguity_mm,
                      max_enclosing_area_ratio, annulus_offset_mm,
                      min_white_annulus_fraction, max_white_saturation,
                      min_white_value]
        if (not np.isfinite(thresholds).all() or not 0 <= min_confidence <= 1
                or not 0 < max_offset_cells <= .5 or not 0 < max_residual < .15
                or not .75 <= min_coverage <= 1 or not 0 < min_box_fraction <= 1
                or not 0 < radius_mm[0] < radius_mm[1] or ambiguity_mm <= 0
                or not 0 < max_enclosing_area_ratio <= .80
                or not 0 < annulus_offset_mm < radius_mm[0]
                or not .75 <= min_white_annulus_fraction <= 1
                or not 0 <= max_white_saturation <= 80
                or not 130 <= min_white_value <= 255):
            raise ValueError("Invalid top-rim quality thresholds")
        self.last_reason = "not sampled"
        self.diagnostic = None

    def estimate_pick_target(self, frame, detections, expected_col, expected_row):
        diagnostic = frame.copy()
        self.diagnostic = diagnostic
        self.last_reason = "no supported top rim near expected cell"
        if tuple(frame.shape[1::-1]) != self.geometry.frame_size:
            self.last_reason = "frame size differs from calibrated profile"
            return None
        candidates = []
        for _, confidence, box in detections or []:
            try:
                x1, y1, x2, y2 = map(float, box)
                if (not np.isfinite([confidence, x1, y1, x2, y2]).all()
                        or confidence < self.min_confidence or min(x2-x1, y2-y1) < 12):
                    continue
                padding = max(x2-x1, y2-y1) * .1 + 2
                left, top = int(math.floor(x1-padding)), int(math.floor(y1-padding))
                right, bottom = int(math.ceil(x2+padding)), int(math.ceil(y2+padding))
                if left < 0 or top < 0 or right >= frame.shape[1] or bottom >= frame.shape[0]:
                    self.last_reason = "ROI clipped by camera frame"
                    continue
                cv2.rectangle(diagnostic, (int(x1), int(y1)), (int(x2), int(y2)), (0, 200, 0), 1)
                gray = cv2.cvtColor(frame[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
                hsv = cv2.cvtColor(frame[top:bottom, left:right], cv2.COLOR_BGR2HSV)
                edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 40, 120)
                contours = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)[0]
                fitted_rims = []
                for contour in contours:
                    if len(contour) < 24:
                        continue
                    pixels = contour.reshape(-1, 2).astype(float) + [left, top]
                    # Do not close an incomplete arc or a contour cut by the ROI.
                    if (np.linalg.norm(pixels[0]-pixels[-1]) > 3
                            or np.any(pixels[:, 0] <= left+1) or np.any(pixels[:, 0] >= right-2)
                            or np.any(pixels[:, 1] <= top+1) or np.any(pixels[:, 1] >= bottom-2)):
                        continue
                    try:
                        xy = self.geometry.pixels_to_top_xy(pixels)
                        center, radius, residual, coverage = fit_metric_circle(xy)
                    except (ValueError, np.linalg.LinAlgError):
                        continue
                    if (residual > self.max_residual or coverage < self.min_coverage
                            or not self.radius_mm[0] <= radius <= self.radius_mm[1]):
                        continue
                    # A cylinder silhouette mixes heights and can still fit a
                    # circle. Require an internal rim, not its duplicate Canny
                    # traces, with a white top-face annulus on both sides.
                    if not self._has_enclosing_body(contour, contours):
                        continue
                    grid = self.geometry.xy_to_grid(center)
                    offset = math.hypot(grid[0]-expected_col, grid[1]-expected_row)
                    fitted_rims.append((residual, center, radius, pixels, grid, offset))
                rims = []
                for rim in fitted_rims:
                    _, center, radius, pixels, _, _ = rim
                    if np.ptp(pixels[:, 0]) < (x2-x1)*self.min_box_fraction:
                        continue
                    # Canny sees both sides of the printed ink stroke. Keep
                    # each contour's geometric fit, but evaluate white surface
                    # support around the stroke centerline between its edges.
                    support_radii = [radius]
                    support_radii.extend((radius+other[2])/2 for other in fitted_rims
                        if np.linalg.norm(center-other[1]) <= min(self.ambiguity_mm, .6)
                        and .5 <= abs(radius-other[2]) <= 2*self.annulus_offset_mm)
                    if any(self._white_annuli(hsv, center, support_radius, left, top)
                           for support_radius in support_radii):
                        rims.append(rim)
                if not rims:
                    continue
                if any(np.linalg.norm(a[1]-b[1]) > self.ambiguity_mm for a in rims for b in rims):
                    self.last_reason = "ambiguous rim centers (top/body/shadow)"
                    # A plausible competing center must invalidate the whole observation.
                    self._label(diagnostic)
                    return None
                # Do not hide a competing supported rim just because it falls
                # outside the expected-cell gate.
                rims = [rim for rim in rims if rim[5] <= self.max_offset_cells
                        and -self.max_offset_cells <= rim[4][0] <= 8+self.max_offset_cells
                        and -self.max_offset_cells <= rim[4][1] <= 9+self.max_offset_cells]
                if not rims:
                    continue
                rim = min(rims, key=lambda item: item[0])
                residual, center, radius, pixels, grid, offset = rim
                candidates.append((offset, confidence, grid, pixels, center, radius, residual))
            except (ValueError, TypeError, cv2.error, np.linalg.LinAlgError):
                self.last_reason = "invalid ROI or ray/circle geometry"
        if candidates:
            if len(candidates) > 1:
                self.last_reason = "multiple detected pieces near selected cell"
            else:
                offset, confidence, grid, pixels, center, radius, residual = candidates[0]
                cv2.polylines(diagnostic, [pixels.astype(np.int32)], True, (255, 255, 0), 1)
                pixel_center = self.geometry.project([center])[0]
                cv2.drawMarker(diagnostic, tuple(np.rint(pixel_center).astype(int)), (0, 255, 255), 0, 18, 2)
                self.last_reason = f"TOP grid={grid[0]:.3f},{grid[1]:.3f} radius={radius:.1f}mm residual={residual:.3f}"
                self._label(diagnostic)
                return GridTarget(float(grid[0]), float(grid[1]), float(confidence), float(offset))
        self._label(diagnostic)
        return None

    def _has_enclosing_body(self, contour, contours):
        area = abs(cv2.contourArea(contour))
        if area <= 0:
            return False
        points = contour.reshape(-1, 2)
        for enclosing in contours:
            enclosing_area = abs(cv2.contourArea(enclosing))
            if enclosing_area <= 0 or area > self.max_enclosing_area_ratio * enclosing_area:
                continue
            if all(cv2.pointPolygonTest(enclosing, (float(x), float(y)), False) >= 0
                   for x, y in points):
                return True
        return False

    def _white_annuli(self, hsv, center, radius, left, top):
        angles = np.linspace(0, 2*np.pi, 180, endpoint=False)
        directions = np.column_stack((np.cos(angles), np.sin(angles)))
        for sample_radius, require_white in ((radius, False),
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
            white = ((samples[:, 1] <= self.max_white_saturation)
                     & (samples[:, 2] >= self.min_white_value))
            # The midpoint must really cross printed ink, not an arbitrary
            # white circle between a body boundary and another fitted contour.
            supported = white if require_white else ~white
            if np.mean(supported) < self.min_white_annulus_fraction:
                return False
        return True

    def _label(self, frame):
        cv2.putText(frame, "LAST PICK SNAPSHOT " + self.geometry.profile_id, (12, 25), 0, .6, (255, 255, 0), 2)
        cv2.putText(frame, self.last_reason, (12, 50), 0, .6, (0, 255, 255), 2)
