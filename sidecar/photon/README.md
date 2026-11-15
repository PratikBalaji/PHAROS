# PHAROS Photon iMessage sidecar (runs on your Mac)

Sends the EXERCISE texts as **iMessages** through Photon's free `@photon-ai/imessage-kit`. Use it when Photon's hosted SMS line is unavailable. It reaches **iPhone/iMessage recipients only**, runs only on **macOS signed into Messages**, and cannot run on Vercel or Linux.

Safety: the recipient is fixed by `PHOTON_SIDECAR_TO` (callers can't choose one), every request needs a bearer token, text must begin with a PHAROS exercise marker, one send per key (repeats are no-ops, a timeout blocks resend), binds to `127.0.0.1`.

## Step by step (about 10 minutes)

1. **Get the code on the Mac** (Node 20+ required, check with `node -v`):
   ```bash
   git clone https://github.com/PratikBalaji/PHAROS.git && cd PHAROS && git pull
   ```
2. **Sign into Messages** on the Mac with your Apple ID and send yourself one normal iMessage so the conversation exists.
3. **Allow Full Disk Access** to the app you run commands in: System Settings, Privacy & Security, Full Disk Access, click `+`, add Terminal (or iTerm/VS Code). Quit and reopen it afterwards.
4. **Install:**
   ```bash
   cd sidecar/photon && npm install
   ```
5. **Start the sidecar** (your own phone number in international format; invent a token of 16+ characters and keep it private):
   ```bash
   export PHOTON_SIDECAR_TO="+1YOURNUMBER"
   export PHOTON_SIDECAR_TOKEN="choose-a-long-random-token"
   npm start
   ```
   Expected: `PHAROS Photon sidecar on http://127.0.0.1:8787`. macOS may ask permission for the terminal to control Messages: click **OK**.
6. **Test with one message.** In a second terminal in the repo root:
   ```bash
   export PHOTON_SIDECAR_TOKEN="same token as above"
   node scripts/send_exercise_sms.mjs --facts scripts/exercise_facts.json --out drafts.md --send --reviewer "Patrick Balage" --sidecar http://127.0.0.1:8787 --batch mac1 verdugo
   ```
   You should get 4 iMessages (English, Armenian, Spanish, then the strategy text), each starting with the exercise marker. Take a screenshot of that Messages thread as the evidence.
7. **All runs:** repeat without the trailing `verdugo` and with a new `--batch` (for example `--batch mac2`).

Notes: the kit confirms that Messages.app **accepted** the send, not that it was delivered, so the screenshot is the proof. `.sidecar-state.json` (git-ignored) remembers sent keys; delete it only to deliberately resend. Drafts are still written by Gemini on https://www.pharos.casa, so the Mac needs internet access.
