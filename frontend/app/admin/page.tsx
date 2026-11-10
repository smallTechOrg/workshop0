"use client";

import { getWithLegacy } from "@/lib/storageCompat";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  ApiError,
  adminListWorkshops,
  type AdminWorkshopSummary,
  type WorkshopFull,
} from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { StubBadge, StubCard } from "@/components/ui/StubBadge";
import { useToast } from "@/components/ui/Toast";
import { WorkshopCard } from "@/components/facilitator/WorkshopCard";
import { CreateWorkshopModal } from "@/components/facilitator/CreateWorkshopModal";
import {
  AdminSessionSignIn,
  loadNetworkIdentity,
  type NetworkIdentity,
} from "@/components/admin/AdminGate";
import { signOut as networkSignOut } from "@/lib/networkAuth";

const LS_ADMIN_KEY = "workshop0_admin_key";

type Phase = "boot" | "gate" | "authed";
/** How the gate was passed: the access key, or a signed-in admin session. */
type Mode = "key" | "session";

export default function AdminHomePage() {
  const toast = useToast();
  const [phase, setPhase] = useState<Phase>("boot");
  const [adminKey, setAdminKey] = useState("");
  const [mode, setMode] = useState<Mode>("key");
  const [identity, setIdentity] = useState<NetworkIdentity>({
    googleEnabled: false,
    user: null,
  });
  const [keyInput, setKeyInput] = useState("");
  const [gateError, setGateError] = useState<string | null>(null);
  const [gateChecking, setGateChecking] = useState(false);
  const [workshops, setWorkshops] = useState<AdminWorkshopSummary[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [justCreatedId, setJustCreatedId] = useState<number | null>(null);

  const validateKey = useCallback(
    async (key: string, fromSaved: boolean) => {
      setGateChecking(true);
      try {
        const { workshops: list } = await adminListWorkshops(key);
        try {
          window.localStorage.setItem(LS_ADMIN_KEY, key);
        } catch {
          // Private-mode browsers: the key just won't persist.
        }
        setAdminKey(key);
        setMode("key");
        setWorkshops(list);
        setGateError(null);
        setPhase("authed");
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          try {
            window.localStorage.setItem(LS_ADMIN_KEY, "");
          } catch {
            // ignore
          }
          setGateError(
            fromSaved
              ? "Your saved key no longer matches this server — enter it again."
              : "invalid_key",
          );
        } else {
          setGateError(
            "Couldn't reach the server — check it's running, then try again.",
          );
        }
        setPhase("gate");
      } finally {
        setGateChecking(false);
      }
    },
    [],
  );

  /** A signed-in admin session passes without a key (the cookie authorises). */
  const enterWithSession = useCallback(async (): Promise<boolean> => {
    try {
      const { workshops: list } = await adminListWorkshops("");
      setAdminKey("");
      setMode("session");
      setWorkshops(list);
      setGateError(null);
      setPhase("authed");
      return true;
    } catch (err) {
      setIdentity((prev) => ({ ...prev, user: null }));
      setGateError(
        err instanceof ApiError && (err.status === 401 || err.status === 403)
          ? "Your sign-in has expired — sign in again, or enter the access key."
          : "Couldn't reach the server — check it's running, then try again.",
      );
      return false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const id = await loadNetworkIdentity();
      if (cancelled) return;
      setIdentity(id);
      if (id.user?.is_admin && (await enterWithSession())) return;
      if (cancelled) return;
      let saved: string | null = null;
      try {
        saved = getWithLegacy(LS_ADMIN_KEY);
      } catch {
        // ignore
      }
      if (saved) {
        void validateKey(saved, true);
      } else {
        setPhase("gate");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [validateKey, enterWithSession]);

  const refreshList = useCallback(async () => {
    if (mode === "key" && !adminKey) return;
    setRefreshing(true);
    setListError(null);
    try {
      const { workshops: list } = await adminListWorkshops(adminKey);
      setWorkshops(list);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setPhase("gate");
        if (mode === "session") {
          setIdentity((prev) => ({ ...prev, user: null }));
          setMode("key");
          setGateError("Your sign-in has expired — sign in again, or enter the access key.");
        } else {
          setGateError("Your key no longer matches this server — enter it again.");
        }
      } else {
        setListError("Couldn't refresh the list — check your connection and try again.");
      }
    } finally {
      setRefreshing(false);
    }
  }, [adminKey, mode]);

  const onCreated = (workshop: WorkshopFull) => {
    setCreateOpen(false);
    setJustCreatedId(workshop.id);
    toast.show(`“${workshop.name}” is live`, "success");
    void refreshList();
  };

  const signOut = () => {
    if (mode === "session") {
      void networkSignOut().catch(() => {
        // Best effort — the gate is shown either way.
      });
      setIdentity((prev) => ({ ...prev, user: null }));
      setMode("key");
    }
    try {
      window.localStorage.setItem(LS_ADMIN_KEY, "");
    } catch {
      // ignore
    }
    setAdminKey("");
    setWorkshops(null);
    setKeyInput("");
    setGateError(null);
    setPhase("gate");
  };

  // ------------------------------------------------------------- boot
  if (phase === "boot") {
    return (
      <main className="mx-auto max-w-5xl px-4 py-10">
        <Skeleton className="h-8 w-64" />
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      </main>
    );
  }

  // ------------------------------------------------------------- gate
  if (phase === "gate") {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <Card className="w-full max-w-md p-8">
          <div className="mb-6 text-center">
            <p aria-hidden="true" className="text-3xl">
              ⛵
            </p>
            <h1 className="mt-2 text-xl font-semibold text-stone-900">
              Workshop0
            </h1>
            <p className="mt-1 text-sm text-stone-500">
              {identity.googleEnabled
                ? "Sign in with an admin Google account, or enter this server's facilitator access key to manage workshops."
                : "Enter this server's facilitator access key to manage workshops."}
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
            <label
              htmlFor="admin-key"
              className="mb-1 block text-sm font-medium text-stone-700"
            >
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
                    That key doesn't match this server's{" "}
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
              loading={gateChecking}
              className="mt-4 w-full"
            >
              Enter
            </Button>
          </form>
        </Card>
      </main>
    );
  }

  // ----------------------------------------------------------- authed
  const list = workshops ?? [];

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-8 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span aria-hidden="true" className="text-2xl">
            ⛵
          </span>
          <h1 className="text-xl font-semibold text-stone-900">Workshop0</h1>
        </div>
        <nav aria-label="Admin actions" className="flex flex-wrap items-center gap-2">
          <Link
            href="/admin/opportunities/"
            data-testid="nav-opportunities"
            className="inline-flex items-center rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 text-sm font-medium text-stone-800 shadow-sm transition-colors hover:bg-stone-50"
          >
            Opportunities
          </Link>
          <Link
            href="/admin/network/"
            data-testid="nav-trainer-network"
            className="inline-flex items-center rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 text-sm font-medium text-stone-800 shadow-sm transition-colors hover:bg-stone-50"
          >
            Trainer network
          </Link>
          <Link
            href="/admin/outbox/"
            data-testid="nav-outbox"
            className="inline-flex items-center rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 text-sm font-medium text-stone-800 shadow-sm transition-colors hover:bg-stone-50"
          >
            Outbox
          </Link>
          <span
            aria-disabled="true"
            className="inline-flex items-center gap-2 rounded-lg border border-dashed border-stone-300 bg-stone-50 px-3 py-1.5 text-sm font-medium text-stone-400 select-none"
          >
            Template library
            <StubBadge />
          </span>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void refreshList()}
            loading={refreshing}
          >
            Refresh
          </Button>
          <Button variant="ghost" size="sm" onClick={signOut}>
            Sign out
          </Button>
          <Button
            data-testid="new-workshop-button"
            size="sm"
            onClick={() => setCreateOpen(true)}
          >
            + New workshop
          </Button>
        </nav>
      </header>

      {listError && (
        <p
          role="alert"
          className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700"
        >
          {listError}
          <Button variant="secondary" size="sm" onClick={() => void refreshList()}>
            Retry
          </Button>
        </p>
      )}

      <section aria-labelledby="live-heading">
        <h2
          id="live-heading"
          className="mb-3 text-sm font-semibold tracking-wide text-stone-500 uppercase"
        >
          Live
        </h2>
        {list.length === 0 ? (
          <EmptyState
            icon="🧭"
            title="No workshops yet — create your first."
            hint="A workshop is one live session: milestones, a join link for the room, and a live dashboard."
            action={
              <Button onClick={() => setCreateOpen(true)}>+ New workshop</Button>
            }
          />
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {list.map((w) => (
              <WorkshopCard
                key={w.id}
                workshop={w}
                justCreated={w.id === justCreatedId}
              />
            ))}
          </div>
        )}
      </section>

      <section aria-label="Future workshop groups" className="mt-8 grid gap-4 sm:grid-cols-2">
        <StubCard
          title="Upcoming"
          description="Workshops scheduled with a start time will group here."
        />
        <StubCard
          title="Ended"
          description="Ended workshops will group here, browsable as read-only archives."
        />
      </section>

      <CreateWorkshopModal
        open={createOpen}
        adminKey={adminKey}
        onClose={() => setCreateOpen(false)}
        onCreated={onCreated}
      />
    </main>
  );
}
