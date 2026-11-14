"""Deterministic scenario facts. Coordinates are schematic units, not geography."""
from math import hypot
from uuid import uuid4
from datetime import datetime, timezone

SOURCES = [
    {'id': 'CAM-07', 'type': 'camera', 'observed_at': '14:32:08 PDT', 'value': 'Smoke signal fixture', 'synthetic': True},
    {'id': 'FIRMS-01', 'type': 'satellite', 'observed_at': '14:29:00 PDT', 'value': 'Separate thermal observation fixture; not a fire perimeter', 'synthetic': True},
    {'id': 'WX-01', 'type': 'weather', 'observed_at': '14:30:00 PDT', 'value': 'Wind from NE, 18 km/h', 'synthetic': True},
]
ROUTES = [
    {'id': 'A', 'name': 'Ridge Road', 'destination': 'North assembly point', 'points': [[350,270],[398,250],[440,215],[480,202],[540,190],[590,165],[650,150]]},
    {'id': 'B', 'name': 'Canyon Connector', 'destination': 'South assembly point', 'points': [[350,270],[325,298],[310,330],[360,354],[440,370],[500,365],[560,350],[620,345]]},
]
SOURCE_IDS = [s['id'] for s in SOURCES] + ['HAZARD-SCENARIO', 'ROUTE-FIXTURE']

def hazards(stage):
    return [{'x':450,'y':215,'r':94 if stage else 65}] + ([{'x':500,'y':365,'r':30}] if stage == 2 else [])

def intersects(a,b,c):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((c['x']-a[0])*dx+(c['y']-a[1])*dy)/(dx*dx+dy*dy or 1)))
    return hypot(a[0]+t*dx-c['x'],a[1]+t*dy-c['y']) <= c['r']

def check_routes(stage):
    return [{**r, 'blocked': any(intersects(a,b,c) for a,b in zip(r['points'],r['points'][1:]) for c in hazards(stage)), 'synthetic':True} for r in ROUTES]

def create_draft(stage):
    route=next((r for r in check_routes(stage) if not r['blocked']),None)
    lead='EXERCISE ONLY — PHAROS scenario, Zone 04. A smoke signal and a separate thermal observation are under review. '
    if route:
        summary='Ridge Road intersects the supplied scenario hazard. Canyon Connector passes the geometry check; field conditions remain unverified.'
        text=lead+f"Candidate for operator review: {route['name']} toward {route['destination']}. This candidate passes the supplied scenario geometry check; road conditions and destination availability are unverified. This is not an evacuation order."
    else:
        summary='Both candidates intersect the supplied scenario zones. Route instructions are withheld.'
        text=lead+'No candidate route passes the supplied hazard checks. Route instructions are withheld. Seek verified instructions from the responsible emergency authority. This is not an evacuation order.'
    return {'id':str(uuid4()),'stage':stage,'route_id':route['id'] if route else None,'engine':'Server template','source_ids':SOURCE_IDS,'summary':summary,'text':text,'approved':False,'delivered':False,'created_at':datetime.now(timezone.utc).isoformat()}

def tool_result(name,stage):
    if name=='get_incident_evidence': return {'mode':'synthetic exercise','sources':SOURCES,'limitations':['No confirmed fire perimeter','No verified road status','No verified destination availability']}
    if name=='get_weather_context': return {'source_id':'WX-01','wind_from':'NE','wind_kmh':18,'synthetic':True,'spread_forecast':None}
    if name=='get_candidate_routes': return {'source_id':'ROUTE-FIXTURE','routes':ROUTES,'synthetic':True}
    if name=='check_route_constraints': return {'source_id':'HAZARD-SCENARIO','routes':check_routes(stage),'method':'segment-circle intersection in schematic units','establishes_safety':False}
    raise ValueError('Unknown tool')
