param(
    [int]$TargetHour = 3,
    [int]$TargetMinute = 45,
    [int]$TargetSecond = 0
)

$ErrorActionPreference = "Continue"

$repoRoot = "D:\OJT\xiangqi_robot_TrainningAI_Final_6"
$promptFile = Join-Path $repoRoot "tools\codex_prompt_fix_collision.md"
$logDir = Join-Path $repoRoot "reports"
if (!(Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir "codex_scheduled_fix_0345.log"
$lastMsgFile = Join-Path $logDir "codex_last_message_0345.md"

$codexExe = Join-Path $env:LOCALAPPDATA "Programs\OpenAI\Codex\bin\codex.exe"
if (!(Test-Path $codexExe)) {
    $codexExe = Join-Path $env:LOCALAPPDATA "OpenAI\Codex\bin\codex.exe"
}

Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Scheduler initialized. Log: $logFile" | Tee-Object -FilePath $logFile

$now = Get-Date
$target = Get-Date -Hour $TargetHour -Minute $TargetMinute -Second $TargetSecond
if ($target -lt $now) {
    $target = $target.AddDays(1)
}

$waitSec = [int]($target - $now).TotalSeconds
Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Waiting until $target ($waitSec seconds remaining)..." | Tee-Object -FilePath $logFile -Append

if ($waitSec -gt 0) {
    Start-Sleep -Seconds $waitSec
}

Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Target time reached! Triggering Codex execution with model gpt-6-sol (reasoning: xhigh) on $repoRoot..." | Tee-Object -FilePath $logFile -Append

if (!(Test-Path $promptFile)) {
    Write-Output "[ERROR] Prompt file not found: $promptFile" | Tee-Object -FilePath $logFile -Append
    exit 1
}

$promptText = Get-Content $promptFile -Raw -Encoding UTF8

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $codexExe
$psi.Arguments = "exec -m gpt-6-sol -c model_reasoning_effort=`"xhigh`" --dangerously-bypass-approvals-and-sandbox -C `"$repoRoot`" -o `"$lastMsgFile`" -"
$psi.WorkingDirectory = $repoRoot
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$proc = [System.Diagnostics.Process]::Start($psi)
$writer = [System.IO.StreamWriter]::new($proc.StandardInput.BaseStream, [System.Text.Encoding]::UTF8)
$writer.Write($promptText)
$writer.Close()

$stdoutTask = $proc.StandardOutput.ReadToEndAsync()
$stderrTask = $proc.StandardError.ReadToEndAsync()

$proc.WaitForExit()

$stdout = $stdoutTask.Result
$stderr = $stderrTask.Result

Write-Output "=== CODEX OUTPUT ===" | Tee-Object -FilePath $logFile -Append
Write-Output $stdout | Tee-Object -FilePath $logFile -Append

if ($stderr) {
    Write-Output "=== CODEX STDERR ===" | Tee-Object -FilePath $logFile -Append
    Write-Output $stderr | Tee-Object -FilePath $logFile -Append
}

Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Codex execution finished with exit code $($proc.ExitCode)." | Tee-Object -FilePath $logFile -Append

# Run verification test after fix
Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Running verification test: pytest tests/unit/test_phase3_final_master.py -q..." | Tee-Object -FilePath $logFile -Append
$testOutput = & pytest "$repoRoot\tests\unit\test_phase3_final_master.py" -q 2>&1 | Out-String
Write-Output $testOutput | Tee-Object -FilePath $logFile -Append
Write-Output "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] All scheduled actions completed." | Tee-Object -FilePath $logFile -Append
