"""Photon Beta SMS adapter; never expose credentials or raw provider errors."""
import os
import re
import httpx

ROOT = 'https://api.photon.codes/v1/projects/'
FIELDS = ['PHOTON_API_KEY', 'PHOTON_PROJECT_ID', 'PHOTON_SENDER_ID', 'PHOTON_SPACE_ID']

def valid_id(value, kind):
    return bool(re.fullmatch(r'pho_' + kind + r'_[0-7][0-9a-hjkmnp-tv-z]{25}', value or ''))

def photon_config():
    missing = [key for key in FIELDS if not os.getenv(key)]
    invalid = [key for key, kind in [('PHOTON_PROJECT_ID', 'prj'), ('PHOTON_SENDER_ID', 'usr'), ('PHOTON_SPACE_ID', 'spc')] if os.getenv(key) and not valid_id(os.getenv(key), kind)]
    return dict(provider='photon', channel='sms', configured=not missing and not invalid, missing=missing, invalid=invalid)

def delivery_config():
    provider = os.getenv('PHAROS_DELIVERY_PROVIDER') or ('photon' if any(os.getenv(k) for k in FIELDS) else 'ntfy' if os.getenv('NTFY_TOPIC_URL') else 'inbox')
    if provider == 'photon': return photon_config()
    if provider == 'photon_imessage':
        from .photon_imessage import imessage_config
        return imessage_config()
    if provider == 'resend_email':
        from .resend_email import resend_config
        return resend_config()
    if provider in ('twilio_whatsapp', 'twilio_sms'):
        from .twilio_wa import twilio_config
        return twilio_config()
    return dict(provider=provider, configured=provider=='inbox' or (provider=='ntfy' and bool(os.getenv('NTFY_TOPIC_URL'))), missing=[], invalid=[] if provider in ['inbox','ntfy'] else ['PHAROS_DELIVERY_PROVIDER'])

class PhotonError(Exception):
    def __init__(self, message, uncertain=False):
        super().__init__(message)
        self.uncertain = uncertain

def base_url():
    if not photon_config()['configured']:
        raise PhotonError('Photon SMS is not configured. Set the Photon server secrets and destination IDs.')
    return ROOT + os.environ['PHOTON_PROJECT_ID']

async def request(client, method, url, **kwargs):
    try:
        response = await client.request(method, url, **kwargs)
    except httpx.HTTPError:
        raise PhotonError('Photon request failed. Check the provider before retrying.', method=='POST') from None
    if not response.is_success:
        code=''
        try:
            raw=response.json().get('code')
            code=''.join(ch for ch in str(raw)[:48] if ch.isalnum() or ch in '_-') if raw else ''
        except (ValueError, AttributeError): pass
        raise PhotonError(f'Photon returned HTTP {response.status_code}{" ("+code+")" if code else ""}. Check project access, SMS line and destination setup.', method=='POST' and (response.status_code>=500 or response.status_code in [408,409]))
    try: return response.json()
    except ValueError:
        raise PhotonError('Photon returned an unreadable response. Check the provider before retrying.', method=='POST') from None

def receipt(message):
    if not isinstance(message,dict) or not valid_id(message.get('id'),'msg') or message.get('status') not in ['dispatched','accepted','delivered','failed']:
        seen=message.get('status') if isinstance(message,dict) else None
        detail=''.join(ch for ch in str(seen)[:24] if ch.isalnum() or ch in '_-') if seen is not None else 'none'
        raise PhotonError(f'Photon returned an unrecognized receipt (status: {detail}). Check the provider before retrying.', True)
    status = message['status']
    return dict(provider='photon', message_id=message['id'], provider_status=status, project_id=os.environ['PHOTON_PROJECT_ID'], status='Photon reports SMS delivered' if status=='delivered' else 'Photon reports SMS delivery failed' if status=='failed' else 'Accepted by Photon; SMS delivery unconfirmed')

def client():
    return httpx.AsyncClient(timeout=12, follow_redirects=False, headers={'Authorization':'Bearer '+os.environ['PHOTON_API_KEY']})

async def send_photon(text, key):
    base = base_url()
    async with client() as c:
        space = await request(c,'GET',base+'/spaces/'+os.environ['PHOTON_SPACE_ID'])
        if space.get('platform')!='sms': raise PhotonError('The configured Photon conversation is not an SMS conversation.')
        return receipt(await request(c,'POST',base+'/messages',headers={'idempotency-key':key},json={'senderId':os.environ['PHOTON_SENDER_ID'],'spaceId':os.environ['PHOTON_SPACE_ID'],'content':{'type':'text','format':'plain','text':text}}))

async def refresh_photon(delivery):
    base = base_url()
    if delivery.get('project_id')!=os.environ['PHOTON_PROJECT_ID'] or not valid_id(delivery.get('message_id'),'msg'):
        raise PhotonError('The receipt belongs to a different Photon configuration.')
    async with client() as c:
        return receipt(await request(c,'GET',base+'/messages/'+delivery['message_id']))
