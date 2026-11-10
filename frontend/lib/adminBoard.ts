/**
 * Typed client for the Phase-10 ADMIN board endpoints — spec/api.md
 * §Phase 10 "Admin surface". Every call sends `X-Admin-Key`, the session
 * cookie and `X-Requested-With: workshop0` (CSRF for Google-signed-in admins).
 *
 * This slice carries its own small fetch helper (roadmap Phase 10 "Assumed")
 * so it never edits the shared `lib/api.ts`; it reuses `ApiError` from there.
 */

import { ApiError } from "@/lib/api";
import type { CompensationUnit, Currency } from "@/lib/compensation";
import type { PartnerRef } from "@/lib/adminPartners";
import type { Location } from "@/lib/locations";

// ---------------------------------------------------------------------------
// Fetch helper
// ---------------------------------------------------------------------------

async function adminRequest<T>(
  adminKey: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      cache: "no-store",
      credentials: "include",
      ...init,
      headers: {
        Accept: "application/json",
        "X-Admin-Key": adminKey,
        // Session-authenticated (Google-admin) mutations need the CSRF header.
        "X-Requested-With": "workshop0",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(init.headers ?? {}),
      },
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

function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------------------
// Shapes (snake_case is normative)
// ---------------------------------------------------------------------------

export type OpportunityType = "workshop" | "engagement" | "role" | "cofacilitation";
export type LocationMode = "remote" | "onsite" | "hybrid";
/** Effective status — computed on read by the server. */
export type OpportunityStatus = "draft" | "open" | "expired" | "closed";
export type StoredStatus = "draft" | "open" | "closed";

export const OPPORTUNITY_TYPES: { value: OpportunityType; label: string }[] = [
  { value: "workshop", label: "Workshop" },
  { value: "engagement", label: "Engagement" },
  { value: "role", label: "Role" },
  { value: "cofacilitation", label: "Co-facilitation" },
];

export const LOCATION_MODES: { value: LocationMode; label: string }[] = [
  { value: "remote", label: "Remote" },
  { value: "onsite", label: "Onsite" },
  { value: "hybrid", label: "Hybrid" },
];

export type MinLevel = "intermediate" | "advanced" | "expert";

export const MIN_LEVELS: { value: MinLevel; label: string }[] = [
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
  { value: "expert", label: "Expert" },
];

export const STATUS_LABELS: Record<OpportunityStatus, string> = {
  draft: "Draft",
  open: "Open",
  expired: "Expired",
  closed: "Closed",
};

export function typeLabel(t: string): string {
  return OPPORTUNITY_TYPES.find((x) => x.value === t)?.label ?? t;
}

export interface AdminTopicRef {
  id: number;
  slug: string;
  name: string;
  active: boolean;
}

/** Admin list row — `description_md` and `internal_notes` are omitted. */
export interface AdminOpportunityRow {
  id: number;
  title: string;
  type: OpportunityType;
  summary: string;
  topics: AdminTopicRef[];
  location_mode: LocationMode;
  /** Every location, in order (`[]` when remote). Phase 11c. */
  locations: Location[];
  /** Legacy, read-only: `locations[0].city`. New UI code reads `locations`. */
  readonly city: string | null;
  starts_on: string | null;
  ends_on: string | null;
  duration_text: string | null;
  compensation_min: number | null;
  compensation_max: number | null;
  compensation_currency: Currency | null;
  compensation_unit: CompensationUnit | null;
  /** The optional note shown after the amount. */
  compensation_text: string | null;
  /** Phase 12 — admin-only matching fields (never on public payloads). */
  budget_min: number | null;
  budget_max: number | null;
  budget_currency: Currency | null;
  budget_unit: CompensationUnit | null;
  min_level: MinLevel | null;
  /** Applications not withdrawn (the Applicants column). */
  applicant_count: number;
  deadline: string;
  partner_display_name: string | null;
  partner_id: number | null;
  partner: PartnerRef | null;
  /** Derived from `partner.internal_name` (read-only). */
  partner_internal_name: string | null;
  status: OpportunityStatus;
  stored_status: StoredStatus;
  /** Frozen on first publish (Phase 11e); `public_url` ends with `/opportunities/{slug}`. */
  slug: string;
  public_url: string;
  published_at: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminOpportunity extends AdminOpportunityRow {
  description_md: string | null;
  internal_notes: string | null;
}

export interface StatusCounts {
  draft: number;
  open: number;
  expired: number;
  closed: number;
}

export interface AdminOpportunityList {
  opportunities: AdminOpportunityRow[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  counts: StatusCounts;
}

export interface ActivityItem {
  id: number;
  action: string;
  detail: {
    title?: string;
    changed_fields?: string[];
    from_status?: string;
    to_status?: string;
    by?: string;
    [k: string]: unknown;
  } | null;
  created_at: string;
}

export interface AdminTopic {
  id: number;
  slug: string;
  name: string;
  category: string;
  position: number;
  active: boolean;
  opportunity_count: number;
}

/** POST body; PATCH accepts any subset. */
export interface OpportunityBody {
  title: string;
  type: OpportunityType;
  summary: string;
  description_md: string;
  topic_ids: number[];
  location_mode: LocationMode;
  /** The editor sends only `locations` (legacy `city` is never sent). */
  locations: Location[];
  starts_on: string | null;
  ends_on: string | null;
  duration_text: string | null;
  compensation_min: number | null;
  compensation_max: number | null;
  compensation_currency: Currency | null;
  compensation_unit: CompensationUnit | null;
  compensation_text: string | null;
  budget_min: number | null;
  budget_max: number | null;
  budget_currency: Currency | null;
  budget_unit: CompensationUnit | null;
  min_level: MinLevel | null;
  deadline: string | null;
  partner_display_name: string | null;
  partner_id: number | null;
  internal_notes: string | null;
  status: StoredStatus;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export function adminListOpportunities(
  adminKey: string,
  params: {
    status?: OpportunityStatus;
    type?: OpportunityType;
    q?: string;
    page?: number;
    page_size?: number;
  } = {},
): Promise<AdminOpportunityList> {
  return adminRequest(adminKey, `/api/admin/opportunities${qs(params)}`);
}

export function adminCreateOpportunity(
  adminKey: string,
  body: OpportunityBody,
): Promise<{ opportunity: AdminOpportunity }> {
  return adminRequest(adminKey, "/api/admin/opportunities", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function adminGetOpportunity(
  adminKey: string,
  id: number,
): Promise<{ opportunity: AdminOpportunity; activity: ActivityItem[] }> {
  return adminRequest(adminKey, `/api/admin/opportunities/${id}`);
}

export function adminPatchOpportunity(
  adminKey: string,
  id: number,
  body: Partial<OpportunityBody>,
): Promise<{ opportunity: AdminOpportunity }> {
  return adminRequest(adminKey, `/api/admin/opportunities/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function adminListTopics(adminKey: string): Promise<{ topics: AdminTopic[] }> {
  return adminRequest(adminKey, "/api/admin/topics");
}

export function adminCreateTopic(
  adminKey: string,
  body: { name: string; category: string },
): Promise<{ topic: AdminTopic }> {
  return adminRequest(adminKey, "/api/admin/topics", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function adminPatchTopic(
  adminKey: string,
  id: number,
  body: Partial<{ name: string; category: string; active: boolean }>,
): Promise<{ topic: AdminTopic }> {
  return adminRequest(adminKey, `/api/admin/topics/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Split a `validation_error` message of the normative form
 * `"<field>: <reason>"` (api.md §POST /api/admin/opportunities). Tolerates
 * a nested suffix such as `topic_ids.0: …`. Returns null for any other shape.
 */
export function parseFieldError(
  message: string,
): { field: string; reason: string } | null {
  const m = /^([a-z_]+)(?:[.[][^:]*)?:\s*(.+)$/s.exec(message.trim());
  if (!m) return null;
  return { field: m[1], reason: m[2] };
}

/** "in 5 days" / "in 3 h" / "expired 2 days ago" relative to `now`. */
export function relativeDeadline(iso: string, now: number = Date.now()): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const diff = t - now;
  const abs = Math.abs(diff);
  const mins = Math.round(abs / 60000);
  const hours = Math.round(abs / 3600000);
  const days = Math.round(abs / 86400000);
  let span: string;
  if (mins < 60) span = `${Math.max(1, mins)} min`;
  else if (hours < 24) span = `${hours} h`;
  else span = `${days} day${days === 1 ? "" : "s"}`;
  return diff > 0 ? `in ${span}` : `expired ${span} ago`;
}
