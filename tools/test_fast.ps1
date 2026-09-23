<#
.SYNOPSIS
    Authoritative fast parallel test runner for Xiangqi Robot unit tests.

.DESCRIPTION
    Executes unit tests using pytest-xdist with worksteal scheduling and
    controlled per-worker thread limits to avoid numerical oversubscription.
    Part A runs parallel-safe tests.
    Part B runs explicitly marked serial tests.
    Hardware tests remain excluded.

.PARAMETER Mode
    Worker presets:
      Full       - 8 workers (Default: single agent full CPU throughput)
      Balanced   - 4 workers (Conservative / balanced resource usage)
      Concurrent - 2 workers (Multi-agent simultaneous testing)

.PARAMETER Workers
    Explicit worker count override. Overrides -Mode when specified.

.PARAMETER Tests
    Target test file(s) or directory. Defaults to 'tests/unit'.

.PARAMETER Marker
    Pytest expression for test selection. Defaults to 'not slow'.

.PARAMETER SerialOnly
    Skip the parallel phase and run only serial-marked tests.

.PARAMETER ParallelOnly
    Skip the serial phase and run only parallel-marked tests.

.PARAMETER Dist
    pytest-xdist distribution mode. Defaults to 'worksteal'.

.PARAMETER Durations
    Number of slowest tests to report. Defaults to 0 (no report).

.PARAMETER VerboseOutput
    Switch for verbose output (-v instead of -q).

.EXAMPLE
    .\tools\test_fast.ps1
    .\tools\test_fast.ps1 -Mode Balanced
    .\tools\test_fast.ps1 -Mode Concurrent
    .\tools\test_fast.ps1 -Workers 4
    .\tools\test_fast.ps1 -Workers 2 -Tests tests/unit/test_phase3b_wiring.py
#>

[CmdletBinding()]
param(
    [ValidateSet("Full", "Balanced", "Concurrent")]
    [string]$Mode = "Full",

    [int]$Workers = 0,

    [string[]]$Tests = @("tests/unit"),

    [string]$Marker = "not slow",

    [switch]$SerialOnly,

    [switch]$ParallelOnly,

    [string]$Dist = "worksteal",

    [int]$Durations = 0,

    [switch]$VerboseOutput
)

$ErrorActionPreference = "Stop"

# Ensure execution from repository root
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# Resolve worker count
$effectiveWorkers = 8
if ($Workers -gt 0) {
    $effectiveWorkers = $Workers
} else {
    switch ($Mode) {
        "Full"       { $effectiveWorkers = 8 }
        "Balanced"   { $effectiveWorkers = 4 }
        "Concurrent" { $effectiveWorkers = 2 }
    }
}

# Enforce strict thread limits to prevent numerical library oversubscription
# (8 worker processes x 1 thread each = 8 logical threads)
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$env:OPENBLAS_NUM_THREADS = "1"
$env:NUMEXPR_NUM_THREADS = "1"
$env:PYTHONPATH = $RepoRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Xiangqi Robot -- Fast Parallel Test Runner" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Mode        : $Mode (Workers: $effectiveWorkers)" -ForegroundColor Gray
Write-Host "Targets     : $($Tests -join ', ')" -ForegroundColor Gray
Write-Host "Base Marker : $Marker" -ForegroundColor Gray
Write-Host "Dist Scheme : $Dist" -ForegroundColor Gray
Write-Host "Thread Caps : OMP=1, MKL=1, OPENBLAS=1, NUMEXPR=1" -ForegroundColor Gray
Write-Host "Repo Root   : $RepoRoot" -ForegroundColor Gray
Write-Host ""

$targetPaths = @()
foreach ($t in $Tests) {
    $cleanPath = $t.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
    $targetPaths += $cleanPath
}

$overallExitCode = 0
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

# -------------------------------------------------------------------------
# Part A: Parallel-Safe Tests
# -------------------------------------------------------------------------
if (-not $SerialOnly) {
    $partAMarker = "$Marker and not serial and not hardware"
    Write-Host ">>> Part A: Running Parallel-Safe Tests (-n $effectiveWorkers) ..." -ForegroundColor Yellow

    $argsA = @("-m", $partAMarker)
    if ($VerboseOutput) {
        $argsA += "-v"
    } else {
        $argsA += "-q"
    }

    $argsA += @("-n", "$effectiveWorkers", "--dist=$Dist")

    if ($Durations -gt 0) {
        $argsA += @("--durations=$Durations", "--durations-min=0.05")
    }

    $argsA += $targetPaths

    python -m pytest @argsA
    $exitA = $LASTEXITCODE

    # Exit code 5 means no tests were collected (e.g. all tests were serial or deselected)
    if ($exitA -ne 0 -and $exitA -ne 5) {
        Write-Host "Part A FAILED with exit code $exitA" -ForegroundColor Red
        $overallExitCode = $exitA
    } elseif ($exitA -eq 5) {
        Write-Host "Part A: No parallel tests collected." -ForegroundColor DarkGray
    } else {
        Write-Host "Part A PASSED." -ForegroundColor Green
    }
}

# -------------------------------------------------------------------------
# Part B: Explicitly Serial Tests
# -------------------------------------------------------------------------
if (-not $ParallelOnly -and $overallExitCode -eq 0) {
    $partBMarker = "$Marker and serial and not hardware"
    Write-Host ">>> Part B: Running Serial Tests (Single Process) ..." -ForegroundColor Yellow

    $argsB = @("-m", $partBMarker)
    if ($VerboseOutput) {
        $argsB += "-v"
    } else {
        $argsB += "-q"
    }

    if ($Durations -gt 0) {
        $argsB += @("--durations=$Durations", "--durations-min=0.05")
    }

    $argsB += $targetPaths

    python -m pytest @argsB
    $exitB = $LASTEXITCODE

    # Exit code 5 means no serial tests collected
    if ($exitB -ne 0 -and $exitB -ne 5) {
        Write-Host "Part B FAILED with exit code $exitB" -ForegroundColor Red
        $overallExitCode = $exitB
    } elseif ($exitB -eq 5) {
        Write-Host "Part B: No serial tests collected (none required)." -ForegroundColor DarkGray
    } else {
        Write-Host "Part B PASSED." -ForegroundColor Green
    }
}

$stopwatch.Stop()
$elapsedSec = [Math]::Round($stopwatch.Elapsed.TotalSeconds, 2)

Write-Host ""
if ($overallExitCode -eq 0) {
    Write-Host "=== ALL TEST SUITES PASSED in $($elapsedSec)s ===" -ForegroundColor Green
} else {
    Write-Host "=== TEST SUITE FAILED (exit code $overallExitCode) in $($elapsedSec)s ===" -ForegroundColor Red
}

exit $overallExitCode
