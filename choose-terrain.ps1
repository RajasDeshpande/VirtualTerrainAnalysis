$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$terrainRoot = $PSScriptRoot
$choiceFile = Join-Path $terrainRoot 'data\terrain-choice.json'
$saved = Get-Content -LiteralPath $choiceFile -Raw | ConvertFrom-Json

$form = New-Object Windows.Forms.Form
$form.Text = 'Choose real terrain for BlenderGIS VR'
$form.Size = New-Object Drawing.Size(650, 455)
$form.StartPosition = 'CenterScreen'
$form.Font = New-Object Drawing.Font('Segoe UI', 10)

function Add-Label([string]$text, [int]$x, [int]$y, [int]$width=590) {
    $label = New-Object Windows.Forms.Label
    $label.Text = $text; $label.Location = New-Object Drawing.Point($x,$y)
    $label.Size = New-Object Drawing.Size($width,24); $form.Controls.Add($label)
    return $label
}

Add-Label 'Search a place, mountain, town or landmark:' 22 18 | Out-Null
$search = New-Object Windows.Forms.TextBox
$search.Location = New-Object Drawing.Point(22,45); $search.Size = New-Object Drawing.Size(475,27)
$search.Text = $saved.place_name; $form.Controls.Add($search)
$searchButton = New-Object Windows.Forms.Button
$searchButton.Text='Search'; $searchButton.Location=New-Object Drawing.Point(510,43)
$searchButton.Size=New-Object Drawing.Size(100,31); $form.Controls.Add($searchButton)

Add-Label 'Search results (select the exact place):' 22 85 | Out-Null
$results = New-Object Windows.Forms.ComboBox
$results.DropDownStyle='DropDownList'; $results.Location=New-Object Drawing.Point(22,112)
$results.Size=New-Object Drawing.Size(588,28); $form.Controls.Add($results)

Add-Label 'Or enter exact latitude and longitude:' 22 156 | Out-Null
$lat = New-Object Windows.Forms.NumericUpDown
$lat.DecimalPlaces=6; $lat.Minimum=-80; $lat.Maximum=84; $lat.Value=[decimal]$saved.latitude
$lat.Location=New-Object Drawing.Point(22,184); $lat.Size=New-Object Drawing.Size(150,27); $form.Controls.Add($lat)
$lon = New-Object Windows.Forms.NumericUpDown
$lon.DecimalPlaces=6; $lon.Minimum=-180; $lon.Maximum=180; $lon.Value=[decimal]$saved.longitude
$lon.Location=New-Object Drawing.Point(187,184); $lon.Size=New-Object Drawing.Size(150,27); $form.Controls.Add($lon)
Add-Label 'Latitude' 25 211 145 | Out-Null; Add-Label 'Longitude' 190 211 145 | Out-Null

Add-Label 'Terrain width:' 370 156 150 | Out-Null
$size = New-Object Windows.Forms.ComboBox
$size.DropDownStyle='DropDownList'; $size.Location=New-Object Drawing.Point(370,184)
$size.Size=New-Object Drawing.Size(240,28)
$sizes = @(@{Text='1 km × 1 km';Half=500},@{Text='2 km × 2 km (recommended)';Half=1000},@{Text='5 km × 5 km';Half=2500},@{Text='10 km × 10 km';Half=5000})
foreach($entry in $sizes){[void]$size.Items.Add($entry.Text)}
$savedIndex = [Array]::FindIndex([object[]]$sizes, [Predicate[object]]{param($item) $item.Half -eq [int]$saved.half_size_m})
$size.SelectedIndex = if($savedIndex -ge 0){$savedIndex}else{1}; $form.Controls.Add($size)

$info = Add-Label 'Provider: automatic — USGS 3DEP in the continental U.S.; GMRT global data elsewhere. The global source is coarser (~100 m samples).' 22 250 588
$info.Size = New-Object Drawing.Size(588,48)
$status = Add-Label 'Choose a place, then press Build terrain.' 22 303 588
$status.ForeColor = [Drawing.Color]::SteelBlue

$build = New-Object Windows.Forms.Button
$build.Text='Build terrain'; $build.Location=New-Object Drawing.Point(430,345)
$build.Size=New-Object Drawing.Size(180,42); $form.Controls.Add($build)
$cancel = New-Object Windows.Forms.Button
$cancel.Text='Cancel'; $cancel.Location=New-Object Drawing.Point(315,345)
$cancel.Size=New-Object Drawing.Size(100,42); $form.Controls.Add($cancel)

$placeResults = @()
$searchButton.Add_Click({
    if([string]::IsNullOrWhiteSpace($search.Text)){return}
    try {
        $status.Text='Searching OpenStreetMap…'; $form.Refresh()
        $query=[uri]::EscapeDataString($search.Text)
        $headers=@{'User-Agent'='Vr3dTerrainChooser/1.0 (local BlenderGIS project)'}
        $script:placeResults=@(Invoke-RestMethod -Uri "https://nominatim.openstreetmap.org/search?q=$query&format=jsonv2&limit=8" -Headers $headers)
        $results.Items.Clear()
        foreach($item in $script:placeResults){[void]$results.Items.Add($item.display_name)}
        if($results.Items.Count -gt 0){$results.SelectedIndex=0;$status.Text="Found $($results.Items.Count) result(s). Select the correct one."}
        else{$status.Text='No results. Try a broader name or enter coordinates.'}
    } catch {$status.Text='Search failed. Check the internet connection or enter coordinates.'}
})
$results.Add_SelectedIndexChanged({
    if($results.SelectedIndex -ge 0 -and $script:placeResults.Count -gt $results.SelectedIndex){
        $picked=$script:placeResults[$results.SelectedIndex]
        $lat.Value=[decimal]$picked.lat; $lon.Value=[decimal]$picked.lon
    }
})
$cancel.Add_Click({$form.Close()})
$build.Add_Click({
    $name=if($results.SelectedIndex -ge 0){$results.SelectedItem}else{$search.Text}
    if([string]::IsNullOrWhiteSpace($name)){$name="Terrain at $($lat.Value), $($lon.Value)"}
    $choice=[ordered]@{place_name=[string]$name;latitude=[double]$lat.Value;longitude=[double]$lon.Value;half_size_m=[int]$sizes[$size.SelectedIndex].Half;provider='auto'}
    $choice | ConvertTo-Json | Set-Content -LiteralPath $choiceFile -Encoding utf8
    $form.Hide()
    Start-Process powershell.exe -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-File',(Join-Path $terrainRoot 'build.ps1'),'-DownloadTerrain')
    $form.Close()
})
[void]$form.ShowDialog()
