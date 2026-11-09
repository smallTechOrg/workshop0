"use client";

import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { cn } from "@/lib/format";
import {
  CITY_MAX,
  COUNTRY_MAX,
  LOCATIONS_MAX,
  addLocations,
  locationKey,
  locationText,
  type Location,
} from "@/lib/locations";

/** Imperative handle: commit any typed-but-unadded city (used before Save). */
export interface LocationsInputHandle {
  /** Returns the new list when pending text was added, otherwise null. */
  commit: () => Location[] | null;
}

const FIELD_CLS =
  "rounded-lg border bg-white px-3 py-2 text-stone-900 placeholder:text-stone-400 focus:border-brand-500 disabled:cursor-not-allowed disabled:bg-stone-50";

/**
 * Multi-city chips input — spec/capabilities.md §C9 additions — Phase 11c.
 * Enter / Add / a typed comma / leaving the input adds chips; × removes one.
 */
export function LocationsInput({
  id,
  value,
  onChange,
  serverError,
  handleRef,
}: {
  /** id of the City input (the field label points at it). */
  id: string;
  value: Location[];
  onChange: (next: Location[]) => void;
  /** The server's `locations:` / `city:` validation reason, if any. */
  serverError?: string;
  handleRef?: Ref<LocationsInputHandle>;
}) {
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [dupHint, setDupHint] = useState(false);
  const dupTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const cityRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => {
    if (dupTimer.current) clearTimeout(dupTimer.current);
  }, []);

  const full = value.length >= LOCATIONS_MAX;

  const flashDuplicate = () => {
    setDupHint(true);
    if (dupTimer.current) clearTimeout(dupTimer.current);
    dupTimer.current = setTimeout(() => setDupHint(false), 2000);
  };

  /** Add `cityText` (comma-split) with the current country. Returns the new list, or null. */
  const add = (cityText: string): Location[] | null => {
    if (!cityText.trim()) return null;
    const r = addLocations(value, cityText, country);
    if (r.error) {
      setLocalError(r.error);
      return null;
    }
    setLocalError(null);
    if (r.duplicate) flashDuplicate();
    if (r.next.length !== value.length) onChange(r.next);
    return r.next;
  };

  const commitAll = (): Location[] | null => {
    const next = add(city);
    if (next) {
      setCity("");
      setCountry("");
    }
    return next && next.length !== value.length ? next : null;
  };

  useImperativeHandle(handleRef, () => ({ commit: commitAll }));

  const onCityChange = (raw: string) => {
    setLocalError(null);
    const last = raw.lastIndexOf(",");
    if (last === -1) {
      setCity(raw);
      return;
    }
    const head = raw.slice(0, last);
    const tail = raw.slice(last + 1).replace(/^\s+/, "");
    if (!head.trim()) {
      setCity(tail);
      return;
    }
    const r = addLocations(value, head, country);
    if (r.error) {
      setLocalError(r.error);
      setCity(raw);
      return;
    }
    if (r.duplicate) flashDuplicate();
    if (r.next.length !== value.length) onChange(r.next);
    setCity(tail);
    setCountry("");
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commitAll();
    }
  };

  const remove = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx));
    setLocalError(null);
    cityRef.current?.focus();
  };

  const error = localError ?? serverError ?? null;
  const hint = dupHint ? "Already added" : full ? "Up to 10 locations" : null;

  return (
    <div
      ref={wrapRef}
      id="opp-locations"
      data-testid="opp-locations"
      onBlur={(e) => {
        // Leaving the whole control with text still typed adds it, so nothing is lost on Save.
        const to = e.relatedTarget as Node | null;
        if (to && wrapRef.current?.contains(to)) return;
        commitAll();
      }}
    >
      {value.length > 0 && (
        <ul className="mb-2 flex flex-wrap gap-1.5" aria-label="Locations">
          {value.map((l, i) => (
            <li
              key={locationKey(l)}
              data-testid="opp-location-chip"
              className="inline-flex items-center gap-1 rounded-full border border-stone-200 bg-stone-100 py-0.5 pr-1 pl-2.5 text-sm text-stone-800"
            >
              <span data-testid="opp-location-chip-label">{locationText(l)}</span>
              <button
                type="button"
                data-testid="opp-location-chip-remove"
                aria-label={`Remove ${l.city}`}
                onClick={() => remove(i)}
                className="inline-flex size-5 items-center justify-center rounded-full text-stone-400 hover:bg-stone-200 hover:text-stone-700"
              >
                <span aria-hidden="true">×</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          ref={cityRef}
          id={id}
          data-testid="opp-location-city-input"
          value={city}
          disabled={full}
          maxLength={CITY_MAX * 11 + 10}
          onChange={(e) => onCityChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={full ? "Up to 10 locations" : "City, e.g. Bengaluru"}
          aria-label="City"
          aria-invalid={Boolean(error)}
          aria-describedby={error ? "opp-locations-error" : undefined}
          className={cn(FIELD_CLS, "min-w-0 flex-1", error ? "border-red-400" : "border-stone-300")}
        />
        <input
          data-testid="opp-location-country-input"
          value={country}
          disabled={full}
          maxLength={COUNTRY_MAX + 10}
          onChange={(e) => {
            setLocalError(null);
            setCountry(e.target.value);
          }}
          onKeyDown={onKeyDown}
          placeholder="Country (optional)"
          aria-label="Country (optional)"
          className={cn(FIELD_CLS, "min-w-0 border-stone-300 sm:w-40")}
        />
        <button
          type="button"
          data-testid="opp-location-add"
          disabled={full || !city.trim()}
          onClick={() => {
            commitAll();
            cityRef.current?.focus();
          }}
          className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm font-medium text-stone-700 shadow-sm hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Add
        </button>
      </div>
      {hint && (
        <p data-testid="opp-locations-hint" className="mt-1 text-xs text-stone-500">
          {hint}
        </p>
      )}
      {!hint && !error && (
        <p className="mt-1 text-xs text-stone-500">
          Press Enter or type a comma to add each city.
        </p>
      )}
      {error && (
        <p
          id="opp-locations-error"
          role="alert"
          data-testid="opp-locations-error"
          className="mt-1 text-sm text-red-600"
        >
          {error}
        </p>
      )}
    </div>
  );
}
