const $=id=>document.getElementById(id);
let waiting=false,seenRunning=false,oldBuild=null,interval=null;
fetch('/api/choice').then(async r=>{const c=await r.json();if(!r.ok)throw Error(c.error);
  $('name').value=c.place_name;$('lat').value=c.latitude;$('lon').value=c.longitude;
  $('width').value=String(c.half_size_m*2);$('provider').value=['auto','copernicus','usgs','local'].includes(c.provider)?c.provider:'auto';
  $('dem').value=c.local_dem||'';$('datum').value=c.vertical_datum||'';showLocal();
}).catch(e=>$('error').textContent=e.message);
function showLocal(){$('local').style.display=$('provider').value==='local'?'block':'none';}
$('provider').onchange=showLocal;
$('find').onclick=async()=>{
  $('error').textContent='';$('find').disabled=true;
  try{const r=await fetch('/api/search?q='+encodeURIComponent($('search').value)),items=await r.json();if(!r.ok)throw Error(items.error);
    $('results').replaceChildren();if(!items.length)$('error').textContent='No results. Try a broader name or enter coordinates.';
    for(const item of items){const b=document.createElement('button');b.type='button';b.textContent=item.name;
      b.onclick=()=>{$('name').value=item.name;$('lat').value=item.latitude;$('lon').value=item.longitude;$('results').replaceChildren();};$('results').appendChild(b);}
  }catch(e){$('error').textContent=e.message;}finally{$('find').disabled=false;}
};
$('locate').onclick=()=>{if(!navigator.geolocation){$('error').textContent='Device location is unavailable; enter coordinates.';return;}
  navigator.geolocation.getCurrentPosition(p=>{$('lat').value=p.coords.latitude;$('lon').value=p.coords.longitude;
    $('name').value='Area around my selected location';$('location-info').textContent=`Device reports approximately ±${p.coords.accuracy.toFixed(0)} m position accuracy. This is separate from DEM accuracy.`;
  },e=>$('error').textContent=e.message,{enableHighAccuracy:true,timeout:20000,maximumAge:0});};
$('choice').onsubmit=async event=>{
  event.preventDefault();$('error').textContent='';$('open').hidden=true;
  if($('provider').value==='local'&&!$('metres').checked){$('error').textContent='Confirm the local DEM elevation units before building.';return;}
  const c={place_name:$('name').value,latitude:Number($('lat').value),longitude:Number($('lon').value),half_size_m:Number($('width').value)/2,provider:$('provider').value};
  if(c.provider==='local')Object.assign(c,{local_dem:$('dem').value,vertical_datum:$('datum').value,vertical_units:'metres',surface_type:$('surface').value});
  try{const prior=await fetch('assets/build-status.json',{cache:'no-store'});oldBuild=prior.ok?(await prior.json()).id:null;}catch{}
  $('fields').disabled=true;
  try{const r=await fetch('/api/build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(c)}),data=await r.json();if(!r.ok)throw Error(data.error);
    waiting=true;seenRunning=false;$('status').textContent='Starting the build…';interval=setInterval(poll,2000);
  }catch(e){$('error').textContent=e.message;$('fields').disabled=false;}
};
async function poll(){
  try{const r=await fetch('assets/build-status.json',{cache:'no-store'});if(!r.ok)return;const s=await r.json();
    if(s.id===oldBuild&&!seenRunning)return;
    if(s.state==='running')seenRunning=true;
    $('status').textContent=s.stage+'\n'+(s.place_name||'');
    if(s.state==='failed'||s.state==='complete'){
      clearInterval(interval);waiting=false;$('fields').disabled=false;
      if(s.state==='failed')$('error').textContent=s.error;
      else{$('status').textContent='Verified terrain is ready. Elevation, imagery and analysis checks passed.';$('open').hidden=false;}
    }
  }catch(e){$('status').textContent='Waiting for the local server…';}
}
