/** Admin workshop facilitators client. spec/api.md §Phase 13. */

import { ApiError } from "@/lib/api";

export type FacilitatorRole = "lead" | "co" | "ta";

export interface Facilitator {
  profile_id: number;
  role: FacilitatorRole;
  display_name: string;
  headline: string;
  email: string;
  linked_by: string;
  created_at: string;
}

async function request<T>(adminKey: string, path: string, init: RequestInit = {}): Promise<T> {
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
    throw new ApiError("network_error", "Could not reach the server — check your connection.", 0);
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // non-JSON body — fall through to status handling
  }
  if (!res.ok) {
    const detail = (body as { detail?: { code?: string; message?: string } } | null)?.detail;
    throw new ApiError(
      detail?.code ?? "internal_error",
      detail?.message ?? `The server returned an unexpected error (${res.status}).`,
      res.status,
    );
  }
  return (body as { data: T }).data;
}

const url = (workshopId: number) => `/api/admin/workshops/${workshopId}/facilitators`;

export function getFacilitators(
  adminKey: string,
  workshopId: number,
): Promise<{ facilitators: Facilitator[] }> {
  return request(adminKey, url(workshopId));
}

/** Replaces the whole set (an empty list unlinks everyone). */
export function putFacilitators(
  adminKey: string,
  workshopId: number,
  facilitators: { profile_id: number; role: FacilitatorRole }[],
): Promise<{ facilitators: Facilitator[] }> {
  return request(adminKey, url(workshopId), {
    method: "PUT",
    body: JSON.stringify({ facilitators }),
  });
}

/** Adds or updates one link. */
export function addFacilitator(
  adminKey: string,
  workshopId: number,
  body: { profile_id: number; role: FacilitatorRole },
): Promise<{ facilitators: Facilitator[] }> {
  return request(adminKey, url(workshopId), { method: "POST", body: JSON.stringify(body) });
}

export const ROLE_LABELS: Record<FacilitatorRole, string> = {
  lead: "Lead",
  co: "Co-facilitator",
  ta: "Teaching assistant",
};
