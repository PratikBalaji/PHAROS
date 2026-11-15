import {hazards,checkRoutes} from './core.js';
export function hideBasemapLabel(layer){return layer.type==='symbol'&&!/^(place_country|place_state|place_city_r)/.test(layer.id);}
export const project=([x,y])=>[-118.23+(x-400)*.00035,34.22-(y-220)*.00025];
export function overlayData(stage){return {hazards:{type:'FeatureCollection',features:hazards(stage).map(c=>({type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[Array.from({length:73},(_,i)=>project([c.x+Math.cos(i/72*Math.PI*2)*c.r,c.y+Math.sin(i/72*Math.PI*2)*c.r]))]}}))},routes:{type:'FeatureCollection',features:checkRoutes(stage).map(r=>({type:'Feature',properties:{id:r.id,blocked:r.blocked},geometry:{type:'LineString',coordinates:r.points.map(project)}}))}};}
const SIM_LAYERS=['sim-projected-fill','sim-projected-line','sim-fire-glow','sim-alts-line','sim-blocked-line','sim-eta','sim-route-old-line','sim-route-glow','sim-route-line','sim-vehicle-halo','sim-vehicle-arrow','sim-vehicle-dot','sim-assembly-dot','sim-assembly-label'];
const EMPTY={type:'FeatureCollection',features:[]};
let map,loaded=false,current={stage:0,layer:'all',selectedRoute:'B'};
export function updateMap(state){current=state;if(!loaded)return;const replay=state.mapMode!=='live';const data=overlayData(state.stage);for(const key of ['hazards','routes'])map.getSource('pharos-'+key)?.setData(data[key]);for(const id of ['route-line','route-glow','hazard-fill','hazard-core','incident-points','incident-labels'])if(map.getLayer(id))map.setLayoutProperty(id,'visibility',replay?'visible':'none');for(const id of ['district-fill','district-line','district-label','perimeter-fill','perimeter-line','fire-extrusion','buildings-3d',...SIM_LAYERS])if(map.getLayer(id))map.setLayoutProperty(id,'visibility',replay?'none':'visible');for(const id of ['evac-glow','evac-line'])if(map.getLayer(id))map.setLayoutProperty(id,'visibility','none');const fc=f=>f?(f.type==='FeatureCollection'?f:{type:'FeatureCollection',features:[f]}):{type:'FeatureCollection',features:[]};if(map.getSource('pharos-districts')){const sel=new Set(state.selectedAreas||[]);map.getSource('pharos-districts').setData({type:'FeatureCollection',features:(state.districts||[]).map(f=>({type:'Feature',properties:{GEOID:f.properties.GEOID,name:f.properties.name,kind:f.properties.kind,selected:sel.has(f.properties.GEOID)},geometry:f.geometry}))});}if(state.perimeters&&map.getSource('pharos-perimeters'))map.getSource('pharos-perimeters').setData(state.perimeters);}
export function zoomMap(delta){if(map)map.easeTo({zoom:map.getZoom()+delta,duration:300});}
export function frameRoute(coords){if(!map||!coords||!coords.length)return;const lons=coords.map(c=>c[0]),lats=coords.map(c=>c[1]);const bounds=[[Math.min(...lons),Math.min(...lats)],[Math.max(...lons),Math.max(...lats)]];try{const cam=map.cameraForBounds(bounds,{padding:{top:130,bottom:150,left:430,right:400}});if(!cam)throw 0;map.easeTo({center:cam.center,zoom:Math.min(cam.zoom,14),pitch:56,bearing:-15,duration:1500});}catch(e){map.easeTo({center:[(Math.min(...lons)+Math.max(...lons))/2,(Math.min(...lats)+Math.max(...lats))/2],zoom:12.6,pitch:56,bearing:-15,duration:1500});}}
export function initializeMap(onRoute,onDistrict){if(!globalThis.maplibregl)return;try{map=new maplibregl.Map({container:'maplibre-canvas',style:'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',center:project([390,240]),zoom:13.3,pitch:55,bearing:-17,maxPitch:80,attributionControl:{compact:true},maxZoom:18,minZoom:9});map.on('style.load',()=>{for(const layer of map.getStyle().layers){if(hideBasemapLabel(layer))map.setLayoutProperty(layer.id,'visibility','none');}const d=overlayData(current.stage);for(const key of ['hazards','routes'])map.addSource('pharos-'+key,{type:'geojson',data:d[key]});map.addLayer({id:'hazard-fill',type:'fill',source:'pharos-hazards',paint:{'fill-color':'#eb835d','fill-opacity':.13,'fill-antialias':true}});map.addLayer({id:'hazard-core',type:'fill',source:'pharos-hazards',paint:{'fill-color':'#e56d49','fill-opacity':.035}});for(const [id,width,opacity,blur] of [['route-glow',11,.12,5],['route-line',3,.85,0]])map.addLayer({id,type:'line',source:'pharos-routes',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':['case',['get','blocked'],'#cf876b','#9bc9b8'],'line-width':width,'line-opacity':opacity,'line-blur':blur}});map.addSource('pharos-districts',{type:'geojson',data:{type:'FeatureCollection',features:[]}});map.addLayer({id:'district-fill',type:'fill',source:'pharos-districts',paint:{'fill-color':['case',['get','selected'],'#9bc9b8','#6f8ba0'],'fill-opacity':['case',['get','selected'],.3,.07]}});map.addLayer({id:'district-line',type:'line',source:'pharos-districts',paint:{'line-color':['case',['get','selected'],'#bfe3d4','#8094a6'],'line-width':['case',['get','selected'],2.2,.8],'line-opacity':.9}});map.addLayer({id:'district-label',type:'symbol',source:'pharos-districts',layout:{'text-field':['get','name'],'text-font':['Open Sans Regular'],'text-size':10,'text-letter-spacing':.06},paint:{'text-color':'#c3d2cc','text-halo-color':'#111718','text-halo-width':1.6}});map.addSource('pharos-perimeters',{type:'geojson',data:{type:'FeatureCollection',features:[]}});map.addLayer({id:'perimeter-fill',type:'fill',source:'pharos-perimeters',paint:{'fill-color':'#e4552e','fill-opacity':.22}});map.addLayer({id:'perimeter-line',type:'line',source:'pharos-perimeters',paint:{'line-color':'#ff7847','line-width':1.6,'line-dasharray':[2,1.5]}});map.addSource('pharos-points',{type:'geojson',data:{type:'FeatureCollection',features:[['OBSERVATION / 07',[450,215],'#f3946c'],['REVIEW ORIGIN',[350,270],'#b6ccc5'],['NORTH ASSEMBLY',[650,150],'#8baba0'],['SOUTH ASSEMBLY',[620,345],'#8baba0']].map(([label,p,color])=>({type:'Feature',properties:{label,color},geometry:{type:'Point',coordinates:project(p)}}))}});map.addLayer({id:'incident-points',type:'circle',source:'pharos-points',paint:{'circle-radius':4,'circle-color':['get','color'],'circle-stroke-width':4,'circle-stroke-color':'rgba(20,26,27,.7)'}});map.addLayer({id:'incident-labels',type:'symbol',source:'pharos-points',layout:{'text-field':['get','label'],'text-font':['Open Sans Regular'],'text-size':10,'text-offset':[0,1.5],'text-anchor':'top','text-letter-spacing':.12},paint:{'text-color':'#a3b4af','text-halo-color':'#111718','text-halo-width':2}});try{map.addSource('terrain-dem',{type:'raster-dem',tiles:['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],encoding:'terrarium',tileSize:256,maxzoom:14});map.setTerrain({source:'terrain-dem',exaggeration:1.4});}catch(e){}try{map.setSky({'sky-color':'#0a131b','horizon-color':'#223440','fog-color':'#0d1113','sky-horizon-blend':.6,'horizon-fog-blend':.55,'fog-ground-blend':.4,'atmosphere-blend':['interpolate',['linear'],['zoom'],8,.7,13,.25]});}catch(e){}try{const vs=Object.keys(map.getStyle().sources).find(id=>map.getStyle().sources[id].type==='vector');if(vs)map.addLayer({id:'buildings-3d',type:'fill-extrusion',source:vs,'source-layer':'building',minzoom:13,paint:{'fill-extrusion-color':['interpolate',['linear'],['coalesce',['get','render_height'],['get','height'],8],0,'#19242e',60,'#28333d',220,'#39505f'],'fill-extrusion-height':['interpolate',['linear'],['zoom'],13,0,15,['coalesce',['get','render_height'],['get','height'],8]],'fill-extrusion-base':['coalesce',['get','render_min_height'],0],'fill-extrusion-opacity':.85}});}catch(e){}map.addSource('pharos-fire',{type:'geojson',data:{type:'FeatureCollection',features:[]}});map.addLayer({id:'fire-extrusion',type:'fill-extrusion',source:'pharos-fire',paint:{'fill-extrusion-color':['interpolate',['linear'],['get','heat'],1,'#ffd27a',3,'#ff8a3c',6,'#e4381f',10,'#9e1a0f'],'fill-extrusion-height':['min',['*',['get','heat'],11],130],'fill-extrusion-base':0,'fill-extrusion-opacity':.8}});map.addSource('pharos-evac',{type:'geojson',data:{type:'FeatureCollection',features:[]}});map.addLayer({id:'evac-glow',type:'line',source:'pharos-evac',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#8fd0ff','line-width':14,'line-opacity':.16,'line-blur':6}});map.addLayer({id:'evac-line',type:'line',source:'pharos-evac',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#cdeaff','line-width':4.5,'line-opacity':.96}});try{for(const id of ['route-line','route-glow','hazard-fill','hazard-core'])map.setLayoutProperty(id,'visibility','none');}catch(e){}addSimLayers();loaded=true;document.body.classList.remove('map-unavailable');document.body.classList.add('map-ready');updateMap(current);if(current.mapMode!=='live')focusReplay();});map.on('click','route-line',e=>onRoute(e.features[0].properties.id));map.on('click','district-fill',e=>{if(onDistrict)onDistrict(e.features[0].properties.GEOID);});map.on('mouseenter','district-fill',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','district-fill',()=>map.getCanvas().style.cursor='');map.on('mouseenter','route-line',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','route-line',()=>map.getCanvas().style.cursor='');map.on('mousemove',e=>{const target=document.querySelector('#coordinates');if(target)target.textContent=`${e.lngLat.lat.toFixed(4)}° N  ${Math.abs(e.lngLat.lng).toFixed(4)}° W`;});map.on('error',()=>{if(!loaded)document.body.classList.add('map-unavailable');});}catch{document.body.classList.add('map-unavailable');}}

export function focusReplay(){if(map)map.easeTo({center:project([440,270]),zoom:13,pitch:0,bearing:0,duration:600});}

// ---------------------------------------------------------------------------------------------
// Live-run layers (fire glow, alternatives, risk-coloured route, vehicle). All ids start with sim-.
// ---------------------------------------------------------------------------------------------
const RISK_COLORS=['#22d3ee','#ffb020','#ff4d3d'];

function addSimLayers(){
  const src=(id,extra={})=>map.addSource(id,{type:'geojson',data:EMPTY,...extra});
  src('sim-fire-pts');src('sim-projected');src('sim-alts');src('sim-blocked');src('sim-eta');src('sim-route-old');src('sim-assembly');
  src('sim-route',{lineMetrics:true});src('sim-vehicle');src('sim-arrow');
  const before=map.getLayer('fire-extrusion')?'fire-extrusion':undefined;
  map.addLayer({id:'sim-fire-glow',type:'heatmap',source:'sim-fire-pts',paint:{
    'heatmap-weight':['interpolate',['linear'],['get','heat'],1,.35,10,1],
    'heatmap-intensity':['interpolate',['linear'],['zoom'],10,.8,15,1.6],
    'heatmap-radius':['interpolate',['exponential',2],['zoom'],10,5,13,22,15,70,17,160],
    'heatmap-color':['interpolate',['linear'],['heatmap-density'],0,'rgba(255,90,20,0)',.25,'rgba(255,120,40,.30)',.55,'rgba(255,90,30,.55)',.8,'rgba(255,170,70,.75)',1,'rgba(255,235,170,.9)'],
    'heatmap-opacity':.95}},before);
  map.addLayer({id:'sim-projected-fill',type:'fill',source:'sim-projected',paint:{'fill-color':'#ff5a4d','fill-opacity':.09}},before);
  map.addLayer({id:'sim-projected-line',type:'line',source:'sim-projected',paint:{'line-color':'#ff7a6b','line-width':1.4,'line-opacity':.75,'line-dasharray':[2,2]}},before);
  map.addLayer({id:'sim-alts-line',type:'line',source:'sim-alts',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#7e8d99','line-width':4,'line-opacity':.55}});
  map.addLayer({id:'sim-blocked-line',type:'line',source:'sim-blocked',layout:{'line-cap':'butt'},paint:{'line-color':'#ff5a4d','line-width':4.5,'line-opacity':.95,'line-dasharray':[1.1,1.1]}});
  map.addLayer({id:'sim-route-old-line',type:'line',source:'sim-route-old',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#9fb3c0','line-width':5,'line-opacity':0}});
  map.addLayer({id:'sim-route-glow',type:'line',source:'sim-route',layout:{'line-cap':'round','line-join':'round'},paint:{'line-color':'#38d9ff','line-width':14,'line-opacity':.2,'line-blur':7}});
  map.addLayer({id:'sim-route-line',type:'line',source:'sim-route',layout:{'line-cap':'round','line-join':'round'},paint:{'line-width':6,'line-opacity':1,'line-gradient':['interpolate',['linear'],['line-progress'],0,RISK_COLORS[0],1,RISK_COLORS[0]]}});
  map.addLayer({id:'sim-eta',type:'symbol',source:'sim-eta',layout:{'text-field':['get','label'],'text-font':['Open Sans Regular'],'text-size':11,'text-allow-overlap':false,'text-padding':4},paint:{'text-color':['case',['get','chosen'],'#d9f6ff','#aab7c0'],'text-halo-color':'#0b1114','text-halo-width':2}});
  map.addLayer({id:'sim-assembly-dot',type:'circle',source:'sim-assembly',paint:{
    'circle-radius':['case',['==',['get','state'],'target'],8,['==',['get','state'],'lost'],6,5],
    'circle-color':['match',['get','state'],'target','#5fe0a7','lost','#ff5a4d','#7e8d99'],
    'circle-stroke-width':['case',['==',['get','state'],'target'],4,2],'circle-stroke-color':'rgba(10,16,18,.75)'}});
  map.addLayer({id:'sim-assembly-label',type:'symbol',source:'sim-assembly',layout:{'text-field':['get','name'],'text-font':['Open Sans Regular'],'text-size':10,'text-offset':[0,1.3],'text-anchor':'top','text-letter-spacing':.04,'text-optional':true},paint:{'text-color':['match',['get','state'],'target','#c8f4df','lost','#ff9a90','#8d9aa5'],'text-halo-color':'#0b1114','text-halo-width':2}});
  map.addLayer({id:'sim-vehicle-halo',type:'circle',source:'sim-vehicle',paint:{'circle-radius':18,'circle-color':'#38d9ff','circle-opacity':.22,'circle-blur':.6}});
  map.addLayer({id:'sim-vehicle-arrow',type:'fill',source:'sim-arrow',paint:{'fill-color':'#ffffff','fill-opacity':.95,'fill-outline-color':'#38d9ff'}});
  map.addLayer({id:'sim-vehicle-dot',type:'circle',source:'sim-vehicle',paint:{'circle-radius':6,'circle-color':'#ffffff','circle-stroke-width':3,'circle-stroke-color':'#19c5ff'}});
}

let ambientTimer=null,fadeFrame=0;
function startAmbient(){
  if(ambientTimer)return;
  ambientTimer=setInterval(()=>{
    if(!map||!loaded||document.hidden||current.mapMode!=='live')return;
    const t=performance.now()/1000;
    if(map.getLayer('fire-extrusion'))map.setPaintProperty('fire-extrusion','fill-extrusion-opacity',.74+.1*Math.sin(t*5.1)+.05*Math.sin(t*11.3));
    if(map.getLayer('sim-route-glow'))map.setPaintProperty('sim-route-glow','line-width',13+4*Math.sin(t*2.4));
    if(map.getLayer('sim-vehicle-halo'))map.setPaintProperty('sim-vehicle-halo','circle-radius',16+5*Math.sin(t*3));
  },110);
}

const asFC=f=>!f?EMPTY:(f.type==='FeatureCollection'?f:{type:'FeatureCollection',features:[f]});
const setData=(id,data)=>{const s=map.getSource(id);if(s)s.setData(data);};

// Push new data into the live-run layers. Every key is optional; only supplied keys change.
export function setSim(d){
  if(!map||!loaded)return;
  startAmbient();
  if('fire' in d)setData('pharos-fire',d.fire||EMPTY);
  if('firePts' in d)setData('sim-fire-pts',d.firePts||EMPTY);
  if('projected' in d)setData('sim-projected',asFC(d.projected));
  if('alts' in d)setData('sim-alts',asFC(d.alts));
  if('blocked' in d)setData('sim-blocked',asFC(d.blocked));
  if('eta' in d)setData('sim-eta',asFC(d.eta));
  if('assembly' in d)setData('sim-assembly',asFC(d.assembly));
  if('vehicle' in d){setData('sim-vehicle',d.vehicle?asFC(d.vehicle):EMPTY);setData('sim-arrow',d.arrow?asFC(d.arrow):EMPTY);}
  if('route' in d){
    setData('sim-route',asFC(d.route));
    if(d.routeStops&&d.routeStops.length>1&&map.getLayer('sim-route-line')){
      const expr=['interpolate',['linear'],['line-progress']];
      let last=-1;
      for(const [p,level] of d.routeStops){const pp=Math.max(p,last+1e-4);expr.push(Math.min(pp,1),RISK_COLORS[level]||RISK_COLORS[0]);last=pp;}
      try{map.setPaintProperty('sim-route-line','line-gradient',expr);}catch(e){}
    }
  }
}

// Cross-fade from the previous route to the new one so a reroute is easy to see.
export function swapRoute(oldRoute,newRoute,ms=900){
  if(!map||!loaded)return;
  cancelAnimationFrame(fadeFrame);
  setData('sim-route-old',asFC(oldRoute));
  setData('sim-route',asFC(newRoute));
  if(!oldRoute){map.setPaintProperty('sim-route-line','line-opacity',1);return;}
  const t0=performance.now();
  const step=now=>{
    const k=Math.min(1,(now-t0)/ms);
    if(map.getLayer('sim-route-old-line'))map.setPaintProperty('sim-route-old-line','line-opacity',.7*(1-k));
    if(map.getLayer('sim-route-line'))map.setPaintProperty('sim-route-line','line-opacity',.25+.75*k);
    if(k<1)fadeFrame=requestAnimationFrame(step);
  };
  fadeFrame=requestAnimationFrame(step);
}

export function clearSim(){
  if(!map||!loaded)return;
  cancelAnimationFrame(fadeFrame);
  for(const id of ['pharos-fire','sim-fire-pts','sim-projected','sim-alts','sim-blocked','sim-eta','sim-route-old','sim-route','sim-vehicle','sim-arrow','sim-assembly'])setData(id,EMPTY);
}

export function followVehicle(point,bearing){
  if(!map||!point)return;
  map.easeTo({center:point,bearing,pitch:62,zoom:Math.max(map.getZoom(),14),duration:650,easing:t=>t});
}

export function fitTo(coords,{padding,pitch=56,bearing=-15,maxZoom=14,duration=1400}={}){
  if(!map||!coords||!coords.length)return;
  const lons=coords.map(c=>c[0]),lats=coords.map(c=>c[1]);
  const bounds=[[Math.min(...lons),Math.min(...lats)],[Math.max(...lons),Math.max(...lats)]];
  const cam=map.cameraForBounds(bounds,{padding:padding||{top:120,bottom:170,left:340,right:380}});
  if(cam)map.easeTo({center:cam.center,zoom:Math.min(cam.zoom,maxZoom),pitch,bearing,duration});
}
