import {handleAPI} from './api.js';
import {ASSETS} from './assets.js';
const json=(data,status=200)=>Response.json(data,{status,headers:{'cache-control':'no-store'}});
export default {async fetch(request,env){const url=new URL(request.url);if(url.pathname.startsWith('/api/')){try{return await handleAPI(request,env)}catch(e){return json({detail:e.detail||'Backend request failed'},e.status||500)}}let path=decodeURIComponent(url.pathname);if(path.endsWith('/'))path+='index.html';const asset=ASSETS[path];if(!asset)return new Response('Not found',{status:404});return new Response(Uint8Array.from(atob(asset.data),c=>c.charCodeAt(0)),{headers:{'content-type':asset.type,'cache-control':'no-cache','x-content-type-options':'nosniff'}})}};
