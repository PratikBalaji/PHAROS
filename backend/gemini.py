"""Gemini calls for the console: choose send-languages from a district's demographic split,
and translate the exercise message. Both raise GeminiError on any problem so callers can fall
back to rules and fixed templates.

The model only ever supplies (a) a list of language codes and a short rationale, and (b) the
translated body of an English exercise sentence. The server owns the per-language exercise
marker, checks the district name survived translation, and bounds length. Output is untrusted.
"""
import json
import os

import httpx

GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
DEFAULT_MODEL = 'gemini-3.5-flash-lite'
MAX_BODY = 700
MAX_DRAFT = 420
MAX_RATIONALE = 320


class GeminiError(Exception):
    pass


def configured():
    return bool(os.getenv('GEMINI_API_KEY'))


def model_id():
    return os.getenv('GEMINI_MODEL', DEFAULT_MODEL)


async def _generate(system, user, schema):
    key = os.getenv('GEMINI_API_KEY')
    if not key:
        raise GeminiError('GEMINI_API_KEY is not configured')
    body = {
        'systemInstruction': {'parts': [{'text': system}]},
        'contents': [{'parts': [{'text': user}]}],
        'generationConfig': {'temperature': 0.2, 'responseMimeType': 'application/json', 'responseSchema': schema},
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(GEMINI_URL.format(model=model_id()), json=body,
                                         headers={'x-goog-api-key': key, 'Content-Type': 'application/json'})
            response.raise_for_status()
            data = response.json()
        return json.loads(data['candidates'][0]['content']['parts'][0]['text'])
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        raise GeminiError('Gemini request failed')


PLAN_SYSTEM = (
    'You help an emergency-communications operator choose which languages to send a wildfire EXERCISE '
    'message in, for one district. Use only the demographic split provided (share = fraction of residents '
    'who speak that language at home). Choose only from the allowed language codes that appear in the split. '
    'Prefer languages with the largest shares; include a smaller language only if its share is meaningful. '
    'Always include English. Give a one-sentence rationale citing the shares. Do not invent data.'
)


async def choose_languages(name, split, allowed):
    """split: [{code,label,share}], allowed: supported codes. Returns {'languages': [...], 'rationale': str}."""
    facts = {'district': name, 'allowed_codes': allowed,
             'demographic_split': [{'code': s['code'], 'label': s.get('label', s['code']), 'share': round(float(s['share']), 4)} for s in split]}
    result = await _generate(PLAN_SYSTEM, json.dumps(facts, ensure_ascii=False), {
        'type': 'OBJECT',
        'properties': {'languages': {'type': 'ARRAY', 'items': {'type': 'STRING'}}, 'rationale': {'type': 'STRING'}},
        'required': ['languages', 'rationale'],
    })
    present = {s['code'] for s in split if float(s.get('share', 0)) > 0}
    chosen = []
    for code in result.get('languages') or []:
        if isinstance(code, str) and code in allowed and (code in present or code == 'en') and code not in chosen:
            chosen.append(code)
    rationale = result.get('rationale')
    if not chosen or not isinstance(rationale, str) or not rationale.strip():
        raise GeminiError('Gemini returned no usable language plan')
    return {'languages': chosen, 'rationale': ' '.join(rationale.split())[:MAX_RATIONALE]}


TRANSLATE_SYSTEM = (
    'Translate a short public-safety EXERCISE (drill) message into each requested language. Keep the meaning '
    'exactly: it is a drill, not an evacuation order. Keep the place name unchanged and use the target '
    'language and script. Do not add instructions, routes, times or shelters. Do not add any disclaimer prefix; '
    'the system adds it. Return one translation per requested language code.'
)


async def translate_message(english_sentence, area, targets):
    """targets: {code: language name}. Returns {code: translated sentence}; raises if any is unusable."""
    facts = {'english': english_sentence, 'place_name': area, 'languages': targets}
    result = await _generate(TRANSLATE_SYSTEM, json.dumps(facts, ensure_ascii=False), {
        'type': 'OBJECT',
        'properties': {'translations': {'type': 'ARRAY', 'items': {
            'type': 'OBJECT', 'properties': {'code': {'type': 'STRING'}, 'text': {'type': 'STRING'}}, 'required': ['code', 'text']}}},
        'required': ['translations'],
    })
    out = {}
    for item in result.get('translations') or []:
        code = item.get('code') if isinstance(item, dict) else None
        text = item.get('text') if isinstance(item, dict) else None
        if code in targets and code not in out and isinstance(text, str):
            text = ' '.join(text.split())
            if 10 <= len(text) <= MAX_BODY and area.lower() in text.lower():
                out[code] = text
    missing = [c for c in targets if c not in out]
    if missing:
        raise GeminiError('Gemini translation missing or invalid for: ' + ', '.join(missing))
    return out


POLISH_SYSTEM = (
    'Rewrite a short wildfire EXERCISE (drill) evacuation-strategy text message in plain, calm language at a '
    '6th-grade reading level, under 420 characters. Use only the facts provided. Keep the place name, assembly '
    'point name, minutes and kilometres exactly as given; never add roads, times, shelters or instructions that '
    'are not in the facts. If outcome is "withheld", say no safe route is known and do not name any route or '
    'destination. It must stay clear that this is a drill and not an evacuation order. Do not add any disclaimer '
    'prefix; the system adds it.'
)


async def polish_strategy(facts, draft):
    """Rewrite the deterministic English draft; returns plain text, raises GeminiError if unusable."""
    result = await _generate(POLISH_SYSTEM, json.dumps({'facts': facts, 'draft': draft}, ensure_ascii=False), {
        'type': 'OBJECT', 'properties': {'text': {'type': 'STRING'}}, 'required': ['text']})
    text = result.get('text')
    if not isinstance(text, str):
        raise GeminiError('Gemini returned no usable strategy text')
    text = ' '.join(text.split())
    if not 20 <= len(text) <= MAX_BODY:
        raise GeminiError('Gemini strategy text had an unusable length')
    return text


DRAFT_SYSTEM = (
    'You write short public-safety notifications for a wildfire evacuation EXERCISE (a drill) that residents of one district '
    'will read on their phone. Write each requested language natively, in its own script, in calm plain words at about a 6th-grade '
    'reading level, 2 to 3 sentences. Each version must (1) name the place exactly as given, (2) say clearly that this is a drill '
    'or exercise and NOT a real emergency or evacuation order, and (3) tell people that in a real event they should follow the '
    'official instructions of their local emergency authority. The versions must carry the same meaning but may be worded naturally '
    'for each language, not word-for-word. Never invent or mention routes, roads, shelters, assembly points, times, phone numbers, '
    'links or instructions to leave. Do not add any "EXERCISE ONLY" style prefix; the system adds it. One item per requested code.'
)


def _draft_ok(text, area):
    low = text.lower()
    return (20 <= len(text) <= MAX_DRAFT and area.lower() in low and 'http' not in low and 'www.' not in low
            and '@' not in text and not any(ch.isdigit() for ch in text))


async def draft_messages(area, targets, context=None):
    """Gemini writes the exercise message in each language itself (not a translation of a fixed sentence).
    targets: {code: language name}. Returns {code: body}; raises GeminiError if any requested language is unusable."""
    facts = {'place_name': area, 'languages': targets}
    if context:
        facts['scenario_context'] = ' '.join(str(context).split())[:200]
    result = await _generate(DRAFT_SYSTEM, json.dumps(facts, ensure_ascii=False), {
        'type': 'OBJECT',
        'properties': {'messages': {'type': 'ARRAY', 'items': {
            'type': 'OBJECT', 'properties': {'code': {'type': 'STRING'}, 'text': {'type': 'STRING'}}, 'required': ['code', 'text']}}},
        'required': ['messages'],
    })
    out = {}
    for item in result.get('messages') or []:
        code = item.get('code') if isinstance(item, dict) else None
        text = item.get('text') if isinstance(item, dict) else None
        if code in targets and code not in out and isinstance(text, str):
            text = ' '.join(text.split())
            if _draft_ok(text, area):
                out[code] = text
    missing = [c for c in targets if c not in out]
    if missing:
        raise GeminiError('Gemini draft missing or invalid for: ' + ', '.join(missing))
    return out
