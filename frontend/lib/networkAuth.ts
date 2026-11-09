/**
 * Network sign-in client — spec/api.md §Phase 11 "Auth" (/api/auth/*).
 *
 * Interface stub laid down by the Phase-11 shared scaffold so every slice can
 * import these exports; slice S9 (fe-network-auth) fills the bodies and keeps
 * the signatures.
 */

export type CurrentUser = {
  id: number;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  is_admin: boolean;
  has_profile: boolean;
};

/** Sent on every network request; mutations without it are refused (403 csrf_failed). */
export const NETWORK_HEADERS = { "X-Requested-With": "workshop0" } as const;

export async function getAuthConfig(): Promise<{ google_enabled: boolean }> {
  return { google_enabled: false };
}

export async function getMe(): Promise<CurrentUser | null> {
  return null;
}

export function signInUrl(next: string, invite?: string): string {
  const params = new URLSearchParams({ next });
  if (invite) params.set("invite", invite);
  return `/api/auth/google/start?${params.toString()}`;
}

export async function signOut(): Promise<void> {
  return;
}

export function useCurrentUser(): {
  user: CurrentUser | null;
  loading: boolean;
  refresh: () => Promise<void>;
} {
  return { user: null, loading: false, refresh: async () => {} };
}
