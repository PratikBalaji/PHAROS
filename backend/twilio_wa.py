"""Twilio WhatsApp adapter (sandbox-friendly). Exercise texts only; never exposes credentials or raw errors."""
import os
import re
import httpx
from .photon import PhotonError

API = 'https://api.twilio.com/2010-04-01/Accounts/'
PROVIDERS = ('twilio_whatsapp', 'twilio_sms')
STATUSES = ['accepted', 'scheduled', 'queued', 'sending', 'sent', 'delivered', 'read', 'undelivered', 'failed', 'receiving', 'received']
MAX_BODY = 1600


class TwilioError(PhotonError):
    pass


def _number(value):
    v = re.sub(r'^whatsapp:', '', (value or '').strip()).replace(' ', '')
    return v if re.fullmatch(r'\+[1-9]\d{7,14}', v) else None


def _sms():
    return os.getenv('PHAROS_DELIVERY_PROVIDER') == 'twilio_sms'


def _from_var():
    # SMS uses TWILIO_FROM (your Twilio number); WhatsApp uses TWILIO_WHATSAPP_FROM (e.g. the sandbox number).
    return 'TWILIO_FROM' if _sms() else 'TWILIO_WHATSAPP_FROM'


def _label():
    return 'SMS' if _sms() else 'WhatsApp'


def _addr(number):
    return number if _sms() else 'whatsapp:' + number


def twilio_config():
    fields = ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', _from_var(), 'TWILIO_TO']
    missing = [k for k in fields if not os.getenv(k)]
    invalid = []
    if os.getenv('TWILIO_ACCOUNT_SID') and not re.fullmatch(r'AC[0-9a-f]{32}', os.environ['TWILIO_ACCOUNT_SID']): invalid.append('TWILIO_ACCOUNT_SID')
    for k in (_from_var(), 'TWILIO_TO'):
        if os.getenv(k) and not _number(os.environ[k]): invalid.append(k)
    return dict(provider='twilio_sms' if _sms() else 'twilio_whatsapp', channel='sms' if _sms() else 'whatsapp', configured=not missing and not invalid, missing=missing, invalid=invalid)


def _client():
    return httpx.AsyncClient(timeout=12, follow_redirects=False, auth=(os.environ['TWILIO_ACCOUNT_SID'], os.environ['TWILIO_AUTH_TOKEN']))


def _base():
    if not twilio_config()['configured']:
        raise TwilioError('Twilio WhatsApp is not configured. Set the Twilio server secrets and numbers.')
    return API + os.environ['TWILIO_ACCOUNT_SID']


async def _request(method, url, **kw):
    try:
        async with _client() as c:
            r = await c.request(method, url, **kw)
    except httpx.HTTPError:
        raise TwilioError('Twilio request failed. Check the provider before retrying.', method == 'POST') from None
    if not r.is_success:
        code = ''
        try:
            raw = r.json().get('code')
            code = ''.join(ch for ch in str(raw)[:12] if ch.isdigit()) if raw else ''
        except (ValueError, AttributeError): pass
        raise TwilioError(f'Twilio returned HTTP {r.status_code}{" (error "+code+")" if code else ""}. Check the sandbox join, numbers and account.',
                          method == 'POST' and (r.status_code >= 500 or r.status_code in (408, 429)))
    try: return r.json()
    except ValueError:
        raise TwilioError('Twilio returned an unreadable response. Check the provider before retrying.', method == 'POST') from None


def receipt(message):
    sid = message.get('sid') if isinstance(message, dict) else None
    status = message.get('status') if isinstance(message, dict) else None
    if not isinstance(sid, str) or not re.fullmatch(r'(SM|MM)[0-9a-f]{32}', sid) or status not in STATUSES:
        seen = ''.join(ch for ch in str(status)[:20] if ch.isalnum() or ch in '_-')
        raise TwilioError(f'Twilio returned an unrecognized receipt (status: {seen or "none"}). Check the provider before retrying.', True)
    text = (f'Twilio reports {_label()} delivered' if status in ('delivered', 'read')
            else f'Twilio reports {_label()} delivery failed' if status in ('failed', 'undelivered')
            else f'Accepted by Twilio; {_label()} delivery unconfirmed')
    return dict(provider='twilio_sms' if _sms() else 'twilio_whatsapp', message_id=sid, provider_status=status, status=text)


async def send_twilio(text, key):
    if len(text) > MAX_BODY:
        raise TwilioError('Message is longer than WhatsApp allows through Twilio (1600 characters).')
    data = {'From': _addr(_number(os.environ[_from_var()])), 'To': _addr(_number(os.environ['TWILIO_TO'])), 'Body': text}
    return receipt(await _request('POST', _base() + '/Messages.json', data=data))


async def refresh_twilio(message_id):
    if not re.fullmatch(r'(SM|MM)[0-9a-f]{32}', message_id or ''):
        raise TwilioError('Not a Twilio message id.')
    return receipt(await _request('GET', _base() + '/Messages/' + message_id + '.json'))
