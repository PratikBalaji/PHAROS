# ntfy delivery (exercise only)

ntfy publishes each message to a topic, and every phone subscribed to that topic shows it as a push notification. No account is needed for ntfy.sh.

1. Install the **ntfy** app (iOS or Android) and **Subscribe to topic**: enter your topic name (the last part of the URL, for example `pharos-drill-x7k2m9`).
2. Vercel, Production environment variables:
   - `PHAROS_DELIVERY_PROVIDER` = `ntfy`
   - `NTFY_TOPIC_URL` = `https://ntfy.sh/<your-topic>` (https, exactly one path segment, no query string)
   - `NTFY_TOKEN` = optional, only if your topic needs an access token
3. Redeploy and check `/api/health` shows `"provider": "ntfy"` and `"configured": true`.

What gets published: with this provider the Console Send button and `scripts/send_exercise_sms.mjs` publish each AI-translated language message and the strategy text. Each notification is titled `PHAROS EXERCISE - <Language>` (ASCII headers) with the full UTF-8 text, including Armenian, Chinese, Korean and Arabic, in the body. Every text still begins with its exercise marker.

**Security:** a topic on the public ntfy.sh has no login. Anyone who guesses the name can read the drill messages and publish fake ones. Use a long random topic name (not `PHAROS_LANG`) or an access token, and keep the topic out of the repo.

ntfy reports no device receipts, so the PHAROS result means "accepted by ntfy"; confirm on the phone.
