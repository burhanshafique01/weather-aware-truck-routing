import L from "leaflet";
import { useEffect, useMemo, useRef } from "react";
import { CircleMarker, MapContainer, Marker, Polyline, Popup, TileLayer, Tooltip, useMap } from "react-leaflet";

import { formatDayTime } from "../format";
import { positionAt } from "../geo";
import { riskStyle, routeColor } from "../risk";
import type { Checkpoint, Plan, Route } from "../types";
import { HeatmapLayer } from "./HeatmapLayer";

interface Props {
  plan: Plan | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  hour: number;
  showHeatmap: boolean;
  focusedCheckpoint: number | null;
  onFocusCheckpoint: (index: number | null) => void;
}

const US_CENTER: L.LatLngTuple = [39.5, -98.35];
// Any XYZ raster source works; OSM's standard tiles need no key (fair-use policy applies).
const TILE_URL =
  (import.meta.env.VITE_TILE_URL as string | undefined) ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

export function MapView({ plan, selectedId, onSelect, hour, showHeatmap, focusedCheckpoint, onFocusCheckpoint }: Props) {
  const selected = plan?.routes.find((r) => r.id === selectedId) ?? null;
  // Unselected routes first so the selected one draws on top.
  const ordered = useMemo(
    () => (plan ? [...plan.routes].sort((a, b) => Number(a.id === selectedId) - Number(b.id === selectedId)) : []),
    [plan, selectedId],
  );

  return (
    <MapContainer center={US_CENTER} zoom={4} preferCanvas className="map" zoomControl={false}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · Weather: <a href="https://open-meteo.com/">Open-Meteo</a>'
        url={TILE_URL}
        maxZoom={19}
      />
      <ZoomControl />
      {plan && (
        <>
          <FitToPlan plan={plan} />
          <HeatmapLayer heatmap={plan.heatmap} hour={Math.floor(hour)} visible={showHeatmap} />
          {ordered.map((route) => (
            // Canvas layers draw in insertion order, so re-mount on selection
            // to put the selected route on top of the others.
            <RouteLine
              key={`${route.id}-${route.id === selectedId}`}
              route={route}
              selected={route.id === selectedId}
              onSelect={onSelect}
            />
          ))}
          {selected && (
            <Checkpoints
              route={selected}
              focused={focusedCheckpoint}
              onFocus={onFocusCheckpoint}
            />
          )}
          {selected && <Truck route={selected} hour={hour} />}
          <Endpoint position={[plan.request.origin.lat, plan.request.origin.lon]} kind="origin" label={plan.request.origin.label} />
          <Endpoint
            position={[plan.request.destination.lat, plan.request.destination.lon]}
            kind="destination"
            label={plan.request.destination.label}
          />
        </>
      )}
    </MapContainer>
  );
}

function ZoomControl() {
  const map = useMap();
  useEffect(() => {
    const control = L.control.zoom({ position: "topright" }).addTo(map);
    return () => {
      control.remove();
    };
  }, [map]);
  return null;
}

function FitToPlan({ plan }: { plan: Plan }) {
  const map = useMap();
  useEffect(() => {
    const bounds = L.latLngBounds(plan.routes.flatMap((r) => r.path.map(([lat, lon]) => [lat, lon] as L.LatLngTuple)));
    map.flyToBounds(bounds, { padding: [48, 48], duration: 0.8 });
  }, [plan, map]);
  return null;
}

function RouteLine({ route, selected, onSelect }: { route: Route; selected: boolean; onSelect: (id: string) => void }) {
  const positions = useMemo(() => route.path.map(([lat, lon]) => [lat, lon] as L.LatLngTuple), [route]);
  const color = routeColor(route.id);
  const handlers = useMemo(() => ({ click: () => onSelect(route.id) }), [onSelect, route.id]);
  return (
    <>
      {selected && <Polyline positions={positions} pathOptions={{ color: "#ffffff", weight: 10, opacity: 0.9 }} interactive={false} />}
      <Polyline
        positions={positions}
        pathOptions={{ color, weight: selected ? 6 : 4, opacity: selected ? 1 : 0.55, dashArray: selected ? undefined : "1 7", lineCap: "round" }}
        eventHandlers={handlers}
      >
        <Tooltip sticky>
          <b>{route.name}</b>
          {route.recommended ? " ★ recommended" : ""}
          <br />
          {route.via.join(", ")}
        </Tooltip>
      </Polyline>
    </>
  );
}

function Checkpoints({ route, focused, onFocus }: { route: Route; focused: number | null; onFocus: (i: number | null) => void }) {
  const map = useMap();
  const refs = useRef(new Map<number, L.CircleMarker>());

  useEffect(() => {
    if (focused === null) return;
    const marker = refs.current.get(focused);
    if (!marker) return;
    map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), 7), { duration: 0.6 });
    marker.openPopup();
  }, [focused, map, route]);

  return (
    <>
      {route.checkpoints.map((cp) => {
        const s = riskStyle(cp.risk.level);
        return (
          <CircleMarker
            key={`${route.id}-${cp.index}`}
            ref={(m) => {
              if (m) refs.current.set(cp.index, m);
              else refs.current.delete(cp.index);
            }}
            center={[cp.lat, cp.lon]}
            radius={cp.risk.level > 0 ? 7 : 5}
            pathOptions={{ color: "#ffffff", weight: 2, fillColor: s.color, fillOpacity: 1 }}
            eventHandlers={{ popupopen: () => onFocus(cp.index), popupclose: () => onFocus(null) }}
          >
            <Popup>
              <CheckpointPopup cp={cp} />
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}

function CheckpointPopup({ cp }: { cp: Checkpoint }) {
  const s = riskStyle(cp.risk.level);
  return (
    <div className="cp-popup">
      <div className="cp-title">
        Mile {cp.mile.toFixed(0)} · ETA {formatDayTime(cp.eta)}
      </div>
      <span className="tip-badge" style={{ background: s.color, color: s.text }}>
        {s.label}
      </span>
      <table>
        <tbody>
          <tr>
            <th>Wind</th>
            <td>
              {cp.weather.wind_mph.toFixed(0)} mph <span className="muted">(gusts {cp.weather.gust_mph.toFixed(0)})</span>
            </td>
          </tr>
          <tr>
            <th>Rain</th>
            <td>{cp.weather.rain_in_hr.toFixed(2)} in/hr</td>
          </tr>
          <tr>
            <th>Snow</th>
            <td>{cp.weather.snow_in_hr.toFixed(2)} in/hr</td>
          </tr>
        </tbody>
      </table>
      {cp.risk.reasons.length > 0 && (
        <ul className="reasons">
          {cp.risk.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

const truckIcon = L.divIcon({
  className: "truck-icon",
  html: '<div class="truck-dot"><svg viewBox="0 0 24 24" width="16" height="16"><path fill="#fff" d="M3 6h11v9H3zM14 9h3.5l3 3.5V15H14z"/><circle cx="7" cy="16.5" r="1.8" fill="#fff"/><circle cx="17" cy="16.5" r="1.8" fill="#fff"/></svg></div>',
  iconSize: [30, 30],
  iconAnchor: [15, 15],
});

function Truck({ route, hour }: { route: Route; hour: number }) {
  const pos = positionAt(route.path, hour * 3600);
  if (!pos) return null;
  return (
    <Marker position={pos} icon={truckIcon} interactive={false} zIndexOffset={1000} />
  );
}

function endpointIcon(kind: "origin" | "destination") {
  return L.divIcon({ className: `endpoint ${kind}`, html: "<span></span>", iconSize: [18, 18], iconAnchor: [9, 9] });
}
const ICONS = { origin: endpointIcon("origin"), destination: endpointIcon("destination") };

function Endpoint({ position, kind, label }: { position: L.LatLngTuple; kind: "origin" | "destination"; label: string }) {
  return (
    <Marker position={position} icon={ICONS[kind]} zIndexOffset={900}>
      <Tooltip direction="top" offset={[0, -8]}>
        {kind === "origin" ? "Start: " : "End: "}
        {label}
      </Tooltip>
    </Marker>
  );
}
