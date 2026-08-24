param(
    [string]$InstallDir = "",
    [switch]$RestoreSystem
)
$ErrorActionPreference = "Stop"

if ($InstallDir -ne "") {
    $base = $InstallDir
} elseif (Test-Path (Join-Path $PSScriptRoot "feishu_mitm_proxy.py")) {
    $base = $PSScriptRoot
} elseif (Test-Path (Join-Path $env:LOCALAPPDATA "FeishuLocalPreview\feishu_mitm_proxy.py")) {
    $base = Join-Path $env:LOCALAPPDATA "FeishuLocalPreview"
} else {
    $base = $PSScriptRoot
}

$proxyPort = 18080
$pacPort = 18081
$configPath = Join-Path $base "config.json"
if (Test-Path $configPath) {
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    $proxyPort = [int]$config.listen_port
    $pacPort = [int]$config.pac_port
}

foreach ($port in @($proxyPort, $pacPort)) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "stopped listener on $port"
    }
}

if ($RestoreSystem) {
    $internet = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    Remove-ItemProperty -Path $internet -Name AutoConfigURL -ErrorAction SilentlyContinue
    Set-ItemProperty -Path $internet -Name ProxyEnable -Value 0 -Type DWord
    Write-Host "system PAC proxy removed"
}
