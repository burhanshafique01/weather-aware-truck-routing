/** Shapes returned by the Django API (see backend/routing/services/planner.py). */

export type RiskLevel = 0 | 1 | 2 | 3 | 4;

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface Conditions {
  wind_mph: number;
  gust_mph: number;
  rain_in_hr: number;
  snow_in_hr: number;
}

export interface Checkpoint {
  index: number;
  mile: number;
  lat: number;
  lon: number;
  eta: string;
  coverage_mi: number;
  weather: Conditions;
  risk: {
    level: RiskLevel;
    label: string;
    components: { wind: RiskLevel; rain: RiskLevel; snow: RiskLevel };
    reasons: string[];
  };
}

export interface MilesByLevel {
  low: number;
  moderate: number;
  high: number;
  severe: number;
  no_travel: number;
}

export interface Route {
  id: string;
  name: string;
  via: string[];
  source: "primary" | "alternate" | "detour";
  distance_mi: number;
  duration_s: number;
  arrival: string;
  metrics: { miles_by_level: MilesByLevel; average_risk: number; max_level: RiskLevel };
  rank: number;
  recommended: boolean;
  reason: string | null;
  /** [lat, lon, seconds since departure] */
  path: [number, number, number][];
  checkpoints: Checkpoint[];
}

export interface HeatmapCell {
  lat: number;
  lon: number;
  /** One digit (risk level) per hour, hour 0 … hours. */
  levels: string;
  wind: number[];
  rain: number[];
  snow: number[];
}

export interface Heatmap {
  start: string;
  hours: number;
  dlat: number;
  dlon: number;
  cells: HeatmapCell[];
}

export interface Plan {
  request: {
    origin: Place;
    destination: Place;
    departure: string;
    load_lb: number;
    interval_mi: 10 | 25 | 50;
  };
  generated_at: string;
  recommended_route_id: string;
  routes: Route[];
  heatmap: Heatmap;
}

export interface PlanInput {
  origin: Place | { label: string };
  destination: Place | { label: string };
  departure: string;
  load_lb: number;
  interval_mi: 10 | 25 | 50;
}
