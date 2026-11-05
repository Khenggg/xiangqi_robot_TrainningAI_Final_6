"""
Clean simulation path resolver for FAIRINO FR3 URDF in PyBullet.

Resolves ROS `package://` mesh paths to local filesystem absolute paths
without destructively modifying the authoritative source URDF.
"""

from pathlib import Path
from typing import Optional
import ctypes
import os
import shutil
import tempfile
import threading

_NATIVE_ASSET_CACHES = {}
_NATIVE_ASSET_LOCK = threading.RLock()


def _short_ascii_path(path):
    if os.name != "nt":
        return None
    function = ctypes.windll.kernel32.GetShortPathNameW
    function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    function.restype = ctypes.c_uint
    buffer = ctypes.create_unicode_buffer(32768)
    if function(str(path), buffer, len(buffer)) and buffer.value.isascii():
        return Path(buffer.value)
    return None


def _native_mesh_directory(directory):
    """Windows Bullet uses narrow file APIs; give it ASCII data-only assets.

    No cwd changes, drive mapping, model/calibration mutation or hardware calls.
    The temporary directory belongs to this process and is removed at exit.
    """
    directory = Path(directory).resolve()
    if os.name != "nt" or str(directory).isascii():
        return directory
    short = _short_ascii_path(directory)
    if short is not None:
        return short
    key = str(directory)
    if key in _NATIVE_ASSET_CACHES:
        return Path(_NATIVE_ASSET_CACHES[key].name)
    public = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Documents"
    candidates = [Path(tempfile.gettempdir()), *directory.parents, public]
    temporary = None
    for candidate in candidates:
        candidate = _short_ascii_path(candidate) or candidate
        if not str(candidate).isascii() or not candidate.is_dir():
            continue
        try:
            temporary = tempfile.TemporaryDirectory(prefix="xiangqi-mesh-", dir=candidate)
            break
        except OSError:
            continue
    if temporary is None:
        raise RuntimeError("PyBullet needs a writable ASCII temporary asset directory on this Windows PC")
    target = Path(temporary.name)
    assert target.parent.resolve() == candidate.resolve()
    try:
        # Mesh/texture data only; no executable, runtime DLL, journal or profile.
        for source in directory.rglob("*"):
            if source.is_file() and source.suffix.lower() in {".stl", ".obj", ".dae", ".mtl", ".png", ".jpg", ".jpeg"}:
                relative = source.relative_to(directory)
                if not str(relative).isascii():
                    raise RuntimeError("Native FR3 asset filenames must be ASCII")
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        _NATIVE_ASSET_CACHES[key] = temporary
        return target
    except Exception:
        temporary.cleanup()
        raise


def native_mesh_directory(directory):
    with _NATIVE_ASSET_LOCK:
        return _native_mesh_directory(directory)


def get_simulation_ready_fr3_urdf(
    source_urdf_path: Optional[Path] = None,
    output_urdf_path: Optional[Path] = None,
) -> Path:
    """
    Generate or return a simulation-ready FR3 URDF with resolved mesh paths for PyBullet.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    src_path = source_urdf_path or (repo_root / "robot-3d-viewer" / "assets" / "fr3_v6" / "fairino3_v6.urdf")
    asset_dir = repo_root / "robot-3d-viewer" / "assets" / "fr3_v6"
    native_dir = native_mesh_directory(asset_dir)
    out_path = output_urdf_path or (native_dir / "fairino3_v6_pybullet.urdf")

    if not src_path.is_file():
        raise FileNotFoundError(f"Source FR3 URDF not found: {src_path}")

    # Preserve an ASCII short-path alias rather than resolve it back to Unicode.
    mesh_dir = native_dir.as_posix()

    content = src_path.read_text(encoding="utf-8")

    # Replace package:// path with resolved absolute posix path
    resolved_content = content.replace(
        "package://fairino_description/meshes/fairino3_v6/",
        f"{mesh_dir}/",
    )

    # A copied/relocated capsule can preserve mtimes while its cached absolute
    # mesh paths still point to the old PC/folder. Compare resolved content.
    if out_path.is_file() and out_path.read_text(encoding="utf-8") == resolved_content:
        return out_path

    # Write atomically via temp file to avoid concurrent read/write locks
    temp_out = out_path.with_suffix(".tmp")
    temp_out.write_text(resolved_content, encoding="utf-8")
    try:
        temp_out.replace(out_path)
    except OSError:
        pass
    return out_path
