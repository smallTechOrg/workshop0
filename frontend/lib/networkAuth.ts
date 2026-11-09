/**
 * Network sign-in client — spec/api.md §Phase 11 "Auth" (/api/auth/*).
 *
 * Every request is same-origin with `credentials: "include"` (the
 * `workshop0_session` cookie is HttpOnly — the browser carries it, JS never
 * sees it). Every cookie-authenticated mutation also sends NETWORK_HEADERS
 * (architecture.md §Network identity → CSRF).
 *
 * `useCurrentUser()` shares ONE `/api/auth/me` fetch between every component
 * on the page (header menu, page body, …) through a tiny module-level store;
 * `refresh()` re-fetches and notifies all subscribers, `signOut()` clears it.
 */

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";

export type CurrentUser = {
  id: number;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  is_admin: boolean;
  has_profile: boolean;
  /** Server truth: an invite was accepted by this user (api.md /api/auth/me). Drives "Verified" before a profile exists. */
  invite_accepted: boolean;
};

/** Sent on every network request; mutations without it are refused (403 csrf_failed). */
export const NETWORK_HEADERS = { "X-Requested-With": "workshop0" } as const;

/** Where the open-redirect guard sends anything that isn't an `/app/` path. */
export const DEFAULT_NEXT = "/app/network/";

/** ApiError plus the optional `error.details` object (e.g. the masked `invite_email`). */
export class NetworkApiError extends ApiError {
  readonly details: Record<string, unknown> | null;

  constructor(code: string, message: string, status: number, details: Record<string, unknown> | null) {
    super(code, message, status);
    this.name = "NetworkApiError";
    this.details = details;
  }
}

// ---------------------------------------------------------------------------
// Low-level request (envelope-aware, cookie-carrying)
// ---------------------------------------------------------------------------

async function authRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      cache: "no-store",
      credentials: "include",
      ...init,
      headers: {
        Accept: "application/json",
        ...NETWORK_HEADERS,
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
    // Empty / non-JSON body (e.g. a 204 sign-out) — handled below.
  }

  if (!res.ok) {
    const detail = (
      body as {
        detail?: { code?: string; message?: string; details?: Record<string, unknown> };
      } | null
    )?.detail;
    throw new NetworkApiError(
      detail?.code ?? "internal_error",
      detail?.message ?? `The server returned an unexpected error (${res.status}).`,
      res.status,
      detail?.details ?? null,
    );
  }

  // Success envelope {"data": …, "error": null}; tolerate a bare payload.
  if (body && typeof body === "object" && "data" in (body as Record<string, unknown>)) {
    return (body as { data: T }).data;
  }
  return body as T;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

/** `GET /api/auth/config` — false means "Sign-in isn't set up on this server" (not an error). */
export async function getAuthConfig(): Promise<{ google_enabled: boolean }> {
  const res = await authRequest<{ google_enabled?: boolean } | null>("/api/auth/config");
  return { google_enabled: Boolean(res?.google_enabled) };
}

/** `GET /api/auth/me` — never 401; `null` when signed out. Throws ApiError on transport/server failure. */
export async function getMe(): Promise<CurrentUser | null> {
  const res = await authRequest<{ user?: CurrentUser | null } | null>("/api/auth/me");
  return res?.user ?? null;
}

/**
 * `POST /api/me/invite/accept` (api.md §Phase 11d) — applies an invite to the
 * signed-in user's (IdP-verified) email without a second Google round-trip.
 * Throws NetworkApiError with `invite_not_found` / `invite_revoked` /
 * `invite_used` / `invite_expired` / `invite_email_mismatch` (details.invite_email).
 */
export async function acceptInvite(
  token: string,
): Promise<{ invite_accepted: boolean; profile_verified: boolean }> {
  const res = await authRequest<{ invite_accepted?: boolean; profile_verified?: boolean } | null>(
    "/api/me/invite/accept",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    },
  );
  return {
    invite_accepted: Boolean(res?.invite_accepted),
    profile_verified: Boolean(res?.profile_verified),
  };
}

/** Client-side mirror of the server's open-redirect guard: `next` must start with `/app/`. */
export function safeNext(next: string | null | undefined): string {
  if (!next) return DEFAULT_NEXT;
  // Reject protocol-relative and backslash tricks as well as foreign paths.
  if (!next.startsWith("/app/") || next.startsWith("//") || next.includes("\\")) {
    return DEFAULT_NEXT;
  }
  return next;
}

/** Full-page navigation target that starts the Google OIDC flow. */
export function signInUrl(next: string, invite?: string): string {
  const params = new URLSearchParams({ next: safeNext(next) });
  if (invite) params.set("invite", invite);
  return `/api/auth/google/start?${params.toString()}`;
}

/** The app's own sign-in page (`/app/signin/`), carrying `next` and optional `invite`. */
export function signInPageUrl(next: string, invite?: string): string {
  const params = new URLSearchParams({ next: safeNext(next) });
  if (invite) params.set("invite", invite);
  return `/app/signin/?${params.toString()}`;
}

/** `POST /api/auth/signout` — idempotent. Clears the shared user store. */
export async function signOut(): Promise<void> {
  await authRequest<unknown>("/api/auth/signout", { method: "POST" });
  setStore({ user: null, loading: false, error: null, loaded: true });
}

// ---------------------------------------------------------------------------
// Shared current-user store + hook
// ---------------------------------------------------------------------------

type Store = {
  user: CurrentUser | null;
  loading: boolean;
  error: string | null;
  loaded: boolean;
};

let store: Store = { user: null, loading: true, error: null, loaded: false };
let inflight: Promise<void> | null = null;
const listeners = new Set<(s: Store) => void>();

function setStore(next: Store) {
  store = next;
  listeners.forEach((l) => l(store));
}

function errorText(err: unknown): string {
  if (err instanceof ApiError && err.code === "network_error") {
    return "We couldn't reach the server — check your connection.";
  }
  return "We couldn't check whether you're signed in.";
}

function loadUser(): Promise<void> {
  if (inflight) return inflight;
  setStore({ ...store, loading: true, error: null });
  inflight = getMe()
    .then((user) => setStore({ user, loading: false, error: null, loaded: true }))
    .catch((err: unknown) =>
      setStore({ user: null, loading: false, error: errorText(err), loaded: true }),
    )
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

/**
 * The signed-in user (or null), shared across components. `error` is set when
 * the check itself failed (network/server) — distinct from "signed out".
 */
export function useCurrentUser(): {
  user: CurrentUser | null;
  loading: boolean;
  refresh: () => Promise<void>;
  error: string | null;
} {
  const [state, setState] = useState<Store>(store);

  useEffect(() => {
    listeners.add(setState);
    setState(store);
    if (!store.loaded && !inflight) void loadUser();
    return () => {
      listeners.delete(setState);
    };
  }, []);

  const refresh = useCallback(() => loadUser(), []);

  return { user: state.user, loading: state.loading, refresh, error: state.error };
}

/** "Priya Sharma" → "PS"; falls back to the email's first letter. */
export function initials(user: Pick<CurrentUser, "display_name" | "email">): string {
  const name = (user.display_name ?? "").trim();
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean);
    const first = parts[0]?.[0] ?? "";
    const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
    return (first + last).toUpperCase();
  }
  return (user.email[0] ?? "?").toUpperCase();
}
