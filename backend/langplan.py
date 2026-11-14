"""Per-district language plan and translated exercise messages for the console demo.

Flow: district demographic split -> Gemini chooses the send languages (with a deterministic
coverage floor) -> Gemini translates the exercise message -> server adds the fixed exercise marker.
If Gemini is unavailable, the same plan falls back to the existing share-based rule and the fixed
human-written templates, clearly labeled. Nothing here sends anything.
"""
import json
from pathlib import Path

from . import gemini

DATA = Path(__file__).resolve().parents[1] / 'dist' / 'data'
FLOOR_SHARE = 0.10   # any supported language at or above this share is always included
MAX_LANGUAGES = 6


def catalogue():
    return json.loads((DATA / 'alert-templates.json').read_text(encoding='utf-8'))


def district(geoid):
    data = json.loads((DATA / 'districts.json').read_text(encoding='utf-8'))
    for feature in data['features']:
        if feature['properties']['GEOID'] == geoid:
            return feature['properties']
    raise ValueError('Unknown recipient district')


def marker(code, cat=None):
    cat = cat or catalogue()
    return cat['templates'][code].split('{area}')[0].strip()


def english_sentence(area, cat=None):
    """The English message after the marker, with the district name filled in."""
    cat = cat or catalogue()
    return cat['templates']['en'].replace('{area}', area).split(marker('en', cat), 1)[1].strip()


def _split(props):
    return [{'code': l['code'], 'label': l.get('label', l['code']), 'share': float(l.get('share', 0))}
            for l in props.get('languages', []) if float(l.get('share', 0)) > 0]


def rules_languages(props, supported):
    """Existing rule: English plus supported languages ranked by population-weighted share."""
    pop = float(props.get('population', 0))
    ranked = sorted((s for s in _split(props) if s['code'] in supported and s['code'] != 'en'),
                    key=lambda s: s['share'] * pop, reverse=True)
    return ['en'] + [s['code'] for s in ranked]


def apply_floor(chosen, props, supported):
    """Make sure no sizeable supported language is dropped; English first; bounded length."""
    forced = [s['code'] for s in sorted(_split(props), key=lambda s: -s['share'])
              if s['code'] in supported and s['code'] != 'en' and s['share'] >= FLOOR_SHARE]
    out = ['en'] + [c for c in chosen if c != 'en']
    added = [c for c in forced if c not in out]
    out += added
    while len(out) > MAX_LANGUAGES:   # trim only AI extras, never a forced language or English
        extra = [c for c in out if c != 'en' and c not in forced]
        if not extra:
            break
        out.remove(extra[-1])
    return out, added


async def resolve_language_plan(geoid):
    cat = catalogue()
    supported = [l['code'] for l in cat['languages']]
    props = district(geoid)
    split = sorted(_split(props), key=lambda s: -s['share'])
    base = {'geoid': geoid, 'name': props['name'], 'population': props.get('population'),
            'demographics_source': props.get('demographics_source', 'unknown'),
            'split': [dict(s, supported=s['code'] in supported) for s in split]}
    try:
        picked = await gemini.choose_languages(props['name'], split, supported)
        languages, added = apply_floor(picked['languages'], props, supported)
        return {**base, 'source': 'gemini', 'engine': 'Gemini · ' + gemini.model_id(),
                'languages': languages, 'rationale': picked['rationale'], 'added_by_floor': added}
    except gemini.GeminiError as exc:
        languages = rules_languages(props, supported)
        return {**base, 'source': 'rules', 'engine': 'Share-based rule',
                'languages': languages, 'added_by_floor': [], 'fallback_reason': str(exc),
                'rationale': 'Rule: English plus supported languages ranked by population-weighted share.'}


async def resolve_translations(geoid, languages):
    cat = catalogue()
    meta = {l['code']: l for l in cat['languages']}
    languages = [c for c in dict.fromkeys(['en', *languages]) if c in meta]
    area = district(geoid)['name']
    messages = {'en': {'text': cat['templates']['en'].replace('{area}', area), 'reviewed': True, 'rtl': False, 'source': 'template'}}
    targets = {c: meta[c]['label'] for c in languages if c != 'en'}
    translated, reason = {}, None
    if targets:
        try:
            translated = await gemini.translate_message(english_sentence(area, cat), area, targets)
        except gemini.GeminiError as exc:
            reason = str(exc)
    for code in targets:
        if code in translated:
            messages[code] = {'text': f"{marker(code, cat)} {translated[code]}", 'reviewed': False,
                              'rtl': bool(meta[code].get('rtl')), 'source': 'gemini'}
        else:
            messages[code] = {'text': cat['templates'][code].replace('{area}', area), 'reviewed': bool(meta[code]['reviewed']),
                              'rtl': bool(meta[code].get('rtl')), 'source': 'template'}
    used_ai = any(m['source'] == 'gemini' for m in messages.values())
    return {'geoid': geoid, 'name': area, 'languages': languages, 'messages': messages,
            'engine': ('Gemini · ' + gemini.model_id()) if used_ai else 'Fixed templates',
            'fallback_reason': reason, 'requires_language_review': any(not m['reviewed'] for m in messages.values())}
