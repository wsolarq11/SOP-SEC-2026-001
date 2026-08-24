param(
    [string]$InstallDir = "",
    [switch]$Edge,
    [switch]$NoEdge,
    [string]$Url = ""
)
$ErrorActionPreference = "Stop"

if ($InstallDir -ne "") {
    $base = $InstallDir
} elseif (Test-Path (Join-Path $PSScriptRoot "feishu_mitm_proxy.py")) {
    $base = $PSScriptRoot
} elseif (Test-Path (Join-Path $env:LOCALAPPDATA "FeishuLocalPreview\feishu_mitm_proxy.py")) {
    $base = Join-Path $env:LOCALAPPDATA "FeishuLocalPreview"
} else {
    throw "feishu_mitm_proxy.py not found. Run install.ps1 first."
}

$proxyScript = Join-Path $base "feishu_mitm_proxy.py"
$configPath = Join-Path $base "config.json"
$exampleConfig = Join-Path $base "config.example.json"
if (-not (Test-Path $configPath)) {
    if (-not (Test-Path $exampleConfig)) {
        throw "config.json and config.example.json are missing from $base"
    }
    Copy-Item $exampleConfig $configPath
}
$config = Get-Content $configPath -Raw | ConvertFrom-Json
$proxyPort = [int]$config.listen_port
$pacPort = [int]$config.pac_port
$runDir = Join-Path $base "run"

if (-not (Test-Path (Join-Path $runDir "certs\leaf.crt"))) {
    & python $proxyScript --setup --base $runDir --config $configPath
    if ($LASTEXITCODE -ne 0) { throw "proxy setup failed" }
}

if (-not (Get-NetTCPConnection -LocalPort $proxyPort -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -WindowStyle Hidden -FilePath "python" -ArgumentList @(
        $proxyScript,
        "--base", $runDir,
        "--config", $configPath,
        "--port", "$proxyPort"
    )
}
if (-not (Get-NetTCPConnection -LocalPort $pacPort -State Listen -ErrorAction SilentlyContinue)) {
    Start-Process -WindowStyle Hidden -FilePath "python" -ArgumentList @(
        "-m", "http.server", "$pacPort", "--bind", "127.0.0.1", "--directory", $runDir
    )
}

Start-Sleep -Milliseconds 1200
$proxyListening = [bool](Get-NetTCPConnection -LocalPort $proxyPort -State Listen -ErrorAction SilentlyContinue)
$pacListening = [bool](Get-NetTCPConnection -LocalPort $pacPort -State Listen -ErrorAction SilentlyContinue)
Write-Host "proxy=$proxyListening pac=$pacListening"

if ($Edge -and -not $NoEdge) {
    $edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if (-not (Test-Path $edge)) {
        $edge = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    }
    if (-not (Test-Path $edge)) {
        $edge = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    }
    if (-not (Test-Path $edge)) {
        throw "Edge/Chrome not found"
    }
    if ($Url -eq "") {
        $Url = "https://xcn87k1zyro7.feishu.cn/wiki/AvrWw2db2i4sa6kyfpYcoJTNncM"
    }
    $profile = Join-Path $runDir "feishu-profile"
    $edgeArgs = @(
        "--user-data-dir=$profile",
        "--no-first-run",
        "--disable-features=msEdgeFirstRunExperience,CalculateNativeWinOcclusion",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--proxy-pac-url=http://127.0.0.1:$pacPort/feishu_proxy.pac",
        $Url
    )
    Start-Process -FilePath $edge -ArgumentList $edgeArgs
}
