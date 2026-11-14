// Photon Beta (2.0). Credentials and the destination stay on the server.
const ROOT='https://api.photon.codes/v1/projects/';
const fields=['PHOTON_API_KEY','PHOTON_PROJECT_ID','PHOTON_SENDER_ID','PHOTON_SPACE_ID'];
const id=(value,kind)=>new RegExp(`^pho_${kind}_[0-7][0-9a-hjkmnp-tv-z]{25}$`).test(value||'');
export function photonConfig(env){
 const missing=fields.filter(key=>!env[key]);
 const invalid=[['PHOTON_PROJECT_ID','prj'],['PHOTON_SENDER_ID','usr'],['PHOTON_SPACE_ID','spc']].filter(([key,kind])=>env[key]&&!id(env[key],kind)).map(([key])=>key);
 return {provider:'photon',channel:'sms',configured:!missing.length&&!invalid.length,missing,invalid};
}
export function deliveryConfig(env){
 const provider=env.PHAROS_DELIVERY_PROVIDER|| (fields.some(key=>env[key])?'photon':'inbox');
 if(provider==='photon')return photonConfig(env);
 if(provider==='inbox')return {provider,configured:true,missing:[],invalid:[]};
 return {provider,configured:false,missing:[],invalid:['PHAROS_DELIVERY_PROVIDER']};
}
export class PhotonError extends Error{
 constructor(message,uncertain=false){super(message);this.uncertain=uncertain;this.status=502;this.detail=message;}
}
function config(env){if(!photonConfig(env).configured)throw new PhotonError('Photon SMS is not configured. Set the Photon server secrets and destination IDs.');return ROOT+env.PHOTON_PROJECT_ID;}
async function request(env,url,options={},fetcher=fetch){
 let response;
 try{response=await fetcher(url,{...options,headers:{Authorization:'Bearer '+env.PHOTON_API_KEY,'Content-Type':'application/json',...options.headers},redirect:'error',signal:AbortSignal.timeout(12000)});}catch{throw new PhotonError('Photon request failed. Check the provider before retrying.',options.method==='POST');}
 if(!response.ok)throw new PhotonError(`Photon returned HTTP ${response.status}. Check project access, SMS line and destination setup.`,options.method==='POST'&&(response.status>=500||[408,409].includes(response.status)));
 try{return await response.json();}catch{throw new PhotonError('Photon returned an unreadable response. Check the provider before retrying.',options.method==='POST');}
}
function receipt(message){
 if(!id(message?.id,'msg')||!['dispatched','accepted','delivered','failed'].includes(message.status))throw new PhotonError('Photon returned an unrecognized receipt. Check the provider before retrying.',true);
 return {provider:'photon',message_id:message.id,provider_status:message.status,status:message.status==='delivered'?'Photon reports SMS delivered':message.status==='failed'?'Photon reports SMS delivery failed':'Accepted by Photon; SMS delivery unconfirmed'};
}
export async function sendPhoton(env,text,key,fetcher=fetch){
 const base=config(env);
 const space=await request(env,base+'/spaces/'+env.PHOTON_SPACE_ID,{},fetcher);
 if(space.platform!=='sms')throw new PhotonError('The configured Photon conversation is not an SMS conversation.');
 const message=await request(env,base+'/messages',{method:'POST',headers:{'idempotency-key':key},body:JSON.stringify({senderId:env.PHOTON_SENDER_ID,spaceId:env.PHOTON_SPACE_ID,content:{type:'text',format:'plain',text}})},fetcher);
 return {...receipt(message),project_id:env.PHOTON_PROJECT_ID};
}
export async function refreshPhoton(env,delivery,fetcher=fetch){
 const base=config(env);
 if(delivery.project_id!==env.PHOTON_PROJECT_ID||!id(delivery.message_id,'msg'))throw new PhotonError('The receipt belongs to a different Photon configuration.');
 return {...receipt(await request(env,base+'/messages/'+delivery.message_id,{},fetcher)),project_id:env.PHOTON_PROJECT_ID};
}
