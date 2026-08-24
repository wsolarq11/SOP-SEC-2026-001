param(
    [string]$InstallDir = "$env:LOCALAPPDATA\FeishuLocalPreview",
    [switch]$RemoveInstallDir
)
$ErrorActionPreference = "Continue"

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "stop.ps1") -RestoreSystem

$startupCmd = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\feishu-local-preview.cmd"
if (Test-Path $startupCmd) {
    Remove-Item $startupCmd -Force
    Write-Host "removed startup entry"
}

$ca = Get-ChildItem Cert:\CurrentUser\Root -ErrorAction SilentlyContinue |
    Where-Object { $_.Subject -match "Local Feishu (Preview|Stream) Proxy CA" }
foreach ($cert in $ca) {
    Remove-Item -Path ("Cert:\CurrentUser\Root\" + $cert.Thumbprint) -Force
    Write-Host "removed local CA $($cert.Thumbprint)"
}

$policyPaths = @(
    "HKCU:\Software\Policies\Microsoft\Edge",
    "HKCU:\Software\Policies\Google\Chrome"
)
$policyNames = @("BackgroundThrottlingEnabled", "IntensiveWakeUpThrottlingEnabled")
foreach ($path in $policyPaths) {
    foreach ($name in $policyNames) {
        Remove-ItemProperty -Path $path -Name $name -ErrorAction SilentlyContinue
    }
}
Write-Host "removed browser throttling policy values"

$desktopShortcuts = Get-ChildItem ([Environment]::GetFolderPath("Desktop")) -Filter "*飞书预览-本机代理*" -ErrorAction SilentlyContinue
foreach ($shortcut in $desktopShortcuts) {
    Remove-Item $shortcut.FullName -Force
    Write-Host "removed $($shortcut.Name)"
}

if ($RemoveInstallDir -and (Test-Path $InstallDir)) {
    Remove-Item $InstallDir -Recurse -Force
    Write-Host "removed $InstallDir"
}
