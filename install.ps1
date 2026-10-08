param(
    [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' })
)
$ErrorActionPreference = 'Stop'

# Validate both resources before touching an installed pet.
$manifestPath = Join-Path $PSScriptRoot 'pet.json'
$sheetPath = Join-Path $PSScriptRoot 'spritesheet.webp'
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.id -ne 'gpt-pet' -or $manifest.spriteVersionNumber -ne 2 -or $manifest.spritesheetPath -cne 'spritesheet.webp') {
    throw 'Invalid GPT pet manifest. Expected gpt-pet, sprite version 2 and spritesheet.webp.'
}
$sheet = [IO.File]::ReadAllBytes($sheetPath)
if ($sheet.Length -lt 25 -or [Text.Encoding]::ASCII.GetString($sheet,0,4) -ne 'RIFF' -or
    [Text.Encoding]::ASCII.GetString($sheet,8,4) -ne 'WEBP' -or
    [Text.Encoding]::ASCII.GetString($sheet,12,4) -ne 'VP8L' -or $sheet[20] -ne 0x2f) {
    throw 'Expected the lossless static WebP spritesheet.'
}
$bits = [BitConverter]::ToUInt32($sheet,21)
if ((1 + ($bits -band 0x3fff)) -ne 1536 -or (1 + (($bits -shr 14) -band 0x3fff)) -ne 2288) {
    throw 'Expected a 1536 x 2288 spritesheet.'
}
if ([string]::IsNullOrWhiteSpace($CodexHome)) { throw 'CodexHome must not be empty.' }
$CodexHome = [IO.Path]::GetFullPath($CodexHome)
$petsRoot = Join-Path $CodexHome 'pets'
$destination = Join-Path $petsRoot 'gpt-pet'
$backupRoot = Join-Path $CodexHome 'pet-backups'
# Do not follow existing links/junctions when writing or backing up files.
foreach ($path in @($CodexHome,$petsRoot,$destination,$backupRoot)) {
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'An installation directory is a file or a symbolic link/junction.'
        }
    }
}
if (Test-Path -LiteralPath $destination) {
    $linkedItems = Get-ChildItem -LiteralPath $destination -Recurse -Force | Where-Object {
        $_.Attributes -band [IO.FileAttributes]::ReparsePoint
    }
    if ($linkedItems) { throw 'The existing pet contains symbolic links/junctions.' }
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $backupName = 'gpt-pet-{0}-{1}' -f (Get-Date -Format 'yyyyMMdd-HHmmss'),([Guid]::NewGuid().ToString('N'))
    $backup = Join-Path $backupRoot $backupName
    Copy-Item -LiteralPath $destination -Destination $backup -Recurse -Force
    Write-Host "Previous pet backed up to: $backup"
}
New-Item -ItemType Directory -Path $destination -Force | Out-Null
foreach ($name in @('pet.json','spritesheet.webp')) {
    $sourcePath = Join-Path $PSScriptRoot $name
    $targetPath = Join-Path $destination $name
    Copy-Item -LiteralPath $sourcePath -Destination $targetPath -Force
    if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash -ne
        (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash) {
        throw "Copy verification failed: $name. Restore your previous pet from pet-backups if needed."
    }
}
Write-Host "Installed GPT pet to: $destination"
Write-Host 'Open pet settings and select GPT niang. Refresh or restart the app if necessary.'
