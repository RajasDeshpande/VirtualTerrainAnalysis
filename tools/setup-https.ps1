param([string]$LanAddress = '192.168.29.26')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$certDirectory = Join-Path $projectRoot 'certs'
New-Item -ItemType Directory -Force -Path $certDirectory | Out-Null
$terrainOpenSSL = 'C:\Program Files\Git\usr\bin\openssl.exe'
if (-not (Test-Path -LiteralPath $terrainOpenSSL)) { throw 'OpenSSL from Git for Windows was not found.' }
if (Test-Path -LiteralPath (Join-Path $certDirectory 'server.key')) { throw 'Certificate already exists. Keep it unless you intentionally need a new certificate.' }
& $terrainOpenSSL req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes -keyout (Join-Path $certDirectory 'server.key') -out (Join-Path $certDirectory 'server.crt') -subj '/CN=Local terrain viewer' -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:$LanAddress" -addext 'extendedKeyUsage=serverAuth'
if ($LASTEXITCODE -ne 0) { throw 'Certificate creation failed' }
Write-Host "Project-local HTTPS certificate ready for https://${LanAddress}:8443 . Restart the terrain server to enable it. Certificate trust is not installed automatically."
