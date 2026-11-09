/**
 * Public Opportunity Board client — spec/api.md §Phase 10 "Public surface".
 *
 * Only the PUBLIC endpoints live here (no auth, no X-Admin-Key). The types are
 * an explicit allow-list of the public serializer fields: internal partner
 * names, internal notes and the stored status do not exist on these types, so
 * a public page cannot render them even by accident.
 *
 * Carries its own small fetch helper (roadmap Phase 10 §Assumed) and reuses
 * `ApiError` from lib/api.ts without editing it.
 */

import { ApiError } from "@/lib/api";
import type { CompensationUnit, Currency } from "@/lib/compensation";
import type { Location, LocationMode } from "@/lib/locations";

export type { Location, LocationMode } from "@/lib/locations";

// ---------------------------------------------------------------------------
// Fetch helper (same envelope handling as lib/api.ts)
// ---------------------------------------------------------------------------

async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ApiError(
      "network_error",
      "Could not reach the server — check your connection.",
      0,
    );
  }

  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // Non-JSON body (proxy error page etc.) — fall through to status handling.
  }

  if (!res.ok) {
    const detail = (body as { detail?: { code?: string; message?: string } } | null)
      ?.detail;
    throw new ApiError(
      detail?.code ?? "internal_error",
      detail?.message ?? `The server returned an unexpected error (${res.status}).`,
      res.status,
    );
  }

  return (body as { data: T }).data;
}

// ---------------------------------------------------------------------------
// Shapes (snake_case is normative)
// ---------------------------------------------------------------------------

export const OPPORTUNITY_TYPES = [
  "workshop",
  "engagement",
  "role",
  "cofacilitation",
] as const;
export type OpportunityType = (typeof OPPORTUNITY_TYPES)[number];

/** Effective status. The public list only ever returns `open`. */
export type PublicOpportunityStatus = "open" | "expired" | "closed";

export interface PublicTopic {
  slug: string;
  name: string;
  category: string;
  open_count: number;
}

export interface PublicTopicRef {
  slug: string;
  name: string;
}

export interface PublicOpportunityCard {
  id: number;
  title: string;
  type: OpportunityType;
  summary: string;
  partner_display_name: string | null;
  topics: PublicTopicRef[];
  location_mode: LocationMode;
  /** Every location, in order (`[]` when remote). Phase 11c. */
  locations: Location[];
  /** Legacy, read-only: `locations[0].city`. New UI code reads `locations`. */
  readonly city: string | null;
  starts_on: string | null;
  ends_on: string | null;
  duration_text: string | null;
  compensation_text: string | null;
  compensation_min: number | null;
  compensation_max: number | null;
  compensation_currency: Currency | null;
  compensation_unit: CompensationUnit | null;
  deadline: string;
  published_at: string | null;
  status: PublicOpportunityStatus;
  public_url: string;
}

export interface PublicOpportunityDetail extends PublicOpportunityCard {
  description_md: string;
}

export interface PublicOpportunityPage {
  opportunities: PublicOpportunityCard[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export type BoardSort = "newest" | "deadline";

export interface BoardQuery {
  type: OpportunityType | null;
  topics: string[];
  sort: BoardSort;
  page: number;
}

export const BOARD_PAGE_SIZE = 12;

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

/** `GET /api/public/topics` — active topics, position order, with open counts. */
export function listPublicTopics(): Promise<{ topics: PublicTopic[] }> {
  return getJson("/api/public/topics");
}

/** `GET /api/public/opportunities` — effective-open listings only. */
export function listPublicOpportunities(q: BoardQuery): Promise<PublicOpportunityPage> {
  const qs = new URLSearchParams();
  if (q.type) qs.set("type", q.type);
  for (const t of q.topics) qs.append("topic", t);
  qs.set("sort", q.sort);
  qs.set("page", String(q.page));
  qs.set("page_size", String(BOARD_PAGE_SIZE));
  return getJson(`/api/public/opportunities?${qs.toString()}`);
}

/** `GET /api/public/opportunities/{id}` — open, expired or closed; 404 otherwise. */
export function getPublicOpportunity(
  id: number,
): Promise<{ opportunity: PublicOpportunityDetail }> {
  return getJson(`/api/public/opportunities/${id}`);
}

// ---------------------------------------------------------------------------
// Board URL state  (?type=&topic=&topic=&sort=&page=)
// ---------------------------------------------------------------------------

function isType(v: string | null): v is OpportunityType {
  return v !== null && (OPPORTUNITY_TYPES as readonly string[]).includes(v);
}

/** Minimal read-only view of URLSearchParams (also satisfied by Next's ReadonlyURLSearchParams). */
interface ParamsLike {
  get(name: string): string | null;
  getAll(name: string): string[];
}

/** Parse the board query from the URL, dropping anything invalid. */
export function parseBoardQuery(params: ParamsLike): BoardQuery {
  const rawType = params.get("type");
  const rawSort = params.get("sort");
  const rawPage = Number.parseInt(params.get("page") ?? "", 10);
  const topics: string[] = [];
  for (const t of params.getAll("topic")) {
    const slug = t.trim();
    if (slug && slug.length <= 48 && !topics.includes(slug)) topics.push(slug);
  }
  return {
    type: isType(rawType) ? rawType : null,
    topics,
    sort: rawSort === "deadline" ? "deadline" : "newest",
    page: Number.isFinite(rawPage) && rawPage >= 1 ? rawPage : 1,
  };
}

/** Serialize to a query string (no leading "?"); defaults are omitted. */
export function boardQueryString(q: BoardQuery): string {
  const qs = new URLSearchParams();
  if (q.type) qs.set("type", q.type);
  for (const t of q.topics) qs.append("topic", t);
  if (q.sort !== "newest") qs.set("sort", q.sort);
  if (q.page > 1) qs.set("page", String(q.page));
  return qs.toString();
}

/** Board href (inside the /app basePath — use with next/link or the router). */
export function boardHref(qs: string): string {
  return qs ? `/opportunities/?${qs}` : "/opportunities/";
}

/** Listing href; `from` carries the board's query so the back link keeps filters. */
export function listingHref(id: number, boardQs: string): string {
  const qs = new URLSearchParams({ id: String(id) });
  if (boardQs) qs.set("from", boardQs);
  return `/opportunities/view/?${qs.toString()}`;
}

/** Re-validate a `from` value so it can only ever be a board query string. */
export function sanitizeFromParam(raw: string | null): string {
  if (!raw) return "";
  return boardQueryString(parseBoardQuery(new URLSearchParams(raw)));
}

export function hasActiveFilters(q: BoardQuery): boolean {
  return q.type !== null || q.topics.length > 0;
}

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

export const TYPE_LABELS: Record<OpportunityType, string> = {
  workshop: "Workshop",
  engagement: "Engagement",
  role: "Role",
  cofacilitation: "Co-facilitation",
};

export const DEFAULT_PARTNER_NAME = "smallTech partner network";

export function partnerName(o: { partner_display_name: string | null }): string {
  const n = o.partner_display_name?.trim();
  return n ? n : DEFAULT_PARTNER_NAME;
}

/** "30 Nov" (adds the year when it isn't the current one). */
export function shortDeadline(iso: string, now: number = Date.now()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const sameYear = d.getFullYear() === new Date(now).getFullYear();
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    ...(sameYear ? {} : { year: "numeric" }),
  });
}

/** Full local date + time, e.g. "Sun, 30 Nov 2026, 11:59 pm IST". */
export function longDeadline(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

/** Parse "YYYY-MM-DD" as a calendar date (no timezone shift). */
function parseDateOnly(s: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

function fmtDay(d: Date): string {
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** "5 Dec 2026" · "5 – 6 Dec 2026" · "From 5 Dec 2026" · null when no dates. */
export function dateRangeLabel(startsOn: string | null, endsOn: string | null): string | null {
  const s = startsOn ? parseDateOnly(startsOn) : null;
  const e = endsOn ? parseDateOnly(endsOn) : null;
  if (s && e) {
    if (s.getTime() === e.getTime()) return fmtDay(s);
    if (s.getFullYear() === e.getFullYear() && s.getMonth() === e.getMonth()) {
      return `${s.getDate()} – ${fmtDay(e)}`;
    }
    return `${fmtDay(s)} – ${fmtDay(e)}`;
  }
  if (s) return `From ${fmtDay(s)}`;
  if (e) return `Until ${fmtDay(e)}`;
  return null;
}

const HOUR = 3600_000;
const DAY = 24 * HOUR;

/**
 * Urgency text for the amber pill when ≤7 days remain ("Closes in 3 days");
 * null when more than 7 days remain or the deadline has already passed.
 */
export function urgencyLabel(iso: string, now: number = Date.now()): string | null {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const left = t - now;
  if (left <= 0 || left > 7 * DAY) return null;
  if (left < HOUR) return "Closes in under an hour";
  if (left < DAY) {
    const h = Math.round(left / HOUR);
    return `Closes in ${h} ${h === 1 ? "hour" : "hours"}`;
  }
  const d = Math.max(1, Math.round(left / DAY));
  return `Closes in ${d} ${d === 1 ? "day" : "days"}`;
}
