"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import {
  adminGetOpportunity,
  adminListTopics,
  type ActivityItem,
  type AdminOpportunity,
  type AdminTopic,
} from "@/lib/adminBoard";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { AdminGate, useAdmin } from "@/components/admin/AdminGate";
import { AdminHeader } from "@/components/admin/AdminHeader";
import { OpportunityEditor } from "@/components/admin/OpportunityEditor";

function EditorSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]" aria-label="Loading editor">
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-24" />
        <Skeleton className="h-48" />
        <Skeleton className="h-32" />
      </div>
      <div className="space-y-4">
        <Skeleton className="h-40" />
        <Skeleton className="h-56" />
      </div>
    </div>
  );
}

type Loaded = { opportunity: AdminOpportunity | null; activity: ActivityItem[] };

function EditorPage() {
  const { adminKey, onUnauthorized } = useAdmin();
  const router = useRouter();
  const params = useSearchParams();
  const rawId = params.get("id");
  const id = rawId && /^\d+$/.test(rawId) ? Number(rawId) : null;
  const badId = rawId !== null && rawId !== "" && id === null;

  const [topics, setTopics] = useState<AdminTopic[] | null>(null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Set right after a create so the URL change refreshes silently. */
  const silentFor = useRef<number | null>(null);

  const load = useCallback(
    async (silent: boolean) => {
      if (!silent) {
        setError(null);
        setNotFound(false);
        setLoaded(null);
      }
      try {
        const [t, o] = await Promise.all([
          adminListTopics(adminKey),
          id !== null ? adminGetOpportunity(adminKey, id) : Promise.resolve(null),
        ]);
        setTopics(t.topics);
        setLoaded(o ? { opportunity: o.opportunity, activity: o.activity } : { opportunity: null, activity: [] });
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          onUnauthorized();
          return;
        }
        if (silent) return; // keep what's on screen; the next save refreshes again
        if (err instanceof ApiError && err.code === "not_found") {
          setNotFound(true);
          return;
        }
        setError(
          err instanceof ApiError && err.status !== 0
            ? `Couldn't load the editor — ${err.message}`
            : "Couldn't load the editor — check your connection and try again.",
        );
      }
    },
    [adminKey, onUnauthorized, id],
  );

  useEffect(() => {
    if (badId) return;
    const silent = id !== null && silentFor.current === id;
    silentFor.current = null;
    void load(silent);
  }, [load, id, badId]);

  const onSaved = (opp: AdminOpportunity, created: boolean) => {
    setLoaded((prev) => ({ opportunity: opp, activity: prev?.activity ?? [] }));
    if (created) {
      silentFor.current = opp.id;
      router.replace(`/admin/opportunities/edit/?id=${opp.id}`, { scroll: false });
    } else {
      void load(true); // refresh Activity
    }
  };

  useEffect(() => {
    const title = loaded?.opportunity?.title;
    document.title = title ? `${title} · Opportunities · Workshop0` : "New opportunity · Workshop0";
  }, [loaded?.opportunity?.title]);

  const heading = loaded?.opportunity ? "Edit opportunity" : id === null && !badId ? "New opportunity" : "Opportunity";

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <AdminHeader current="opportunities" />
      <div className="mb-5">
        <Link
          href="/admin/opportunities/"
          className="text-sm font-medium text-stone-500 hover:text-stone-800"
        >
          ← All opportunities
        </Link>
        <h1 className="mt-1 text-2xl font-semibold break-words text-stone-900">{heading}</h1>
      </div>

      {badId || notFound ? (
        <EmptyState
          icon="🗂️"
          title="This opportunity doesn't exist."
          hint="It may have been mistyped — opportunities are never deleted, so check the list."
          action={
            <Link
              href="/admin/opportunities/"
              className="inline-flex items-center rounded-lg bg-brand-600 px-4 py-2 font-medium text-white hover:bg-brand-700"
            >
              Back to opportunities
            </Link>
          }
        />
      ) : error ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
          <Button variant="secondary" size="sm" onClick={() => void load(false)}>
            Retry
          </Button>
        </div>
      ) : !loaded || !topics ? (
        <EditorSkeleton />
      ) : (
        <OpportunityEditor
          key={loaded.opportunity ? `opp-${loaded.opportunity.id}` : "new"}
          opportunity={loaded.opportunity}
          activity={loaded.activity}
          topics={topics}
          onSaved={onSaved}
        />
      )}
    </main>
  );
}

export default function AdminOpportunityEditPage() {
  return (
    <AdminGate purpose="to manage opportunities">
      <Suspense
        fallback={
          <main className="mx-auto max-w-6xl px-4 py-8">
            <EditorSkeleton />
          </main>
        }
      >
        <EditorPage />
      </Suspense>
    </AdminGate>
  );
}
