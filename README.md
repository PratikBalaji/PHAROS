# PHAROS — Wildfire & Evacuation Relay

A solo-hackathon prototype for reviewing wildfire evidence, checking candidate routes against **synthetic** hazard zones, preparing an alert, and relaying an approved exercise notification.

## What works

- Map-first tactical dashboard with a full-bleed MapLibre dark vector basemap, floating translucent panels, monospace telemetry, and three replay stages. POIs, road names, and minor labels are hidden programmatically; country, state, and selected city labels remain. Synthetic hazard/route overlays are not aligned to verified roads. An offline schematic remains available if the basemap cannot load.
- Deterministic segment/circle intersection checks. Ridge Road is excluded initially; the closure scenario excludes both routes.
- Evidence detail, editable exercise messages, named approval, automatic draft invalidation on replay changes, browser-local activity, and JSON export.
- Hosted dashboard works without credentials using clearly labeled local templates and a local test inbox.
- Python FastAPI backend serves the same dashboard, stores drafts/approvals/audit in SQLite, and supports Bedrock Converse tool use and ntfy test delivery.
- A standalone read-only MCP server exposes four typed scenario tools. The Bedrock runner invokes the same service functions via Converse tool schemas; it does **not** currently connect to that server over MCP transport.
- NASA FIRMS, Open-Meteo and OSRM live-data API adapters. These endpoints are available in `/docs`; their output is **not yet fused into the replay dashboard**.

## Run the full local app

Python 3.11+ recommended. From this directory:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The dashboard detects its local backend automatically. API docs: `http://127.0.0.1:8000/docs`.

The hosted version is static. To use a remote Python backend, select Integrations → Connect backend. That backend needs HTTPS, appropriate CORS origins, and authentication at a reverse proxy. The prototype has **no application-level authentication** and must not be exposed openly. For a first demo, run it on loopback.

## Bedrock

Use the AWS credential chain (for example your authenticated AWS CLI profile). Never put AWS secrets in browser settings or commit them.

```sh
export AWS_PROFILE=your-profile
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=your-supported-model-or-inference-profile-id
```

Restart the backend after setting configuration. The model must support the Bedrock Converse API and tool use. Account/region/model access must already be enabled. No fixed model name is assumed.

The model is asked to retrieve all four tools and return an incident brief with source IDs. The server validates the schema, source allowlist, and tool retrieval. This does not prove semantic factuality; the brief remains reviewable. Routing decisions and the default message are deterministic. Bedrock errors are surfaced rather than presented as successful AI output. Without `BEDROCK_MODEL_ID`, the server labels output “Server template.”

## Data and notifications

See `.env.example` for variable names. Export them in your shell; no `.env` loader is enabled.

- `FIRMS_MAP_KEY`: free NASA FIRMS API key from https://firms.modaps.eosdis.nasa.gov/api/map_key/ . Thermal observations are not a perimeter.
- `OSRM_URL`: defaults to the public OSRM demo service. For sustained use, host OSRM or select a provider and observe usage limits.
- `NTFY_TOPIC_URL`: HTTPS topic URL. Leave empty for a SQLite-backed test inbox. Use an authenticated topic for private content.
- `NTFY_TOKEN`: optional bearer token stored only on the server.
- `PHAROS_ALLOWED_ORIGINS`: comma-separated allowed frontend origins. CORS is not authentication.
- `PHAROS_DB`: optional SQLite path. Default: `work/pharos.sqlite3`.

No real messages have been sent during development. A successful ntfy HTTP response means provider acceptance, not device receipt. Requests with ambiguous delivery failures are not automatically resent. Sent drafts are idempotent and cannot be edited; create a new draft instead. Drafts expire after 15 minutes.

## MCP server

```sh
PHAROS_STAGE=0 python -m backend.mcp_server
```

Use stdio transport. Valid stages are 0, 1, 2. Tools:

- `get_incident_evidence`
- `get_weather_context`
- `get_candidate_routes`
- `check_route_constraints`

All MCP tools currently return synthetic scenario data. Delivery is an explicit backend operation after named review, not an agent tool.

## Verification

```sh
npm run check   # syntax-check dist/app.js, core.js, geospatial.js
npm test        # node --test tests/*.test.js
python -m unittest discover -s tests -p 'test_*.py' -v   # needs requirements.txt installed
```

Tests cover geometry, missing routes, exercise labels, review gates, expiration, changed stages, repeated sends, and backend validation. Bedrock tests use mocked Converse responses. Live Bedrock credentials, FIRMS credentials, device delivery, and a browser visual pass are not verified in this environment.

## Two-minute demo

1. Open Overview and inspect the camera, thermal, and weather fixtures.
2. Click Ridge Road to explain why it intersects the assumed hazard.
3. Prepare a draft; inspect source IDs and the passing scenario candidate.
4. Enter a reviewer name, approve, then record a test notification.
5. Load “Road closure.” Show both routes excluded and the new draft withholding route instructions.
6. Export the incident report and open Activity to show the review trail.

## Next milestones

1. Add actual D-Fire-compatible smoke detector weights and evaluate on held-out data; the current camera signal is not inference.
2. Align hazard and route overlays to verified roads, and add verified closure/perimeter sources. Keep the current fixtures as reproducible tests.
3. Fuse live observations with timestamp, spatial matching, freshness, and provenance rules.
4. Connect Bedrock to MCP transport if multiple external tool servers are needed.
5. Add authenticated operator accounts and durable versioned incident state before multi-user deployment.

No precision, recall, reliability, alert-to-route latency, ecological impact, or production emergency capability is claimed. This is an exercise prototype, not navigation or emergency guidance.

## Repository layout

```text
backend/   FastAPI app (app.py), scenario facts and routing checks (core.py),
           Bedrock tool loop (bedrock.py), stdio MCP server (mcp_server.py)
dist/      Static dashboard: vanilla JS, CSS, vendored MapLibre GL JS
tests/     Node (geometry, map overlays) and Python (backend, Bedrock mocks) tests
work/      Runtime SQLite state (git-ignored, created on first run)
```

## Deployment

`dist/` contains the complete static dashboard, and the FastAPI backend also serves it. `.openai/hosting.json` identifies its private Sites deployment. Python services are run separately; static hosting does not run FastAPI. Keep credentials and runtime state (`.env*`, `work/`) out of version control; `.gitignore` already excludes them.

`dist/pharos-source.zip` is a bundled snapshot of the source offered by the dashboard's Integrations page. It is not regenerated automatically, so it can lag behind this repository.

External resources: Google Fonts (system-font fallback), CARTO Dark Matter vector style/tiles and OpenStreetMap data with on-map attribution. MapLibre GL JS 5.6.1 is vendored under its included license. The geographic map requires network access and WebGL. The interface remains vanilla JavaScript; this refactor does not add React.
