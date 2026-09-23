<#
.SYNOPSIS
    Authoritative serial pytest runner for Xiangqi Robot unit tests.

.DESCRIPTION
    Executes unit tests strictly in a single process.
    Used for serial vs parallel equivalence checking, debugging flaky tests,
    and verifying process-isolation issues.
    Never executes physical hardware tests.

.PARAMETER Tests
    Target test file(s) or directory. Defaults to 'tests/unit'.

.PARAMETER Marker
    Pytest expression for marker selection. Defaults to 'not slow and not hardware'.

.PARAMETER Durations
    Number of slowest tests to report. Defaults to 0 (no report).

.PARAMETER VerboseOutput
    Switch for verbose output (-v instead of -q).

.EXAMPLE
    .\tools\test_serial.ps1
    .\tools\test_serial.ps1 -Tests tests/unit/test_phase3b_wiring.py
    .\tools\test_serial.ps1 -Durations 10
#>

[CmdletBinding()]
param(
    [string[]]$Tests = @("tests/unit"),
    [string]$Marker = "not slow and not hardware",
    [int]$Durations = 0,
    [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"

# Ensure we run from repository root
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# Enforce clean environment
$env:PYTHONPATH = $RepoRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Xiangqi Robot -- Serial Test Runner (Debug / Equivalence)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Targets : $($Tests -join ', ')" -ForegroundColor Gray
Write-Host "Marker  : $Marker" -ForegroundColor Gray
Write-Host "Root    : $RepoRoot" -ForegroundColor Gray
Write-Host ""

$pytestArgs = @("-m", $Marker)
if ($VerboseOutput) {
    $pytestArgs += "-v"
} else {
    $pytestArgs += "-q"
}

if ($Durations -gt 0) {
    $pytestArgs += @("--durations=$Durations", "--durations-min=0.05")
}

foreach ($t in $Tests) {
    $cleanPath = $t.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
    $pytestArgs += $cleanPath
}

$startTime = [System.Diagnostics.Stopwatch]::StartNew()

Write-Host "Running: python -m pytest $($pytestArgs -join ' ')" -ForegroundColor Yellow
python -m pytest @pytestArgs
$exitCode = $LASTEXITCODE

$startTime.Stop()
$elapsedSec = [Math]::Round($startTime.Elapsed.TotalSeconds, 2)

Write-Host ""
if ($exitCode -eq 0) {
    Write-Host "=== SERIAL RUN PASSED in $($elapsedSec)s ===" -ForegroundColor Green
} else {
    Write-Host "=== SERIAL RUN FAILED (exit code $exitCode) in $($elapsedSec)s ===" -ForegroundColor Red
}

exit $exitCode
