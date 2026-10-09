"""Exercise real Windows launchers in isolated clones, never start physical hardware."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "win32" and sys.version_info[:2] == (3, 12), "Windows/Python 3.12 launcher tests")
class WindowsBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="xiangqi bootstrap ")
        cls.root = Path(cls.temporary.name) / "New folder" / "project"
        cls.root.mkdir(parents=True)
        (cls.root / "scripts").mkdir()
        for name in ("RUN.bat", "SETUP_WINDOWS.bat", "scripts/windows_bootstrap.ps1", "scripts/check_runtime.py"):
            shutil.copy2(ROOT / name, cls.root / name)
        (cls.root / "main.py").write_text("raise AssertionError('Client must not start during failed preflight')\n")
        (cls.root / "requirements-lock-win-py312.txt").write_text("# Empty test fixture only\n")
        (cls.root / "config.py").write_text("MOONFISH_EXE='moonfish/moonfish_ucci.py'\nVISUAL_HEIGHT_PICK_ENABLED=False\nVISUAL_RING_PICK_ENABLED=False\nVISUAL_TOP_FACE_ENABLED=False\n")
        for name in ("models/best.pt", "models/cchess/pose_4_v6.onnx", "models/cchess/layout_nano_v3.onnx",
                     "assets/ui/ink-jade-landscape-1440x1080.png", "moonfish/moonfish_ucci.py"):
            path = cls.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"Fixture data, not a real model")
        cls.environment = dict(os.environ, XIANGQI_NO_PAUSE="1")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_command(self, arguments):
        return subprocess.run(arguments, cwd=self.root, env=self.environment, capture_output=True,
                              encoding="utf-8", errors="replace", timeout=60)

    def test_01_run_missing_environment_does_not_fall_back_to_system_python(self):
        result = self.run_command(["cmd.exe", "/c", "RUN.bat"])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("SETUP_WINDOWS.bat", result.stdout)
        self.assertIn("environment missing/broken", result.stdout)
        self.assertNotIn("Client must not start", result.stdout + result.stderr)

    def test_02_assets_only_handles_spaces_and_reports_missing_model(self):
        model = self.root / "models/best.pt"
        model.unlink()
        try:
            result = self.run_command([sys.executable, "scripts/check_runtime.py", "--assets-only"])
            self.assertEqual(result.returncode, 1)
            self.assertIn("Missing/empty project asset", result.stderr)
            self.assertIn("best.pt", result.stderr)
            self.assertNotIn("ultralytics", result.stderr)
        finally:
            model.write_bytes(b"Fixture model")

    def test_03_git_lfs_pointer_is_not_accepted_as_a_model(self):
        model = self.root / "models/best.pt"
        model.write_text("version https://git-lfs.github.com/spec/v1\n")
        try:
            result = self.run_command([sys.executable, "scripts/check_runtime.py", "--assets-only"])
            self.assertEqual(result.returncode, 1)
            self.assertIn("Git LFS pointer", result.stderr)
        finally:
            model.write_bytes(b"Fixture model")

    def test_04_incomplete_venv_is_detected_before_main_with_logged_traceback(self):
        creation = self.run_command([sys.executable, "-m", "venv", "--without-pip", ".venv312"])
        self.assertEqual(creation.returncode, 0, creation.stderr)
        result = self.run_command(["cmd.exe", "/c", "RUN.bat"])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Project assets OK", result.stdout)
        self.assertIn("No module named 'cv2'", result.stdout + result.stderr)
        self.assertNotIn("Client must not start", result.stdout + result.stderr)
        self.assertIn("SETUP_WINDOWS.bat", result.stdout)
        logs = list((self.root / "logs").glob("run-windows-*.log"))
        self.assertTrue(logs)
        self.assertTrue(any("No module named 'cv2'" in path.read_text(encoding="utf-8-sig", errors="replace") for path in logs))

    def test_05_setup_repairs_missing_pip_but_never_reports_false_success(self):
        system_directory = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32"
        if not all((system_directory / name).is_file() for name in ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")):
            self.skipTest("Do not request system runtime installation from an automated test")
        creation = self.run_command([sys.executable, "-m", "venv", "--without-pip", ".venv312"])
        self.assertEqual(creation.returncode, 0, creation.stderr)
        python = str(self.root / ".venv312/Scripts/python.exe")
        self.assertNotEqual(self.run_command([python, "-m", "pip", "--version"]).returncode, 0)
        result = self.run_command(["cmd.exe", "/c", "SETUP_WINDOWS.bat"])
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(self.run_command([python, "-m", "pip", "--version"]).returncode, 0)
        self.assertIn("No module named 'cv2'", result.stdout + result.stderr)
        self.assertIn("Setup did NOT complete", result.stdout)
        self.assertNotIn("Dependencies OK", result.stdout)
        self.assertNotIn("Setup complete. Double-click", result.stdout)


if __name__ == "__main__":
    unittest.main()
