"""Independent standard-library GLB parser: bounds, indices, colors and slopes."""
import json, struct, math, os
from pathlib import Path
ROOT = Path(os.environ.get('TERRAIN_BUILD_ROOT', Path(__file__).resolve().parents[1]))
raw = (ROOT/'webxr/assets/terrain.glb').read_bytes()
magic, version, size = struct.unpack_from('<4sII',raw)
assert magic == b'glTF' and version == 2 and size == len(raw)
length, kind = struct.unpack_from('<II',raw,12)
assert kind == 0x4E4F534A
doc = json.loads(raw[20:20+length]); start = 20+length
blen,bkind = struct.unpack_from('<II',raw,start)
assert bkind == 0x004E4942
binary = raw[start+8:start+8+blen]
def accessor(i):
    a = doc['accessors'][i]; v = doc['bufferViews'][a['bufferView']]
    fmt = {5126:'f',5125:'I',5123:'H',5121:'B'}[a['componentType']]
    width = {'SCALAR':1,'VEC3':3,'VEC4':4,'VEC2':2}[a['type']]
    fmt = '<'+fmt*width; stride = v.get('byteStride',struct.calcsize(fmt))
    base = v.get('byteOffset',0)+a.get('byteOffset',0)
    return [struct.unpack_from(fmt,binary,base+j*stride) for j in range(a['count'])]
stats = json.loads((ROOT/'webxr/assets/terrain-stats.json').read_text())
assert len(doc['meshes']) == 1 and len(doc.get('nodes',[])) == 1
node = doc['nodes'][0]
assert 'matrix' not in node and node.get('scale',[1,1,1]) == [1,1,1]
assert node.get('rotation',[0,0,0,1]) == [0,0,0,1]
assert node.get('translation',[0,0,0]) == [0,0,0]
counts = {r['name']:0 for r in stats['classes']}
all_points=[]
for p in doc['meshes'][0]['primitives']:
    assert p.get('mode',4)==4
    material=doc['materials'][p['material']]
    name=material['name'].removeprefix('Slope_')
    row=next(r for r in stats['classes'] if r['name']==name)
    col=material['pbrMetallicRoughness']['baseColorFactor']
    expected=[int(row['color'][i:i+2],16)/255 for i in (1,3,5)]
    expected=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in expected]
    assert max(abs(a-b) for a,b in zip(col[:3],expected))<1e-6
    points=accessor(p['attributes']['POSITION']); all_points.extend(points)
    indices=[x[0] for x in accessor(p['indices'])]
    assert len(indices)%3==0 and max(indices)<len(points)
    for i in range(0,len(indices),3):
        a,b,c=[points[k] for k in indices[i:i+3]]
        u=[b[j]-a[j] for j in range(3)]; v=[c[j]-a[j] for j in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        norm=math.sqrt(sum(x*x for x in n)); assert norm>0
        slope=math.degrees(math.acos(min(1,abs(n[1])/norm)))
        upper=row['upper_deg']; idx=stats['classes'].index(row)
        lower=0 if idx==0 else stats['classes'][idx-1]['upper_deg']
        assert lower-.002<=slope<=upper+.002,(name,slope)
        counts[name]+=1
for row in stats['classes']: assert counts[row['name']]==row['triangles']
assert sum(counts.values())==stats['triangles']
report=dict(result='PASS',file_bytes=len(raw),triangles=sum(counts.values()),
    class_triangles=counts,checks=['GLB container','all index bounds','five material colors',
    'every triangle slope matches its exported class','identity transform','Y-up orientation'],
    bounds_min=[min(p[j] for p in all_points) for j in range(3)],
    bounds_max=[max(p[j] for p in all_points) for j in range(3)])
(ROOT/'logs/glb-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
