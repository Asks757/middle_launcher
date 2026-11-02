param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [Parameter(Mandatory = $true)][string]$Target
)
$ErrorActionPreference = 'Stop'
$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$lnkPath = Join-Path $desktop 'Middle Launcher.lnk'
$lnk = $ws.CreateShortcut($lnkPath)
$lnk.TargetPath = $Target
$lnk.Arguments = '"' + (Join-Path $AppDir 'app.py') + '"'
$lnk.WorkingDirectory = $AppDir
$ico = Join-Path $AppDir 'assets\icon.ico'
if (Test-Path $ico) { $lnk.IconLocation = $ico }
$lnk.Description = 'Middle-click radial launcher'
$lnk.Save()
Write-Output "Shortcut created: $lnkPath"
