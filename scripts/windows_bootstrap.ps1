# Windows PowerShell 5.1 compatible. Both launchers use one project environment.
[CmdletBinding()]
param([ValidateSet('Setup', 'Run')][string]$Mode = 'Setup')
# PowerShell 7 parents can pass a module path that omits Windows PowerShell modules.
$windowsModules = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\Modules'
$env:PSModulePath = $windowsModules + ';' + $env:PSModulePath
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
$env:PYTHONUNBUFFERED = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:PYGAME_HIDE_SUPPORT_PROMPT = '1'
$venvPython = Join-Path $projectRoot '.venv312\Scripts\python.exe'
$checkScript = Join-Path $PSScriptRoot 'check_runtime.py'
$logDirectory = Join-Path $projectRoot 'logs'
$transcribing = $false
$result = 1

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    # PS5 transcripts omit native stderr unless routed through host output.
    # Preserve the complete traceback without treating native stderr as a PS exception.
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Executable @Arguments 2>&1 | ForEach-Object { Write-Host $_ }
        $commandResult = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousErrorAction }
    if ($commandResult -ne 0) { throw "Command failed (exit $commandResult): $Executable $($Arguments -join ' ')" }
}

function Install-VisualCppRuntime {
    $systemDirectory = Join-Path $env:WINDIR 'System32'
    $missing = @('vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll') | Where-Object { -not (Test-Path -LiteralPath (Join-Path $systemDirectory $_)) }
    if ($missing.Count -eq 0) { return }
    $cacheDirectory = Join-Path $projectRoot '.setup-cache'
    New-Item -ItemType Directory -Force -Path $cacheDirectory | Out-Null
    $installer = Join-Path $cacheDirectory 'vc_redist.x64.exe'
    Write-Host '[SETUP] Downloading Microsoft Visual C++ x64 runtime required by PyTorch/ONNX.'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $previousProgress = $ProgressPreference
    try {
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/vc14/vc_redist.x64.exe' -OutFile $installer
    } finally { $ProgressPreference = $previousProgress }
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)') {
        throw 'Microsoft runtime installer signature is invalid. Setup stopped before executing it.'
    }
    Write-Host '[SETUP] Installing Microsoft runtime. Accept the Windows administrator permission prompt if shown.'
    $process = Start-Process -FilePath $installer -ArgumentList @('/install', '/passive', '/norestart', '/log', ('"{0}"' -f (Join-Path $logDirectory 'vc-runtime-installer.log'))) -Verb RunAs -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -notin @(0, 3010, 1638)) { throw "Microsoft runtime installation failed (exit $($process.ExitCode)). See logs/vc-runtime-installer.log." }
    if ($process.ExitCode -eq 3010) { Write-Host '[SETUP] Microsoft runtime requested a Windows restart; if preflight fails, restart and run SETUP again.' }
}

function Test-Python312 {
    param([string]$Executable)
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) { return $false }
    try {
        & $Executable -I -c "import sys, struct; sys.exit(0 if sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8 else 1)" *> $null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Find-Python312 {
    if (Test-Python312 $venvPython) { return $venvPython }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $candidate = & $launcher.Source -3.12 -I -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Python312 ($candidate | Select-Object -Last 1))) { return ($candidate | Select-Object -Last 1) }
        } catch { }
    }
    $candidates = @((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'), (Join-Path $env:LOCALAPPDATA 'XiangqiRobot\Python312\python.exe'))
    foreach ($registryPath in @('HKCU:\Software\Python\PythonCore\3.12\InstallPath', 'HKLM:\Software\Python\PythonCore\3.12\InstallPath')) {
        if (Test-Path $registryPath) {
            $properties = Get-ItemProperty $registryPath
            if ($properties.ExecutablePath) { $candidates += $properties.ExecutablePath }
        }
    }
    foreach ($candidate in $candidates) { if (Test-Python312 $candidate) { return $candidate } }
    return $null
}

function Install-Python312 {
    # Final 3.12 release with a traditional Windows installer:
    # https://www.python.org/downloads/release/python-31210/
    $cacheDirectory = Join-Path $projectRoot '.setup-cache'
    New-Item -ItemType Directory -Force -Path $cacheDirectory | Out-Null
    $installer = Join-Path $cacheDirectory 'python-3.12.10-amd64.exe'
    $expectedHash = '67B5635E80EA51072B87941312D00EC8927C4DB9BA18938F7AD2D27B328B95FB'
    if (-not (Test-Path -LiteralPath $installer) -or (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne $expectedHash) {
        Write-Host '[SETUP] Downloading official Python 3.12.10 (64-bit)...'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $previousProgress = $ProgressPreference
        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $installer
        } finally { $ProgressPreference = $previousProgress }
    }
    if ((Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Python installer SHA256 mismatch. Setup stopped before executing it.' }
    $targetDirectory = Join-Path $env:LOCALAPPDATA 'XiangqiRobot\Python312'
    Write-Host "[SETUP] Installing Python for this Windows user: $targetDirectory"
    $installerArguments = @('/quiet', 'InstallAllUsers=0', ('TargetDir="{0}"' -f $targetDirectory), 'Include_pip=1', 'Include_test=0', 'Include_launcher=0', 'PrependPath=0', 'Shortcuts=0', '/log', ('"{0}"' -f (Join-Path $logDirectory 'python-installer.log')))
    $process = Start-Process -FilePath $installer -ArgumentList $installerArguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -notin @(0, 3010)) { throw "Python installer failed (exit $($process.ExitCode)). See logs/python-installer.log." }
    $installedPython = Join-Path $targetDirectory 'python.exe'
    if (-not (Test-Python312 $installedPython)) { throw 'Python installation did not produce working Python 3.12 x64. See logs/python-installer.log.' }
    return $installedPython
}

try {
    New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
    $logPath = Join-Path $logDirectory ("{0}-windows-{1}.log" -f $Mode.ToLower(), (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Start-Transcript -LiteralPath $logPath | Out-Null
    $transcribing = $true
    Write-Host "[$Mode] Project: $projectRoot"
    Write-Host "[$Mode] Log: $logPath"
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64' -or $env:PROCESSOR_ARCHITEW6432 -eq 'ARM64') { throw 'This dependency lock requires Windows x64 (Intel/AMD), not Windows 32-bit or ARM64.' }
    foreach ($file in @('main.py', 'config.py', 'requirements-lock-win-py312.txt', 'scripts\check_runtime.py')) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $file) -PathType Leaf)) { throw "Missing project file: $file. Extract/clone the complete repository first." }
    }
    if ($Mode -eq 'Setup') {
        Install-VisualCppRuntime
        $basePython = Find-Python312
        if (-not $basePython) { $basePython = Install-Python312 }
        Invoke-Checked $basePython @('-X', 'utf8', $checkScript, '--assets-only')
        if (-not (Test-Python312 $venvPython)) {
            $venvDirectory = Join-Path $projectRoot '.venv312'
            if (Test-Path -LiteralPath $venvDirectory) {
                # Literal fixed child path, verified before moving; preserve failed environments.
                $resolvedVenv = (Resolve-Path -LiteralPath $venvDirectory).Path
                if ((Split-Path -Parent $resolvedVenv) -ne $projectRoot) { throw 'Environment path escaped project root; refusing to move it.' }
                $backupPath = Join-Path $projectRoot ('.venv312-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
                Move-Item -LiteralPath $venvDirectory -Destination $backupPath
                Write-Host "[SETUP] Broken environment saved at $backupPath"
            }
            Invoke-Checked $basePython @('-m', 'venv', (Join-Path $projectRoot '.venv312'))
        }
        Write-Host '[SETUP] Installing locked dependencies. Large downloads can take several minutes.'
        Invoke-Checked $venvPython @('-m', 'ensurepip', '--upgrade')
        Invoke-Checked $venvPython @('-m', 'pip', 'install', '--only-binary=:all:', '--timeout', '120', '--retries', '5', '--log', (Join-Path $logDirectory 'pip-install.log'), '-r', (Join-Path $projectRoot 'requirements-lock-win-py312.txt'))
        Invoke-Checked $venvPython @('-m', 'pip', 'check')
        Invoke-Checked $venvPython @('-X', 'utf8', $checkScript)
        Write-Host 'Dependencies OK'
        Write-Host 'Setup complete. Double-click RUN.bat to open the client.'
        Write-Host 'Camera/robot connection and teaching points depend on the physical installation.'
    } else {
        if (-not (Test-Python312 $venvPython)) { throw 'Project Python environment missing/broken. Double-click SETUP_WINDOWS.bat and wait for Setup complete.' }
        Write-Host "[RUN] Python: $venvPython"
        Invoke-Checked $venvPython @('-X', 'utf8', $checkScript)
        Invoke-Checked $venvPython @('-X', 'utf8', (Join-Path $projectRoot 'main.py'))
        Write-Host '[RUN] Client closed.'
    }
    $result = 0
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    if ($Mode -eq 'Setup') { Write-Host 'Setup did NOT complete. Correct the error above, then double-click SETUP_WINDOWS.bat again.' }
    else { Write-Host 'For dependency/model errors, run SETUP_WINDOWS.bat again. Full details are in the log.' }
    if ($logPath) { Write-Host "Log: $logPath" }
} finally { if ($transcribing) { Stop-Transcript | Out-Null } }
exit $result
