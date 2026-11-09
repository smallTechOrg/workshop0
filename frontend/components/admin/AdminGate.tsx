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
import { getWithLegacy } from "@/lib/storageCompat";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

/** Same storage key as Admin Home (`app/admin/page.tsx`). */
const LS_ADMIN_KEY = "workshop0_admin_key";

interface AdminSession {
  adminKey: string;
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

/**
 * Key gate for the admin board pages. Reuses the key Admin Home stored in
 * `workshop0_admin_key` (via the legacy-compat reader) and shows the same
 * messages as Admin Home's gate. Children render only once the key has been
 * validated against the server.
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
  const [keyInput, setKeyInput] = useState("");
  const [gateError, setGateError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

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
    let saved: string | null = null;
    try {
      saved = getWithLegacy(LS_ADMIN_KEY);
    } catch {
      // ignore
    }
    if (saved) void validateKey(saved, true);
    else setPhase("gate");
  }, [validateKey]);

  const onUnauthorized = useCallback(() => {
    persist("");
    setAdminKey("");
    setGateError("Your key no longer matches this server — enter it again.");
    setPhase("gate");
  }, []);

  const signOut = useCallback(() => {
    persist("");
    setAdminKey("");
    setKeyInput("");
    setGateError(null);
    setPhase("gate");
  }, []);

  const session = useMemo(
    () => ({ adminKey, onUnauthorized, signOut }),
    [adminKey, onUnauthorized, signOut],
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
              Enter this server&apos;s facilitator access key {purpose}.
            </p>
          </div>
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
