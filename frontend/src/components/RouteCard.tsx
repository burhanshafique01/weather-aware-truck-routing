import { formatDayTime, formatDuration, formatMiles } from "../format";
import { routeColor } from "../risk";
import type { Route } from "../types";
import { RiskBadge } from "./RiskBadge";
import { RiskBar } from "./RiskBar";

interface Props {
  route: Route;
  selected: boolean;
  fastestS: number;
  onSelect: () => void;
}

export function RouteCard({ route, selected, fastestS, onSelect }: Props) {
  const m = route.metrics.miles_by_level;
  const extra = route.duration_s - fastestS;
  return (
    <button
      type="button"
      className={`route-card${selected ? " selected" : ""}${route.recommended ? " recommended" : ""}`}
      style={{ "--route": routeColor(route.id) } as React.CSSProperties}
      onClick={onSelect}
      aria-pressed={selected}
    >
      <div className="route-head">
        <span className="route-swatch">{route.id}</span>
        <div className="route-title">
          <strong>{route.via.length ? `via ${route.via.slice(0, 2).join(", ")}` : route.name}</strong>
          <span className="muted">
            {formatMiles(route.distance_mi)} · {formatDuration(route.duration_s)}
            {extra > 60 ? <span className="slower"> (+{formatDuration(extra)})</span> : null}
          </span>
        </div>
        {route.recommended ? <span className="pill best">★ Best</span> : <span className="pill rank">#{route.rank}</span>}
      </div>

      <RiskBar miles={m} />

      <dl className="route-stats">
        <div>
          <dt>Severe+</dt>
          <dd className={m.severe + m.no_travel > 0 ? "bad" : ""}>{(m.severe + m.no_travel).toFixed(0)} mi</dd>
        </div>
        <div>
          <dt>High</dt>
          <dd className={m.high > 0 ? "warn" : ""}>{m.high.toFixed(0)} mi</dd>
        </div>
        <div>
          <dt>Avg risk</dt>
          <dd>{route.metrics.average_risk.toFixed(2)}</dd>
        </div>
        <div>
          <dt>Arrive</dt>
          <dd>{formatDayTime(route.arrival)}</dd>
        </div>
      </dl>

      <div className="route-foot">
        <span className="muted">Worst conditions</span>
        <RiskBadge level={route.metrics.max_level} compact />
        {m.no_travel > 0 ? <span className="pill danger">No-travel segment</span> : null}
      </div>
    </button>
  );
}
