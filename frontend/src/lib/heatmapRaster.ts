/**
 * Turns the coarse forecast grid into smooth heatmap images.
 *
 * The grid is regular in Web Mercator, so one image stretched over its bounds
 * lines up with the map. Each output pixel is a bilinear blend of the four
 * surrounding cell centres; cells without data get zero weight, which both
 * keeps edge values honest and fades the heatmap out at the corridor edge.
 * Pixel->cell weights are computed once per grid and reused for every frame,
 * and encoded frames are cached, so scrubbing the slider is cheap.
 */
import type { HeatLayer, HeatmapResponse } from "../types";

type Stop = [value: number, r: number, g: number, b: number, a: number];

interface Ramp {
  stops: Stop[];
  max: number;
  unit: string;
  label: string;
  ticks: number[];
}

// Colour stops sit on the risk thresholds, so the heatmap and the risk legend agree.
export const RAMPS: Record<HeatLayer, Ramp> = {
  risk: {
    label: "Weather risk (with load rules)",
    unit: "",
    max: 4,
    ticks: [0, 1, 2, 3, 4],
    stops: [
      [0, 34, 160, 107, 0.1],
      [1, 230, 180, 0, 0.5],
      [2, 242, 120, 12, 0.6],
      [3, 217, 45, 32, 0.68],
      [4, 107, 33, 168, 0.75],
    ],
  },
  wind: {
    label: "Wind speed",
    unit: "mph",
    max: 60,
    ticks: [0, 25, 35, 45, 55],
    stops: [
      [0, 90, 160, 220, 0],
      [10, 90, 160, 220, 0.12],
      [24.9, 120, 180, 230, 0.35],
      [25, 230, 180, 0, 0.5],
      [35, 242, 120, 12, 0.6],
      [45, 217, 45, 32, 0.68],
      [55, 107, 33, 168, 0.75],
    ],
  },
  gust: {
    label: "Wind gusts (info only)",
    unit: "mph",
    max: 70,
    ticks: [0, 25, 35, 45, 55],
    stops: [
      [0, 90, 160, 220, 0],
      [15, 90, 160, 220, 0.12],
      [24.9, 120, 180, 230, 0.35],
      [25, 230, 180, 0, 0.5],
      [35, 242, 120, 12, 0.6],
      [45, 217, 45, 32, 0.68],
      [55, 107, 33, 168, 0.75],
    ],
  },
  rain: {
    label: "Rain",
    unit: "in/hr",
    max: 1.2,
    ticks: [0, 0.1, 0.25, 0.5, 1.0],
    stops: [
      [0, 70, 140, 230, 0],
      [0.005, 70, 140, 230, 0.2],
      [0.099, 40, 100, 210, 0.45],
      [0.1, 230, 180, 0, 0.5],
      [0.25, 242, 120, 12, 0.6],
      [0.5, 217, 45, 32, 0.68],
      [1.0, 107, 33, 168, 0.75],
    ],
  },
  snow: {
    label: "Snowfall",
    unit: "in/hr",
    max: 3.5,
    ticks: [0, 0.5, 1, 2, 3],
    stops: [
      [0, 120, 200, 240, 0],
      [0.02, 120, 200, 240, 0.25],
      [0.49, 80, 150, 235, 0.5],
      [0.5, 230, 180, 0, 0.5],
      [1.0, 242, 120, 12, 0.6],
      [2.0, 217, 45, 32, 0.68],
      [3.0, 107, 33, 168, 0.75],
    ],
  },
};

const LUT_SIZE = 512;
const lutCache = new Map<HeatLayer, Uint8ClampedArray>();

export function rampColor(ramp: Ramp, v: number): [number, number, number, number] {
  const s = ramp.stops;
  if (v <= s[0][0]) return [s[0][1], s[0][2], s[0][3], s[0][4]];
  for (let i = 1; i < s.length; i++) {
    if (v <= s[i][0]) {
      const [v0, r0, g0, b0, a0] = s[i - 1];
      const [v1, r1, g1, b1, a1] = s[i];
      const t = (v - v0) / (v1 - v0);
      return [r0 + (r1 - r0) * t, g0 + (g1 - g0) * t, b0 + (b1 - b0) * t, a0 + (a1 - a0) * t];
    }
  }
  const last = s[s.length - 1];
  return [last[1], last[2], last[3], last[4]];
}

function lut(layer: HeatLayer): Uint8ClampedArray {
  let table = lutCache.get(layer);
  if (!table) {
    const ramp = RAMPS[layer];
    table = new Uint8ClampedArray(LUT_SIZE * 4);
    for (let i = 0; i < LUT_SIZE; i++) {
      const [r, g, b, a] = rampColor(ramp, (i / (LUT_SIZE - 1)) * ramp.max);
      table.set([r, g, b, a * 255], i * 4);
    }
    lutCache.set(layer, table);
  }
  return table;
}

export interface RasterPlan {
  width: number;
  height: number;
  /** For each pixel: 4 data-cell slots (k index into the cell arrays, or -1) and their weights. */
  slots: Int32Array;
  weights: Float32Array;
}

export function planRaster(h: HeatmapResponse, targetPx = 320): RasterPlan {
  const scale = Math.max(4, Math.round(targetPx / Math.max(h.nx, h.ny)));
  const width = h.nx * scale;
  const height = h.ny * scale;
  const cellToK = new Int32Array(h.nx * h.ny).fill(-1);
  h.cells.forEach((cell, k) => (cellToK[cell] = k));

  const slots = new Int32Array(width * height * 4);
  const weights = new Float32Array(width * height * 4);
  const clampX = (x: number) => Math.min(h.nx - 1, Math.max(0, x));
  const clampY = (y: number) => Math.min(h.ny - 1, Math.max(0, y));
  for (let py = 0; py < height; py++) {
    const gy = (py + 0.5) / scale - 0.5;
    const y0 = Math.floor(gy);
    const fy = gy - y0;
    for (let px = 0; px < width; px++) {
      const gx = (px + 0.5) / scale - 0.5;
      const x0 = Math.floor(gx);
      const fx = gx - x0;
      const o = (py * width + px) * 4;
      const corners: [number, number, number][] = [
        [x0, y0, (1 - fx) * (1 - fy)],
        [x0 + 1, y0, fx * (1 - fy)],
        [x0, y0 + 1, (1 - fx) * fy],
        [x0 + 1, y0 + 1, fx * fy],
      ];
      corners.forEach(([cx, cy, w], j) => {
        const inside = cx === clampX(cx) && cy === clampY(cy);
        const k = inside ? cellToK[cy * h.nx + cx] : -1;
        slots[o + j] = k;
        weights[o + j] = k >= 0 ? w : 0;
      });
    }
  }
  return { width, height, slots, weights };
}

/** Fill `out` (RGBA, width*height*4) with one heatmap frame. */
export function renderFrame(plan: RasterPlan, values: number[], layer: HeatLayer, out: Uint8ClampedArray): void {
  const table = lut(layer);
  const max = RAMPS[layer].max;
  const { slots, weights } = plan;
  const n = plan.width * plan.height;
  for (let p = 0; p < n; p++) {
    const o = p * 4;
    let wsum = 0;
    let vsum = 0;
    for (let j = 0; j < 4; j++) {
      const w = weights[o + j];
      if (w > 0) {
        wsum += w;
        vsum += w * values[slots[o + j]];
      }
    }
    if (wsum <= 0.001) {
      out[o + 3] = 0;
      continue;
    }
    const v = vsum / wsum;
    const li = Math.min(LUT_SIZE - 1, Math.max(0, Math.round((v / max) * (LUT_SIZE - 1)))) * 4;
    // Fade out towards the edge of the corridor (where neighbouring cells have no data).
    const edge = Math.min(1, wsum * 1.6);
    out[o] = table[li];
    out[o + 1] = table[li + 1];
    out[o + 2] = table[li + 2];
    out[o + 3] = table[li + 3] * edge;
  }
}

/** Renders frames to PNG data URLs on demand and caches them. */
export class HeatmapFrames {
  private plan: RasterPlan;
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private image: ImageData;
  private cache = new Map<string, string>();

  constructor(private data: HeatmapResponse) {
    this.plan = planRaster(data);
    this.canvas = document.createElement("canvas");
    this.canvas.width = this.plan.width;
    this.canvas.height = this.plan.height;
    this.ctx = this.canvas.getContext("2d")!;
    this.image = this.ctx.createImageData(this.plan.width, this.plan.height);
  }

  get coordinates(): [[number, number], [number, number], [number, number], [number, number]] {
    const { west, east, north, south } = this.data.bounds;
    return [
      [west, north],
      [east, north],
      [east, south],
      [west, south],
    ];
  }

  /**
   * Frame for a moment in time. Precipitation at timestamp T is the total for
   * the hour ending at T, so a moment uses the first frame at or after it
   * (the same rule the backend uses for checkpoints).
   */
  frameAt(timeMs: number): number {
    const t = timeMs / 1000 - this.data.times[0];
    return Math.min(this.data.times.length - 1, Math.max(0, Math.ceil(t / 3600 - 1e-9)));
  }

  url(layer: HeatLayer, hour: number): string {
    const key = `${layer}:${hour}`;
    let url = this.cache.get(key);
    if (!url) {
      renderFrame(this.plan, this.data.layers[layer][hour], layer, this.image.data);
      this.ctx.putImageData(this.image, 0, 0);
      url = this.canvas.toDataURL("image/png");
      this.cache.set(key, url);
    }
    return url;
  }

  /** Pre-render a layer's frames during idle time so playback never stalls. */
  warm(layer: HeatLayer, isCancelled: () => boolean): void {
    let hour = 0;
    const total = this.data.times.length;
    const idle: (cb: () => void) => void =
      "requestIdleCallback" in window ? (cb) => window.requestIdleCallback(cb) : (cb) => setTimeout(cb, 16);
    const step = () => {
      if (isCancelled() || hour >= total) return;
      this.url(layer, hour++);
      idle(step);
    };
    idle(step);
  }
}
