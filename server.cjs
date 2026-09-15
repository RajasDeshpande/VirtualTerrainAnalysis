// Dependency-free static HTTP server; serve only the webxr directory.
const http=require('node:http'),https=require('node:https'),fs=require('node:fs'),path=require('node:path');
const {spawn}=require('node:child_process');
const root=path.join(__dirname,'webxr'), reports=[];
const mime={'.css':'text/css; charset=utf-8','.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.json':'application/json','.glb':'model/gltf-binary','.png':'image/png','.jpg':'image/jpeg','.csv':'text/csv; charset=utf-8','.tif':'image/tiff','.woff':'font/woff'};
let activeBuild=null,lastSearch=0;
const searchCache=new Map();
function json(res,value,status=200){res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(value));}
function localPC(req){
  try{return ['127.0.0.1','::1','::ffff:127.0.0.1'].includes(req.socket.remoteAddress)&&
    ['localhost','127.0.0.1','[::1]'].includes(new URL('http://'+req.headers.host).hostname);}catch{return false;}
}
function sameOrigin(req){try{return new URL(req.headers.origin).host===req.headers.host;}catch{return false;}}
function handler(req,res){
  const pathname=new URL(req.url,'http://localhost').pathname;
  if(pathname==='/api/choice'){
    if(!localPC(req))return json(res,{error:'Open the chooser on this PC to build terrain.'},403);
    return json(res,JSON.parse(fs.readFileSync(path.join(__dirname,'data/terrain-choice.json'),'utf8').replace(/^\uFEFF/,'')));
  }
  if(pathname==='/api/search'){
    if(!localPC(req))return json(res,{error:'Place search is available on the PC.'},403);
    const q=new URL(req.url,'http://localhost').searchParams.get('q')?.trim();
    if(!q||q.length>200)return json(res,{error:'Enter a place name (up to 200 characters).'},400);
    if(searchCache.has(q))return json(res,searchCache.get(q));
    if(Date.now()-lastSearch<1100)return json(res,{error:'Wait a second before searching again.'},429);
    lastSearch=Date.now();
    fetch('https://nominatim.openstreetmap.org/search?format=jsonv2&limit=8&q='+encodeURIComponent(q),
      {headers:{'User-Agent':'Vr3dTerrainChooser/2.0 (local BlenderGIS project)'},signal:AbortSignal.timeout(20000)})
      .then(async r=>{if(!r.ok)throw Error('Place search unavailable');return r.json();})
      .then(items=>{const values=items.map(x=>({name:x.display_name,latitude:Number(x.lat),longitude:Number(x.lon)}));searchCache.set(q,values);json(res,values);})
      .catch(e=>json(res,{error:e.message+'; exact coordinates can still be entered.'},502));return;
  }
  if(pathname==='/api/build'){
    if(req.method!=='POST')return json(res,{error:'POST required'},405);
    if(!localPC(req)||!sameOrigin(req))return json(res,{error:'Builds must be requested from the chooser on this PC.'},403);
    if(activeBuild||fs.existsSync(path.join(__dirname,'data/build.lock')))return json(res,{error:'A build is already running.'},409);
    let body='';req.on('data',chunk=>{body+=chunk;if(body.length>16000)req.destroy();});
    req.on('end',()=>{
      try{
        const c=JSON.parse(body);
        if(!Number.isFinite(c.latitude)||!Number.isFinite(c.longitude)||!Number.isFinite(c.half_size_m)||
          c.latitude<=-79.8||c.latitude>=83.8||Math.abs(c.longitude)>=179.8||c.half_size_m<250||c.half_size_m>5000||
          !['auto','copernicus','usgs','local'].includes(c.provider))throw Error('Invalid coordinates, extent or data source.');
        c.place_name=String(c.place_name||`${c.latitude}, ${c.longitude}`).slice(0,250);
        const requestFile=path.join(__dirname,'data/build-request.json');
        fs.writeFileSync(requestFile,JSON.stringify(c,null,2));
        const log=fs.openSync(path.join(__dirname,'logs/last-build.log'),'w');
        activeBuild=spawn(path.join(__dirname,'.venv/Scripts/python.exe'),['tools/build_terrain.py','--choice-file',requestFile],
          {cwd:__dirname,windowsHide:true,stdio:['ignore',log,log],shell:false});
        fs.closeSync(log);
        activeBuild.on('error',error=>{activeBuild=null;fs.writeFileSync(path.join(root,'assets/build-status.json'),JSON.stringify({state:'failed',stage:'Starting Python',error:error.message}));});
        activeBuild.on('exit',code=>{activeBuild=null;if(code){let current={};try{current=JSON.parse(fs.readFileSync(path.join(root,'assets/build-status.json')));}catch{}
          if(current.state!=='failed')fs.writeFileSync(path.join(root,'assets/build-status.json'),JSON.stringify({state:'failed',stage:'Building',error:'Build failed. See logs/last-build.log.'}));}});
        json(res,{state:'starting'},202);
      }catch(error){json(res,{error:error.message},400);}
    });return;
  }
  if(pathname==='/api/runtime'){
    if(req.method==='POST'){
      let body='';req.on('data',chunk=>{body+=chunk;if(body.length>16384)req.destroy();});
      req.on('end',()=>{try{const data=JSON.parse(body);reports.push({time:new Date().toISOString(),browser:req.headers['user-agent'],...data});
        if(reports.length>40)reports.shift();fs.writeFileSync(path.join(__dirname,'logs','browser-runtime.json'),JSON.stringify(reports,null,2));
        res.writeHead(204);res.end();}catch{res.writeHead(400);res.end();}});return;
    }
    res.setHeader('Content-Type','application/json');res.end(JSON.stringify(reports));return;
  }
  if(req.method!=='GET'&&req.method!=='HEAD'){res.writeHead(405);res.end();return;}
  let decoded;try{decoded=decodeURIComponent(pathname);}catch{res.writeHead(400);res.end();return;}
  const file=path.resolve(root,'.'+(decoded==='/'?'/index.html':decoded));
  if(!file.startsWith(root+path.sep)){res.writeHead(403);res.end();return;}
  fs.stat(file,(err,stat)=>{if(err||!stat.isFile()){res.writeHead(404);res.end('Not found');return;}
    res.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');
    res.setHeader('Content-Length',stat.size);res.setHeader('Cache-Control','no-cache');
    res.setHeader('X-Content-Type-Options','nosniff');
    if(req.method==='HEAD'){res.end();return;}fs.createReadStream(file).pipe(res);
  });
}
const port=Number(process.env.PORT||8080);
http.createServer(handler).listen(port,'0.0.0.0',()=>console.log(`Terrain HTTP http://localhost:${port}`));
if(fs.existsSync(path.join(__dirname,'certs','server.key'))){
  https.createServer({key:fs.readFileSync(path.join(__dirname,'certs','server.key')),cert:fs.readFileSync(path.join(__dirname,'certs','server.crt'))},handler)
    .listen(8443,'0.0.0.0',()=>console.log('Terrain HTTPS on port 8443'));
}
