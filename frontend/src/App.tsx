import { useCallback, useMemo, useRef, useState } from "react";

import { ApiError, planTrip } from "./api";
import { CheckpointTable } from "./components/CheckpointTable";
import { MapView } from "./components/MapView";
import { RouteCard } from "./components/RouteCard";
import { TimeSlider } from "./components/TimeSlider";
import { TripForm } from "./components/TripForm";
import { formatDayTime } from "./format";
import { routeColor } from "./risk";
import type { Plan, PlanInput, Route } from "./types";

export default function App() {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hour, setHour] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [focused, setFocused] = useState<number | null>(null);
  const inflight = useRef<AbortController | null>(null);

  const submit = useCallback(async (input: PlanInput) => {
    inflight.current?.abort();
    const controller = new AbortController();
    inflight.current = controller;
    setLoading(true);
    setError(null);
    setPlaying(false);
    try {
      const result = await planTrip(input, controller.signal);
      setPlan(result);
      setSelectedId(result.recommended_route_id);
      setHour(0);
      setFocused(null);
    } catch (e) {
      if (controller.signal.aborted) return;
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      if (inflight.current === controller) setLoading(false);
    }
  }, []);

  const selected = plan?.routes.find((r) => r.id === selectedId) ?? null;
  const recommended = plan?.routes.find((r) => r.recommended) ?? null;
  const sortedRoutes = useMemo(() => (plan ? [...plan.routes].sort((a, b) => a.rank - b.rank) : []), [plan]);
  const fastestS = plan ? Math.min(...plan.routes.map((r) => r.duration_s)) : 0;

  const selectRoute = useCallback((id: string) => {
    setSelectedId(id);
    setFocused(null);
  }, []);

  return (
    <div className="app">
      <aside className="panel">
        <header className="brand">
          <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" width={36} height={36} />
          <div>
            <h1>Weather-Aware Truck Routing</h1>
            <p>Pick the safest route using forecast wind, rain and snow at the time you'll actually be there.</p>
          </div>
        </header>

        <TripForm loading={loading} onSubmit={submit} />

        {error && (
          <div className="alert" role="alert">
            {error}
          </div>
        )}

        {plan && recommended ? (
          <section className="results" aria-live="polite">
            <div className="recommendation" style={{ "--route": routeColor(recommended.id) } as React.CSSProperties}>
              <span className="eyebrow">Recommended</span>
              <h2>
                {recommended.name}
                {recommended.via.length ? <span> via {recommended.via.slice(0, 2).join(", ")}</span> : null}
              </h2>
              <p>{recommended.reason}</p>
              <p className="muted small">
                Departing {formatDayTime(plan.request.departure)} · {plan.request.load_lb.toLocaleString()} lb · checkpoints
                every {plan.request.interval_mi} mi
              </p>
            </div>

            <h3 className="section-title">Route options</h3>
            <div className="route-list">
              {sortedRoutes.map((route) => (
                <RouteCard
                  key={route.id}
                  route={route}
                  selected={route.id === selectedId}
                  fastestS={fastestS}
                  onSelect={() => selectRoute(route.id)}
                />
              ))}
            </div>

            {selected && (
              <>
                <h3 className="section-title">
                  Checkpoints · {selected.name}
                  <span className="muted"> ({selected.checkpoints.length})</span>
                </h3>
                <CheckpointTable checkpoints={selected.checkpoints} focused={focused} onFocus={setFocused} />
              </>
            )}
          </section>
        ) : (
          !loading && <HowItWorks />
        )}

        <footer className="credits">
          Routing: Valhalla (OSM, truck profile) · Weather: Open-Meteo · Geocoding: Photon
        </footer>
      </aside>

      <main className="map-area">
        <MapView
          plan={plan}
          selectedId={selectedId}
          onSelect={selectRoute}
          hour={hour}
          showHeatmap={showHeatmap}
          focusedCheckpoint={focused}
          onFocusCheckpoint={setFocused}
        />
        {plan && (
          <TimeSlider
            start={plan.heatmap.start}
            hours={plan.heatmap.hours}
            value={hour}
            onChange={setHour}
            playing={playing}
            onPlayingChange={setPlaying}
            showHeatmap={showHeatmap}
            onShowHeatmapChange={setShowHeatmap}
            truckStatus={selected ? truckStatus(selected, hour) : ""}
          />
        )}
        {loading && (
          <div className="map-loading">
            <span className="spinner large" />
            <span>Sampling forecasts along each route…</span>
          </div>
        )}
      </main>
    </div>
  );
}

function truckStatus(route: Route, hour: number): string {
  const elapsed = hour * 3600;
  if (elapsed >= route.duration_s) return `${route.name}: arrived`;
  const depart = new Date(route.checkpoints[0]?.eta ?? 0).getTime();
  const cps = route.checkpoints;
  for (let i = 1; i < cps.length; i++) {
    const t0 = (new Date(cps[i - 1].eta).getTime() - depart) / 1000;
    const t1 = (new Date(cps[i].eta).getTime() - depart) / 1000;
    if (elapsed <= t1) {
      const f = t1 === t0 ? 0 : (elapsed - t0) / (t1 - t0);
      const mile = cps[i - 1].mile + (cps[i].mile - cps[i - 1].mile) * f;
      return `${route.name}: truck at mile ${mile.toFixed(0)}`;
    }
  }
  return `${route.name}: en route`;
}

function HowItWorks() {
  return (
    <section className="how">
      <h3 className="section-title">How it works</h3>
      <ol>
        <li>
          <b>3 truck routes</b> are generated for your load (OpenStreetMap truck profile).
        </li>
        <li>
          Each route is sampled every <b>10, 25 or 50 miles</b>, and the truck's <b>ETA</b> at each checkpoint is
          computed.
        </li>
        <li>
          The forecast <b>at that ETA</b> is classified using the wind, rain and snow thresholds plus the load rules.
        </li>
        <li>
          Routes are ranked by fewest Severe miles, then High miles, then average risk, then travel time.
        </li>
      </ol>
    </section>
  );
}
