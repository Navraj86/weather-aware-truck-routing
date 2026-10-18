import { useState } from "react";
import { nextQuarterHour, toLocalInputValue } from "../lib/format";
import type { Place, PlanRequest } from "../types";
import { PlaceInput } from "./PlaceInput";

const SAMPLES: { name: string; origin: Place; destination: Place }[] = [
  {
    name: "Denver → Chicago",
    origin: { label: "Denver, Colorado, US", lat: 39.7392, lon: -104.9849 },
    destination: { label: "Chicago, Illinois, US", lat: 41.8756, lon: -87.6244 },
  },
  {
    name: "Seattle → Salt Lake City",
    origin: { label: "Seattle, Washington, US", lat: 47.6038, lon: -122.3301 },
    destination: { label: "Salt Lake City, Utah, US", lat: 40.7596, lon: -111.8868 },
  },
  {
    name: "Dallas → Atlanta",
    origin: { label: "Dallas, Texas, US", lat: 32.7763, lon: -96.7969 },
    destination: { label: "Atlanta, Georgia, US", lat: 33.749, lon: -84.3902 },
  },
];

const INTERVALS = [10, 25, 50] as const;

interface Props {
  busy: boolean;
  onSubmit: (req: PlanRequest) => void;
}

export function TripForm({ busy, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(SAMPLES[0].origin);
  const [destination, setDestination] = useState<Place | null>(SAMPLES[0].destination);
  const [departure, setDeparture] = useState(() => toLocalInputValue(nextQuarterHour()));
  const [load, setLoad] = useState("42000");
  const [sampleInterval, setSampleInterval] = useState<(typeof INTERVALS)[number]>(25);
  const [hos, setHos] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const now = new Date();
  const minDeparture = toLocalInputValue(new Date(now.getTime() - 30 * 60_000));
  const maxDeparture = toLocalInputValue(new Date(now.getTime() + 7 * 24 * 3600_000 - 60_000));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const loadLb = Number(load);
    const dep = new Date(departure);
    if (!origin || !destination) return setError("Pick an origin and a destination from the suggestions.");
    if (!Number.isFinite(loadLb) || loadLb < 0 || loadLb > 150_000) return setError("Load must be between 0 and 150,000 lb.");
    if (Number.isNaN(dep.getTime())) return setError("Enter a valid departure time.");
    setError(null);
    onSubmit({ origin, destination, departure: dep.toISOString(), load_lb: loadLb, interval_mi: sampleInterval, hos });
  };

  return (
    <form className="trip-form" onSubmit={submit} noValidate>
      <div className="places">
        <PlaceInput label="Origin" value={origin} onChange={setOrigin} placeholder="City, address or lat, lon" />
        <button
          type="button"
          className="swap"
          title="Swap origin and destination"
          aria-label="Swap origin and destination"
          onClick={() => {
            setOrigin(destination);
            setDestination(origin);
          }}
        >
          ⇅
        </button>
        <PlaceInput label="Destination" value={destination} onChange={setDestination} placeholder="City, address or lat, lon" />
      </div>

      <div className="samples" aria-label="Sample trips">
        {SAMPLES.map((s) => (
          <button
            key={s.name}
            type="button"
            className="chip"
            onClick={() => {
              setOrigin(s.origin);
              setDestination(s.destination);
            }}
          >
            {s.name}
          </button>
        ))}
      </div>

      <div className="row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input
            id="departure"
            type="datetime-local"
            value={departure}
            min={minDeparture}
            max={maxDeparture}
            onChange={(e) => setDeparture(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="load">Load weight (lb)</label>
          <input
            id="load"
            type="number"
            inputMode="numeric"
            min={0}
            max={150000}
            step={500}
            value={load}
            onChange={(e) => setLoad(e.target.value)}
            required
          />
        </div>
      </div>

      <div className="row row-center">
        <div className="field">
          <span className="label" id="interval-label">
            Weather sample every
          </span>
          <div className="segmented" role="radiogroup" aria-labelledby="interval-label">
            {INTERVALS.map((mi) => (
              <button
                key={mi}
                type="button"
                role="radio"
                aria-checked={sampleInterval === mi}
                className={sampleInterval === mi ? "on" : undefined}
                onClick={() => setSampleInterval(mi)}
              >
                {mi} mi
              </button>
            ))}
          </div>
        </div>
        <label className="check" title="Adds a 30-min break after 8 h and a 10-h rest after 11 h of driving">
          <input type="checkbox" checked={hos} onChange={(e) => setHos(e.target.checked)} />
          Hours-of-service stops
        </label>
      </div>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <button className="primary" type="submit" disabled={busy}>
        {busy ? "Planning routes…" : "Find safest route"}
      </button>
    </form>
  );
}
