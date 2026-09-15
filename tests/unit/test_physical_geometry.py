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

import tempfile

import config
from src.domain.geometry import (
    GeometryConfig,
    canonical_geometry,
    grid_to_metric_mm,
    load_physical_geometry,
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

    def test_geometry_validation_fail_fast(self):
        """Ensure load_physical_geometry rejects invalid / corrupted geometry configurations."""
        base_valid = {
            "schema_version": 1,
            "unit": "mm",
            "board": {
                "outer_width": 367.0,
                "outer_length": 410.0,
                "columns": 9,
                "rows": 10,
                "column_spacing": 40.0,
                "row_spacing": 40.0,
            },
            "piece": {"diameter": 22.5, "height": 9.43},
            "board_convention": {
                "black_home_row": 0,
                "red_home_row": 9,
                "col_min": 0,
                "col_max": 8,
                "row_min": 0,
                "row_max": 9,
            },
        }

        def assert_raises_with_override(override_fn):
            import copy
            cfg = copy.deepcopy(base_valid)
            override_fn(cfg)
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
                json.dump(cfg, tf)
                temp_path = tf.name
            try:
                with self.assertRaises(ValueError):
                    load_physical_geometry(temp_path)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        # 1. Invalid unit
        assert_raises_with_override(lambda c: c.update({"unit": "cm"}))
        # 2. Negative outer width
        assert_raises_with_override(lambda c: c["board"].update({"outer_width": -100.0}))
        # 3. NaN or inf in spacing
        assert_raises_with_override(lambda c: c["board"].update({"column_spacing": float("nan")}))
        assert_raises_with_override(lambda c: c["board"].update({"row_spacing": float("inf")}))
        # 4. Columns < 2
        assert_raises_with_override(lambda c: c["board"].update({"columns": 1}))
        # 5. Playable area larger than outer board dimensions
        assert_raises_with_override(lambda c: c["board"].update({"column_spacing": 60.0}))  # 8 * 60 = 480 > 367
        # 6. Negative piece diameter or height
        assert_raises_with_override(lambda c: c["piece"].update({"diameter": 0.0}))
        assert_raises_with_override(lambda c: c["piece"].update({"height": -5.0}))
        # 7. Mismatch convention bounds
        assert_raises_with_override(lambda c: c["board_convention"].update({"col_max": 7}))
        assert_raises_with_override(lambda c: c["board_convention"].update({"row_max": 10}))
        # 8. Same black and red home row
        assert_raises_with_override(lambda c: c["board_convention"].update({"black_home_row": 9, "red_home_row": 9}))
        # 9. Float columns (e.g. 9.5) rejected without silent truncation
        assert_raises_with_override(lambda c: c["board"].update({"columns": 9.5}))

    def test_validate_int_strictness(self):
        """Verify _validate_int rejects non-integral floats, NaNs, infinities, booleans without truncation."""
        from src.domain.geometry import _validate_int
        # Valid cases
        self.assertEqual(_validate_int(9, "val"), 9)
        self.assertEqual(_validate_int(9.0, "val"), 9)
        self.assertEqual(_validate_int("9", "val"), 9)
        self.assertEqual(_validate_int(0, "val", min_val=0), 0)

        # Invalid cases: must raise ValueError
        invalid_inputs = [9.5, -3.14, float("nan"), float("inf"), float("-inf"), "9.5", True, False, None, [9]]
        for inp in invalid_inputs:
            with self.assertRaises(ValueError, msg=f"Should reject {inp!r}"):
                _validate_int(inp, "val")

        # Boundary check
        with self.assertRaises(ValueError):
            _validate_int(-1, "val", min_val=0)

    def test_js_geometry_validation_parity(self):
        """Verify JavaScript geometry.mjs enforces the same contract parity via Node.js."""
        import shutil
        import subprocess
        node_bin = shutil.which("node")
        if not node_bin:
            self.skipTest("Node.js runtime not found; skipping JS geometry contract parity test")

        js_code = """
        import { parsePhysicalGeometry } from './robot-3d-viewer/geometry.mjs';
        import fs from 'node:fs';

        const valid = JSON.parse(fs.readFileSync('./shared/physical_geometry.json', 'utf8'));
        const parsed = parsePhysicalGeometry(valid);
        if (parsed.schemaVersion !== 1 || parsed.convention.blackHomeRow !== 0 || parsed.convention.redHomeRow !== 9) {
            throw new Error('Valid parse failed parity check');
        }

        function assertThrows(fn, desc) {
            try {
                fn();
                throw new Error('Expected failure for: ' + desc);
            } catch (err) {
                if (err.message.startsWith('Expected failure')) throw err;
            }
        }

        // Test missing schema_version
        assertThrows(() => {
            const c = JSON.parse(JSON.stringify(valid));
            delete c.schema_version;
            parsePhysicalGeometry(c);
        }, 'missing schema_version');

        // Test float columns (must fail integer check)
        assertThrows(() => {
            const c = JSON.parse(JSON.stringify(valid));
            c.board.columns = 9.5;
            parsePhysicalGeometry(c);
        }, 'float columns');

        // Test missing board_convention
        assertThrows(() => {
            const c = JSON.parse(JSON.stringify(valid));
            delete c.board_convention;
            parsePhysicalGeometry(c);
        }, 'missing board_convention');

        // Test same home row
        assertThrows(() => {
            const c = JSON.parse(JSON.stringify(valid));
            c.board_convention.black_home_row = 9;
            c.board_convention.red_home_row = 9;
            parsePhysicalGeometry(c);
        }, 'same home row');

        console.log('OK');
        """

        proc = subprocess.run(
            [node_bin, "--input-type=module", "-e", js_code],
            capture_output=True,
            text=True,
            cwd=_PROJECT_ROOT,
        )
        self.assertEqual(proc.returncode, 0, f"Node script failed: {proc.stderr}")
        self.assertIn("OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()


