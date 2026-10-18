import type { HeatmapResponse, Place, PlanRequest, PlanResponse } from "./types";

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("Network error: could not reach the server.");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(describeError(body) ?? `Request failed (HTTP ${res.status})`);
  return body as T;
}

/** Flatten DRF validation errors / upstream errors into one readable sentence. */
function describeError(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;
  if (typeof b.error === "string") return b.service ? `${capitalize(String(b.service))} service: ${b.error}` : b.error;
  if (typeof b.detail === "string") return b.detail;
  const parts: string[] = [];
  for (const [field, msgs] of Object.entries(b)) {
    const text = flatten(msgs).join(" ");
    parts.push(field === "non_field_errors" ? text : `${field.replace(/_/g, " ")}: ${text}`);
  }
  return parts.join(" ") || null;
}

function flatten(v: unknown): string[] {
  if (Array.isArray(v)) return v.flatMap(flatten);
  if (v && typeof v === "object") return Object.values(v).flatMap(flatten);
  return [String(v)];
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function geocode(q: string, signal?: AbortSignal): Promise<Place[]> {
  return request<{ results: Place[] }>(`/api/geocode?q=${encodeURIComponent(q)}`, { signal }).then((r) => r.results);
}

export function planTrip(body: PlanRequest, signal?: AbortSignal): Promise<PlanResponse> {
  return request<PlanResponse>("/api/plan", { method: "POST", body: JSON.stringify(body), signal });
}

export function fetchHeatmap(plan: PlanResponse, signal?: AbortSignal): Promise<HeatmapResponse> {
  return request<HeatmapResponse>("/api/heatmap", {
    method: "POST",
    body: JSON.stringify({
      corridors: plan.routes.map((r) => r.corridor),
      departure: plan.request.departure,
      load_lb: plan.request.load_lb,
    }),
    signal,
  });
}
