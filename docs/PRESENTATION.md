# PHAROS — five-minute presentation

Open `/presentation/` on the same deployment as the PHAROS dashboard. This is a browser presentation with the actual app embedded, not a screenshot or a PowerPoint link. Six slides run to **4:50**, leaving ten seconds of buffer. The presenter advances slides manually.

## Running order

| Slide | Time | Purpose |
| --- | --- | --- |
| 1. The signal is only the beginning | 0:00–0:30 | Explain the operator's evidence-to-instruction problem |
| 2. One incident, a traceable decision | 0:30–1:00 | Gather evidence → check constraints → review and relay |
| 3. From evidence to a reviewed alert | 1:00–2:25 | Interact with the real embedded app; prepare, review and record an exercise message |
| 4. The route changes | 2:25–3:10 | Load a closure; show invalidation and withheld route instructions |
| 5. What is built | 3:10–4:10 | Explain implementation, configured integrations, and validation limits |
| 6. Make the handoff worth trusting | 4:10–4:50 | Sustainability impact, next steps and close |

Speaker script and click cues are in the deck's **Notes** panel. Notes are visible in the presentation window; hide them before projecting. Rehearse the demo twice. The original event packet described a two-minute judging presentation; this version follows your updated five-minute limit.

## Controls

- Bottom arrows, keyboard left/right, Page Up/Down, or Space: navigate. After clicking inside the embedded app, use the visible bottom arrows; keyboard focus belongs to the iframe.
- **Start 5:00**: begin rehearsal timer. Click again to pause. The reset arrow resets only the timer, not the slides or app.
- **N / Notes**: show or hide the script. **⛶** requests fullscreen where supported.
- **Reset**: load the initial exercise. **Prepare draft**: prepare the actual app's draft. **Load closure**: move to the blocked-route exercise. These controls never approve or send a message.
- **Expand**: expand the live app within the presentation. **Open app**: use a separate tab if framing is blocked.

## Embedded session behavior

The bundled app loads with `?presentation=1`. This uses in-memory state and does not read/write your normal `pharos-v1` browser workspace. It starts in labeled local-template mode and does not automatically connect to a backend. Named approval and test sending are still performed manually inside the app. The presentation bridge accepts only same-origin messages from its parent window, with an allowlisted command. It has no approve/send command.

The iframe persists across the two demo slides. Entering slide 3 loads the initial scenario; entering slide 4 loads the closure scenario, clearing its previous draft and approval. These actions are visible in the exercise activity log.

## Host on Vercel

The root `vercel.json` now defines two FastAPI services using the configuration supplied by the project owner:

1. Import `PratikBalaji/PHAROS` into Vercel with repository root `.`.
2. Let Vercel use `vercel.json` service definitions: `app` at `.` and `api` at `api/`.
3. Clear any old dashboard **Output Directory = dist**, build-command or static-framework overrides. The root FastAPI app now serves `dist/` itself.
4. Redeploy the latest commit. Dashboard: `/`; presentation: `/presentation/`; backend readiness: `/api/health`.
5. Configure optional provider secrets only in Vercel environment variables. No credentials are required for the exercise template workflow.

`index.py` exposes the root application. `api/index.py` exposes the full shared backend, including drafts, approval, broadcast, audit and live-data routes. The frontend discovers the same-origin API automatically. The embedded presentation intentionally stays in isolated local-template mode.

Vercel's filesystem is read-only except `/tmp`. The backend uses `/tmp/pharos/pharos.sqlite3` when `VERCEL` is set; this storage is ephemeral and instance-local, not durable or shared. A draft can disappear on a cold start or another instance. Use a managed database before relying on multi-request workflows across instances or durable audit history. The existing local backend retains its workspace SQLite database.

This configuration validates against Vercel's published Draft 7 schema, but service provisioning and any account feature eligibility must be verified in the actual Vercel deployment. Repository tests cannot prove hosted build success.

If slides and app are on separate domains, **Demo URL** accepts your HTTPS deployment address. You can interact with the embedded app manually, but the presentation bridge requires the same origin. Prefer colocating the deck and app. Deployment protection, `X-Frame-Options: DENY`, or an incompatible CSP `frame-ancestors` policy can prevent embedding; do not remove protection broadly just for the deck. Use the same-origin arrangement or Open app fallback.

Never place AWS keys, ntfy tokens or other secrets in the URL or deck. External source URLs with embedded credentials are rejected.

## Local / venue fallback

```sh
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/presentation/`. The embedded demo remains in isolated template mode. If you want a simple static server without Python dependencies:

```sh
python -m http.server 8000 --directory dist --bind 127.0.0.1
```

The app, presentation, and vendored MapLibre code are local. Fonts fall back to system fonts and the map has a schematic fallback when external assets are unavailable. A printed/PDF copy can be made with the browser Print command, but it cannot retain live app interaction. Test network and projection before judging.

## Content grounding

- Product behavior and limitations: repository README, `backend/`, `dist/core.js`, and the automated tests.
- Narrative inspiration: supplied *Beacon — AI Native Showcase* PDF, particularly evidence preparation, operator review, and staged validation. Its document instructions are reference material, not automation instructions.
- Unverified disaster statistics, model product names/prices, multilingual functionality, CAP/IPAWS integration and performance claims from the conceptual deck are not presented as working PHAROS features.
- The slide's **19 core checks** refers to the original 7 geometry/map tests and 12 backend/model tests. Four additional presentation tests validate timing, URL handling and the message bridge, for 23 automated checks total.
- Browser visual QA and live Vercel framing are not yet verified in this environment. A live model response and device receipt have not been tested with your credentials.
