param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
$folder = [IO.Path]::GetFullPath($Root)
$config = Join-Path $folder 'app\config.py'
if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
    throw 'Extract this patch into the existing Xiangqi folder containing start.bat and app/config.py.'
}
$text = [IO.File]::ReadAllText($config)
$openPattern = '(?m)^(GRIPPER_OPEN_DO_ID\s*=\s*)\d+'
$closePattern = '(?m)^(GRIPPER_CLOSE_DO_ID\s*=\s*)\d+'
if ([regex]::Matches($text, $openPattern).Count -ne 1 -or [regex]::Matches($text, $closePattern).Count -ne 1) {
    throw 'Expected exactly one open/close DO assignment; config.py was not changed.'
}
$updated = [regex]::Replace($text, $openPattern, '${1}0')
$updated = [regex]::Replace($updated, $closePattern, '${1}1')
if ($updated -eq $text) {
    Write-Host 'Already configured: DO0 OPEN, DO1 CLOSE.'
    return
}
$backup = $config + '.before-do-swap-' + [guid]::NewGuid().ToString('N')
Copy-Item -LiteralPath $config -Destination $backup
$temporary = $config + '.do-patch-' + [guid]::NewGuid().ToString('N')
[IO.File]::WriteAllText($temporary, $updated, (New-Object Text.UTF8Encoding($false)))
Move-Item -LiteralPath $temporary -Destination $config -Force
Write-Host 'Applied: DO0 OPEN, DO1 CLOSE. Pulse timings, camera/IP and GPU runtime are unchanged.'
Write-Host ('Config backup: ' + $backup)
Write-Host 'Open start.bat again. No GPU reinstallation needed.'
