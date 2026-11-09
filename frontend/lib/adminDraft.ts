/** Admin paste-to-fill drafting client. spec/api.md §Phase 11b. */

import { ApiError } from "@/lib/api";
import type { CompensationUnit, Currency } from "@/lib/compensation";
import type { Location } from "@/lib/locations";

export type DraftedField =
  | "title"
  | "type"
  | "summary"
  | "description_md"
  | "topics"
  | "location"
  | "dates"
  | "duration_text"
  | "deadline"
  | "compensation"
  | "partner"
  | "partner_display_name"
  | "internal_notes";

export interface OpportunityDraft {
  title: string | null;
  type: "workshop" | "engagement" | "role" | "cofacilitation" | null;
  summary: string | null;
  description_md: string | null;
  topic_slugs: string[];
  location_mode: "remote" | "onsite" | "hybrid" | null;
  /** Every drafted venue city, in order (Phase 11c; replaces `city`). */
  locations: Location[];
  starts_on: string | null;
  ends_on: string | null;
  duration_text: string | null;
  deadline_on: string | null;
  compensation_min: number | null;
  compensation_max: number | null;
  compensation_currency: Currency | null;
  compensation_unit: CompensationUnit | null;
  compensation_text: string | null;
  partner_id: number | null;
  suggested_partner: { internal_name: string; display_name: string | null } | null;
  partner_display_name: string | null;
  internal_notes: string | null;
}

export interface DraftResponse {
  draft: OpportunityDraft;
  drafted_fields: DraftedField[];
  cost_usd: number;
  model: string;
}

async function draftRequest<T>(
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
        "X-Requested-With": "workshop0",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
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
    // non-JSON body — fall through to status handling
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

export async function getDraftConfig(
  adminKey: string,
): Promise<{ available: boolean; model: string }> {
  return draftRequest(adminKey, "/api/admin/opportunity-draft/config");
}

export async function draftOpportunity(
  adminKey: string,
  body: { text: string; opportunity_id: number | null; keep_partner_identity: boolean },
): Promise<DraftResponse> {
  return draftRequest(adminKey, "/api/admin/opportunity-draft", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
