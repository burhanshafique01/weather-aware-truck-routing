import { useEffect, useId, useRef, useState } from "react";

import { searchPlaces } from "../api";
import type { Place } from "../types";

interface Props {
  label: string;
  value: Place | { label: string };
  onChange: (value: Place | { label: string }) => void;
  placeholder?: string;
  icon: "origin" | "destination";
}

const DEBOUNCE_MS = 250;

/** Type-ahead place search. Picking a suggestion stores its coordinates; free
 * text is also accepted and geocoded by the server. */
export function PlaceInput({ label, value, onChange, placeholder, icon }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<Place[]>([]);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState(false);
  const typed = useRef(false);

  useEffect(() => {
    if (!typed.current || value.label.trim().length < 3) {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        setResults(await searchPlaces(value.label, controller.signal));
        setActive(-1);
        setOpen(true);
      } catch {
        if (!controller.signal.aborted) setResults([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [value.label]);

  const pick = (place: Place) => {
    typed.current = false;
    onChange(place);
    setOpen(false);
    setResults([]);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open || !results.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a <= 0 ? results.length - 1 : a - 1));
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      pick(results[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const resolved = "lat" in value;
  return (
    <div className="field place">
      <label htmlFor={id}>{label}</label>
      <div className={`place-input ${icon}`}>
        <span className="place-dot" aria-hidden />
        <input
          id={id}
          type="text"
          autoComplete="off"
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          placeholder={placeholder}
          value={value.label}
          onChange={(e) => {
            typed.current = true;
            onChange({ label: e.target.value });
          }}
          onKeyDown={onKeyDown}
          onFocus={() => results.length && setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          required
        />
        {loading ? <span className="spinner small" aria-label="Searching" /> : resolved ? <span className="check" title="Location confirmed">✓</span> : null}
      </div>
      {open && results.length > 0 && (
        <ul className="suggestions" id={`${id}-list`} role="listbox">
          {results.map((r, i) => (
            <li
              key={`${r.label}-${r.lat}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? "active" : ""}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(r);
              }}
            >
              {r.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
