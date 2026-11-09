/**
 * Multi-location helpers — spec/capabilities.md §C9 additions — Phase 11c and
 * §C10 → Location display. This is the ONLY location formatter: the board
 * card, the listing page and the admin preview all use it.
 */

export type LocationMode = "remote" | "onsite" | "hybrid";

export interface Location {
  city: string;
  country: string | null;
}

export const LOCATIONS_MAX = 10;
export const CITY_MAX = 80;
export const COUNTRY_MAX = 80;

const SEP = " · ";

/** Trim and collapse internal whitespace. */
export function collapse(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

/** Dedupe key: case-insensitive, whitespace-collapsed city + country. */
export function locationKey(l: Location): string {
  return `${collapse(l.city).toLowerCase()}|${collapse(l.country ?? "").toLowerCase()}`;
}

/**
 * Add the comma-separated cities in `cityInput` (each with `countryInput`) to
 * `current`. Blank parts are skipped, duplicates are dropped (flagged by
 * `duplicate`) and the list is capped at LOCATIONS_MAX. When any part is over
 * the length bound nothing is added and `error` carries the inline message.
 */
export function addLocations(
  current: Location[],
  cityInput: string,
  countryInput: string,
): { next: Location[]; duplicate: boolean; error: string | null } {
  const country = collapse(countryInput);
  if (country.length > COUNTRY_MAX) {
    return { next: current, duplicate: false, error: "Country must be 80 characters or fewer" };
  }
  const cities = cityInput.split(",").map(collapse).filter(Boolean);
  if (cities.some((c) => c.length > CITY_MAX)) {
    return { next: current, duplicate: false, error: "City must be 80 characters or fewer" };
  }
  const next = [...current];
  const seen = new Set(next.map(locationKey));
  let duplicate = false;
  for (const city of cities) {
    const loc: Location = { city, country: country || null };
    const key = locationKey(loc);
    if (seen.has(key)) {
      duplicate = true;
      continue;
    }
    if (next.length >= LOCATIONS_MAX) break;
    seen.add(key);
    next.push(loc);
  }
  return { next, duplicate, error: null };
}

interface Locatable {
  location_mode: LocationMode;
  locations?: Location[] | null;
  /** Legacy read-only mirror; used only when `locations` is absent. */
  city?: string | null;
}

/** The listing's locations, falling back to the legacy `city` when absent. */
export function locationsOf(o: Locatable): Location[] {
  if (Array.isArray(o.locations)) return o.locations;
  const c = o.city ? collapse(o.city) : "";
  return c ? [{ city: c, country: null }] : [];
}

function modeLabel(mode: LocationMode): string {
  return mode === "onsite" ? "Onsite" : "Hybrid";
}

/** Card / preview: "Remote" · "Pune · Onsite" · "Bengaluru · Pune · +1 · Hybrid". */
export function locationLabel(o: Locatable): string {
  if (o.location_mode === "remote") return "Remote";
  const locs = locationsOf(o);
  const parts = locs.slice(0, 2).map((l) => l.city);
  if (locs.length > 2) parts.push(`+${locs.length - 2}`);
  parts.push(modeLabel(o.location_mode));
  return parts.join(SEP);
}

/** "City" or "City, Country". */
export function locationText(l: Location): string {
  return l.country ? `${l.city}, ${l.country}` : l.city;
}

/** Listing page: "Bengaluru, India · Pune · Hyderabad · Hybrid". */
export function locationDetailLabel(o: Locatable): string {
  if (o.location_mode === "remote") return "Remote";
  return [...locationsOf(o).map(locationText), modeLabel(o.location_mode)].join(SEP);
}

/** The card's `title`: every city joined with ", ". */
export function locationTitle(locations: Location[]): string {
  return locations.map((l) => l.city).join(", ");
}
