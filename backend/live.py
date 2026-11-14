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
            if getattr(response, 'is_redirect', False):
                # e.g. Census ACS 302 -> missing_key.html when no CENSUS_API_KEY is set.
                raise LiveDataError('Upstream redirected (likely a missing API key)', status=502)
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


# =====================================================================
# Real-world adapters: NWS alerts, NIFC/WFIGS perimeters, Census TIGERweb
# boundaries, Census ACS language demographics. Same live-or-fallback
# contract as above. None of these establish an evacuation order.
# =====================================================================

NWS_ALERTS_URL = 'https://api.weather.gov/alerts/active'
WFIGS_URL = ('https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/'
             'WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query')
TIGERWEB_URL = ('https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/'
                'Places_CouSub_ConCity_SubMCD/MapServer/{layer}/query')
ACS_URL = 'https://api.census.gov/data/2023/acs/acs5'

# ACS table C16001 "Language Spoken at Home" — the per-group total lines only.
# Armenian, Farsi, etc. fall under "Other Indo-European" at this table's grain.
ACS_LANGUAGE_VARS = {
    'C16001_002E': ('en', 'English only'),
    'C16001_003E': ('es', 'Spanish'),
    'C16001_005E': ('fr', 'French / Haitian / Cajun'),
    'C16001_007E': ('de', 'German / other West Germanic'),
    'C16001_009E': ('ru', 'Russian / Polish / other Slavic'),
    'C16001_011E': ('hy', 'Other Indo-European (incl. Armenian, Farsi)'),
    'C16001_013E': ('ko', 'Korean'),
    'C16001_015E': ('zh', 'Chinese (Mandarin / Cantonese)'),
    'C16001_017E': ('vi', 'Vietnamese'),
    'C16001_019E': ('tl', 'Tagalog / Filipino'),
    'C16001_021E': ('as', 'Other Asian / Pacific Island'),
    'C16001_023E': ('ar', 'Arabic'),
    'C16001_025E': ('ot', 'Other / unspecified'),
}


# --- NWS active alerts ---

async def fetch_nws_alerts(area=None, point=None, event=None):
    params = {}
    if area:
        params['area'] = area
    if point:
        params['point'] = point
    if event:
        params['event'] = event
    ua = os.getenv('NWS_USER_AGENT', 'PHAROS-wildfire-exercise (set NWS_USER_AGENT to your contact)')
    try:
        async with httpx.AsyncClient(timeout=15, headers={'User-Agent': ua, 'Accept': 'application/geo+json'}) as client:
            response = await client.get(NWS_ALERTS_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        raise LiveDataError('NWS alerts unavailable; no substitute alerts returned', status=502)
    features = data.get('features', []) if isinstance(data, dict) else []
    return {
        'source': 'NWS / api.weather.gov', 'retrieved_at': _now(), 'data_source': 'live',
        'alerts': features, 'count': len(features), 'is_evacuation_order': False,
        'note': 'Fire-weather and other NWS products. NOT a civil evacuation order.',
    }


def _synthetic_alerts():
    return [{'properties': {
        'event': 'Red Flag Warning', 'severity': 'Severe', 'certainty': 'Likely',
        'areaDesc': 'Scenario foothills zone', 'headline': 'EXERCISE — Red Flag Warning (synthetic fixture)',
        'synthetic': True}}]


async def resolve_nws_alerts(area=None, point=None, event=None):
    try:
        return await fetch_nws_alerts(area, point, event)
    except LiveDataError as exc:
        features = _synthetic_alerts()
        return {
            'source': 'NWS (synthetic fallback)', 'retrieved_at': _now(), 'data_source': 'synthetic-fallback',
            'fallback_reason': str(exc), 'alerts': features, 'count': len(features), 'is_evacuation_order': False,
            'note': 'Synthetic fire-weather fixture. NOT a civil evacuation order.',
        }


# --- NIFC / WFIGS active fire perimeters ---

async def fetch_fire_perimeters(where='1=1', out_fields='attr_IncidentName,poly_IncidentName,attr_FireDiscoveryDateTime', limit=50):
    data = await _get_json(WFIGS_URL, {'where': where, 'outFields': out_fields, 'outSR': '4326', 'f': 'geojson', 'resultRecordCount': limit})
    if not isinstance(data, dict) or 'error' in data or data.get('type') != 'FeatureCollection':
        raise LiveDataError('Fire perimeter service returned no usable data', status=502)
    features = data.get('features', [])
    return {
        'source': 'NIFC WFIGS Interagency Perimeters (Current)', 'retrieved_at': _now(), 'data_source': 'live',
        'perimeters': features, 'count': len(features), 'authoritative': True, 'is_live_perimeter': True,
    }


def _synthetic_perimeter():
    ring = [[-118.25, 34.205], [-118.215, 34.205], [-118.205, 34.235], [-118.245, 34.245], [-118.25, 34.205]]
    return [{'type': 'Feature', 'properties': {'IncidentName': 'Scenario Fire (synthetic)', 'synthetic': True},
             'geometry': {'type': 'Polygon', 'coordinates': [ring]}}]


async def resolve_fire_perimeters(where='1=1', limit=50):
    try:
        return await fetch_fire_perimeters(where=where, limit=limit)
    except LiveDataError as exc:
        features = _synthetic_perimeter()
        return {
            'source': 'NIFC WFIGS (synthetic fallback)', 'retrieved_at': _now(), 'data_source': 'synthetic-fallback',
            'fallback_reason': str(exc), 'perimeters': features, 'count': len(features),
            'authoritative': False, 'is_live_perimeter': False,
        }


# --- Census TIGERweb administrative boundaries ---

async def fetch_place_boundaries(state_fips='06', layer=26, where=None, out_fields='NAME,GEOID'):
    url = TIGERWEB_URL.format(layer=layer)
    params = {'where': where or f"STATE='{state_fips}'", 'outFields': out_fields, 'outSR': '4326', 'f': 'geojson'}
    data = await _get_json(url, params)
    if not isinstance(data, dict) or 'error' in data or data.get('type') != 'FeatureCollection':
        raise LiveDataError('TIGERweb returned no usable boundary data', status=502)
    features = data.get('features', [])
    return {'source': 'US Census TIGERweb', 'retrieved_at': _now(), 'data_source': 'live', 'boundaries': features, 'count': len(features)}


async def resolve_place_boundaries(state_fips='06', layer=26, where=None):
    try:
        return await fetch_place_boundaries(state_fips=state_fips, layer=layer, where=where)
    except LiveDataError as exc:
        return {'source': 'US Census TIGERweb (synthetic fallback)', 'retrieved_at': _now(),
                'data_source': 'synthetic-fallback', 'fallback_reason': str(exc), 'boundaries': [], 'count': 0}


# --- Census ACS language demographics ---

def _parse_acs_languages(data):
    header, row = data[0], data[1]
    values = dict(zip(header, row))
    total = float(values.get('C16001_001E') or 0) or 1.0
    langs = []
    for var, (code, label) in ACS_LANGUAGE_VARS.items():
        count = values.get(var)
        if count in (None, '', '-', '-666666666'):
            continue
        share = round(float(count) / total, 4)
        if share > 0:
            langs.append({'code': code, 'label': label, 'share': share})
    langs.sort(key=lambda item: item['share'], reverse=True)
    return langs, int(total)


async def fetch_language_demographics(geoid):
    if not geoid or len(geoid) < 7:
        raise LiveDataError('A 7-digit place GEOID is required', status=400)
    state_fips, place = geoid[:2], geoid[2:7]
    variables = ['NAME', 'C16001_001E'] + list(ACS_LANGUAGE_VARS.keys())
    params = {'get': ','.join(variables), 'for': f'place:{place}', 'in': f'state:{state_fips}'}
    key = os.getenv('CENSUS_API_KEY')
    if key:
        params['key'] = key
    data = await _get_json(ACS_URL, params)
    if not isinstance(data, list) or len(data) < 2:
        raise LiveDataError('ACS returned no usable demographics', status=502)
    languages, population = _parse_acs_languages(data)
    return {
        'source': 'US Census ACS 5-year (table C16001)', 'vintage': '2023', 'retrieved_at': _now(),
        'data_source': 'live', 'is_estimate': True, 'geoid': geoid, 'population_5plus': population, 'languages': languages,
    }


def _synthetic_languages():
    return [
        {'code': 'en', 'label': 'English only', 'share': 0.52},
        {'code': 'es', 'label': 'Spanish', 'share': 0.28},
        {'code': 'zh', 'label': 'Chinese (Mandarin / Cantonese)', 'share': 0.07},
        {'code': 'hy', 'label': 'Other Indo-European (incl. Armenian, Farsi)', 'share': 0.05},
        {'code': 'tl', 'label': 'Tagalog / Filipino', 'share': 0.04},
        {'code': 'ko', 'label': 'Korean', 'share': 0.025},
        {'code': 'vi', 'label': 'Vietnamese', 'share': 0.015},
    ]


async def resolve_language_demographics(geoid=None, stage=0):
    try:
        return await fetch_language_demographics(geoid)
    except LiveDataError as exc:
        return {
            'source': 'US Census ACS (synthetic fallback)', 'vintage': '2023', 'retrieved_at': _now(),
            'data_source': 'synthetic-fallback', 'fallback_reason': str(exc), 'is_estimate': True,
            'geoid': geoid, 'population_5plus': 24000, 'languages': _synthetic_languages(),
        }
