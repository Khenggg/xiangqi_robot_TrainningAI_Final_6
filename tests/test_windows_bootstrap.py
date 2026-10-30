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
        # test_04 already created this isolated no-pip environment. Rewriting
        # python.exe immediately after RUN can fail while Windows releases it.
        # This test still works in isolation and verifies the no-pip precondition.
        if not (self.root / '.venv312/Scripts/python.exe').exists():
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

    def test_06_repeated_healthy_setup_skips_install_even_with_unreachable_index(self):
        system_directory = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'System32'
        if not all((system_directory / name).is_file() for name in
                   ('vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll')):
            self.skipTest('Do not install system runtime in a test')
        # An empty lock intentionally models a fully satisfied environment;
        # real imports/models are covered by check_runtime on the project.
        # Do not start the app or access physical hardware from this fixture.
        check = self.root / 'scripts/check_runtime.py'
        original = check.read_bytes()
        original_environment = self.environment
        try:
            python = str(self.root / '.venv312/Scripts/python.exe')
            if not Path(python).exists():
                creation = self.run_command([sys.executable, '-m', 'venv', '.venv312'])
                self.assertEqual(creation.returncode, 0, creation.stderr)
            else:
                creation = self.run_command([python, '-m', 'ensurepip'])
                self.assertEqual(creation.returncode, 0, creation.stderr)
            check.write_text("print('Fixture preflight OK')\n", encoding='utf-8')
            self.environment = dict(self.environment, PIP_INDEX_URL='http://127.0.0.1:1',
                                    PIP_RETRIES='0', PIP_DEFAULT_TIMEOUT='1')
            for _ in range(2):
                result = self.run_command(['cmd.exe', '/c', 'SETUP_WINDOWS.bat'])
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('skipping pip install and downloads', result.stdout)
                self.assertIn('Fixture preflight OK', result.stdout)
                self.assertIn('Setup complete. Double-click', result.stdout)
        finally:
            check.write_bytes(original)
            self.environment = original_environment


@unittest.skipUnless(sys.platform == 'win32', 'Windows PowerShell cache tests')
class RuntimeCacheTests(unittest.TestCase):
    def run_cache_case(self, cached, downloaded, expected_downloads, expected_installs):
        with tempfile.TemporaryDirectory(prefix='xiangqi cache ') as folder:
            root = Path(folder)
            cache = root / '.setup-cache'
            cache.mkdir()
            installer = cache / 'vc_redist.x64.exe'
            installer.write_text(cached)
            harness = root / 'cache-test.ps1'
            harness.write_text(r'''
param($SourceScript, $Downloaded, [int]$ExpectedDownloads, [int]$ExpectedInstalls)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$logDirectory = Join-Path $projectRoot 'logs'
$env:WINDIR = Join-Path $projectRoot 'fake-windows'
$tokens = $null; $parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($SourceScript, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
$names = @('Install-VisualCppRuntime', 'Test-MicrosoftInstaller')
$functions = $ast.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in $names}, $true)
foreach ($function in $functions) { Invoke-Expression $function.Extent.Text }
$script:downloads = 0; $script:installs = 0
function Get-AuthenticodeSignature {
    param($LiteralPath)
    $status = if ((Get-Content -LiteralPath $LiteralPath -Raw) -eq 'verified') {'Valid'} else {'NotSigned'}
    return [pscustomobject]@{Status=$status; SignerCertificate=[pscustomobject]@{Subject='CN=Microsoft, O=Microsoft Corporation, C=US'}}
}
function Invoke-WebRequest {
    param([switch]$UseBasicParsing, $Uri, $OutFile)
    $script:downloads++
    [IO.File]::WriteAllText($OutFile, $Downloaded)
}
function Start-Process {
    param($FilePath, $ArgumentList, $Verb, $WindowStyle, [switch]$Wait, [switch]$PassThru)
    $script:installs++
    return [pscustomobject]@{ExitCode=0}
}
try { Install-VisualCppRuntime } catch {
    if ($ExpectedInstalls -ne 0) { throw }
}
if ($script:downloads -ne $ExpectedDownloads -or $script:installs -ne $ExpectedInstalls) {
    throw "Unexpected downloads=$script:downloads installs=$script:installs"
}
if (Test-Path -LiteralPath (Join-Path $projectRoot '.setup-cache/vc_redist.x64.exe.download')) {
    throw 'Partial download not cleaned up'
}
''', encoding='utf-8')
            result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                     '-File', str(harness), str(ROOT / 'scripts/windows_bootstrap.ps1'),
                                     downloaded, str(expected_downloads), str(expected_installs)],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return installer.read_text()

    def test_verified_cached_installer_is_reused_without_network(self):
        self.assertEqual(self.run_cache_case('verified', 'unused', 0, 1), 'verified')

    def test_invalid_cache_downloads_verified_replacement(self):
        self.assertEqual(self.run_cache_case('broken', 'verified', 1, 1), 'verified')

    def test_untrusted_download_never_executes_or_replaces_cache(self):
        self.assertEqual(self.run_cache_case('old', 'untrusted', 1, 0), 'old')


if __name__ == "__main__":
    unittest.main()
