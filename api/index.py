"""Thin Vercel serverless API for the static deployment.

Vercel serves dist/ statically and rewrites /api/* to this ASGI app. It exposes only the
endpoints the static front-end needs at runtime — evacuation rerouting, fire perimeters, and
weather — reusing the pure httpx-based functions in backend/live.py (no boto3/mcp, to stay well
under Vercel's function size limit). Set ORS_API_KEY in the Vercel project for avoid-polygons
rerouting; without it, routing falls back to keyless OSRM.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from backend.live import LiveDataError, resolve_evac_route, resolve_fire_perimeters, fetch_weather

app = FastAPI(title='PHAROS edge API', description='Serverless routing and live data for the static deploy. Exercise only.')


class EvacRequest(BaseModel):
    origin: list[float] = Field(min_length=2, max_length=2)
    dest: list[float] = Field(min_length=2, max_length=2)
    avoid: dict | None = None


@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': 'vercel-edge', 'ors_configured': bool(os.getenv('ORS_API_KEY'))}


@app.post('/api/evac-route')
async def evac_route(body: EvacRequest):
    return await resolve_evac_route(body.origin, body.dest, body.avoid)


@app.get('/api/live/perimeters')
async def perimeters(where: str = '1=1', limit: int = Query(25, ge=1, le=500)):
    return await resolve_fire_perimeters(where=where, limit=limit)


@app.get('/api/live/weather')
async def weather(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180)):
    try:
        return await fetch_weather(latitude, longitude)
    except LiveDataError as exc:
        raise HTTPException(exc.status, str(exc))
