import test from 'node:test';
import assert from 'node:assert/strict';
import { projectFire, convexHull } from '../dist/firemodel.js';

const IGN = [-118.1356, 34.1922]; // Altadena-ish

test('convexHull returns a closed ring enclosing its points', () => {
  const ring = convexHull([[0, 0], [1, 0], [1, 1], [0, 1], [0.5, 0.5]]);
  assert.deepEqual(ring[0], ring[ring.length - 1]); // closed
  assert.ok(ring.length >= 5);
});

test('fire grows monotonically over steps and is deterministic for a seed', () => {
  const a = projectFire(IGN, { speed: 20, dirFrom: 270 }, { steps: 6, seed: 42 });
  const b = projectFire(IGN, { speed: 20, dirFrom: 270 }, { steps: 6, seed: 42 });
  const counts = a.frames.map(f => f.count);
  for (let i = 1; i < counts.length; i++) assert.ok(counts[i] >= counts[i - 1], 'burn area never shrinks');
  assert.ok(counts[counts.length - 1] > counts[0], 'fire spreads');
  assert.deepEqual(counts, b.frames.map(f => f.count), 'same seed -> same result');
});

test('each frame exposes a renderable fire FC and a closed hazard polygon', () => {
  const { frames } = projectFire(IGN, { speed: 15, dirFrom: 0 }, { steps: 4, seed: 7 });
  for (const f of frames) {
    assert.equal(f.fire.type, 'FeatureCollection');
    assert.ok(f.fire.features.length === f.count);
    assert.ok(f.fire.features.every(ft => ft.properties.heat >= 1));
    const ring = f.hazard.coordinates[0];
    assert.deepEqual(ring[0], ring[ring.length - 1], 'hazard ring is closed');
  }
});

test('strong wind biases the burn downwind (west wind pushes the fire east)', () => {
  // dirFrom 270 = wind FROM the west, so fire is pushed toward the east (+lon).
  const { frames } = projectFire(IGN, { speed: 50, dirFrom: 270 }, { steps: 8, seed: 11 });
  const last = frames[frames.length - 1];
  let sx = 0, n = 0;
  for (const ft of last.fire.features) {
    const ring = ft.geometry.coordinates[0];
    sx += (ring[0][0] + ring[2][0]) / 2; n++;
  }
  const meanLon = sx / n;
  assert.ok(meanLon > IGN[0], `burn centroid lon ${meanLon} should be east of ignition ${IGN[0]}`);
});
