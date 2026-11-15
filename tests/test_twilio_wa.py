import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault('PHAROS_DB', tempfile.mktemp(suffix='.sqlite3'))

import httpx
from fastapi.testclient import TestClient

from backend import app as appmod, langplan, twilio_wa
from backend.photon import delivery_config

SID = 'AC' + 'a' * 32
MSG = 'SM' + 'b' * 32
ENV = {'TWILIO_ACCOUNT_SID': SID, 'TWILIO_AUTH_TOKEN': 'tok', 'TWILIO_WHATSAPP_FROM': 'whatsapp:+14155238886', 'TWILIO_TO': '+15555550123', 'PHAROS_DELIVERY_PROVIDER': 'twilio_whatsapp'}
client = TestClient(appmod.app)


def run(c):
    return asyncio.run(c)


def mock_client(handler):
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), auth=(SID, 'tok'))


class ConfigTests(unittest.TestCase):
    def test_config_reports_missing_and_invalid(self):
        with patch.dict(os.environ, {'PHAROS_DELIVERY_PROVIDER': 'twilio_whatsapp', 'TWILIO_ACCOUNT_SID': 'nope', 'TWILIO_TO': '555'}, clear=True):
            c = delivery_config()
        self.assertFalse(c['configured'])
        self.assertEqual(set(c['invalid']), {'TWILIO_ACCOUNT_SID', 'TWILIO_TO'})
        self.assertIn('TWILIO_AUTH_TOKEN', c['missing'])
        with patch.dict(os.environ, ENV, clear=True):
            self.assertTrue(delivery_config()['configured'])


class AdapterTests(unittest.TestCase):
    def test_send_builds_whatsapp_form_and_parses_receipt(self):
        seen = {}
        def h(req):
            seen['body'] = req.content.decode(); seen['url'] = str(req.url); seen['idem'] = req.headers.get('I-Twilio-Idempotency-Token')
            return httpx.Response(201, json={'sid': MSG, 'status': 'queued'})
        with patch.dict(os.environ, ENV, clear=True), patch.object(twilio_wa, '_client', mock_client(h)):
            r = run(twilio_wa.send_twilio('EXERCISE ONLY test message here', 'key-1'))
        self.assertEqual((r['message_id'], r['provider_status']), (MSG, 'queued'))
        self.assertIn('From=whatsapp%3A%2B14155238886', seen['body'])
        self.assertIn('To=whatsapp%3A%2B15555550123', seen['body'])
        self.assertTrue(seen['url'].endswith(f'/Accounts/{SID}/Messages.json'))
        self.assertEqual(seen['idem'], 'key-1')

    def test_server_error_is_uncertain_client_error_is_not(self):
        with patch.dict(os.environ, ENV, clear=True):
            with patch.object(twilio_wa, '_client', mock_client(lambda r: httpx.Response(503, json={}))):
                with self.assertRaises(twilio_wa.TwilioError) as e: run(twilio_wa.send_twilio('x' * 30, 'k'))
                self.assertTrue(e.exception.uncertain)
            with patch.object(twilio_wa, '_client', mock_client(lambda r: httpx.Response(400, json={'code': 63015}))):
                with self.assertRaises(twilio_wa.TwilioError) as e: run(twilio_wa.send_twilio('x' * 30, 'k'))
                self.assertFalse(e.exception.uncertain)
                self.assertIn('63015', str(e.exception))

    def test_unrecognized_receipt_is_uncertain_and_long_text_refused(self):
        with self.assertRaises(twilio_wa.TwilioError) as e: twilio_wa.receipt({'sid': MSG, 'status': 'weird'})
        self.assertTrue(e.exception.uncertain)
        with patch.dict(os.environ, ENV, clear=True):
            with self.assertRaises(twilio_wa.TwilioError): run(twilio_wa.send_twilio('x' * 1700, 'k'))

    def test_refresh_maps_delivered(self):
        h = lambda r: httpx.Response(200, json={'sid': MSG, 'status': 'delivered'})
        with patch.dict(os.environ, ENV, clear=True), patch.object(twilio_wa, '_client', mock_client(h)):
            self.assertEqual(run(twilio_wa.refresh_twilio(MSG))['status'], 'Twilio reports WhatsApp delivered')
            with self.assertRaises(twilio_wa.TwilioError): run(twilio_wa.refresh_twilio('bad'))


class ConsoleTests(unittest.TestCase):
    def test_console_sends_through_twilio_once_and_status_routes_by_id(self):
        text = langplan.catalogue()['templates']['en'].replace('{area}', 'Glendale city')
        body = {'request_id': 'req-twilio-01', 'geoid': '0630000', 'reviewer': 'Op', 'reviewed': True, 'texts': {'en': text}}
        receipt = {'provider': 'twilio_whatsapp', 'message_id': MSG, 'provider_status': 'queued', 'status': 'Accepted by Twilio; WhatsApp delivery unconfirmed'}
        send = AsyncMock(return_value=receipt)
        with patch.dict(os.environ, ENV, clear=True), patch.object(appmod, 'send_twilio', send):
            a = client.post('/api/console/send-sms', json=body).json()
            b = client.post('/api/console/send-sms', json=body).json()
        self.assertEqual(send.await_count, 1)
        self.assertEqual((a['channel'], a['counts']['submitted']), ('twilio_whatsapp', 1))
        self.assertTrue(b['results'][0]['duplicate'])
        fresh = dict(receipt, provider_status='delivered', status='Twilio reports WhatsApp delivered')
        with patch.dict(os.environ, ENV, clear=True), patch.object(appmod, 'refresh_twilio', AsyncMock(return_value=fresh)):
            r = client.get('/api/console/sms-status', params={'ids': MSG}).json()
        self.assertEqual(r['receipts'][0]['provider_status'], 'delivered')


if __name__ == '__main__':
    unittest.main()
