/** Trainer applications + matches client — spec/api.md §Phase 12 (/api/me/applications, /api/me/matches). */

import { NetworkApiError } from "@/lib/network";
import { NETWORK_HEADERS } from "@/lib/networkAuth";
import type { PublicOpportunityCard } from "@/lib/board";

export { NetworkApiError };

export type ApplicationStatus =
  | "applied"
  | "shortlisted"
  | "selected"
  | "not_selected"
  | "withdrawn";

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  applied: "Applied",
  shortlisted: "Shortlisted",
  selected: "Selected",
  not_selected: "Not selected",
  withdrawn: "Withdrawn",
};

export const STATUS_TONES: Record<
  ApplicationStatus,
  "info" | "brand" | "success" | "neutral" | "warning"
> = {
  applied: "info",
  shortlisted: "brand",
  selected: "success",
  not_selected: "neutral",
  withdrawn: "warning",
};

export const NOTE_MAX = 1000;

export interface MyApplication {
  id: number;
  opportunity_id: number;
  status: ApplicationStatus;
  note: string | null;
  source: "self" | "invited";
  status_changed_at: string;
  created_at: string;
  opportunity: PublicOpportunityCard;
}

export interface MatchedOpportunity {
  opportunity: PublicOpportunityCard;
  rule_score: number;
  invited: boolean;
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      cache: "no-store",
      credentials: "same-origin",
      ...init,
      headers: {
        Accept: "application/json",
        ...NETWORK_HEADERS,
        ...(init.body ? { "Content-Type": "application/json" } : {}),
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
    // non-JSON
  }
  if (!res.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    const d = (detail && typeof detail === "object" ? detail : {}) as {
      code?: string;
      message?: string;
    };
    const retry = Number.parseInt(res.headers.get("Retry-After") ?? "", 10);
    throw new NetworkApiError(
      d.code ?? (res.status === 401 ? "not_signed_in" : "internal_error"),
      d.message ?? `The server returned an unexpected error (${res.status}).`,
      res.status,
      Number.isFinite(retry) ? retry : null,
    );
  }
  return (body as { data: T }).data;
}

export function applyTo(opportunityId: number, note: string | null): Promise<{ application: MyApplication }> {
  return call("/api/me/applications", {
    method: "POST",
    body: JSON.stringify({ opportunity_id: opportunityId, note: note?.trim() || null }),
  });
}

export function listMyApplications(): Promise<{ applications: MyApplication[] }> {
  return call("/api/me/applications");
}

export function withdrawApplication(id: number): Promise<{ application: MyApplication }> {
  return call(`/api/me/applications/${id}/withdraw`, { method: "POST" });
}

export function listMatches(): Promise<{ matches: MatchedOpportunity[] }> {
  return call("/api/me/matches");
}

export function errorText(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong.";
}
