import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from backend import live


class FakeResponse:
    def __init__(self, json_data=None, text=''):
        self._json = json_data
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        if self._json is None:
            raise ValueError('no json')
        return self._json


class FakeClient:
    """Stands in for httpx.AsyncClient(...). Returns a response or raises."""

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


def client_returning(response):
    return patch.object(live.httpx, 'AsyncClient', lambda *a, **k: FakeClient(response=response))


def client_failing():
    return patch.object(live.httpx, 'AsyncClient', lambda *a, **k: FakeClient(exc=httpx.ConnectError('boom')))


def run(coro):
    return asyncio.run(coro)


class WeatherTests(unittest.TestCase):
    def test_live(self):
        with client_returning(FakeResponse(json_data={'current': {'wind_speed_10m': 12}})):
            out = run(live.resolve_weather(34.2, -118.2))
        self.assertEqual(out['data_source'], 'live')
        self.assertEqual(out['source'], 'Open-Meteo')
        self.assertEqual(out['data']['current']['wind_speed_10m'], 12)
        self.assertIsNone(out['fire_spread_forecast'])

    def test_fallback_on_error(self):
        with client_failing():
            out = run(live.resolve_weather(34.2, -118.2))
        self.assertEqual(out['data_source'], 'synthetic-fallback')
        self.assertIn('fallback_reason', out)
        self.assertEqual(out['data']['source_id'], 'WX-01')


class FirmsTests(unittest.TestCase):
    def test_live(self):
        csv_text = 'latitude,longitude,bright_ti4\n34.1,-118.2,320\n'
        with patch.dict(os.environ, {'FIRMS_MAP_KEY': 'testkey'}), client_returning(FakeResponse(text=csv_text)):
            out = run(live.resolve_firms(-119, 34, -118, 35))
        self.assertEqual(out['data_source'], 'live')
        self.assertFalse(out['is_fire_perimeter'])
        self.assertEqual(out['observations'][0]['latitude'], '34.1')

    def test_missing_key_falls_back(self):
        with patch.dict(os.environ, {'FIRMS_MAP_KEY': ''}):
            out = run(live.resolve_firms(-119, 34, -118, 35))
        self.assertEqual(out['data_source'], 'synthetic-fallback')
        self.assertFalse(out['is_fire_perimeter'])
        self.assertEqual(out['observations'][0]['id'], 'FIRMS-01')

    def test_fetch_missing_key_status_503(self):
        with patch.dict(os.environ, {'FIRMS_MAP_KEY': ''}):
            with self.assertRaises(live.LiveDataError) as ctx:
                run(live.fetch_firms(-119, 34, -118, 35))
        self.assertEqual(ctx.exception.status, 503)

    def test_fetch_bad_bbox_status_400(self):
        with patch.dict(os.environ, {'FIRMS_MAP_KEY': 'testkey'}):
            with self.assertRaises(live.LiveDataError) as ctx:
                run(live.fetch_firms(-118, 34, -119, 35))  # west >= east
        self.assertEqual(ctx.exception.status, 400)


class RoutesTests(unittest.TestCase):
    def test_live(self):
        with client_returning(FakeResponse(json_data={'code': 'Ok', 'routes': [{'distance': 1}]})):
            out = run(live.resolve_routes(-118.2, 34.1, -118.3, 34.2))
        self.assertEqual(out['data_source'], 'live')
        self.assertFalse(out['hazard_checked'])
        self.assertEqual(out['routes'], [{'distance': 1}])

    def test_fallback_on_error(self):
        with client_failing():
            out = run(live.resolve_routes(-118.2, 34.1, -118.3, 34.2))
        self.assertEqual(out['data_source'], 'synthetic-fallback')
        self.assertFalse(out['hazard_checked'])
        self.assertEqual(len(out['routes']), 2)


class CameraTests(unittest.TestCase):
    def test_live(self):
        feed = {'detections': [{'label': 'smoke', 'confidence': 0.7}]}
        with patch.dict(os.environ, {'CAMERA_FEED_URL': 'https://cam.example/api'}), client_returning(FakeResponse(json_data=feed)):
            out = run(live.resolve_camera())
        self.assertEqual(out['data_source'], 'live')
        self.assertTrue(out['provider_reported'])
        self.assertFalse(out['is_confirmed_fire'])
        self.assertFalse(out['is_inference'])
        self.assertEqual(out['detections'][0]['label'], 'smoke')

    def test_missing_url_falls_back(self):
        with patch.dict(os.environ, {'CAMERA_FEED_URL': ''}):
            out = run(live.resolve_camera())
        self.assertEqual(out['data_source'], 'synthetic-fallback')
        self.assertFalse(out['provider_reported'])
        self.assertFalse(out['is_inference'])
        self.assertEqual(out['detections'][0]['id'], 'CAM-07')

    def test_fetch_missing_url_status_503(self):
        with patch.dict(os.environ, {'CAMERA_FEED_URL': ''}):
            with self.assertRaises(live.LiveDataError) as ctx:
                run(live.fetch_camera_detections())
        self.assertEqual(ctx.exception.status, 503)


if __name__ == '__main__':
    unittest.main()
