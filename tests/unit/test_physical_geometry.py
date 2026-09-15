"""Unit tests for Xiangqi physical geometry contract and coordinate conversions.

Verifies:
1. Canonical measured physical values match shared/physical_geometry.json.
2. Derived values (playable area, margins) are mathematically exact.
3. Grid-to-metric and metric-to-grid mappings handle corners and continuous floats.
4. Out-of-bounds handling: strict mode raises ValueError; non-strict mode computes
   without silent boundary clamping.
5. Backward compatibility aliases in config.py remain consistent.
"""

import json
import os
import sys
import unittest

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import config
from src.domain.geometry import (
    GeometryConfig,
    canonical_geometry,
    grid_to_metric_mm,
    metric_to_grid,
)


class PhysicalGeometryTests(unittest.TestCase):
    """Test canonical geometry values and derived dimensions."""

    def setUp(self):
        self.geom = canonical_geometry

    def test_canonical_measured_values(self):
        """Test A: Physical measured values match the measured physical board."""
        self.assertAlmostEqual(self.geom.outer_width_mm, 367.0, places=3)
        self.assertAlmostEqual(self.geom.outer_length_mm, 410.0, places=3)
        self.assertAlmostEqual(self.geom.grid_cell_width_mm, 40.0, places=3)
        self.assertAlmostEqual(self.geom.grid_cell_length_mm, 40.0, places=3)
        self.assertAlmostEqual(self.geom.piece_diameter_mm, 22.5, places=3)
        self.assertAlmostEqual(self.geom.piece_height_mm, 9.43, places=3)

    def test_canonical_json_parity(self):
        """Verify geometry.py values match shared/physical_geometry.json directly."""
        json_path = os.path.join(_PROJECT_ROOT, "shared", "physical_geometry.json")
        self.assertTrue(os.path.exists(json_path), f"JSON file missing at {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(data["board"]["outer_width"], self.geom.outer_width_mm)
        self.assertEqual(data["board"]["outer_length"], self.geom.outer_length_mm)
        self.assertEqual(data["board"]["column_spacing"], self.geom.grid_cell_width_mm)
        self.assertEqual(data["board"]["row_spacing"], self.geom.grid_cell_length_mm)
        self.assertEqual(data["piece"]["diameter"], self.geom.piece_diameter_mm)
        self.assertEqual(data["piece"]["height"], self.geom.piece_height_mm)

    def test_derived_dimensions(self):
        """Test B: Playable dimensions and border margins."""
        # 8 columns * 40mm = 320mm
        self.assertAlmostEqual(self.geom.playable_width_mm, 320.0, places=3)
        # 9 rows * 40mm = 360mm
        self.assertAlmostEqual(self.geom.playable_length_mm, 360.0, places=3)
        # Margin X = (367 - 320) / 2 = 23.5mm
        self.assertAlmostEqual(self.geom.margin_x_mm, 23.5, places=3)
        # Margin Y = (410 - 360) / 2 = 25.0mm
        self.assertAlmostEqual(self.geom.margin_y_mm, 25.0, places=3)

    def test_grid_to_metric_corners(self):
        """Test C: Grid corner intersections mapped to board metric mm."""
        # (0, 0) is top-left playable intersection
        x0, y0 = grid_to_metric_mm(0, 0, self.geom)
        self.assertAlmostEqual(x0, 0.0, places=3)
        self.assertAlmostEqual(y0, 0.0, places=3)

        # (8, 0) is top-right playable intersection
        x1, y1 = grid_to_metric_mm(8, 0, self.geom)
        self.assertAlmostEqual(x1, 320.0, places=3)
        self.assertAlmostEqual(y1, 0.0, places=3)

        # (0, 9) is bottom-left playable intersection
        x2, y2 = grid_to_metric_mm(0, 9, self.geom)
        self.assertAlmostEqual(x2, 0.0, places=3)
        self.assertAlmostEqual(y2, 360.0, places=3)

        # (8, 9) is bottom-right playable intersection
        x3, y3 = grid_to_metric_mm(8, 9, self.geom)
        self.assertAlmostEqual(x3, 320.0, places=3)
        self.assertAlmostEqual(y3, 360.0, places=3)

    def test_continuous_coordinates(self):
        """Test D: Continuous float coordinates for sub-cell visual pick positions."""
        col, row = 4.13, 5.08
        x, y = grid_to_metric_mm(col, row, self.geom)
        self.assertAlmostEqual(x, 4.13 * 40.0, places=3)  # 165.2
        self.assertAlmostEqual(y, 5.08 * 40.0, places=3)  # 203.2

        # Center of board
        cx, cy = grid_to_metric_mm(4.0, 4.5, self.geom)
        self.assertAlmostEqual(cx, 160.0, places=3)
        self.assertAlmostEqual(cy, 180.0, places=3)

    def test_metric_to_grid_roundtrip(self):
        """Test roundtrip conversion between grid and metric space."""
        test_points = [(0.0, 0.0), (4.0, 4.5), (8.0, 9.0), (1.25, 7.82)]
        for col, row in test_points:
            x, y = grid_to_metric_mm(col, row, self.geom)
            r_col, r_row = metric_to_grid(x, y, self.geom)
            self.assertAlmostEqual(col, r_col, places=5)
            self.assertAlmostEqual(row, r_row, places=5)

    def test_out_of_bounds_handling(self):
        """Test E: Strict mode raises ValueError; non-strict does not clamp."""
        # Strict mode should raise ValueError on out-of-bounds coordinates
        with self.assertRaises(ValueError):
            grid_to_metric_mm(-0.5, 2.0, self.geom, strict=True)
        with self.assertRaises(ValueError):
            grid_to_metric_mm(8.5, 2.0, self.geom, strict=True)
        with self.assertRaises(ValueError):
            grid_to_metric_mm(4.0, -0.1, self.geom, strict=True)
        with self.assertRaises(ValueError):
            grid_to_metric_mm(4.0, 9.5, self.geom, strict=True)

        with self.assertRaises(ValueError):
            metric_to_grid(-5.0, 100.0, self.geom, strict=True)
        with self.assertRaises(ValueError):
            metric_to_grid(325.0, 100.0, self.geom, strict=True)
        with self.assertRaises(ValueError):
            metric_to_grid(100.0, -1.0, self.geom, strict=True)
        with self.assertRaises(ValueError):
            metric_to_grid(100.0, 365.0, self.geom, strict=True)

        # Non-strict mode must compute linearly without silent clamping
        x_neg, y = grid_to_metric_mm(-1.0, 0.0, self.geom, strict=False)
        self.assertAlmostEqual(x_neg, -40.0, places=3)
        self.assertNotEqual(x_neg, 0.0, "Must NOT silently clamp to 0")

        col_neg, row = metric_to_grid(-20.0, 0.0, self.geom, strict=False)
        self.assertAlmostEqual(col_neg, -0.5, places=3)
        self.assertNotEqual(col_neg, 0.0, "Must NOT silently clamp to 0")

    def test_geometry_immutability(self):
        """Ensure GeometryConfig instances are frozen / immutable."""
        with self.assertRaises(Exception):
            self.geom.outer_width_mm = 500.0

    def test_config_backward_compatibility_aliases(self):
        """Ensure legacy aliases in config.py resolve to canonical geometry."""
        self.assertEqual(config.CELL_SIZE_X, 40.0)
        self.assertEqual(config.CELL_SIZE_Y, 40.0)
        self.assertEqual(config.BOARD_WIDTH_MM, 367.0)
        self.assertEqual(config.BOARD_LENGTH_MM, 410.0)
        self.assertEqual(config.PIECE_DIAMETER_MM, 22.5)
        self.assertEqual(config.PIECE_HEIGHT_MM, 9.43)
        self.assertEqual(config.PLAYABLE_WIDTH_MM, 320.0)
        self.assertEqual(config.PLAYABLE_LENGTH_MM, 360.0)
        self.assertEqual(config.BOARD_MARGIN_X_MM, 23.5)
        self.assertEqual(config.BOARD_MARGIN_Y_MM, 25.0)


if __name__ == "__main__":
    unittest.main()
