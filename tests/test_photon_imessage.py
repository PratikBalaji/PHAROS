import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault('PHAROS_DB', tempfile.mktemp(suffix='.sqlite3'))

import httpx
from fastapi.testclient import TestClient

from backend import app as appmod, langplan, photon_imessage
from backend.photon import delivery_config

PRJ = 'pho_prj_01m7dw21ypen99cbybaedeeajh'
ENV = {'PHOTON_API_KEY': 'pho_sk_test', 'PHOTON_PROJECT_ID': PRJ, 'PHOTON_IMESSAGE_TO': '+15555550123', 'PHAROS_DELIVERY_PROVIDER': 'photon_imessage'}
client = TestClient(appmod.app)


def run(c):
    return asyncio.run(c)


def mock_client(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), headers={'Authorization': 'Bearer ' + os.environ['PHOTON_API_KEY']})


class ImessageTests(unittest.TestCase):
    def test_config(self):
        with patch.dict(os.environ, {'PHAROS_DELIVERY_PROVIDER': 'photon_imessage'}, clear=True):
            self.assertEqual(set(delivery_config()['missing']), {'PHOTON_API_KEY', 'PHOTON_PROJECT_ID', 'PHOTON_IMESSAGE_TO'})
        with patch.dict(os.environ, {**ENV, 'PHOTON_IMESSAGE_TO': '555', 'PHOTON_API_BASE': 'https://evil.example.com'}, clear=True):
            self.assertEqual(set(delivery_config()['invalid']), {'PHOTON_IMESSAGE_TO', 'PHOTON_API_BASE'})
        with patch.dict(os.environ, ENV, clear=True):
            c = delivery_config()
        self.assertEqual((c['provider'], c['channel'], c['configured']), ('photon_imessage', 'imessage', True))

    def test_send_hits_documented_endpoint_with_fixed_recipient(self):
        seen = {}
        def h(req):
            import json
            seen.update(json.loads(req.content), url=str(req.url), auth=req.headers['authorization'])
            return httpx.Response(200, json={'id': 'msg_123'})
        with patch.dict(os.environ, ENV, clear=True), patch.object(photon_imessage, '_client', mock_client(h)):
            r = run(photon_imessage.send_imessage('EXERCISE ONLY — hello there drill', 'k'))
        self.assertEqual(seen['url'], f'https://api.beta.photon.codes/v1/projects/{PRJ}/platforms/imessage/send')
        self.assertEqual((seen['to'], seen['message']), ('+15555550123', 'EXERCISE ONLY — hello there drill'))
        self.assertEqual(seen['auth'], 'Bearer pho_sk_test')
        self.assertEqual((r['message_id'], r['provider_status']), ('msg_123', 'accepted'))

    def test_empty_200_body_is_accepted_without_id(self):
        with patch.dict(os.environ, ENV, clear=True), patch.object(photon_imessage, '_client', mock_client(lambda r: httpx.Response(200, text='ok'))):
            self.assertIsNone(run(photon_imessage.send_imessage('x' * 30, 'k'))['message_id'])

    def test_error_classes(self):
        with patch.dict(os.environ, ENV, clear=True):
            with patch.object(photon_imessage, '_client', mock_client(lambda r: httpx.Response(401, json={'code': 'NOT_AUTHENTICATED'}))):
                with self.assertRaises(photon_imessage.PhotonImessageError) as e: run(photon_imessage.send_imessage('x' * 30, 'k'))
                self.assertFalse(e.exception.uncertain); self.assertIn('NOT_AUTHENTICATED', str(e.exception))
            with patch.object(photon_imessage, '_client', mock_client(lambda r: httpx.Response(409, json={'code': 'CONFLICT'}))):
                with self.assertRaises(photon_imessage.PhotonImessageError) as e: run(photon_imessage.send_imessage('x' * 30, 'k'))
                self.assertTrue(e.exception.uncertain)

    def test_connection_failure_names_the_cause_and_is_not_uncertain(self):
        def boom(req): raise httpx.ConnectError('dns')
        with patch.dict(os.environ, ENV, clear=True), patch.object(photon_imessage, '_client', mock_client(boom)):
            with self.assertRaises(photon_imessage.PhotonImessageError) as e: run(photon_imessage.send_imessage('x' * 30, 'k'))
        self.assertIn('ConnectError', str(e.exception))
        self.assertFalse(e.exception.uncertain)
        def slow(req): raise httpx.ReadTimeout('slow')
        with patch.dict(os.environ, ENV, clear=True), patch.object(photon_imessage, '_client', mock_client(slow)):
            with self.assertRaises(photon_imessage.PhotonImessageError) as e: run(photon_imessage.send_imessage('x' * 30, 'k'))
        self.assertTrue(e.exception.uncertain)

    def test_console_sends_once(self):
        text = langplan.catalogue()['templates']['en'].replace('{area}', 'Glendale city')
        body = {'request_id': 'req-imsg-0001', 'geoid': '0630000', 'reviewer': 'Op', 'reviewed': True, 'texts': {'en': text}}
        receipt = {'provider': 'photon_imessage', 'message_id': None, 'provider_status': 'accepted', 'status': 'Accepted by Photon; iMessage delivery unconfirmed'}
        send = AsyncMock(return_value=receipt)
        with patch.dict(os.environ, ENV, clear=True), patch.object(appmod, 'send_imessage', send):
            a = client.post('/api/console/send-sms', json=body).json()
            b = client.post('/api/console/send-sms', json=body).json()
        self.assertEqual(send.await_count, 1)
        self.assertEqual((a['channel'], a['counts']['submitted']), ('photon_imessage', 1))
        self.assertTrue(b['results'][0]['duplicate'])


if __name__ == '__main__':
    unittest.main()
