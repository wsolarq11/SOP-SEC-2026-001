param(
    [string]$InstallDir = "$env:LOCALAPPDATA\FeishuLocalPreview",
    [switch]$ConfigureSystem,
    [switch]$Startup,
    [switch]$Edge,
    [string]$Url = ""
)
$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
$proxyScript = Join-Path $src "feishu_mitm_proxy.py"
if (-not (Test-Path $proxyScript)) {
    throw "install.ps1 must run from tools\feishu_preview_proxy"
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
$files = @(
    "feishu_mitm_proxy.py",
    "feishu_proxy.pac",
    "config.example.json",
    "start.ps1",
    "stop.ps1",
    "uninstall.ps1",
    "README.md"
)
foreach ($f in $files) {
    $source = Join-Path $src $f
    if (Test-Path $source) {
        Copy-Item $source (Join-Path $InstallDir $f) -Force
    }
}

$configPath = Join-Path $InstallDir "config.json"
if (-not (Test-Path $configPath)) {
    Copy-Item (Join-Path $InstallDir "config.example.json") $configPath
}

$runDir = Join-Path $InstallDir "run"
& python (Join-Path $InstallDir "feishu_mitm_proxy.py") --setup --base $runDir --config $configPath
if ($LASTEXITCODE -ne 0) { throw "proxy setup failed" }

$config = Get-Content $configPath -Raw | ConvertFrom-Json
$pacPort = [int]$config.pac_port

if ($ConfigureSystem) {
    $ca = Join-Path $runDir "certs\ca.crt"
    $existingCa = Get-ChildItem Cert:\CurrentUser\Root -ErrorAction SilentlyContinue |
        Where-Object { $_.Subject -match "Local Feishu (Preview|Stream) Proxy CA" }
    if (-not $existingCa) {
        Import-Certificate -FilePath $ca -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
    }
    $internet = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    Set-ItemProperty -Path $internet -Name ProxyEnable -Value 1 -Type DWord
    Set-ItemProperty -Path $internet -Name AutoConfigURL -Value "http://127.0.0.1:$pacPort/feishu_proxy.pac"
}

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallDir "start.ps1") -NoEdge
if ($LASTEXITCODE -ne 0) { throw "start.ps1 failed" }

if ($Startup) {
    $startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
    New-Item -ItemType Directory -Path $startupDir -Force | Out-Null
    $startupCmd = Join-Path $startupDir "feishu-local-preview.cmd"
    $cmdBody = "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\start.ps1`" -NoEdge"
    Set-Content -Path $startupCmd -Value $cmdBody -Encoding ASCII
}

if ($Edge) {
    if ($Url -eq "") {
        $Url = "https://xcn87k1zyro7.feishu.cn/wiki/AvrWw2db2i4sa6kyfpYcoJTNncM"
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallDir "start.ps1") -Edge -Url $Url
}

Write-Host "installed to $InstallDir"
if ($ConfigureSystem) {
    Write-Host "system proxy and local CA configured"
}
