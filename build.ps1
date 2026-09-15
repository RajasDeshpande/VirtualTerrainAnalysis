param([switch]$DownloadTerrain)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$terrainBlender = 'D:\SteamLibrary\steamapps\common\Blender\blender.exe'
if (-not (Test-Path -LiteralPath $terrainBlender)) { throw 'Update the Steam Blender path in build.ps1.' }
$terrainPython=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $terrainPython)) { throw 'Project Python environment missing. Run python -m venv .venv, then .venv\Scripts\python.exe -m pip install -r requirements.txt.' }
& $terrainPython tools/build_terrain.py
if ($LASTEXITCODE -ne 0) { throw 'Terrain build failed. The browser retains the last verified terrain; details are in builds\ and webxr\assets\build-status.json.' }
Start-Process 'http://localhost:8080'
