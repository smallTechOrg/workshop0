/**
 * Typed API client — implements spec/api.md exactly (Phase 1 surface).
 *
 * Same-origin: all calls hit absolute paths under /api/ (NOT under /app).
 * Success envelope: HTTP 200 -> {"data": <payload>, "error": null}
 * Error envelope:  HTTP 4xx/5xx -> {"detail": {"code": ..., "message": ...}}
 */

// ---------------------------------------------------------------------------
// Envelope + errors
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

interface SuccessEnvelope<T> {
  data: T;
  error: null;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      cache: "no-store",
      credentials: "same-origin",
      ...init,
      headers: {
        Accept: "application/json",
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

  return (body as SuccessEnvelope<T>).data;
}

// ---------------------------------------------------------------------------
// Shared shapes (spec/api.md — snake_case is normative)
// ---------------------------------------------------------------------------

export type WorkshopStatus = "live" | "grace" | "archived";
export type HelpStatus = "open" | "answered" | "resolved";
export type AnswerSource = "facilitator" | "ai" | "participant";

/** Unchanged short-circuit for versioned poll endpoints. */
export interface PollUnchanged {
  changed: false;
  version: number;
  content_version: number;
}

export type MilestoneInputType = "github_url" | "url" | "text" | "dropdown";

export interface MilestoneInputConfig {
  type: MilestoneInputType;
  label: string;
  options?: string[];
}

export interface MilestoneFull {
  id: number;
  position: number;
  title: string;
  content_md: string;
  minutes: number | null;
  input_config: MilestoneInputConfig | null;
}

export interface MilestoneMeta {
  id: number;
  position: number;
  title: string;
  minutes: number | null;
  input_config: MilestoneInputConfig | null;
}

// ---------------------------------------------------------------------------
// Admin surface (header X-Admin-Key)
// ---------------------------------------------------------------------------

/**
 * Every admin call also carries the session cookie and the CSRF header, so a
 * Google-signed-in admin with no key can mutate (a session-authenticated
 * mutation without `X-Requested-With: workshop0` is 403 `csrf_failed` —
 * architecture.md §Network identity). `X-Admin-Key` is still sent as before.
 */
function adminInit(adminKey: string): Pick<RequestInit, "headers" | "credentials"> {
  return {
    credentials: "include",
    headers: { "X-Admin-Key": adminKey, "X-Requested-With": "workshop0" },
  };
}

/** Where a workshop came from — spec/api.md §Phase 6. */
export type WorkshopOrigin = "admin" | "public";

export interface AdminWorkshopSummary {
  id: number;
  name: string;
  status: WorkshopStatus;
  participant_count: number;
  open_help_count: number;
  created_at: string;
  join_slug: string;
  join_url: string;
  facilitator_url: string;
  /** Phase 6 — admin surface only. Older servers omit these. */
  created_via?: WorkshopOrigin;
  creator_email?: string | null;
}

export interface WorkshopFull {
  id: number;
  name: string;
  description_md: string;
  status: WorkshopStatus;
  paused: boolean;
  ai_enabled: boolean;
  admin_token: string;
  join_slug: string;
  join_url: string;
  facilitator_url: string;
  created_at: string;
  /** Phase 6 — present on public creates; `"admin"`/`null` on admin creates. */
  created_via?: WorkshopOrigin;
  creator_email?: string | null;
}

export interface MilestoneInput {
  title: string;
  content_md: string;
  minutes: number | null;
  input_config?: MilestoneInputConfig | null;
}

export interface CreateWorkshopBody {
  name: string;
  description_md: string;
  milestones: MilestoneInput[];
  join_form?: JoinFormField[];
}

export function adminListWorkshops(
  adminKey: string,
): Promise<{ workshops: AdminWorkshopSummary[] }> {
  return request("/api/admin/workshops", adminInit(adminKey));
}

export function adminCreateWorkshop(
  adminKey: string,
  body: CreateWorkshopBody,
): Promise<{ workshop: WorkshopFull }> {
  return request("/api/admin/workshops", {
    method: "POST",
    ...adminInit(adminKey),
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Public surface (no auth) — spec/api.md §Phase 6
// ---------------------------------------------------------------------------

export interface PublicCreateWorkshopBody extends CreateWorkshopBody {
  /** Required. Trimmed + lower-cased server-side; stored, admin-visible only. */
  creator_email: string;
}

/**
 * Keyless twin of `adminCreateWorkshop` — `POST /api/public/workshops`.
 * No `X-Admin-Key` is sent (the route ignores one if present).
 */
export function createPublicWorkshop(
  body: PublicCreateWorkshopBody,
): Promise<{ workshop: WorkshopFull }> {
  return request("/api/public/workshops", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// Facilitator surface (path admin_token)
// ---------------------------------------------------------------------------

export interface FacilitatorWorkshop {
  id: number;
  name: string;
  description_md: string;
  status: WorkshopStatus;
  paused: boolean;
  ai_enabled: boolean;
  join_slug: string;
  join_form: JoinFormField[];
  join_url: string;
  facilitator_url: string;
  created_at: string;
}

export interface FacilitatorWorkshopPayload {
  content_version: number;
  workshop: FacilitatorWorkshop;
  milestones: MilestoneFull[];
}

export interface DashboardStats {
  participant_count: number;
  active_count: number;
  finished_count: number;
  median_progress_pct: number;
  open_help_count: number;
  answered_help_count: number;
  resolved_help_count: number;
}

export interface MilestoneStat {
  milestone_id: number;
  position: number;
  title: string;
  completed_count: number;
  completed_pct: number;
  input_config: MilestoneInputConfig | null;
}

export interface DistributionBucket {
  completed_count: number;
  participants: number;
}

export interface DashboardParticipant {
  id: number;
  name: string;
  answers: Record<string, string>;
  joined_at: string;
  last_seen_at: string;
  completed_milestone_ids: number[];
  completed_count: number;
  progress_pct: number;
  current_milestone_id: number | null;
  open_help_count: number;
  participant_url: string;
  /** {milestone_id: submitted value} for input-gated milestones they've done. */
  milestone_inputs: Record<string, string>;
}

export interface HelpAnswer {
  id: number;
  source: AnswerSource;
  answer_md: string;
  draft: boolean;
  created_at: string;
  ai_confidence: number | null;
  ai_model: string | null;
  ai_context: unknown | null;
}

export interface HelpQueueItem {
  id: number;
  participant_id: number;
  participant_name: string;
  milestone_id: number | null;
  milestone_title: string | null;
  message: string;
  status: HelpStatus;
  resolved_by?: "participant" | "facilitator" | null;
  escalated: boolean;
  created_at: string;
  updated_at: string;
  answers: HelpAnswer[];
}

export interface BroadcastInfo {
  id: number;
  message_md: string;
  created_at: string;
}

export interface StuckParticipant {
  participant_id: number;
  name: string;
  minutes_inactive: number;
  current_milestone_id: number | null;
}

export interface Bottleneck {
  milestone_id: number;
  title: string;
  waiting_count: number;
}

export interface DashboardAlerts {
  stuck: StuckParticipant[];
  bottleneck: Bottleneck | null;
}

export interface DashboardPulse {
  pace_ratio: number;
  on_track_pct: number;
  open_help_count: number;
  projected_finish_at: string | null;
}

export interface DashboardPayload {
  changed: true;
  version: number;
  content_version: number;
  workshop: {
    id: number;
    name: string;
    status: WorkshopStatus;
    paused: boolean;
    ai_enabled: boolean;
  };
  stats: DashboardStats;
  milestone_stats: MilestoneStat[];
  distribution: DistributionBucket[];
  participants: DashboardParticipant[];
  help_queue: HelpQueueItem[];
  broadcast: BroadcastInfo | null;
  alerts: DashboardAlerts | null;
  pulse: DashboardPulse | null;
  spend: unknown | null;
}

export type DashboardPoll = PollUnchanged | DashboardPayload;

export function facilitatorWorkshop(
  adminToken: string,
): Promise<FacilitatorWorkshopPayload> {
  return request(`/api/f/${encodeURIComponent(adminToken)}/workshop`);
}

export function facilitatorDashboard(
  adminToken: string,
  v: number,
): Promise<DashboardPoll> {
  return request(
    `/api/f/${encodeURIComponent(adminToken)}/dashboard?v=${v}`,
  );
}

export function facilitatorAnswerHelp(
  adminToken: string,
  helpRequestId: number,
  answerMd: string,
): Promise<{ help_request: HelpQueueItem; version: number }> {
  return request(
    `/api/f/${encodeURIComponent(adminToken)}/help/${helpRequestId}/answer`,
    { method: "POST", body: JSON.stringify({ answer_md: answerMd }) },
  );
}

export function facilitatorResolveHelp(
  adminToken: string,
  helpRequestId: number,
): Promise<{ help_request: HelpQueueItem; version: number }> {
  return request(
    `/api/f/${encodeURIComponent(adminToken)}/help/${helpRequestId}/resolve`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

// ---------------------------------------------------------------------------
// Facilitator command surface (Phase 2)
// ---------------------------------------------------------------------------

export function facilitatorBroadcast(
  adminToken: string,
  messageMd: string,
): Promise<{ broadcast: BroadcastInfo; version: number; undoable_action_id: number }> {
  return request(`/api/f/${encodeURIComponent(adminToken)}/broadcast`, {
    method: "POST",
    body: JSON.stringify({ message_md: messageMd }),
  });
}

export function facilitatorClearBroadcast(
  adminToken: string,
): Promise<{ version: number }> {
  return request(`/api/f/${encodeURIComponent(adminToken)}/broadcast/clear`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function facilitatorPause(
  adminToken: string,
  paused: boolean,
): Promise<{ version: number; undoable_action_id: number }> {
  return request(`/api/f/${encodeURIComponent(adminToken)}/pause`, {
    method: "POST",
    body: JSON.stringify({ paused }),
  });
}

export function facilitatorAdvance(
  adminToken: string,
  milestoneId: number,
  participantIds: number[] | null,
): Promise<{ version: number; undoable_action_id: number; affected_count: number }> {
  return request(`/api/f/${encodeURIComponent(adminToken)}/milestones/advance`, {
    method: "POST",
    body: JSON.stringify({
      milestone_id: milestoneId,
      participant_ids: participantIds,
    }),
  });
}

export function facilitatorReorder(
  adminToken: string,
  milestoneIds: number[],
): Promise<{ version: number }> {
  return request(`/api/f/${encodeURIComponent(adminToken)}/milestones/reorder`, {
    method: "POST",
    body: JSON.stringify({ milestone_ids: milestoneIds }),
  });
}

export function facilitatorEditWorkshop(
  adminToken: string,
  body: { name?: string; description_md?: string; join_form?: JoinFormField[] },
): Promise<{ workshop: { id: number; name: string; description_md: string }; version: number }> {
  return request(`/api/f/${encodeURIComponent(adminToken)}/workshop`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function facilitatorEditParticipant(
  adminToken: string,
  participantId: number,
  body: { name?: string; answers?: Record<string, string> },
): Promise<{
  participant: { id: number; name: string; answers: Record<string, string> };
  version: number;
}> {
  return request(
    `/api/f/${encodeURIComponent(adminToken)}/participants/${participantId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

export function facilitatorAddMilestone(
  adminToken: string,
  body: MilestoneInput,
): Promise<{ version: number }> {
  return request(`/api/f/${encodeURIComponent(adminToken)}/milestones`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function facilitatorEditMilestone(
  adminToken: string,
  milestoneId: number,
  body: Partial<MilestoneInput>,
): Promise<{ version: number }> {
  return request(
    `/api/f/${encodeURIComponent(adminToken)}/milestones/${milestoneId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
}

export function facilitatorDeleteMilestone(
  adminToken: string,
  milestoneId: number,
): Promise<{ version: number }> {
  return request(
    `/api/f/${encodeURIComponent(adminToken)}/milestones/${milestoneId}`,
    { method: "DELETE" },
  );
}

export function facilitatorUndo(
  adminToken: string,
  actionId: number,
): Promise<{ version: number }> {
  return request(`/api/f/${encodeURIComponent(adminToken)}/undo/${actionId}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export interface AuditAction {
  id: number;
  actor: string;
  action: string;
  detail: Record<string, unknown>;
  created_at: string;
  undone_at: string | null;
}

export function facilitatorAudit(
  adminToken: string,
  opts: { beforeId?: number; limit?: number } = {},
): Promise<{ actions: AuditAction[]; has_more: boolean }> {
  const qs = new URLSearchParams();
  if (opts.beforeId !== undefined) qs.set("before_id", String(opts.beforeId));
  if (opts.limit !== undefined) qs.set("limit", String(opts.limit));
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return request(`/api/f/${encodeURIComponent(adminToken)}/audit${suffix}`);
}

export function facilitatorSettings(
  adminToken: string,
  stuckMinutes: number,
): Promise<{ version: number }> {
  return request(`/api/f/${encodeURIComponent(adminToken)}/settings`, {
    method: "PATCH",
    body: JSON.stringify({ stuck_minutes: stuckMinutes }),
  });
}

// ---------------------------------------------------------------------------
// Participant surface
// ---------------------------------------------------------------------------

export interface JoinFormField {
  key: string;
  label: string;
  type: "text" | "dropdown";
  required: boolean;
  options?: string[];
}

export interface JoinInfo {
  workshop: {
    name: string;
    description_md: string;
    status: WorkshopStatus;
    milestone_count: number;
    participant_count: number;
    join_form: JoinFormField[];
  };
  me: { participant_token: string; name: string } | null;
}

export interface JoinResult {
  participant_token: string;
  participant_url: string;
  name: string;
}

export interface TrackerMe {
  id: number;
  name: string;
  answers: Record<string, string>;
  milestone_inputs: Record<string, string>;
  completed_milestone_ids: number[];
  completed_count: number;
  total_count: number;
  progress_pct: number;
  rank: number;
}

export interface LeaderboardRow {
  rank: number;
  name: string;
  completed_count: number;
  progress_pct: number;
  is_me: boolean;
}

export interface TrackerHelpAnswer {
  id: number;
  source: AnswerSource;
  answer_md: string;
  created_at: string;
}

export interface TrackerHelpRequest {
  id: number;
  message: string;
  status: HelpStatus;
  resolved_by?: "participant" | "facilitator" | null;
  escalated: boolean;
  milestone_id: number | null;
  created_at: string;
  answers: TrackerHelpAnswer[];
}

export interface RoomQuestion {
  id: number;
  asker_name: string;
  message: string;
  status: HelpStatus;
  resolved_by?: "participant" | "facilitator" | null;
  created_at: string;
  answers: TrackerHelpAnswer[];
}

export interface StatePayload {
  changed: true;
  version: number;
  content_version: number;
  workshop: { name: string; status: WorkshopStatus; paused: boolean };
  milestones: MilestoneMeta[];
  me: TrackerMe;
  join_form: JoinFormField[];
  leaderboard: LeaderboardRow[];
  participants_count: number;
  room_open_help_count: number;
  broadcast: BroadcastInfo | null;
  help_requests: TrackerHelpRequest[];
}

export type StatePoll = PollUnchanged | StatePayload;

export interface ContentPayload {
  changed: true;
  content_version: number;
  workshop: { name: string; description_md: string };
  milestones: MilestoneFull[];
}

export type ContentPoll = { changed: false; content_version: number } | ContentPayload;

export interface CompletionResult {
  completed_milestone_ids: number[];
  completed_count: number;
  progress_pct: number;
  version: number;
}

export function joinInfo(joinSlug: string): Promise<JoinInfo> {
  return request(`/api/join/${encodeURIComponent(joinSlug)}`);
}

export function joinWorkshop(
  joinSlug: string,
  name: string,
  answers: Record<string, string> = {},
): Promise<JoinResult> {
  return request(`/api/join/${encodeURIComponent(joinSlug)}`, {
    method: "POST",
    body: JSON.stringify({ name, answers }),
  });
}

export function participantState(
  participantToken: string,
  v: number,
): Promise<StatePoll> {
  return request(
    `/api/p/${encodeURIComponent(participantToken)}/state?v=${v}`,
  );
}

export function participantContent(
  participantToken: string,
  cv: number,
): Promise<ContentPoll> {
  return request(
    `/api/p/${encodeURIComponent(participantToken)}/content?cv=${cv}`,
  );
}

export function completeMilestone(
  participantToken: string,
  milestoneId: number,
  input?: string,
): Promise<CompletionResult> {
  return request(
    `/api/p/${encodeURIComponent(participantToken)}/milestones/${milestoneId}/complete`,
    {
      method: "POST",
      body: JSON.stringify(input === undefined ? {} : { input }),
    },
  );
}

export function uncompleteMilestone(
  participantToken: string,
  milestoneId: number,
): Promise<CompletionResult> {
  return request(
    `/api/p/${encodeURIComponent(participantToken)}/milestones/${milestoneId}/uncomplete`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

export function submitHelp(
  participantToken: string,
  message: string,
): Promise<{ help_request: TrackerHelpRequest; version: number }> {
  return request(`/api/p/${encodeURIComponent(participantToken)}/help`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function participantEditProfile(
  participantToken: string,
  body: { name?: string; answers?: Record<string, string> },
): Promise<{
  participant: { id: number; name: string; answers: Record<string, string> };
  version: number;
}> {
  return request(`/api/p/${encodeURIComponent(participantToken)}/profile`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function participantReplyHelp(
  participantToken: string,
  helpRequestId: number,
  message: string,
): Promise<{ help_request: TrackerHelpRequest; version: number }> {
  return request(
    `/api/p/${encodeURIComponent(participantToken)}/help/${helpRequestId}/reply`,
    { method: "POST", body: JSON.stringify({ message }) },
  );
}

export function participantResolveHelp(
  participantToken: string,
  helpRequestId: number,
): Promise<{ help_request: TrackerHelpRequest; version: number }> {
  return request(
    `/api/p/${encodeURIComponent(participantToken)}/help/${helpRequestId}/resolve`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

export function participantReopenHelp(
  participantToken: string,
  helpRequestId: number,
): Promise<{ help_request: TrackerHelpRequest; version: number }> {
  return request(
    `/api/p/${encodeURIComponent(participantToken)}/help/${helpRequestId}/reopen`,
    { method: "POST", body: JSON.stringify({}) },
  );
}

export function participantRoomQuestions(
  participantToken: string,
): Promise<{ questions: RoomQuestion[] }> {
  return request(`/api/p/${encodeURIComponent(participantToken)}/questions`);
}

// ---------------------------------------------------------------------------
// Pretty-link helpers (architecture.md §Auth — share links use pretty forms)
// ---------------------------------------------------------------------------

export function prettyParticipantUrl(participantToken: string): string {
  return `${window.location.origin}/p/${participantToken}`;
}

export function prettyJoinUrl(joinSlug: string): string {
  return `${window.location.origin}/j/${joinSlug}`;
}

/** Extract the admin token from a facilitator_url ("…/f/<token>"). */
export function tokenFromFacilitatorUrl(facilitatorUrl: string): string {
  const idx = facilitatorUrl.lastIndexOf("/f/");
  return idx >= 0 ? facilitatorUrl.slice(idx + 3) : "";
}

/** Extract the join slug from a join_url ("…/j/<slug>"). */
export function slugFromJoinUrl(joinUrl: string): string {
  const idx = joinUrl.lastIndexOf("/j/");
  return idx >= 0 ? joinUrl.slice(idx + 3) : "";
}
