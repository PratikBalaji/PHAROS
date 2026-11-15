# Resend email delivery (exercise only)

Free tier is enough for a demo. Works from Vercel (HTTPS API), so the Console and the sender script deliver with no tunnel.

1. Sign up at https://resend.com and open **API Keys**, then **Create API Key** (name it PHAROS, permission "Sending access"). Copy the `re_...` key once.
2. Vercel, Production environment variables:
   - `PHAROS_DELIVERY_PROVIDER` = `resend_email`
   - `RESEND_API_KEY` = the `re_...` key (secret)
   - `RESEND_TO` = **the email address you signed up to Resend with**
   - `RESEND_FROM` (optional) = leave empty to use `PHAROS Exercise <onboarding@resend.dev>`
3. Redeploy, check `/api/health` shows `resend_email`, `configured: true`.

Limit: without a verified domain, Resend's test sender can only deliver to your own account email. To email others, verify a domain in Resend and set `RESEND_FROM` to an address on it.
Receipts: Resend reports delivered, bounced or complained per email id. Each email is subject-marked `EXERCISE ONLY` and ends with a drill footer.
