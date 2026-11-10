/** Admin applicant-pipeline client. spec/api.md §Phase 12. */

import { ApiError } from "@/lib/api";

export type AppStatus = "applied" | "shortlisted" | "selected" | "not_selected" | "withdrawn";
export const PIPELINE_STATUSES: { key: AppStatus; label: string }[] = [
  { key: "applied", label: "Applied" },
  { key: "shortlisted", label: "Shortlisted" },
  { key: "selected", label: "Selected" },
  { key: "not_selected", label: "Not selected" },
  { key: "withdrawn", label: "Withdrawn" },
];
export const MOVE_TARGETS = PIPELINE_STATUSES.filter((s) => s.key !== "withdrawn");

export interface PipelineApplication {
  id: number;
  opportunity_id: number;
  status: AppStatus;
  note: string | null;
  source: string;
  status_changed_at: string;
  created_at: string;
  trainer: {
    id: number;
    user_id: number;
    display_name: string;
    email: string;
    headline: string | null;
    city: string | null;
    remote_ok: boolean;
    verified: boolean;
  };
}

export interface PipelineData {
  applications: PipelineApplication[];
  counts: Record<AppStatus, number>;
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface BulkResult {
  emails_queued?: number;
  [k: string]: unknown;
}

function headers(adminKey: string, json: boolean): HeadersInit {
  return {
    Accept: "application/json",
    "X-Admin-Key": adminKey,
    "X-Requested-With": "workshop0",
    ...(json ? { "Content-Type": "application/json" } : {}),
  };
}

async function failure(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // non-JSON
  }
  const d = (body as { detail?: { code?: string; message?: string } } | null)?.detail;
  return new ApiError(
    d?.code ?? "internal_error",
    d?.message ?? `The server returned an unexpected error (${res.status}).`,
    res.status,
  );
}

async function call<T>(adminKey: string, path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      cache: "no-store",
      credentials: "include",
      ...init,
      headers: headers(adminKey, !!init.body),
    });
  } catch {
    throw new ApiError("network_error", "Could not reach the server — check your connection.", 0);
  }
  if (!res.ok) throw await failure(res);
  return ((await res.json()) as { data: T }).data;
}

export function adminListApplications(adminKey: string, opportunityId: number) {
  return call<PipelineData>(
    adminKey,
    `/api/admin/opportunities/${opportunityId}/applications?page_size=200`,
  );
}

export function adminMoveApplications(
  adminKey: string,
  opportunityId: number,
  body: { application_ids: number[]; status: AppStatus; notify: boolean },
) {
  return call<BulkResult>(adminKey, `/api/admin/opportunities/${opportunityId}/applications/status`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Downloads the CSV (auth headers can't ride a plain link). */
export async function adminDownloadApplicationsCsv(
  adminKey: string,
  opportunityId: number,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`/api/admin/opportunities/${opportunityId}/applications.csv`, {
      cache: "no-store",
      credentials: "include",
      headers: headers(adminKey, false),
    });
  } catch {
    throw new ApiError("network_error", "Could not reach the server — check your connection.", 0);
  }
  if (!res.ok) throw await failure(res);
  const cd = res.headers.get("Content-Disposition") ?? "";
  const name = /filename="?([^";]+)"?/.exec(cd)?.[1] ?? `applications-${opportunityId}.csv`;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
