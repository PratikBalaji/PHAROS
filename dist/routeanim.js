// Pure helpers for live rerouting: geometry on [lon,lat] lines, hazard tests against a Polygon or
// MultiPolygon, and the small decisions the simulation makes (when to re-plan, what changed).
// No DOM and no map code here, so everything is unit-testable.

const EARTH = 6371000;
const rad = d => d * Math.PI / 180;

export function haversine(a, b) {
  const dLat = rad(b[1] - a[1]), dLon = rad(b[0] - a[0]);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a[1])) * Math.cos(rad(b[1])) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function lineLength(coords) {
  let m = 0;
  for (let i = 1; i < coords.length; i++) m += haversine(coords[i - 1], coords[i]);
  return m;
}

// Compass bearing in degrees (0 = north, clockwise) from a to b.
export function bearingBetween(a, b) {
  const y = Math.sin(rad(b[0] - a[0])) * Math.cos(rad(b[1]));
  const x = Math.cos(rad(a[1])) * Math.sin(rad(b[1])) - Math.sin(rad(a[1])) * Math.cos(rad(b[1])) * Math.cos(rad(b[0] - a[0]));
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

// Position after travelling `meters` along the line. Clamps to the ends.
export function pointAlong(coords, meters) {
  if (!coords || coords.length < 2) return { point: coords && coords[0] || null, bearing: 0, index: 0, done: true, traveled: 0 };
  let left = Math.max(0, meters);
  for (let i = 1; i < coords.length; i++) {
    const seg = haversine(coords[i - 1], coords[i]);
    if (left <= seg || i === coords.length - 1) {
      const t = seg > 0 ? Math.min(1, left / seg) : 0;
      const a = coords[i - 1], b = coords[i];
      return {
        point: [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t],
        bearing: bearingBetween(a, b), index: i - 1,
        done: left >= seg && i === coords.length - 1,
        traveled: Math.min(meters, lineLength(coords)),
      };
    }
    left -= seg;
  }
  return { point: coords[coords.length - 1], bearing: 0, index: coords.length - 2, done: true, traveled: lineLength(coords) };
}

// The part of the line still ahead after `meters`, starting at the exact current position.
export function sliceFrom(coords, meters) {
  const at = pointAlong(coords, meters);
  if (!at.point) return [];
  return [at.point, ...coords.slice(at.index + 1)];
}

// ---- hazard geometry (Polygon or MultiPolygon) ----

export function toPolys(geom) {
  if (!geom) return [];
  if (geom.type === 'MultiPolygon') return geom.coordinates;
  if (geom.type === 'Polygon') return [geom.coordinates];
  return [];
}

function ringContains(ring, x, y) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / ((yj - yi) || 1e-12) + xi) inside = !inside;
  }
  return inside;
}

function bbox(ring) {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  for (const [x, y] of ring) { if (x < minx) minx = x; if (x > maxx) maxx = x; if (y < miny) miny = y; if (y > maxy) maxy = y; }
  return [minx, miny, maxx, maxy];
}

export function pointInHazard(pt, geom) {
  for (const poly of toPolys(geom)) {
    const [minx, miny, maxx, maxy] = bbox(poly[0]);
    if (pt[0] < minx || pt[0] > maxx || pt[1] < miny || pt[1] > maxy) continue;
    if (ringContains(poly[0], pt[0], pt[1]) && !poly.slice(1).some(h => ringContains(h, pt[0], pt[1]))) return true;
  }
  return false;
}

const ccw = (a, b, c) => (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0]);
const cross = (a, b, c, d) => ccw(a, c, d) !== ccw(b, c, d) && ccw(a, b, c) !== ccw(a, b, d);

function segmentHits(a, b, geom) {
  const sx0 = Math.min(a[0], b[0]), sx1 = Math.max(a[0], b[0]), sy0 = Math.min(a[1], b[1]), sy1 = Math.max(a[1], b[1]);
  for (const poly of toPolys(geom)) {
    const [minx, miny, maxx, maxy] = bbox(poly[0]);
    if (sx1 < minx || sx0 > maxx || sy1 < miny || sy0 > maxy) continue;
    for (const ring of poly) for (let i = 0; i < ring.length - 1; i++) if (cross(a, b, ring[i], ring[i + 1])) return true;
  }
  return false;
}

export function lineHitsHazard(coords, geom) {
  if (!coords || !geom) return false;
  for (let i = 0; i < coords.length; i++) {
    if (pointInHazard(coords[i], geom)) return true;
    if (i > 0 && segmentHits(coords[i - 1], coords[i], geom)) return true;
  }
  return false;
}

// Split a line into runs that stay clear of the hazard and runs that enter it.
export function splitByHazard(coords, geom) {
  const safe = [], blocked = [];
  let cur = null, curBlocked = null;
  for (let i = 1; i < coords.length; i++) {
    const a = coords[i - 1], b = coords[i];
    const bad = pointInHazard(a, geom) || pointInHazard(b, geom) || segmentHits(a, b, geom);
    if (cur && curBlocked === bad) cur.push(b);
    else { cur = [a, b]; curBlocked = bad; (bad ? blocked : safe).push(cur); }
  }
  return { safe, blocked };
}

// Approximate hazard area in km^2 (sum of rectangles, fine for growth comparisons).
export function hazardAreaKm2(geom) {
  let total = 0;
  for (const poly of toPolys(geom)) {
    const ring = poly[0];
    let a = 0;
    for (let i = 0; i < ring.length - 1; i++) a += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
    const latMid = ring.reduce((s, p) => s + p[1], 0) / ring.length;
    total += Math.abs(a) / 2 * 111.32 * 111.32 * Math.cos(rad(latMid));
  }
  return total;
}

// Nearest distance in metres from a point to the hazard (0 if inside). Uses rectangle bounds.
export function distanceToHazard(pt, geom) {
  if (pointInHazard(pt, geom)) return 0;
  const mx = 111320 * Math.cos(rad(pt[1])), my = 110540;
  let best = Infinity;
  for (const poly of toPolys(geom)) {
    const [minx, miny, maxx, maxy] = bbox(poly[0]);
    const dx = Math.max(minx - pt[0], 0, pt[0] - maxx) * mx;
    const dy = Math.max(miny - pt[1], 0, pt[1] - maxy) * my;
    const d = Math.hypot(dx, dy);
    if (d < best) best = d;
  }
  return best;
}

// Risk levels along a route for a colour gradient: 0 clear, 1 near the fire, 2 inside.
export function riskStops(coords, geom, nearMeters = 1200, samples = 24) {
  const total = lineLength(coords);
  if (!total) return [[0, 0], [1, 0]];
  const stops = [];
  for (let i = 0; i <= samples; i++) {
    const p = i / samples;
    const at = pointAlong(coords, total * p).point;
    const d = distanceToHazard(at, geom);
    stops.push([p, d === 0 ? 2 : d < nearMeters ? 1 : 0]);
  }
  return stops;
}

// ---- decisions ----

// Distance in metres from a point to a polyline (local flat approximation, fine at city scale).
export function distanceToLine(pt, coords) {
  const mx = 111320 * Math.cos(rad(pt[1])), my = 110540;
  let best = Infinity;
  for (let i = 1; i < coords.length; i++) {
    const ax = (coords[i - 1][0] - pt[0]) * mx, ay = (coords[i - 1][1] - pt[1]) * my;
    const bx = (coords[i][0] - pt[0]) * mx, by = (coords[i][1] - pt[1]) * my;
    const dx = bx - ax, dy = by - ay, len2 = dx * dx + dy * dy;
    const t = len2 ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / len2)) : 0;
    const d = Math.hypot(ax + t * dx, ay + t * dy);
    if (d < best) best = d;
  }
  return best;
}

// Share of the next route that runs along the previous one (within `tol` metres).
export function overlapRatio(nextCoords, prevCoords, tol = 60, samples = 20) {
  if (!nextCoords || nextCoords.length < 2 || !prevCoords || prevCoords.length < 2) return 0;
  const total = lineLength(nextCoords);
  let hit = 0;
  for (let i = 0; i < samples; i++) {
    const at = pointAlong(nextCoords, total * (i + 0.5) / samples).point;
    if (distanceToLine(at, prevCoords) <= tol) hit++;
  }
  return hit / samples;
}

// Compare the previous plan with the next one. Each plan: {route: GeoJSON Feature|null}, where the
// feature has geometry (LineString) and properties {distance_m, duration_s}.
export function routeDiff(prev, next) {
  const pr = prev && prev.route, nr = next && next.route;
  if (!nr) return { kind: pr ? 'withheld' : prev ? 'still-withheld' : 'withheld', dMin: 0, dKm: 0 };
  if (!pr) return { kind: prev ? 'resumed' : 'new', dMin: 0, dKm: 0 };
  const dMin = Math.round((nr.properties.duration_s - pr.properties.duration_s) / 60);
  const dKm = Math.round((nr.properties.distance_m - pr.properties.distance_m) / 100) / 10;
  const same = overlapRatio(nr.geometry.coordinates, pr.geometry.coordinates) >= 0.9; // a detour of even a fifth of the route counts
  return { kind: same ? 'unchanged' : 'rerouted', dMin, dKm };
}

// When to ask the router again. Keeps calls to the public OSRM server modest.
// route is the part of the current route still ahead (or null when withheld).
export function shouldReplan({ now, lastAt, minGapMs = 2500, retryGapMs = 7500, neverPlanned, route, hazard, area, lastArea, nearMeters = 1500 }) {
  if (neverPlanned) return 'first';
  if (now - lastAt < minGapMs) return null;
  if (!route) return area !== lastArea && now - lastAt >= retryGapMs ? 'retry' : null;   // withheld: ask rarely
  if (lineHitsHazard(route, hazard)) return 'blocked';
  if (area !== lastArea && riskStops(route, hazard, nearMeters, 8).some(([, level]) => level > 0)) return 'near';
  return null;
}

// A small triangle polygon at `point`, pointing along `bearing` (degrees), for the vehicle heading marker.
// lengthM is tip-to-tail; the triangle is about 60% as wide as it is long.
export function arrowPolygon(point, bearing, lengthM = 90) {
  const mx = 111320 * Math.cos(rad(point[1])), my = 110540;
  const b = rad(bearing);
  const fwd = [Math.sin(b), Math.cos(b)], side = [Math.cos(b), -Math.sin(b)];
  const at = (f, s) => [point[0] + (fwd[0] * f + side[0] * s) / mx, point[1] + (fwd[1] * f + side[1] * s) / my];
  const half = lengthM * 0.3;
  const ring = [at(lengthM * 0.6, 0), at(-lengthM * 0.4, half), at(-lengthM * 0.2, 0), at(-lengthM * 0.4, -half)];
  ring.push(ring[0]);
  return { type: 'Polygon', coordinates: [ring] };
}
