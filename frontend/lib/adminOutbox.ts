/** Admin outbox client. spec/api.md §Phase 12. */

import { ApiError } from "@/lib/api";

export type OutboxStatus = "queued" | "sent" | "recorded" | "failed";

export interface OutboxItem {
  id: number;
  to: string;
  template: string;
  subject: string;
  status: OutboxStatus;
  attempts: number;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface OutboxPage {
  items: OutboxItem[];
  page: number;
  page_size: number;
  total: number;
  smtp_configured: boolean;
}

async function call<T>(adminKey: string, path: string, init: RequestInit = {}): Promise<T> {
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
      },
    });
  } catch {
    throw new ApiError("network_error", "Could not reach the server — check your connection.", 0);
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // non-JSON
  }
  if (!res.ok) {
    const d = (body as { detail?: { code?: string; message?: string } } | null)?.detail;
    throw new ApiError(
      d?.code ?? "internal_error",
      d?.message ?? `The server returned an unexpected error (${res.status}).`,
      res.status,
    );
  }
  return (body as { data: T }).data;
}

export function adminListOutbox(adminKey: string, page: number, status?: OutboxStatus) {
  const sp = new URLSearchParams({ page: String(page) });
  if (status) sp.set("status", status);
  return call<OutboxPage>(adminKey, `/api/admin/outbox?${sp}`);
}

export function adminRetryOutbox(adminKey: string, id: number) {
  return call<unknown>(adminKey, `/api/admin/outbox/${id}/retry`, { method: "POST" });
}
