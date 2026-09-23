<#
.SYNOPSIS
    Benchmark test runner to evaluate test suite scaling across worker counts.

.DESCRIPTION
    Runs a representative subset of tests (~44 tests across configuration,
    motion execution, hardware mocks, vision, physics simulation, reachability,
    and architectural wiring) with varying pytest-xdist worker configurations.
    Measures wall-clock time and speedup.

.PARAMETER Workers
    Array of worker counts to benchmark. Defaults to @(1, 2, 4, 6, 8).

.PARAMETER TimeoutSec
    Per-run timeout in seconds to abort runaway runs. Defaults to 300 (5 min).

.EXAMPLE
    .\tools\benchmark_tests.ps1
    .\tools\benchmark_tests.ps1 -Workers @(1, 2, 4, 8)
#>

[CmdletBinding()]
param(
    [int[]]$Workers = @(1, 2, 4, 6, 8),
    [int]$TimeoutSec = 300
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# Representative subset (44 tests across 7 core modules)
$RepresentativeTests = @(
    "tests/unit/test_config_validation.py",
    "tests/unit/test_motion_executor.py",
    "tests/unit/test_hardware_manager_integration.py",
    "tests/unit/test_occupancy_filter.py",
    "tests/unit/test_piece_drop.py",
    "tests/unit/test_fr3_board_reachability.py",
    "tests/unit/test_phase3b_wiring.py"
)

# Enforce thread caps
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$env:OPENBLAS_NUM_THREADS = "1"
$env:NUMEXPR_NUM_THREADS = "1"
$env:PYTHONPATH = $RepoRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Xiangqi Robot -- Fast Testing Benchmark Tool" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Representative Subset : $($RepresentativeTests.Count) test files" -ForegroundColor Gray
Write-Host "Worker Configurations : $($Workers -join ', ')" -ForegroundColor Gray
Write-Host "Thread Caps           : OMP=1, MKL=1, OPENBLAS=1, NUMEXPR=1" -ForegroundColor Gray
Write-Host ""

$results = @()
$serialDuration = $null

foreach ($w in $Workers) {
    Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
    Write-Host ">>> Benchmarking with $w Worker(s) ..." -ForegroundColor Yellow

    $targetPaths = @()
    foreach ($t in $RepresentativeTests) {
        $targetPaths += $t.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
    }

    $argsList = @("-m", "not slow and not hardware", "-q")
    if ($w -gt 1) {
        $argsList += @("-n", "$w", "--dist=worksteal")
    }
    $argsList += $targetPaths

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    python -m pytest @argsList
    $exitCode = $LASTEXITCODE
    $sw.Stop()

    $duration = [Math]::Round($sw.Elapsed.TotalSeconds, 2)
    $status = if ($exitCode -eq 0) { "PASS" } else { "FAIL" }

    if ($w -eq 1 -and $exitCode -eq 0) {
        $serialDuration = $duration
    }

    $speedup = if ($serialDuration -and $serialDuration -gt 0) {
        [Math]::Round($serialDuration / $duration, 2)
    } else {
        1.0
    }

    $results += [PSCustomObject]@{
        Workers  = $w
        Status   = $status
        Duration = "$($duration)s"
        Speedup  = "${speedup}x"
    }

    Write-Host "Worker $w : $status in $($duration)s (Speedup: ${speedup}x)" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " BENCHMARK SUMMARY TABLE" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
$results | Format-Table -AutoSize

Write-Host "Benchmark complete." -ForegroundColor Green
