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
from .live import (
    LiveDataError, fetch_weather, fetch_firms, fetch_routes, fetch_camera_detections,
    resolve_nws_alerts, resolve_fire_perimeters, resolve_language_demographics, resolve_evac_route,
)

ROOT=Path(__file__).resolve().parents[1]
DB_PATH=Path(os.getenv('PHAROS_DB',str(ROOT/'work'/'pharos.sqlite3')))
DB_PATH.parent.mkdir(parents=True,exist_ok=True)
LOCK=threading.Lock()
app=FastAPI(title='PHAROS',version='0.1.0',description='Synthetic wildfire exercise and open-data adapters. Not an emergency dispatch service.')
origins=[v.strip() for v in os.getenv('PHAROS_ALLOWED_ORIGINS','http://localhost:8000,http://127.0.0.1:8000').split(',') if v.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=['GET','POST'],allow_headers=['Content-Type'])
with sqlite3.connect(DB_PATH) as db:
    db.execute('CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS audit (time TEXT, action TEXT, draft_id TEXT)')

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
    return {'status':'ok','mode':'synthetic exercise','bedrock_configured':bool(os.getenv('BEDROCK_MODEL_ID')),'ntfy_configured':bool(os.getenv('NTFY_TOPIC_URL')),'firms_configured':bool(os.getenv('FIRMS_MAP_KEY'))}

@app.get('/api/scenario')
def scenario(stage: Literal[0,1,2]=0):
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
        if d.get('delivered'): return {'status':d['delivery_status'],'duplicate':True}
        if d.get('sending'): raise HTTPException(409,'Delivery is pending or uncertain; inspect provider before retrying')
        d['sending']=True;save(d)
    topic=os.getenv('NTFY_TOPIC_URL')
    if topic:
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
    return {'status':status,'duplicate':False}

class Broadcast(BaseModel):
    reviewer: str=Field(min_length=1,max_length=80)
    areas: list[str]=Field(min_length=1,max_length=64)
    geoids: list[str]=Field(default_factory=list,max_length=64)
    languages: list[str]=Field(min_length=1,max_length=20)

@app.post('/api/broadcast')
def broadcast(body: Broadcast):
    # Exercise-only: records a reviewed broadcast per area. No real public alerting
    # (no IPAWS/WEA), consistent with the whole prototype's posture.
    if not body.reviewer.strip(): raise HTTPException(400,'Named review is required')
    with LOCK:
        for area in body.areas:
            audit(f'EXERCISE broadcast to {area} in {len(body.languages)} language(s) by {body.reviewer.strip()}')
    return {'status':'Recorded (exercise)','areas':len(body.areas),'languages':body.languages,'public_alert':False}

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
    # Reroutes a real road route around a projected-fire polygon; withholds when unsafe.
    return await resolve_evac_route(body.origin,body.dest,body.avoid)

app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='dashboard')
