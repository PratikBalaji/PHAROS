import asyncio
import os
import unittest
from unittest.mock import patch

import httpx

from backend import live


class FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def raise_for_status(self):
        return None

    def json(self):
        if self._json is None:
            raise ValueError('no json')
        return self._json


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


def returning(response):
    return patch.object(live.httpx, 'AsyncClient', lambda *a, **k: FakeClient(response=response))


def failing():
    return patch.object(live.httpx, 'AsyncClient', lambda *a, **k: FakeClient(exc=httpx.ConnectError('boom')))


def run(coro):
    return asyncio.run(coro)


class NwsAlertTests(unittest.TestCase):
    def test_live(self):
        feed = {'features': [{'properties': {'event': 'Red Flag Warning'}}]}
        with returning(FakeResponse(feed)):
            out = run(live.resolve_nws_alerts('CA'))
        self.assertEqual(out['data_source'], 'live')
        self.assertEqual(out['count'], 1)
        self.assertFalse(out['is_evacuation_order'])

    def test_fallback_still_not_evacuation_order(self):
        with failing():
            out = run(live.resolve_nws_alerts('CA'))
        self.assertEqual(out['data_source'], 'synthetic-fallback')
        self.assertFalse(out['is_evacuation_order'])
        self.assertIn('fallback_reason', out)

    def test_user_agent_is_generic(self):
        # Default UA must not carry personal data; just assert it is set and generic.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('NWS_USER_AGENT', None)
            captured = {}

            class CapturingClient(FakeClient):
                def __init__(self, *a, **k):
                    super().__init__(response=FakeResponse({'features': []}))
                    captured['headers'] = k.get('headers', {})

            with patch.object(live.httpx, 'AsyncClient', CapturingClient):
                run(live.fetch_nws_alerts('CA'))
        self.assertIn('User-Agent', captured['headers'])
        self.assertIn('PHAROS', captured['headers']['User-Agent'])


class PerimeterTests(unittest.TestCase):
    def test_live(self):
        fc = {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'geometry': {}, 'properties': {}}]}
        with returning(FakeResponse(fc)):
            out = run(live.resolve_fire_perimeters())
        self.assertEqual(out['data_source'], 'live')
        self.assertTrue(out['authoritative'])
        self.assertEqual(out['count'], 1)

    def test_arcgis_error_falls_back(self):
        with returning(FakeResponse({'error': {'code': 400}})):
            out = run(live.resolve_fire_perimeters())
        self.assertEqual(out['data_source'], 'synthetic-fallback')
        self.assertFalse(out['authoritative'])
        self.assertEqual(out['count'], 1)  # one synthetic polygon

    def test_fallback_polygon_is_closed(self):
        with failing():
            out = run(live.resolve_fire_perimeters())
        ring = out['perimeters'][0]['geometry']['coordinates'][0]
        self.assertEqual(ring[0], ring[-1])


class BoundaryTests(unittest.TestCase):
    def test_live(self):
        fc = {'type': 'FeatureCollection', 'features': [{'properties': {'NAME': 'Pasadena', 'GEOID': '0656000'}}]}
        with returning(FakeResponse(fc)):
            out = run(live.resolve_place_boundaries())
        self.assertEqual(out['data_source'], 'live')
        self.assertEqual(out['count'], 1)

    def test_fallback_empty(self):
        with failing():
            out = run(live.resolve_place_boundaries())
        self.assertEqual(out['data_source'], 'synthetic-fallback')
        self.assertEqual(out['boundaries'], [])


class DemographicsTests(unittest.TestCase):
    def test_live_parses_and_sorts_shares(self):
        # ACS returns [header, row]; total 1000, Spanish 300, English 600.
        header = ['NAME', 'C16001_001E', 'C16001_002E', 'C16001_003E', 'state', 'place']
        row = ['Testville', '1000', '600', '300', '06', '00001']
        # include remaining vars as 0 so parser handles them
        extra = [v for v in live.ACS_LANGUAGE_VARS if v not in ('C16001_002E', 'C16001_003E')]
        header = header[:4] + extra + header[4:]
        row = row[:4] + ['0'] * len(extra) + row[4:]
        with returning(FakeResponse([header, row])):
            out = run(live.resolve_language_demographics('0600001'))
        self.assertEqual(out['data_source'], 'live')
        self.assertTrue(out['is_estimate'])
        self.assertEqual(out['population_5plus'], 1000)
        self.assertEqual(out['languages'][0]['code'], 'en')
        self.assertEqual(out['languages'][0]['share'], 0.6)
        self.assertEqual(out['languages'][1]['code'], 'es')

    def test_bad_geoid_falls_back(self):
        out = run(live.resolve_language_demographics('123'))
        self.assertEqual(out['data_source'], 'synthetic-fallback')
        self.assertTrue(out['is_estimate'])
        self.assertTrue(len(out['languages']) >= 3)

    def test_fetch_bad_geoid_status_400(self):
        with self.assertRaises(live.LiveDataError) as ctx:
            run(live.fetch_language_demographics('123'))
        self.assertEqual(ctx.exception.status, 400)


if __name__ == '__main__':
    unittest.main()


class AcsMappingTests(unittest.TestCase):
    def test_variables_are_the_group_total_rows(self):
        # C16001 total rows sit at 002, 003, then every third row; the rows between split by English ability.
        self.assertEqual(sorted(live.ACS_LANGUAGE_VARS),['C16001_%03dE'%n for n in (2,3,6,9,12,15,18,21,24,27,30,33,36)])
        self.assertEqual(live.ACS_LANGUAGE_VARS['C16001_021E'][0],'zh')
        self.assertEqual(live.ACS_LANGUAGE_VARS['C16001_015E'][0],'hy')
