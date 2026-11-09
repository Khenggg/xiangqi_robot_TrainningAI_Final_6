param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
$capsuleRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\')
$archivePath = Join-Path $capsuleRoot 'runtime.zip'
$runtimePath = Join-Path $capsuleRoot 'runtime'
$markerPath = Join-Path $runtimePath '.capsule-ready'
$manifest = Get-Content -LiteralPath (Join-Path $capsuleRoot 'manifest.json') -Raw | ConvertFrom-Json
$expected = $manifest.files.'runtime.zip'
if (-not $expected) { throw 'Missing runtime.zip manifest entry. Extract the complete xiangqi.zip.' }
if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) { throw 'Missing runtime.zip.' }
if ((Get-Item -LiteralPath $archivePath).Length -ne $expected.size) { throw 'runtime.zip size mismatch.' }
$hasher = [Security.Cryptography.SHA256]::Create()
$archiveStream = [IO.File]::OpenRead($archivePath)
try { $digest = ([BitConverter]::ToString($hasher.ComputeHash($archiveStream))).Replace('-', '').ToLowerInvariant() }
finally { $archiveStream.Dispose(); $hasher.Dispose() }
if ($digest -ne $expected.sha256) { throw 'runtime.zip checksum mismatch. Extract xiangqi.zip again.' }
if ((Test-Path -LiteralPath (Join-Path $runtimePath 'python.exe')) -and (Test-Path -LiteralPath $markerPath) -and ((Get-Content -LiteralPath $markerPath -Raw).Trim() -eq $digest)) {
    Write-Host '[SETUP] Runtime already ready.'
    return
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stagingPath = Join-Path $capsuleRoot ('.runtime-install-' + [guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($stagingPath) | Out-Null
$archive = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    Write-Host '[SETUP] Installing base runtime locally...'
    $stagingPrefix = [IO.Path]::GetFullPath($stagingPath).TrimEnd('\') + '\'
    foreach ($entry in $archive.Entries) {
        $target = [IO.Path]::GetFullPath((Join-Path $stagingPath $entry.FullName))
        if (-not $target.StartsWith($stagingPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw ('Unsafe runtime archive entry: ' + $entry.FullName) }
        if ($entry.FullName.EndsWith('/')) {
            [IO.Directory]::CreateDirectory($target) | Out-Null
        } else {
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $target, $false)
        }
    }
} finally { $archive.Dispose() }
if (-not (Test-Path -LiteralPath (Join-Path $stagingPath 'python.exe') -PathType Leaf)) { throw 'Bundled interpreter missing after extraction.' }
if (Test-Path -LiteralPath $runtimePath) {
    $resolvedRuntime = (Resolve-Path -LiteralPath $runtimePath).Path
    if ([IO.Path]::GetDirectoryName($resolvedRuntime) -ne $capsuleRoot) { throw 'Runtime path escaped capsule folder.' }
    $backupPath = Join-Path $capsuleRoot ('runtime-backup-' + [guid]::NewGuid().ToString('N'))
    Move-Item -LiteralPath $resolvedRuntime -Destination $backupPath
}
Move-Item -LiteralPath $stagingPath -Destination $runtimePath
if ($manifest.first_run_downloads) {
    & (Join-Path $runtimePath 'python.exe') -u -I -X utf8 (Join-Path $capsuleRoot 'setup_runtime.py')
    if ($LASTEXITCODE -ne 0) { throw 'ML setup failed. Keep this folder and rerun INSTALL.bat after fixing Internet/driver.' }
}
[IO.File]::WriteAllText($markerPath, $digest, [Text.Encoding]::ASCII)
Write-Host '[SETUP] Complete. Open start.bat to run Xiangqi.'
