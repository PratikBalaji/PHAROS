"""Resend email adapter for exercise messages. Fixed recipient from server settings; never exposes credentials."""
import os
import re
import httpx
from .photon import PhotonError

API = 'https://api.resend.com/emails'
SUBJECT = 'EXERCISE ONLY — PHAROS wildfire drill message'
FOOTER = '\n\n—\nSent by the PHAROS exercise relay. This is a drill, not a real alert.'
EMAIL_RE = r'[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+'
STATUS_TEXT = {
    'delivered': 'Resend reports email delivered', 'opened': 'Resend reports email delivered', 'clicked': 'Resend reports email delivered',
    'bounced': 'Resend reports email bounced', 'complained': 'Resend reports email marked as spam', 'failed': 'Resend reports email failed',
}


class ResendError(PhotonError):
    pass


def resend_config():
    missing = [k for k in ('RESEND_API_KEY', 'RESEND_TO') if not os.getenv(k)]
    invalid = []
    if os.getenv('RESEND_API_KEY') and not re.fullmatch(r're_[A-Za-z0-9_\-]{10,}', os.environ['RESEND_API_KEY']): invalid.append('RESEND_API_KEY')
    if os.getenv('RESEND_TO') and not re.fullmatch(EMAIL_RE, os.environ['RESEND_TO'].strip()): invalid.append('RESEND_TO')
    frm = os.getenv('RESEND_FROM')
    if frm and not re.fullmatch(r'(.+<' + EMAIL_RE + r'>|' + EMAIL_RE + ')', frm.strip()): invalid.append('RESEND_FROM')
    return dict(provider='resend_email', channel='email', configured=not missing and not invalid, missing=missing, invalid=invalid)


def _from():
    return (os.getenv('RESEND_FROM') or 'PHAROS Exercise <onboarding@resend.dev>').strip()


def _client():
    return httpx.AsyncClient(timeout=12, follow_redirects=False, headers={'Authorization': 'Bearer ' + os.environ['RESEND_API_KEY']})


async def _request(method, url, **kw):
    if not resend_config()['configured']:
        raise ResendError('Resend email is not configured. Set RESEND_API_KEY and RESEND_TO on the server.')
    try:
        async with _client() as c:
            r = await c.request(method, url, **kw)
    except httpx.HTTPError:
        raise ResendError('Resend request failed. Check the provider before retrying.', method == 'POST') from None
    if not r.is_success:
        name = ''
        try: name = re.sub(r'[^a-z_]', '', str(r.json().get('name', ''))[:40])
        except (ValueError, AttributeError): pass
        raise ResendError(f'Resend returned HTTP {r.status_code}{" ("+name+")" if name else ""}. Check the API key, sender and recipient.',
                          method == 'POST' and (r.status_code >= 500 or r.status_code in (408, 429)))
    try: return r.json()
    except ValueError:
        raise ResendError('Resend returned an unreadable response. Check the provider before retrying.', method == 'POST') from None


def _receipt(message_id, event):
    event = event or 'sent'
    return dict(provider='resend_email', message_id=message_id, provider_status=event,
                status=STATUS_TEXT.get(event, 'Accepted by Resend; email delivery unconfirmed'))


async def send_resend(text, key):
    body = {'from': _from(), 'to': [os.environ['RESEND_TO'].strip()], 'subject': SUBJECT, 'text': text + FOOTER}
    data = await _request('POST', API, json=body)
    mid = data.get('id') if isinstance(data, dict) else None
    if not isinstance(mid, str) or not re.fullmatch(r'[0-9a-fA-F-]{36}', mid):
        raise ResendError('Resend returned an unrecognized receipt. Check the provider before retrying.', True)
    return _receipt(mid, 'sent')


async def refresh_resend(message_id):
    if not re.fullmatch(r'[0-9a-fA-F-]{36}', message_id or ''):
        raise ResendError('Not a Resend email id.')
    data = await _request('GET', API + '/' + message_id)
    return _receipt(message_id, data.get('last_event') if isinstance(data, dict) else None)
