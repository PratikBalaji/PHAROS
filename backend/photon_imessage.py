"""Photon hosted iMessage adapter (POST /v1/projects/{id}/platforms/imessage/send).
Recipient is fixed by server settings; credentials and raw provider errors are never exposed."""
import os
import re
import httpx
from .photon import PhotonError, valid_id

DEFAULT_BASE = 'https://api.beta.photon.codes'
MAX_TEXT = 2000


class PhotonImessageError(PhotonError):
    pass


def imessage_config():
    missing = [k for k in ('PHOTON_API_KEY', 'PHOTON_PROJECT_ID', 'PHOTON_IMESSAGE_TO') if not os.getenv(k)]
    invalid = []
    if os.getenv('PHOTON_PROJECT_ID') and not valid_id(os.environ['PHOTON_PROJECT_ID'], 'prj'): invalid.append('PHOTON_PROJECT_ID')
    to = os.getenv('PHOTON_IMESSAGE_TO')
    if to and not re.fullmatch(r'\+[1-9]\d{7,14}|[^@\s]+@[^@\s]+\.[^@\s]+', to.strip()): invalid.append('PHOTON_IMESSAGE_TO')
    base = os.getenv('PHOTON_API_BASE')
    if base and not re.fullmatch(r'https://[a-z0-9.-]+\.photon\.codes', base.strip()): invalid.append('PHOTON_API_BASE')
    return dict(provider='photon_imessage', channel='imessage', configured=not missing and not invalid, missing=missing, invalid=invalid)


def _url():
    return (os.getenv('PHOTON_API_BASE') or DEFAULT_BASE).strip() + '/v1/projects/' + os.environ['PHOTON_PROJECT_ID'] + '/platforms/imessage/send'


def _client():
    return httpx.AsyncClient(timeout=15, follow_redirects=False, headers={'Authorization': 'Bearer ' + os.environ['PHOTON_API_KEY']})


async def send_imessage(text, key):
    if not imessage_config()['configured']:
        raise PhotonImessageError('Photon iMessage is not configured. Set PHOTON_API_KEY, PHOTON_PROJECT_ID and PHOTON_IMESSAGE_TO on the server.')
    if len(text) > MAX_TEXT:
        raise PhotonImessageError('Message is too long for one iMessage.')
    try:
        async with _client() as c:
            r = await c.post(_url(), json={'to': os.environ['PHOTON_IMESSAGE_TO'].strip(), 'message': text})
    except httpx.HTTPError as e:
        kind = type(e).__name__  # e.g. ConnectError, ConnectTimeout, ReadTimeout: safe to show, no secrets
        # Only a read timeout or dropped response may mean the message went out; a failed connect never did.
        sent_maybe = isinstance(e, (httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError, httpx.WriteTimeout))
        raise PhotonImessageError(f'Photon request failed ({kind}). Check the provider before retrying.', sent_maybe) from None
    if not r.is_success:
        code = ''
        try:
            raw = r.json()
            raw = raw.get('code') or raw.get('error') or raw.get('title') if isinstance(raw, dict) else None
            code = re.sub(r'[^A-Za-z0-9_ -]', '', str(raw))[:48] if raw else ''
        except ValueError: pass
        raise PhotonImessageError(f'Photon returned HTTP {r.status_code}{" ("+code+")" if code else ""}. Check the project, recipient and iMessage setup.',
                                  r.status_code >= 500 or r.status_code in (408, 409, 429))
    mid = None
    try:
        data = r.json()
        if isinstance(data, dict):
            for k in ('id', 'messageId', 'message_id'):
                if isinstance(data.get(k), str): mid = re.sub(r'[^A-Za-z0-9_-]', '', data[k])[:80] or None; break
    except ValueError: pass
    # The documented success is HTTP 200 only; delivery is not reported back.
    return dict(provider='photon_imessage', message_id=mid, provider_status='accepted', status='Accepted by Photon; iMessage delivery unconfirmed')
