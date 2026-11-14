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
        self.assertEqual(config['services'],{'app':{'root':'.','framework':'fastapi'},'api':{'root':'api','framework':'fastapi'}})
        self.assertEqual([r['destination']['service'] for r in config['rewrites']],['api','app'])
    def test_root_serves_app_and_presentation(self):
        client=TestClient(root_app)
        for path in ['/','/presentation/','/app.js']:
            self.assertEqual(client.get(path).status_code,200,path)
    def test_api_includes_workflow_and_live_routes(self):
        client=TestClient(api_app)
        self.assertEqual(client.get('/api/health').json()['status'],'ok')
        paths=client.get('/openapi.json').json()['paths']
        for path in ['/api/drafts','/api/drafts/{draft_id}/approve','/api/drafts/{draft_id}/send','/api/broadcast','/api/audit','/api/evac-route','/api/live/perimeters','/api/live/alerts']:
            self.assertIn(path,paths)
