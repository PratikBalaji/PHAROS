"""Single-operator prototype API. Bind to loopback; protect any remote deployment."""
import asyncio
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .core import create_draft, tool_result, check_routes
from .broadcast import build_plan
from . import gemini, langplan
from .photon import delivery_config, send_photon, refresh_photon, PhotonError
from .twilio_wa import send_twilio, refresh_twilio
from .resend_email import send_resend, refresh_resend
from .photon_imessage import send_imessage
from .ntfy import send_ntfy
from uuid import uuid4
from .live import (
    LiveDataError, fetch_weather, fetch_firms, fetch_routes, fetch_camera_detections,
    resolve_nws_alerts, resolve_fire_perimeters, resolve_language_demographics, resolve_evac_route,
)

ROOT=Path(__file__).resolve().parents[1]
# Vercel's application bundle is read-only. Its /tmp storage is ephemeral.
DEFAULT_DB=Path('/tmp/pharos/pharos.sqlite3') if os.getenv('VERCEL') else ROOT/'work'/'pharos.sqlite3'
DB_PATH=Path(os.getenv('PHAROS_DB',str(DEFAULT_DB)))
DB_PATH.parent.mkdir(parents=True,exist_ok=True)
LOCK=threading.Lock()
app=FastAPI(title='PHAROS',version='0.1.0',description='Synthetic wildfire exercise and open-data adapters. Not an emergency dispatch service.')
origins=[v.strip() for v in os.getenv('PHAROS_ALLOWED_ORIGINS','http://localhost:8000,http://127.0.0.1:8000').split(',') if v.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=['GET','POST'],allow_headers=['Content-Type'])
with sqlite3.connect(DB_PATH) as db:
    db.execute('CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS audit (time TEXT, action TEXT, draft_id TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS broadcasts (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS sms_sends (request_id TEXT NOT NULL, code TEXT NOT NULL, state TEXT NOT NULL, status TEXT, receipt TEXT, PRIMARY KEY (request_id, code))')

def save(d):
    with sqlite3.connect(DB_PATH) as db: db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?)',(d['id'],json.dumps(d)))
def audit(action,draft_id=''):
    with sqlite3.connect(DB_PATH) as db: db.execute('INSERT INTO audit VALUES (?,?,?)',(datetime.now(timezone.utc).isoformat(),action,draft_id))
def get_draft(draft_id):
    with sqlite3.connect(DB_PATH) as db: row=db.execute('SELECT payload FROM drafts WHERE id=?',(draft_id,)).fetchone()
    if not row: raise HTTPException(404,'Draft not found')
    return json.loads(row[0])
def fresh(d,stage):
    if d['stage']!=stage: raise HTTPException(409,'Scenario changed; regenerate the draft')
    if datetime.now(timezone.utc)-datetime.fromisoformat(d['created_at'])>timedelta(minutes=15): raise HTTPException(409,'Draft expired; regenerate and review current evidence')

class DraftRequest(BaseModel): stage: Literal[0,1,2]=0
class Approval(DraftRequest):
    reviewer: str=Field(min_length=1,max_length=80)
    text: str=Field(min_length=20,max_length=4000)
    reviewed: bool

@app.get('/api/health')
def health():
    return {'status':'ok','mode':'synthetic exercise','storage':'ephemeral-instance' if os.getenv('VERCEL') else 'local-sqlite','bedrock_configured':bool(os.getenv('BEDROCK_MODEL_ID')),'ntfy_configured':bool(os.getenv('NTFY_TOPIC_URL')),'firms_configured':bool(os.getenv('FIRMS_MAP_KEY')),'delivery':delivery_config(),'gemini_configured':gemini.configured(),'ors_configured':bool(os.getenv('ORS_API_KEY'))}

@app.get('/api/scenario')
def scenario(stage: int=Query(0,ge=0,le=2)):
    return {'evidence':tool_result('get_incident_evidence',stage),'routes':check_routes(stage)}

@app.post('/api/drafts')
async def draft(body: DraftRequest):
    d=create_draft(body.stage)
    if os.getenv('BEDROCK_MODEL_ID'):
        try:
            from .bedrock import generate_brief
            d.update(await asyncio.to_thread(generate_brief,body.stage))
        except Exception:
            # Avoid returning credentials or raw upstream errors. No silent fabricated AI fallback.
            raise HTTPException(502,'Bedrock drafting failed. Check server credentials, model access, and model tool support, or unset BEDROCK_MODEL_ID to use the labeled template.')
    save(d);audit('Draft created with '+d['engine'],d['id']);return d

@app.post('/api/drafts/{draft_id}/approve')
def approve(draft_id: str,body: Approval):
    with LOCK:
        d=get_draft(draft_id);fresh(d,body.stage)
        if d.get('delivered') or d.get('sending'): raise HTTPException(409,'Already delivered or sending; create a new draft')
        if not body.reviewed or not body.reviewer.strip(): raise HTTPException(400,'Named review is required')
        if not body.text.startswith('EXERCISE ONLY'): raise HTTPException(400,'Exercise label must be preserved')
        d.update(text=body.text,reviewer=body.reviewer.strip(),approved=True,approved_at=datetime.now(timezone.utc).isoformat())
        save(d);audit('Approved by '+d['reviewer'],draft_id);return {'approved':True}

@app.post('/api/drafts/{draft_id}/send')
async def send(draft_id: str,body: DraftRequest):
    with LOCK:
        d=get_draft(draft_id);fresh(d,body.stage)
        if not d['approved']: raise HTTPException(409,'Review and approve the draft first')
        if d.get('delivered'): return {'status':d['delivery_status'],'delivery':d.get('delivery'),'duplicate':True}
        if d.get('sending'): raise HTTPException(409,'Delivery is pending or uncertain; inspect provider before retrying')
        channel=delivery_config()
        if not channel['configured']: raise HTTPException(503,'Delivery is not configured. Check the Integrations panel for missing server settings.')
        d['sending']=True;save(d)
    topic=os.getenv('NTFY_TOPIC_URL')
    if channel['provider']=='photon':
        try:
            d['delivery']=await send_photon(d['text'],'pharos-draft-'+d['id'])
            status=d['delivery']['status']
        except PhotonError as e:
            if not e.uncertain: d['sending']=False;save(d)
            audit('Photon delivery uncertain; automatic resend blocked' if e.uncertain else 'Photon request rejected; no delivery recorded',draft_id)
            raise HTTPException(502,str(e)) from None
    elif channel['provider'] in ('twilio_whatsapp','twilio_sms','resend_email','photon_imessage'):
        d['sending']=False;save(d);raise HTTPException(409,'Console-only delivery is available from the Console, not this draft route')
    elif channel['provider']=='ntfy':
        parsed=urlparse(topic)
        if parsed.scheme!='https' or not parsed.netloc:
            d['sending']=False;save(d);raise HTTPException(503,'Configure an HTTPS ntfy topic URL')
        headers={'Title':'PHAROS exercise notification','Tags':'test_tube','Content-Type':'text/plain; charset=utf-8'}
        if os.getenv('NTFY_TOKEN'): headers['Authorization']='Bearer '+os.environ['NTFY_TOKEN']
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                r=await client.post(topic,content=d['text'].encode('utf-8'),headers=headers)
                r.raise_for_status()
        except httpx.HTTPError:
            audit('Delivery uncertain; automatic resend blocked',draft_id)
            raise HTTPException(502,'Notification status is uncertain. Check the ntfy topic before attempting another delivery; automatic resend is blocked.')
        status='Accepted by ntfy; device receipt unverified'
    else: status='Recorded in backend test inbox'
    d.update(delivered=True,sending=False,delivery_status=status);save(d);audit(status,draft_id)
    return {'status':status,'delivery':d.get('delivery'),'duplicate':False}

@app.get('/api/drafts/{draft_id}/delivery')
async def delivery_receipt(draft_id: str):
    d=get_draft(draft_id)
    if d.get('delivery',{}).get('provider')!='photon': raise HTTPException(409,'No Photon receipt exists for this draft')
    try: d['delivery']=await refresh_photon(d['delivery'])
    except PhotonError as e: raise HTTPException(502,str(e)) from None
    d['delivery_status']=d['delivery']['status'];save(d)
    return {'status':d['delivery_status'],'delivery':d['delivery']}

class Broadcast(BaseModel):
    reviewer: str=Field(min_length=1,max_length=80)
    geoids: list[str]=Field(min_length=1,max_length=64)
    mode: Literal['auto','all']='auto'
    reviewed: bool

@app.post('/api/broadcast')
def broadcast(body: Broadcast):
    if not body.reviewed or not body.reviewer.strip(): raise HTTPException(400,'Named exercise review is required')
    try: plan=build_plan(body.geoids,body.mode)
    except ValueError as e: raise HTTPException(422,str(e))
    record={'id':str(uuid4()),'created_at':datetime.now(timezone.utc).isoformat(),'reviewer':body.reviewer.strip(),'plan':plan,'public_alert':False,'status':'Recorded in backend exercise log'}
    with LOCK:
        with sqlite3.connect(DB_PATH) as db: db.execute('INSERT INTO broadcasts VALUES (?,?)',(record['id'],json.dumps(record)))
        audit(f"EXERCISE bundle {record['id']}: {plan['message_count']} messages across {len(plan['areas'])} areas reviewed by {record['reviewer']}")
    return record

@app.get('/api/broadcasts/{broadcast_id}')
def get_broadcast(broadcast_id: str):
    with sqlite3.connect(DB_PATH) as db: row=db.execute('SELECT payload FROM broadcasts WHERE id=?',(broadcast_id,)).fetchone()
    if not row: raise HTTPException(404,'Bundle not found')
    return json.loads(row[0])

class LanguagePlanRequest(BaseModel):
    geoid: str=Field(min_length=3,max_length=40)

@app.post('/api/console/language-plan')
async def console_language_plan(body: LanguagePlanRequest):
    # Gemini chooses the send languages from the district's demographic split; a share-based
    # rule is the labeled fallback. Nothing is sent here.
    try: return await langplan.resolve_language_plan(body.geoid)
    except ValueError as e: raise HTTPException(422,str(e))

class TranslateRequest(BaseModel):
    geoid: str=Field(min_length=3,max_length=40)
    languages: list[str]=Field(min_length=1,max_length=9)
    context: str|None=Field(default=None,max_length=200)

@app.post('/api/console/translate')
async def console_translate(body: TranslateRequest):
    # Gemini drafts the message in every language (English included); the server adds the fixed exercise marker
    # and flags review. Fixed templates are only a labeled fallback when Gemini is unavailable.
    try: return await langplan.resolve_translations(body.geoid,body.languages,body.context)
    except ValueError as e: raise HTTPException(422,str(e))

class ConsoleSms(BaseModel):
    request_id: str=Field(min_length=8,max_length=64,pattern=r'^[A-Za-z0-9_-]+$')
    geoid: str=Field(min_length=3,max_length=40)
    reviewer: str=Field(min_length=1,max_length=80)
    reviewed: bool
    texts: dict[str,str]=Field(min_length=1,max_length=9)

def sms_result(code,row):
    receipt=json.loads(row[2]) if row[2] else {}
    state=row[0]
    return {'code':code,'state':state,'status':'Delivery status uncertain; inspect Photon before retrying' if state=='sending' else row[1],'message_id':receipt.get('message_id'),'provider_status':receipt.get('provider_status')}

PACING={'twilio_whatsapp':3.2,'twilio_sms':3.2,'resend_email':0.6,'photon_imessage':1.0,'ntfy':0.3}  # seconds between sends
def sender_for(provider):
    # looked up at call time so tests and hot-swaps see the current function
    return {'photon':send_photon,'twilio_whatsapp':send_twilio,'twilio_sms':send_twilio,'resend_email':send_resend,'photon_imessage':send_imessage,'ntfy':send_ntfy}.get(provider)

async def deliver_texts(request_id,texts,channel):
    # One idempotent send per (request_id, key). A key is a language code, or 'strategy'.
    results=[]
    for n,(code,text) in enumerate(texts.items()):
        if n and channel['provider'] in PACING: await asyncio.sleep(PACING[channel['provider']])  # provider rate limits
        with LOCK:
            with sqlite3.connect(DB_PATH) as db:
                row=db.execute('SELECT state,status,receipt FROM sms_sends WHERE request_id=? AND code=?',(request_id,code)).fetchone()
                if not row: db.execute('INSERT INTO sms_sends (request_id,code,state) VALUES (?,?,?)',(request_id,code,'sending'))
        if row: results.append({**sms_result(code,row),'duplicate':True}); continue
        receipt=None
        if sender_for(channel['provider']):
            try:
                receipt=await sender_for(channel['provider'])(text,f'pharos-sms-{request_id}-{code}')
                state,status='submitted',receipt['status']
            except PhotonError as e:
                if e.uncertain: state,status='uncertain',f'Delivery status uncertain; automatic resend blocked. Reason: {e}'
                else:
                    state,status='rejected',str(e)
                    with sqlite3.connect(DB_PATH) as db: db.execute('DELETE FROM sms_sends WHERE request_id=? AND code=?',(request_id,code))
        else: state,status='recorded','Recorded in backend test inbox'
        if state!='rejected':
            with sqlite3.connect(DB_PATH) as db: db.execute('UPDATE sms_sends SET state=?,status=?,receipt=? WHERE request_id=? AND code=?',(state,status,json.dumps(receipt) if receipt else None,request_id,code))
        results.append({'code':code,'state':state,'status':status,'message_id':(receipt or {}).get('message_id'),'provider_status':(receipt or {}).get('provider_status'),'duplicate':False})
    return results

@app.post('/api/console/send-sms')
async def console_send_sms(body: ConsoleSms):
    # Exercise only. Texts each reviewed, marker-prefixed version to the single configured SMS
    # conversation (a stand-in for the district). One SMS per language, idempotent per request.
    if not body.reviewed or not body.reviewer.strip(): raise HTTPException(400,'Named exercise review is required')
    try: props=langplan.district(body.geoid)
    except ValueError as e: raise HTTPException(422,str(e))
    cat=langplan.catalogue()
    for code,text in body.texts.items():
        if code not in cat['templates'] or not text.startswith(langplan.marker(code,cat)) or props['name'] not in text or len(text)>1000:
            raise HTTPException(400,'Each message must keep its exercise marker and name the district')
    channel=delivery_config()
    if not channel['configured']: raise HTTPException(503,'Delivery is not configured. Check the Integrations panel for missing server settings.')
    if channel['provider'] not in ('photon','photon_imessage','twilio_whatsapp','twilio_sms','resend_email','ntfy','inbox'): raise HTTPException(409,'Console messages require the photon, photon_imessage, twilio_whatsapp, twilio_sms, resend_email, ntfy or inbox delivery provider')
    results=await deliver_texts(body.request_id,body.texts,channel)
    counts={k:sum(1 for r in results if r['state']==k) for k in ('submitted','recorded','uncertain','rejected','sending')}
    audit(f"EXERCISE SMS {body.request_id} for {props['name']}: {len(results)} language(s), {counts['submitted']} submitted, {counts['recorded']} recorded, {counts['uncertain']+counts['sending']} uncertain, {counts['rejected']} rejected; reviewed by {body.reviewer.strip()}")
    return {'request_id':body.request_id,'geoid':body.geoid,'name':props['name'],'channel':channel['provider'],'public_alert':False,'recipient':'configured test conversation (stands in for the district)','results':results,'counts':counts}

class StrategyFacts(BaseModel):
    run_name: str=Field(min_length=1,max_length=60,pattern=r"^[A-Za-z0-9 \-']+$")
    outcome: Literal['arrived','rerouted','driving','withheld']
    assembly: str|None=Field(default=None,max_length=60,pattern=r"^[A-Za-z0-9 \-'.]+$")
    minutes: int|None=Field(default=None,ge=1,le=600)
    km: float|None=Field(default=None,ge=0,le=500)

def check_facts(f):
    if f.outcome!='withheld' and (not f.assembly or f.minutes is None or f.km is None): raise HTTPException(422,'This outcome needs assembly, minutes and km')
    return f.model_dump()

class StrategyPlanRequest(BaseModel):
    geoid: str=Field(min_length=3,max_length=40)
    facts: StrategyFacts

@app.post('/api/console/strategy-plan')
async def console_strategy_plan(body: StrategyPlanRequest):
    # Drafts the strategy text from the planner's facts; Gemini only rephrases. Nothing is sent.
    facts=check_facts(body.facts)
    try: return await langplan.resolve_strategy(body.geoid,facts)
    except ValueError as e: raise HTTPException(422,str(e))

class StrategySms(BaseModel):
    request_id: str=Field(min_length=8,max_length=64,pattern=r'^[A-Za-z0-9_-]+$')
    geoid: str=Field(min_length=3,max_length=40)
    reviewer: str=Field(min_length=1,max_length=80)
    reviewed: bool
    facts: StrategyFacts
    text: str=Field(min_length=20,max_length=langplan.STRATEGY_MAX)

@app.post('/api/console/strategy-sms')
async def console_strategy_sms(body: StrategySms):
    if not body.reviewed or not body.reviewer.strip(): raise HTTPException(400,'Named exercise review is required')
    facts=check_facts(body.facts)
    try: props=langplan.district(body.geoid)
    except ValueError as e: raise HTTPException(422,str(e))
    if not langplan.strategy_valid(body.text,props['name'],facts): raise HTTPException(400,'Strategy text must keep the exercise marker, the district name and the planner facts')
    channel=delivery_config()
    if not channel['configured']: raise HTTPException(503,'Delivery is not configured. Check the Integrations panel for missing server settings.')
    if channel['provider'] not in ('photon','photon_imessage','twilio_whatsapp','twilio_sms','resend_email','ntfy','inbox'): raise HTTPException(409,'Console messages require the photon, photon_imessage, twilio_whatsapp, twilio_sms, resend_email, ntfy or inbox delivery provider')
    results=await deliver_texts(body.request_id,{'strategy':body.text},channel)
    r=results[0]
    audit(f"EXERCISE STRATEGY SMS {body.request_id} for {props['name']} ({facts['outcome']}): {r['state']}; reviewed by {body.reviewer.strip()}")
    return {'request_id':body.request_id,'geoid':body.geoid,'name':props['name'],'channel':channel['provider'],'public_alert':False,'result':r}

@app.get('/api/console/sms-status')
async def console_sms_status(ids: str=Query(min_length=1,max_length=2000)):
    # Stateless Photon receipt refresh, so receipts survive ephemeral storage.
    if delivery_config()['provider']=='ntfy': return {'receipts':[{'message_id':i.strip(),'provider_status':'published','status':'ntfy does not report device receipts; confirm on the phone'} for i in ids.split(',') if i.strip()][:40]}
    out=[]
    for mid in list(dict.fromkeys(i.strip() for i in ids.split(',') if i.strip()))[:40]:
        try:
            r=await refresh_twilio(mid) if mid[:2] in ('SM','MM') else await refresh_resend(mid) if len(mid)==36 and '-' in mid else await refresh_photon({'project_id':os.environ.get('PHOTON_PROJECT_ID'),'message_id':mid})
            out.append({'message_id':mid,'provider_status':r['provider_status'],'status':r['status']})
        except PhotonError as e: out.append({'message_id':mid,'error':str(e)})
    return {'receipts':out}

@app.get('/api/audit')
def audit_rows():
    with sqlite3.connect(DB_PATH) as db: rows=db.execute('SELECT time,action,draft_id FROM audit ORDER BY rowid DESC LIMIT 100').fetchall()
    return [{'time':r[0],'action':r[1],'draft_id':r[2]} for r in rows]

# Live open-data adapters. These REST routes surface live sources directly and
# return an error when a configured source is unavailable; the MCP server wraps
# the same fetchers with a labeled synthetic fallback (see backend/live.py).

@app.get('/api/live/weather')
async def weather(latitude: float=Query(ge=-90,le=90),longitude: float=Query(ge=-180,le=180)):
    try: return await fetch_weather(latitude,longitude)
    except LiveDataError as e: raise HTTPException(e.status,str(e))

@app.get('/api/live/firms')
async def firms(west: float=Query(ge=-180,le=180),south: float=Query(ge=-90,le=90),east: float=Query(ge=-180,le=180),north: float=Query(ge=-90,le=90)):
    try: return await fetch_firms(west,south,east,north)
    except LiveDataError as e: raise HTTPException(e.status,str(e))

@app.get('/api/live/routes')
async def routes(start_lon: float=Query(ge=-180,le=180),start_lat: float=Query(ge=-90,le=90),end_lon: float=Query(ge=-180,le=180),end_lat: float=Query(ge=-90,le=90)):
    try: return await fetch_routes(start_lon,start_lat,end_lon,end_lat)
    except LiveDataError as e: raise HTTPException(e.status,str(e))

@app.get('/api/live/camera')
async def camera():
    try: return await fetch_camera_detections()
    except LiveDataError as e: raise HTTPException(e.status,str(e))

# These use the live-or-synthetic resolvers so the console always renders something
# labeled, even when a source is unreachable. None asserts an evacuation order.

@app.get('/api/live/alerts')
async def alerts(area: str='', point: str='', event: str=''):
    return await resolve_nws_alerts(area or None, point or None, event or None)

@app.get('/api/live/perimeters')
async def perimeters(where: str='1=1', limit: int=Query(50,ge=1,le=500)):
    return await resolve_fire_perimeters(where=where,limit=limit)

@app.get('/api/live/demographics')
async def demographics(geoid: str=Query(min_length=7,max_length=10)):
    return await resolve_language_demographics(geoid=geoid)

class EvacRequest(BaseModel):
    origin: list[float]=Field(min_length=2,max_length=2)
    dest: list[float]=Field(min_length=2,max_length=2)
    avoid: dict|None=None

@app.post('/api/evac-route')
async def evac_route(body: EvacRequest):
    # Reroutes a real road route around a projected-fire hazard (Polygon or MultiPolygon);
    # withholds when unsafe. The response lists every candidate with its geometry and safe flag.
    avoid=body.avoid
    if avoid is not None:
        polys=avoid.get('coordinates') if isinstance(avoid,dict) else None
        if not isinstance(avoid,dict) or avoid.get('type') not in ('Polygon','MultiPolygon') or not isinstance(polys,list) or not polys: raise HTTPException(422,'avoid must be a GeoJSON Polygon or MultiPolygon')
        if avoid['type']=='MultiPolygon' and len(polys)>2000: raise HTTPException(422,'avoid has too many polygons')
    return await resolve_evac_route(body.origin,body.dest,avoid)

# API-only bundles may omit frontend assets; API startup must still succeed.
if (ROOT/'dist').is_dir():
    app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='dashboard')
