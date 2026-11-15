import os
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
os.environ['PHAROS_DB']=tempfile.mktemp(suffix='.sqlite3')
os.environ.pop('BEDROCK_MODEL_ID',None)
os.environ.pop('NTFY_TOPIC_URL',None)
from fastapi.testclient import TestClient
from backend.app import app, get_draft, save
from backend.core import check_routes
client=TestClient(app)

class WorkflowTests(unittest.TestCase):
    def draft(self,stage=0):
        response=client.post('/api/drafts',json={'stage':stage});self.assertEqual(response.status_code,200);return response.json()
    def approve(self,d,**changes):
        payload={'stage':d['stage'],'reviewer':'Test operator','reviewed':True,'text':d['text']};payload.update(changes)
        return client.post('/api/drafts/'+d['id']+'/approve',json=payload)
    def test_scenario_query_accepts_stage_1_and_rejects_3(self):
        c=TestClient(app)
        self.assertEqual(c.get('/api/scenario?stage=1').status_code,200)
        self.assertEqual(c.get('/api/scenario?stage=3').status_code,422)
    def test_scenario_checks(self):
        self.assertEqual([r['blocked'] for r in check_routes(0)],[True,False])
        self.assertTrue(all(r['blocked'] for r in check_routes(2)))
    def test_unapproved_send_denied(self):
        d=self.draft();r=client.post('/api/drafts/'+d['id']+'/send',json={'stage':0});self.assertEqual(r.status_code,409)
    def test_approval_then_idempotent_send(self):
        d=self.draft();self.assertEqual(self.approve(d).status_code,200)
        r=client.post('/api/drafts/'+d['id']+'/send',json={'stage':0});self.assertEqual(r.status_code,200);self.assertFalse(r.json()['duplicate'])
        r=client.post('/api/drafts/'+d['id']+'/send',json={'stage':0});self.assertTrue(r.json()['duplicate'])
        self.assertEqual(self.approve(d).status_code,409)
    def test_missing_review_and_exercise_prefix_denied(self):
        d=self.draft();self.assertEqual(self.approve(d,reviewed=False).status_code,400)
        self.assertEqual(self.approve(d,reviewer='   ').status_code,400)
        self.assertEqual(self.approve(d,text='Follow this instruction immediately.').status_code,400)
    def test_changed_stage_denied(self):
        d=self.draft();self.assertEqual(self.approve(d,stage=2).status_code,409)
        self.approve(d);self.assertEqual(client.post('/api/drafts/'+d['id']+'/send',json={'stage':2}).status_code,409)
    def test_expired_draft_denied(self):
        d=self.draft();d['created_at']=(datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat();save(d)
        self.assertEqual(self.approve(d).status_code,409)
    def test_no_route_withholds_instructions(self):
        d=self.draft(2);self.assertIsNone(d['route_id']);self.assertIn('Route instructions are withheld',d['text'])
    def test_validation_and_static_dashboard(self):
        self.assertEqual(client.post('/api/drafts',json={'stage':3}).status_code,422)
        self.assertEqual(client.get('/').status_code,200)
        self.assertEqual(client.get('/api/live/firms',params={'west':-119,'east':-118,'south':34,'north':35}).status_code,503)

if __name__=='__main__': unittest.main()
