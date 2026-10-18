export type RiskKey = "low" | "moderate" | "high" | "severe" | "no_travel";

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface PlanRequest {
  origin: Place;
  destination: Place;
  departure: string; // ISO 8601 with offset
  load_lb: number;
  interval_mi: 10 | 25 | 50;
  hos: boolean;
}

export interface Weather {
  wind_mph: number;
  gust_mph: number;
  rain_in_hr: number;
  snow_in_hr: number;
  weather_code: number | null;
  description: string;
  missing: boolean;
}

export interface Risk {
  level: RiskKey;
  label: string;
  score: number;
  components: { wind: RiskKey; rain: RiskKey; snow: RiskKey; load: RiskKey };
  drivers: string[];
}

export interface Checkpoint {
  index: number;
  mile: number;
  lat: number;
  lon: number;
  eta: string;
  covers_mi: [number, number];
  weather: Weather;
  risk: Risk;
}

export interface RiskSegment {
  level: RiskKey;
  from_mi: number;
  to_mi: number;
  coords: [number, number][]; // [lon, lat]
}

export interface Stop {
  kind: "break" | "rest";
  lat: number;
  lon: number;
  drive_s: number;
  start: string;
  end: string;
}

export interface RouteRisk {
  miles_by_level: Record<RiskKey, number>;
  no_travel_mi: number;
  severe_mi: number;
  high_mi: number;
  avg_score: number;
  max_level: RiskKey;
}

export interface RouteOption {
  id: string;
  provider: string;
  roads: string[];
  distance_mi: number;
  drive_s: number;
  travel_s: number;
  departure: string;
  arrival: string;
  risk: RouteRisk;
  geometry: [number, number][]; // [lon, lat]
  drive_timeline: number[];
  risk_segments: RiskSegment[];
  checkpoints: Checkpoint[];
  stops: Stop[];
  corridor: [number, number][]; // [lat, lon]
}

export interface Recommendation {
  route_id: string;
  ranking: string[];
  versus: { route_id: string; reason: string }[];
  warnings: string[];
  criteria: string[];
}

export interface PlanResponse {
  request: Omit<PlanRequest, "origin" | "destination"> & {
    origin: { lat: number; lon: number };
    destination: { lat: number; lon: number };
  };
  routes: RouteOption[];
  recommendation: Recommendation;
  generated_at: string;
}

export type HeatLayer = "risk" | "wind" | "gust" | "rain" | "snow";

export interface HeatmapResponse {
  bounds: { west: number; east: number; north: number; south: number };
  nx: number;
  ny: number;
  cells: number[];
  times: number[]; // unix seconds
  layers: Record<HeatLayer, number[][]>; // [hour][cell]
}
