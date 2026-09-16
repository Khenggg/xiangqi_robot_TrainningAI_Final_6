"""
Clean simulation path resolver for FAIRINO FR3 URDF in PyBullet.

Resolves ROS `package://` mesh paths to local filesystem absolute paths
without destructively modifying the authoritative source URDF.
"""

from pathlib import Path
from typing import Optional


def get_simulation_ready_fr3_urdf(
    source_urdf_path: Optional[Path] = None,
    output_urdf_path: Optional[Path] = None,
) -> Path:
    """
    Generate or return a simulation-ready FR3 URDF with resolved mesh paths for PyBullet.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    src_path = source_urdf_path or (repo_root / "robot-3d-viewer" / "assets" / "fr3_v6" / "fairino3_v6.urdf")
    out_path = output_urdf_path or (repo_root / "robot-3d-viewer" / "assets" / "fr3_v6" / "fairino3_v6_pybullet.urdf")

    if not src_path.is_file():
        raise FileNotFoundError(f"Source FR3 URDF not found: {src_path}")

    mesh_dir = (repo_root / "robot-3d-viewer" / "assets" / "fr3_v6").resolve().as_posix()
    content = src_path.read_text(encoding="utf-8")

    # Replace package:// path with resolved absolute posix path
    resolved_content = content.replace(
        "package://fairino_description/meshes/fairino3_v6/",
        f"{mesh_dir}/",
    )

    out_path.write_text(resolved_content, encoding="utf-8")
    return out_path
