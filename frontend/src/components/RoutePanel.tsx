import { formatDayTime, formatDuration, formatMiles } from "../lib/format";
import { RISK_COLOR, RISK_INK, RISK_LABEL, RISK_LEVELS } from "../lib/risk";
import type { PlanResponse, RiskKey, RouteOption } from "../types";

export function RiskBadge({ level, compact = false }: { level: RiskKey; compact?: boolean }) {
  return (
    <span className={`badge${compact ? " compact" : ""}`} style={{ background: RISK_COLOR[level], color: RISK_INK[level] }}>
      {RISK_LABEL[level]}
    </span>
  );
}

/** Horizontal bar showing which stretches of the route carry which risk level. */
export function RiskStrip({ route }: { route: RouteOption }) {
  const total = route.distance_mi || 1;
  return (
    <div className="risk-strip" role="img" aria-label={stripLabel(route)}>
      {route.risk_segments.map((s, i) => (
        <span
          key={i}
          style={{ width: `${((s.to_mi - s.from_mi) / total) * 100}%`, background: RISK_COLOR[s.level] }}
          title={`Mile ${Math.round(s.from_mi)}–${Math.round(s.to_mi)}: ${RISK_LABEL[s.level]}`}
        />
      ))}
    </div>
  );
}

function stripLabel(route: RouteOption): string {
  return RISK_LEVELS.filter((l) => route.risk.miles_by_level[l] > 0)
    .map((l) => `${RISK_LABEL[l]} ${Math.round(route.risk.miles_by_level[l])} mi`)
    .join(", ");
}

export function Recommendation({ plan }: { plan: PlanResponse }) {
  const rec = plan.recommendation;
  const best = plan.routes.find((r) => r.id === rec.route_id)!;
  return (
    <section className="recommendation" aria-live="polite">
      <div className="rec-head">
        <span className={`route-letter route-${best.id}`}>{best.id}</span>
        <div>
          <h2>Route {best.id} is recommended</h2>
          <p className="muted">
            {best.roads.length ? `via ${best.roads.join(", ")} · ` : ""}
            {formatMiles(best.distance_mi)} · {formatDuration(best.travel_s)}
          </p>
        </div>
      </div>
      {rec.versus.length > 0 && (
        <ul className="rec-reasons">
          {rec.versus.map((v) => (
            <li key={v.route_id}>
              vs Route {v.route_id}: {v.reason}
            </li>
          ))}
        </ul>
      )}
      {rec.warnings.map((w) => (
        <p key={w} className="warning" role="alert">
          {w}
        </p>
      ))}
      <details className="criteria">
        <summary>How routes are ranked</summary>
        <ol>
          {rec.criteria.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ol>
        <p className="muted">
          Each checkpoint's risk applies to the road halfway to its neighbouring checkpoints, so risk miles add up to the
          route length.
        </p>
      </details>
    </section>
  );
}

interface CardsProps {
  plan: PlanResponse;
  selectedId: string;
  onSelect: (id: string) => void;
}

export function RouteCards({ plan, selectedId, onSelect }: CardsProps) {
  return (
    <div className="route-cards" role="radiogroup" aria-label="Route options">
      {plan.routes.map((r) => {
        const recommended = r.id === plan.recommendation.route_id;
        const selected = r.id === selectedId;
        return (
          <button
            key={r.id}
            type="button"
            role="radio"
            aria-checked={selected}
            className={`route-card${selected ? " selected" : ""}`}
            onClick={() => onSelect(r.id)}
          >
            <div className="card-head">
              <span className={`route-letter route-${r.id}`}>{r.id}</span>
              <div className="card-title">
                <strong>{r.roads.length ? `via ${r.roads.slice(0, 2).join(", ")}` : `Route ${r.id}`}</strong>
                <span className="muted">
                  {formatMiles(r.distance_mi)} · {formatDuration(r.travel_s)}
                </span>
              </div>
              {recommended && <span className="tag">Recommended</span>}
            </div>
            <RiskStrip route={r} />
            <dl className="metrics">
              <div>
                <dt>Severe+</dt>
                <dd className={r.risk.severe_mi > 0 ? "bad" : undefined}>{Math.round(r.risk.severe_mi)} mi</dd>
              </div>
              <div>
                <dt>High</dt>
                <dd className={r.risk.high_mi > 0 ? "warn" : undefined}>{Math.round(r.risk.high_mi)} mi</dd>
              </div>
              <div>
                <dt>Avg risk</dt>
                <dd>{r.risk.avg_score.toFixed(2)}</dd>
              </div>
              <div>
                <dt>Worst</dt>
                <dd>
                  <RiskBadge level={r.risk.max_level} compact />
                </dd>
              </div>
            </dl>
            <p className="eta muted">
              Arrive {formatDayTime(r.arrival)}
              {r.stops.length > 0 && ` · ${r.stops.length} HOS stop${r.stops.length > 1 ? "s" : ""}`}
            </p>
          </button>
        );
      })}
    </div>
  );
}
