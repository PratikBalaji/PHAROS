# PHAROS — Wildfire & Evacuation Relay |  HackPrinceton Fall '26 - Sustainability Track

An MCP server that reviews wildfire evidence, selects real municipalities and districts, drafts a reviewable **multilingual** exercise alert, and relays it—with a separate map view backed by real fire-weather alerts and fire perimeters. Delivery stays **exercise-only**: no real public alert (IPAWS / WEA) is ever issued.

## What works

- **Communications console (primary view)** — pick real municipalities and districts from a recipients rail, compose an exercise alert, and record a broadcast to a sent-alert log. The console is vanilla JS over a committed dataset of real boundaries, so it works offline.
- **Demographic-driven multilingual drafting** — each selected district's recommended languages come from US Census ACS "language spoken at home" data; an operator can switch the alert among supported languages (English, Spanish, Chinese, Korean, Tagalog, Vietnamese, Armenian, Arabic, Russian). Non-English text is rendered from human-authored templates and flagged for native-speaker review.
- **Immersive 3D Map view** — a pitched MapLibre scene with open 3D terrain (AWS elevation tiles), extruded buildings, and sky, showing real NIFC/WFIGS fire perimeters and the district boundaries you are targeting. **Live Explorer** runs one of **8 mock fire runs**: pick a run, press Play, and watch a wind-driven cellular-automaton fire grow while a vehicle drives a real OSRM road route that **keeps changing** (new road, new assembly point, or **withheld** when every path is cut off). The route is colored cyan to amber to red by distance from the fire, alternatives are gray with ETAs, and blocked stretches are red dashed. An offline schematic remains available if the basemap cannot load.
- Routing uses OpenRouteService `avoid_polygons` when `ORS_API_KEY` is set, otherwise a keyless OSRM fallback that rejects any candidate crossing the projected fire. When no backend is reachable the browser calls the public OSRM server directly (it allows cross-origin requests), so Live Explorer still works on a static deploy. Replans are throttled and cached to stay within the public demo server's fair-use limits; for sustained use set `OSRM_URL` to your own instance. The fire model and routes are **simplified exercise decision-support — not operational fire prediction or authoritative navigation**.
- Deterministic segment/circle intersection checks for the replay scenario; named approval, automatic draft invalidation on replay changes, browser-local activity, and JSON export.
- Python FastAPI backend serves the dashboard, stores drafts/approvals/audit in SQLite, records exercise broadcasts, and supports Bedrock Converse tool use, Photon SMS and optional ntfy delivery.
- A standalone read-only MCP server any agent can call for retrieval. It exposes four synthetic scenario tools plus **eight** live retrieval tools (satellite, weather, routing, camera, fire-weather alerts, fire perimeters, place boundaries, language demographics) and runs over stdio (local agents) or token-authenticated Streamable HTTP (remote agents). The Bedrock runner invokes the same service functions via Converse tool schemas; it does **not** currently connect to that server over MCP transport.
- Open-data adapters (some require keys) — NASA FIRMS (satellite), Open-Meteo (weather), OSRM (routing), NWS `api.weather.gov` (fire-weather alerts), NIFC/WFIGS (fire perimeters), US Census TIGERweb (boundaries) — plus US Census ACS (language demographics, free key) and an AI-camera detection ingest adapter. Reachable as REST endpoints (see `/docs`) and through the MCP tools. When a source is unconfigured or unreachable, the tools return a clearly labeled synthetic fallback rather than fabricated live data.

## Five-minute live presentation

Open `/presentation/` on the dashboard deployment. The six-slide browser deck embeds this actual application, includes speaker notes and a rehearsal timer, and uses a 4:50 running order with a 10-second buffer. The embedded exercise is isolated from your normal browser workspace. Setup, Vercel deployment instructions, and demo cues are in [docs/PRESENTATION.md](docs/PRESENTATION.md).

## Run the full local app

Install Python 3.11+ and run:

```sh
python3 run.py
```

On Windows use `py run.py`. The launcher creates `.venv`, installs dependencies, loads local `.env` settings and serves the frontend + backend together at **http://127.0.0.1:8000**. Node.js and cloud hosting are not required. Local exercise messages use a test inbox by default; configure Photon in `.env` to activate SMS.

Presentation: `/presentation/` · API docs: `/docs` · Stop: Ctrl+C. Use `--port 8080` for another port or `--reload` for backend development. [Full local setup instructions](docs/LOCAL_SETUP.md).

## Communications console & real data

The default view is a communications console: a rail of real municipalities and districts, a compose panel with a demographic-driven language switcher, and a broadcast log. Selecting areas updates the recommended languages (from each area's Census ACS split) and the compose preview. **Broadcast** requires a reviewer name and a review checkbox; it records an exercise broadcast per area (`POST /api/broadcast`, stored in the SQLite audit) and never issues a real public alert.

Recipients come from `dist/data/districts.json`, a committed dataset of real LA/Angeles-foothills municipalities (incorporated cities) and districts (census-designated places, plus scenario sub-districts such as West Altadena). Boundaries are real US Census TIGERweb polygons. Rebuild it with:

```sh
python scripts/build_districts.py
```

Demographics are **real ACS 5-year estimates when `CENSUS_API_KEY` is set**, otherwise clearly-labeled **illustrative** splits so the console still demonstrates per-district language targeting. Get a free key at https://api.census.gov/data/key_signup.html and re-run the script to bake real data in.

Live fire-weather alerts (NWS) and fire perimeters (NIFC/WFIGS) render on the **Map** view when their hosts are reachable. These are real sources but keyless; the browser fetches perimeters from the backend (`/api/live/perimeters`). None of this asserts a civil evacuation order — NWS products are fire-*weather*, and true evacuation orders (FEMA IPAWS) require an authorized agency interface, which is out of scope.

Vercel uses two FastAPI services from the root `vercel.json`: `app` serves the dashboard and `api` serves the full API. The browser auto-detects its same-origin API. The separate Sites-hosted copy is static. To use a remote Python backend there, select Integrations → Connect backend. That backend needs HTTPS, appropriate CORS origins, and authentication at a reverse proxy. The prototype has **no application-level authentication** and must not be exposed openly. For a first demo, run it on loopback.

## Bedrock

Use the AWS credential chain (for example your authenticated AWS CLI profile). Never put AWS secrets in browser settings or commit them.

```sh
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=your-supported-model-or-inference-profile-id
```

Restart the backend after setting configuration. The model must support the Bedrock Converse API and tool use. Account/region/model access must already be enabled. No fixed model name is assumed.

The model is asked to retrieve all four tools and return an incident brief with source IDs. The server validates the schema, source allowlist, and tool retrieval. This does not prove semantic factuality; the brief remains reviewable. Routing decisions and the default message are deterministic. Bedrock errors are surfaced rather than presented as successful AI output. Without `BEDROCK_MODEL_ID`, the server labels output “Server template.”

## Photon SMS

Photon Beta SMS is implemented in both backends. See [setup and MCP connection instructions](docs/PHOTON_SETUP.md). Set `PHAROS_DELIVERY_PROVIDER=photon` and the project API key, project ID, sender User ID and SMS Space ID. The UI shows missing setup, sends only approved exercise drafts, and can refresh a provider delivery receipt. The Console's per-district flow (live demographic split, Gemini-chosen languages, Gemini translation, then one exercise SMS per language) is described in the setup guide; it texts the single configured test conversation, and `GEMINI_API_KEY` is optional because a share-based rule and fixed templates are the labeled fallback. Recording a complete multilingual bundle remains a log entry until recipient-to-language mapping is implemented.

## Data and notifications

See `.env.example` for variable names. `python3 run.py` creates and loads your local `.env`; existing shell variables take precedence. Direct uvicorn launches require exported variables or `--env-file .env`.

- `FIRMS_MAP_KEY`: free NASA FIRMS API key from https://firms.modaps.eosdis.nasa.gov/api/map_key/ . Thermal observations are not a perimeter.
- `OSRM_URL`: defaults to the public OSRM demo service. For sustained use, host OSRM or select a provider and observe usage limits.
- `NWS_USER_AGENT`: identifier sent to `api.weather.gov` (required by NWS). Keep it generic; do not put personal data in it.
- `CENSUS_API_KEY`: optional free Census key (https://api.census.gov/data/key_signup.html) enabling real ACS language demographics; without it, demographics fall back to labeled illustrative splits.
- `ORS_API_KEY`: optional free OpenRouteService key (https://openrouteservice.org/dev/#/signup) for evacuation rerouting with true avoid-polygons; without it, routing falls back to keyless OSRM alternatives.
- `CAMERA_FEED_URL`: optional HTTP(S) endpoint returning JSON detections (a list, or an object with a `detections` array). Leave empty to serve the synthetic camera fixture. Detections are provider-reported, not confirmed fire and not local inference.
- `CAMERA_FEED_TOKEN`: optional bearer token for the camera feed, stored only on the server.
- `NTFY_TOPIC_URL`: HTTPS topic URL. Used only when ntfy is selected; choose `PHAROS_DELIVERY_PROVIDER=inbox` for storage-only testing. Use an authenticated topic for private content.
- `NTFY_TOKEN`: optional bearer token stored only on the server.
- `PHAROS_ALLOWED_ORIGINS`: comma-separated allowed frontend origins. CORS is not authentication.
- `PHAROS_DB`: optional SQLite path. Local default: `work/pharos.sqlite3`. On Vercel the default is `/tmp/pharos/pharos.sqlite3`, which is ephemeral and instance-local. It cannot provide durable/shared draft or audit storage; a managed database is needed for reliable multi-instance workflows.

No real messages have been sent during development. A successful ntfy HTTP response means provider acceptance, not device receipt. Requests with ambiguous delivery failures are not automatically resent. Sent drafts are idempotent and cannot be edited; create a new draft instead. Drafts expire after 15 minutes.

## MCP server

A read-only retrieval server for agents. Delivery of an alert is never an MCP tool; it remains the reviewed backend operation in `backend/app.py`.

### Local (stdio)

```sh
PHAROS_STAGE=0 python -m backend.mcp_server
```

`PHAROS_STAGE` (0, 1, 2) selects the synthetic exercise used by the scenario tools and as the fallback for the live tools.

### Remote (Streamable HTTP + auth)

```sh
export PHAROS_MCP_TRANSPORT=http
export PHAROS_MCP_TOKEN=choose-a-long-random-secret
export PHAROS_MCP_HOST=127.0.0.1    # default
export PHAROS_MCP_PORT=8787         # default
python -m backend.mcp_server
```

The endpoint is served at `/mcp`. Every request must send `Authorization: Bearer $PHAROS_MCP_TOKEN`; the server refuses to start without a token and rejects unauthenticated requests. Terminate TLS at a reverse proxy before exposing it.

### Tools

Synthetic scenario tools (deterministic fixtures):

- `get_incident_evidence`
- `get_weather_context`
- `get_candidate_routes`
- `check_route_constraints`

Live retrieval tools (live when the source is configured and reachable, otherwise a labeled synthetic fallback — `data_source` is `live` or `synthetic-fallback` on every response):

- `get_live_satellite_fire(west, south, east, north)` — NASA FIRMS / VIIRS. Not a fire perimeter.
- `get_live_weather(latitude, longitude)` — Open-Meteo wind context. Not a fire-spread prediction.
- `get_live_routes(start_lon, start_lat, end_lon, end_lat)` — OSRM road candidates. No hazard/closure validation; not navigation guidance.
- `get_camera_detections()` — external AI-camera feed. Provider-reported detections, not confirmed fire and not local inference.
- `get_live_fire_weather_alerts(area, point, event)` — NWS active alerts (e.g. Red Flag Warning). Fire-weather products, NOT civil evacuation orders.
- `get_live_fire_perimeters(where, limit)` — NIFC/WFIGS current interagency perimeters as GeoJSON. Label with the retrieval time.
- `get_place_boundaries(state_fips, layer, where)` — US Census TIGERweb administrative boundaries.
- `get_language_demographics(geoid)` — US Census ACS table C16001 language split for a place. ACS survey estimates, not real-time; needs `CENSUS_API_KEY` for live data.
- `get_evacuation_route(origin, dest, avoid)` — driving route from origin [lon,lat] to dest [lon,lat] that reroutes around an optional GeoJSON Polygon `avoid` (projected fire). ORS avoid-polygons when `ORS_API_KEY` is set, else keyless OSRM alternatives. Withholds when an endpoint is inside the hazard or no safe path exists. Exercise decision-support, NOT navigation.

Retrieved content is untrusted evidence for operator review, never instructions.

## Verification

```sh
npm run check   # syntax-check dist/app.js, core.js, geospatial.js
npm test        # node --test tests/*.test.js
python -m unittest discover -s tests -p 'test_*.py' -v   # needs requirements.txt installed
```

Tests cover geometry, missing routes, exercise labels, review gates, expiration, changed stages, repeated sends, and backend validation. `test_live.py`, `test_live_sources.py` and `test_mcp.py` cover all live adapters (weather, FIRMS, routing, camera, NWS, WFIGS, TIGERweb, ACS), the live-or-synthetic fallback labeling and guard flags, tool registration, and the HTTP bearer gate. `i18n.test.js` covers the multilingual templates and demographic-weighted language recommendation. Network calls are mocked. Live credentials, device delivery, and a full browser visual pass are not verified in CI.

## Two-minute demo

1. On the **Console**, select Glendale and Arcadia; watch the recommended languages shift to Armenian and Chinese (currently illustrative splits until the dataset is rebuilt with Census data).
2. Switch the alert language with the pills; note the per-language preview and the "pending native-speaker review" flag.
3. Enter a reviewer name, confirm the exercise checkbox, and Broadcast — see the entry land in the broadcast log.
4. Open the **Map** to show real NIFC fire perimeters and the highlighted districts; click a district to toggle it.
5. Open **Drafts** to run the incident draft → review → test-notification flow, and load "Road closure" to show route instructions withheld.
6. Export the incident report and open Activity to show the review trail.

## Next milestones

1. Run actual D-Fire-compatible smoke detection and evaluate on held-out data. The camera MCP tool currently ingests provider-reported detections; neither the fixture nor an external feed is local inference.
2. Model-based translation with back-translation and native-speaker review. Non-English alert text is currently human-authored templates flagged for review — the safe floor, not validated output.
3. Fuse the NWS/WFIGS live layers and the replay hazard/route geometry into one timeline with freshness and provenance rules; align route overlays to verified roads.
4. Integrate a real, authorized alerting path (e.g. FEMA IPAWS via an agency MOA) before anything leaves the exercise sandbox; connect Bedrock to MCP transport if multiple external tool servers are needed.
5. Add authenticated operator accounts and durable versioned incident state before multi-user deployment.

No precision, recall, reliability, alert-to-route latency, ecological impact, or production emergency capability is claimed. This is an exercise prototype, not navigation or emergency guidance.

## Repository layout

```text
backend/   FastAPI app (app.py), scenario facts and routing checks (core.py),
           live open-data adapters + fallback resolvers (live.py),
           Bedrock tool loop (bedrock.py), stdio/HTTP MCP server (mcp_server.py)
dist/      Static dashboard: vanilla JS (app.js, core.js, geospatial.js, i18n.js),
           CSS, vendored MapLibre GL JS, data/districts.json (curated recipients),
           and presentation/ (five-minute browser deck)
dist/      ... plus firemodel.js (wind-driven cellular fire model), fireruns.js (8 mock runs),
           routeanim.js (pure route/hazard geometry), liveplan.js (which assembly point, keep or replace a route)
scripts/   build_districts.py — rebuilds dist/data/districts.json from TIGERweb + ACS;
           simulate_runs.mjs — headless replay of the fire runs against live OSRM
api/       index.py — thin Vercel serverless API (evac-route, perimeters, weather)
docs/      PRESENTATION.md — presentation setup, deployment, and demo cues
tests/     Node (geometry, map overlays, i18n, fire model, presentation) and Python (backend, live, sources, evac, mcp, Bedrock) tests
work/      Runtime SQLite state (git-ignored, created on first run)
```

Licensed under the MIT License (see `LICENSE`).

## Deployment

`dist/` contains the complete static dashboard, and the FastAPI backend also serves it. `.openai/hosting.json` identifies its private Sites deployment. Keep credentials and runtime state (`.env*`, `work/`) out of version control; `.gitignore` already excludes them.

**Vercel (recommended):** import `PratikBalaji/PHAROS` at vercel.com → Framework preset **Other**, no build command, Output Directory `dist`. `vercel.json` rewrites `/api/*` to `api/index.py`, a thin Python serverless function (evac routing + perimeters + weather) that reuses `backend/live.py`. Set `ORS_API_KEY` (and optionally `FIRMS_MAP_KEY`, `CENSUS_API_KEY`) in the Vercel project's Environment Variables for live rerouting and data; without them the app still runs on keyless fallbacks. Push-to-deploy and per-PR previews follow automatically.

`dist/pharos-source.zip` is a bundled snapshot of the source offered by the dashboard's Integrations page. It is not regenerated automatically, so it can lag behind this repository.

External resources: Google Fonts (system-font fallback), CARTO Dark Matter vector style/tiles and OpenStreetMap data with on-map attribution. MapLibre GL JS 5.6.1 is vendored under its included license. The geographic map requires network access and WebGL. The interface remains vanilla JavaScript; this refactor does not add React.

## Vercel service deployment

The root `vercel.json` routes `/api/*` to the FastAPI service rooted at `api/`, and everything else to the FastAPI service rooted at `.`. `index.py` and `api/index.py` expose the same backend implementation so routes do not drift. Remove any old Vercel project Output Directory override (`dist`) and redeploy using the service configuration. Verify `/api/health` returns JSON before testing the workflow. See [deployment notes](docs/PRESENTATION.md#host-on-vercel).

The source configuration has been schema-checked and both ASGI entry points tested locally. This does not prove Vercel build success or provision a managed database.

## Published full-stack hackathon demo

The private Sites deployment now serves both the frontend and a JavaScript Worker backend. The Worker uses a provisioned R2 bucket for durable exercise drafts, named approvals, test-inbox records and audit events. `/api/health` reports `runtime: cloudflare-worker` and `storage: durable-r2`. These records survive Worker instance restarts. Publication does not change the private audience.

The hosted Worker supports the exercise draft/approve/send flow, exercise broadcasts, audit retrieval, weather, NWS alerts, NIFC perimeters, and OSRM alternatives checked against supplied hazard polygons. Delivery supports Photon Beta SMS for approved drafts when configured, or an explicitly selected test inbox. It does not send ntfy or official emergency alerts from the Worker. Bedrock inference and the Python MCP server remain in the FastAPI implementation and are **not running in the Worker**. The runtime reports these capabilities honestly. The original FastAPI/Vercel configuration remains available, but Vercel deployment access is not connected to this workspace.

Build the hosted runtime with `npm ci && npm run build:sites`. `worker/assets.js` and `dist/server/` are generated and ignored. The build embeds the dashboard assets so the Worker handles static routes and API routes on the same origin. Never place secrets in generated assets.

### Useful incident replay

Open **Map → Incident replay**. Choose Smoke signal, Wind context, then Road closure. Each step updates the same scenario hazard geometry, route statuses, and draft state. Stage changes invalidate any previous draft and approval. The closure excludes both candidates and the draft withholds route instructions. Click the scenario's draft button, enter a reviewer name, approve and record a hosted test. **Live explorer** is a separate mode: live perimeters and the cellular fire projection are not evidence for the deterministic replay.

The replay also updates the offline schematic, so it remains demonstrable when external basemap assets are unavailable. Scenarios are synthetic exercises; the map's geographic placement is illustrative, not road-aligned navigation.

## Readiness audit and multilingual batches

The original vision is not fully implemented. Read [PLAN_AUDIT.md](docs/PLAN_AUDIT.md), [API_KEYS.md](docs/API_KEYS.md), and [CODEBASE_INDEX.md](docs/CODEBASE_INDEX.md) before configuring providers or making performance claims.

The console now builds a **complete per-district language bundle** automatically. Select districts, choose Automatic per district or All 9 supported languages, review the plan and record one batch. Preview tabs do not affect the batch. The backend constructs and stores every localized message from canonical templates. Unsupported/grouped languages and illustrative demographics are disclosed. These are fixed exercise templates, not model translations or real notification delivery.

### Live Explorer: mock fire runs

Open **Map → Live explorer** and choose one of eight fictional runs (Verdugo Hills, Arroyo Seco, Altadena Ridge, Sierra Madre Canyon, Flintridge Crest, Santa Anita Wash, Monrovia Canyon, Wind-Shift Run). They are set in the real foothill geography but are not forecasts and do not represent any real incident. Each run is 24 five-minute steps. Press **Play** (1×, 2× or 4×).

- The vehicle starts in the run's district and heads for a primary assembly point. When the fire cuts the road ahead, or closes in on it, the planner asks OSRM again from the vehicle's current position. It tries the primary assembly point first, then the nearest safe ones, and reports whether the route is **clear**, **rerouted** (with the minutes and kilometres it changed by) or **withheld**.
- The hazard used for routing is the burned area plus a one-cell margin, not a convex hull, so a wind shift does not make the hazard wildly larger than the fire.
- The **Wind-Shift Run** reverses the wind at T+55, so the fire turns back on itself. **Verdugo Hills** is deliberately a no-safe-exit run: the fire cuts both roads out early, so the route is withheld with the reason shown.
- Routes are planned against the fire **as projected 15 minutes ahead**, drawn as a dashed outline, so the vehicle is switched away from a road before it is cut. A "fire nearby" check only recolors the route; it is replaced only when the projected fire would block it.
- Toggle **Alternatives** and **Follow vehicle** in the status card. The vehicle's speed is illustrative.

The fire model and routes are simplified exercise decision support, not operational fire prediction or navigation.

To see what the planner does without a browser, replay the runs headlessly against live OSRM. It uses the same decision code as the app (`dist/liveplan.js`) and prints reroutes, assembly-point switches, withheld periods and whether the vehicle arrives:

```sh
NODE_USE_ENV_PROXY=1 node scripts/simulate_runs.mjs              # all eight runs
node scripts/simulate_runs.mjs altadena windshift                # chosen runs
OSRM_BASE=https://your-osrm.example node scripts/simulate_runs.mjs
```

`NODE_USE_ENV_PROXY=1` is only needed behind an HTTP proxy. The script pauses between requests to stay within the public demo server's fair-use limits.
