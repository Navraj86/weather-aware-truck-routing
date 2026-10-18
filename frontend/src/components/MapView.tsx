import maplibregl, { type GeoJSONSource, type ImageSource, type LngLatBoundsLike } from "maplibre-gl";
import type { FeatureCollection } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { formatDayTime } from "../lib/format";
import type { HeatmapFrames } from "../lib/heatmapRaster";
import { RISK_COLOR, RISK_LABEL } from "../lib/risk";
import { truckAt } from "../lib/truck";
import type { HeatLayer, PlanResponse, RiskKey, RouteOption } from "../types";

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

const riskColorExpr = [
  "match",
  ["get", "level"],
  ...Object.entries(RISK_COLOR).flat(),
  "#888",
] as unknown as maplibregl.ExpressionSpecification;

export interface CheckpointRef {
  routeId: string;
  index: number;
}

interface Props {
  plan: PlanResponse | null;
  frames: HeatmapFrames | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  heatLayer: HeatLayer;
  showHeat: boolean;
  timeMs: number | null;
  focus: CheckpointRef | null;
  pick: (CheckpointRef & { nonce: number }) | null;
}

export function MapView(props: Props) {
  const { plan, frames, selectedId, onSelect, heatLayer, showHeat, timeMs, focus, pick } = props;
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const markersRef = useRef<{ trucks: Map<string, maplibregl.Marker>; static: maplibregl.Marker[] }>({
    trucks: new Map(),
    static: [],
  });
  const planRef = useRef<PlanResponse | null>(null);
  const onSelectRef = useRef(onSelect);
  const [ready, setReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);

  planRef.current = plan;
  onSelectRef.current = onSelect;

  // ---------------------------------------------------------------- map setup
  useEffect(() => {
    const map = new maplibregl.Map({
      container: container.current!,
      style: STYLE_URL,
      center: [-96, 38.5],
      zoom: 3.6,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
    });
    mapRef.current = map;
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");
    map.on("error", (e) => {
      if (!map.isStyleLoaded() && e.error?.message) setMapError("Base map failed to load. Routes are still shown.");
    });

    map.on("load", () => {
      const beforeLabels = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
      map.addSource("routes", { type: "geojson", data: EMPTY });
      map.addSource("segments", { type: "geojson", data: EMPTY });
      map.addSource("checkpoints", { type: "geojson", data: EMPTY });
      map.addSource("stops", { type: "geojson", data: EMPTY });

      map.addLayer(
        {
          id: "route-casing",
          type: "line",
          source: "routes",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": ["case", ["get", "selected"], "#111827", "#ffffff"],
            "line-width": ["interpolate", ["linear"], ["zoom"], 4, ["case", ["get", "selected"], 7, 4.5], 10, ["case", ["get", "selected"], 12, 8]],
            "line-opacity": ["case", ["get", "selected"], 0.9, 0.8],
          },
        },
        beforeLabels,
      );
      map.addLayer(
        {
          id: "route-segments",
          type: "line",
          source: "segments",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: {
            "line-color": riskColorExpr,
            "line-width": ["interpolate", ["linear"], ["zoom"], 4, ["case", ["get", "selected"], 4.5, 2.5], 10, ["case", ["get", "selected"], 8, 5]],
            "line-opacity": ["case", ["get", "selected"], 1, 0.55],
          },
        },
        beforeLabels,
      );
      map.addLayer({
        id: "route-hit",
        type: "line",
        source: "routes",
        paint: { "line-color": "#000", "line-opacity": 0, "line-width": 18 },
      });
      map.addLayer({
        id: "checkpoint-circles",
        type: "circle",
        source: "checkpoints",
        paint: {
          "circle-color": riskColorExpr,
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, ["case", ["get", "selected"], 4, 2.5], 10, ["case", ["get", "selected"], 7, 4.5]],
          "circle-stroke-color": "#fff",
          "circle-stroke-width": ["case", ["get", "selected"], 1.5, 1],
          "circle-opacity": ["case", ["get", "selected"], 1, 0.7],
          "circle-stroke-opacity": ["case", ["get", "selected"], 1, 0.7],
        },
      });
      map.addLayer({
        id: "checkpoint-focus",
        type: "circle",
        source: "checkpoints",
        filter: ["==", ["get", "key"], ""],
        paint: {
          "circle-color": "rgba(0,0,0,0)",
          "circle-radius": 11,
          "circle-stroke-color": "#111827",
          "circle-stroke-width": 2.5,
        },
      });
      map.addLayer({
        id: "stop-circles",
        type: "circle",
        source: "stops",
        paint: {
          "circle-color": "#1f2937",
          "circle-radius": 6,
          "circle-stroke-color": "#fbbf24",
          "circle-stroke-width": 2,
        },
      });

      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10, maxWidth: "280px" });
      popupRef.current = popup;

      map.on("mousemove", "checkpoint-circles", (e) => {
        const f = e.features?.[0];
        const route = planRef.current?.routes.find((r) => r.id === f?.properties?.route);
        if (!f || !route) return;
        map.getCanvas().style.cursor = "pointer";
        const cp = route.checkpoints[f.properties!.index as number];
        popup.setLngLat([cp.lon, cp.lat]).setHTML(checkpointHtml(route, cp.index)).addTo(map);
      });
      map.on("mouseleave", "checkpoint-circles", () => {
        map.getCanvas().style.cursor = "";
        popup.remove();
      });
      map.on("mousemove", "stop-circles", (e) => {
        const p = e.features?.[0]?.properties;
        if (!p) return;
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<strong>${p.kind === "rest" ? "10-hour rest" : "30-minute break"}</strong> · Route ${esc(p.route)}<br>` +
              `${esc(formatDayTime(p.start))} – ${esc(formatDayTime(p.end))}`,
          )
          .addTo(map);
      });
      map.on("mouseleave", "stop-circles", () => popup.remove());
      map.on("mouseenter", "route-hit", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "route-hit", () => (map.getCanvas().style.cursor = ""));
      map.on("click", (e) => {
        const hit = map.queryRenderedFeatures(e.point, { layers: ["checkpoint-circles", "route-hit"] })[0];
        if (hit?.properties?.route) onSelectRef.current(hit.properties.route as string);
      });
      setReady(true);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // ---------------------------------------------------------------- routes & checkpoints
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const routes = plan?.routes ?? [];
    const sel = (id: string) => (id === selectedId ? 1 : 0);
    // Draw unselected routes first so the selected one sits on top.
    const ordered = [...routes].sort((a, b) => sel(a.id) - sel(b.id));

    (map.getSource("routes") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: ordered.map((r) => ({
        type: "Feature",
        properties: { route: r.id, selected: sel(r.id) === 1 },
        geometry: { type: "LineString", coordinates: r.geometry },
      })),
    });
    (map.getSource("segments") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: ordered.flatMap((r) =>
        r.risk_segments.map((s) => ({
          type: "Feature" as const,
          properties: { route: r.id, level: s.level, selected: sel(r.id) === 1 },
          geometry: { type: "LineString" as const, coordinates: s.coords },
        })),
      ),
    });
    (map.getSource("checkpoints") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: ordered.flatMap((r) =>
        r.checkpoints.map((c) => ({
          type: "Feature" as const,
          properties: { route: r.id, index: c.index, level: c.risk.level, selected: sel(r.id) === 1, key: `${r.id}:${c.index}` },
          geometry: { type: "Point" as const, coordinates: [c.lon, c.lat] },
        })),
      ),
    });
    (map.getSource("stops") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: routes
        .filter((r) => r.id === selectedId)
        .flatMap((r) =>
          r.stops.map((s) => ({
            type: "Feature" as const,
            properties: { route: r.id, kind: s.kind, start: s.start, end: s.end },
            geometry: { type: "Point" as const, coordinates: [s.lon, s.lat] },
          })),
        ),
    });
  }, [plan, selectedId, ready]);

  // Static markers (endpoints, route letters) and the camera, once per plan.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const store = markersRef.current;
    store.static.forEach((m) => m.remove());
    store.trucks.forEach((m) => m.remove());
    store.static = [];
    store.trucks.clear();
    if (!plan) return;

    const first = plan.routes[0].geometry;
    store.static.push(endpointMarker(first[0], "start", "Origin").addTo(map));
    store.static.push(endpointMarker(first[first.length - 1], "end", "Destination").addTo(map));
    for (const r of plan.routes) {
      const labelAt = r.geometry[Math.floor(r.geometry.length * labelFraction(r.id))];
      const el = document.createElement("button");
      el.className = `route-label route-${r.id}`;
      el.textContent = r.id;
      el.setAttribute("aria-label", `Select route ${r.id}`);
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        onSelectRef.current(r.id);
      });
      store.static.push(new maplibregl.Marker({ element: el }).setLngLat(labelAt).addTo(map));

      const truck = document.createElement("div");
      truck.className = `truck-marker route-${r.id}`;
      truck.innerHTML = `<span>${r.id}</span>`;
      store.trucks.set(r.id, new maplibregl.Marker({ element: truck }).setLngLat(r.geometry[0]));
    }

    const bounds = new maplibregl.LngLatBounds();
    plan.routes.forEach((r) => r.geometry.forEach((p) => bounds.extend(p)));
    const narrow = map.getContainer().clientWidth < 640;
    map.fitBounds(bounds as LngLatBoundsLike, {
      padding: narrow ? { top: 40, bottom: 150, left: 30, right: 30 } : { top: 60, bottom: 170, left: 60, right: 70 },
      duration: 900,
    });
  }, [plan, ready]);

  // ---------------------------------------------------------------- trucks at slider time
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !plan || timeMs === null) {
      markersRef.current.trucks.forEach((m) => m.remove());
      return;
    }
    for (const r of plan.routes) {
      const marker = markersRef.current.trucks.get(r.id);
      if (!marker) continue;
      const t = truckAt(r, timeMs);
      marker.setLngLat([t.lon, t.lat]);
      const el = marker.getElement();
      el.classList.toggle("selected", r.id === selectedId);
      el.classList.toggle("stopped", t.status !== "driving");
      el.title = `Route ${r.id}: ${statusText(t.status)} · mile ${Math.round(t.mile)}`;
      if (!el.isConnected) marker.addTo(map);
    }
  }, [plan, timeMs, selectedId, ready]);

  // ---------------------------------------------------------------- heatmap
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (!frames || timeMs === null) {
      if (map.getLayer("heat")) map.setLayoutProperty("heat", "visibility", "none");
      return;
    }
    const url = frames.url(heatLayer, frames.frameAt(timeMs));
    const src = map.getSource("heat") as ImageSource | undefined;
    if (src) {
      src.updateImage({ url, coordinates: frames.coordinates });
    } else {
      map.addSource("heat", { type: "image", url, coordinates: frames.coordinates });
      map.addLayer(
        {
          id: "heat",
          type: "raster",
          source: "heat",
          paint: { "raster-opacity": 0.9, "raster-fade-duration": 0, "raster-resampling": "linear" },
        },
        "route-casing",
      );
    }
    map.setLayoutProperty("heat", "visibility", showHeat ? "visible" : "none");
  }, [frames, heatLayer, timeMs, showHeat, ready]);

  useEffect(() => {
    if (!frames) return;
    let cancelled = false;
    frames.warm(heatLayer, () => cancelled);
    return () => {
      cancelled = true;
    };
  }, [frames, heatLayer]);

  // ---------------------------------------------------------------- checkpoint focus / pick from the table
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.setFilter("checkpoint-focus", ["==", ["get", "key"], focus ? `${focus.routeId}:${focus.index}` : ""]);
  }, [focus, ready]);

  useEffect(() => {
    const map = mapRef.current;
    const route = plan?.routes.find((r) => r.id === pick?.routeId);
    if (!map || !ready || !pick || !route) return;
    const cp = route.checkpoints[pick.index];
    map.easeTo({ center: [cp.lon, cp.lat], zoom: Math.max(map.getZoom(), 8), duration: 700 });
    popupRef.current?.setLngLat([cp.lon, cp.lat]).setHTML(checkpointHtml(route, cp.index)).addTo(map);
    // Only re-run when a new pick is made, not when the plan or selection changes.
  }, [pick?.nonce, ready]);

  return (
    <div className="map-wrap">
      <div ref={container} className="map" aria-label="Route map" />
      {mapError && <div className="map-error">{mapError}</div>}
    </div>
  );
}

// ------------------------------------------------------------------ helpers

function labelFraction(id: string): number {
  // Stagger route letters so they don't stack where routes overlap.
  return { A: 0.42, B: 0.55, C: 0.68 }[id] ?? 0.5;
}

function endpointMarker(lngLat: [number, number], kind: "start" | "end", title: string) {
  const el = document.createElement("div");
  el.className = `endpoint endpoint-${kind}`;
  el.title = title;
  return new maplibregl.Marker({ element: el }).setLngLat(lngLat);
}

function statusText(s: string): string {
  return { waiting: "not departed", driving: "driving", break: "on 30-min break", rest: "on 10-h rest", arrived: "arrived" }[s] ?? s;
}

function esc(s: unknown): string {
  return String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function checkpointHtml(route: RouteOption, index: number): string {
  const cp = route.checkpoints[index];
  const w = cp.weather;
  const level = cp.risk.level as RiskKey;
  const drivers = cp.risk.drivers.length ? `<div class="pp-drivers">${cp.risk.drivers.map(esc).join("<br>")}</div>` : "";
  return `
    <div class="pp">
      <div class="pp-head">
        <strong>Route ${esc(route.id)} · mile ${Math.round(cp.mile)}</strong>
        <span class="badge compact" style="background:${RISK_COLOR[level]};color:${level === "moderate" ? "#2b2100" : "#fff"}">${RISK_LABEL[level]}</span>
      </div>
      <div class="pp-eta">ETA ${esc(formatDayTime(cp.eta))} · ${esc(w.description)}</div>
      <table class="pp-table">
        <tr><td>Wind</td><td>${w.wind_mph.toFixed(0)} mph <span class="muted">(gusts ${w.gust_mph.toFixed(0)})</span></td></tr>
        <tr><td>Rain</td><td>${w.rain_in_hr.toFixed(2)} in/hr</td></tr>
        <tr><td>Snow</td><td>${w.snow_in_hr.toFixed(2)} in/hr</td></tr>
      </table>
      ${drivers}
      ${w.missing ? '<div class="pp-missing">Forecast incomplete at this time</div>' : ""}
    </div>`;
}
