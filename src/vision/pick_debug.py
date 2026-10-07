"""Draw diagnostic markers on the exact measured frame, never on a live substitute."""
import cv2
import numpy as np


def draw_pick_debug(frame, box, cell, observation, consensus, geometry):
    image = frame.copy()
    x1, y1, x2, y2 = box
    cv2.rectangle(image, (round(x1), round(y1)), (round(x2), round(y2)), (0, 255, 0), 1)
    bbox_center = ((x1+x2)/2, (y1+y2)/2)
    logical = geometry.project(geometry.grid_to_xy([cell]), top=False)[0]
    # Project top-plane XY onto the BOARD plane to make parallax correction visible.
    corrected = geometry.project(geometry.grid_to_xy([[observation.col, observation.row]]), top=False)[0]
    for point, color in ((bbox_center, (0, 255, 0)), (logical, (255, 255, 0)),
                         (corrected, (255, 0, 255))):
        cv2.drawMarker(image, tuple(np.rint(point).astype(int)), color, cv2.MARKER_CROSS, 15, 2)
    if consensus is not None:
        point = geometry.project(geometry.grid_to_xy([[consensus.col, consensus.row]]), top=False)[0]
        cv2.circle(image, tuple(np.rint(point).astype(int)), 9, (0, 165, 255), 2)
    lines = ["FROZEN measured frame | D: return LIVE in test",
             "Green: bbox center | Cyan: logical BOARD point",
             "Magenta: height XY on BOARD | Orange: consensus on BOARD",
             "Board projections are not gripper pixels",
             f"Sample grid=({observation.col:.4f},{observation.row:.4f})"]
    lines.append("CONSENSUS BLOCKED" if consensus is None else
                 f"Command grid=({consensus.col:.4f},{consensus.row:.4f}) conf={consensus.confidence:.3f}")
    panel = np.zeros((len(lines)*22+8, image.shape[1], 3), dtype=np.uint8)
    for i, line in enumerate(lines):
        cv2.putText(panel, line, (7, 20+i*22), cv2.FONT_HERSHEY_SIMPLEX, .43, (255, 255, 255), 1)
    return np.vstack((image, panel))
