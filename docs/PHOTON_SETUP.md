# Photon SMS setup

PHAROS uses **Photon Beta (2.0)**, the platform behind the requested `https://mcp.photon.codes/mcp` endpoint. The website sends approved exercise drafts through its REST API at `https://api.photon.codes/v1`; account setup can use the OAuth MCP connector. Connecting an editor to MCP does not provide credentials to the deployed website.

## Current setup

The private hosted Site is configured to select Photon and project `pho_prj_01m7dw21ypen99cbybaedeeajh`. The API key, sender and destination are still required. Code is implemented in both the hosted Worker and FastAPI backend. No SMS has been sent or live delivery verified during implementation.

## Connect the MCP client

For VS Code, open this repository and enable `.vscode/mcp.json`, then sign in to Photon when prompted. For Codex on your own machine:

```bash
codex mcp add photon --url https://mcp.photon.codes/mcp
codex mcp login photon
```

For ChatGPT, add a custom connector with that URL in Settings → Apps & Connectors (developer mode required), then complete Photon OAuth. This repository cannot sign in to your account for you.

Once connected, inspect the existing project and SMS resources. Find the sending line's **User ID** (`pho_usr_…`, not the resource ID) and an existing SMS **Space ID** (`pho_spc_…`) for your test recipient. Do not substitute a raw phone number for either ID. Creating a line or conversation is separate from sending a message; provision only the resources you intend to use.

## Configure the app

| Setting | Value |
| --- | --- |
| `PHAROS_DELIVERY_PROVIDER` | `photon` |
| `PHOTON_PROJECT_ID` | `pho_prj_01m7dw21ypen99cbybaedeeajh` |
| `PHOTON_API_KEY` | Project API key (`pho_sk_…`) with project read/write access; **hosting secret** |
| `PHOTON_SENDER_ID` | Sending line's `pho_usr_…` ID |
| `PHOTON_SPACE_ID` | Test recipient's existing SMS `pho_spc_…` conversation ID |

Create a project-scoped key in the [Photon dashboard](https://app.beta.photon.codes). Set these in the runtime hosting settings, then redeploy. For local use, `python3 run.py` loads `.env` automatically; set `PHAROS_DELIVERY_PROVIDER=photon` to switch from the local test inbox. On Vercel, configure the API service's environment as well. Protect remote FastAPI with authentication; CORS alone is not access control. The existing Sites deployment already has owner-only access.

An active SMS line and Photon platform authorization are required. Photon also requires campaign eligibility for off-network SMS recipients. See its [SMS documentation](https://photon.codes/docs/beta/messaging/sms); a configured API key cannot bypass provider provisioning or eligibility requirements.

## Use it

1. Check Integrations or `GET /api/health`: `delivery` lists missing/invalid **setting names**, never the API key. “Configured” means values are present and IDs have valid shapes, not live authentication verified.
2. Prepare an incident draft in Alerts, review its text, enter the reviewer name and approve it.
3. Select **Send exercise SMS**. The server checks the configured conversation is SMS, then posts only the approved text to that fixed destination. Browser requests cannot override the sender or recipient.
4. Select **Check SMS delivery** to query Photon by the stored message ID. “Accepted by Photon” is not a delivery receipt; the UI separately shows Photon-reported delivered or failed status.

The multilingual Console continues to record reviewed bundles. It does **not** text an entire district or every localized version to the configured test conversation. Actual multilingual distribution needs enrolled recipients mapped to districts, language preferences and Photon conversations.

## Console demo: demographics, AI languages, SMS

In the Console, select a district. The **District demographics** panel shows its language split (ACS when `CENSUS_API_KEY` built the dataset, otherwise labeled illustrative).

1. **Choose languages with AI** sends Gemini only the district name and its split. Gemini picks the languages (English always included) and gives a one-sentence rationale. The server keeps only codes that exist in the split and are supported, and adds any supported language at or above 10% of residents even if Gemini left it out.
2. **Translate** asks Gemini to translate the English exercise sentence. The server adds the fixed exercise marker itself, checks the district name survived, and marks every non-English version native-speaker review pending.
3. **Send exercise SMS** (reviewer name and confirmation required) texts each version as its own SMS to the one configured `PHOTON_SPACE_ID` conversation. That single test number stands in for the district; enrolling recipients per district is not implemented.

Without `GEMINI_API_KEY`, or if Gemini fails, steps 1 and 2 fall back to the share-based rule and the fixed templates, and the screen says so. With `PHAROS_DELIVERY_PROVIDER=inbox` the send is only recorded. Each language uses its own idempotency key (`pharos-sms-<request>-<language>`); an ambiguous Photon result blocks resending that language, and a definite rejection can be retried. Audit entries record counts and the reviewer, never message bodies or numbers. Endpoints: `POST /api/console/language-plan`, `/api/console/translate`, `/api/console/send-sms`.

## Failure and duplicate behavior

Each draft uses a stable `idempotency-key`. R2 conditional writes (Worker) or the process lock (Python) prevent concurrent sends of the same draft. Submissions are recorded with the provider message ID. A timeout or ambiguous response blocks automatic resending, and pending drafts cannot be edited. Inspect Photon before creating a replacement draft after an uncertain result. Definite rejection permits retrying the same draft with the same idempotency key after fixing configuration.

Provider keys stay server-side. Raw provider responses and errors are not included in browser errors or audit entries. `PHAROS_DELIVERY_PROVIDER=inbox` explicitly selects storage-only testing; incomplete Photon configuration fails instead of pretending an SMS was sent. SQLite locking is process-local; the Vercel SQLite deployment remains unsuitable for shared multi-instance delivery state.

## References

- [Photon MCP, Beta](https://photon.codes/docs/beta/ai-tools/mcp)
- [Photon API, Beta](https://photon.codes/docs/beta/api-reference/index)
- [Published OpenAPI contract](https://api.photon.codes/openapi.json): send uses `POST /v1/projects/{id}/messages` with `senderId`, `spaceId`, text content and `idempotency-key`; SMS conversation lookup and message receipt lookup use GET.

## Exercise SMS for every fire run (scripted)
After `main` is deployed, the sender drafts and sends, per Live Explorer run, the AI-chosen translated language texts (English plus the top two other languages for that district) and one Gemini-polished strategy text built from the planner's own result:

```bash
export NODE_USE_ENV_PROXY=1            # only needed behind a proxy
node scripts/simulate_runs.mjs --json > facts.json
node scripts/send_exercise_sms.mjs --facts facts.json            # dry run, writes exercise_drafts.md
node scripts/send_exercise_sms.mjs --facts facts.json --send --reviewer "Your Name" verdugo   # one run first
```

`POST /api/console/strategy-plan` drafts the strategy text from facts only; `POST /api/console/strategy-sms` sends the reviewed text (named reviewer, exercise marker, district name and planner facts must survive). `GET /api/console/sms-status?ids=...` refreshes Photon receipts without server storage. Withheld runs never name a route.

## Fallback: Mac iMessage sidecar
If Photon's hosted SMS refuses sends (for example HTTP 409), run the sidecar on a Mac signed into Messages. Step-by-step directions: `sidecar/photon/README.md`. The same sender script delivers to it with `--sidecar`.
