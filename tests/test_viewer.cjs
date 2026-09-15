// Integration test of the real viewer logic in a DOM with Three.js geometry.
// No browser/driver is controlled and no GPU/XR support is simulated as a pass.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const {JSDOM}=require('../.test-runtime/node_modules/jsdom');
const THREE=require('../.test-runtime/node_modules/three');
const proj4=require('../webxr/js/proj4-2.22.0.js');
const root=path.join(__dirname,'..'),manifest=JSON.parse(fs.readFileSync(path.join(root,'webxr/assets/current.json')));
const base=path.join(root,'webxr',manifest.base),stats=JSON.parse(fs.readFileSync(path.join(base,'terrain-stats.json')));
const dom=new JSDOM(fs.readFileSync(path.join(root,'webxr/index.html'),'utf8'),{url:'http://localhost:8080/',runScripts:'outside-only'});
const window=dom.window,document=window.document,components={},reports=[];
window.THREE=THREE;window.proj4=proj4;window.AFRAME={registerComponent:(name,definition)=>components[name]=definition};
Object.defineProperty(window,'isSecureContext',{value:true});
window.fetch=async url=>{
  if(url==='/api/runtime')return {ok:true};
  const full=path.join(root,'webxr',url);return {ok:fs.existsSync(full),json:async()=>JSON.parse(fs.readFileSync(full))};
};
vm.runInContext(fs.readFileSync(path.join(root,'webxr/js/terrain.js'),'utf8'),dom.getInternalVMContext());
const scene=document.querySelector('a-scene'),terrain=document.getElementById('terrain'),rig=document.getElementById('rig'),camera=document.getElementById('camera');
scene.object3D=new THREE.Scene();scene.is=()=>false;scene.renderer={xr:{getSession:()=>null}};
for(const element of [terrain,rig,camera,document.getElementById('legend-vr'),document.getElementById('teleport-marker')])element.object3D=new THREE.Group();
scene.object3D.add(terrain.object3D,rig.object3D);rig.object3D.add(camera.object3D);
camera.components={'look-controls':{yawObject:new THREE.Group(),pitchObject:new THREE.Group()}};
// Read the actual exported mesh so material and measurement tests use real data.
const raw=fs.readFileSync(path.join(base,'terrain.glb')),length=raw.readUInt32LE(12),doc=JSON.parse(raw.subarray(20,20+length));
const bin=raw.subarray(28+length),group=new THREE.Group();terrain.object3D.add(group);
function accessor(i){const a=doc.accessors[i],v=doc.bufferViews[a.bufferView],n={SCALAR:1,VEC2:2,VEC3:3}[a.type],bytes={5126:4,5125:4,5123:2}[a.componentType],data=[];
  for(let j=0;j<a.count;j++)for(let k=0;k<n;k++){const offset=(v.byteOffset||0)+(a.byteOffset||0)+j*(v.byteStride||n*bytes)+k*bytes;
    data.push(a.componentType===5126?bin.readFloatLE(offset):a.componentType===5125?bin.readUInt32LE(offset):bin.readUInt16LE(offset));}return data;}
for(const p of doc.meshes[0].primitives){const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(accessor(p.attributes.POSITION),3));
  if(p.attributes.TEXCOORD_0!==undefined)g.setAttribute('uv',new THREE.Float32BufferAttribute(accessor(p.attributes.TEXCOORD_0),2));g.setIndex(accessor(p.indices));g.computeVertexNormals();
  const m=new THREE.MeshStandardMaterial();m.name=doc.materials[p.material].name;group.add(new THREE.Mesh(g,m));}
terrain.getObject3D=()=>group;
const app={...components['terrain-app'],el:scene};
app.init();
(async()=>{
  for(let i=0;i<10;i++)await new Promise(resolve=>setImmediate(resolve));
  assert.equal(app.stats.place_name,stats.place_name);assert(document.title.startsWith(stats.place_name));
  assert(!document.body.textContent.includes('Yosemite'),'Stale location label');
  app.loadImagery=()=>{app.imageryMaterial=new THREE.MeshBasicMaterial();};
  terrain.dispatchEvent(new window.Event('model-loaded'));
  assert(document.getElementById('status').textContent.includes(stats.triangles.toLocaleString()));
  document.getElementById('view-imagery').disabled=false;document.getElementById('view-imagery').click();
  assert.equal(document.getElementById('view-imagery').getAttribute('aria-pressed'),'true');
  assert(group.children.every(m=>m.material===app.imageryMaterial));
  document.getElementById('view-elevation').click();assert(group.children.every(m=>m.material.vertexColors));
  document.getElementById('view-slope').click();assert(group.children.every(m=>m.material.name.startsWith('Slope_')));
  document.getElementById('explore').click();assert.equal(terrain.object3D.scale.x,1);
  terrain.object3D.updateMatrixWorld(true);
  const hitAt=(x,z)=>new THREE.Raycaster(new THREE.Vector3(x,10000,z),new THREE.Vector3(0,-1,0)).intersectObject(group,true)[0];
  const a=hitAt(0,0),b=hitAt(100,0);assert(a&&b);app.inspect(a);app.inspect(b);
  assert.equal(app.points.length,2);assert(document.getElementById('measurement').textContent.includes('100.0 m'));
  assert(Math.abs(app.points[0].lat-stats.center_lon_lat[1])<1e-6);assert(Math.abs(app.points[0].lon-stats.center_lon_lat[0])<1e-6);
  const expected=a.point.y+stats.export_elevation_offset_m;assert(Math.abs(app.points[0].elevation-expected)<1e-4);
  document.getElementById('clear-points').click();assert.equal(app.points.length,0);
  document.getElementById('overview').click();assert(terrain.object3D.scale.x<1);
  for(const id of ['stats','points','slopes','dem','checks']){
    const url=new URL(document.getElementById('download-'+id).href);assert(fs.existsSync(path.join(root,'webxr',url.pathname)));}
  fs.writeFileSync(path.join(root,'logs/viewer-logic-tests.json'),JSON.stringify({result:'PASS',tests:['manifest loading','current location title','three material modes','full-scale and fit modes','real mesh raycast','two-point measurements','UTM inverse coordinates','data download paths'],gpu_render_tested:false,quest_tested:false},null,2));
  console.log('PASS: actual viewer logic, material switching, geographic point inspection and downloads');dom.window.close();
})().catch(e=>{console.error(e);dom.window.close();process.exitCode=1;});
