"""Compare exported geometry/UVs to the actual projected source raster."""
import os, json, struct, runpy, math
from pathlib import Path
import numpy as np
import rasterio
PROJECT=Path(__file__).resolve().parents[1]
ROOT=Path(os.environ.get('TERRAIN_BUILD_ROOT',PROJECT))
checked=runpy.run_path(str(PROJECT/'tests/verify_glb.py'))
stats=checked['stats'];doc=checked['doc'];accessor=checked['accessor']
origin=stats['export_origin_easting_northing_m'];offset=stats['export_elevation_offset_m']
with rasterio.open(ROOT/'data/elevation.tif') as dem:
    data=dem.read(1);errors=[];uv_error=0;count=0
    for primitive in doc['meshes'][0]['primitives']:
        points=np.array(accessor(primitive['attributes']['POSITION']))
        e=origin[0]+points[:,0];n=origin[1]-points[:,2]
        rows,cols=rasterio.transform.rowcol(dem.transform,e,n)
        rows=np.asarray(rows);cols=np.asarray(cols)
        assert np.all(rows>=0) and np.all(rows<dem.height) and np.all(cols>=0) and np.all(cols<dem.width)
        expected=data[rows,cols];z=points[:,1]+offset
        errors.extend(np.abs(z-expected).tolist());count+=len(points)
        if stats['imagery']['available']:
            uv=np.array(accessor(primitive['attributes']['TEXCOORD_0']))
            x0,y0,x1,y1=stats['imagery']['extent_projected_m']
            expected_uv=np.column_stack(((e-x0)/(x1-x0),(y1-n)/(y1-y0)))
            uv_error=max(uv_error,float(np.max(np.abs(uv-expected_uv))))
    assert max(errors)<.01, max(errors)
    assert uv_error<1e-5,uv_error
    assert abs(stats['min_elevation_m']-float(data.min()))<.01
    assert abs(stats['max_elevation_m']-float(data.max()))<.01
    assert abs(stats['horizontal_area_m2']-(dem.width-1)*(dem.height-1)*abs(dem.transform.a*dem.transform.e))<1
if stats['imagery']['available']:
    raw=(ROOT/'webxr/assets/terrain-imagery.glb').read_bytes()
    length,kind=struct.unpack_from('<II',raw,12);imagery_doc=json.loads(raw[20:20+length])
    assert imagery_doc['images'] and 'bufferView' in imagery_doc['images'][0]
    assert 'baseColorTexture' in imagery_doc['materials'][0]['pbrMetallicRoughness']
    from PIL import Image
    with Image.open(ROOT/'webxr/assets/imagery.jpg') as image:
        assert image.width>=1024 and image.height>=1024
        assert np.asarray(image).std()>10,'Imagery is blank'
report={'result':'PASS','vertex_records_checked':count,
    'max_elevation_difference_from_dem_m':max(errors),'max_georeferenced_uv_error':uv_error,
    'datum':stats['quality']['vertical_datum'],'grid_spacing_m':stats['quality']['grid_spacing_m'],
    'geometry_matches_source':True,'local_survey_accuracy_validated':False,
    'imagery_embedded':stats['imagery']['available']}
(ROOT/'webxr/assets/verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
