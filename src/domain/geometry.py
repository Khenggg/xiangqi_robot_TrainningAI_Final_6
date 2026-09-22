"""
Domain module for Xiangqi physical geometry and coordinate conversion.

Single source of truth loaded from `shared/physical_geometry.json`.
Does NOT import `config.py` to prevent circular dependencies.
"""

from dataclasses import dataclass
from enum import Enum
import json
import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class ProvenanceStatus(str, Enum):
    """
    Source provenance status for physical and geometric constants.
    Guarantees no unverified or provisional values are silently treated as ground truth.
    """
    MEASURED = "MEASURED"                          # Ground truth directly measured with certified physical tool
    MEASURED_APPROXIMATE = "MEASURED_APPROXIMATE"  # Hand-measured on physical hardware (e.g. caliper / tape ~150mm)
    CAD_DERIVED = "CAD_DERIVED"                    # Extracted directly from CAD STEP / URDF model
    PROVISIONAL_SIMULATION = "PROVISIONAL_SIMULATION"  # Simulation-only tuning candidate pending physical validation
    LEGACY_UNVERIFIED = "LEGACY_UNVERIFIED"        # Historical / obsolete value (e.g. 218mm with unverified adapter)


@dataclass(frozen=True)
class ProvenanceRecord:
    """Rigorous audit record for a physical or kinematic parameter."""
    parameter: str
    value: Any
    unit: str
    status: ProvenanceStatus
    description: str
    notes: Optional[str] = None


@dataclass(frozen=True)
class ToolGeometry:
    """Canonical single-source-of-truth tool definition for FAIRINO FR3 gripper."""
    canonical_tcp_offset_m: Tuple[float, float, float]  # [0.0, 0.0, 0.150]
    flange_to_tcp_distance_m: float                     # 0.150
    flange_to_tcp_distance_mm: float                    # 150.0
    cad_length_mm: float                                # 147.5
    legacy_unverified_length_mm: float                  # 218.0
    status: ProvenanceStatus                            # ProvenanceStatus.MEASURED_APPROXIMATE
    cad_status: ProvenanceStatus = ProvenanceStatus.CAD_DERIVED
    legacy_status: ProvenanceStatus = ProvenanceStatus.LEGACY_UNVERIFIED
    mount_type: str = "DIRECT_J6_FLANGE"
    has_adapter_plate: bool = False
    source_file: str = "shared/robot_profiles/fr3.json"




@dataclass(frozen=True)
class BoardGeometry:
    outer_width: float          # mm (367.0)
    outer_length: float         # mm (410.0)
    columns: int                # 9
    rows: int                   # 10
    column_spacing: float       # mm (40.0)
    row_spacing: float          # mm (40.0)
    thickness: float = 10.5     # mm (10.5)

    @property
    def playable_grid_width_mm(self) -> float:
        """Width between column 0 and column (cols-1): (9-1)*40 = 320.0 mm."""
        return (self.columns - 1) * self.column_spacing

    @property
    def playable_grid_length_mm(self) -> float:
        """Length between row 0 and row (rows-1): (10-1)*40 = 360.0 mm."""
        return (self.rows - 1) * self.row_spacing

    @property
    def margin_horizontal_mm(self) -> float:
        """Left/right border margin: (367 - 320) / 2 = 23.5 mm."""
        return (self.outer_width - self.playable_grid_width_mm) / 2.0

    @property
    def margin_vertical_mm(self) -> float:
        """Top/bottom border margin: (410 - 360) / 2 = 25.0 mm."""
        return (self.outer_length - self.playable_grid_length_mm) / 2.0


@dataclass(frozen=True)
class PieceGeometry:
    diameter: float             # mm (22.5)
    height: float               # mm (9.43)

    @property
    def radius(self) -> float:
        """Piece radius in mm (11.25 mm)."""
        return self.diameter / 2.0


@dataclass(frozen=True)
class BoardConvention:
    black_home_row: int         # 0
    red_home_row: int           # 9
    col_min: int                # 0
    col_max: int                # 8
    row_min: int                # 0
    row_max: int                # 9


@dataclass(frozen=True)
class PhysicalGeometry:
    schema_version: int
    unit: str
    board: BoardGeometry
    piece: PieceGeometry
    convention: BoardConvention

    @property
    def outer_width_mm(self) -> float:
        return self.board.outer_width

    @property
    def outer_length_mm(self) -> float:
        return self.board.outer_length

    @property
    def thickness_mm(self) -> float:
        return self.board.thickness

    @property
    def board_thickness_m(self) -> float:
        return self.board.thickness / 1000.0

    @property
    def grid_cell_width_mm(self) -> float:
        return self.board.column_spacing

    @property
    def grid_cell_length_mm(self) -> float:
        return self.board.row_spacing

    @property
    def piece_diameter_mm(self) -> float:
        return self.piece.diameter

    @property
    def piece_height_mm(self) -> float:
        return self.piece.height

    @property
    def playable_width_mm(self) -> float:
        return self.board.playable_grid_width_mm

    @property
    def playable_length_mm(self) -> float:
        return self.board.playable_grid_length_mm

    @property
    def margin_x_mm(self) -> float:
        return self.board.margin_horizontal_mm

    @property
    def margin_y_mm(self) -> float:
        return self.board.margin_vertical_mm

    def grid_to_metric_mm(
        self, col: float, row: float, strict: bool = False
    ) -> Tuple[float, float]:
        """
        Convert Xiangqi board grid coordinate (col, row) to intrinsic board_metric_mm (u_mm, v_mm).
        
        Coordinate definition:
          - Origin (0 mm, 0 mm) is at intersection (col=0, row=0) [Black Xe Left].
          - u_mm increases with col: u_mm = col * column_spacing
          - v_mm increases with row: v_mm = row * row_spacing
        
        Supports continuous float coordinates (e.g. 4.13, 5.08) for visual pick / loose piece.
        If strict=True: enforces bounds [col_min, col_max] and [row_min, row_max].
        If strict=False: performs unbounded conversion without silent clamping.
        """
        if strict:
            if not (self.convention.col_min <= col <= self.convention.col_max):
                raise ValueError(
                    f"col {col} out of strict board grid bounds "
                    f"[{self.convention.col_min}, {self.convention.col_max}]"
                )
            if not (self.convention.row_min <= row <= self.convention.row_max):
                raise ValueError(
                    f"row {row} out of strict board grid bounds "
                    f"[{self.convention.row_min}, {self.convention.row_max}]"
                )

        u_mm = float(col) * self.board.column_spacing
        v_mm = float(row) * self.board.row_spacing
        return (u_mm, v_mm)

    def metric_to_grid(
        self, u_mm: float, v_mm: float, strict: bool = False
    ) -> Tuple[float, float]:
        """
        Convert intrinsic board_metric_mm (u_mm, v_mm) back to board grid (col, row).
        
        col = u_mm / column_spacing
        row = v_mm / row_spacing
        
        If strict=True: enforces bounds.
        If strict=False: returns continuous float values without clamping.
        """
        col = float(u_mm) / self.board.column_spacing
        row = float(v_mm) / self.board.row_spacing

        if strict:
            if not (self.convention.col_min <= col <= self.convention.col_max):
                raise ValueError(
                    f"u_mm={u_mm} maps to col {col}, out of bounds "
                    f"[{self.convention.col_min}, {self.convention.col_max}]"
                )
            if not (self.convention.row_min <= row <= self.convention.row_max):
                raise ValueError(
                    f"v_mm={v_mm} maps to row {row}, out of bounds "
                    f"[{self.convention.row_min}, {self.convention.row_max}]"
                )

        return (col, row)


# Type alias
GeometryConfig = PhysicalGeometry


_CACHED_GEOMETRY: Optional[PhysicalGeometry] = None


def get_default_json_path() -> Path:
    """Resolve default path to shared/physical_geometry.json relative to repository root."""
    # This file is located at <repo>/src/domain/geometry.py
    repo_root = Path(__file__).resolve().parent.parent.parent
    return repo_root / "shared" / "physical_geometry.json"


def _validate_positive_finite(value: object, name: str) -> float:
    try:
        val = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{name} must be a valid float number, got {value!r}")
    if not math.isfinite(val) or val <= 0.0:
        raise ValueError(f"{name} must be a positive finite number (> 0), got {val}")
    return val


def _validate_int(value: object, name: str, min_val: int = 0) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, got boolean {value!r}")
    if isinstance(value, int):
        val = value
    elif isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise ValueError(f"{name} must be an integer value, got {value!r}")
        val = int(value)
    elif isinstance(value, str):
        try:
            val = int(value)
        except ValueError:
            raise ValueError(f"{name} must be an integer, got {value!r}")
    else:
        raise ValueError(f"{name} must be an integer, got {value!r}")

    if val < min_val:
        raise ValueError(f"{name} must be >= {min_val}, got {val}")
    return val


def load_physical_geometry(json_path: Optional[Path] = None) -> PhysicalGeometry:
    """Load and strictly validate physical geometry from canonical JSON."""
    path = Path(json_path) if json_path else get_default_json_path()
    if not path.is_file():
        raise FileNotFoundError(f"Canonical physical geometry file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Root configuration must be a JSON object, got {type(data).__name__}")

    unit = data.get("unit")
    if unit != "mm":
        raise ValueError(f"Expected unit 'mm', found {unit!r} in {path}")

    board_data = data.get("board")
    if not isinstance(board_data, dict):
        raise ValueError("Missing or invalid 'board' object in geometry JSON")

    outer_width = _validate_positive_finite(board_data.get("outer_width"), "board.outer_width")
    outer_length = _validate_positive_finite(board_data.get("outer_length"), "board.outer_length")
    columns = _validate_int(board_data.get("columns"), "board.columns", min_val=2)
    rows = _validate_int(board_data.get("rows"), "board.rows", min_val=2)
    column_spacing = _validate_positive_finite(board_data.get("column_spacing"), "board.column_spacing")
    row_spacing = _validate_positive_finite(board_data.get("row_spacing"), "board.row_spacing")
    thickness = _validate_positive_finite(board_data.get("thickness", 10.5), "board.thickness")

    playable_w = (columns - 1) * column_spacing
    playable_l = (rows - 1) * row_spacing
    if playable_w > outer_width:
        raise ValueError(
            f"Playable grid width ({playable_w}mm) exceeds board outer width ({outer_width}mm)"
        )
    if playable_l > outer_length:
        raise ValueError(
            f"Playable grid length ({playable_l}mm) exceeds board outer length ({outer_length}mm)"
        )

    board = BoardGeometry(
        outer_width=outer_width,
        outer_length=outer_length,
        columns=columns,
        rows=rows,
        column_spacing=column_spacing,
        row_spacing=row_spacing,
        thickness=thickness,
    )

    piece_data = data.get("piece")
    if not isinstance(piece_data, dict):
        raise ValueError("Missing or invalid 'piece' object in geometry JSON")

    piece_diameter = _validate_positive_finite(piece_data.get("diameter"), "piece.diameter")
    piece_height = _validate_positive_finite(piece_data.get("height"), "piece.height")

    piece = PieceGeometry(
        diameter=piece_diameter,
        height=piece_height,
    )

    conv_data = data.get("board_convention")
    if not isinstance(conv_data, dict):
        raise ValueError("Missing or invalid 'board_convention' object in geometry JSON")

    col_min = _validate_int(conv_data.get("col_min"), "convention.col_min", min_val=0)
    col_max = _validate_int(conv_data.get("col_max"), "convention.col_max", min_val=1)
    row_min = _validate_int(conv_data.get("row_min"), "convention.row_min", min_val=0)
    row_max = _validate_int(conv_data.get("row_max"), "convention.row_max", min_val=1)

    if col_min != 0 or col_max != columns - 1:
        raise ValueError(
            f"convention [col_min, col_max] must be [0, {columns - 1}], got [{col_min}, {col_max}]"
        )
    if row_min != 0 or row_max != rows - 1:
        raise ValueError(
            f"convention [row_min, row_max] must be [0, {rows - 1}], got [{row_min}, {row_max}]"
        )

    black_home_row = _validate_int(conv_data.get("black_home_row"), "convention.black_home_row", min_val=row_min)
    red_home_row = _validate_int(conv_data.get("red_home_row"), "convention.red_home_row", min_val=row_min)

    if not (row_min <= black_home_row <= row_max):
        raise ValueError(f"black_home_row={black_home_row} must be within [{row_min}, {row_max}]")
    if not (row_min <= red_home_row <= row_max):
        raise ValueError(f"red_home_row={red_home_row} must be within [{row_min}, {row_max}]")
    if black_home_row == red_home_row:
        raise ValueError("black_home_row and red_home_row cannot be the same row")

    convention = BoardConvention(
        black_home_row=black_home_row,
        red_home_row=red_home_row,
        col_min=col_min,
        col_max=col_max,
        row_min=row_min,
        row_max=row_max,
    )

    schema_version = _validate_int(data.get("schema_version", 1), "schema_version", min_val=1)

    return PhysicalGeometry(
        schema_version=schema_version,
        unit=unit,
        board=board,
        piece=piece,
        convention=convention,
    )


def get_physical_geometry(reload: bool = False) -> PhysicalGeometry:
    """Return cached singleton PhysicalGeometry instance."""
    global _CACHED_GEOMETRY
    if _CACHED_GEOMETRY is None or reload:
        _CACHED_GEOMETRY = load_physical_geometry()
    return _CACHED_GEOMETRY


canonical_geometry: PhysicalGeometry = get_physical_geometry()


def grid_to_metric_mm(
    col: float,
    row: float,
    geom: Optional[PhysicalGeometry] = None,
    strict: bool = False,
) -> Tuple[float, float]:
    """Module-level helper to convert grid (col, row) to metric (u_mm, v_mm)."""
    g = geom or get_physical_geometry()
    return g.grid_to_metric_mm(col, row, strict=strict)


def metric_to_grid(
    u_mm: float,
    v_mm: float,
    geom: Optional[PhysicalGeometry] = None,
    strict: bool = False,
) -> Tuple[float, float]:
    """Module-level helper to convert metric (u_mm, v_mm) to grid (col, row)."""
    g = geom or get_physical_geometry()
    return g.metric_to_grid(u_mm, v_mm, strict=strict)


_CACHED_TOOL_GEOMETRY: Optional[ToolGeometry] = None


def get_default_robot_profile_path() -> Path:
    """Resolve default path to shared/robot_profiles/fr3.json relative to repository root."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    return repo_root / "shared" / "robot_profiles" / "fr3.json"


def load_canonical_tool_geometry(profile_path: Optional[Path] = None) -> ToolGeometry:
    """
    Load canonical tool geometry from shared/robot_profiles/fr3.json.
    Falls back to shared/virtual_fr3_scene.json or measured defaults.
    """
    path = Path(profile_path) if profile_path else get_default_robot_profile_path()
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            tool_data = data.get("tool", {})
            can_tcp = tool_data.get("canonical_tcp", {})
            cad_data = tool_data.get("cad_geometry", {})
            legacy_data = tool_data.get("legacy_geometry", {})

            tcp_xyz = tuple(float(x) for x in can_tcp.get("flange_to_tcp_xyz_m", [0.0, 0.0, 0.150]))
            dist_m = float(can_tcp.get("flange_to_tcp_distance_m", tcp_xyz[2]))
            dist_mm = float(can_tcp.get("length_mm", dist_m * 1000.0))
            cad_mm = float(cad_data.get("length_mm", 147.5))
            legacy_mm = float(legacy_data.get("length_mm", 218.0))
            status = ProvenanceStatus(can_tcp.get("provenance", "MEASURED_APPROXIMATE"))

            return ToolGeometry(
                canonical_tcp_offset_m=(tcp_xyz[0], tcp_xyz[1], tcp_xyz[2]),
                flange_to_tcp_distance_m=dist_m,
                flange_to_tcp_distance_mm=dist_mm,
                cad_length_mm=cad_mm,
                legacy_unverified_length_mm=legacy_mm,
                status=status,
                cad_status=ProvenanceStatus.CAD_DERIVED,
                legacy_status=ProvenanceStatus.LEGACY_UNVERIFIED,
                mount_type=str(tool_data.get("mount_type", "DIRECT_J6_FLANGE")),
                has_adapter_plate=bool(tool_data.get("has_adapter_plate", False)),
                source_file=str(path),
            )
        except Exception:
            pass

    # Fallback to defaults
    return ToolGeometry(
        canonical_tcp_offset_m=(0.0, 0.0, 0.150),
        flange_to_tcp_distance_m=0.150,
        flange_to_tcp_distance_mm=150.0,
        cad_length_mm=147.5,
        legacy_unverified_length_mm=218.0,
        status=ProvenanceStatus.MEASURED_APPROXIMATE,
        cad_status=ProvenanceStatus.CAD_DERIVED,
        legacy_status=ProvenanceStatus.LEGACY_UNVERIFIED,
        mount_type="DIRECT_J6_FLANGE",
        has_adapter_plate=False,
        source_file="defaults",
    )


def get_canonical_tool_geometry(reload: bool = False) -> ToolGeometry:
    """Return cached singleton ToolGeometry instance."""
    global _CACHED_TOOL_GEOMETRY
    if _CACHED_TOOL_GEOMETRY is None or reload:
        _CACHED_TOOL_GEOMETRY = load_canonical_tool_geometry()
    return _CACHED_TOOL_GEOMETRY


def get_physical_constants_provenance() -> Dict[str, ProvenanceRecord]:
    """
    Return comprehensive provenance registry for all physical-critical constants.
    Ensures PROVISIONAL and LEGACY_UNVERIFIED constants are explicitly audited.
    """
    geom = get_physical_geometry()
    tool = get_canonical_tool_geometry()

    return {
        "tool_length": ProvenanceRecord(
            parameter="tool_length",
            value=tool.flange_to_tcp_distance_mm,
            unit="mm",
            status=ProvenanceStatus.MEASURED_APPROXIMATE,
            description="FR3 J6 flange plane to actual grasp center of Xiangqi piece (direct mount)",
            notes="Approx. 150mm measured on physical FR3 hardware. Does not include obsolete adapter plate.",
        ),
        "cad_tool_length": ProvenanceRecord(
            parameter="cad_tool_length",
            value=tool.cad_length_mm,
            unit="mm",
            status=ProvenanceStatus.CAD_DERIVED,
            description="Axial distance from flange mount to fingertip from CAD STEP model",
            notes="Extracted from Assieme_pinza_dita_parallele.stp (147.5mm).",
        ),
        "legacy_tool_length": ProvenanceRecord(
            parameter="legacy_tool_length",
            value=tool.legacy_unverified_length_mm,
            unit="mm",
            status=ProvenanceStatus.LEGACY_UNVERIFIED,
            description="Obsolete Virtual Twin flange-to-TCP length with custom adapter plate",
            notes="OBSOLETE / UNVERIFIED. 218mm replaced by 150mm on direct flange mount.",
        ),
        "board_outer_width": ProvenanceRecord(
            parameter="board_outer_width",
            value=geom.outer_width_mm,
            unit="mm",
            status=ProvenanceStatus.MEASURED,
            description="Full outer wooden frame width across columns (367.0mm)",
        ),
        "board_outer_length": ProvenanceRecord(
            parameter="board_outer_length",
            value=geom.outer_length_mm,
            unit="mm",
            status=ProvenanceStatus.MEASURED,
            description="Full outer wooden frame length across rows (410.0mm)",
        ),
        "board_thickness": ProvenanceRecord(
            parameter="board_thickness",
            value=geom.thickness_mm,
            unit="mm",
            status=ProvenanceStatus.MEASURED,
            description="Board substrate height above table surface (10.5mm)",
        ),
        "grid_column_spacing": ProvenanceRecord(
            parameter="grid_column_spacing",
            value=geom.grid_cell_width_mm,
            unit="mm",
            status=ProvenanceStatus.MEASURED,
            description="Center-to-center spacing between board columns (40.0mm)",
        ),
        "grid_row_spacing": ProvenanceRecord(
            parameter="grid_row_spacing",
            value=geom.grid_cell_length_mm,
            unit="mm",
            status=ProvenanceStatus.MEASURED,
            description="Center-to-center spacing between board rows (40.0mm)",
        ),
        "piece_diameter": ProvenanceRecord(
            parameter="piece_diameter",
            value=geom.piece_diameter_mm,
            unit="mm",
            status=ProvenanceStatus.MEASURED,
            description="Diameter of standard Xiangqi piece (22.5mm)",
        ),
        "piece_height": ProvenanceRecord(
            parameter="piece_height",
            value=geom.piece_height_mm,
            unit="mm",
            status=ProvenanceStatus.MEASURED,
            description="Height of standard Xiangqi piece (9.43mm)",
        ),
        "board_pose_nominal": ProvenanceRecord(
            parameter="board_pose_nominal",
            value={"forward_shift_mm": 15.0, "board_yaw_deg": 90.0, "z_offset_mm": 0.0},
            unit="mm/deg",
            status=ProvenanceStatus.PROVISIONAL_SIMULATION,
            description="Nominal simulation board placement relative to robot base",
            notes="Pending in-situ camera calibration on physical workstation.",
        ),
        "tool_orientation": ProvenanceRecord(
            parameter="tool_orientation",
            value=[180.0, 0.0, 90.0],
            unit="deg",
            status=ProvenanceStatus.PROVISIONAL_SIMULATION,
            description="Target tool downward perpendicular orientation Euler angles (RPY)",
            notes="Points tool approach vector (+Z_tool) along -Z_robot.",
        ),
        "SAFE_Z": ProvenanceRecord(
            parameter="SAFE_Z",
            value=40.0,
            unit="mm",
            status=ProvenanceStatus.PROVISIONAL_SIMULATION,
            description="Safe transit flight height clearance above board surface (H = 40.0mm)",
            notes="Ensures collision-free transit across all board pieces.",
        ),
        "PICK_Z": ProvenanceRecord(
            parameter="PICK_Z",
            value=round(geom.thickness_mm + geom.piece_height_mm / 2.0, 3),
            unit="mm",
            status=ProvenanceStatus.MEASURED_APPROXIMATE,
            description="Nominal TCP z-height at piece grasp center (15.215mm from table, 4.715mm from board surface)",
            notes="Piece center = board_thickness (10.5mm) + piece_height / 2 (4.715mm).",
        ),
        "PLACE_Z": ProvenanceRecord(
            parameter="PLACE_Z",
            value=round(geom.thickness_mm + geom.piece_height_mm / 2.0, 3),
            unit="mm",
            status=ProvenanceStatus.MEASURED_APPROXIMATE,
            description="Nominal TCP z-height at piece release center (15.215mm from table, 4.715mm from board surface)",
            notes="Piece center = board_thickness (10.5mm) + piece_height / 2 (4.715mm).",
        ),
    }


# Canonical board grid dimensions derived directly from shared/physical_geometry.json
CANONICAL_GRID_WIDTH_MM: float = canonical_geometry.board.playable_grid_width_mm    # 320.0 mm
CANONICAL_GRID_LENGTH_MM: float = canonical_geometry.board.playable_grid_length_mm  # 360.0 mm
CANONICAL_BOARD_THICKNESS_MM: float = canonical_geometry.board.thickness            # 10.5 mm
CANONICAL_CELL_SPACING_MM: float = canonical_geometry.board.column_spacing          # 40.0 mm
CANONICAL_GRID_DIAGONAL_MM: float = math.hypot(CANONICAL_GRID_WIDTH_MM, CANONICAL_GRID_LENGTH_MM)  # ~481.66 mm
