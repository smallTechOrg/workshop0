/** Admin partners client. spec/api.md §Phase 11b. */

import { ApiError } from "@/lib/api";

export interface PartnerRef {
  id: number;
  internal_name: string;
  display_name: string | null;
  active: boolean;
}

export interface AdminPartner extends PartnerRef {
  notes: string | null;
  opportunity_count: number;
  created_at: string;
  updated_at: string;
}

async function partnerRequest<T>(
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
        ...(adminKey ? { "X-Admin-Key": adminKey } : {}),
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

export function adminListPartners(
  adminKey: string,
): Promise<{ partners: AdminPartner[] }> {
  return partnerRequest(adminKey, "/api/admin/partners");
}

export function adminCreatePartner(
  adminKey: string,
  body: { internal_name: string; display_name?: string; notes?: string },
): Promise<{ partner: AdminPartner }> {
  return partnerRequest(adminKey, "/api/admin/partners", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function adminPatchPartner(
  adminKey: string,
  id: number,
  body: Partial<{
    internal_name: string;
    display_name: string;
    notes: string;
    active: boolean;
  }>,
): Promise<{ partner: AdminPartner }> {
  return partnerRequest(adminKey, `/api/admin/partners/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** Calm, human message for a partner API error. */
export function partnerErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "partner_exists")
      return "A partner with that name already exists — pick it from the list instead.";
    return err.message;
  }
  return "Something went wrong — please try again.";
}
