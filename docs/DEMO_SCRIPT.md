# PHAROS demo script (about 5 minutes)

**One sentence:** PHAROS helps an emergency office tell every resident what is happening in the language they actually speak, and keeps evacuation routes honest while a fire changes the map.

Everything on screen is an **exercise**: fire runs are fictional, messages start with an "EXERCISE ONLY" marker, and a named human must sign off before anything is sent. Say this once, early.

## Before you go on stage (2 minutes)
1. Open https://www.pharos.casa/api/health. You want `"status":"ok"`, `gemini_configured: true`, and your delivery channel `configured: true`.
2. Subscribe your phone to the ntfy topic and put it where the audience can see it (or screen-mirror it).
3. Open the site in a fresh private window at 1440 px wide or larger. Zoom the browser to 100%.
4. Have the Live Explorer's **Wind-Shift Run** and **Verdugo Hills** in mind. Do one dry run of the Console so Gemini's first call is warm.
5. Backup plan: if Gemini is slow, say "it is drafting live" and wait up to 10 seconds. If it fails, the screen shows "Fixed templates (Gemini unavailable)". Say that is the safety fallback working.

## 0:00 - 0:30  The problem
"When a wildfire moves, two things fail people. The alert is in a language they do not read, and the evacuation route is out of date within minutes. PHAROS is a communication relay that fixes both. The name means lighthouse."

## 0:30 - 2:00  Console: the right language for each district  (click path)
1. Sidebar **Console**. Click **Glendale city** and **Arcadia city**.
2. Point at the demographic bars: "These are real US Census numbers. About 38 percent of Glendale speaks an Indo-European language that is largely Armenian. Arcadia is a third Chinese-speaking."
3. Click **Choose languages with AI**. Read the reason Gemini gives: "It picks the languages and explains why, citing the shares. A rule guarantees no big group is skipped."
4. Click **Draft with Gemini**. Open the Armenian and Spanish drafts: "Gemini writes each message in its own language, including English. Nothing here is a fixed sentence."
5. Point at the safety design: "Every draft starts with a fixed EXERCISE marker added by the server, not the model. They are flagged unreviewed, and the server rejects any draft that drops the district name or invents routes, times or links."
6. Type a reviewer name, tick the review box, click **Publish** (or Send). Show the phone buzzing. "One review, every language, delivered."

## 2:00 - 3:45  Live Explorer: routes that change with the fire
1. Sidebar **Map**, then **LIVE EXPLORER**.
2. Click **Wind-Shift Run**, press **2x**, then **Play**.
3. Narrate while it runs: "This is a fictional fire on a real road network. The route is live, from OpenStreetMap routing. The engine plans against where the fire will be in fifteen minutes, not where it is now."
4. When the route turns amber near the fire: "The colour shows risk along the route." When the log shows **Rerouted**: "It reroutes before the road is cut."
5. Pick **Verdugo Hills** and play. "Here both exits are cut. PHAROS does not invent a route. It withholds it, says why, and tells people to wait for official instructions. Saying no is a feature."

## 3:45 - 4:30  Open data and agents
Sidebar **Integrations**: "NASA satellite detections, weather, real fire perimeters from the national interagency feed, Census, routing. Credentials stay on the server. It also exposes read-only tools through MCP, so other AI agents can ask for evidence or a language plan. They cannot send anything."

## 4:30 - 5:00  Close
"PHAROS never pretends. The data is labeled, the messages are marked, the model drafts and a person approves. Next steps are native-speaker review of translations and a registered sender for real delivery."

## Likely questions
- **Is this a real alerting system?** No. It is an exercise tool. It never uses public alert systems (WEA/IPAWS) and every message says so.
- **Are the translations accurate?** They are machine drafts, flagged "unreviewed". The design requires native-speaker review before real use.
- **Is the fire prediction real?** No. It is a simplified wind-driven model for routing demos, not an operational forecast.
- **Why not just use Google Maps?** It does not know the fire perimeter, does not withhold when no safe route exists, and does not handle who should be told in which language.
- **What is real data and what is not?** Real: Census demographics, fire perimeters, NASA detections, weather, road routing. Fictional: the eight fire runs and the replay scenario.
- **What if Gemini is down?** The Console falls back to fixed templates, labeled as such.

## Do not say
- That messages reached real residents. They go to one test channel.
- That the fire runs are forecasts.
- That Armenian is measured directly: the Census category is "Other Indo-European", mapped to Armenian for Glendale as a stated assumption.
