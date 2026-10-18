import { useCallback, useMemo, useRef, useState } from "react";
import { fetchHeatmap, planTrip } from "./api";
import { CheckpointTable } from "./components/CheckpointTable";
import { MapView, type CheckpointRef } from "./components/MapView";
import { Recommendation, RouteCards } from "./components/RoutePanel";
import { TimeControls } from "./components/TimeControls";
import { TripForm } from "./components/TripForm";
import { localTimeZoneName } from "./lib/format";
import { HeatmapFrames } from "./lib/heatmapRaster";
import { truckAt } from "./lib/truck";
import type { HeatLayer, HeatmapResponse, PlanRequest, PlanResponse } from "./types";

type HeatState = { status: "idle" | "loading" } | { status: "ready"; data: HeatmapResponse } | { status: "error"; error: string };

const HOUR_MS = 3600_000;

export default function App() {
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [planning, setPlanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [heat, setHeat] = useState<HeatState>({ status: "idle" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [layer, setLayer] = useState<HeatLayer>("risk");
  const [hour, setHour] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [showHeat, setShowHeat] = useState(true);
  const [focus, setFocus] = useState<number | null>(null);
  const [pick, setPick] = useState<(CheckpointRef & { nonce: number }) | null>(null);
  const inflight = useRef<AbortController | null>(null);

  const submit = useCallback(async (req: PlanRequest) => {
    inflight.current?.abort();
    const ctrl = new AbortController();
    inflight.current = ctrl;
    setPlanning(true);
    setError(null);
    try {
      const result = await planTrip(req, ctrl.signal);
      setPlan(result);
      setSelectedId(result.recommendation.route_id);
      setHour(0);
      setPlaying(false);
      setFocus(null);
      setHeat({ status: "loading" });
      fetchHeatmap(result, ctrl.signal)
        .then((data) => !ctrl.signal.aborted && setHeat({ status: "ready", data }))
        .catch((e: Error) => !ctrl.signal.aborted && setHeat({ status: "error", error: e.message }));
    } catch (e) {
      if (!ctrl.signal.aborted) setError((e as Error).message);
    } finally {
      if (inflight.current === ctrl) setPlanning(false);
    }
  }, []);

  const frames = useMemo(() => (heat.status === "ready" ? new HeatmapFrames(heat.data) : null), [heat]);
  const selected = plan?.routes.find((r) => r.id === selectedId) ?? null;

  // The slider runs from departure to departure + 48 h.
  const startMs = plan ? Date.parse(plan.request.departure) : null;
  const timeMs = startMs === null ? null : startMs + hour * HOUR_MS;
  const truck = selected && timeMs !== null ? { ...truckAt(selected, timeMs), routeId: selected.id } : null;

  const onPick = useCallback(
    (index: number) => selectedId && setPick({ routeId: selectedId, index, nonce: Date.now() }),
    [selectedId],
  );

  return (
    <div className="app">
      <aside className="panel">
        <header className="brand">
          <div className="logo" aria-hidden>
            <svg viewBox="0 0 32 32" width="28" height="28">
              <rect width="32" height="32" rx="7" fill="#1d4ed8" />
              <path d="M5 20h13V10H5zM18 14h5l4 4v2h-9z" fill="#fff" />
              <circle cx="10" cy="22" r="2.6" fill="#fbbf24" />
              <circle cx="22" cy="22" r="2.6" fill="#fbbf24" />
            </svg>
          </div>
          <div>
            <h1>Weather-Aware Truck Routing</h1>
            <p className="muted">Forecast weather at the truck's arrival time, along three route options.</p>
          </div>
        </header>

        <TripForm busy={planning} onSubmit={submit} />

        {error && (
          <div className="error-box" role="alert">
            {error}
          </div>
        )}

        {plan && selected && (
          <div className={`results${planning ? " stale" : ""}`}>
            <Recommendation plan={plan} />
            <RouteCards plan={plan} selectedId={selected.id} onSelect={setSelectedId} />
            <CheckpointTable route={selected} focused={focus} onFocus={setFocus} onPick={onPick} />
            <p className="muted small">
              Times in {localTimeZoneName()}. Routing: {selected.provider.startsWith("valhalla") ? "Valhalla truck profile" : "OSRM"}.
            </p>
          </div>
        )}

        <footer className="credits muted small">
          Routing © <a href="https://valhalla.github.io/valhalla/">Valhalla</a> / OpenStreetMap contributors · Weather{" "}
          <a href="https://open-meteo.com/">Open-Meteo</a> · Geocoding <a href="https://photon.komoot.io/">Photon</a> · Map{" "}
          <a href="https://openfreemap.org/">OpenFreeMap</a>
        </footer>
      </aside>

      <main className="stage">
        <MapView
          plan={plan}
          frames={frames}
          selectedId={selectedId}
          onSelect={setSelectedId}
          heatLayer={layer}
          showHeat={showHeat}
          timeMs={timeMs}
          focus={focus !== null && selectedId ? { routeId: selectedId, index: focus } : null}
          pick={pick}
        />
        {plan && startMs !== null && (
          <TimeControls
            startMs={startMs}
            hour={hour}
            setHour={setHour}
            playing={playing}
            setPlaying={setPlaying}
            layer={layer}
            setLayer={setLayer}
            showHeat={showHeat}
            setShowHeat={setShowHeat}
            status={heat.status === "ready" ? "ready" : heat.status === "error" ? "error" : "loading"}
            errorText={heat.status === "error" ? heat.error : undefined}
            truck={truck}
          />
        )}
        {!plan && !planning && (
          <div className="map-hint">Enter a trip and press “Find safest route” to compare three routes.</div>
        )}
        {planning && (
          <div className="map-busy" role="status">
            <span className="spinner" aria-hidden /> Routing and checking the forecast at every checkpoint…
          </div>
        )}
      </main>
    </div>
  );
}
