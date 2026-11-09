/**
 * Trainer self-service client — spec/api.md §Phase 11 "Trainer self-service" (/api/me/*).
 *
 * Every request is cookie-authenticated (`workshop0_session`, same origin) and
 * carries `NETWORK_HEADERS` (`X-Requested-With: workshop0`); mutations without
 * it are refused with 403 `csrf_failed`. Envelopes follow api.md §Conventions:
 * 200 → `{"data": …, "error": null}`, 4xx/5xx → `{"detail": {"code", "message"}}`.
 *
 * Rates are owner-only data: they exist on these types because `/api/me/profile`
 * is the one non-admin payload allowed to carry them.
 */

import { ApiError } from "@/lib/api";
import { NETWORK_HEADERS } from "@/lib/networkAuth";

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/** ApiError plus the `Retry-After` seconds of a 429 `rate_limited`. */
export class NetworkApiError extends ApiError {
  readonly retryAfterS: number | null;

  constructor(code: string, message: string, status: number, retryAfterS: number | null) {
    super(code, message, status);
    this.name = "NetworkApiError";
    this.retryAfterS = retryAfterS;
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = typeof FormData !== "undefined" && init.body instanceof FormData;
  let res: Response;
  try {
    res = await fetch(path, {
      cache: "no-store",
      credentials: "same-origin",
      ...init,
      headers: {
        Accept: "application/json",
        ...NETWORK_HEADERS,
        ...(init.body && !isForm ? { "Content-Type": "application/json" } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new NetworkApiError(
      "network_error",
      "Could not reach the server — check your connection.",
      0,
      null,
    );
  }

  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // Non-JSON body (proxy error page etc.) — fall through to status handling.
  }

  if (!res.ok) {
    const detail = (body as { detail?: { code?: string; message?: string } } | null)?.detail;
    const retry = Number.parseInt(res.headers.get("Retry-After") ?? "", 10);
    throw new NetworkApiError(
      detail?.code ?? (res.status === 401 ? "not_signed_in" : "internal_error"),
      detail?.message ?? `The server returned an unexpected error (${res.status}).`,
      res.status,
      Number.isFinite(retry) ? retry : null,
    );
  }

  return (body as { data: T }).data;
}

// ---------------------------------------------------------------------------
// Shapes (snake_case is normative)
// ---------------------------------------------------------------------------

export const TOPIC_LEVELS = ["intermediate", "advanced", "expert"] as const;
export type TopicLevel = (typeof TOPIC_LEVELS)[number];
export const TOPIC_LEVEL_LABELS: Record<TopicLevel, string> = {
  intermediate: "Intermediate",
  advanced: "Advanced",
  expert: "Expert",
};
export const MAX_TOPICS = 15;

export const CURRENCIES = ["INR", "USD"] as const;
export type Currency = (typeof CURRENCIES)[number];

export const RATE_UNITS = ["hour", "day", "course", "month"] as const;
export type RateUnit = (typeof RATE_UNITS)[number];
export const RATE_UNIT_LABELS: Record<RateUnit, string> = {
  hour: "/ hour",
  day: "/ day",
  course: "/ course",
  month: "/ month",
};

export const PAST_WORK_KINDS = ["workshop", "talk", "course", "other"] as const;
export type PastWorkKind = (typeof PAST_WORK_KINDS)[number];
export const PAST_WORK_KIND_LABELS: Record<PastWorkKind, string> = {
  workshop: "Workshop",
  talk: "Talk",
  course: "Course",
  other: "Other",
};
export const MAX_PAST_WORK = 30;

export const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
export type Weekday = (typeof WEEKDAYS)[number];
export const WEEKDAY_LABELS: Record<Weekday, string> = {
  mon: "Mon",
  tue: "Tue",
  wed: "Wed",
  thu: "Thu",
  fri: "Fri",
  sat: "Sat",
  sun: "Sun",
};
export const DAY_PARTS = ["morning", "afternoon", "evening"] as const;
export type DayPart = (typeof DAY_PARTS)[number];
export const DAY_PART_LABELS: Record<DayPart, string> = {
  morning: "Morning",
  afternoon: "Afternoon",
  evening: "Evening",
};
export const MAX_BLACKOUTS = 20;

export type Availability = Partial<Record<Weekday, DayPart[]>>;

export interface ProfileTopic {
  slug: string;
  level: TopicLevel;
}

export interface PastWorkItem {
  title: string;
  kind: PastWorkKind;
  org: string | null;
  year: number | null;
}

export interface Blackout {
  start: string;
  end: string;
}

/** api.md §Phase 11 ProfileInput — only `headline` (3–160) and ≥1 topic are required. */
export interface ProfileInput {
  headline: string;
  bio_md: string;
  city: string | null;
  remote_ok: boolean;
  linkedin_url: string | null;
  github_url: string | null;
  website_url: string | null;
  topics: ProfileTopic[];
  past_work: PastWorkItem[];
  rate_min: number | null;
  rate_max: number | null;
  rate_currency: Currency | null;
  rate_unit: RateUnit | null;
  pro_bono: boolean;
  availability: Availability;
  available_from: string | null;
  blackouts: Blackout[];
}

export type ProfileField = keyof ProfileInput;

export type DraftStatus = "pending" | "ready" | "failed" | "skipped";

/** `POST /api/me/cv` / `POST /api/me/cv/text` response (`profiles.cv_summary`). */
export interface CvSummary {
  id: number;
  source: "pdf" | "docx" | "text";
  original_filename: string | null;
  draft_status: DraftStatus;
}

/** Owner CV metadata on OwnProfile (`profiles.cv_meta`) — never the extracted text. */
export interface CvMeta extends CvSummary {
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface DraftPayload {
  draft_status: DraftStatus;
  draft: Partial<ProfileInput> | null;
  autofilled_fields: string[];
}

/** A profile topic as returned by `/api/me/profile` (decorated with its curated name). */
export interface OwnProfileTopic extends ProfileTopic {
  name: string;
}

/** OwnProfile (`profiles.own_profile`) — the ONLY non-admin payload carrying rates, email, CV. */
export interface OwnProfile extends Omit<ProfileInput, "topics"> {
  id: number;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  topics: OwnProfileTopic[];
  visibility: string;
  verified: boolean;
  verified_at: string | null;
  consent_at: string;
  consent_version: string;
  autofilled_fields: string[];
  cv: CvMeta | null;
  created_at: string;
  updated_at: string;
}

/** `services/profiles.py::completeness` — `missing` holds these check keys, in formula order. */
export type CompletenessCheck =
  | "headline"
  | "bio"
  | "topics"
  | "location"
  | "link"
  | "past_work"
  | "rate"
  | "availability"
  | "available_from"
  | "cv";

export interface Completeness {
  pct: number;
  missing: string[];
}

export interface OwnProfilePayload {
  profile: OwnProfile;
  completeness: Completeness;
}

// ---------------------------------------------------------------------------
// Normalisation — drafts and profiles may omit keys; the form needs every one.
// ---------------------------------------------------------------------------

export function emptyProfileInput(): ProfileInput {
  return {
    headline: "",
    bio_md: "",
    city: null,
    remote_ok: true,
    linkedin_url: null,
    github_url: null,
    website_url: null,
    topics: [],
    past_work: [],
    rate_min: null,
    rate_max: null,
    rate_currency: null,
    rate_unit: null,
    pro_bono: false,
    availability: {},
    available_from: null,
    blackouts: [],
  };
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() !== "" ? v : null;
}

function int(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? Math.trunc(v) : null;
}

function oneOf<T extends string>(v: unknown, allowed: readonly T[]): T | null {
  return typeof v === "string" && (allowed as readonly string[]).includes(v) ? (v as T) : null;
}

/** Coerce a (possibly partial or slightly off-shape) draft/profile into a full ProfileInput. */
export function normalizeProfileInput(raw: Partial<ProfileInput> | null | undefined): ProfileInput {
  const base = emptyProfileInput();
  if (!raw) return base;
  const r = raw as Record<string, unknown>;

  const topics: ProfileTopic[] = [];
  if (Array.isArray(r.topics)) {
    for (const t of r.topics) {
      const slug = str((t as { slug?: unknown })?.slug);
      if (!slug || topics.some((x) => x.slug === slug)) continue;
      topics.push({
        slug,
        level: oneOf((t as { level?: unknown }).level, TOPIC_LEVELS) ?? "intermediate",
      });
    }
  }

  const pastWork: PastWorkItem[] = [];
  if (Array.isArray(r.past_work)) {
    for (const p of r.past_work) {
      const item = p as Record<string, unknown>;
      const title = str(item?.title);
      if (!title) continue;
      pastWork.push({
        title,
        kind: oneOf(item.kind, PAST_WORK_KINDS) ?? "other",
        org: str(item.org),
        year: int(item.year),
      });
    }
  }

  const availability: Availability = {};
  if (r.availability && typeof r.availability === "object") {
    for (const day of WEEKDAYS) {
      const parts = (r.availability as Record<string, unknown>)[day];
      if (Array.isArray(parts)) {
        const clean = DAY_PARTS.filter((p) => parts.includes(p));
        if (clean.length) availability[day] = clean;
      }
    }
  }

  const blackouts: Blackout[] = [];
  if (Array.isArray(r.blackouts)) {
    for (const b of r.blackouts) {
      const start = str((b as { start?: unknown })?.start);
      const end = str((b as { end?: unknown })?.end);
      if (start && end) blackouts.push({ start, end });
    }
  }

  return {
    headline: typeof r.headline === "string" ? r.headline : "",
    bio_md: typeof r.bio_md === "string" ? r.bio_md : "",
    city: str(r.city),
    remote_ok: typeof r.remote_ok === "boolean" ? r.remote_ok : base.remote_ok,
    linkedin_url: str(r.linkedin_url),
    github_url: str(r.github_url),
    website_url: str(r.website_url),
    topics,
    past_work: pastWork,
    rate_min: int(r.rate_min),
    rate_max: int(r.rate_max),
    rate_currency: oneOf(r.rate_currency, CURRENCIES),
    rate_unit: oneOf(r.rate_unit, RATE_UNITS),
    pro_bono: r.pro_bono === true,
    availability,
    available_from: str(r.available_from),
    blackouts,
  };
}

// ---------------------------------------------------------------------------
// Completeness — labels for the ten checks (api.md §Completeness)
// ---------------------------------------------------------------------------

/** Nudge copy per missing check, in the formula's order (first three are shown). */
const COMPLETENESS_NUDGES: Array<{ key: CompletenessCheck; label: string }> = [
  { key: "headline", label: "Add a headline" },
  { key: "bio", label: "Write a bio of at least 80 characters" },
  { key: "topics", label: "Add at least 3 topics" },
  { key: "location", label: "Add your city or mark remote OK" },
  { key: "link", label: "Add a LinkedIn, GitHub or website link" },
  { key: "past_work", label: "Add a past workshop or talk" },
  { key: "rate", label: "Add your rate range, currency and unit (or mark pro-bono)" },
  { key: "availability", label: "Mark your weekly availability" },
  { key: "available_from", label: "Set the date you're available from" },
  { key: "cv", label: "Upload your CV" },
];

export function completenessNudge(key: string): string {
  const hit = COMPLETENESS_NUDGES.find((n) => n.key === key);
  if (hit) return hit.label;
  const words = key.replace(/_/g, " ");
  return `Add ${words}`;
}

/** Missing keys sorted into formula order (unknown keys last), de-duplicated by nudge. */
export function orderedNudges(missing: string[]): string[] {
  const rank = (k: string) => {
    const i = COMPLETENESS_NUDGES.findIndex((n) => n.key === k);
    return i === -1 ? COMPLETENESS_NUDGES.length : i;
  };
  const seen = new Set<string>();
  const out: string[] = [];
  for (const k of [...missing].sort((a, b) => rank(a) - rank(b))) {
    const label = completenessNudge(k);
    if (!seen.has(label)) {
      seen.add(label);
      out.push(label);
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const MAX_CV_BYTES = 5 * 1024 * 1024;
export const PASTE_MIN = 200;
export const PASTE_MAX = 30000;
export const DRAFT_POLL_MS = 1500;
export const DRAFT_POLL_LIMIT_MS = 60000;

/** Own-CV download (GET, cookie auth) — a plain link, so the browser handles the file. */
export const OWN_CV_URL = "/api/me/cv/file";

/** `POST /api/me/cv` — multipart `file` (PDF/DOCX ≤5 MB). */
export function uploadCv(file: File): Promise<{ cv: CvSummary }> {
  const form = new FormData();
  form.append("file", file);
  return call("/api/me/cv", { method: "POST", body: form });
}

/** `POST /api/me/cv/text` — pasted CV/LinkedIn text, 200–30000 chars. */
export function submitCvText(text: string): Promise<{ cv: CvSummary }> {
  return call("/api/me/cv/text", { method: "POST", body: JSON.stringify({ text }) });
}

/** `GET /api/me/cv/draft` — polled every 1.5 s, ≤60 s. */
export function getDraft(): Promise<DraftPayload> {
  return call("/api/me/cv/draft");
}

/** `POST /api/me/profile` — ProfileInput + `consent: true`. */
export function createProfile(
  input: ProfileInput,
  consent: boolean,
): Promise<OwnProfilePayload> {
  return call("/api/me/profile", {
    method: "POST",
    body: JSON.stringify({ ...input, consent }),
  });
}

/** `GET /api/me/profile`. */
export function getProfile(): Promise<OwnProfilePayload> {
  return call("/api/me/profile");
}

/** `PATCH /api/me/profile` — partial ProfileInput; clears `autofilled_fields`. */
export function patchProfile(input: Partial<ProfileInput>): Promise<OwnProfilePayload> {
  return call("/api/me/profile", { method: "PATCH", body: JSON.stringify(input) });
}

/** `DELETE /api/me` — `{"confirm_email": "<own email>"}`. */
export function deleteAccount(confirmEmail: string): Promise<{ deleted: true }> {
  return call("/api/me", {
    method: "DELETE",
    body: JSON.stringify({ confirm_email: confirmEmail }),
  });
}

// ---------------------------------------------------------------------------
// Human error copy for the CV intake + profile forms
// ---------------------------------------------------------------------------

export function cvErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case "file_too_large":
        return "That file is larger than 5 MB — try a smaller export, or paste the text instead.";
      case "unsupported_file":
        return "We can read PDF and DOCX files only — save your CV as one of those, or paste the text.";
      case "cv_unreadable":
        return "We couldn't find any text in that file (it may be a scanned image) — paste your CV text instead.";
      case "rate_limited": {
        const s = err instanceof NetworkApiError ? err.retryAfterS : null;
        const mins = s ? Math.max(1, Math.ceil(s / 60)) : null;
        return mins
          ? `You've sent a lot of CVs in the last hour — try again in about ${mins} minute${mins === 1 ? "" : "s"}.`
          : "You've sent a lot of CVs in the last hour — try again a little later.";
      }
      case "validation_error":
        return err.message;
      case "network_error":
        return "We couldn't reach the server — check your connection and try again.";
      case "not_signed_in":
        return "Your sign-in has expired — sign in again to continue.";
    }
  }
  return "Something went wrong on our side while reading your CV — try again, or paste the text instead.";
}

export function saveErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "validation_error") return err.message;
    if (err.code === "network_error")
      return "We couldn't reach the server — your changes are still here; try again.";
    if (err.code === "not_signed_in") return "Your sign-in has expired — sign in again to save.";
    if (err.code === "profile_exists") return "You already have a profile.";
  }
  return "Something went wrong on our side while saving — your changes are still here; try again.";
}

/**
 * Server validation messages are `"<field>: <message>"` (pydantic loc joined with
 * dots, e.g. `"past_work.0.title: is required"`). Returns the top-level ProfileInput
 * field (or `consent`) and the human part, so the form can show it inline.
 */
export function splitFieldError(message: string): { field: string | null; message: string } {
  const m = /^([a-z_]+)(?:\.[\w.]+)?:\s*([\s\S]+)$/.exec(message.trim());
  if (!m) return { field: null, message };
  return { field: m[1], message: m[2] };
}
