// Pure planning decisions for the Live Explorer, kept free of the DOM and the map so they can be
// unit-tested and run headlessly against live OSRM (see scripts/simulate_runs.mjs).
import { pointInHazard, lineHitsHazard, sliceFrom, haversine, lineLength, routeDiff } from './routeanim.js';

// Up to `limit` assembly points to try, primary first, then the nearest ones the fire has not taken.
export function destinationOrder({ origin, hazard, primary, points, limit = 3 }) {
  const open = points.filter(a => !pointInHazard(a.lonlat, hazard));
  const first = open.find(a => a.name === primary);
  const rest = open.filter(a => a !== first).sort((a, b) => haversine(a.lonlat, origin) - haversine(b.lonlat, origin));
  return [first, ...rest].filter(Boolean).slice(0, limit);
}

// Ask the router for each destination in turn until one gives a safe route.
// fetchRoute(origin, destLonLat, hazard) resolves to {route, candidate_routes, chosen_id, ...} where route is null when withheld.
export async function chooseRoute({ origin, hazard, primary, points, fetchRoute, isStale = () => false }) {
  let lastTry = null;
  for (const dest of destinationOrder({ origin, hazard, primary, points })) {
    const res = await fetchRoute(origin, dest.lonlat, hazard);
    if (isStale()) return { stale: true, found: null, lastTry: null };
    lastTry = { res, dest };
    if (res.route) return { found: { res, dest }, lastTry };
  }
  return { found: null, lastTry };
}

// A "fire nearby" check must not swap a route that is still safe. Only a blocked route is replaced.
export function keepCurrentRoute({ reason, routeCoords, vehicleM, hazard }) {
  if (reason !== 'near' || !routeCoords) return false;
  return !lineHitsHazard(sliceFrom(routeCoords, vehicleM), hazard);
}

// Classify a freshly computed plan against the one in force. The old route is compared from where the
// vehicle is now, so "same road, new request" is not reported as a reroute.
export function describePlan({ plan, route, routeCoords, vehicleM, destName, found }) {
  const next = found ? { route: found.res.route, dest: found.dest } : { route: null, dest: null };
  let prevForDiff = plan ? { route: null } : null;
  if (plan && route && routeCoords) {
    const ahead = sliceFrom(routeCoords, vehicleM);
    const frac = lineLength(ahead) / Math.max(1, lineLength(routeCoords));
    prevForDiff = { route: { geometry: { coordinates: ahead },
      properties: { distance_m: route.properties.distance_m * frac, duration_s: route.properties.duration_s * frac } } };
  }
  const diff = routeDiff(prevForDiff, next);
  const switched = !!(found && destName && found.dest.name !== destName);
  return { next, diff, switched };
}
