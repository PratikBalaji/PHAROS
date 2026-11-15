import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault('PHAROS_DB', tempfile.mktemp(suffix='.sqlite3'))

import httpx
from fastapi.testclient import TestClient

from backend import app as appmod, langplan, ntfy
from backend.photon import delivery_config

TOPIC = 'https://ntfy.sh/pharos-drill-x7k2m9'
ENV = {'NTFY_TOPIC_URL': TOPIC, 'PHAROS_DELIVERY_PROVIDER': 'ntfy'}
client = TestClient(appmod.app)


def run(c):
    return asyncio.run(c)


def mock_client(handler, token=None):
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=headers)


class ConfigTests(unittest.TestCase):
    def test_config(self):
        with patch.dict(os.environ, {'PHAROS_DELIVERY_PROVIDER': 'ntfy'}, clear=True):
            self.assertEqual(delivery_config()['missing'], ['NTFY_TOPIC_URL'])
        for bad in ('http://ntfy.sh/x', 'https://ntfy.sh/', 'https://ntfy.sh/a/b', 'https://u:p@ntfy.sh/x', 'https://ntfy.sh/x?auth=1', 'nope'):
            with patch.dict(os.environ, {**ENV, 'NTFY_TOPIC_URL': bad}, clear=True):
                self.assertEqual(delivery_config()['invalid'], ['NTFY_TOPIC_URL'], bad)
        with patch.dict(os.environ, ENV, clear=True):
            c = delivery_config()
        self.assertEqual((c['provider'], c['channel'], c['configured']), ('ntfy', 'notification', True))


class AdapterTests(unittest.TestCase):
    def test_publishes_utf8_body_with_ascii_title(self):
        seen = {}
        def h(req):
            seen.update(body=req.content.decode('utf-8'), title=req.headers['title'], url=str(req.url), auth=req.headers.get('authorization'))
            return httpx.Response(200, json={'id': 'abcDEF123456', 'event': 'message'})
        arm = 'ՄԻԱՅՆ ՎԱՐԺԱՆՔ — սա իրական արտակարգ իրավիճակ չէ: Glendale city'
        with patch.dict(os.environ, {**ENV, 'NTFY_TOKEN': 'tk_secret'}, clear=True), patch.object(ntfy, '_client', mock_client(h, 'tk_secret')):
            r = run(ntfy.send_ntfy(arm, 'pharos-sms-req123-hy'))
        self.assertEqual(seen['body'], arm)
        self.assertEqual(seen['title'], 'PHAROS EXERCISE - Armenian')
        self.assertTrue(seen['title'].isascii())
        self.assertEqual(seen['url'], TOPIC)
        self.assertEqual(seen['auth'], 'Bearer tk_secret')
        self.assertEqual((r['message_id'], r['provider_status']), ('abcDEF123456', 'published'))
        self.assertNotIn('tk_secret', str(r))

    def test_strategy_title_and_non_json_ok(self):
        with patch.dict(os.environ, ENV, clear=True), patch.object(ntfy, '_client', mock_client(lambda r: httpx.Response(200, text='ok'))):
            self.assertIsNone(run(ntfy.send_ntfy('EXERCISE ONLY — strategy text here', 'pharos-sms-req123-strategy'))['message_id'])
        self.assertEqual(ntfy._title('pharos-sms-req123-strategy'), 'PHAROS EXERCISE - Strategy')

    def test_error_classes(self):
        with patch.dict(os.environ, ENV, clear=True):
            with patch.object(ntfy, '_client', mock_client(lambda r: httpx.Response(403, json={}))):
                with self.assertRaises(ntfy.NtfyError) as e: run(ntfy.send_ntfy('x' * 30, 'k-en'))
                self.assertFalse(e.exception.uncertain); self.assertIn('403', str(e.exception))
            with patch.object(ntfy, '_client', mock_client(lambda r: httpx.Response(503, json={}))):
                with self.assertRaises(ntfy.NtfyError) as e: run(ntfy.send_ntfy('x' * 30, 'k-en'))
                self.assertTrue(e.exception.uncertain)
            def boom(req): raise httpx.ConnectError('dns')
            with patch.object(ntfy, '_client', mock_client(boom)):
                with self.assertRaises(ntfy.NtfyError) as e: run(ntfy.send_ntfy('x' * 30, 'k-en'))
                self.assertIn('ConnectError', str(e.exception)); self.assertFalse(e.exception.uncertain)
            def slow(req): raise httpx.ReadTimeout('slow')
            with patch.object(ntfy, '_client', mock_client(slow)):
                with self.assertRaises(ntfy.NtfyError) as e: run(ntfy.send_ntfy('x' * 30, 'k-en'))
                self.assertTrue(e.exception.uncertain)
        with patch.dict(os.environ, {'PHAROS_DELIVERY_PROVIDER': 'ntfy'}, clear=True), self.assertRaises(ntfy.NtfyError):
            run(ntfy.send_ntfy('x' * 30, 'k-en'))


class ConsoleTests(unittest.TestCase):
    def test_language_messages_and_strategy_go_to_ntfy_once(self):
        cat = langplan.catalogue()
        texts = {c: cat['templates'][c].replace('{area}', 'Glendale city') for c in ('en', 'hy')}
        body = {'request_id': 'req-ntfy-0001', 'geoid': '0630000', 'reviewer': 'Op', 'reviewed': True, 'texts': texts}
        receipt = {'provider': 'ntfy', 'message_id': 'abc', 'provider_status': 'published', 'status': 'Accepted by ntfy; device receipt unverified'}
        send = AsyncMock(return_value=receipt)
        with patch.dict(os.environ, ENV, clear=True), patch.object(appmod, 'send_ntfy', send):
            a = client.post('/api/console/send-sms', json=body).json()
            b = client.post('/api/console/send-sms', json=body).json()
            facts = {'run_name': 'Verdugo Hills', 'outcome': 'withheld'}
            st = {'request_id': 'req-ntfy-0002', 'geoid': '0630000', 'reviewer': 'Op', 'reviewed': True, 'facts': facts, 'text': langplan.strategy_draft('Glendale city', facts)}
            s = client.post('/api/console/strategy-sms', json=st).json()
        self.assertEqual(send.await_count, 3)
        self.assertEqual([c.args[1] for c in send.await_args_list][:2], ['pharos-sms-req-ntfy-0001-en', 'pharos-sms-req-ntfy-0001-hy'])
        self.assertEqual((a['channel'], a['counts']['submitted']), ('ntfy', 2))
        self.assertTrue(all(r['duplicate'] for r in b['results']))
        self.assertEqual(s['result']['state'], 'submitted')

    def test_status_is_honest_about_receipts(self):
        with patch.dict(os.environ, ENV, clear=True):
            r = client.get('/api/console/sms-status', params={'ids': 'abc123'}).json()
        self.assertIn('does not report device receipts', r['receipts'][0]['status'])

    def test_unconfigured_is_503(self):
        with patch.dict(os.environ, {'PHAROS_DELIVERY_PROVIDER': 'ntfy'}, clear=True):
            text = langplan.catalogue()['templates']['en'].replace('{area}', 'Glendale city')
            r = client.post('/api/console/send-sms', json={'request_id': 'req-ntfy-0003', 'geoid': '0630000', 'reviewer': 'Op', 'reviewed': True, 'texts': {'en': text}})
        self.assertEqual(r.status_code, 503)


if __name__ == '__main__':
    unittest.main()
