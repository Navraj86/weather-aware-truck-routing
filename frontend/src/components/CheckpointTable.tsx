import { memo } from "react";
import { formatDayTime } from "../lib/format";
import type { RouteOption } from "../types";
import { RiskBadge } from "./RoutePanel";

interface Props {
  route: RouteOption;
  focused: number | null;
  onFocus: (index: number | null) => void;
  onPick: (index: number) => void;
}

export const CheckpointTable = memo(function CheckpointTable({ route, focused, onFocus, onPick }: Props) {
  return (
    <section className="checkpoints">
      <h3>
        Route {route.id} checkpoints <span className="muted">({route.checkpoints.length})</span>
      </h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th scope="col">Mile</th>
              <th scope="col">ETA</th>
              <th scope="col" title="Sustained wind (gusts)">
                Wind
              </th>
              <th scope="col">Rain</th>
              <th scope="col">Snow</th>
              <th scope="col">Risk</th>
            </tr>
          </thead>
          <tbody onMouseLeave={() => onFocus(null)}>
            {route.checkpoints.map((c) => (
              <tr
                key={c.index}
                className={focused === c.index ? "focused" : undefined}
                onMouseEnter={() => onFocus(c.index)}
                onClick={() => onPick(c.index)}
                title={[c.weather.description, ...c.risk.drivers].join(" · ")}
              >
                <td className="num">{Math.round(c.mile)}</td>
                <td>{formatDayTime(c.eta)}</td>
                <td className="num">
                  {Math.round(c.weather.wind_mph)}
                  <span className="muted"> ({Math.round(c.weather.gust_mph)})</span>
                </td>
                <td className="num">{c.weather.rain_in_hr.toFixed(2)}</td>
                <td className="num">{c.weather.snow_in_hr.toFixed(2)}</td>
                <td>
                  <RiskBadge level={c.risk.level} compact />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted small">Wind in mph (gusts shown for reference only), rain and snow in in/hr, at the truck's ETA.</p>
    </section>
  );
});
