# Twilio WhatsApp setup (sandbox, exercise only)

Free to try: a Twilio trial account includes credit, and the WhatsApp **sandbox** needs no Meta approval. Not for real resident alerting.

1. Create an account at https://www.twilio.com/try-twilio and verify your email and phone.
2. In the Twilio Console: **Messaging, Try it out, Send a WhatsApp message**. That page shows the **sandbox number** (usually +1 415 523 8886) and your **join code** (`join two-words`).
3. From your phone's WhatsApp, message the sandbox number: `join <your-code>`. Twilio replies to confirm. Repeat if it lapses (about 72 hours idle).
4. **Account SID** (starts `AC`) and **Auth Token**: Console home page, "Account Info" box (click the eye icon to reveal the token).
5. In Vercel, Settings, Environment Variables (Production), add:
   - `PHAROS_DELIVERY_PROVIDER` = `twilio_whatsapp`
   - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` (secret)
   - `TWILIO_WHATSAPP_FROM` = the sandbox number, e.g. `+14155238886`
   - `TWILIO_TO` = your own WhatsApp number in international format, e.g. `+15551234567`
6. Redeploy, check `/api/health` shows `delivery.provider` `twilio_whatsapp` and `configured: true`, then run the sender (see `docs/PHOTON_SETUP.md`, scripts section) starting with one run.

Receipts come from Twilio: queued, sent, delivered, read or failed. The sandbox allows free-form text, so all languages work.
