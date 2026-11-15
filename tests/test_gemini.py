import asyncio
import json
import os
import unittest
from unittest.mock import patch

import httpx

from backend import gemini


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class FakeClient:
    calls = []

    def __init__(self, data=None, exc=None):
        self._data, self._exc = data, exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        FakeClient.calls.append({'url': url, 'json': json, 'headers': headers})
        if self._exc:
            raise self._exc
        return FakeResponse(self._data)


def fake(obj=None, exc=None):
    FakeClient.calls = []
    data = None if obj is None else {'candidates': [{'content': {'parts': [{'text': json.dumps(obj)}]}}]}
    return patch.object(gemini.httpx, 'AsyncClient', lambda *a, **k: FakeClient(data, exc))


def run(coro):
    return asyncio.run(coro)


SPLIT = [{'code': 'en', 'label': 'English only', 'share': 0.38}, {'code': 'hy', 'label': 'Armenian', 'share': 0.34},
         {'code': 'es', 'label': 'Spanish', 'share': 0.12}, {'code': 'ot', 'label': 'Other', 'share': 0.04}]
ALLOWED = ['en', 'es', 'zh', 'ko', 'tl', 'vi', 'hy', 'ar', 'ru']
KEY = {'GEMINI_API_KEY': 'k'}


class ChooseLanguagesTests(unittest.TestCase):
    def test_keeps_only_allowed_present_codes_and_sends_key_header(self):
        out = {'languages': ['hy', 'zh', 'xx', 'hy', 'es'], 'rationale': 'Armenian is 34% and Spanish 12%.'}
        with patch.dict(os.environ, KEY), fake(out):
            plan = run(gemini.choose_languages('Glendale city', SPLIT, ALLOWED))
        self.assertEqual(plan['languages'], ['hy', 'es'])  # zh absent from the split, xx unsupported, duplicate dropped
        self.assertEqual(FakeClient.calls[0]['headers']['x-goog-api-key'], 'k')
        self.assertIn(':generateContent', FakeClient.calls[0]['url'])

    def test_no_usable_output_or_key_or_http_error_raises(self):
        with patch.dict(os.environ, KEY), fake({'languages': ['zh'], 'rationale': 'x'}):
            with self.assertRaises(gemini.GeminiError):
                run(gemini.choose_languages('Glendale city', SPLIT, ALLOWED))
        with patch.dict(os.environ, {'GEMINI_API_KEY': ''}):
            with self.assertRaises(gemini.GeminiError):
                run(gemini.choose_languages('Glendale city', SPLIT, ALLOWED))
        with patch.dict(os.environ, KEY), fake(exc=httpx.ConnectError('x')):
            with self.assertRaises(gemini.GeminiError):
                run(gemini.choose_languages('Glendale city', SPLIT, ALLOWED))


class DraftMessagesTests(unittest.TestCase):
    TARGETS = {'en': 'English', 'hy': 'Armenian'}

    def test_returns_clean_drafts_for_every_language(self):
        out = {'messages': [{'code': 'en', 'text': 'Glendale city is holding a wildfire drill. This is not a real emergency.'},
                            {'code': 'hy', 'text': 'Glendale city: սա հրդեհի վարժանք է, իրական արտակարգ իրավիճակ չէ։'}, {'code': 'xx', 'text': 'ignored'}]}
        with patch.dict(os.environ, KEY), fake(out):
            drafts = run(gemini.draft_messages('Glendale city', self.TARGETS, 'a drill'))
        self.assertEqual(set(drafts), {'en', 'hy'})
        self.assertIn('scenario_context', FakeClient.calls[0]['json']['contents'][0]['parts'][0]['text'])

    def test_rejects_drafts_with_invented_details_or_missing_area(self):
        bad_variants = ['Glendale city drill: go to Victory Park at 3pm.',            # digits
                        'Glendale city drill, see http://example.com for routes.',      # link
                        'A wildfire drill is happening nearby. Not a real emergency.',  # area name missing
                        'Glendale city',                                                # too short
                        'Glendale city drill. ' + 'x' * 500]                            # too long
        for text in bad_variants:
            out = {'messages': [{'code': 'en', 'text': text}]}
            with patch.dict(os.environ, KEY), fake(out):
                with self.assertRaises(gemini.GeminiError):
                    run(gemini.draft_messages('Glendale city', {'en': 'English'}))

    def test_missing_language_raises_so_callers_can_fall_back(self):
        out = {'messages': [{'code': 'en', 'text': 'Glendale city is holding a wildfire drill. This is not a real emergency.'}]}
        with patch.dict(os.environ, KEY), fake(out):
            with self.assertRaises(gemini.GeminiError):
                run(gemini.draft_messages('Glendale city', self.TARGETS))


class TranslateTests(unittest.TestCase):
    def test_returns_translations_that_name_the_area(self):
        out = {'translations': [{'code': 'es', 'text': 'Glendale city: hay un simulacro de evacuación.'}]}
        with patch.dict(os.environ, KEY), fake(out):
            got = run(gemini.translate_message('Glendale city: a drill.', 'Glendale city', {'es': 'Spanish'}))
        self.assertEqual(got, {'es': 'Glendale city: hay un simulacro de evacuación.'})

    def test_rejects_translation_that_lost_the_area_or_missing_language(self):
        out = {'translations': [{'code': 'es', 'text': 'Hay un simulacro de evacuación en la zona.'}]}
        with patch.dict(os.environ, KEY), fake(out):
            with self.assertRaises(gemini.GeminiError):
                run(gemini.translate_message('Glendale city: a drill.', 'Glendale city', {'es': 'Spanish'}))
        with patch.dict(os.environ, KEY), fake({'translations': []}):
            with self.assertRaises(gemini.GeminiError):
                run(gemini.translate_message('Glendale city: a drill.', 'Glendale city', {'es': 'Spanish'}))


if __name__ == '__main__':
    unittest.main()
