/** Saved searches + email preferences client. spec/api.md §Phase 13. */

import { NetworkApiError } from "@/lib/network";
import { NETWORK_HEADERS } from "@/lib/networkAuth";

export { NetworkApiError };

export interface SearchCriteria {
  types: string[];
  topic_slugs: string[];
  location_modes: string[];
  cities: string[];
}

export interface SavedSearch {
  id: number;
  name: string;
  criteria: SearchCriteria;
  alerts_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmailPrefs {
  alerts: boolean;
  digest: boolean;
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

export function listSearches(): Promise<{ searches: SavedSearch[]; limit: number }> {
  return call("/api/me/searches");
}

export function createSearch(body: {
  name: string;
  criteria: SearchCriteria;
  alerts_enabled?: boolean;
}): Promise<SavedSearch> {
  return call("/api/me/searches", { method: "POST", body: JSON.stringify(body) });
}

export function updateSearch(
  id: number,
  body: Partial<{ name: string; criteria: SearchCriteria; alerts_enabled: boolean }>,
): Promise<SavedSearch> {
  return call(`/api/me/searches/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function deleteSearch(id: number): Promise<{ deleted: boolean }> {
  return call(`/api/me/searches/${id}`, { method: "DELETE" });
}

export function getEmailPrefs(): Promise<EmailPrefs> {
  return call("/api/me/email-prefs");
}

export function setEmailPrefs(body: Partial<EmailPrefs>): Promise<EmailPrefs> {
  return call("/api/me/email-prefs", { method: "PATCH", body: JSON.stringify(body) });
}
