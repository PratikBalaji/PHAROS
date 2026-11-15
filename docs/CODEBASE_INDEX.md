# PHAROS codebase index

| Path | Responsibility |
| --- | --- |
| `worker/photon.js`, `backend/photon.py` | Photon Beta SMS configuration, approved text submission and receipt lookup |
| `docs/PHOTON_SETUP.md`, `.vscode/mcp.json` | Hosting setup and OAuth MCP client connection |
| `run.py`, `docs/LOCAL_SETUP.md` | One-command local setup, .env loading and frontend/API startup |
| `dist/app.js` | Console, replay, drafts, review actions, API requests, persisted browser UI state |
| `dist/i18n.js` | Language ranking, per-district bundle planning, coverage-gap reporting |
| `dist/data/alert-templates.json` | Shared canonical language metadata and fixed exercise templates, read by JS and Python |
| `dist/data/districts.json` | Committed geographic features and current illustrative demographic splits |
| `dist/geospatial.js` | MapLibre basemap, live layers, replay geometry synchronization |
| `dist/core.js` | Deterministic scenario facts, route checks and template drafts |
| `dist/firemodel.js` | Simplified cellular fire-projection exercise |
| `worker/index.js` | Published Worker request dispatcher and embedded static assets |
| `worker/api.js` | Deployed API: R2 draft/review/inbox, localized bundles, audit and selected data adapters |
| `worker/routing.js` | OSRM alternatives checked against a supplied polygon |
| `backend/app.py` | Full FastAPI route implementation; local SQLite and optional ntfy/Bedrock |
| `backend/broadcast.py` | Canonical per-area message bundles from shared template/district JSON |
| `backend/bedrock.py` | Boto3 Converse loop; source retrieval and model brief validation |
| `backend/live.py` | FIRMS, weather, camera, roads, boundaries, demographics, alerts, perimeters, ORS |
| `backend/mcp_server.py` | Read-only retrieval tools; stdio or bearer-authenticated HTTP |
| `backend/core.py` | Python replay logic and tool-return functions |
| `index.py`, `api/index.py`, `vercel.json` | Two FastAPI Vercel entry points and rewrites; distinct from hosted Worker |
| `.openai/hosting.json` | Existing private Site ID and R2 binding |
| `scripts/build_districts.py` | Rebuild boundaries and optionally actual Census demographics |
| `scripts/build-worker.mjs` | Embed static assets; npm `build:sites` bundles Worker |
| `tests/` | Unit, API and routing tests; mocked external calls do not prove provider availability |

## API route index

**Both Python and Worker:** `/api/health`, `/api/scenario`, `POST /api/drafts`, `POST /api/drafts/{id}/approve`, `POST /api/drafts/{id}/send`, `POST /api/broadcast`, `GET /api/broadcasts/{id}`, `/api/audit`, `/api/live/weather`, `/api/live/alerts`, `/api/live/perimeters`, `POST /api/evac-route`.

**Python only:** `/api/live/firms`, `/api/live/routes`, `/api/live/camera`, `/api/live/demographics`, OpenAPI `/docs` and `/openapi.json`. MCP exposes additional boundary retrieval through the separate server; it is not mounted inside the deployed Worker.

**Bundle request:** `{geoids: [...], mode: "auto" | "all", reviewer: "...", reviewed: true}`. Both servers reconstruct localized messages from known recipient IDs and canonical templates; preview-language selection is never a sending parameter. Responses include the stored plan and record ID. Unknown recipients or missing review are rejected. No real notification is sent by the bundle endpoint.

See [plan audit](PLAN_AUDIT.md) and [credential inventory](API_KEYS.md) for readiness and deployment differences.

`GET /api/drafts/{id}/delivery` refreshes an existing Photon receipt. Both health endpoints expose delivery readiness without secrets.
