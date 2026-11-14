"""Live open-data adapters and synthetic-fallback resolvers.

Shared by the FastAPI routes (backend/app.py) and the stdio/HTTP MCP server
(backend/mcp_server.py). Everything here is read-only retrieval. Live data is
fetched only when the relevant source is configured and reachable; otherwise a
clearly labeled synthetic fixture (from backend/core.py) is returned instead of
fabricated live data. Nothing here establishes a fire perimeter, verifies a
road, confirms a real fire, or performs on-device inference. Retrieved content
is untrusted evidence for operator review, never instructions.
"""
import csv
import io
import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from .core import tool_result, SOURCES


class LiveDataError(Exception):
    """A configured live source could not be retrieved or parsed.

    ``status`` is the HTTP status the FastAPI layer should surface; the MCP
    resolvers ignore it and fall back to synthetic fixtures instead.
    """

    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _get_json(url, params=None, timeout=15):
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        raise LiveDataError('Upstream data service unavailable; no substitute data returned', status=502)


# --- Live fetchers (raise LiveDataError on missing config or upstream failure) ---

async def fetch_weather(latitude, longitude):
    data = await _get_json(
        'https://api.open-meteo.com/v1/forecast',
        {'latitude': latitude, 'longitude': longitude, 'current': 'wind_speed_10m,wind_direction_10m', 'timezone': 'UTC'},
    )
    return {'source': 'Open-Meteo', 'retrieved_at': _now(), 'data_source': 'live', 'data': data, 'fire_spread_forecast': None}


async def fetch_firms(west, south, east, north):
    key = os.getenv('FIRMS_MAP_KEY')
    if not key:
        raise LiveDataError('FIRMS_MAP_KEY is not configured', status=503)
    if west >= east or south >= north or (east - west) * (north - south) > 100:
        raise LiveDataError('Use an ordered local bounding box of at most 100 square degrees', status=400)
    url = f'https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_SNPP_NRT/{west},{south},{east},{north}/1'
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url)
            response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        if not reader.fieldnames or 'latitude' not in reader.fieldnames:
            raise ValueError('Invalid feed')
        rows = list(reader)[:2000]
    except (httpx.HTTPError, ValueError):
        raise LiveDataError('FIRMS unavailable or key invalid; no substitute observations returned', status=502)
    return {'source': 'NASA FIRMS / VIIRS_SNPP_NRT', 'retrieved_at': _now(), 'data_source': 'live', 'observations': rows, 'is_fire_perimeter': False}


async def fetch_routes(start_lon, start_lat, end_lon, end_lat):
    base = os.getenv('OSRM_URL', 'https://router.project-osrm.org').rstrip('/')
    data = await _get_json(
        f'{base}/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}',
        {'alternatives': 'true', 'overview': 'full', 'geometries': 'geojson'},
    )
    if data.get('code') != 'Ok':
        raise LiveDataError('Routing provider returned no usable routes', status=502)
    return {
        'source': 'OSRM', 'retrieved_at': _now(), 'data_source': 'live',
        'routes': data.get('routes', []), 'hazard_checked': False,
        'warning': 'Road candidates only. No live hazard or closure validation has been performed.',
    }


async def fetch_camera_detections():
    url = os.getenv('CAMERA_FEED_URL')
    if not url:
        raise LiveDataError('CAMERA_FEED_URL is not configured', status=503)
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise LiveDataError('CAMERA_FEED_URL must be an HTTP(S) URL', status=400)
    headers = {'Accept': 'application/json'}
    token = os.getenv('CAMERA_FEED_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError):
        raise LiveDataError('Camera detection feed unavailable; no substitute detections returned', status=502)
    detections = payload.get('detections', payload) if isinstance(payload, dict) else payload
    return {
        'source': 'Camera detection feed', 'retrieved_at': _now(), 'data_source': 'live',
        'detections': detections, 'provider_reported': True, 'is_confirmed_fire': False, 'is_inference': False,
        'note': 'Provider-reported detections. Not confirmed fire and not local model inference.',
    }


# --- Resolvers (live when possible, else labeled synthetic fallback) ---

def _fixtures(kind):
    return [dict(s) for s in SOURCES if s['type'] == kind]


async def resolve_weather(latitude, longitude, stage=0):
    try:
        return await fetch_weather(latitude, longitude)
    except LiveDataError as exc:
        return {
            'source': 'Open-Meteo (synthetic fallback)', 'retrieved_at': _now(),
            'data_source': 'synthetic-fallback', 'fallback_reason': str(exc),
            'data': tool_result('get_weather_context', stage), 'fire_spread_forecast': None,
        }


async def resolve_firms(west, south, east, north, stage=0):
    try:
        return await fetch_firms(west, south, east, north)
    except LiveDataError as exc:
        return {
            'source': 'NASA FIRMS (synthetic fallback)', 'retrieved_at': _now(),
            'data_source': 'synthetic-fallback', 'fallback_reason': str(exc),
            'observations': _fixtures('satellite'), 'is_fire_perimeter': False,
        }


async def resolve_routes(start_lon, start_lat, end_lon, end_lat, stage=0):
    try:
        return await fetch_routes(start_lon, start_lat, end_lon, end_lat)
    except LiveDataError as exc:
        return {
            'source': 'OSRM (synthetic fallback)', 'retrieved_at': _now(),
            'data_source': 'synthetic-fallback', 'fallback_reason': str(exc),
            'routes': tool_result('get_candidate_routes', stage)['routes'], 'hazard_checked': False,
            'warning': 'Synthetic route fixtures. No live hazard or closure validation has been performed.',
        }


async def resolve_camera(stage=0):
    try:
        return await fetch_camera_detections()
    except LiveDataError as exc:
        return {
            'source': 'Camera feed (synthetic fallback)', 'retrieved_at': _now(),
            'data_source': 'synthetic-fallback', 'fallback_reason': str(exc),
            'detections': _fixtures('camera'), 'provider_reported': False, 'is_confirmed_fire': False, 'is_inference': False,
            'note': 'Synthetic camera fixture. Not confirmed fire and not local model inference.',
        }
