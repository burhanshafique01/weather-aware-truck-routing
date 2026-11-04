import { useEffect, useRef, useState } from "react";

import { nextQuarterHour, timezoneLabel, toLocalInputValue } from "../format";
import { readSharedTrip, writeSharedTrip } from "../share";
import type { Place, PlanInput } from "../types";
import { PlaceInput } from "./PlaceInput";

type Location = Place | { label: string };

const EXAMPLES: { name: string; origin: Place; destination: Place }[] = [
  {
    name: "Chicago → Denver",
    origin: { label: "Chicago, Illinois", lat: 41.8781, lon: -87.6298 },
    destination: { label: "Denver, Colorado", lat: 39.7392, lon: -104.9903 },
  },
  {
    name: "Seattle → Salt Lake City",
    origin: { label: "Seattle, Washington", lat: 47.6062, lon: -122.3321 },
    destination: { label: "Salt Lake City, Utah", lat: 40.7608, lon: -111.891 },
  },
  {
    name: "Dallas → Atlanta",
    origin: { label: "Dallas, Texas", lat: 32.7767, lon: -96.797 },
    destination: { label: "Atlanta, Georgia", lat: 33.749, lon: -84.388 },
  },
];

const INTERVALS = [10, 25, 50] as const;

interface Props {
  loading: boolean;
  onSubmit: (input: PlanInput) => void;
}

export function TripForm({ loading, onSubmit }: Props) {
  const [shared] = useState(() => readSharedTrip());
  const [origin, setOrigin] = useState<Location>(shared?.origin ?? { label: "" });
  const [destination, setDestination] = useState<Location>(shared?.destination ?? { label: "" });
  const [departure, setDeparture] = useState(() => toLocalInputValue(shared?.departure ?? nextQuarterHour()));
  const [load, setLoad] = useState(String(shared?.load ?? 38000));
  const [interval, setInterval] = useState<(typeof INTERVALS)[number]>(shared?.every ?? 25);

  const build = (): PlanInput => ({
    origin,
    destination,
    departure: new Date(departure).toISOString(),
    load_lb: Number(load),
    interval_mi: interval,
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const input = build();
    writeSharedTrip(input);
    onSubmit(input);
  };

  // A shared link plans immediately.
  const autoRan = useRef(false);
  useEffect(() => {
    if (shared && !autoRan.current) {
      autoRan.current = true;
      onSubmit(build());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount
  }, []);

  const now = new Date();
  const maxDeparture = new Date(now.getTime() + 7 * 24 * 3600 * 1000);

  return (
    <form className="trip-form" onSubmit={submit}>
      <div className="places">
        <PlaceInput label="Origin" icon="origin" value={origin} onChange={setOrigin} placeholder="City or address" />
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
        <PlaceInput
          label="Destination"
          icon="destination"
          value={destination}
          onChange={setDestination}
          placeholder="City or address"
        />
      </div>

      <div className="row">
        <div className="field">
          <label htmlFor="departure">
            Departure <span className="hint">({timezoneLabel})</span>
          </label>
          <input
            id="departure"
            type="datetime-local"
            value={departure}
            min={toLocalInputValue(now)}
            max={toLocalInputValue(maxDeparture)}
            onChange={(e) => setDeparture(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="load">Load weight</label>
          <div className="suffix-input">
            <input
              id="load"
              type="number"
              inputMode="numeric"
              min={0}
              max={80000}
              step={500}
              value={load}
              onChange={(e) => setLoad(e.target.value)}
              required
            />
            <span>lb</span>
          </div>
        </div>
      </div>

      <div className="field">
        <span className="label" id="interval-label">
          Weather checkpoint every
        </span>
        <div className="segmented" role="radiogroup" aria-labelledby="interval-label">
          {INTERVALS.map((mi) => (
            <button
              key={mi}
              type="button"
              role="radio"
              aria-checked={interval === mi}
              className={interval === mi ? "on" : ""}
              onClick={() => setInterval(mi)}
            >
              {mi} mi
            </button>
          ))}
        </div>
      </div>

      <button className="primary" type="submit" disabled={loading}>
        {loading ? (
          <>
            <span className="spinner" /> Checking routes & forecasts…
          </>
        ) : (
          "Find safest route"
        )}
      </button>

      <div className="examples">
        <span>Try:</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.name}
            type="button"
            className="link"
            onClick={() => {
              setOrigin(ex.origin);
              setDestination(ex.destination);
            }}
          >
            {ex.name}
          </button>
        ))}
      </div>
    </form>
  );
}
