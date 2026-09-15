<#
.SYNOPSIS
    Expose the terrain viewer over the internet with a real HTTPS URL.

.DESCRIPTION
    WebXR requires a secure context (HTTPS). This script:
      1. Ensures the local terrain server is running on port 8080.
      2. Opens a public HTTPS tunnel using ngrok (preferred) or cloudflared.
      3. Prints and logs the public URL so you can open it on a Quest or share it.

    INSTALL ONE TUNNEL TOOL (only needed once):
      ngrok       - https://ngrok.com/download
                    then: ngrok config add-authtoken <token>
      cloudflared - winget install --id Cloudflare.cloudflared  (no account needed)

    USAGE:
      .\tools\start-tunnel.ps1                    # auto-detect tool
      .\tools\start-tunnel.ps1 -Tool ngrok        # force ngrok
      .\tools\start-tunnel.ps1 -Tool cloudflared  # force cloudflared

.NOTES
    Build API (/api/build) is intentionally restricted to localhost by server.cjs.
    Viewing, measurements and downloads work from the public URL; builds do not.
#>

param(
    [ValidateSet('auto', 'ngrok', 'cloudflared')]
    [string]$Tool = 'auto',

    [ValidateRange(1, 65535)]
    [int]$Port = 8080
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path $PSScriptRoot -Parent)

# -- 1. Ensure the terrain server is running ----------------------------------

$listening = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host "OK  Terrain server already on port $Port." -ForegroundColor Green
} else {
    Write-Host "Starting terrain server on port $Port..." -ForegroundColor Cyan
    $root      = Split-Path $PSScriptRoot -Parent
    $logsDir   = Join-Path $root 'logs'
    New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
    Start-Process -FilePath (Get-Command node -ErrorAction Stop).Source `
        -ArgumentList ""$(Join-Path $root 'server.cjs')"" `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logsDir 'server.log') `
        -RedirectStandardError  (Join-Path $logsDir 'server-error.log')

    $deadline = [DateTime]::Now.AddSeconds(8)
    while (-not (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)) {
        if ([DateTime]::Now -gt $deadline) {
            throw "Server did not start within 8 s. Check logs\server-error.log."
        }
        Start-Sleep -Milliseconds 300
    }
    Write-Host "OK  Terrain server started on port $Port." -ForegroundColor Green
}

# -- 2. Pick tunnel tool -------------------------------------------------------

function Find-Exe([string]$name) { Get-Command $name -ErrorAction SilentlyContinue }

$useNgrok = $false; $useCloudflared = $false

switch ($Tool) {
    'ngrok' {
        if (-not (Find-Exe 'ngrok')) { throw 'ngrok not found. https://ngrok.com/download' }
        $useNgrok = $true
    }
    'cloudflared' {
        if (-not (Find-Exe 'cloudflared')) { throw 'cloudflared not found. Run: winget install --id Cloudflare.cloudflared' }
        $useCloudflared = $true
    }
    'auto' {
        if (Find-Exe 'ngrok') {
            $useNgrok = $true; Write-Host 'Using ngrok (found in PATH).' -ForegroundColor Cyan
        } elseif (Find-Exe 'cloudflared') {
            $useCloudflared = $true; Write-Host 'Using cloudflared (found in PATH).' -ForegroundColor Cyan
        } else {
            Write-Host ''
            Write-Host 'Neither ngrok nor cloudflared found. Install one:' -ForegroundColor Yellow
            Write-Host '  ngrok:        https://ngrok.com/download'
            Write-Host '                ngrok config add-authtoken <token>'
            Write-Host '  cloudflared:  winget install --id Cloudflare.cloudflared'
            Write-Host ''
            exit 1
        }
    }
}

# -- 3. Start tunnel -----------------------------------------------------------

$root      = Split-Path $PSScriptRoot -Parent
$logsDir   = Join-Path $root 'logs'
$tunnelLog = Join-Path $logsDir 'tunnel.log'
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$publicUrl   = $null
$tunnelProc  = $null

if ($useNgrok) {
    Write-Host "
Starting ngrok -> http://localhost:$Port ..." -ForegroundColor Cyan
    $tunnelProc = Start-Process ngrok `
        -ArgumentList "http $Port --log=stdout --log-format=json" `
        -RedirectStandardOutput $tunnelLog `
        -WindowStyle Hidden -PassThru

    $deadline = [DateTime]::Now.AddSeconds(15)
    while (-not $publicUrl) {
        if ([DateTime]::Now -gt $deadline) {
            $tunnelProc | Stop-Process -Force -ErrorAction SilentlyContinue
            throw "ngrok did not give a URL in 15 s. Check logs\tunnel.log and run: ngrok config add-authtoken <token>"
        }
        Start-Sleep -Milliseconds 500
        try {
            $api   = Invoke-RestMethod -Uri 'http://localhost:4040/api/tunnels' -ErrorAction SilentlyContinue
            $https = $api.tunnels | Where-Object { $_.proto -eq 'https' } | Select-Object -First 1
            if ($https) { $publicUrl = $https.public_url }
        } catch {}
    }
    Write-Host "OK  ngrok tunnel live." -ForegroundColor Green

} elseif ($useCloudflared) {
    Write-Host "
Starting cloudflared -> http://localhost:$Port ..." -ForegroundColor Cyan
    $tunnelProc = Start-Process cloudflared `
        -ArgumentList "tunnel --url http://localhost:$Port" `
        -RedirectStandardError $tunnelLog `
        -WindowStyle Hidden -PassThru

    $deadline = [DateTime]::Now.AddSeconds(25)
    while (-not $publicUrl) {
        if ([DateTime]::Now -gt $deadline) {
            $tunnelProc | Stop-Process -Force -ErrorAction SilentlyContinue
            throw "cloudflared did not give a URL in 25 s. Check logs\tunnel.log."
        }
        Start-Sleep -Milliseconds 500
        if (Test-Path $tunnelLog) {
            $m = Select-String -Path $tunnelLog `
                -Pattern 'https://[a-zA-Z0-9\-]+\.trycloudflare\.com' `
                -ErrorAction SilentlyContinue
            if ($m) { $publicUrl = $m.Matches[0].Value }
        }
    }
    Write-Host "OK  cloudflared tunnel live." -ForegroundColor Green
}

# -- 4. Show and save URL -----------------------------------------------------

$urlLog = Join-Path $logsDir 'public-url.txt'
"$publicUrl
Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" |
    Set-Content -Path $urlLog -Encoding UTF8

Write-Host ""
Write-Host "================================================" -ForegroundColor Yellow
Write-Host " PUBLIC HTTPS URL (works in Quest browser):"     -ForegroundColor Yellow
Write-Host ""
Write-Host "   $publicUrl"                                   -ForegroundColor White
Write-Host ""
Write-Host " Chooser:  $publicUrl/choose.html"              -ForegroundColor Cyan
Write-Host " Guide:    $publicUrl/guide.html"               -ForegroundColor Cyan
Write-Host ""
Write-Host " /api/build is blocked remotely (by design)."   -ForegroundColor DarkGray
Write-Host " URL saved: logs\public-url.txt"                 -ForegroundColor DarkGray
Write-Host "================================================" -ForegroundColor Yellow
Write-Host ""
Write-Host "Press Ctrl+C to close the tunnel." -ForegroundColor Gray

Start-Process $publicUrl

# -- 5. Keep alive until Ctrl+C -----------------------------------------------
try {
    while ($true) { Start-Sleep -Seconds 30 }
} finally {
    if ($tunnelProc) { $tunnelProc | Stop-Process -Force -ErrorAction SilentlyContinue }
    Write-Host "
Tunnel closed." -ForegroundColor Cyan
}