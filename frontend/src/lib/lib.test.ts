import { describe, expect, it } from "vitest";
import type { HeatmapResponse, RouteOption } from "../types";
import { planRaster, rampColor, RAMPS, renderFrame } from "./heatmapRaster";
import { drivingSecondsAt, truckAt } from "./truck";

const HOUR = 3600;
const DEP = "2026-01-01T00:00:00Z";
const at = (s: number) => new Date(Date.parse(DEP) + s * 1000).toISOString();

function route(overrides: Partial<RouteOption> = {}): RouteOption {
  return {
    id: "A",
    provider: "test",
    roads: [],
    distance_mi: 100,
    drive_s: 20 * HOUR,
    travel_s: 31 * HOUR,
    departure: DEP,
    arrival: at(31 * HOUR),
    risk: {} as RouteOption["risk"],
    geometry: [
      [0, 0],
      [1, 0],
    ],
    drive_timeline: [0, 20 * HOUR],
    risk_segments: [],
    checkpoints: [],
    stops: [
      { kind: "break", lat: 0, lon: 0.4, drive_s: 8 * HOUR, start: at(8 * HOUR), end: at(8.5 * HOUR) },
      { kind: "rest", lat: 0, lon: 0.55, drive_s: 11 * HOUR, start: at(11.5 * HOUR), end: at(21.5 * HOUR) },
      { kind: "break", lat: 0, lon: 0.95, drive_s: 19 * HOUR, start: at(29.5 * HOUR), end: at(30 * HOUR) },
    ],
    corridor: [],
    ...overrides,
  };
}

describe("drivingSecondsAt", () => {
  it("subtracts completed stops and freezes during a stop", () => {
    const r = route();
    expect(drivingSecondsAt(r, -5)).toEqual({ drive: 0, status: "waiting" });
    expect(drivingSecondsAt(r, 4 * HOUR)).toEqual({ drive: 4 * HOUR, status: "driving" });
    expect(drivingSecondsAt(r, 8.25 * HOUR)).toEqual({ drive: 8 * HOUR, status: "break" });
    expect(drivingSecondsAt(r, 10 * HOUR)).toEqual({ drive: 9.5 * HOUR, status: "driving" });
    expect(drivingSecondsAt(r, 15 * HOUR)).toEqual({ drive: 11 * HOUR, status: "rest" });
    expect(drivingSecondsAt(r, 22.5 * HOUR)).toEqual({ drive: 12 * HOUR, status: "driving" });
    expect(drivingSecondsAt(r, 40 * HOUR)).toEqual({ drive: 20 * HOUR, status: "arrived" });
  });
});

describe("truckAt", () => {
  it("interpolates position along the geometry by driving time", () => {
    const r = route({ stops: [], travel_s: 20 * HOUR });
    const t = truckAt(r, Date.parse(DEP) + 5 * HOUR * 1000);
    expect(t.lon).toBeCloseTo(0.25);
    expect(t.mile).toBeCloseTo(25);
    expect(t.status).toBe("driving");
  });
});

describe("heatmap raster", () => {
  // 3x2 grid; the bottom-right cell has no data.
  const grid: HeatmapResponse = {
    bounds: { west: 0, east: 3, north: 2, south: 0 },
    nx: 3,
    ny: 2,
    cells: [0, 1, 2, 3, 4],
    times: [0],
    layers: { risk: [[0, 4, 4, 0, 4]], wind: [[]], gust: [[]], rain: [[]], snow: [[]] },
  };

  it("never lets weights from cells without data leak in", () => {
    const plan = planRaster(grid, 30);
    for (let p = 0; p < plan.width * plan.height; p++) {
      for (let j = 0; j < 4; j++) {
        if (plan.slots[p * 4 + j] < 0) expect(plan.weights[p * 4 + j]).toBe(0);
      }
    }
  });

  it("reproduces cell values at cell centres and fades out where there is no data", () => {
    const plan = planRaster(grid, 30);
    const out = new Uint8ClampedArray(plan.width * plan.height * 4);
    renderFrame(plan, grid.layers.risk[0], "risk", out);
    const scale = plan.width / grid.nx;
    const px = (cx: number, cy: number) => (Math.floor((cy + 0.5) * scale) * plan.width + Math.floor((cx + 0.5) * scale)) * 4;
    const noTravel = rampColor(RAMPS.risk, 4);
    const o = px(1, 0);
    expect(out[o]).toBeCloseTo(noTravel[0], -1);
    expect(out[o + 2]).toBeCloseTo(noTravel[2], -1);
    // Far corner of the empty cell: no data anywhere nearby -> transparent.
    expect(out[(plan.height * plan.width - 1) * 4 + 3]).toBe(0);
  });
});
