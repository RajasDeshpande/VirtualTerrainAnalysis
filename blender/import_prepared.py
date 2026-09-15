"""Create the actual terrain using BlenderGIS's DEM_RAW importer."""
import bpy, addon_utils, importlib, json, os, math
from pathlib import Path
import numpy as np

ROOT=Path(os.environ.get('TERRAIN_BUILD_ROOT',Path(__file__).resolve().parents[1]))
meta=json.loads((ROOT/'data/prepared.json').read_text(encoding='utf-8'))
addons=[m.__name__ for m in addon_utils.modules() if m.__name__.lower().startswith('blendergis')]
if len(addons)!=1: raise RuntimeError('Install or enable exactly one BlenderGIS addon')
addon=addons[0]
assert addon_utils.enable(addon,default_set=True),'BlenderGIS failed to enable'
prefs=bpy.context.preferences.addons[addon].preferences
prefs.adjust3Dview=False; prefs.forceTexturedSolid=False
GeoScene=importlib.import_module(addon+'.geoscene').GeoScene
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
geo=GeoScene(scene);geo.crs=meta['crs'];geo.setOriginPrj(*meta['origin_easting_northing_m'])
# Scene and raster are already in the same metric CRS. BlenderGIS must create
# the vertices/faces; no alternate mesh generator participates in the pipeline.
result=bpy.ops.importgis.georaster(filepath=str(ROOT/'data/elevation.tif'),
    importMode='DEM_RAW',reprojection=False,step=1,buildFaces=True)
assert result=={'FINISHED'}
terrain=bpy.context.object
terrain.name='Terrain_BlenderGIS'
terrain['terrain_source']=meta['quality']['dataset']+' via BlenderGIS DEM_RAW'
terrain['analysis_up_world']=[0.,0.,1.];terrain['elevation_offset_m']=0.
terrain['crs']=meta['crs'];terrain['place_name']=meta['place_name']
coords=np.array([tuple(v.co) for v in terrain.data.vertices])
assert np.isfinite(coords).all(), 'BlenderGIS imported invalid coordinates'
ny,nx=meta['quality']['grid_samples'];assert len(coords)==nx*ny
assert len(terrain.data.polygons)==(nx-1)*(ny-1)
half=meta['requested_half_size_m']
assert abs(coords[:,0].min()+half)<.05 and abs(coords[:,0].max()-half)<.05
assert abs(coords[:,1].min()+half)<.05 and abs(coords[:,1].max()-half)<.05
meta.update(source=terrain['terrain_source'],vertices=len(coords),quads=len(terrain.data.polygons),
    min_elevation_m=float(coords[:,2].min()),max_elevation_m=float(coords[:,2].max()),
    blender_version=bpy.app.version_string,addon=addon,discarded_nodata_vertices=0,
    imported_geometry_verified=True)
(ROOT/'data/provenance.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'blender/source.blend'))
print('BLENDERGIS_IMPORT_PASS',len(coords),'vertices; exact projected extent verified')
