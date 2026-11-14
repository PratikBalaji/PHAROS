import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from backend import live, mcp_server as m


class FakeClient:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        if self._exc:
            raise self._exc
        return self._response


class FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


def run(coro):
    return asyncio.run(coro)


class SyntheticToolTests(unittest.TestCase):
    def test_scenario_tools_are_synthetic(self):
        self.assertEqual(m.get_incident_evidence()['mode'], 'synthetic exercise')
        self.assertEqual(m.get_weather_context()['source_id'], 'WX-01')
        self.assertFalse(m.check_route_constraints()['establishes_safety'])

    def test_all_tools_registered(self):
        names = {t.name for t in run(m.mcp.list_tools())}
        self.assertEqual(names, {
            'get_incident_evidence', 'get_weather_context', 'get_candidate_routes', 'check_route_constraints',
            'get_live_weather', 'get_live_satellite_fire', 'get_live_routes', 'get_camera_detections',
            'get_live_fire_weather_alerts', 'get_live_fire_perimeters', 'get_place_boundaries', 'get_language_demographics',
        })


class LiveToolTests(unittest.TestCase):
    def test_fallback_when_unconfigured(self):
        env = {'FIRMS_MAP_KEY': '', 'CAMERA_FEED_URL': ''}
        fail = patch.object(live.httpx, 'AsyncClient', lambda *a, **k: FakeClient(exc=httpx.ConnectError('x')))
        with patch.dict(os.environ, env), fail:
            self.assertEqual(run(m.get_live_weather(34.2, -118.2))['data_source'], 'synthetic-fallback')
            self.assertEqual(run(m.get_live_satellite_fire(-119, 34, -118, 35))['data_source'], 'synthetic-fallback')
            self.assertEqual(run(m.get_live_routes(-118.2, 34.1, -118.3, 34.2))['data_source'], 'synthetic-fallback')
            self.assertEqual(run(m.get_camera_detections())['data_source'], 'synthetic-fallback')

    def test_live_path_labeled_live(self):
        ok = patch.object(live.httpx, 'AsyncClient', lambda *a, **k: FakeClient(response=FakeResponse({'current': {}})))
        with ok:
            self.assertEqual(run(m.get_live_weather(34.2, -118.2))['data_source'], 'live')


class TransportTests(unittest.TestCase):
    def test_check_bearer(self):
        self.assertTrue(m.check_bearer('Bearer secret', 'secret'))
        self.assertFalse(m.check_bearer('Bearer wrong', 'secret'))
        self.assertFalse(m.check_bearer('', 'secret'))
        self.assertFalse(m.check_bearer('Bearer secret', None))

    def test_bearer_asgi_rejects_missing_token(self):
        sent = []

        async def inner(scope, receive, send):
            sent.append('inner-called')

        async def send(msg):
            sent.append(msg)

        gate = m.BearerAuthASGI(inner, 'secret')
        scope = {'type': 'http', 'headers': [(b'authorization', b'Bearer wrong')]}
        run(gate(scope, None, send))
        self.assertNotIn('inner-called', sent)
        self.assertEqual(sent[0]['status'], 401)

    def test_bearer_asgi_passes_valid_token(self):
        sent = []

        async def inner(scope, receive, send):
            sent.append('inner-called')

        async def send(msg):
            sent.append(msg)

        gate = m.BearerAuthASGI(inner, 'secret')
        scope = {'type': 'http', 'headers': [(b'authorization', b'Bearer secret')]}
        run(gate(scope, None, send))
        self.assertIn('inner-called', sent)

    def test_http_requires_token(self):
        with patch.dict(os.environ, {'PHAROS_MCP_TOKEN': ''}):
            with self.assertRaises(SystemExit):
                m.run_http()

    def test_invalid_transport_rejected(self):
        with patch.dict(os.environ, {'PHAROS_MCP_TRANSPORT': 'carrier-pigeon'}):
            with self.assertRaises(SystemExit):
                m.main()


if __name__ == '__main__':
    unittest.main()
