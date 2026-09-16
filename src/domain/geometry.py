"""
Domain module for Xiangqi physical geometry and coordinate conversion.

Single source of truth loaded from `shared/physical_geometry.json`.
Does NOT import `config.py` to prevent circular dependencies.
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Optional, Tuple



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

