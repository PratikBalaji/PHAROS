import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault('PHAROS_DB', tempfile.mktemp(suffix='.sqlite3'))

import httpx
from fastapi.testclient import TestClient

from backend import app as appmod, langplan, resend_email
from backend.photon import delivery_config

MID = '4ef9a417-02e9-4d39-ad75-9611e0fcc33c'
ENV = {'RESEND_API_KEY': 're_abc123DEF456_xyz', 'RESEND_TO': 'me@example.com', 'PHAROS_DELIVERY_PROVIDER': 'resend_email'}
client = TestClient(appmod.app)


def run(c):
    return asyncio.run(c)


def mock_client(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), headers={'Authorization': 'Bearer ' + os.environ['RESEND_API_KEY']})


class ConfigTests(unittest.TestCase):
    def test_config(self):
        with patch.dict(os.environ, {'PHAROS_DELIVERY_PROVIDER': 'resend_email', 'RESEND_API_KEY': 'bad', 'RESEND_TO': 'nope'}, clear=True):
            c = delivery_config()
        self.assertEqual((c['provider'], c['channel'], c['configured']), ('resend_email', 'email', False))
        self.assertEqual(set(c['invalid']), {'RESEND_API_KEY', 'RESEND_TO'})
        with patch.dict(os.environ, {'PHAROS_DELIVERY_PROVIDER': 'resend_email'}, clear=True):
            self.assertEqual(set(delivery_config()['missing']), {'RESEND_API_KEY', 'RESEND_TO'})
        with patch.dict(os.environ, ENV, clear=True):
            self.assertTrue(delivery_config()['configured'])


class AdapterTests(unittest.TestCase):
    def test_send_posts_fixed_recipient_marker_subject(self):
        seen = {}
        def h(req):
            import json
            seen.update(json.loads(req.content), auth=req.headers['authorization'], url=str(req.url))
            return httpx.Response(200, json={'id': MID})
        with patch.dict(os.environ, ENV, clear=True), patch.object(resend_email, '_client', mock_client(h)):
            r = run(resend_email.send_resend('EXERCISE ONLY — test body text', 'k'))
        self.assertEqual((r['message_id'], r['provider_status']), (MID, 'sent'))
        self.assertEqual(seen['to'], ['me@example.com'])
        self.assertTrue(seen['subject'].startswith('EXERCISE ONLY'))
        self.assertIn('drill, not a real alert', seen['text'])
        self.assertEqual(seen['url'], 'https://api.resend.com/emails')
        self.assertTrue(seen['from'].endswith('<onboarding@resend.dev>'))

    def test_error_classes(self):
        with patch.dict(os.environ, ENV, clear=True):
            with patch.object(resend_email, '_client', mock_client(lambda r: httpx.Response(403, json={'name': 'validation_error'}))):
                with self.assertRaises(resend_email.ResendError) as e: run(resend_email.send_resend('x' * 30, 'k'))
                self.assertFalse(e.exception.uncertain); self.assertIn('validation_error', str(e.exception))
            with patch.object(resend_email, '_client', mock_client(lambda r: httpx.Response(500, json={}))):
                with self.assertRaises(resend_email.ResendError) as e: run(resend_email.send_resend('x' * 30, 'k'))
                self.assertTrue(e.exception.uncertain)
            with patch.object(resend_email, '_client', mock_client(lambda r: httpx.Response(200, json={'id': 'nope'}))):
                with self.assertRaises(resend_email.ResendError) as e: run(resend_email.send_resend('x' * 30, 'k'))
                self.assertTrue(e.exception.uncertain)

    def test_refresh_maps_events(self):
        for ev, word in (('delivered', 'delivered'), ('bounced', 'bounced'), ('sent', 'unconfirmed')):
            h = lambda r, ev=ev: httpx.Response(200, json={'id': MID, 'last_event': ev})
            with patch.dict(os.environ, ENV, clear=True), patch.object(resend_email, '_client', mock_client(h)):
                self.assertIn(word, run(resend_email.refresh_resend(MID))['status'])
        with patch.dict(os.environ, ENV, clear=True), self.assertRaises(resend_email.ResendError): run(resend_email.refresh_resend('bad'))


class ConsoleTests(unittest.TestCase):
    def test_console_send_once_and_status(self):
        text = langplan.catalogue()['templates']['en'].replace('{area}', 'Glendale city')
        body = {'request_id': 'req-resend-01', 'geoid': '0630000', 'reviewer': 'Op', 'reviewed': True, 'texts': {'en': text}}
        receipt = {'provider': 'resend_email', 'message_id': MID, 'provider_status': 'sent', 'status': 'Accepted by Resend; email delivery unconfirmed'}
        send = AsyncMock(return_value=receipt)
        with patch.dict(os.environ, ENV, clear=True), patch.object(appmod, 'send_resend', send):
            a = client.post('/api/console/send-sms', json=body).json()
            b = client.post('/api/console/send-sms', json=body).json()
        self.assertEqual(send.await_count, 1)
        self.assertEqual((a['channel'], a['counts']['submitted']), ('resend_email', 1))
        self.assertTrue(b['results'][0]['duplicate'])
        fresh = dict(receipt, provider_status='delivered', status='Resend reports email delivered')
        with patch.dict(os.environ, ENV, clear=True), patch.object(appmod, 'refresh_resend', AsyncMock(return_value=fresh)):
            r = client.get('/api/console/sms-status', params={'ids': MID}).json()
        self.assertEqual(r['receipts'][0]['provider_status'], 'delivered')


if __name__ == '__main__':
    unittest.main()
