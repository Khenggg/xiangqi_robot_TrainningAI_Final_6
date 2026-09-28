"""Virtual FR3 link, mounting flange, and TCP frame contract.

The canonical tool length is measured from the mounting flange.  URDF forward
kinematics ends at the wrist3_link origin, which is a separate frame.
"""

import json
from pathlib import Path

import numpy as np

from src.domain.geometry import get_canonical_tool_geometry


ROOT = Path(__file__).resolve().parents[2]
VISUAL_ASSET_PATH = ROOT / "shared" / "gripper_visual_asset.json"


def virtual_link_to_tcp_offset_m() -> np.ndarray:
    """Return wrist3_link -> TCP in metres, including the link -> flange datum."""
    asset = json.loads(VISUAL_ASSET_PATH.read_text(encoding="utf-8-sig"))
    flange = np.asarray(asset["profiles"]["fr3"]["robot_flange_origin_m"], dtype=float)
    tool = np.asarray(get_canonical_tool_geometry().canonical_tcp_offset_m, dtype=float)
    if flange.shape != (3,) or not np.all(np.isfinite(flange)):
        raise ValueError("Invalid wrist3_link to mounting flange transform")
    if not np.allclose(flange[:2], 0.0, atol=1e-9) or flange[2] <= 0:
        raise ValueError("Unsupported wrist3_link to mounting flange transform")
    visual_length = float(asset["profiles"]["fr3"]["target_flange_to_tip_m"])
    if abs(visual_length - float(np.linalg.norm(tool))) > 0.0005:
        raise ValueError("Visual gripper tip differs from canonical flange-to-TCP by >0.5 mm")
    return flange + tool
