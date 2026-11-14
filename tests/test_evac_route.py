import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from backend import live

# Hazard box roughly between origin and destination.
HAZARD = {'type': 'Polygon', 'coordinates': [[[-118.17, 34.16], [-118.14, 34.16], [-118.14, 34.19], [-118.17, 34.19], [-118.17, 34.16]]]}
ORIGIN = [-118.20, 34.20]
DEST = [-118.10, 34.14]


class FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


class FakeClient:
    def __init__(self, get_json=None, post_json=None):
        self._get = get_json
        self._post = post_json

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        return FakeResponse(self._get)

    async def post(self, url, json=None, headers=None):
        return FakeResponse(self._post)


def patch_client(**kw):
    return patch.object(live.httpx, 'AsyncClient', lambda *a, **k: FakeClient(**kw))


def run(coro):
    return asyncio.run(coro)


def osrm(routes):
    return {'code': 'Ok', 'routes': routes}


def route(coords, distance=1000):
    return {'geometry': {'type': 'LineString', 'coordinates': coords}, 'distance': distance, 'duration': distance / 10}


class GeometryTests(unittest.TestCase):
    def test_point_in_polygon(self):
        self.assertTrue(live._point_in_polygon([-118.155, 34.175], HAZARD))
        self.assertFalse(live._point_in_polygon([-118.0, 34.175], HAZARD))

    def test_line_intersection(self):
        crossing = [[-118.18, 34.175], [-118.13, 34.175]]
        clear = [[-118.18, 34.0], [-118.13, 34.0]]
        self.assertTrue(live._line_intersects_polygon(crossing, HAZARD))
        self.assertFalse(live._line_intersects_polygon(clear, HAZARD))


class WithholdTests(unittest.TestCase):
    def test_origin_in_hazard_withholds(self):
        out = run(live.resolve_evac_route([-118.155, 34.175], DEST, HAZARD))
        self.assertTrue(out['withheld'])
        self.assertIn('Origin', out['reason'])

    def test_destination_in_hazard_withholds(self):
        out = run(live.resolve_evac_route(ORIGIN, [-118.155, 34.175], HAZARD))
        self.assertTrue(out['withheld'])
        self.assertIn('Destination', out['reason'])


class OsrmFallbackTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop('ORS_API_KEY', None)

    def test_picks_safe_alternative(self):
        crossing = route([[-118.20, 34.20], [-118.155, 34.175], [-118.10, 34.14]], 900)  # through hazard
        safe = route([[-118.20, 34.20], [-118.20, 34.14], [-118.10, 34.14]], 1200)        # around (south)
        with patch_client(get_json=osrm([crossing, safe])):
            out = run(live.resolve_evac_route(ORIGIN, DEST, HAZARD))
        self.assertFalse(out['withheld'])
        self.assertEqual(out['source'], 'OSRM')
        self.assertEqual(out['route']['geometry']['coordinates'], safe['geometry']['coordinates'])

    def test_all_cross_withholds(self):
        a = route([[-118.20, 34.20], [-118.155, 34.175], [-118.10, 34.14]], 900)
        b = route([[-118.20, 34.20], [-118.16, 34.18], [-118.10, 34.14]], 950)
        with patch_client(get_json=osrm([a, b])):
            out = run(live.resolve_evac_route(ORIGIN, DEST, HAZARD))
        self.assertTrue(out['withheld'])
        self.assertIn('crosses', out['reason'])

    def test_no_hazard_returns_first(self):
        only = route([[-118.20, 34.20], [-118.10, 34.14]], 800)
        with patch_client(get_json=osrm([only])):
            out = run(live.resolve_evac_route(ORIGIN, DEST, None))
        self.assertFalse(out['withheld'])
        self.assertFalse(out['rerouted'])


class OrsTests(unittest.TestCase):
    def test_ors_avoid_polygons_used_when_keyed(self):
        feat = {'features': [{'geometry': {'type': 'LineString', 'coordinates': [[-118.2, 34.2], [-118.1, 34.14]]},
                              'properties': {'summary': {'distance': 1500, 'duration': 180}}}]}
        with patch.dict(os.environ, {'ORS_API_KEY': 'test'}), patch_client(post_json=feat):
            out = run(live.resolve_evac_route(ORIGIN, DEST, HAZARD))
        self.assertEqual(out['source'], 'OpenRouteService')
        self.assertEqual(out['route']['properties']['engine'], 'ors-avoid-polygons')
        self.assertTrue(out['rerouted'])
        self.assertEqual(out['route']['properties']['distance_m'], 1500)


if __name__ == '__main__':
    unittest.main()
