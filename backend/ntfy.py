"""ntfy adapter for the Console: publishes each exercise message to one fixed topic.
The topic URL and optional token come from server settings only; nothing here exposes them."""
import os
import re
from urllib.parse import urlparse
import httpx
from .photon import PhotonError

LANG_NAMES = {'en': 'English', 'es': 'Spanish', 'zh': 'Chinese', 'ko': 'Korean', 'tl': 'Tagalog', 'vi': 'Vietnamese', 'hy': 'Armenian', 'ar': 'Arabic', 'ru': 'Russian', 'strategy': 'Strategy'}
MAX_BODY = 4000


class NtfyError(PhotonError):
    pass


def _topic_ok(url):
    p = urlparse((url or '').strip().rstrip('/'))
    return p.scheme == 'https' and bool(p.netloc) and bool(re.fullmatch(r'/[A-Za-z0-9_-]{1,64}', p.path)) and not p.query and not p.params and not p.username


def _env_url(name):
    return (os.getenv(name) or '').strip()


def ntfy_config():
    missing = [] if os.getenv('NTFY_TOPIC_URL') else ['NTFY_TOPIC_URL']
    invalid = [n for n in ('NTFY_TOPIC_URL', 'NTFY_STRATEGY_TOPIC_URL') if os.getenv(n) and not _topic_ok(os.environ[n])]
    return dict(provider='ntfy', channel='notification', configured=not missing and not invalid, missing=missing, invalid=invalid,
                strategy_topic=bool(os.getenv('NTFY_STRATEGY_TOPIC_URL')) and 'NTFY_STRATEGY_TOPIC_URL' not in invalid)


def _topic_for(key):
    """Strategy texts go to NTFY_STRATEGY_TOPIC_URL when it is set; everything else (language messages) to NTFY_TOPIC_URL."""
    if key.rsplit('-', 1)[-1] == 'strategy' and _env_url('NTFY_STRATEGY_TOPIC_URL'):
        return _env_url('NTFY_STRATEGY_TOPIC_URL').rstrip('/')
    return _env_url('NTFY_TOPIC_URL').rstrip('/')


def _title(key):
    code = key.rsplit('-', 1)[-1]
    return 'PHAROS EXERCISE - ' + LANG_NAMES.get(code, re.sub(r'[^A-Za-z]', '', code).upper()[:12] or 'Message')


def _client():
    headers = {}
    if os.getenv('NTFY_TOKEN'): headers['Authorization'] = 'Bearer ' + os.environ['NTFY_TOKEN']
    return httpx.AsyncClient(timeout=12, follow_redirects=False, headers=headers)


async def send_ntfy(text, key):
    if not ntfy_config()['configured']:
        raise NtfyError('ntfy is not configured. Set NTFY_TOPIC_URL (and optionally NTFY_STRATEGY_TOPIC_URL) to https topic URLs on the server.')
    if len(text) > MAX_BODY:
        raise NtfyError('Message is too long for one ntfy notification.')
    headers = {'Title': _title(key), 'Tags': 'test_tube', 'Priority': '3', 'Content-Type': 'text/plain; charset=utf-8'}
    try:
        async with _client() as c:
            r = await c.post(_topic_for(key), content=text.encode('utf-8'), headers=headers)
    except httpx.HTTPError as e:
        raise NtfyError(f'ntfy request failed ({type(e).__name__}). Check the topic before retrying.', not isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout))) from None
    if not r.is_success:
        raise NtfyError(f'ntfy returned HTTP {r.status_code}. Check the topic URL and token.', r.status_code >= 500 or r.status_code in (408, 429))
    mid = None
    try:
        data = r.json()
        if isinstance(data, dict) and isinstance(data.get('id'), str): mid = re.sub(r'[^A-Za-z0-9_-]', '', data['id'])[:40] or None
    except ValueError: pass
    return dict(provider='ntfy', message_id=mid, provider_status='published', status='Accepted by ntfy; device receipt unverified')
