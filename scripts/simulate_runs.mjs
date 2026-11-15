#!/usr/bin/env node
// Replay the Live Explorer's fire runs headlessly against live OSRM and report what the planner does.
// Uses the same pure decision code as the app (dist/liveplan.js, dist/routeanim.js), with no map or DOM.
//
//   NODE_USE_ENV_PROXY=1 node scripts/simulate_runs.mjs            # all runs at 1x
//   node scripts/simulate_runs.mjs altadena windshift              # chosen runs
//   OSRM_BASE=https://your-osrm.example node scripts/simulate_runs.mjs
//
// Behind a proxy, Node needs NODE_USE_ENV_PROXY=1 (and NODE_EXTRA_CA_CERTS for a custom CA).
import fs from 'node:fs';
import { FIRE_RUNS, ASSEMBLY_POINTS, RUN_STEPS, LOOKAHEAD_STEPS, buildRun, runById } from '../dist/fireruns.js';
import { pointAlong, lineLength, hazardAreaKm2, lineHitsHazard, riskStops, shouldReplan, sliceFrom, pointInHazard, distanceToHazard } from '../dist/routeanim.js';
import { chooseRoute, keepCurrentRoute, describePlan } from '../dist/liveplan.js';

const districts = JSON.parse(fs.readFileSync(new URL('../dist/data/districts.json', import.meta.url)));
const centroid = geoid => districts.features.find(f => f.properties.GEOID === geoid).properties.centroid;
const BASE = process.env.OSRM_BASE || 'https://router.project-osrm.org';
const TRIP_STEPS = 14, STEP_MS = 2500, SPEED = 1;
const VERBOSE = process.argv.includes('--verbose');
const wait = ms => new Promise(r => setTimeout(r, ms));
let calls = 0;

async function fetchRoute(origin, dest, hazard) {
  calls++;
  await wait(350); // be polite to the public demo server
  const url = `${BASE}/route/v1/driving/${origin[0]},${origin[1]};${dest[0]},${dest[1]}?alternatives=true&overview=full&geometries=geojson`;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const j = await (await fetch(url)).json();
      if (j.code !== 'Ok' || !j.routes?.length) throw new Error('no route');
      const listed = j.routes.map((x, i) => ({ id: 'R' + (i + 1), distance_m: Math.round(x.distance), duration_s: Math.round(x.duration), geometry: x.geometry, safe: !lineHitsHazard(x.geometry.coordinates, hazard) }));
      const safe = listed.filter(x => x.safe);
      if (!safe.length) return { route: null, candidate_routes: listed };
      const best = safe.reduce((a, b) => a.distance_m <= b.distance_m ? a : b);
      return { route: { type: 'Feature', geometry: best.geometry, properties: { distance_m: best.distance_m, duration_s: best.duration_s } }, candidate_routes: listed, chosen_id: best.id };
    } catch (e) { await wait(800); }
  }
  throw new Error('routing unavailable');
}

async function simulate(run) {
  const data = buildRun(run, centroid(run.geoid));
  const s = { step: 0, idx: -1, hazard: null, planHazard: null, area: 0, planArea: 0, lastPlanArea: 0, caught: false, vehicleM: 0, vstep: null, route: null, coords: null, plan: null,
    destName: run.primary, lastPlanAt: -1e9, arrived: false, origin: centroid(run.geoid), vehicle: null };
  const out = { id: run.id, events: [], reroutes: 0, switches: 0, withheld: 0, resumed: 0, nearKept: 0 };
  calls = 0;

  const plan = async reason => {
    const origin = s.vehicle || s.origin;
    const tried = [];
    const logged = async (o, d, h) => { const r = await fetchRoute(o, d, h); tried.push(`${ASSEMBLY_POINTS.find(a => a.lonlat === d).name}:${(r.candidate_routes || []).map(c => c.safe ? 'safe' : 'hit').join('/') || 'none'}`); return r; };
    const { found, lastTry } = await chooseRoute({ origin, hazard: s.planHazard, primary: run.primary, points: ASSEMBLY_POINTS, fetchRoute: VERBOSE ? logged : fetchRoute });
    if (VERBOSE) out.events.push(`  [plan ${reason} @${s.step.toFixed(2)}] vehicle ${s.vehicle ? (pointInHazard(s.vehicle, s.hazard) ? 'INSIDE hazard' : distanceToHazard(s.vehicle, s.hazard).toFixed(0) + ' m from hazard') : 'at start'} | ${tried.join(' ; ')} -> ${found ? found.dest.name : 'none'}`);
    if (found && keepCurrentRoute({ reason, routeCoords: s.coords, vehicleM: s.vehicleM, hazard: s.planHazard })) { out.nearKept++; return; }
    const { next, diff, switched } = describePlan({ plan: s.plan, route: s.route, routeCoords: s.coords, vehicleM: s.vehicleM, destName: s.destName, found });
    const at = `step ${s.step.toFixed(1)}`;
    if (found) {
      s.route = found.res.route; s.coords = s.route.geometry.coordinates; s.vehicleM = 0; s.arrived = false;
      if (!s.vstep) s.vstep = Math.min(900, Math.max(250, lineLength(s.coords) / TRIP_STEPS));
      s.destName = found.dest.name;
      out.lastRoute = { assembly: found.dest.name, minutes: Math.max(1, Math.round(s.route.properties.duration_s / 60)), km: Math.round(s.route.properties.distance_m / 100) / 10 };
      if (switched) { out.switches++; out.events.push(`${at} switched to ${found.dest.name} (${reason})`); }
      if (diff.kind === 'rerouted' || switched) out.reroutes++;
      if (diff.kind === 'rerouted' && !switched) out.events.push(`${at} rerouted ${diff.dMin >= 0 ? '+' : ''}${diff.dMin} min (${reason})`);
      if (diff.kind === 'resumed') { out.resumed++; out.events.push(`${at} route restored`); }
    } else {
      s.route = null; s.coords = null;
      if (diff.kind === 'withheld') { out.withheld++; out.events.push(`${at} WITHHELD (${reason})`); }
    }
    s.plan = next;
  };

  const maybePlan = async force => {
    if (s.vehicle && pointInHazard(s.vehicle, s.hazard)) {
      if (!s.caught) { s.caught = true; s.route = null; s.coords = null; s.plan = { route: null, dest: null }; out.events.push(`step ${s.step.toFixed(1)} VEHICLE INSIDE FIRE AREA`); }
      return;
    }
    const now = s.step * STEP_MS / SPEED;
    const ahead = s.coords ? sliceFrom(s.coords, s.vehicleM) : null;
    const why = force ? 'first' : shouldReplan({ now, lastAt: s.lastPlanAt, minGapMs: Math.max(700, 1800 / SPEED), retryGapMs: 7500 / SPEED, neverPlanned: !s.plan,
      route: s.arrived ? [] : ahead, hazard: s.planHazard, area: s.planArea, lastArea: s.lastPlanArea, nearMeters: 700 });
    if (why === 'near' && now - s.lastPlanAt < 6000 / SPEED) return;
    if (why && !s.arrived) { s.lastPlanAt = now; s.lastPlanArea = s.planArea; await plan(why); }
  };

  const show = i => { s.idx = i; const f = data.frames[i]; s.hazard = f.hazardCells; s.planHazard = data.frames[Math.min(i + LOOKAHEAD_STEPS, data.frames.length - 1)].hazardCells; s.area = hazardAreaKm2(f.hazardCells); s.planArea = hazardAreaKm2(s.planHazard); };
  show(0); await maybePlan(true);
  const dS = 0.25;
  while (s.step < RUN_STEPS) {
    s.step = Math.min(RUN_STEPS, s.step + dS);
    if (s.coords && !s.arrived && s.vstep) {
      s.vehicleM += dS * s.vstep;
      const at = pointAlong(s.coords, s.vehicleM); s.vehicle = at.point;
      if (at.done) { s.arrived = true; out.events.push(`step ${s.step.toFixed(1)} ARRIVED at ${s.destName}`); }
    }
    const idx = Math.floor(s.step);
    if (idx !== s.idx) { show(idx); await maybePlan(false); }
  }
  out.calls = calls; out.arrived = s.arrived; out.endedWithRoute = !!s.route;
  out.outcome = s.arrived ? 'arrived' : !s.route ? 'withheld' : (out.reroutes || out.switches) ? 'rerouted' : 'driving';
  return out;
}

const wanted = process.argv.slice(2).filter(a => !a.startsWith('--'));
const runs = wanted.length ? wanted.map(runById) : FIRE_RUNS;
const JSON_OUT = process.argv.includes('--json'); // machine-readable facts for the SMS sender
const facts = [];
for (const run of runs) {
  const r = await simulate(run);
  if (JSON_OUT) { facts.push({ run: run.id, runName: run.name, geoid: run.geoid, outcome: r.outcome, reroutes: r.reroutes, switches: r.switches, withheld: r.withheld, ...(r.lastRoute || {}) }); continue; }
  console.log(`\n${r.id.padEnd(11)} calls ${String(r.calls).padStart(2)} | reroutes ${r.reroutes} | assembly switches ${r.switches} | withheld ${r.withheld} | restored ${r.resumed} | near-kept ${r.nearKept} | ${r.arrived ? 'ARRIVED' : r.endedWithRoute ? 'still driving' : 'no route at end'}`);
  for (const e of r.events) console.log('   ', e);
}
if (JSON_OUT) console.log(JSON.stringify(facts, null, 2));
