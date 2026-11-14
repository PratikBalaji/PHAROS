# API credentials and configuration inventory

Do not put secrets in source, `dist/`, `vercel.json`, browser settings, or a GitHub issue. Set secret values in the chosen hosting environment's secret fields. Share non-secret model IDs/regions and configuration decisions separately. Never supply AWS root credentials.

| Integration | Variables / access | Needs a key? | Implementation / hosted support |
| --- | --- | --- | --- |
| AWS Bedrock | `AWS_REGION`, `BEDROCK_MODEL_ID`, and a Boto3 credential chain with model invocation permission. For temporary environment credentials: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`; or use a role/profile. | AWS identity + model access; model ID/region are not secrets | `backend/bedrock.py`; Python only. Account/region must support selected model/inference profile and Converse tool use. Current Worker cannot activate this by setting variables. |
| NASA FIRMS | `FIRMS_MAP_KEY` | Free MAP_KEY required by current area CSV adapter | `backend/live.py: fetch_firms`; Python/MCP only. [Get key](https://firms.modaps.eosdis.nasa.gov/api/map_key/). Worker health no longer falsely reports a configured key as an active adapter. |
| Census ACS | `CENSUS_API_KEY` | Free key recommended; current dataset build uses it to attempt real ACS data. Live fetch code can attempt a request without it. | `scripts/build_districts.py`, `backend/live.py: fetch_language_demographics`. [Get key](https://api.census.gov/data/key_signup.html). Rebuild `dist/data/districts.json`, verify each source label, then redeploy. |
| OpenRouteService | `ORS_API_KEY` | Optional free API key for actual avoid-polygons routing | `backend/live.py: resolve_evac_route`; Python only. [Sign up](https://openrouteservice.org/dev/#/signup). Worker currently uses OSRM candidate rejection. |
| OSRM | `OSRM_URL` in Python, public default in Worker | No key for public demo service | Python and Worker routing. Observe demo limits or host your own service. |
| Open-Meteo | Latitude/longitude; no stored credentials | No key for current free endpoint | Python and Worker. Provider terms/rate limits apply. |
| NWS | `NWS_USER_AGENT` identifies the Python client; Worker sends generic app identifier | No API key | Python and Worker. Fire-weather alerts are not civil evacuation orders. |
| NIFC/WFIGS | Public ArcGIS query endpoint | No key | Python and Worker; live perimeters are not projected scenario geometry. |
| Census TIGERweb | Public ArcGIS boundaries endpoint | No key | Python/MCP + dataset-building script. Runtime Worker serves the committed dataset. |
| External AI camera feed | `CAMERA_FEED_URL`; optional `CAMERA_FEED_TOKEN` | Depends on chosen feed | `backend/live.py: fetch_camera_detections`; Python/MCP only. Need a JSON detection provider, not just an arbitrary camera stream URL. No local YOLO inference. |
| Photon Beta SMS | `PHOTON_API_KEY`, `PHOTON_PROJECT_ID`, `PHOTON_SENDER_ID`, `PHOTON_SPACE_ID`; `PHAROS_DELIVERY_PROVIDER=photon` | Project-scoped key + existing SMS sender/conversation | Implemented in Worker and Python; key/sender/space still needed. [Setup](PHOTON_SETUP.md). MCP OAuth is separate from app runtime credentials. |
| Google Gemini | `GEMINI_API_KEY`; optional `GEMINI_MODEL` | Free AI Studio key (Flash / Flash-Lite free tier; limits are per project) | `backend/gemini.py`, `backend/langplan.py`; Python/MCP only. [Get key](https://aistudio.google.com/apikey). Chooses each district's send languages from its demographic split and translates the exercise message. Without a key the console uses a share-based rule and fixed templates, labeled as such. Key travels in the `x-goog-api-key` header. |
| ntfy | `NTFY_TOPIC_URL`, optional/required-by-topic `NTFY_TOKEN` | URL required; token depends on topic permissions | `backend/app.py: send`; Python only. Current Worker stores a test receipt, not phone push. HTTP acceptance is not device receipt. |
| Remote MCP | `PHAROS_MCP_TOKEN`, plus transport/host/port | Generate a new strong app token; no vendor key | `backend/mcp_server.py`; mandatory for HTTP mode, not stdio. Requires separate hosted process and HTTPS. |
| MapLibre + CARTO basemap | Vendored MapLibre, public CARTO style | No Mapbox token needed | Frontend. External asset availability/terms still apply. |
| Terrain tiles | Public AWS S3 elevation tiles | No AWS credential | Frontend; unrelated to Bedrock account access. |
| Google Fonts | Public stylesheet/font endpoints | No key | Frontend, system-font fallback. |
| Sites R2 storage | `BUCKET` runtime binding | Provisioned by Sites, no key from user | Worker durable exercise records. |
| Twilio SMS | Not in source | Do not collect Twilio credentials yet | Would require a new integration, sender provisioning and recipient configuration. |
| D-Fire / YOLO | Dataset, compatible weights, inference/training compute | Not an API-key problem | Not implemented. Review dataset/model licenses and collect actual evaluation results. |

## Non-secret application settings

`PHAROS_ALLOWED_ORIGINS` (CORS, not authentication), `PHAROS_DB` (local/temporary SQLite path), `PHAROS_STAGE` (0/1/2), `PHAROS_MCP_TRANSPORT`, `PHAROS_MCP_HOST`, `PHAROS_MCP_PORT`. `VERCEL` is platform-provided. Vercel deployment authorization is separate from API credentials; never put a deployment token in app runtime variables.

## What to provide first

1. AWS region and accessible Bedrock model/inference-profile ID (non-secret).
2. Census API key through secret configuration, to rebuild real demographic data.
3. FIRMS MAP_KEY and optionally ORS_API_KEY, after choosing which runtime will consume them.
4. Chosen notification channel and its protected destination; camera provider and feed format if available.

At the initial audit the Site environment was empty. Photon setup subsequently configured the provider and project ID; the API key, sender and conversation are still outstanding. Do not assume that your personal Bedrock account access has already been configured on the app.
