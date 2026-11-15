import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { FIRE_RUNS, ASSEMBLY_POINTS, buildRun, windFor, runById, RUN_STEPS } from '../dist/fireruns.js';
import { pointInHazard, hazardAreaKm2, haversine } from '../dist/routeanim.js';

const districts = JSON.parse(fs.readFileSync(new URL('../dist/data/districts.json', import.meta.url)));
const centroid = geoid => districts.features.find(f => f.properties.GEOID === geoid).properties.centroid;

test('there are 8 runs with unique ids, real districts and known assembly points', () => {
  assert.equal(FIRE_RUNS.length, 8);
  assert.equal(new Set(FIRE_RUNS.map(r => r.id)).size, 8);
  const names = new Set(ASSEMBLY_POINTS.map(a => a.name));
  for (const r of FIRE_RUNS) {
    assert.ok(districts.features.some(f => f.properties.GEOID === r.geoid), `${r.id} district exists`);
    assert.ok(names.has(r.primary), `${r.id} primary assembly exists`);
    assert.ok(r.blurb.length > 10);
    assert.ok(haversine(r.ignition, centroid(r.geoid)) < 12000, `${r.id} ignition is near its district`);
  }
  assert.equal(runById('nope').id, FIRE_RUNS[0].id);
});

test('each run has 25 deterministic frames, growing, with a tight hazard of sensible size', () => {
  for (const r of FIRE_RUNS) {
    const a = buildRun(r, centroid(r.geoid)).frames;
    assert.equal(a.length, RUN_STEPS + 1);
    assert.equal(a[0].count, 1, 'frame 0 is only the ignition cell');
    for (let i = 1; i < a.length; i++) assert.ok(a[i].count >= a[i - 1].count);
    assert.equal(a[0].hazardCells.type, 'MultiPolygon');
    const km2 = hazardAreaKm2(a[RUN_STEPS].hazardCells);
    assert.ok(km2 > 5 && km2 < 80, `${r.id} final hazard ${km2.toFixed(1)} km2`);
    assert.ok(hazardAreaKm2(a[RUN_STEPS].hazardCells) > hazardAreaKm2(a[0].hazardCells));
  }
});

test('the vehicle starting point is safe for the first steps of every run', () => {
  for (const r of FIRE_RUNS) {
    const c = centroid(r.geoid);
    const frames = buildRun(r, c).frames;
    for (let i = 0; i <= 3; i++) assert.equal(pointInHazard(c, frames[i].hazardCells), false, `${r.id} origin safe at step ${i}`);
  }
});

test('the wind-shift run changes wind at step 11 and the burn turns around', () => {
  const r = runById('windshift');
  const w = windFor(r);
  assert.equal(w(10).dirFrom, 45);
  assert.equal(w(11).dirFrom, 250);
  const frames = buildRun(r, centroid(r.geoid)).frames;
  assert.equal(frames[10].wind.dirFrom, 45);
  assert.equal(frames[12].wind.dirFrom, 250);
  const meanLon = f => f.fire.features.reduce((s, ft) => s + ft.geometry.coordinates[0][0][0], 0) / f.count;
  assert.ok(meanLon(frames[11]) < meanLon(frames[1]), 'north-east wind drives the burn west first');
  assert.ok(meanLon(frames[24]) > meanLon(frames[11]), 'after the shift it drives back east');
});
