/* A-Frame owns rendering and XR sessions. No external locomotion plugins. */
const state = {loaded:false, scale:0.01, display:'slope', errors:[], actions:{teleports:0, moves:0, turns:0}};
function report(event, extra={}) {
  fetch('/api/runtime', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({event, secure:window.isSecureContext, loaded:state.loaded,
      immersive:!!document.querySelector('a-scene')?.is('vr-mode'), ...extra})}).catch(()=>{});
}
function fail(message) {
  state.errors.push(String(message)); document.getElementById('error').textContent=String(message);
  report('error',{message:String(message)});
}
window.addEventListener('error', e=>fail(e.message));
window.addEventListener('unhandledrejection',e=>fail(e.reason?.message || e.reason));

AFRAME.registerComponent('terrain-app', {
  init() {
    const scene=this.el, terrain=document.getElementById('terrain');
    this.stats=null; this.points=[]; this.originalMaterials=new Map(); this.elevationMaterials=new Map();
    this.base='assets/';
    terrain.addEventListener('model-error',()=>fail('Terrain GLB could not load. Check the server and assets/terrain.glb.'));
    terrain.addEventListener('model-loaded',()=>{
      let triangles=0, meshes=0; const materials=new Set();
      terrain.getObject3D('mesh').traverse(o=>{if(o.isMesh){this.originalMaterials.set(o,o.material);meshes++; triangles+=(o.geometry.index?.count || o.geometry.attributes.position.count)/3;
        (Array.isArray(o.material)?o.material:[o.material]).forEach(m=>materials.add(m.name));}});
      state.loaded=true; state.model={meshes,triangles,materials:[...materials]};
      this.setMode(state.scale);
      document.getElementById('status').textContent=`Terrain loaded · ${triangles.toLocaleString()} triangles · ${materials.size} slope colors`;
      report('model-loaded',state.model);
      if(this.stats?.imagery?.available)this.loadImagery();
    });
    this.loadBundle();
    const xrText=document.getElementById('xr-status');
    if(!window.isSecureContext){xrText.textContent='VR needs HTTPS or Quest USB localhost forwarding.';report('xr-unavailable',{reason:'insecure-context'});}
    else if(!navigator.xr){xrText.textContent='This browser does not expose WebXR. Desktop preview is available.';report('xr-unavailable',{reason:'no-api'});}
    else navigator.xr.isSessionSupported('immersive-vr').then(supported=>{
      state.xrSupported=supported;
      xrText.textContent=supported?'VR available — use the headset button at the bottom right.':'Desktop preview ready. Open on Quest to test immersive VR.';
      report('xr-capability',{supported});
    }).catch(e=>fail(e.message));
    scene.addEventListener('enter-vr',()=>{
      document.body.classList.add('immersive');
      document.getElementById('legend-vr').object3D.visible=true;
      const session=scene.renderer.xr.getSession();
      report('enter-vr',{actualXRSession:!!session});
      if(session)session.addEventListener('inputsourceschange',()=>report('xr-inputs',{sources:session.inputSources.length}));
    });
    scene.addEventListener('exit-vr',()=>{document.body.classList.remove('immersive');document.getElementById('legend-vr').object3D.visible=false;report('exit-vr');});
    document.getElementById('overview').onclick=()=>this.setMode(this.overviewScale());
    document.getElementById('explore').onclick=()=>this.setMode(1);
    document.getElementById('reset').onclick=()=>this.setMode(state.scale);
    for(const mode of ['imagery','slope','elevation'])document.getElementById('view-'+mode).onclick=()=>this.setDisplay(mode);
    document.getElementById('clear-points').onclick=()=>this.clearPoints();
    scene.addEventListener('renderstart',()=>{
      scene.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1,1.5));
      const canvas=scene.canvas;canvas.tabIndex=0;canvas.setAttribute('aria-label','3D terrain. Drag to look, WASD to fly, click to inspect.');
      canvas.addEventListener('webglcontextlost',()=>fail('Graphics context was lost. Reload this page; the terrain data remains saved.'));
      let start=null;
      canvas.addEventListener('pointerdown',e=>{canvas.focus();start={x:e.clientX,y:e.clientY};});
      canvas.addEventListener('pointerup',e=>{
        if(!start||Math.hypot(e.clientX-start.x,e.clientY-start.y)>5||!state.loaded||scene.is('vr-mode'))return;
        const rect=canvas.getBoundingClientRect(),ray=new THREE.Raycaster();
        ray.setFromCamera(new THREE.Vector2(2*(e.clientX-rect.left)/rect.width-1,1-2*(e.clientY-rect.top)/rect.height),scene.camera);
        const hit=ray.intersectObject(terrain.getObject3D('mesh'),true)[0];if(hit)this.inspect(hit);
      });
    });
  },
  async loadBundle(){
    try{
      const response=await fetch('assets/current.json',{cache:'no-store'});
      if(response.ok){const manifest=await response.json();this.base=manifest.base;}
      const r=await fetch(this.base+'terrain-stats.json');if(!r.ok)throw Error('Statistics unavailable');
      const stats=await r.json();this.stats=stats;
      const name=stats.place_name || 'Selected terrain';document.title=name+' • Terrain analysis';
      document.getElementById('location-name').textContent=name;
      const q=stats.quality||{},im=stats.imagery||{};
      document.getElementById('source-note').textContent=`${q.dataset||stats.source} · ${q.grid_spacing_m?.toFixed(1)||'unknown'} m elevation grid`;
      document.getElementById('quality').textContent=`${q.surface_type||''}. ${q.vertical_datum||'Vertical datum unspecified'}. ${q.vertical_accuracy||'Local accuracy not established'}. ${q.acquisition||''}. ${q.processing||''}`;
      const records=im.source_records||[],atCenter=records.find(x=>x.SRC_DATE2||x.DATE)||{};
      document.getElementById('imagery-quality').textContent=im.available?
        `Imagery: ${im.source}. Export pixels: ${im.export_pixel_spacing_m.toFixed(2)} m. Centre metadata: ${atCenter.SRC_DATE2||atCenter.DATE||'date unknown'}; source resolution ${atCenter.SRC_RES||atCenter.RESOLUTION||'unknown'} m. This imagery detail does not change DEM detail.`:
        'Imagery unavailable: '+(im.error||'not included in this build');
      document.getElementById('summary-stats').textContent=`Elevation ${stats.min_elevation_m.toFixed(1)}–${stats.max_elevation_m.toFixed(1)} m; relief ${stats.elevation_range_m.toFixed(1)} m; average slope ${stats.average_slope_deg.toFixed(1)}°. Footprint ${(stats.horizontal_area_m2/1e6).toFixed(2)} km².`;
      const files={stats:'terrain-stats.json',points:'elevation-samples.csv',slopes:'slope-triangles.csv',dem:'elevation.tif',checks:'verification.json'};
      for(const [id,file]of Object.entries(files))document.getElementById('download-'+id).href=this.base+file;
      document.getElementById('credit').textContent=[q.attribution,im.available?im.attribution:''].filter(Boolean).join(' | ');
      this.makeLegend(stats);
      state.scale=this.overviewScale();
      document.getElementById('terrain').setAttribute('gltf-model','url('+this.base+'terrain.glb)');
    }catch(e){fail(e.message);}
  },
  overviewScale(){return this.stats?24/Math.max(this.stats.export_dimensions_m[0],this.stats.export_dimensions_m[1]):.01;},
  loadImagery(){
    new THREE.TextureLoader().load(this.base+'imagery.jpg',texture=>{
      texture.colorSpace=THREE.SRGBColorSpace;texture.flipY=false;
      texture.anisotropy=Math.min(8,this.el.renderer.capabilities.getMaxAnisotropy());
      this.imageryMaterial=new THREE.MeshBasicMaterial({map:texture});
      document.getElementById('view-imagery').disabled=false;
      this.setDisplay('imagery');
    },undefined,()=>fail('Imagery could not load; slope and elevation views remain available.'));
  },
  setDisplay(mode){
    if(!state.loaded||(mode==='imagery'&&!this.imageryMaterial))return;
    this.originalMaterials.forEach((original,mesh)=>{
      if(mode==='slope')mesh.material=original;
      else if(mode==='imagery')mesh.material=this.imageryMaterial;
      else{
        if(!this.elevationMaterials.has(mesh)){
          const positions=mesh.geometry.attributes.position,colors=new Float32Array(positions.count*3);
          const low=new THREE.Color('#2377c9'),high=new THREE.Color('#f6d875'),color=new THREE.Color();
          const range=this.stats.elevation_range_m||1;
          for(let i=0;i<positions.count;i++){
            color.copy(low).lerp(high,Math.max(0,Math.min(1,positions.getY(i)/range)));color.toArray(colors,i*3);
          }
          mesh.geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
          this.elevationMaterials.set(mesh,new THREE.MeshBasicMaterial({vertexColors:true}));
        }
        mesh.material=this.elevationMaterials.get(mesh);
      }
    });
    state.display=mode;
    for(const value of ['imagery','slope','elevation'])document.getElementById('view-'+value).setAttribute('aria-pressed',String(value===mode));
    document.getElementById('display-note').textContent=mode==='slope'?'Colors show slope steepness, not elevation.':mode==='elevation'?`Blue = ${this.stats.min_elevation_m.toFixed(0)} m; yellow = ${this.stats.max_elevation_m.toFixed(0)} m. Colors show elevation.`:'Real aerial/satellite imagery, draped over the DEM. Images are not live.';
    const title=document.getElementById('vr-legend-title');if(title)title.setAttribute('value',mode==='slope'?'SLOPE (degrees)':mode==='imagery'?'IMAGERY | slope legend below':'ELEVATION | slope legend below');
    report('display-change',{mode});
  },
  clearPoints(){
    for(const point of this.points){point.marker.geometry.dispose();point.marker.material.dispose();point.marker.removeFromParent();}
    this.points=[];document.getElementById('measurement').textContent='No points selected.';
    document.dispatchEvent(new CustomEvent('terrain-point',{detail:null}));
  },
  inspect(hit){
    if(!this.stats?.export_origin_easting_northing_m)return;
    if(this.points.length===2)this.clearPoints();
    const local=document.getElementById('terrain').object3D.worldToLocal(hit.point.clone());
    const origin=this.stats.export_origin_easting_northing_m;
    const east=origin[0]+local.x,north=origin[1]-local.z,elevation=this.stats.export_elevation_offset_m+local.y;
    const epsg=Number(this.stats.crs.split(':')[1]),zone=epsg%100;
    const [lon,lat]=proj4(`+proj=utm +zone=${zone} ${epsg>=32700?'+south':''} +datum=WGS84 +units=m +no_defs`,'EPSG:4326',[east,north]);
    const n=hit.face.normal.clone().applyNormalMatrix(new THREE.Matrix3().getNormalMatrix(hit.object.matrixWorld));
    const slope=THREE.MathUtils.radToDeg(Math.acos(Math.min(1,Math.abs(n.y))));
    const marker=new THREE.Mesh(new THREE.SphereGeometry(state.scale===1?.5:.13,12,8),new THREE.MeshBasicMaterial({color:this.points.length?'#ff9f43':'#ffffff'}));
    marker.position.copy(hit.point);this.el.object3D.add(marker);
    this.points.push({east,north,elevation,slope,lat,lon,marker});
    let text=this.points.map((p,i)=>`${i?'B':'A'}: ${p.elevation.toFixed(1)} m elevation · ${p.slope.toFixed(1)}° slope\n${p.lat.toFixed(6)}, ${p.lon.toFixed(6)}`).join('\n');
    if(this.points.length===2){const[a,b]=this.points,horizontal=Math.hypot(b.east-a.east,b.north-a.north),dz=b.elevation-a.elevation;
      text+=`\nB minus A: ${dz.toFixed(1)} m ${dz>=0?'rise':'drop'}\nHorizontal separation: ${horizontal.toFixed(1)} m\nStraight-line 3D distance: ${Math.hypot(horizontal,dz).toFixed(1)} m (not surface path)`;}
    document.getElementById('measurement').textContent=text;
    document.getElementById('measurement').closest('details').open=true;
    document.dispatchEvent(new CustomEvent('terrain-point',{detail:{lat,lon,elevation,slope,classification:this.stats.classes.find(row=>slope<=row.upper_deg)?.name||'RED'}}));
    report('point-inspected',{count:this.points.length});
  },
  setMode(scale) {
    if(!state.loaded)return;
    state.scale=scale;
    this.clearPoints();
    const terrain=document.getElementById('terrain'); terrain.object3D.scale.setScalar(scale); terrain.object3D.updateMatrixWorld(true);
    const rig=document.getElementById('rig');rig.object3D.rotation.set(0,0,0);
    if(scale===1){
      const ray=new THREE.Raycaster(new THREE.Vector3(0,10000,0),new THREE.Vector3(0,-1,0));
      const hit=ray.intersectObject(terrain.getObject3D('mesh'),true)[0];
      rig.object3D.position.set(0,(hit?.point.y || 0)+3,0);
    }else rig.object3D.position.set(0,Math.max(7,this.stats.export_dimensions_m[2]*scale+3),28);
    const cam=document.getElementById('camera');
    const look=cam.components['look-controls'];
    if(look){look.yawObject.rotation.y=0;look.pitchObject.rotation.x=scale===1?0:-Math.PI/10;}
    const legend=document.getElementById('legend-vr').object3D;
    legend.visible=this.el.is('vr-mode');
    if(scale===1)legend.position.set(-5,rig.object3D.position.y+2,-5);
    else legend.position.set(-18,5,5);
    document.getElementById('right').setAttribute('raycaster','far',scale===1?500:80);
    document.getElementById('scale-label').textContent=scale===1?'Full scale: 1 metre represents 1 metre. Flight navigation.':`Overview: 1 metre represents ${(1/scale).toFixed(1)} metres. No vertical exaggeration.`;
    report('mode-change',{scale});
  },
  makeLegend(stats) {
    const dom=document.getElementById('legend'), vr=document.getElementById('legend-vr');
    const bg=document.createElement('a-plane');bg.setAttribute('width',7);bg.setAttribute('height',3.3);
    bg.setAttribute('material','color: #101c2e; shader: flat; opacity: 0.95');vr.appendChild(bg);
    const title=document.createElement('a-text');title.id='vr-legend-title';title.setAttribute('value','SLOPE (degrees)');title.setAttribute('width',6);
    title.setAttribute('position','-3.1 1.2 0.02');vr.appendChild(title);
    stats.classes.forEach((row,i)=>{
      const label=i===0?'0–10°':i===4?'>45°':`${stats.classes[i-1].upper_deg}–${row.upper_deg}°`;
      const entry=document.createElement('div'),swatch=document.createElement('span');
      swatch.className='swatch';swatch.style.background=row.color;entry.appendChild(swatch);entry.append(`${row.name} = ${label}`);dom.appendChild(entry);
      const square=document.createElement('a-plane');square.setAttribute('width',.23);square.setAttribute('height',.23);
      square.setAttribute('position',`-2.95 ${.65-i*.4} .02`);square.setAttribute('material',`shader: flat; color: ${row.color}`);vr.appendChild(square);
      const text=document.createElement('a-text');text.setAttribute('value',`${row.name} = ${label.replace('°',' deg').replace('–','-')}`);
      text.setAttribute('width',6);text.setAttribute('position',`-2.65 ${.65-i*.4} .02`);vr.appendChild(text);
    });
  }
});

AFRAME.registerComponent('terrain-navigation', {
  init() {
    this.keys=new Set();this.turnReady=true;this.moveReported=false;
    window.addEventListener('keydown',e=>{
      if(!e.target.closest?.('button,a,input,textarea,select,summary,[contenteditable]')){
        this.keys.add(e.code);
        if(['KeyW','KeyA','KeyS','KeyD','KeyQ','KeyE'].includes(e.code)&&!this.keyReported){
          this.keyReported=true;report('keyboard-input',{code:e.code});
        }
      }
    });
    window.addEventListener('keyup',e=>this.keys.delete(e.code));
    window.addEventListener('blur',()=>this.keys.clear());
    document.addEventListener('focusin',()=>this.keys.clear());
    document.addEventListener('visibilitychange',()=>this.keys.clear());
  },
  tick(time,dt) {
    if(!state.loaded||!dt)return;
    const session=this.el.sceneEl.renderer.xr.getSession();
    let x=0,z=0,y=0,turn=0;
    if(session){for(const input of session.inputSources){
      const axes=input.gamepad?.axes;if(!axes)continue;
      const ax=axes.length>=4?axes[2]:axes[0], ay=axes.length>=4?axes[3]:axes[1];
      if(input.handedness==='left'){x=ax||0;z=ay||0;}
      if(input.handedness==='right'){turn=ax||0;y=-(ay||0);}
    }}else{
      x=Number(this.keys.has('KeyD'))-Number(this.keys.has('KeyA'));
      z=Number(this.keys.has('KeyS'))-Number(this.keys.has('KeyW'));
      y=Number(this.keys.has('KeyE'))-Number(this.keys.has('KeyQ'));
    }
    if(Math.abs(turn)<.3)this.turnReady=true;
    if(Math.abs(turn)>.7&&this.turnReady){
      // Rotate about the viewer, including room-scale headset offset.
      const before=new THREE.Vector3();document.getElementById('camera').object3D.getWorldPosition(before);
      this.el.object3D.rotation.y-=Math.sign(turn)*Math.PI/6;this.el.object3D.updateMatrixWorld(true);
      const after=new THREE.Vector3();document.getElementById('camera').object3D.getWorldPosition(after);
      this.el.object3D.position.add(before.sub(after));this.turnReady=false;
      state.actions.turns++;report('snap-turn',{count:state.actions.turns});
    }
    x=Math.abs(x)>.18?x:0;z=Math.abs(z)>.18?z:0;y=Math.abs(y)>.18?y:0;
    if(!x&&!z&&!y)return;
    const camera=this.el.sceneEl.camera, direction=new THREE.Vector3();camera.getWorldDirection(direction);
    direction.y=0;direction.normalize();const right=new THREE.Vector3(-direction.z,0,direction.x);
    const movement=right.multiplyScalar(x).addScaledVector(direction,-z);movement.y=y;
    if(movement.length()>1)movement.normalize();
    const speed=state.scale===1?35:4;
    this.el.object3D.position.addScaledVector(movement,speed*Math.min(dt,50)/1000);
    const terrain=document.getElementById('terrain');
    const position=this.el.object3D.position;
    // Keep flight above the DEM and floor; ray origin is above the highest point.
    const ray=new THREE.Raycaster(new THREE.Vector3(position.x,10000,position.z),new THREE.Vector3(0,-1,0));
    const ground=ray.intersectObject(terrain.getObject3D('mesh'),true)[0];
    position.y=Math.max(position.y,(ground?.point.y||0)+.3);
    if(!this.moveReported){this.moveReported=true;report('navigation-used',{immersive:!!session});}
  }
});

AFRAME.registerComponent('terrain-teleport', {
  init(){this.el.addEventListener('triggerdown',()=>{
    const hit=this.target();if(!hit)return;
    const rig=document.getElementById('rig').object3D, camera=document.getElementById('camera').object3D;
    const head=new THREE.Vector3();camera.getWorldPosition(head);
    rig.position.set(hit.point.x-(head.x-rig.position.x),hit.point.y+.3,hit.point.z-(head.z-rig.position.z));
    state.actions.teleports++;report('teleport',{count:state.actions.teleports});
  });},
  target(){
    const hits=this.el.components.raycaster?.intersections||[];
    const hit=hits[0];if(!hit?.face)return null;
    const normal=hit.face.normal.clone().applyNormalMatrix(new THREE.Matrix3().getNormalMatrix(hit.object.matrixWorld));
    return Math.abs(normal.y)>=Math.cos(Math.PI/4)?hit:null;
  },
  tick(){const marker=document.getElementById('teleport-marker').object3D;
    const hit=this.el.sceneEl.is('vr-mode')?this.target():null;marker.visible=!!hit;
    if(hit)marker.position.copy(hit.point).add(new THREE.Vector3(0,.04,0));}
});
