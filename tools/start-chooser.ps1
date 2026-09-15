$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
if (-not (Get-NetTCPConnection -State Listen -LocalPort 8080 -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath (Get-Command node).Source -ArgumentList ('"'+(Join-Path $projectRoot 'server.cjs')+'"') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'logs/server.log') -RedirectStandardError (Join-Path $projectRoot 'logs/server-error.log')
}
# Open the actual Chrome executable, independent of the old taskbar shortcut.
$terrainChrome='C:\Program Files\Google\Chrome\Application\chrome.exe'
if(Test-Path -LiteralPath $terrainChrome){Start-Process -FilePath $terrainChrome -ArgumentList 'http://localhost:8080/choose.html'}
else{Start-Process 'http://localhost:8080/choose.html'}
