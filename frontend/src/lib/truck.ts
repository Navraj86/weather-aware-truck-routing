import type { Checkpoint, RouteOption } from "../types";

export type TruckStatus = "waiting" | "driving" | "break" | "rest" | "arrived";

export interface TruckState {
  lon: number;
  lat: number;
  mile: number;
  status: TruckStatus;
  checkpoint: Checkpoint | null; // checkpoint whose stretch of road the truck is on
}

const EARTH_RADIUS_MI = 3958.7613;
const cumulativeMiles = new WeakMap<RouteOption, Float64Array>();

function haversineMi([lon1, lat1]: [number, number], [lon2, lat2]: [number, number]): number {
  const toRad = Math.PI / 180;
  const dLat = (lat2 - lat1) * toRad;
  const dLon = (lon2 - lon1) * toRad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_MI * Math.asin(Math.min(1, Math.sqrt(h)));
}

function milesAlong(route: RouteOption): Float64Array {
  let cum = cumulativeMiles.get(route);
  if (!cum) {
    cum = new Float64Array(route.geometry.length);
    for (let i = 1; i < route.geometry.length; i++) {
      cum[i] = cum[i - 1] + haversineMi(route.geometry[i - 1], route.geometry[i]);
    }
    // Rescale so the end matches the router's reported distance.
    const scale = cum[cum.length - 1] > 0 ? route.distance_mi / cum[cum.length - 1] : 1;
    for (let i = 0; i < cum.length; i++) cum[i] *= scale;
    cumulativeMiles.set(route, cum);
  }
  return cum;
}

/** Driving seconds completed after `elapsed` wall-clock seconds, honouring HOS stops. */
export function drivingSecondsAt(route: RouteOption, elapsed: number): { drive: number; status: TruckStatus } {
  if (elapsed < 0) return { drive: 0, status: "waiting" };
  if (elapsed >= route.travel_s) return { drive: route.drive_s, status: "arrived" };
  const dep = Date.parse(route.departure);
  let drive = elapsed;
  for (const stop of route.stops) {
    const start = (Date.parse(stop.start) - dep) / 1000;
    const end = (Date.parse(stop.end) - dep) / 1000;
    if (elapsed >= end) drive -= end - start;
    else if (elapsed >= start) return { drive: stop.drive_s, status: stop.kind };
    else break;
  }
  return { drive: Math.min(drive, route.drive_s), status: "driving" };
}

export function truckAt(route: RouteOption, timeMs: number): TruckState {
  const elapsed = (timeMs - Date.parse(route.departure)) / 1000;
  const { drive, status } = drivingSecondsAt(route, elapsed);
  const tl = route.drive_timeline;
  const geom = route.geometry;
  const cum = milesAlong(route);

  // Last vertex whose timeline value is <= drive.
  let lo = 0;
  let hi = tl.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (tl[mid] <= drive) lo = mid;
    else hi = mid - 1;
  }
  const i = Math.min(lo, geom.length - 2);
  const span = tl[i + 1] - tl[i];
  const f = span > 0 ? Math.min(1, Math.max(0, (drive - tl[i]) / span)) : 0;
  const lon = geom[i][0] + (geom[i + 1][0] - geom[i][0]) * f;
  const lat = geom[i][1] + (geom[i + 1][1] - geom[i][1]) * f;
  const mile = cum[i] + (cum[i + 1] - cum[i]) * f;
  const checkpoint = route.checkpoints.find((c) => mile >= c.covers_mi[0] && mile <= c.covers_mi[1]) ?? null;
  return { lon, lat, mile, status, checkpoint };
}
