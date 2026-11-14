// Predictive fire-spread: a wind-biased cellular automaton over a real lng/lat grid.
// SIMPLIFIED and NOT an operational fire model — for exercise/decision-support only.
// projectFire() returns per-timestep frames, each with:
//   - fire:   a GeoJSON FeatureCollection of burned cell squares (properties.heat) to render
//             as a 3D extrusion (the irregular "cellular" front).
//   - hazard: a single GeoJSON Polygon (convex hull of the burn) used to reroute around it.
//   - count:  number of burned cells.
// Deterministic given a seed, so the UI and tests are reproducible.

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Convex hull (Andrew's monotone chain). points: [[lon,lat],...] -> closed ring [[lon,lat],...].
export function convexHull(points) {
  const pts = points.slice().sort((p, q) => (p[0] - q[0]) || (p[1] - q[1]));
  if (pts.length < 3) return pts.slice();
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper = [];
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  const ring = lower.slice(0, -1).concat(upper.slice(0, -1));
  ring.push(ring[0]);
  return ring;
}

// Meteorological wind direction (degrees FROM which it blows) -> unit vector the fire is pushed TO.
function downwindVector(windDirFromDeg) {
  const toBearing = ((Number(windDirFromDeg) || 0) + 180) * Math.PI / 180; // clockwise from north
  return { e: Math.sin(toBearing), n: Math.cos(toBearing) };
}

/**
 * @param {[number,number]} ignition  [lon, lat]
 * @param {{speed:number, dirFrom:number}} wind  speed (km/h), dirFrom (deg, meteorological)
 * @param {object} opts  { steps, grid, spanDeg, baseProb, windStrength, seed }
 * @returns {{ frames: Array, meta: object }}
 */
export function projectFire(ignition, wind = {}, opts = {}) {
  const steps = opts.steps ?? 6;
  const grid = opts.grid ?? 41;                 // cells per side (odd -> centered ignition)
  const spanDeg = opts.spanDeg ?? 0.09;         // total latitude span of the grid (~10 km)
  const baseProb = opts.baseProb ?? 0.22;
  const speed = Math.max(0, Number(wind.speed) || 0);
  const windStrength = (opts.windStrength ?? 0.12) * Math.min(speed, 60); // saturates
  const rnd = mulberry32(opts.seed ?? 1337);
  const wv = downwindVector(wind.dirFrom);

  const lat = ignition[1];
  const cellLat = spanDeg / grid;
  const cellLon = (spanDeg / grid) / Math.max(0.2, Math.cos(lat * Math.PI / 180));
  const originLon = ignition[0] - (cellLon * grid) / 2;
  const originLat = ignition[1] - (cellLat * grid) / 2;

  const ignitedAt = new Int16Array(grid * grid).fill(-1);
  const idx = (r, c) => r * grid + c;
  const center = Math.floor(grid / 2);
  ignitedAt[idx(center, center)] = 0;

  const cellPolygon = (r, c) => {
    const x0 = originLon + c * cellLon, y0 = originLat + r * cellLat;
    const x1 = x0 + cellLon, y1 = y0 + cellLat;
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]];
  };

  const neighbours = [[-1, -1], [-1, 0], [-1, 1], [0, -1], [0, 1], [1, -1], [1, 0], [1, 1]];
  const frames = [];

  for (let s = 1; s <= steps; s++) {
    const toIgnite = [];
    for (let r = 0; r < grid; r++) {
      for (let c = 0; c < grid; c++) {
        if (ignitedAt[idx(r, c)] < 0 || ignitedAt[idx(r, c)] > s - 1) continue;
        for (const [dr, dc] of neighbours) {
          const nr = r + dr, nc = c + dc;
          if (nr < 0 || nc < 0 || nr >= grid || nc >= grid) continue;
          if (ignitedAt[idx(nr, nc)] >= 0) continue;
          // geographic direction of this neighbour (east=+dc, north=-dr)
          const len = Math.hypot(dc, -dr) || 1;
          const align = (dc / len) * wv.e + (-dr / len) * wv.n; // dot with downwind
          const p = baseProb * (1 + windStrength * Math.max(0, align)) / (len > 1.1 ? 1.6 : 1); // diagonals slower
          if (rnd() < p) toIgnite.push(idx(nr, nc));
        }
      }
    }
    for (const i of toIgnite) if (ignitedAt[i] < 0) ignitedAt[i] = s;

    // build frame
    const features = [];
    const corners = [];
    for (let r = 0; r < grid; r++) {
      for (let c = 0; c < grid; c++) {
        const t = ignitedAt[idx(r, c)];
        if (t < 0) continue;
        const ring = cellPolygon(r, c);
        features.push({ type: 'Feature', properties: { heat: s - t + 1 }, geometry: { type: 'Polygon', coordinates: [ring] } });
        for (const pt of ring) corners.push(pt);
      }
    }
    const hullRing = convexHull(corners);
    frames.push({
      step: s,
      count: features.length,
      fire: { type: 'FeatureCollection', features },
      hazard: { type: 'Polygon', coordinates: [hullRing.length >= 4 ? hullRing : cellPolygon(center, center)] },
    });
  }

  return {
    frames,
    meta: {
      ignition, steps, grid, spanDeg,
      wind: { speed, dirFrom: Number(wind.dirFrom) || 0 },
      note: 'Simulated wind-driven cellular projection. Simplified and not an operational fire model.',
    },
  };
}
