import os
import unittest
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from backend import photon
from backend.app import app

SUFFIX='0'*25+'1'
ENV={'PHAROS_DELIVERY_PROVIDER':'photon','PHOTON_API_KEY':'test-only','PHOTON_PROJECT_ID':'pho_prj_'+SUFFIX,'PHOTON_SENDER_ID':'pho_usr_'+SUFFIX,'PHOTON_SPACE_ID':'pho_spc_'+SUFFIX}
MESSAGE={'id':'pho_msg_'+SUFFIX,'status':'dispatched'}

class PhotonTests(unittest.IsolatedAsyncioTestCase):
    async def test_sms_contract_and_receipt(self):
        calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(200,json={'platform':'sms'} if request.method=='GET' else MESSAGE)
        with patch.dict(os.environ,ENV),patch.object(photon,'client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(handler))):
            result=await photon.send_photon('EXERCISE ONLY · 中文','draft-key')
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[1].headers['idempotency-key'],'draft-key')
        self.assertIn('中文',calls[1].content.decode())
        self.assertEqual(result['provider_status'],'dispatched')
        self.assertIn('unconfirmed',result['status'])

    async def test_reject_non_sms_without_post(self):
        calls=[]
        def handler(request):
            calls.append(request);return httpx.Response(200,json={'platform':'imessage'})
        with patch.dict(os.environ,ENV),patch.object(photon,'client',lambda:httpx.AsyncClient(transport=httpx.MockTransport(handler))):
            with self.assertRaisesRegex(photon.PhotonError,'not an SMS'):await photon.send_photon('test','key')
        self.assertEqual(len(calls),1)

    async def test_missing_configuration(self):
        with patch.dict(os.environ,{'PHOTON_API_KEY':'','PHAROS_DELIVERY_PROVIDER':'photon'}):
            self.assertFalse(photon.delivery_config()['configured'])
            with self.assertRaises(photon.PhotonError):await photon.send_photon('test','key')

class PhotonWorkflowTests(unittest.TestCase):
    def draft(self,c):
        d=c.post('/api/drafts',json={'stage':0}).json()
        c.post('/api/drafts/'+d['id']+'/approve',json={'stage':0,'reviewer':'QA','reviewed':True,'text':d['text']})
        return '/api/drafts/'+d['id']

    def test_submission_and_receipt_refresh(self):
        with patch.dict(os.environ,ENV),patch('backend.app.send_photon',return_value={'provider':'photon','status':'Accepted','message_id':MESSAGE['id']}) as send:
            c=TestClient(app);path=self.draft(c)
            self.assertEqual(c.post(path+'/send',json={'stage':0}).status_code,200)
            self.assertTrue(c.post(path+'/send',json={'stage':0}).json()['duplicate']);send.assert_called_once()
            with patch('backend.app.refresh_photon',return_value={'status':'Photon reports SMS delivered','provider_status':'delivered'}):
                self.assertEqual(c.get(path+'/delivery').json()['delivery']['provider_status'],'delivered')

    def test_uncertain_delivery_stays_blocked(self):
        with patch.dict(os.environ,ENV),patch('backend.app.send_photon',side_effect=photon.PhotonError('Timeout',True)):
            c=TestClient(app);path=self.draft(c)
            self.assertEqual(c.post(path+'/send',json={'stage':0}).status_code,502)
            self.assertEqual(c.post(path+'/send',json={'stage':0}).status_code,409)
