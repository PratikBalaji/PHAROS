# PHAROS plan audit — November 14, 2026

**Photon update:** Photon Beta SMS adapters now exist in Worker and Python, with approved-draft submission, idempotency and receipt refresh. Provider/project settings are configured; API key, sender and SMS conversation remain outstanding. No live SMS delivery has been verified. This replaces Twilio as the selected texting platform. See [setup](PHOTON_SETUP.md). The table below records the original audit.

Reviewed after pulling `116e8e7` from GitHub main. **The hackathon exercise workflow is built; the original end-to-end AI detection and emergency dispatch vision is not complete.** This assessment is based on source and runtime configuration, not README claims alone.

| Original goal | Current evidence | Status / remaining work |
| --- | --- | --- |
| MCP server modeled on NaDIng | `backend/mcp_server.py` provides typed read-only tools over stdio and authenticated HTTP | Implemented in Python. No supplied NaDIng reference to verify architectural parity. Not deployed on the current Worker site. |
| Unify NASA FIRMS + AI cameras | `backend/live.py` implements separate FIRMS and camera adapters; MCP exposes them | Partial. Not fused by spatial/temporal correlation into a live incident. Camera records are external provider reports or fixtures. Worker has neither adapter. |
| Fine-tuned YOLOv8 on D-Fire | No training scripts, weights, detector inference, evaluation split or detector dependency in source | Not built. A feed API key will not implement a model. Need data/weights, GPU training or selected pretrained weights, and held-out evaluation. |
| 92.4% precision / 89.1% recall | No supporting detector evaluation artifact | Unmeasured target, not an achieved result. |
| Claude via Bedrock | `backend/bedrock.py` uses Converse with four typed tool calls and JSON/source-ID checks | Implemented and mocked in tests, not live-verified. Model writes an incident brief; deterministic code selects scenario routes and message template. Does not invoke MCP transport. Worker has no Bedrock client. |
| Event + forecast reasoning | Forecast and source adapters exist; replay uses fixtures | Partial. No validated live incident fusion or operational spread forecasting. Cellular fire projection is an exercise model. |
| Route planning | Python: ORS avoid-polygons with OSRM fallback; Worker: OSRM candidates and polygon rejection | Implemented for exercise decision support. Road closure freshness, verified destinations, traffic/capacity, and authoritative safety checks remain missing. |
| Automated emergency dispatch via Twilio | No Twilio integration exists. Python has ntfy adapter; Worker records test inbox entries | Not built as specified. Need recipient enrollment, channel selection, provider setup and permissioned delivery. Official IPAWS/WEA is out of scope. |
| 99.2% reliability / 2.4-second alert-to-route latency | No statistically supported measurement | Unmeasured targets. Test pass rate is not operational reliability. |
| Operator review + audit | Named approvals, invalidation, expiry, duplicate test-send protection; Worker R2 persistence | Working deployed exercise workflow. Does not establish production operational readiness. |
| Multilingual communication | Nine fixed templates; automatic per-district bundles added in this change | Exercise workflow built. No model-based translation/back-translation; non-English templates need native-speaker review. Demographic groups can exceed supported template coverage. |
| Real demographic targeting | Committed districts contain `demographics_source: illustrative` | Not real demographic estimates yet. Configure Census key, rebuild dataset, inspect results, redeploy. Setting a runtime key alone does not replace the committed dataset. |
| Presentation | Six-slide deck embeds app with a timed script | Built. Script must keep distinguishing replay, templates, Python-only capabilities and live services. |

## Runtime gap that keys alone cannot solve

The published private site runs `worker/index.js` + `worker/api.js`, with durable R2 storage. FastAPI, Bedrock, ntfy and the Python MCP service are separate code paths. The Worker does not execute Python. No provider environment variables were configured on the Site when inspected. The checked execution environment also had no listed provider variables set; this does not inspect credentials in the user's own AWS account or device.

Choose a deployment approach before configuring Bedrock/FIRMS/camera/ntfy: deploy and connect the full Python backend, or implement those missing adapters in the Worker. Existing Vercel service configuration is in the repository, but successful live Vercel provisioning has not been established.

## Prioritized finish plan

1. Keep the verified replay + approved multilingual exercise bundle as the demo's dependable core.
2. Rebuild and validate Census demographics; real recommendations improve the console immediately.
3. Activate a real Bedrock brief in the chosen runtime; show engine, tool evidence and measured latency.
4. Add FIRMS/camera incident correlation, with timestamps, provenance and stale-data behavior.
5. Configure one controlled test-notification channel and verify device receipt separately from provider acceptance.
6. Evaluate actual smoke inference and collect performance evidence before adding numeric claims.
