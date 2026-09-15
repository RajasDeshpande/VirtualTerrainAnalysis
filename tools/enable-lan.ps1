# Windows requires administrator rights for this specific firewall rule.
$ErrorActionPreference = 'Stop'
$ruleName = 'Vr3dProject terrain local LAN'
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8080,8443 -Program 'C:\Program Files\nodejs\node.exe' -Profile Private -RemoteAddress LocalSubnet | Out-Null
}
Write-Host 'Terrain ports allowed only from the local subnet on Private networks.'
