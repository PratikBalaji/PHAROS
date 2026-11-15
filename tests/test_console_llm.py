import asyncio
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault('PHAROS_DB', tempfile.mktemp(suffix='.sqlite3'))

from fastapi.testclient import TestClient

from backend import app as appmod, gemini, langplan
from backend.photon import PhotonError

client = TestClient(appmod.app)
GLENDALE = '0630000'   # committed ACS dataset: Armenian-heavy (C16001 'Other Indo-European') ~38%, English ~34%, Spanish ~14%
SIERRA = '0671806'     # mostly English


def run(coro):
    return asyncio.run(coro)


class LanguagePlanTests(unittest.TestCase):
    def test_floor_adds_sizeable_languages_the_model_left_out(self):
        picked = {'languages': ['en'], 'rationale': 'Mostly English.'}
        with patch.object(gemini, 'choose_languages', AsyncMock(return_value=picked)):
            plan = run(langplan.resolve_language_plan(GLENDALE))
        self.assertEqual(plan['source'], 'gemini')
        self.assertEqual(plan['languages'][0], 'en')
        self.assertIn('hy', plan['languages'])
        self.assertIn('es', plan['languages'])
        self.assertEqual(set(plan['added_by_floor']), {'hy', 'es'})
        self.assertTrue(any(s['code'] == 'hy' and s['share'] > 0.3 for s in plan['split']))

    def test_gemini_failure_falls_back_to_rule_and_says_so(self):
        with patch.object(gemini, 'choose_languages', AsyncMock(side_effect=gemini.GeminiError('down'))):
            plan = run(langplan.resolve_language_plan(GLENDALE))
        self.assertEqual(plan['source'], 'rules')
        self.assertEqual(plan['engine'], 'Share-based rule')
        self.assertEqual(plan['languages'][:2], ['en', 'hy'])
        self.assertEqual(plan['fallback_reason'], 'down')

    def test_unknown_district_is_422(self):
        self.assertEqual(client.post('/api/console/language-plan', json={'geoid': 'nope-1'}).status_code, 422)

    def test_endpoint_without_key_uses_rules(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}):
            body = client.post('/api/console/language-plan', json={'geoid': SIERRA}).json()
        self.assertEqual(body['source'], 'rules')
        self.assertEqual(body['languages'][0], 'en')


class TranslationTests(unittest.TestCase):
    def test_server_adds_marker_and_flags_review(self):
        tr = AsyncMock(return_value={'hy': 'Glendale city: Հրդեհի տարհանման վարժանք է:'})
        with patch.object(gemini, 'translate_message', tr):
            out = run(langplan.resolve_translations(GLENDALE, ['hy']))
        hy = out['messages']['hy']
        self.assertTrue(hy['text'].startswith(langplan.marker('hy')))
        self.assertEqual(hy['source'], 'gemini')
        self.assertFalse(hy['reviewed'])
        self.assertTrue(out['messages']['en']['reviewed'])
        self.assertEqual(out['messages']['en']['source'], 'template')
        self.assertTrue(out['engine'].startswith('Gemini'))

    def test_failure_uses_fixed_templates(self):
        with patch.object(gemini, 'translate_message', AsyncMock(side_effect=gemini.GeminiError('bad'))):
            out = run(langplan.resolve_translations(GLENDALE, ['hy', 'es']))
        self.assertEqual(out['engine'], 'Fixed templates')
        self.assertTrue(all(m['source'] == 'template' for m in out['messages'].values()))
        self.assertEqual(out['fallback_reason'], 'bad')
        self.assertTrue(out['messages']['hy']['text'].startswith(langplan.marker('hy')))


def texts(codes=('en', 'es')):
    cat = langplan.catalogue()
    return {c: cat['templates'][c].replace('{area}', 'Glendale city') for c in codes}


def sms_body(request_id, **kw):
    body = {'request_id': request_id, 'geoid': GLENDALE, 'reviewer': 'Op', 'reviewed': True, 'texts': texts()}
    body.update(kw)
    return body


PHOTON = {'provider': 'photon', 'configured': True, 'missing': [], 'invalid': []}
INBOX = {'provider': 'inbox', 'configured': True, 'missing': [], 'invalid': []}
RECEIPT = {'provider': 'photon', 'message_id': 'pho_msg_x', 'provider_status': 'accepted', 'status': 'Accepted by Photon; SMS delivery unconfirmed'}


class SendSmsTests(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(client.post('/api/console/send-sms', json=sms_body('req-valid-01', reviewed=False)).status_code, 400)
        self.assertEqual(client.post('/api/console/send-sms', json=sms_body('req-valid-02', texts={'en': 'Evacuate now.'})).status_code, 400)
        wrong_area = {'en': langplan.catalogue()['templates']['en'].replace('{area}', 'Somewhere')}
        self.assertEqual(client.post('/api/console/send-sms', json=sms_body('req-valid-03', texts=wrong_area)).status_code, 400)

    def test_inbox_never_calls_photon(self):
        boom = AsyncMock(side_effect=AssertionError('photon must not be called'))
        with patch.object(appmod, 'delivery_config', lambda: INBOX), patch.object(appmod, 'send_photon', boom):
            r = client.post('/api/console/send-sms', json=sms_body('req-inbox-01'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['counts']['recorded'], 2)
        self.assertFalse(r.json()['public_alert'])
        boom.assert_not_called()

    def test_photon_sends_one_per_language_and_is_idempotent(self):
        send = AsyncMock(return_value=RECEIPT)
        with patch.object(appmod, 'delivery_config', lambda: PHOTON), patch.object(appmod, 'send_photon', send):
            first = client.post('/api/console/send-sms', json=sms_body('req-photon-01')).json()
            again = client.post('/api/console/send-sms', json=sms_body('req-photon-01')).json()
        self.assertEqual(send.await_count, 2)
        self.assertEqual([c.args[1] for c in send.await_args_list], ['pharos-sms-req-photon-01-en', 'pharos-sms-req-photon-01-es'])
        self.assertEqual(first['counts']['submitted'], 2)
        self.assertTrue(all(r['duplicate'] for r in again['results']))
        self.assertEqual(first['results'][0]['message_id'], 'pho_msg_x')

    def test_uncertain_blocks_resend_but_rejection_allows_retry(self):
        uncertain = AsyncMock(side_effect=PhotonError('timeout', True))
        with patch.object(appmod, 'delivery_config', lambda: PHOTON), patch.object(appmod, 'send_photon', uncertain):
            client.post('/api/console/send-sms', json=sms_body('req-uncert-01', texts=texts(('en',))))
            client.post('/api/console/send-sms', json=sms_body('req-uncert-01', texts=texts(('en',))))
        self.assertEqual(uncertain.await_count, 1)
        rejected = AsyncMock(side_effect=PhotonError('HTTP 403', False))
        with patch.object(appmod, 'delivery_config', lambda: PHOTON), patch.object(appmod, 'send_photon', rejected):
            r = client.post('/api/console/send-sms', json=sms_body('req-reject-01', texts=texts(('en',)))).json()
            client.post('/api/console/send-sms', json=sms_body('req-reject-01', texts=texts(('en',))))
        self.assertEqual(r['counts']['rejected'], 1)
        self.assertEqual(rejected.await_count, 2)

    def test_unconfigured_provider_is_503(self):
        off = {'provider': 'photon', 'configured': False, 'missing': ['PHOTON_API_KEY'], 'invalid': []}
        with patch.object(appmod, 'delivery_config', lambda: off):
            self.assertEqual(client.post('/api/console/send-sms', json=sms_body('req-off-0001')).status_code, 503)


FACTS = {'run_name': 'Altadena Ridge', 'outcome': 'rerouted', 'assembly': 'Victory Park', 'minutes': 9, 'km': 4.2}
WITHHELD = {'run_name': 'Verdugo Hills', 'outcome': 'withheld'}


def strategy_body(request_id, text, facts=FACTS, **kw):
    body = {'request_id': request_id, 'geoid': GLENDALE, 'reviewer': 'Op', 'reviewed': True, 'facts': facts, 'text': text}
    body.update(kw)
    return body


class StrategyTests(unittest.TestCase):
    def test_draft_uses_only_planner_facts(self):
        text = langplan.strategy_draft('Glendale city', FACTS)
        self.assertTrue(text.startswith(langplan.marker('en')))
        for needle in ('Victory Park', '9 min', '4.2 km', 'Glendale city'):
            self.assertIn(needle, text)
        held = langplan.strategy_draft('Glendale city', WITHHELD)
        self.assertIn('no safe route', held)
        self.assertNotIn('Victory Park', held)
        self.assertNotIn('min,', held)

    def test_gemini_polish_is_used_when_it_keeps_the_facts(self):
        good = 'Glendale city, drill: the fire moved, so you now head to Victory Park, about 9 minutes away. This is a drill.'
        with patch.object(gemini, 'polish_strategy', AsyncMock(return_value=good)):
            out = run(langplan.resolve_strategy(GLENDALE, FACTS))
        self.assertEqual(out['source'], 'gemini')
        self.assertTrue(out['text'].startswith(langplan.marker('en')))

    def test_polish_that_drops_facts_or_fails_falls_back_to_the_draft(self):
        bad = 'Go somewhere safe, quickly. This is a drill.'
        with patch.object(gemini, 'polish_strategy', AsyncMock(return_value=bad)):
            out = run(langplan.resolve_strategy(GLENDALE, FACTS))
        self.assertEqual((out['source'], out['text']), ('template', out['draft']))
        with patch.object(gemini, 'polish_strategy', AsyncMock(side_effect=gemini.GeminiError('down'))):
            out = run(langplan.resolve_strategy(GLENDALE, FACTS))
        self.assertEqual(out['fallback_reason'], 'down')

    def test_withheld_text_may_not_invent_a_destination(self):
        invented = f"{langplan.marker('en')} Glendale city: no safe route. Try Victory Park. This is a drill."
        self.assertFalse(langplan.strategy_valid(invented, 'Glendale city', {**WITHHELD, 'assembly': 'Victory Park'}))
        self.assertTrue(langplan.strategy_valid(langplan.strategy_draft('Glendale city', WITHHELD), 'Glendale city', WITHHELD))

    def test_plan_endpoint_validates_facts(self):
        self.assertEqual(client.post('/api/console/strategy-plan', json={'geoid': GLENDALE, 'facts': {'run_name': 'X', 'outcome': 'arrived'}}).status_code, 422)
        self.assertEqual(client.post('/api/console/strategy-plan', json={'geoid': GLENDALE, 'facts': {**FACTS, 'outcome': 'teleported'}}).status_code, 422)
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}):
            r = client.post('/api/console/strategy-plan', json={'geoid': GLENDALE, 'facts': WITHHELD})
        self.assertEqual((r.status_code, r.json()['source']), (200, 'template'))

    def test_send_gates(self):
        good = langplan.strategy_draft('Glendale city', FACTS)
        self.assertEqual(client.post('/api/console/strategy-sms', json=strategy_body('req-strat-g1', good, reviewed=False)).status_code, 400)
        self.assertEqual(client.post('/api/console/strategy-sms', json=strategy_body('req-strat-g2', 'Evacuate right now to the park please.')).status_code, 400)
        self.assertEqual(client.post('/api/console/strategy-sms', json=strategy_body('req-strat-g3', good.replace('Victory Park', 'Elsewhere'))).status_code, 400)
        self.assertEqual(client.post('/api/console/strategy-sms', json=strategy_body('req-strat-g4', good, reviewer=' ')).status_code, 400)

    def test_send_once_per_request_and_receipts_survive_without_storage(self):
        good = langplan.strategy_draft('Glendale city', FACTS)
        send = AsyncMock(return_value=RECEIPT)
        with patch.object(appmod, 'delivery_config', lambda: PHOTON), patch.object(appmod, 'send_photon', send):
            first = client.post('/api/console/strategy-sms', json=strategy_body('req-strat-01', good)).json()
            again = client.post('/api/console/strategy-sms', json=strategy_body('req-strat-01', good)).json()
        self.assertEqual(send.await_count, 1)
        self.assertEqual(send.await_args.args[1], 'pharos-sms-req-strat-01-strategy')
        self.assertEqual((first['result']['state'], first['public_alert']), ('submitted', False))
        self.assertTrue(again['result']['duplicate'])
        fresh = {'provider': 'photon', 'message_id': 'pho_msg_x', 'provider_status': 'delivered', 'status': 'Photon reports SMS delivered'}
        with patch.object(appmod, 'refresh_photon', AsyncMock(return_value=fresh)), patch.dict(os.environ, {'PHOTON_PROJECT_ID': 'pho_prj_x'}):
            r = client.get('/api/console/sms-status', params={'ids': 'pho_msg_x,pho_msg_x'}).json()
        self.assertEqual(r['receipts'], [{'message_id': 'pho_msg_x', 'provider_status': 'delivered', 'status': 'Photon reports SMS delivered'}])

    def test_status_reports_per_id_errors(self):
        with patch.object(appmod, 'refresh_photon', AsyncMock(side_effect=PhotonError('nope'))):
            r = client.get('/api/console/sms-status', params={'ids': 'bad'}).json()
        self.assertEqual(r['receipts'], [{'message_id': 'bad', 'error': 'nope'}])


if __name__ == '__main__':
    unittest.main()
