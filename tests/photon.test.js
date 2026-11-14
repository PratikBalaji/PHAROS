import test from 'node:test';
import assert from 'node:assert/strict';
import {deliveryConfig,sendPhoton,refreshPhoton} from '../worker/photon.js';
const suffix='0'.repeat(25)+'1';
const env={PHAROS_DELIVERY_PROVIDER:'photon',PHOTON_API_KEY:'test-only',PHOTON_PROJECT_ID:'pho_prj_'+suffix,PHOTON_SENDER_ID:'pho_usr_'+suffix,PHOTON_SPACE_ID:'pho_spc_'+suffix};
const message={id:'pho_msg_'+suffix,status:'dispatched'};
test('Photon setup never exposes secrets or silently falls back for partial configuration',()=>{
 const result=deliveryConfig({PHOTON_API_KEY:'sensitive'});
 assert.equal(result.provider,'photon');assert.equal(result.configured,false);
 assert.ok(result.missing.includes('PHOTON_SPACE_ID'));assert.ok(!JSON.stringify(result).includes('sensitive'));
 assert.equal(deliveryConfig(env).configured,true);
});
test('Photon checks SMS conversation, uses canonical contract and preserves Unicode',async()=>{
 const calls=[];const text='EXERCISE ONLY · Հայերեն · 中文';
 const result=await sendPhoton(env,text,'draft-key',async(url,options)=>{calls.push({url,options});return Response.json(calls.length===1?{platform:'sms'}:message)});
 assert.equal(calls[0].url,`https://api.photon.codes/v1/projects/${env.PHOTON_PROJECT_ID}/spaces/${env.PHOTON_SPACE_ID}`);
 assert.equal(calls[1].options.headers['idempotency-key'],'draft-key');
 assert.deepEqual(JSON.parse(calls[1].options.body),{senderId:env.PHOTON_SENDER_ID,spaceId:env.PHOTON_SPACE_ID,content:{type:'text',format:'plain',text}});
 assert.equal(result.provider_status,'dispatched');assert.match(result.status,/unconfirmed/);
 const refreshed=await refreshPhoton(env,result,async()=>Response.json({...message,status:'delivered'}));assert.match(refreshed.status,/reports SMS delivered/);
});
test('Photon refuses non-SMS spaces without posting a message',async()=>{
 let calls=0;
 await assert.rejects(()=>sendPhoton(env,'test','key',async()=>{calls++;return Response.json({platform:'imessage'})}),/not an SMS/);
 assert.equal(calls,1);
});
test('Photon distinguishes rejection from ambiguous transmission and hides raw errors',async()=>{
 for(const status of [401,429,503]){
  let calls=0;
  await assert.rejects(()=>sendPhoton(env,'test','key',async()=>++calls===1?Response.json({platform:'sms'}):new Response('secret provider detail',{status})),e=>e.uncertain===(status===503)&&!e.message.includes('secret'));
 }
});
