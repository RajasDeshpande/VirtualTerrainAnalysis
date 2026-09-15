# Terrain analysis and VR

Open **http://localhost:8080** to view your current terrain, or
**http://localhost:8080/choose.html** to select a place and rebuild.
The existing `choose-terrain.cmd` launcher opens the new web chooser using the
installed Chrome executable directly. `start.ps1` starts the local server.

## What you can do

- Choose a place, enter coordinates, or request your device's location.
- Select an exact square area from 0.5 to 10 km wide.
- Switch between real imagery, slope classes and elevation colors.
- Click two points to inspect height, slope, coordinates, rise/drop, horizontal
  separation and straight-line 3D distance. Drag to look around.
- Download the elevation GeoTIFF, elevation CSV, slope CSV, statistics and checks.
- Use a fitted overview or 1:1 exploration with no vertical exaggeration.

Read **http://localhost:8080/guide.html** for an explanation of height, depth,
slope, source accuracy and the processing steps. Quest controller flight and
teleportation remain implemented but not physically verified.

## Accuracy comes from the source

The selected Leh terrain now uses **Copernicus GLO-30**, with an approximately
30 m elevation grid, replacing the coarse GMRT source used by the first chooser.
It covers the requested exact 2 km square, without the old automatic padding.

Copernicus is a surface model (DSM), potentially including vegetation and
structures, referenced to the EGM2008 geoid. This AWS archive is the 2021 release;
primary acquisitions are from 2011–2015, with possible older local infill.
The published vertical specification is <4 m at 90% confidence. **That is not
a locally measured accuracy for this project.** Regional models do not resolve
every path, ditch, building or recent earthwork.

Esri World Imagery supplies real photographed appearance. Centre source/date
metadata are recorded when available. Sharp imagery does not create precise
height measurements. Geographic UVs use the exact projected image extent and
are independently checked against exported vertex coordinates.

For detailed site operations, select **My survey / LiDAR GeoTIFF**. Enter the
path to a georeferenced elevation TIFF covering the chosen area, confirm metre
height units, and describe the vertical datum. Compare it with independent
ground control. The app does not certify local accuracy or route safety.

Automatic mode uses USGS within a continental-U.S. bounding box and Copernicus
elsewhere; explicitly choose the source near borders. Missing coverage stops
the build. Valid flat terrain is accepted. Large local survey areas are capped
at about 500 cells per side for VR; any resulting coarser grid spacing is shown.

## What happens when you build

1. `tools/prepare_data.py` reads the needed DEM window, projects into a metric
   UTM grid, records quality metadata and obtains imagery.
2. `blender/import_prepared.py` uses **BlenderGIS DEM_RAW** to create the actual
   terrain mesh from that GeoTIFF.
3. `blender/terrain_analysis.py` triangulates evaluated world geometry,
   calculates slope against explicit geographic up, assigns materials, and
   exports slope/imagery GLBs, statistics and CSVs.
4. `tests/verify_glb.py` and `tests/verify_accuracy.py` validate every triangle's
   class, exported heights against the DEM, projected extent and imagery UVs.
5. `tools/build_terrain.py` publishes an immutable asset folder and updates
   `webxr/assets/current.json` only after validation passes.

The browser retains the last verified build during processing. Stage progress
and errors appear in the chooser. Previous builds are retained in `builds/`;
the original pre-upgrade terrain is in `backups/before-accuracy-update/`.

Slope thresholds remain editable in `blender/terrain_analysis.py`:
BLUE [0,10], GREEN (10,25], YELLOW (25,35], ORANGE (35,45], RED (45,90] degrees.
Averages are surface-area weighted; surface and horizontal areas are reported
separately. The analysis measures the triangulated model, not sub-grid features.

## Running and testing

Steam Blender: `D:\SteamLibrary\steamapps\common\Blender\blender.exe`.

The project Python environment is `.venv/`. To recreate it:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use the chooser normally. `build.ps1` invokes the same build with
`data/terrain-choice.json`. The old `blender/import_terrain.py` and
`choose-terrain.ps1` are legacy files; the current launcher/server uses the new
pipeline above. Node serves only `webxr/`. Build/search APIs accept requests
from the local PC; LAN/Quest clients can view the published terrain.

- `webxr/assets/verification.json`: geometry-to-raster and geographic UV checks.
- `logs/viewer-logic-tests.json`: DOM/Three.js tests of location labels, display
  modes, scale switching, real mesh raycasts, coordinates and download paths.
- `tests/test_data_quality.py`: input validation, CRS zones, known ramp, exact
  extent and rejection of missing samples.
- `tests/test_slopes.py`: analytic slopes, rotations and reversed winding.
- `logs/imagery-preview.png`, `logs/slope-preview.png`: Blender renders of GLBs.

The DOM tests do not claim to test WebGL or a headset. Live browser interaction
was blocked during this turn. GPU browser rendering and Quest entry still need
live verification. UI tests use jsdom 26.1.0 and A-Frame's Three.js fork
super-three 0.173.4 in `.test-runtime/`; run `node tests/test_viewer.cjs`.

## Quest and Chrome

PC: http://localhost:8080. Current LAN: http://192.168.29.26:8080.
HTTPS: https://192.168.29.26:8443. WebXR requires a secure context.
The LAN certificate is self-signed; headset trust/firewall access remain
unverified. `tools/enable-lan.cmd` requests administrator approval for the
narrowly scoped LAN rule. Authorized ADB reverse forwarding over USB is an
alternative for a developer-enabled Quest; no physical Quest test has run.

Chrome's installed executable launches. Its broken taskbar shortcut points to a
temporary Chrome 152 `old_chrome.exe`, while Chrome 153 is installed. Automatic
approval review blocked the attempted shortcut edit. Windows computer control
also stopped because it could not verify the browser URL. The taskbar repair
was not applied. Desktop/Start Menu Chrome shortcuts target the correct
executable, and the chooser launcher uses it directly.

## Sources

- Copernicus archive: https://registry.opendata.aws/copernicus-dem/
- Accuracy/datum/licence: https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM
- BlenderGIS: https://github.com/domlysz/BlenderGIS
- USGS: https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer
- Imagery: https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer

Dataset attribution is included in generated metadata and displayed in the viewer.
