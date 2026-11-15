import test from 'node:test';
import assert from 'node:assert/strict';
import {
  haversine, lineLength, bearingBetween, pointAlong, sliceFrom, pointInHazard, lineHitsHazard, splitByHazard,
  distanceToHazard, riskStops, overlapRatio, routeDiff, shouldReplan, hazardAreaKm2,
} from '../dist/routeanim.js';

const box = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]];
const POLY = { type: 'Polygon', coordinates: [box(-118.10, 34.10, -118.08, 34.12)] };
const MULTI = { type: 'MultiPolygon', coordinates: [[box(-118.10, 34.10, -118.09, 34.12)], [box(-118.07, 34.10, -118.06, 34.12)]] };
const LINE = [[-118.20, 34.11], [-118.00, 34.11]];      // runs west to east through the boxes
const CLEAR = [[-118.20, 34.00], [-118.00, 34.00]];     // runs south of them

test('distance and bearing basics', () => {
  assert.ok(Math.abs(haversine([0, 0], [0, 1]) - 111195) < 400);
  assert.ok(Math.abs(bearingBetween([0, 0], [1, 0]) - 90) < 0.01);
  assert.ok(Math.abs(bearingBetween([0, 0], [0, 1]) - 0) < 0.01);
  assert.ok(Math.abs(lineLength([[0, 0], [0, 1], [0, 2]]) - 222390) < 800);
});

test('pointAlong moves along the line, clamps at the end and reports heading', () => {
  const line = [[0, 0], [0.01, 0], [0.01, 0.01]];
  const total = lineLength(line);
  const mid = pointAlong(line, total / 2);
  assert.ok(mid.point[0] > 0.0049 && mid.point[0] <= 0.0101);
  const first = pointAlong(line, 10);
  assert.ok(Math.abs(first.bearing - 90) < 0.5);
  const end = pointAlong(line, total * 5);
  assert.equal(end.done, true);
  assert.deepEqual(end.point, [0.01, 0.01]);
  const ahead = sliceFrom(line, total * 0.75);
  assert.deepEqual(ahead[ahead.length - 1], [0.01, 0.01]);
  assert.ok(lineLength(ahead) < total * 0.3);
});

test('hazard tests work for Polygon and MultiPolygon', () => {
  assert.equal(pointInHazard([-118.09, 34.11], POLY), true);
  assert.equal(pointInHazard([-118.20, 34.11], POLY), false);
  assert.equal(pointInHazard([-118.065, 34.11], MULTI), true);
  assert.equal(pointInHazard([-118.08, 34.11], MULTI), false);   // gap between the two boxes
  assert.equal(lineHitsHazard(LINE, POLY), true);
  assert.equal(lineHitsHazard(LINE, MULTI), true);
  assert.equal(lineHitsHazard(CLEAR, MULTI), false);
  assert.equal(lineHitsHazard(null, POLY), false);
});

test('splitByHazard separates blocked stretches and distance/area are sensible', () => {
  const long = [[-118.20, 34.11], [-118.12, 34.11], [-118.05, 34.11], [-117.95, 34.11]];
  const { safe, blocked } = splitByHazard(long, POLY);
  assert.ok(blocked.length >= 1 && safe.length >= 1);
  assert.ok(distanceToHazard([-118.20, 34.11], POLY) > 9000);
  assert.equal(distanceToHazard([-118.09, 34.11], POLY), 0);
  const km2 = hazardAreaKm2(POLY);
  assert.ok(km2 > 3 && km2 < 5, `area ${km2}`);   // 0.02 x 0.02 degrees is about 4 km2
});

test('riskStops flags the part of a route near the fire', () => {
  const near = [[-118.1, 34.0], [-118.1, 34.095]];   // ends about 550 m from the box
  const stops = riskStops(near, POLY, 1200, 8);
  assert.equal(stops[0][1], 0);
  assert.equal(stops[stops.length - 1][1], 1);
  assert.ok(stops.every((s, i) => i === 0 || s[0] > stops[i - 1][0]));
});

const feat = (coords, d, t) => ({ geometry: { coordinates: coords }, properties: { distance_m: d, duration_s: t } });

test('routeDiff distinguishes same road, new road, withheld and resumed', () => {
  const road = [[-118.2, 34.1], [-118.15, 34.1], [-118.1, 34.1]];
  const shorter = [[-118.17, 34.1], [-118.15, 34.1], [-118.1, 34.1]];
  const other = [[-118.2, 34.1], [-118.15, 34.14], [-118.1, 34.1]];
  const a = { route: feat(road, 5000, 600) };
  assert.ok(overlapRatio(shorter, road) >= 0.8);
  assert.equal(routeDiff(a, { route: feat(shorter, 3000, 380) }).kind, 'unchanged');
  const re = routeDiff(a, { route: feat(other, 6200, 840) });
  assert.equal(re.kind, 'rerouted');
  assert.equal(re.dMin, 4);
  assert.equal(re.dKm, 1.2);
  // a detour over a fifth of the route is a reroute, not "the same road"
  const longRoad = [[-118.20, 34.10], [-118.18, 34.10], [-118.16, 34.10], [-118.14, 34.10], [-118.12, 34.10], [-118.10, 34.10]];
  const detour = [[-118.20, 34.10], [-118.18, 34.10], [-118.17, 34.112], [-118.15, 34.112], [-118.14, 34.10], [-118.12, 34.10], [-118.10, 34.10]];
  assert.equal(routeDiff({ route: feat(longRoad, 5000, 600) }, { route: feat(detour, 5400, 680) }).kind, 'rerouted');
  assert.equal(routeDiff(a, { route: null }).kind, 'withheld');
  assert.equal(routeDiff({ route: null }, { route: null }).kind, 'still-withheld');
  assert.equal(routeDiff({ route: null }, a).kind, 'resumed');
  assert.equal(routeDiff(null, a).kind, 'new');
});

test('shouldReplan is throttled and only fires for a reason', () => {
  const base = { now: 10000, lastAt: 0, route: CLEAR, hazard: POLY, area: 5, lastArea: 5 };
  assert.equal(shouldReplan({ ...base, neverPlanned: true }), 'first');
  assert.equal(shouldReplan({ ...base, route: LINE, now: 1000, lastAt: 0 }), null, 'too soon');
  assert.equal(shouldReplan({ ...base, route: LINE }), 'blocked');
  assert.equal(shouldReplan(base), null, 'clear route, nothing changed');
  const nearRoute = [[-118.1, 34.0], [-118.1, 34.095]];
  assert.equal(shouldReplan({ ...base, route: nearRoute, area: 6 }), 'near');
  assert.equal(shouldReplan({ ...base, route: nearRoute, area: 5 }), null, 'hazard unchanged');
  assert.equal(shouldReplan({ ...base, route: null, area: 6 }), 'retry');
  assert.equal(shouldReplan({ ...base, route: null, area: 5 }), null);
});

import { arrowPolygon } from '../dist/routeanim.js';

test('arrowPolygon points along the bearing and stays small and closed', () => {
  const p = [-118.15, 34.15];
  const north = arrowPolygon(p, 0, 100).coordinates[0];
  assert.deepEqual(north[0], north[north.length - 1]);
  assert.ok(north[0][1] > p[1], 'tip is north of the point');
  assert.ok(Math.abs(north[0][0] - p[0]) < 1e-9);
  const east = arrowPolygon(p, 90, 100).coordinates[0];
  assert.ok(east[0][0] > p[0], 'tip is east of the point');
  assert.ok(haversine(north[0], p) < 80);
});
