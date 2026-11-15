// Mock fire runs for the Live Explorer. FICTIONAL exercise scenarios, named only for the foothill
// geography they are set in. They are not forecasts and do not represent any real incident.
import { projectFire } from './firemodel.js';

export const STEP_MINUTES = 5;
export const RUN_STEPS = 24; // 2 simulated hours
export const LOOKAHEAD_STEPS = 3; // routes are planned against the fire as projected 15 minutes ahead

// Assembly points (mock destinations, approximate locations). OSRM snaps each to the nearest road.
export const ASSEMBLY_POINTS = [
  { name: 'Rose Bowl', lonlat: [-118.1676, 34.1613] },
  { name: 'Victory Park', lonlat: [-118.1120, 34.1668] },
  { name: 'Pasadena City College', lonlat: [-118.1445, 34.1451] },
  { name: 'Glendale College', lonlat: [-118.2297, 34.1566] },
  { name: 'Glendale Central Park', lonlat: [-118.2551, 34.1425] },
  { name: 'Santa Anita Park', lonlat: [-118.0447, 34.1397] },
  { name: 'Arcadia County Park', lonlat: [-118.0366, 34.1197] },
  { name: 'Monrovia Library Park', lonlat: [-117.9985, 34.1485] },
];

// primary is the assembly point the run starts out heading for; if the fire cuts that road the
// planner switches to the next-safest assembly point. ignition is authored just upwind of the
// primary route so the fire sweeps across the road partway through the trip.
// windFrom is the meteorological direction the wind blows FROM, in degrees. Santa Ana style
// winds come from the north-east, so the fire starts north-east of the district and runs at it.
export const FIRE_RUNS = [
  { id: 'verdugo', name: 'Verdugo Hills', geoid: '0630000', windFrom: 40, windKmh: 45, primary: 'Glendale College', ignition: [-118.2447, 34.1526], seed: 11,
    blurb: 'No safe exit: the fire cuts both roads out, so routes are withheld and the reason is shown.' },
  { id: 'arroyo', name: 'Arroyo Seco', geoid: '0656000', windFrom: 35, windKmh: 38, primary: 'Glendale College', ignition: [-118.1996, 34.134], seed: 23,
    blurb: 'A canyon fire runs along the arroyo toward Pasadena.' },
  { id: 'altadena', name: 'Altadena Ridge', geoid: '0601290', windFrom: 50, windKmh: 55, primary: 'Victory Park', ignition: [-118.1369, 34.1635], seed: 5,
    blurb: 'Strong wind carries embers from the ridge into Altadena.' },
  { id: 'madre', name: 'Sierra Madre Canyon', geoid: '0671806', windFrom: 60, windKmh: 42, primary: 'Santa Anita Park', ignition: [-118.057, 34.1304], seed: 37,
    blurb: 'A steep-canyon fire above Sierra Madre with limited exits.' },
  { id: 'flintridge', name: 'Flintridge Crest', geoid: '0639003', windFrom: 30, windKmh: 48, primary: 'Rose Bowl', ignition: [-118.1487, 34.1785], seed: 41,
    blurb: 'Crest fire spreading toward La Cañada Flintridge.' },
  { id: 'santaanita', name: 'Santa Anita Wash', geoid: '0602462', windFrom: 55, windKmh: 40, primary: 'Monrovia Library Park', ignition: [-118.0115, 34.1358], seed: 53,
    blurb: 'Wash-line fire moving south-west toward Arcadia.' },
  { id: 'monrovia', name: 'Monrovia Canyon', geoid: '0648648', windFrom: 45, windKmh: 36, primary: 'Arcadia County Park', ignition: [-118.0153, 34.1381], seed: 67,
    blurb: 'Canyon fire with moderate wind above Monrovia.' },
  { id: 'windshift', name: 'Wind-Shift Run', geoid: '0639045', windFrom: 45, windKmh: 50, primary: 'Glendale College', ignition: [-118.2051, 34.1885], seed: 71,
    shift: { atStep: 11, windFrom: 250, windKmh: 48 },
    blurb: 'The wind reverses at T+55 and the fire turns back on itself.' },
];

export function runById(id) {
  return FIRE_RUNS.find(r => r.id === id) || FIRE_RUNS[0];
}

export function windFor(run) {
  return step => (run.shift && step >= run.shift.atStep)
    ? { speed: run.shift.windKmh, dirFrom: run.shift.windFrom }
    : { speed: run.windKmh, dirFrom: run.windFrom };
}

// Start point. Authored runs carry an explicit ignition just upwind of the primary route; otherwise
// fall back to a point upwind of the district centroid.
export function ignitionFor(run, centroid) {
  if (run.ignition) return run.ignition;
  const offsetKm = run.offsetKm || 3.4;
  const to = (run.windFrom * Math.PI) / 180; // towards the wind source
  const dLat = (offsetKm * Math.cos(to)) / 110.54;
  const dLon = (offsetKm * Math.sin(to)) / (111.32 * Math.cos((centroid[1] * Math.PI) / 180));
  return [centroid[0] + dLon, centroid[1] + dLat];
}

const cache = new Map();

// Frames 0..RUN_STEPS (frame 0 is the ignition cell only). Cached per run.
export function buildRun(run, centroid) {
  const key = run.id + '|' + centroid.join(',');
  if (!cache.has(key)) {
    const ignition = ignitionFor(run, centroid);
    const result = projectFire(ignition, windFor(run), {
      steps: RUN_STEPS, grid: 61, spanDeg: 0.11, baseProb: 0.06, windStrength: 0.3, seed: run.seed, includeStart: true,
    });
    cache.set(key, { run, ignition, frames: result.frames });
  }
  return cache.get(key);
}
