"""Independent camera/grid error measurements; no AI or robot imports."""
import csv
import math
from pathlib import Path
import cv2
import numpy as np

REFERENCE_CELLS = ((0, 0), (4, 0), (8, 0), (0, 4), (4, 4),
                   (8, 4), (0, 9), (4, 9), (8, 9))


def camera_grid_error(matrix, pixel, expected):
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise ValueError('Invalid camera-to-grid matrix')
    point = np.array([float(pixel[0]), float(pixel[1]), 1.0])
    projected = matrix @ point
    if not np.isfinite(projected).all() or abs(projected[2]) < 1e-12:
        raise ValueError('Pixel projects to an invalid grid point')
    col, row = projected[:2] / projected[2]
    dc, dr = col - expected[0], row - expected[1]
    return dict(expected_col=expected[0], expected_row=expected[1],
                pixel_x=float(pixel[0]), pixel_y=float(pixel[1]),
                measured_col=float(col), measured_row=float(row),
                delta_col=float(dc), delta_row=float(dr), error_cells=math.hypot(dc, dr))


def robot_xy_error(cell, commanded, aligned, measurement_z, z_tolerance=1.0):
    """Aligned pose must be read in the SAME tool/user frame as the command."""
    commanded = [float(value) for value in commanded]
    aligned = [float(value) for value in aligned]
    if len(commanded) < 3 or len(aligned) != 3 or not all(map(math.isfinite, commanded + aligned)):
        raise ValueError('Enter finite X Y Z in millimetres')
    if abs(aligned[2] - measurement_z) > z_tolerance:
        raise ValueError(f'Measure at Z={measurement_z:.2f}mm (+/-{z_tolerance}mm); do not mix heights')
    dx, dy = aligned[0] - commanded[0], aligned[1] - commanded[1]
    return dict(col=cell[0], row=cell[1], commanded_x=commanded[0], commanded_y=commanded[1],
                aligned_x=aligned[0], aligned_y=aligned[1], measurement_z=aligned[2],
                delta_x_mm=dx, delta_y_mm=dy, error_mm=math.hypot(dx, dy))


def save_csv(path, rows, fieldnames=None):
    if not rows and fieldnames is None:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def draw_grid(frame, matrix):
    result = frame.copy()
    inverse = np.linalg.inv(matrix)
    lines = [((0, r), (8, r)) for r in range(10)]
    lines += [((c, 0), (c, 9)) for c in range(9)]
    for start, end in lines:
        points = cv2.perspectiveTransform(np.array([[start, end]], np.float32), inverse)[0]
        cv2.line(result, tuple(np.rint(points[0]).astype(int)),
                 tuple(np.rint(points[1]).astype(int)), (0, 215, 255), 1)
    return result
