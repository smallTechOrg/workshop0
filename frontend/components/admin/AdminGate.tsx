"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { ApiError } from "@/lib/api";
import { adminListOpportunities } from "@/lib/adminBoard";
import {
  getAuthConfig,
  getMe,
  signInUrl,
  signOut as networkSignOut,
  type CurrentUser,
} from "@/lib/networkAuth";
import { getWithLegacy } from "@/lib/storageCompat";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

/** Same storage key as Admin Home (`app/admin/page.tsx`). */
const LS_ADMIN_KEY = "workshop0_admin_key";

interface AdminSession {
  /**
   * The access key, or `""` when the admin passed the gate with a signed-in
   * admin session (the server then authorises by the session cookie).
   */
  adminKey: string;
  /** Email of the signed-in admin when the gate was passed by session, else null. */
  signedInAs: string | null;
  /** Call on any 401 from an admin endpoint — drops back to the gate. */
  onUnauthorized: () => void;
  signOut: () => void;
}

const AdminContext = createContext<AdminSession | null>(null);

export function useAdmin(): AdminSession {
  const ctx = useContext(AdminContext);
  if (!ctx) throw new Error("useAdmin must be used inside <AdminGate>");
  return ctx;
}

type Phase = "boot" | "gate" | "authed";

function persist(value: string) {
  try {
    window.localStorage.setItem(LS_ADMIN_KEY, value);
  } catch {
    // Private-mode browsers: the key just won't persist.
  }
}

// ---------------------------------------------------------------------------
// Network identity (shared with Admin Home's own gate)
// ---------------------------------------------------------------------------

export interface NetworkIdentity {
  googleEnabled: boolean;
  user: CurrentUser | null;
}

const NO_IDENTITY: NetworkIdentity = { googleEnabled: false, user: null };

function withTimeout<T>(p: Promise<T>, fallback: T, ms = 5000): Promise<T> {
  return new Promise((resolve) => {
    const id = setTimeout(() => resolve(fallback), ms);
    p.then(
      (v) => {
        clearTimeout(id);
        resolve(v);
      },
      () => {
        clearTimeout(id);
        resolve(fallback);
      },
    );
  });
}

/**
 * Sign-in config + the current user. Never throws and never hangs the gate:
 * any failure (or a slow server) degrades to "no Google, not signed in", which
 * leaves the access-key gate exactly as it always was.
 */
export async function loadNetworkIdentity(): Promise<NetworkIdentity> {
  const [config, user] = await Promise.all([
    withTimeout(getAuthConfig(), { google_enabled: false }),
    withTimeout(getMe(), null),
  ]);
  return { googleEnabled: Boolean(config?.google_enabled), user: user ?? null };
}

/** The page the admin is on, as a `/app/...` path for the sign-in `next`. */
export function currentAdminPath(): string {
  if (typeof window === "undefined") return "/app/admin/";
  const path = `${window.location.pathname}${window.location.search}`;
  return path.startsWith("/app/") ? path : "/app/admin/";
}

function GoogleMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 48 48" className="size-5">
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"
      />
      <path
        fill="#FF3D00"
        d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"
      />
    </svg>
  );
}

/**
 * The session half of an admin gate: a "not an admin" notice for a signed-in
 * non-admin, and a **Continue with Google** link when sign-in is configured.
 * Renders nothing when Google is off and nobody is signed in, so the key gate
 * looks exactly as before.
 */
export function AdminSessionSignIn({ identity }: { identity: NetworkIdentity }) {
  const { googleEnabled, user } = identity;
  const notAdmin = user !== null && !user.is_admin;
  if (!googleEnabled && !notAdmin) return null;

  return (
    <div className="mb-5">
      {notAdmin && (
        <div
          role="status"
          data-testid="admin-not-admin"
          className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800"
        >
          You&apos;re signed in as <span className="font-medium">{user.email}</span>, which
          isn&apos;t an admin on this server.{" "}
          {googleEnabled
            ? "Continue with an admin Google account, or enter the access key below."
            : "Enter the access key below to continue."}
        </div>
      )}
      {googleEnabled && (
        <>
          <a
            href={signInUrl(currentAdminPath())}
            data-testid="admin-google-signin"
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-stone-300 bg-white px-4 py-2 font-medium text-stone-800 shadow-sm transition-colors hover:bg-stone-50 active:bg-stone-100"
          >
            <GoogleMark />
            {notAdmin ? "Continue with a different Google account" : "Continue with Google"}
          </a>
          <div className="mt-5 flex items-center gap-3 text-xs text-stone-400" aria-hidden="true">
            <span className="h-px flex-1 bg-stone-200" />
            or use the access key
            <span className="h-px flex-1 bg-stone-200" />
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Gate
// ---------------------------------------------------------------------------

/**
 * Gate for the admin board pages. A signed-in admin session (`/api/auth/me`
 * → `is_admin`) passes without a key. Otherwise it reuses the key Admin Home
 * stored in `workshop0_admin_key` (via the legacy-compat reader) and shows the
 * same messages as Admin Home's gate. Children render only once one of the
 * two has been accepted.
 */
export function AdminGate({
  purpose,
  children,
}: {
  /** One line under the title, e.g. "to manage opportunities". */
  purpose: string;
  children: React.ReactNode;
}) {
  const [phase, setPhase] = useState<Phase>("boot");
  const [adminKey, setAdminKey] = useState("");
  const [identity, setIdentity] = useState<NetworkIdentity>(NO_IDENTITY);
  const [keyInput, setKeyInput] = useState("");
  const [gateError, setGateError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  const sessionAdmin = identity.user?.is_admin ? identity.user : null;

  const validateKey = useCallback(async (key: string, fromSaved: boolean) => {
    setChecking(true);
    try {
      await adminListOpportunities(key, { page_size: 1 });
      persist(key);
      setAdminKey(key);
      setGateError(null);
      setPhase("authed");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        persist("");
        setGateError(
          fromSaved
            ? "Your saved key no longer matches this server — enter it again."
            : "invalid_key",
        );
      } else {
        setGateError("Couldn't reach the server — check it's running, then try again.");
      }
      setPhase("gate");
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const id = await loadNetworkIdentity();
      if (cancelled) return;
      setIdentity(id);
      if (id.user?.is_admin) {
        // Session admin: the cookie authorises every admin call; no key needed.
        setAdminKey("");
        setGateError(null);
        setPhase("authed");
        return;
      }
      let saved: string | null = null;
      try {
        saved = getWithLegacy(LS_ADMIN_KEY);
      } catch {
        // ignore
      }
      if (saved) void validateKey(saved, true);
      else setPhase("gate");
    })();
    return () => {
      cancelled = true;
    };
  }, [validateKey]);

  const onUnauthorized = useCallback(() => {
    if (sessionAdmin) {
      // The session expired or was revoked (or the email left the allowlist).
      setIdentity((prev) => ({ ...prev, user: null }));
      setAdminKey("");
      setGateError("Your sign-in has expired — sign in again, or enter the access key.");
      setPhase("gate");
      return;
    }
    persist("");
    setAdminKey("");
    setGateError("Your key no longer matches this server — enter it again.");
    setPhase("gate");
  }, [sessionAdmin]);

  const signOut = useCallback(() => {
    if (sessionAdmin) {
      void networkSignOut().catch(() => {
        // Best effort — the gate is shown either way.
      });
      setIdentity((prev) => ({ ...prev, user: null }));
    }
    persist("");
    setAdminKey("");
    setKeyInput("");
    setGateError(null);
    setPhase("gate");
  }, [sessionAdmin]);

  const session = useMemo(
    () => ({
      adminKey,
      signedInAs: sessionAdmin?.email ?? null,
      onUnauthorized,
      signOut,
    }),
    [adminKey, sessionAdmin, onUnauthorized, signOut],
  );

  if (phase === "boot") {
    return (
      <main className="mx-auto max-w-6xl px-4 py-10">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-6 h-10 w-full max-w-xl" />
        <div className="mt-6 space-y-3">
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
        </div>
      </main>
    );
  }

  if (phase === "gate") {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <Card className="w-full max-w-md p-8">
          <div className="mb-6 text-center">
            <p aria-hidden="true" className="text-3xl">
              ⛵
            </p>
            <h1 className="mt-2 text-xl font-semibold text-stone-900">Workshop0</h1>
            <p className="mt-1 text-sm text-stone-500">
              {identity.googleEnabled
                ? `Sign in with an admin Google account, or enter this server's facilitator access key ${purpose}.`
                : `Enter this server's facilitator access key ${purpose}.`}
            </p>
          </div>
          <AdminSessionSignIn identity={identity} />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const key = keyInput.trim();
              if (key === "") {
                setGateError("invalid_key_empty");
                return;
              }
              void validateKey(key, false);
            }}
          >
            <label htmlFor="admin-key" className="mb-1 block text-sm font-medium text-stone-700">
              Access key
            </label>
            <input
              id="admin-key"
              data-testid="admin-key-input"
              type="password"
              autoComplete="current-password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-stone-900 focus:border-brand-500"
            />
            {gateError && (
              <p role="alert" className="mt-2 text-sm text-red-600">
                {gateError === "invalid_key" ? (
                  <>
                    That key doesn&apos;t match this server&apos;s{" "}
                    <code className="rounded bg-red-50 px-1 font-mono text-xs">
                      WORKSHOP0_ADMIN_KEY
                    </code>
                    .
                  </>
                ) : gateError === "invalid_key_empty" ? (
                  "Enter the access key to continue."
                ) : (
                  gateError
                )}
              </p>
            )}
            <Button
              type="submit"
              data-testid="admin-key-submit"
              loading={checking}
              className="mt-4 w-full"
            >
              Enter
            </Button>
          </form>
        </Card>
      </main>
    );
  }

  return <AdminContext.Provider value={session}>{children}</AdminContext.Provider>;
}
