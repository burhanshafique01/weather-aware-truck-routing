import { useEffect, useRef } from "react";

import { formatDayTime } from "../format";
import { RISK } from "../risk";

interface Props {
  start: string;
  hours: number;
  value: number;
  onChange: (hour: number) => void;
  playing: boolean;
  onPlayingChange: (playing: boolean) => void;
  showHeatmap: boolean;
  onShowHeatmapChange: (show: boolean) => void;
  truckStatus: string;
}

const HOURS_PER_SECOND = 3;

/** 0–48 h forecast scrubber with play/pause, legend and heatmap toggle. */
export function TimeSlider(props: Props) {
  const { start, hours, value, onChange, playing, onPlayingChange } = props;
  const valueRef = useRef(value);
  valueRef.current = value;

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const next = valueRef.current + ((now - last) / 1000) * HOURS_PER_SECOND;
      last = now;
      if (next >= hours) {
        onChange(hours);
        onPlayingChange(false);
        return;
      }
      onChange(next);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, hours, onChange, onPlayingChange]);

  const when = new Date(new Date(start).getTime() + Math.floor(value) * 3600_000);
  const ticks = [0, 12, 24, 36, 48].filter((t) => t <= hours);

  return (
    <div className="time-panel">
      <div className="time-row">
        <button
          type="button"
          className="play"
          onClick={() => {
            if (!playing && value >= hours) onChange(0);
            onPlayingChange(!playing);
          }}
          aria-label={playing ? "Pause forecast animation" : "Play forecast animation"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="time-label">
          <strong>{formatDayTime(when)}</strong>
          <span className="muted">
            Departure +{Math.floor(value)} h · {props.truckStatus}
          </span>
        </div>
        <label className="toggle">
          <input type="checkbox" checked={props.showHeatmap} onChange={(e) => props.onShowHeatmapChange(e.target.checked)} />
          <span>Heatmap</span>
        </label>
      </div>
      <input
        className="slider"
        type="range"
        min={0}
        max={hours}
        step={0.25}
        value={value}
        onChange={(e) => {
          onPlayingChange(false);
          onChange(Number(e.target.value));
        }}
        aria-label="Forecast hour after departure"
        aria-valuetext={`${Math.floor(value)} hours after departure, ${formatDayTime(when)}`}
      />
      <div className="ticks" aria-hidden>
        {ticks.map((t) => (
          <span key={t} style={{ left: `${(t / hours) * 100}%` }}>
            +{t}h
          </span>
        ))}
      </div>
      <div className="legend">
        {RISK.map((r) => (
          <span key={r.key}>
            <i style={{ background: r.color }} />
            {r.label}
          </span>
        ))}
      </div>
    </div>
  );
}
