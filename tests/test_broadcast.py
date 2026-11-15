import unittest
from fastapi.testclient import TestClient
from backend.app import app
from backend.broadcast import build_plan

class BroadcastTests(unittest.TestCase):
    def test_all_languages_per_area(self):
        p=build_plan(['0630000','0602462'],'all')
        self.assertEqual(p['message_count'],18)
        self.assertEqual(p['has_illustrative_data'],any(not a['demographics_source'].startswith('ACS') for a in p['areas']))
        for area in p['areas']:
            self.assertTrue(all(area['name'] in m['text'] for m in area['messages']))
    def test_stored_bundle_round_trip(self):
        c=TestClient(app)
        r=c.post('/api/broadcast',json={'geoids':['0630000'],'mode':'auto','reviewer':'QA','reviewed':True})
        self.assertEqual(r.status_code,200)
        saved=c.get('/api/broadcasts/'+r.json()['id']).json()
        self.assertEqual(saved['plan'],r.json()['plan'])
        self.assertFalse(saved['public_alert'])
    def test_review_and_unknown_district_rejected(self):
        c=TestClient(app)
        for geoids,reviewed,status in [(['fake'],True,422),(['0630000'],False,400)]:
            r=c.post('/api/broadcast',json={'geoids':geoids,'mode':'auto','reviewer':'QA','reviewed':reviewed})
            self.assertEqual(r.status_code,status)
