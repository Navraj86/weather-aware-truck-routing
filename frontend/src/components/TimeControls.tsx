import { useEffect } from "react";
import { formatDayTime } from "../lib/format";
import { RAMPS, rampColor } from "../lib/heatmapRaster";
import { RISK_COLOR, RISK_LABEL, RISK_LEVELS } from "../lib/risk";
import type { TruckState } from "../lib/truck";
import type { HeatLayer } from "../types";

const LAYERS: { id: HeatLayer; label: string }[] = [
  { id: "risk", label: "Risk" },
  { id: "wind", label: "Wind" },
  { id: "gust", label: "Gusts" },
  { id: "rain", label: "Rain" },
  { id: "snow", label: "Snow" },
];

const HOURS = 48;
const PLAY_MS_PER_HOUR = 450;

interface Props {
  startMs: number;
  hour: number;
  setHour: (h: number | ((h: number) => number)) => void;
  playing: boolean;
  setPlaying: (p: boolean) => void;
  layer: HeatLayer;
  setLayer: (l: HeatLayer) => void;
  showHeat: boolean;
  setShowHeat: (v: boolean) => void;
  status: "loading" | "ready" | "error";
  errorText?: string;
  truck: (TruckState & { routeId: string }) | null;
}

export function TimeControls(p: Props) {
  const { hour, setHour, playing, setPlaying } = p;

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => setHour((h) => (h >= HOURS ? 0 : h + 1)), PLAY_MS_PER_HOUR);
    return () => window.clearInterval(id);
  }, [playing, setHour]);

  const t = p.startMs + hour * 3600_000;
  return (
    <div className="time-controls">
      <div className="tc-top">
        <div className="layer-tabs" role="radiogroup" aria-label="Heatmap layer">
          {LAYERS.map((l) => (
            <button
              key={l.id}
              type="button"
              role="radio"
              aria-checked={p.layer === l.id}
              className={p.layer === l.id ? "on" : undefined}
              onClick={() => p.setLayer(l.id)}
            >
              {l.label}
            </button>
          ))}
        </div>
        <label className="check small">
          <input type="checkbox" checked={p.showHeat} onChange={(e) => p.setShowHeat(e.target.checked)} />
          Heatmap
        </label>
      </div>

      <div className="tc-slider">
        <button
          type="button"
          className="play"
          onClick={() => setPlaying(!playing)}
          disabled={p.status !== "ready"}
          aria-label={playing ? "Pause forecast animation" : "Play forecast animation"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="slider-col">
          <input
            type="range"
            min={0}
            max={HOURS}
            step={1}
            value={hour}
            onChange={(e) => {
              setPlaying(false);
              setHour(Number(e.target.value));
            }}
            aria-label="Forecast hour after departure"
            aria-valuetext={`+${hour} hours, ${formatDayTime(t)}`}
          />
          <div className="slider-ticks" aria-hidden>
            {[0, 12, 24, 36, 48].map((h) => (
              <span key={h}>+{h}h</span>
            ))}
          </div>
        </div>
        <div className="tc-time">
          <strong>+{hour} h</strong>
          <span>{formatDayTime(t)}</span>
        </div>
      </div>

      <div className="tc-bottom">
        <Legend layer={p.layer} />
        <div className="tc-status">
          {p.status === "loading" && <span className="muted">Loading corridor forecast…</span>}
          {p.status === "error" && <span className="error-text">Heatmap unavailable: {p.errorText}</span>}
          {p.status === "ready" && p.truck && <TruckReadout truck={p.truck} />}
        </div>
      </div>
    </div>
  );
}

function TruckReadout({ truck }: { truck: TruckState & { routeId: string } }) {
  const status = {
    waiting: "not yet departed",
    driving: `at mile ${Math.round(truck.mile)}`,
    break: `on break, mile ${Math.round(truck.mile)}`,
    rest: `resting, mile ${Math.round(truck.mile)}`,
    arrived: "arrived",
  }[truck.status];
  const level = truck.checkpoint?.risk.level;
  return (
    <span className="truck-readout">
      Truck {truck.routeId}: {status}
      {level && truck.status !== "waiting" && truck.status !== "arrived" && (
        <>
          {" · "}
          <span className="dot" style={{ background: RISK_COLOR[level] }} /> {RISK_LABEL[level]} at ETA
        </>
      )}
    </span>
  );
}

function Legend({ layer }: { layer: HeatLayer }) {
  const ramp = RAMPS[layer];
  if (layer === "risk") {
    return (
      <div className="legend" aria-label="Risk legend">
        {RISK_LEVELS.map((l) => (
          <span key={l} className="legend-item">
            <span className="dot" style={{ background: RISK_COLOR[l] }} />
            {RISK_LABEL[l]}
          </span>
        ))}
      </div>
    );
  }
  const steps = 24;
  const gradient = Array.from({ length: steps + 1 }, (_, i) => {
    const [r, g, b, a] = rampColor(ramp, (i / steps) * ramp.max);
    return `rgba(${r | 0},${g | 0},${b | 0},${Math.max(a, 0.08).toFixed(2)}) ${((i / steps) * 100).toFixed(1)}%`;
  }).join(",");
  return (
    <div className="legend gradient-legend" aria-label={`${ramp.label} legend`}>
      <span className="legend-title">
        {ramp.label} ({ramp.unit})
      </span>
      <div className="gradient-bar" style={{ background: `linear-gradient(90deg, ${gradient})` }} />
      <div className="gradient-ticks">
        {ramp.ticks.map((v) => (
          <span key={v} style={{ left: `${(v / ramp.max) * 100}%` }}>
            {v}
          </span>
        ))}
      </div>
    </div>
  );
}
