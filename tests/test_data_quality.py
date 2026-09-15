import sys, tempfile, unittest, math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import prepare_data as data
import numpy as np
import rasterio
from rasterio.transform import from_origin

class DataQualityTests(unittest.TestCase):
    def test_input_validation_and_metric_crs(self):
        c={'latitude':34.17,'longitude':77.58,'half_size_m':1000,'provider':'copernicus'}
        self.assertEqual(data.validate_choice(c)[-1],'EPSG:32643')
        self.assertEqual(data.validate_choice({**c,'latitude':-33,'longitude':18})[-1],'EPSG:32734')
        self.assertEqual(data.validate_choice({**c,'latitude':60,'longitude':4})[-1],'EPSG:32632')
        for field,value in [('latitude',float('nan')),('longitude',200),('half_size_m',500000),('provider','gmrt')]:
            with self.assertRaises(ValueError):data.validate_choice({**c,field:value})
    def test_metric_ramp_preserves_elevation_and_extent(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'ramp.tif'
            a=np.fromfunction(lambda y,x:100+x*10,(11,11)).astype('float32')
            with rasterio.open(source,'w',driver='GTiff',width=11,height=11,count=1,
                dtype='float32',crs='EPSG:32643',transform=from_origin(499995,1000105,10,10),nodata=-9999) as ds:ds.write(a,1)
            grid,transform,step,info=data.warp_sources([source],[500000,1000000,500100,1000100],'EPSG:32643',10)
            np.testing.assert_allclose(grid,a,atol=1e-4)
            self.assertEqual(step,10)
            self.assertAlmostEqual(math.degrees(math.atan2(grid[0,1]-grid[0,0],step)),45)
            self.assertAlmostEqual(transform.c+step/2,500000)
            self.assertAlmostEqual(transform.f-step/2,1000100)
    def test_no_data_is_rejected_instead_of_filled(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'hole.tif';a=np.ones((11,11),dtype='float32')*100;a[5,5]=-9999
            with rasterio.open(source,'w',driver='GTiff',width=11,height=11,count=1,dtype='float32',
                crs='EPSG:32643',transform=from_origin(499995,1000105,10,10),nodata=-9999) as ds:ds.write(a,1)
            with self.assertRaisesRegex(ValueError,'incomplete'):
                data.warp_sources([source],[500000,1000000,500100,1000100],'EPSG:32643',10)
    def test_southern_and_western_tiles(self):
        self.assertIn('S34_00_W071_00',data.tile_url(-71,-34))

if __name__=='__main__':unittest.main()
