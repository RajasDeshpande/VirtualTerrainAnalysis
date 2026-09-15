/* Presentation for the terrain inspector; all measurements come from terrain.js. */
(() => {
  'use strict';
  const toggle=document.getElementById('toggle-inspector');
  toggle.onclick=()=>{
    const hidden=document.body.classList.toggle('inspector-hidden');
    toggle.setAttribute('aria-expanded',String(!hidden));
    window.dispatchEvent(new Event('resize'));
  };
  document.addEventListener('terrain-point',event=>{
    const point=event.detail;
    document.getElementById('selected-point').textContent=point
      ? `${point.lat.toFixed(6)}, ${point.lon.toFixed(6)}\n${point.elevation.toFixed(1)} m elevation · ${point.slope.toFixed(1)}° slope\n${point.classification} terrain class`
      : 'No point selected';
  });
})();
