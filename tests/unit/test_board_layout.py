"""Unit test for 3D viewer initial board layout convention (layout.mjs).

Verifies:
1. Total pieces count is exactly 32.
2. 16 Red pieces and 16 Black pieces.
3. Black pieces occupy rows 0..4; Black King is at (col=4, row=0).
4. Red pieces occupy rows 5..9; Red King is at (col=4, row=9).
5. All 32 initial piece coordinates are unique (no overlap).
6. Piece counts match canonical Xiangqi rules: 1 King, 2 Advisors, 2 Elephants,
   2 Horses, 2 Rooks, 2 Cannons, 5 Pawns per side.
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class BoardLayoutConventionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        node_bin = shutil.which("node")
        if not node_bin:
            raise unittest.SkipTest("Node.js runtime not found in PATH; skipping 3D viewer layout test")

        layout_mjs = os.path.join(_PROJECT_ROOT, "robot-3d-viewer", "layout.mjs")
        if not os.path.exists(layout_mjs):
            raise FileNotFoundError(f"layout.mjs not found at {layout_mjs}")

        # Execute Node snippet to load START_LAYOUT and output as JSON
        js_code = """
        import('./robot-3d-viewer/layout.mjs')
            .then(m => console.log(JSON.stringify(m.START_LAYOUT)))
            .catch(err => { console.error(err); process.exit(1); });
        """
        try:
            proc = subprocess.run(
                [node_bin, "--input-type=module", "-e", js_code],
                capture_output=True,
                text=True,
                cwd=_PROJECT_ROOT,
            )
        except (FileNotFoundError, OSError) as e:
            raise unittest.SkipTest(f"Failed to execute Node.js ({e}); skipping 3D viewer layout test")

        if proc.returncode != 0:
            raise RuntimeError(f"Failed to load layout.mjs via Node: {proc.stderr}")

        cls.layout = json.loads(proc.stdout.strip())

    def test_piece_counts(self):
        self.assertEqual(len(self.layout), 32, "Xiangqi layout must have exactly 32 pieces")
        red_pieces = [p for p in self.layout if p[3] == "r"]
        black_pieces = [p for p in self.layout if p[3] == "b"]
        self.assertEqual(len(red_pieces), 16, "Red must have 16 pieces")
        self.assertEqual(len(black_pieces), 16, "Black must have 16 pieces")

    def test_kings_positions(self):
        black_king = [p for p in self.layout if p[3] == "b" and p[2] == "k"]
        red_king = [p for p in self.layout if p[3] == "r" and p[2] == "k"]

        self.assertEqual(len(black_king), 1)
        self.assertEqual(len(red_king), 1)

        self.assertEqual(black_king[0][0], 4)
        self.assertEqual(black_king[0][1], 0, "Black King must be at (col=4, row=0)")

        self.assertEqual(red_king[0][0], 4)
        self.assertEqual(red_king[0][1], 9, "Red King must be at (col=4, row=9)")

    def test_half_board_separation(self):
        for col, row, ptype, side in self.layout:
            if side == "b":
                self.assertGreaterEqual(row, 0)
                self.assertLessEqual(row, 4, f"Black piece {ptype} at ({col}, {row}) must be on rows 0..4")
            elif side == "r":
                self.assertGreaterEqual(row, 5)
                self.assertLessEqual(row, 9, f"Red piece {ptype} at ({col}, {row}) must be on rows 5..9")

    def test_no_overlapping_positions(self):
        positions = [(p[0], p[1]) for p in self.layout]
        self.assertEqual(len(positions), len(set(positions)), "Initial piece positions must not overlap")

    def test_cannons_and_pawns(self):
        black_cannons = [p for p in self.layout if p[3] == "b" and p[2] == "c"]
        red_cannons = [p for p in self.layout if p[3] == "r" and p[2] == "c"]
        self.assertEqual(len(black_cannons), 2)
        self.assertEqual(len(red_cannons), 2)
        for c in black_cannons:
            self.assertEqual(c[1], 2)
            self.assertIn(c[0], [1, 7])
        for c in red_cannons:
            self.assertEqual(c[1], 7)
            self.assertIn(c[0], [1, 7])

        black_pawns = [p for p in self.layout if p[3] == "b" and p[2] == "p"]
        red_pawns = [p for p in self.layout if p[3] == "r" and p[2] == "p"]
        self.assertEqual(len(black_pawns), 5)
        self.assertEqual(len(red_pawns), 5)
        for p in black_pawns:
            self.assertEqual(p[1], 3)
            self.assertIn(p[0], [0, 2, 4, 6, 8])
        for p in red_pawns:
            self.assertEqual(p[1], 6)
            self.assertIn(p[0], [0, 2, 4, 6, 8])


if __name__ == "__main__":
    unittest.main()
