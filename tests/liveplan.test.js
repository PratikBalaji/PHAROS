import test from 'node:test';
import assert from 'node:assert/strict';
import { destinationOrder, chooseRoute, keepCurrentRoute, describePlan } from '../dist/liveplan.js';

const box = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]];
const HAZARD = { type: 'MultiPolygon', coordinates: [[box(-118.12, 34.10, -118.10, 34.12)]] };
const POINTS = [
  { name: 'Primary', lonlat: [-118.30, 34.10] },
  { name: 'Near', lonlat: [-118.25, 34.10] },
  { name: 'Mid', lonlat: [-118.20, 34.10] },
  { name: 'Far', lonlat: [-118.00, 34.10] },
  { name: 'Burned', lonlat: [-118.11, 34.11] },
];
const ORIGIN = [-118.22, 34.10];
const feat = (coords, d = 1000, t = 120) => ({ type: 'Feature', geometry: { type: 'LineString', coordinates: coords }, properties: { distance_m: d, duration_s: t } });

test('destinationOrder tries the primary first, skips burned points and caps the list', () => {
  const order = destinationOrder({ origin: ORIGIN, hazard: HAZARD, primary: 'Primary', points: POINTS });
  assert.deepEqual(order.map(p => p.name), ['Primary', 'Mid', 'Near']);   // Burned is inside the hazard; nearest others follow
  const lost = destinationOrder({ origin: ORIGIN, hazard: HAZARD, primary: 'Burned', points: POINTS });
  assert.ok(!lost.some(p => p.name === 'Burned'), 'a burned primary is dropped');
  assert.equal(lost[0].name, 'Mid');
});

test('chooseRoute falls through to the next assembly point when a route is withheld', async () => {
  const calls = [];
  const fetchRoute = async (origin, dest) => {
    calls.push(dest);
    return dest[0] === -118.30 ? { route: null, candidate_routes: [] } : { route: feat([origin, dest]), candidate_routes: [], chosen_id: 'R1' };
  };
  const out = await chooseRoute({ origin: ORIGIN, hazard: HAZARD, primary: 'Primary', points: POINTS, fetchRoute });
  assert.equal(out.found.dest.name, 'Mid');
  assert.equal(calls.length, 2);
});

test('chooseRoute reports nothing found, and stops quietly when the run changed', async () => {
  const none = await chooseRoute({ origin: ORIGIN, hazard: HAZARD, primary: 'Primary', points: POINTS, fetchRoute: async () => ({ route: null, candidate_routes: [] }) });
  assert.equal(none.found, null);
  assert.ok(none.lastTry, 'the last attempt is kept so its alternatives can be drawn');
  let n = 0;
  const stale = await chooseRoute({ origin: ORIGIN, hazard: HAZARD, primary: 'Primary', points: POINTS, fetchRoute: async () => ({ route: null }), isStale: () => ++n > 0 });
  assert.equal(stale.stale, true);
});

test('keepCurrentRoute only holds a safe route during a "fire nearby" check', () => {
  const safe = [[-118.30, 34.05], [-118.14, 34.05]];
  const cut = [[-118.30, 34.11], [-118.05, 34.11]];
  assert.equal(keepCurrentRoute({ reason: 'near', routeCoords: safe, vehicleM: 0, hazard: HAZARD }), true);
  assert.equal(keepCurrentRoute({ reason: 'near', routeCoords: cut, vehicleM: 0, hazard: HAZARD }), false);
  assert.equal(keepCurrentRoute({ reason: 'blocked', routeCoords: safe, vehicleM: 0, hazard: HAZARD }), false);
  assert.equal(keepCurrentRoute({ reason: 'near', routeCoords: null, vehicleM: 0, hazard: HAZARD }), false);
});

test('describePlan separates new, unchanged, rerouted, switched and withheld', () => {
  const road = [[-118.30, 34.05], [-118.25, 34.05], [-118.20, 34.05], [-118.15, 34.05], [-118.10, 34.05]];
  const dest = { name: 'Primary' };
  const first = describePlan({ plan: null, route: null, routeCoords: null, vehicleM: 0, destName: 'Primary', found: { res: { route: feat(road, 9000, 900) }, dest } });
  assert.equal(first.diff.kind, 'new');
  const plan = first.next;
  // asked again from further along the same road: still the same road
  const rest = [[-118.22, 34.05], [-118.20, 34.05], [-118.15, 34.05], [-118.10, 34.05]];
  const same = describePlan({ plan, route: plan.route, routeCoords: road, vehicleM: 2500, destName: 'Primary', found: { res: { route: feat(rest, 6000, 600) }, dest } });
  assert.equal(same.diff.kind, 'unchanged');
  // a different road to the same place
  const detour = [[-118.22, 34.05], [-118.20, 34.09], [-118.12, 34.09], [-118.10, 34.05]];
  const re = describePlan({ plan, route: plan.route, routeCoords: road, vehicleM: 2500, destName: 'Primary', found: { res: { route: feat(detour, 8000, 900) }, dest } });
  assert.equal(re.diff.kind, 'rerouted');
  assert.equal(re.switched, false);
  // the same road shape but a different assembly point is a switch
  const sw = describePlan({ plan, route: plan.route, routeCoords: road, vehicleM: 2500, destName: 'Primary', found: { res: { route: feat(rest, 6000, 600) }, dest: { name: 'Mid' } } });
  assert.equal(sw.switched, true);
  const gone = describePlan({ plan, route: plan.route, routeCoords: road, vehicleM: 2500, destName: 'Primary', found: null });
  assert.equal(gone.diff.kind, 'withheld');
  assert.equal(gone.next.route, null);
});
