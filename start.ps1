$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction SilentlyContinue) {
    Write-Host 'Port 8080 is already listening. Terrain preview: http://localhost:8080'
} else {
    Start-Process -FilePath (Get-Command node).Source -ArgumentList ('"' + (Join-Path $PSScriptRoot 'server.cjs') + '"') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'logs/server.log') -RedirectStandardError (Join-Path $PSScriptRoot 'logs/server-error.log')
    Write-Host 'Terrain server started: http://localhost:8080'
}
Start-Process 'http://localhost:8080'
