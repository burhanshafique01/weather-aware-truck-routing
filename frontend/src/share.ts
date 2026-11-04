/**
 * Shareable trip links: ?from=Chicago@41.88,-87.63&to=Denver@39.74,-104.99&load=38000&every=25
 *
 * Departure is deliberately left out of shared links (they would go stale);
 * the recipient plans from the next quarter hour unless `dep` is given.
 */
import type { Place, PlanInput } from "./types";

type Location = Place | { label: string };

export interface SharedTrip {
  origin: Location;
  destination: Location;
  load?: number;
  every?: 10 | 25 | 50;
  departure?: Date;
}

export function encodePlace(place: Location): string {
  return "lat" in place ? `${place.label}@${place.lat.toFixed(4)},${place.lon.toFixed(4)}` : place.label;
}

export function decodePlace(value: string): Location {
  const match = /^(.*)@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)$/.exec(value);
  if (!match) return { label: value };
  return { label: match[1], lat: Number(match[2]), lon: Number(match[3]) };
}

export function readSharedTrip(search = window.location.search): SharedTrip | null {
  const params = new URLSearchParams(search);
  const from = params.get("from");
  const to = params.get("to");
  if (!from || !to) return null;
  const load = Number(params.get("load"));
  const every = Number(params.get("every"));
  const dep = params.get("dep");
  const departure = dep ? new Date(dep) : undefined;
  return {
    origin: decodePlace(from),
    destination: decodePlace(to),
    load: Number.isFinite(load) && load > 0 ? load : undefined,
    every: every === 10 || every === 25 || every === 50 ? every : undefined,
    departure: departure && !Number.isNaN(departure.getTime()) ? departure : undefined,
  };
}

export function writeSharedTrip(input: PlanInput): void {
  const params = new URLSearchParams({
    from: encodePlace(input.origin),
    to: encodePlace(input.destination),
    load: String(input.load_lb),
    every: String(input.interval_mi),
  });
  window.history.replaceState(null, "", `${window.location.pathname}?${params}`);
}
