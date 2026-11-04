import { formatDayTime } from "../format";
import type { Checkpoint } from "../types";
import { RiskBadge } from "./RiskBadge";

interface Props {
  checkpoints: Checkpoint[];
  focused: number | null;
  onFocus: (index: number) => void;
}

export function CheckpointTable({ checkpoints, focused, onFocus }: Props) {
  return (
    <div className="checkpoints">
      <table>
        <thead>
          <tr>
            <th>Mile</th>
            <th>ETA</th>
            <th title="Sustained wind (gust)">Wind</th>
            <th title="Rain, inches per hour">Rain</th>
            <th title="Snowfall, inches per hour">Snow</th>
            <th>Risk</th>
          </tr>
        </thead>
        <tbody>
          {checkpoints.map((cp) => (
            <tr
              key={cp.index}
              className={focused === cp.index ? "focused" : ""}
              onClick={() => onFocus(cp.index)}
              title={cp.risk.reasons.join("\n") || "No weather concerns"}
            >
              <td className="num">{cp.mile.toFixed(0)}</td>
              <td>{formatDayTime(cp.eta)}</td>
              <td className="num">
                {cp.weather.wind_mph.toFixed(0)}
                <span className="muted"> ({cp.weather.gust_mph.toFixed(0)})</span>
              </td>
              <td className="num">{cp.weather.rain_in_hr.toFixed(2)}</td>
              <td className="num">{cp.weather.snow_in_hr.toFixed(2)}</td>
              <td>
                <RiskBadge level={cp.risk.level} compact />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
