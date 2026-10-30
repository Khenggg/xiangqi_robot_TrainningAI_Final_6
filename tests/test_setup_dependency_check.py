"""Offline dependency inventory and active-mode assets; no hardware access."""
from importlib import metadata
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts.check_runtime import check_assets, check_locked_dependencies


class SetupDependencyTests(unittest.TestCase):
    def check_lock(self, text, versions):
        def installed(name):
            if name not in versions:
                raise metadata.PackageNotFoundError(name)
            return versions[name]
        with tempfile.TemporaryDirectory() as folder:
            lock = Path(folder) / 'requirements.txt'
            lock.write_text(text, encoding='utf-8')
            with patch('scripts.check_runtime.metadata.version', side_effect=installed):
                check_locked_dependencies(lock)

    def test_matching_cpu_wheel_and_marker_need_no_install(self):
        self.check_lock('# lock\ntorch==2.14.0\nunused==1; python_version < "3"\n',
                        {'torch': '2.14.0+cpu'})

    def test_missing_and_wrong_versions_both_reported(self):
        with self.assertRaises(RuntimeError) as caught:
            self.check_lock('numpy==2.5.3\npygame==2.6.1\n', {'numpy': '1.0'})
        self.assertIn('numpy: installed 1.0', str(caught.exception))
        self.assertIn('pygame: missing', str(caught.exception))

    def test_pvp_assets_do_not_require_inactive_geometry_profiles(self):
        cfg = SimpleNamespace(MOONFISH_EXE='engine.py', VISUAL_PVP_PICK_ENABLED=True,
                              VISUAL_HEIGHT_PICK_ENABLED=True, VISUAL_RING_PICK_ENABLED=True,
                              VISUAL_TOP_FACE_ENABLED=True,
                              VISUAL_CAMERA_INTRINSICS_PATH='intrinsics.json',
                              VISUAL_PICK_GEOMETRY_PATH='geometry.json')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('main.py', 'models/best.pt', 'models/cchess/pose_4_v6.onnx',
                         'models/cchess/layout_nano_v3.onnx',
                         'assets/ui/ink-jade-landscape-1440x1080.png', 'engine.py'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture')
            with patch('scripts.check_runtime.ROOT', root):
                check_assets(cfg)
                cfg.VISUAL_PVP_PICK_ENABLED = False
                with self.assertRaisesRegex(FileNotFoundError, 'intrinsics.json'):
                    check_assets(cfg)


if __name__ == '__main__':
    unittest.main()
