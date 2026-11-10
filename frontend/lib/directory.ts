/** Public trainer directory client. spec/api.md §Phase 13 (no auth). */

import { ApiError } from "@/lib/api";

async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new ApiError("network_error", "Could not reach the server — check your connection.", 0);
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // non-JSON body: handled by status below
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

export interface PublicTrainer {
  slug: string;
  display_name: string;
  avatar_url: string | null;
  headline: string;
  city: string | null;
  remote_ok: boolean;
  topics: { slug: string; name: string; level: string }[];
  verified: boolean;
  links: { linkedin: string | null; github: string | null; website: string | null };
  public_url: string;
}

export interface PublicTrainerDetail extends PublicTrainer {
  bio_md: string;
  past_work: { title: string; kind: string; org: string | null; year: number | null }[];
}

export async function listTrainers(
  topic?: string,
  page?: number,
): Promise<{ items: PublicTrainer[]; page: number; page_size: number; total: number }> {
  const q = new URLSearchParams();
  if (topic) q.set("topic", topic);
  if (page && page > 1) q.set("page", String(page));
  const qs = q.toString();
  return getJson(`/api/public/trainers${qs ? `?${qs}` : ""}`);
}

export async function getTrainer(slug: string): Promise<PublicTrainerDetail> {
  return getJson(`/api/public/trainers/${encodeURIComponent(slug)}`);
}

/** Only http(s) URLs are rendered as links. */
export function safeHref(url: string | null): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null;
}
