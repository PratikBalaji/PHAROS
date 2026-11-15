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
        live.clear_route_cache()

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
    def setUp(self):
        live.clear_route_cache()

    def test_ors_avoid_polygons_used_when_keyed(self):
        feat = {'features': [{'geometry': {'type': 'LineString', 'coordinates': [[-118.2, 34.2], [-118.1, 34.14]]},
                              'properties': {'summary': {'distance': 1500, 'duration': 180}}}]}
        with patch.dict(os.environ, {'ORS_API_KEY': 'test'}), patch_client(post_json=feat):
            out = run(live.resolve_evac_route(ORIGIN, DEST, HAZARD))
        self.assertEqual(out['source'], 'OpenRouteService')
        self.assertEqual(out['route']['properties']['engine'], 'ors-avoid-polygons')
        self.assertTrue(out['rerouted'])
        self.assertEqual(out['route']['properties']['distance_m'], 1500)


MULTI = {'type': 'MultiPolygon', 'coordinates': [
    [[[-118.17, 34.16], [-118.155, 34.16], [-118.155, 34.19], [-118.17, 34.19], [-118.17, 34.16]]],
    [[[-118.12, 34.14], [-118.11, 34.14], [-118.11, 34.15], [-118.12, 34.15], [-118.12, 34.14]]],
]}


class MultiPolygonAndCandidatesTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop('ORS_API_KEY', None)
        live.clear_route_cache()

    def test_multipolygon_geometry_helpers(self):
        self.assertTrue(live._point_in_polygon([-118.162, 34.175], MULTI))
        self.assertTrue(live._point_in_polygon([-118.115, 34.145], MULTI))
        self.assertFalse(live._point_in_polygon([-118.14, 34.15], MULTI))   # gap between the two shapes
        self.assertTrue(live._line_intersects_polygon([[-118.20, 34.145], [-118.10, 34.145]], MULTI))
        self.assertFalse(live._line_intersects_polygon([[-118.20, 34.00], [-118.10, 34.00]], MULTI))

    def test_every_candidate_is_returned_with_geometry_and_safe_flag(self):
        crossing = route([[-118.20, 34.20], [-118.162, 34.175], [-118.10, 34.14]], 900)
        safe = route([[-118.20, 34.20], [-118.20, 34.12], [-118.10, 34.12], [-118.10, 34.14]], 1200)
        with patch_client(get_json=osrm([crossing, safe])):
            out = run(live.resolve_evac_route(ORIGIN, DEST, MULTI))
        listed = out['candidate_routes']
        self.assertEqual([c['id'] for c in listed], ['R1', 'R2'])
        self.assertEqual([c['safe'] for c in listed], [False, True])
        self.assertEqual(listed[1]['geometry']['coordinates'], safe['geometry']['coordinates'])
        self.assertEqual(out['chosen_id'], 'R2')
        self.assertTrue(out['rerouted'])

    def test_withheld_still_lists_candidates(self):
        a = route([[-118.20, 34.20], [-118.162, 34.175], [-118.10, 34.14]], 900)
        with patch_client(get_json=osrm([a])):
            out = run(live.resolve_evac_route(ORIGIN, DEST, MULTI))
        self.assertTrue(out['withheld'])
        self.assertEqual(out['candidate_routes'][0]['safe'], False)

    def test_identical_request_is_cached_for_a_short_time(self):
        only = route([[-118.20, 34.20], [-118.10, 34.14]], 800)
        calls = []

        class Counting(FakeClient):
            async def get(self, url, params=None, headers=None):
                calls.append(url)
                return await super().get(url, params, headers)

        with patch.object(live.httpx, 'AsyncClient', lambda *a, **k: Counting(get_json=osrm([only]))):
            first = run(live.resolve_evac_route(ORIGIN, DEST, None))
            second = run(live.resolve_evac_route(ORIGIN, DEST, None))
        self.assertEqual(len(calls), 1)
        self.assertTrue(second.get('cached'))
        self.assertEqual(first['route']['geometry'], second['route']['geometry'])
        with patch.dict(os.environ, {'PHAROS_ROUTE_CACHE_SECONDS': '0'}):
            live.clear_route_cache()
            with patch.object(live.httpx, 'AsyncClient', lambda *a, **k: Counting(get_json=osrm([only]))):
                run(live.resolve_evac_route(ORIGIN, DEST, None))
                run(live.resolve_evac_route(ORIGIN, DEST, None))
        self.assertEqual(len(calls), 3)


class EvacEndpointValidationTests(unittest.TestCase):
    def test_bad_avoid_is_rejected(self):
        os.environ.setdefault('PHAROS_DB', __import__('tempfile').mktemp(suffix='.sqlite3'))
        from fastapi.testclient import TestClient
        from backend.app import app
        client = TestClient(app)
        base = {'origin': [-118.2, 34.2], 'dest': [-118.1, 34.14]}
        self.assertEqual(client.post('/api/evac-route', json={**base, 'avoid': {'type': 'Point', 'coordinates': [0, 0]}}).status_code, 422)
        self.assertEqual(client.post('/api/evac-route', json={**base, 'avoid': {'type': 'MultiPolygon', 'coordinates': []}}).status_code, 422)
        huge = {'type': 'MultiPolygon', 'coordinates': [[[[0, 0], [1, 0], [1, 1], [0, 0]]]] * 2001}
        self.assertEqual(client.post('/api/evac-route', json={**base, 'avoid': huge}).status_code, 422)


if __name__ == '__main__':
    unittest.main()
