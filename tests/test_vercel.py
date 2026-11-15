"""Verify service discovery and the API surface used by the hosted dashboard."""
import json
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from index import app as root_app
from api.index import app as api_app

class VercelEntrypoints(unittest.TestCase):
    def test_service_roots_and_rewrite_order(self):
        config=json.loads((Path(__file__).resolve().parents[1]/'vercel.json').read_text())
        # One service serves the dashboard and every /api route. A separate `api` service rooted at api/
        # crashed on Vercel (FUNCTION_INVOCATION_FAILED on every /api call) while this service stayed healthy.
        self.assertEqual(config['services'],{'app':{'root':'.','framework':'fastapi'}})
        self.assertEqual([r['destination']['service'] for r in config['rewrites']],['app'])
    def test_root_serves_app_and_presentation(self):
        client=TestClient(root_app)
        for path in ['/','/presentation/','/app.js']:
            self.assertEqual(client.get(path).status_code,200,path)
    def test_root_service_also_serves_every_api_route(self):
        client=TestClient(root_app)
        self.assertEqual(client.get('/api/health').json()['status'],'ok')
        paths=client.get('/openapi.json').json()['paths']
        for path in ['/api/console/language-plan','/api/console/send-sms','/api/evac-route','/api/live/weather']:
            self.assertIn(path,paths)
    def test_api_includes_workflow_and_live_routes(self):
        client=TestClient(api_app)
        self.assertEqual(client.get('/api/health').json()['status'],'ok')
        paths=client.get('/openapi.json').json()['paths']
        for path in ['/api/drafts','/api/drafts/{draft_id}/approve','/api/drafts/{draft_id}/send','/api/broadcast','/api/audit','/api/evac-route','/api/live/perimeters','/api/live/alerts']:
            self.assertIn(path,paths)
