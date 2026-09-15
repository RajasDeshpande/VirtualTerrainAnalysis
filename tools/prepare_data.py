"""Clip actual elevation, project in metres, and acquire georeferenced imagery.
Rasterio handles raster I/O; BlenderGIS remains responsible for terrain creation.
"""
import json, os, math, hashlib, time
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
import numpy as np
import rasterio
from rasterio.warp import reproject, transform_bounds, Resampling
from rasterio.transform import from_origin
from rasterio.windows import from_bounds, Window
from pyproj import Transformer, Geod
from PIL import Image

PROJECT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('TERRAIN_BUILD_ROOT', PROJECT))
IMAGERY = 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
COP_NOTICE = ('produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and '
              '© Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS '
              'by the European Union and ESA; all rights reserved')

def get(url, binary=False):
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers={'User-Agent':'TerrainAnalysis/2.0'}),timeout=45) as response:
                data = response.read()
            return data if binary else json.loads(data)
        except Exception:
            if attempt == 2: raise
            time.sleep(2)

def validate_choice(c):
    lon, lat = float(c['longitude']), float(c['latitude'])
    half = float(c.get('half_size_m',1000))
    if not all(math.isfinite(x) for x in (lon,lat,half)):
        raise ValueError('Coordinates and area size must be finite numbers')
    if not (-179.8 < lon < 179.8 and -79.8 < lat < 83.8):
        raise ValueError('Choose an area between 80°S and 84°N, away from the date line')
    if not 250 <= half <= 5000: raise ValueError('Choose a width between 0.5 and 10 km')
    provider = c.get('provider','auto')
    if provider not in ('auto','copernicus','usgs','local'):
        raise ValueError('Choose Copernicus 30 m, USGS, or a local survey GeoTIFF')
    zone = min(60, int((lon+180)//6)+1)
    if 56 <= lat < 64 and 3 <= lon < 12: zone=32
    if 72 <= lat < 84 and 0 <= lon < 42:
        zone = 31 if lon<9 else 33 if lon<21 else 35 if lon<33 else 37
    crs = f'EPSG:{(32600 if lat>=0 else 32700)+zone}'
    return lon,lat,half,provider,crs

def tile_url(lon,lat):
    stem=f"Copernicus_DSM_COG_10_{'N' if lat>=0 else 'S'}{abs(lat):02d}_00_{'E' if lon>=0 else 'W'}{abs(lon):03d}_00_DEM"
    return f'https://copernicus-dem-30m.s3.amazonaws.com/{stem}/{stem}.tif'

def warp_sources(sources, bounds, crs, step):
    # Posts span the exact selected extent. GeoTIFF tags locate pixel centres.
    cells=math.ceil((bounds[2]-bounds[0])/step)
    if cells>512: raise ValueError('This extent needs too many samples for VR; reduce area or use a coarser grid')
    step=(bounds[2]-bounds[0])/cells
    n=cells+1
    dst_transform=from_origin(bounds[0]-step/2,bounds[3]+step/2,step,step)
    output=np.full((n,n),np.nan,dtype='float32')
    source_info=[]
    for source in sources:
        with rasterio.open(source) as ds:
            if ds.crs is None: raise ValueError('The source GeoTIFF has no coordinate system')
            sb=transform_bounds(crs,ds.crs,*bounds,densify_pts=21)
            wb=from_bounds(*sb,transform=ds.transform)
            x0=max(0,math.floor(wb.col_off)-3);y0=max(0,math.floor(wb.row_off)-3)
            x1=min(ds.width,math.ceil(wb.col_off+wb.width)+3);y1=min(ds.height,math.ceil(wb.row_off+wb.height)+3)
            if x1<=x0 or y1<=y0: continue
            window=Window(x0,y0,x1-x0,y1-y0)
            arr=ds.read(1,window=window,masked=True).astype('float32').filled(np.nan)
            piece=np.full_like(output,np.nan)
            reproject(arr,piece,src_transform=ds.window_transform(window),src_crs=ds.crs,
                src_nodata=np.nan,dst_transform=dst_transform,dst_crs=crs,dst_nodata=np.nan,
                resampling=Resampling.bilinear)
            output[np.isfinite(piece)]=piece[np.isfinite(piece)]
            source_info.append({'url_or_file':str(source),'crs':str(ds.crs),
                'pixel_spacing_source_units':list(ds.res),'window_samples':[int(window.width),int(window.height)]})
    if not np.isfinite(output).all():
        raise ValueError(f'Elevation coverage is incomplete ({100*np.isfinite(output).mean():.1f}% valid). Choose a smaller area or a complete local DEM. Missing terrain is not invented.')
    if not (-12000<float(output.min())<=float(output.max())<10000):
        raise ValueError('Invalid elevation range; check source units and no-data values')
    return output,dst_transform,step,source_info

def fetch_imagery(bounds,crs):
    size=2048
    info=get(IMAGERY+'/export?'+urlencode({'bbox':','.join(map(str,bounds)),
        'bboxSR':crs.split(':')[1],'imageSR':crs.split(':')[1],
        'size':f'{size},{size}','format':'jpg','f':'json'}))
    if 'error' in info: raise ValueError(str(info['error']))
    href=info['href']
    if not urlparse(href).hostname.endswith('arcgisonline.com'): raise ValueError('Unexpected imagery host')
    path=ROOT/'webxr/assets/imagery.jpg';path.write_bytes(get(href,True))
    with Image.open(path) as img:
        img.verify()
    extent=info['extent']; bb=[extent[k] for k in ('xmin','ymin','xmax','ymax')]
    # Both texture and DEM use this exact projected reference; no guessed UVs.
    credit=get(IMAGERY+'?f=json').get('copyrightText','Esri, Maxar, Earthstar Geographics and the GIS User Community')
    metadata={'available':True,'source':'Esri World Imagery','attribution':credit,
        'extent_projected_m':bb,'crs':crs,'width':info['width'],'height':info['height'],
        'export_pixel_spacing_m':(bb[2]-bb[0])/info['width'],
        'acquisition_date':'Not established for this image; imagery is not live',
        'native_resolution':'Varies by imagery source; output pixel size does not establish source accuracy',
        'service':IMAGERY}
    # Metadata is useful when available, but failure must not invalidate the DEM.
    try:
        q=get(IMAGERY+'/identify?'+urlencode({'geometry':f'{(bb[0]+bb[2])/2},{(bb[1]+bb[3])/2}',
            'geometryType':'esriGeometryPoint','sr':crs.split(':')[1],
            'mapExtent':','.join(map(str,bb)),'imageDisplay':f'{size},{size},96',
            'tolerance':1,'layers':'all','returnGeometry':'false','f':'json'}))
        metadata['source_records']=[r.get('attributes',{}) for r in q.get('results',[])][:8]
    except Exception: metadata['source_records']=[]
    return metadata

def run():
    for d in ('data','blender','webxr/assets','logs'): (ROOT/d).mkdir(parents=True,exist_ok=True)
    c=json.loads((ROOT/'data/terrain-choice.json').read_text(encoding='utf-8-sig'))
    lon,lat,half,provider,crs=validate_choice(c)
    if provider=='auto': provider='usgs' if -125<=lon<=-66 and 24<=lat<=50 else 'copernicus'
    to_utm=Transformer.from_crs(4326,crs,always_xy=True)
    cx,cy=to_utm.transform(lon,lat)
    bounds=[cx-half,cy-half,cx+half,cy+half]
    if provider=='copernicus':
        geo=transform_bounds(crs,4326,*bounds,densify_pts=21)
        sources=[tile_url(x,y) for x in range(math.floor(geo[0]),math.floor(geo[2])+1)
                 for y in range(math.floor(geo[1]),math.floor(geo[3])+1)]
        if len(sources)>4: raise ValueError('Choose a smaller area')
        step=30
        quality={'dataset':'Copernicus GLO-30 (AWS 2021 release)',
            'surface_type':'DSM — reflective surface, includes vegetation and structures',
            'nominal_resolution_m':30,'vertical_datum':'EGM2008 orthometric height',
            'vertical_accuracy':'Dataset specification: <4 m at 90% confidence; not locally validated',
            'local_accuracy_validated':False,'acquisition':'Primarily 2011–2015; local infill may be older',
            'attribution':COP_NOTICE,'reference':'https://registry.opendata.aws/copernicus-dem/'}
    elif provider=='usgs':
        step=max(10,2*half/500)
        n=math.ceil(2*half/step)+1
        # Export a raster whose centres cover the exact measurement extent.
        pad=2*half/(n-1)/2
        requested=[bounds[0]-pad,bounds[1]-pad,bounds[2]+pad,bounds[3]+pad]
        service='https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer'
        params={'bbox':','.join(map(str,requested)),'bboxSR':crs.split(':')[1],
            'imageSR':crs.split(':')[1],'size':f'{n},{n}','format':'tiff','pixelType':'F32',
            'renderingRule':json.dumps({'rasterFunction':'None'}),'f':'json'}
        info=get(service+'/exportImage?'+urlencode(params))
        if 'error' in info: raise ValueError(str(info['error']))
        local=ROOT/'data/usgs-source.tif';local.write_bytes(get(info['href'],True));sources=[local]
        quality={'dataset':'USGS 3DEP','surface_type':'Bare-earth DEM mosaic',
            'nominal_resolution_m':None,'vertical_datum':'USGS source datum; no vertical conversion applied',
            'vertical_accuracy':'Depends on source survey; not locally validated',
            'local_accuracy_validated':False,'acquisition':'Varies by source tile',
            'attribution':'USGS National Map 3D Elevation Program','reference':service,
            'request':params,'source_note':'10 m target grid; actual source detail varies'}
    else:
        local=Path(c.get('local_dem',''))
        if not local.is_file() or local.suffix.lower() not in ('.tif','.tiff'):
            raise ValueError('Choose a valid local survey GeoTIFF file')
        if c.get('vertical_units')!='metres': raise ValueError('Confirm that local DEM elevations are in metres')
        with rasterio.open(local) as ds:
            if ds.crs is None: raise ValueError('Local DEM needs a CRS')
            pt=Transformer.from_crs(4326,ds.crs,always_xy=True).transform(lon,lat)
            tr=Transformer.from_crs(ds.crs,4326,always_xy=True)
            a=tr.transform(*pt);b=tr.transform(pt[0]+ds.res[0],pt[1]);d=tr.transform(pt[0],pt[1]+ds.res[1])
            geod=Geod(ellps='WGS84');native=max(abs(geod.inv(*a,*b)[2]),abs(geod.inv(*a,*d)[2]))
        step=max(native,2*half/500);sources=[local]
        quality={'dataset':'Local survey DEM: '+local.name,'surface_type':c.get('surface_type','Unspecified local DEM'),
            'nominal_resolution_m':native,'vertical_datum':c.get('vertical_datum') or 'Unspecified — verify before comparing heights',
            'vertical_accuracy':'Refer to survey control and source metadata; not validated by this app',
            'local_accuracy_validated':False,'acquisition':c.get('acquisition_date') or 'Unspecified',
            'attribution':'User-provided local GeoTIFF','reference':'Local source file'}
    grid,transform,spacing,source_info=warp_sources(sources,bounds,crs,step)
    dem=ROOT/'data/elevation.tif'
    # Uncompressed single-band TIFF is read directly by BlenderGIS's FreeImage.
    with rasterio.open(dem,'w',driver='GTiff',height=grid.shape[0],width=grid.shape[1],
        count=1,dtype='float32',crs=crs,transform=transform,nodata=-9999) as ds: ds.write(grid,1)
    quality.update(grid_spacing_m=spacing,grid_samples=list(grid.shape),
        processing='Bilinear metric reprojection only; no terrain smoothing or vertical exaggeration',
        suitability='Regional terrain interpretation. Site operations require suitable survey data and ground validation.')
    try: imagery=fetch_imagery(bounds,crs)
    except Exception as error: imagery={'available':False,'error':str(error),'source':'Esri World Imagery'}
    meta={'place_name':c.get('place_name') or f'{lat:.5f}, {lon:.5f}',
        'provider':provider,'center_lon_lat':[lon,lat],'requested_half_size_m':half,
        'crs':crs,'origin_easting_northing_m':[cx,cy],'bounds_projected_m':bounds,
        'dem_sha256':hashlib.sha256(dem.read_bytes()).hexdigest(),'quality':quality,
        'source_windows':source_info,'imagery':imagery,'prepared_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    (ROOT/'data/prepared.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(f"Prepared {meta['place_name']}: {grid.shape}, {spacing:.2f} m grid; imagery={imagery['available']}",flush=True)

if __name__=='__main__': run()
