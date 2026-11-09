/**
 * Typed client for the Phase-11 ADMIN trainer-pool endpoints — spec/api.md
 * §Phase 11 "Admin pool" (`/api/admin/network/*`).
 *
 * Auth works with EITHER the stored admin key (`X-Admin-Key`, sent only when
 * non-empty) OR the admin's session cookie (`credentials: "include"`). Every
 * request carries `X-Requested-With: workshop0` so cookie-authenticated
 * mutations pass the CSRF check (403 `csrf_failed` otherwise).
 *
 * This slice carries its own small fetch helper so it never edits the shared
 * `lib/api.ts`; it reuses `ApiError` from there.
 */

import { ApiError } from "@/lib/api";

const BASE = "/api/admin/network";

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

function authHeaders(adminKey: string): Record<string, string> {
  const h: Record<string, string> = { "X-Requested-With": "workshop0" };
  if (adminKey) h["X-Admin-Key"] = adminKey;
  return h;
}

async function rawFetch(adminKey: string, path: string, init: RequestInit = {}): Promise<Response> {
  try {
    return await fetch(path, {
      cache: "no-store",
      credentials: "include",
      ...init,
      headers: {
        ...authHeaders(adminKey),
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError("network_error", "Could not reach the server — check your connection.", 0);
  }
}

async function errorFrom(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // Non-JSON body — fall through.
  }
  const detail = (body as { detail?: { code?: string; message?: string } } | null)?.detail;
  return new ApiError(
    detail?.code ?? "internal_error",
    detail?.message ?? `The server returned an unexpected error (${res.status}).`,
    res.status,
  );
}

async function networkRequest<T>(adminKey: string, path: string, init: RequestInit = {}): Promise<T> {
  const res = await rawFetch(adminKey, path, {
    ...init,
    headers: { Accept: "application/json", ...(init.headers ?? {}) },
  });
  if (!res.ok) throw await errorFrom(res);
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    throw new ApiError("internal_error", "The server returned an unreadable response.", res.status);
  }
  return (body as { data: T }).data;
}

/** True for errors that mean "not (or no longer) an admin" — drop back to the gate. */
export function isAuthError(err: unknown): boolean {
  return (
    err instanceof ApiError &&
    (err.status === 401 || (err.status === 403 && err.code === "not_admin"))
  );
}

// ---------------------------------------------------------------------------
// Shapes — exactly what services/pool.py and services/invites.py serialize
// (snake_case is normative).
// ---------------------------------------------------------------------------

export type TopicLevel = "intermediate" | "advanced" | "expert";
export type RateUnit = "hour" | "day" | "course" | "month";

export interface TrainerTopic {
  slug: string;
  name: string;
  level: TopicLevel | string;
}

/** Admin-only rate; the server sends `null` when nothing is set. */
export interface TrainerRate {
  min: number | null;
  max: number | null;
  currency: string | null;
  unit: RateUnit | string | null;
  pro_bono: boolean;
}

export interface PoolRow {
  id: number;
  user_id: number;
  display_name: string;
  email: string;
  avatar_url: string | null;
  headline: string;
  city: string | null;
  remote_ok: boolean;
  topics: TrainerTopic[];
  rate: TrainerRate | null;
  verified: boolean;
  completeness_pct: number;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface PoolPage {
  trainers: PoolRow[];
  page: number;
  page_size: number;
  total: number;
  /** 0 when there are no matches. */
  total_pages: number;
}

export interface PoolFilters {
  q?: string;
  topic?: string[];
  verified?: "true" | "false";
  tag?: string;
  page?: number;
  page_size?: number;
}

export interface PastWorkItem {
  title: string;
  kind?: string | null;
  org?: string | null;
  year?: number | null;
  url?: string | null;
}

export interface AdminNote {
  id: number;
  body: string;
  author: string;
  created_at: string;
}

export interface CvMeta {
  id: number;
  source: string;
  original_filename: string | null;
  content_type: string | null;
  size_bytes: number | null;
  draft_status: string | null;
  /** False for a pasted-text CV (downloaded as a .txt). */
  has_file: boolean;
  created_at: string;
}

export interface TrainerActivity {
  id: number;
  action: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface TrainerDetailProfile extends PoolRow {
  bio_md: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  website_url: string | null;
  past_work: PastWorkItem[];
  rate_min: number | null;
  rate_max: number | null;
  rate_currency: string | null;
  rate_unit: string | null;
  pro_bono: boolean;
  availability: Record<string, unknown>;
  available_from: string | null;
  blackouts: Array<{ start?: string; end?: string }>;
  visibility: string;
  verified_at: string | null;
  verified_by: string | null;
  consent_at: string | null;
  consent_version: string | null;
  completeness: { pct: number; missing: string[] };
  last_login_at: string | null;
}

export interface TrainerDetail {
  trainer: TrainerDetailProfile;
  notes: AdminNote[];
  tags: string[];
  cv: CvMeta | null;
  ai_cost_usd: number;
  activity: TrainerActivity[];
}

export type InviteStatus = "pending" | "accepted" | "expired";

export interface NetworkInvite {
  id: number;
  email: string;
  name: string | null;
  /** Absolute: `<base>/invite/<token>`. */
  url: string;
  status: InviteStatus;
  created_by: string;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
}

export interface InvitePage {
  invites: NetworkInvite[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface SpendByPurpose {
  purpose: string;
  cost_usd: number;
  count: number;
}

export interface NetworkSpend {
  total_cost_usd: number;
  call_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  by_purpose: SpendByPurpose[];
}

export interface PoolTopic {
  id: number;
  slug: string;
  name: string;
  category: string;
  active: boolean;
}

// ---------------------------------------------------------------------------
// Query strings
// ---------------------------------------------------------------------------

export function poolQuery(f: PoolFilters): string {
  const sp = new URLSearchParams();
  if (f.q && f.q.trim()) sp.set("q", f.q.trim());
  for (const t of f.topic ?? []) if (t) sp.append("topic", t);
  if (f.verified) sp.set("verified", f.verified);
  if (f.tag && f.tag.trim()) sp.set("tag", f.tag.trim().toLowerCase());
  if (f.page && f.page > 1) sp.set("page", String(f.page));
  if (f.page_size) sp.set("page_size", String(f.page_size));
  const s = sp.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export function listTrainers(adminKey: string, f: PoolFilters): Promise<PoolPage> {
  return networkRequest<PoolPage>(adminKey, `${BASE}/trainers${poolQuery(f)}`);
}

export function getTrainer(adminKey: string, id: number): Promise<TrainerDetail> {
  return networkRequest<TrainerDetail>(adminKey, `${BASE}/trainers/${id}`);
}

/** Verify / unverify — the server returns the refreshed trainer detail. */
export function verifyTrainer(adminKey: string, id: number, verified: boolean): Promise<TrainerDetail> {
  return networkRequest<TrainerDetail>(
    adminKey,
    `${BASE}/trainers/${id}/${verified ? "verify" : "unverify"}`,
    { method: "POST" },
  );
}

export function addNote(
  adminKey: string,
  id: number,
  body: string,
): Promise<{ note: AdminNote; notes: AdminNote[] }> {
  return networkRequest(adminKey, `${BASE}/trainers/${id}/notes`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

/** Replaces the whole tag set; returns the normalised, sorted set. */
export function setTags(adminKey: string, id: number, tags: string[]): Promise<{ tags: string[] }> {
  return networkRequest(adminKey, `${BASE}/trainers/${id}/tags`, {
    method: "PUT",
    body: JSON.stringify({ tags }),
  });
}

export function listInvites(adminKey: string, page = 1, page_size = 25): Promise<InvitePage> {
  const qs = new URLSearchParams({ page: String(page), page_size: String(page_size) });
  return networkRequest<InvitePage>(adminKey, `${BASE}/invites?${qs.toString()}`);
}

export async function createInvite(
  adminKey: string,
  body: { email: string; name: string | null },
): Promise<NetworkInvite> {
  const d = await networkRequest<{ invite: NetworkInvite }>(adminKey, `${BASE}/invites`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return d.invite;
}

export function getSpend(adminKey: string): Promise<NetworkSpend> {
  return networkRequest<NetworkSpend>(adminKey, `${BASE}/ai-spend`);
}

/** Active topics for the pool's topic filter (admin taxonomy endpoint). */
export async function listPoolTopics(adminKey: string): Promise<PoolTopic[]> {
  const d = await networkRequest<{ topics: PoolTopic[] }>(adminKey, "/api/admin/topics");
  return d.topics.filter((t) => t.active);
}

// ---------------------------------------------------------------------------
// Downloads (CSV, CV)
// ---------------------------------------------------------------------------

function filenameFrom(res: Response, fallback: string): string {
  const cd = res.headers.get("Content-Disposition") ?? "";
  const star = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"|"$/g, ""));
    } catch {
      // fall through
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(cd);
  return plain ? plain[1].trim() : fallback;
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

function navigateDownload(path: string) {
  const a = document.createElement("a");
  a.href = path;
  // `download` keeps the page in place even if the server answers with an error body.
  a.download = "";
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function today(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`;
}

export function trainersCsvPath(f: PoolFilters): string {
  const { page: _p, page_size: _s, ...filters } = f;
  return `${BASE}/trainers.csv${poolQuery(filters)}`;
}

/** Fetches the CSV for the current filters and saves it. */
export async function downloadCsv(adminKey: string, f: PoolFilters): Promise<void> {
  const res = await rawFetch(adminKey, trainersCsvPath(f), { headers: { Accept: "text/csv" } });
  if (!res.ok) throw await errorFrom(res);
  saveBlob(await res.blob(), filenameFrom(res, `workshop0-trainers-${today()}.csv`));
}

/**
 * Downloads the trainer's CV. A session admin (no stored key) navigates to the
 * endpoint so the cookie rides along and a cloud-storage 307 to a signed URL
 * is followed natively. A key admin needs the header, so the file is fetched
 * and saved from memory.
 */
export async function downloadCv(adminKey: string, id: number, fallbackName: string): Promise<void> {
  const path = `${BASE}/trainers/${id}/cv`;
  if (!adminKey) {
    navigateDownload(path);
    return;
  }
  const res = await rawFetch(adminKey, path);
  if (!res.ok) throw await errorFrom(res);
  saveBlob(await res.blob(), filenameFrom(res, fallbackName));
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

export const LEVEL_LABELS: Record<string, string> = {
  intermediate: "Intermediate",
  advanced: "Advanced",
  expert: "Expert",
};

const LEVEL_RANK: Record<string, number> = { expert: 3, advanced: 2, intermediate: 1 };

/** Highest-level topics first. */
export function topTopics(topics: TrainerTopic[], n = 3): TrainerTopic[] {
  return [...topics].sort((a, b) => (LEVEL_RANK[b.level] ?? 0) - (LEVEL_RANK[a.level] ?? 0)).slice(0, n);
}

const UNIT_LABELS: Record<string, string> = {
  hour: "hour",
  day: "day",
  course: "course",
  month: "month",
};

function money(n: number, currency: string | null | undefined): string {
  const c = (currency ?? "").toUpperCase();
  const sym = c === "INR" ? "₹" : c === "USD" ? "$" : c ? `${c} ` : "";
  return `${sym}${n.toLocaleString("en-IN")}`;
}

/** "₹5,000–8,000 / day", "Pro bono", or null when nothing is set. */
export function formatRate(r: TrainerRate | null | undefined): string | null {
  if (!r) return null;
  const min = r.min ?? null;
  const max = r.max ?? null;
  const unit = r.unit ? ` / ${UNIT_LABELS[r.unit] ?? r.unit}` : "";
  let core: string | null = null;
  if (min !== null && max !== null && min !== max) core = `${money(min, r.currency)}–${max.toLocaleString("en-IN")}${unit}`;
  else if (min !== null || max !== null) core = `${money((min ?? max) as number, r.currency)}${unit}`;
  if (core && r.pro_bono) return `${core} · pro bono OK`;
  if (core) return core;
  return r.pro_bono ? "Pro bono" : null;
}

/** "$0.0123" — four decimals under a dollar, two above. */
export function formatUsd(n: number | null | undefined): string {
  const v = Number(n ?? 0) || 0;
  return v < 1 ? `$${v.toFixed(4)}` : `$${v.toFixed(2)}`;
}

export const TAG_RE = /^[a-z0-9][a-z0-9 -]{0,39}$/;
export const MAX_TAGS = 20;

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

/** Same normalisation as the server's `normalize_tag`: trim, lower-case, collapse spaces. */
export function normalizeTag(value: string): string {
  return value.trim().toLowerCase().split(/\s+/).filter(Boolean).join(" ");
}

export const ACTIVITY_LABELS: Record<string, string> = {
  "trainer.verify": "Verified",
  "trainer.unverify": "Unverified",
  "trainer.note": "Added a private note",
  "trainer.tag": "Changed tags",
  "cv.download": "Downloaded the CV",
};

export const PURPOSE_LABELS: Record<string, string> = {
  profile_draft: "Profile drafts from CVs",
  opportunity_draft: "Opportunity drafts",
};
