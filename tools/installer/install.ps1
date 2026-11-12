# Xiangqi-FR3 installer: find or install Python 3.12, create the project venv if
# it does not exist, then let env_check.py add only what is missing.
# Windows PowerShell 5.1 compatible; ASCII only (no BOM needed).
param(
    [Parameter(Mandatory = $true)][string]$Root,
    [ValidateSet('ask', 'yes', 'no')][string]$Mode = 'ask'
)
$CheckArgs = @{ 'ask' = @(); 'yes' = @('--yes'); 'no' = @('--no-input') }[$Mode]
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $Root).Path
$venv = Join-Path $Root '.venv312'
$venvPython = Join-Path $venv 'Scripts\python.exe'
$probe = "import sys,struct;print(sys.version_info[:2]==(3,12) and struct.calcsize('P')==8);print(sys.executable)"

function Write-Step([string]$tag, [string]$message) { Write-Host (" [{0}] {1}" -f $tag, $message) }

function Get-Python312([string]$exe, [string[]]$prefix) {
    if (-not $exe) { return $null }
    try {
        $out = & $exe @prefix -c $probe 2>$null
        if ($LASTEXITCODE -eq 0 -and $out -and $out[0] -eq 'True') { return $out[1] }
    } catch { }
    return $null
}

function Find-Python312 {
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $found = Get-Python312 'py.exe' @('-3.12')
        if ($found) { return $found }
    }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:ProgramFiles 'Python312\python.exe')
    )
    $onPath = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($onPath) { $candidates += $onPath.Source }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            $found = Get-Python312 $candidate @()
            if ($found) { return $found }
        }
    }
    return $null
}

Write-Host ''
Write-Host ' ===================== Xiangqi-FR3 setup check ====================='
if (Test-Path -LiteralPath $venvPython) {
    if (-not (Get-Python312 $venvPython @())) {
        Write-Step 'ERROR' "$venv exists but is not Python 3.12 x64. It was left untouched; rename it and start again."
        exit 1
    }
    Write-Step 'OK' "Project environment: $venv"
} else {
    $python = Find-Python312
    if ($python) {
        Write-Step 'OK' "Python 3.12 found: $python"
    } else {
        $setup = Join-Path $Root 'tools\installer\vendor\python-3.12.10-amd64.exe'
        if (-not (Test-Path -LiteralPath $setup)) {
            Write-Step 'ERROR' 'Python 3.12 is not installed and the bundled installer is missing. Install Python 3.12 x64 and start again.'
            exit 1
        }
        Write-Step 'INSTALL' 'Python 3.12.10 for the current user (other Python versions are kept)...'
        $arguments = @('/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_launcher=1',
                       'InstallLauncherAllUsers=0', 'Include_test=0', 'Shortcuts=0')
        $process = Start-Process -FilePath $setup -ArgumentList $arguments -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            Write-Step 'ERROR' "Python installer failed with exit code $($process.ExitCode)."
            exit 1
        }
        $python = Find-Python312
        if (-not $python) { Write-Step 'ERROR' 'Python 3.12 still not found after installation.'; exit 1 }
        Write-Step 'OK' "Python 3.12 installed: $python"
    }
    # System site-packages stay visible, so libraries already on this PC are reused, not reinstalled.
    Write-Step 'INSTALL' "Creating project environment $venv"
    & $python -m venv --system-site-packages $venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
        Write-Step 'ERROR' 'Could not create the project environment.'
        exit 1
    }
}

& $venvPython -I -X utf8 (Join-Path $Root 'tools\installer\env_check.py') --root $Root @CheckArgs
exit $LASTEXITCODE
