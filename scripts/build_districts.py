#!/usr/bin/env python3
"""Build dist/data/districts.json: real municipality/district boundaries (US Census
TIGERweb) + language demographics for a curated LA/Angeles-foothills set.

- Boundaries are REAL (TIGERweb), simplified server-side to keep the file small.
- Demographics are REAL when CENSUS_API_KEY is set (ACS 5-year table C16001);
  otherwise clearly-labeled ILLUSTRATIVE splits so the console still demonstrates
  per-district language targeting. Re-run with a key to replace them with real data.
- If TIGERweb is unreachable, falls back to approximate bounding-box polygons so the
  dataset always builds and the UI always loads.

Usage:  python scripts/build_districts.py
Key:    export CENSUS_API_KEY=xxxxx   (free: https://api.census.gov/data/key_signup.html)
"""
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.live import ACS_LANGUAGE_VARS, ACS_URL  # noqa: E402  (reuse the variable map)

TIGERWEB = ('https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/'
            'Places_CouSub_ConCity_SubMCD/MapServer/{layer}/query')
STATE_FIPS = '06'  # California
SIMPLIFY = 0.0006  # degrees (~60m) server-side generalization

# Curated set: (basename, TIGERweb layer, kind, approx population, illustrative split).
# municipality = incorporated city (layer 4); district = census-designated place (layer 5).
# Illustrative splits reflect well-known community composition but are NOT exact ACS
# figures; they are replaced by real ACS data when CENSUS_API_KEY is set.
CURATED = [
    ('Pasadena', 4, 'municipality', 138000, {'en': .58, 'es': .22, 'zh': .08, 'hy': .04, 'tl': .03, 'ko': .02, 'vi': .01, 'ot': .02}),
    ('Glendale', 4, 'municipality', 196000, {'en': .38, 'hy': .34, 'es': .12, 'ko': .04, 'ru': .03, 'zh': .03, 'tl': .02, 'ot': .04}),
    ('Sierra Madre', 4, 'municipality', 11000, {'en': .80, 'es': .07, 'zh': .05, 'ot': .08}),
    ('La Cañada Flintridge', 4, 'municipality', 20000, {'en': .62, 'ko': .14, 'zh': .10, 'hy': .06, 'es': .04, 'ot': .04}),
    ('Arcadia', 4, 'municipality', 56000, {'en': .42, 'zh': .44, 'es': .05, 'ko': .03, 'ot': .06}),
    ('Monrovia', 4, 'municipality', 37000, {'en': .64, 'es': .26, 'zh': .04, 'tl': .02, 'ot': .04}),
    ('Altadena', 5, 'district', 42000, {'en': .68, 'es': .18, 'zh': .03, 'tl': .03, 'hy': .02, 'ot': .06}),
    ('La Crescenta-Montrose', 5, 'district', 20000, {'en': .55, 'hy': .18, 'ko': .12, 'es': .06, 'zh': .05, 'ot': .04}),
]

LABELS = {code: label for code, label in
          [(c, l) for c, l in [(v[0], v[1]) for v in ACS_LANGUAGE_VARS.values()]]}
LABELS.setdefault('ru', 'Russian / Polish / other Slavic')


def _round_geom(geom):
    def r(x):
        return round(x, 5)

    def walk(coords):
        if coords and isinstance(coords[0], (int, float)):
            return [r(coords[0]), r(coords[1])]
        return [walk(c) for c in coords]

    geom['coordinates'] = walk(geom['coordinates'])
    return geom


def fetch_boundary(basename, layer):
    url = TIGERWEB.format(layer=layer)
    params = {'where': f"BASENAME='{basename}' AND STATE='{STATE_FIPS}'",
              'outFields': 'NAME,GEOID,BASENAME,INTPTLAT,INTPTLON', 'outSR': '4326',
              'maxAllowableOffset': SIMPLIFY, 'f': 'geojson'}
    r = httpx.get(url, params=params, timeout=30)
    r.raise_for_status()
    feats = r.json().get('features', [])
    if not feats:
        raise RuntimeError(f'no TIGERweb feature for {basename}')
    return feats[0]


def fetch_acs_languages(geoid, key):
    state, place = geoid[:2], geoid[2:7]
    variables = ['NAME', 'C16001_001E'] + list(ACS_LANGUAGE_VARS.keys())
    params = {'get': ','.join(variables), 'for': f'place:{place}', 'in': f'state:{state}', 'key': key}
    r = httpx.get(ACS_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
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


def illustrative_languages(split):
    return sorted(
        [{'code': c, 'label': LABELS.get(c, c), 'share': round(s, 4)} for c, s in split.items()],
        key=lambda item: item['share'], reverse=True,
    )


def bbox_polygon(lat, lon, dlat=0.02, dlon=0.025):
    return {'type': 'Polygon', 'coordinates': [[
        [round(lon - dlon, 5), round(lat - dlat, 5)], [round(lon + dlon, 5), round(lat - dlat, 5)],
        [round(lon + dlon, 5), round(lat + dlat, 5)], [round(lon - dlon, 5), round(lat + dlat, 5)],
        [round(lon - dlon, 5), round(lat - dlat, 5)]]]}


def build():
    key = os.getenv('CENSUS_API_KEY')
    features = []
    acs_vintage = '2023'
    for basename, layer, kind, pop, split in CURATED:
        name = basename
        geoid = None
        centroid = None
        geometry = None
        boundary_source = 'TIGERweb'
        try:
            feat = fetch_boundary(basename, layer)
            props = feat['properties']
            name = props.get('NAME', basename)
            geoid = props.get('GEOID')
            centroid = [float(props['INTPTLON']), float(props['INTPTLAT'])]
            geometry = _round_geom(feat['geometry'])
        except Exception as exc:  # network blocked / service hiccup -> approximate box
            print(f'  ! {basename}: boundary fallback ({exc})')
            boundary_source = 'approximate-bbox'
            # rough centroid near the Angeles foothills if lookup failed
            centroid = centroid or [-118.14, 34.19]
            geometry = bbox_polygon(centroid[1], centroid[0])

        if key and geoid:
            try:
                langs, pop = fetch_acs_languages(geoid, key)
                demo_source = 'ACS 5-year (C16001)'
            except Exception as exc:
                print(f'  ! {basename}: ACS fallback ({exc})')
                langs, demo_source = illustrative_languages(split), 'illustrative'
        else:
            langs, demo_source = illustrative_languages(split), 'illustrative'

        features.append({
            'type': 'Feature',
            'properties': {
                'GEOID': geoid or f'SYN-{basename}', 'name': name, 'kind': kind,
                'population': pop, 'centroid': centroid,
                'languages': langs,
                'boundary_source': boundary_source,
                'demographics_source': demo_source,
                'demographics_vintage': acs_vintage if demo_source.startswith('ACS') else None,
            },
            'geometry': geometry,
        })
        print(f'  + {name} ({kind}) GEOID {geoid} · boundary {boundary_source} · demo {demo_source}')

    # Scenario sub-districts (not census places) — clearly labeled synthetic boundaries,
    # demographics inherited from the parent district (Altadena), matching the deck's
    # "west-Altadena" framing.
    altadena = next((f for f in features if f['properties']['name'].startswith('Altadena')), None)
    if altadena:
        c = altadena['properties']['centroid']
        for label, dlon in (('West Altadena', -0.015), ('East Altadena', 0.015)):
            features.append({
                'type': 'Feature',
                'properties': {
                    'GEOID': f'SCEN-{label.replace(" ", "-")}', 'name': label, 'kind': 'district',
                    'population': altadena['properties']['population'] // 2,
                    'centroid': [round(c[0] + dlon, 5), c[1]],
                    'languages': altadena['properties']['languages'],
                    'boundary_source': 'scenario-synthetic',
                    'demographics_source': altadena['properties']['demographics_source'] + ' (inherited)',
                    'demographics_vintage': altadena['properties']['demographics_vintage'],
                },
                'geometry': bbox_polygon(c[1], c[0] + dlon, dlat=0.012, dlon=0.012),
            })
            print(f'  + {label} (scenario district)')

    fc = {
        'type': 'FeatureCollection',
        'metadata': {
            'title': 'PHAROS curated municipalities & districts (LA / Angeles foothills)',
            'region': 'Los Angeles County, CA',
            'boundary_source': 'US Census TIGERweb',
            'demographics_source': 'US Census ACS 5-year table C16001' if key else 'illustrative (set CENSUS_API_KEY for real ACS data)',
            'note': 'Exercise prototype. Demographics are survey estimates, not real-time. Scenario sub-districts have synthetic boundaries.',
        },
        'features': features,
    }
    out = ROOT / 'dist' / 'data' / 'districts.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fc, ensure_ascii=False, indent=1))
    kb = out.stat().st_size / 1024
    print(f'\nWrote {out} ({len(features)} areas, {kb:.0f} KB). '
          f'Demographics: {"REAL ACS" if key else "illustrative (no CENSUS_API_KEY)"}.')


if __name__ == '__main__':
    build()
