"""Acquire a small real DEM using BlenderGIS's own web-service operator.
Run in Steam Blender with --background --python this_file.
"""
import bpy, addon_utils, importlib, json, hashlib, math, re
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
ADDON = 'BlenderGIS-2215'
choice_path = ROOT / 'data' / 'terrain-choice.json'
# Windows PowerShell 5.1 may write UTF-8 JSON with a byte-order mark.  utf-8-sig
# accepts that form while continuing to read ordinary UTF-8 files correctly.
choice = json.loads(choice_path.read_text(encoding='utf-8-sig')) if choice_path.exists() else {}
LON = float(choice.get('longitude', -119.60))
LAT = float(choice.get('latitude', 37.745))
HALF_SIZE_M = int(choice.get('half_size_m', 1000))
PLACE_NAME = str(choice.get('place_name', 'Yosemite')).strip() or 'Selected terrain'
PROVIDER = str(choice.get('provider', 'auto')).lower()
if not (-180 <= LON <= 180 and -80 <= LAT <= 84):
    raise ValueError('Location must be within longitude -180..180 and latitude -80..84')
if not (250 <= HALF_SIZE_M <= 25000):
    raise ValueError('Half-size must be between 250 and 25,000 metres')
zone = max(1, min(60, int((LON + 180) // 6) + 1))
CRS = f"EPSG:{32600 + zone if LAT >= 0 else 32700 + zone}"
# USGS 3DEP covers the United States. The automatic boundary is deliberately
# conservative; users can explicitly select either provider in the chooser.
if PROVIDER == 'auto':
    PROVIDER = 'usgs' if (-125 <= LON <= -66 and 24 <= LAT <= 50) else 'gmrt'
assert addon_utils.enable(ADDON, default_set=True), 'BlenderGIS failed to enable'
GeoScene = importlib.import_module(ADDON + '.geoscene').GeoScene
reprojPt = importlib.import_module(ADDON + '.core.proj').reprojPt
prefs = bpy.context.preferences.addons[ADDON].preferences
prefs.adjust3Dview = False
prefs.forceTexturedSolid = False
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1
geo = GeoScene(scene)
geo.crs = CRS
cx, cy = reprojPt(4326, int(CRS.split(':')[1]), LON, LAT)
geo.setOriginPrj(cx, cy)
bpy.ops.mesh.primitive_plane_add(size=2 * HALF_SIZE_M)
extent = bpy.context.object
extent.name = 'Download_extent_only'
# BlenderGIS expects this service to return WGS84 GeoTIFF; it does the
# geographic bounding-box conversion, HTTP download and initial DEM import.
if PROVIDER == 'usgs':
    params = {'bbox':'{W},{S},{E},{N}', 'bboxSR':4326, 'imageSR':4326,
              'size':'201,201', 'format':'tiff', 'pixelType':'F32',
              'interpolation':'RSP_BilinearInterpolation',
              'renderingRule':json.dumps({'rasterFunction':'None'}), 'f':'image'}
    url = 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage?' + urlencode(params)
    for key in ('W', 'S', 'E', 'N'):
        url = url.replace('%7B' + key + '%7D', '{' + key + '}')
    provider_label = 'USGS 3DEP'
else:
    url = ('https://www.gmrt.org/services/GridServer?west={W}&east={E}&south={S}'
           '&north={N}&layer=topo&format=geotiff&mresolution=100')
    provider_label = 'GMRT global topography'
entries = json.loads(prefs.demServerJson)
if not any(e[0] == url for e in entries):
    entries.append([url, provider_label, 'Real elevation selected by the terrain chooser'])
prefs.demServerJson = json.dumps(entries)
prefs.demServer = url
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'blender' / 'source.blend'))
assert bpy.ops.importgis.dem_query() == {'FINISHED'}
dem = ROOT / 'blender' / 'srtm.tif'
assert dem.stat().st_size > 10000
# Reimport every DEM sample via BlenderGIS to avoid subdivided texture
# interpolation and obtain metric UTM coordinates for slope calculations.
bpy.data.objects.remove(extent, do_unlink=True)
assert bpy.ops.importgis.georaster(filepath=str(dem), importMode='DEM_RAW',
    rastCRS='EPSG:4326', reprojection=True, step=1, buildFaces=True) == {'FINISHED'}
terrain = bpy.context.object
safe_name = re.sub(r'[^A-Za-z0-9_-]+', '_', PLACE_NAME)[:48].strip('_') or 'Selected'
terrain.name = f'Terrain_{safe_name}_BlenderGIS'

# GMRT GeoTIFF responses can include a one-pixel NaN/no-data border. BlenderGIS
# keeps those samples in DEM_RAW mode, so remove only invalid vertices and any
# faces that touch them before validating or analysing the terrain.
mesh = terrain.data
finite_indices = {
    vertex.index for vertex in mesh.vertices
    if all(math.isfinite(value) for value in vertex.co)
}
discarded_vertices = len(mesh.vertices) - len(finite_indices)
if discarded_vertices:
    assert len(finite_indices) >= 16, 'DEM contains too few usable elevation samples'
    index_map = {old: new for new, old in enumerate(sorted(finite_indices))}
    vertices = [tuple(mesh.vertices[old].co) for old in sorted(finite_indices)]
    faces = [
        tuple(index_map[index] for index in polygon.vertices)
        for polygon in mesh.polygons
        if all(index in finite_indices for index in polygon.vertices)
    ]
    assert faces, 'DEM contains no usable terrain faces after removing no-data samples'
    cleaned = bpy.data.meshes.new(mesh.name + '_finite')
    cleaned.from_pydata(vertices, [], faces)
    cleaned.validate(verbose=True)
    cleaned.update()
    terrain.data = cleaned
    bpy.data.meshes.remove(mesh)

terrain['terrain_source'] = f'{provider_label} via BlenderGIS importgis.dem_query + importgis.georaster DEM_RAW'
terrain['analysis_up_world'] = [0.0, 0.0, 1.0]
terrain['elevation_offset_m'] = 0.0
terrain['crs'] = CRS
zs = [v.co.z for v in terrain.data.vertices]
assert len(zs) >= 16 and all(math.isfinite(z) for z in zs), 'Invalid DEM samples'
assert max(zs) - min(zs) > 0.1, 'Selected DEM is flat or contains no usable relief'
assert -12000 < min(zs) < max(zs) < 10000, 'Invalid or no-data elevations'
metadata = {'source':terrain['terrain_source'], 'service_template':url,
    'place_name':PLACE_NAME, 'provider':PROVIDER,
    'center_lon_lat':[LON,LAT], 'requested_half_size_m':HALF_SIZE_M,
    'note':'BlenderGIS expands bounds by 0.002 degrees; actual coverage is slightly larger than requested.',
    'crs':CRS,'origin_easting_northing_m':[cx,cy],
    'dem_sha256':hashlib.sha256(dem.read_bytes()).hexdigest(),
    'discarded_nodata_vertices':discarded_vertices,
    'vertices':len(zs), 'quads':len(terrain.data.polygons),
    'min_elevation_m':min(zs),'max_elevation_m':max(zs),
    'blender_version':bpy.app.version_string, 'addon':ADDON}
(ROOT / 'data' / 'provenance.json').write_text(json.dumps(metadata,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'blender' / 'source.blend'))
print('TERRAIN_IMPORT_VERIFIED', json.dumps(metadata))
