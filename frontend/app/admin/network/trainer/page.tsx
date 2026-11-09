"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import { getTrainer, isAuthError, type TrainerDetail } from "@/lib/adminNetwork";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { AdminGate, useAdmin } from "@/components/admin/AdminGate";
import { NetworkHeader } from "@/components/admin/network/NetworkHeader";
import { TrainerSummary } from "@/components/admin/network/TrainerSummary";
import { TrainerProfile } from "@/components/admin/network/TrainerProfile";
import { TagsEditor } from "@/components/admin/network/TagsEditor";
import { NotesPanel } from "@/components/admin/network/NotesPanel";
import { TrainerActivityList } from "@/components/admin/network/TrainerActivity";

function parseId(raw: string | null): number | null {
  if (!raw || !/^\d+$/.test(raw)) return null;
  const n = Number.parseInt(raw, 10);
  return n > 0 ? n : null;
}

function DetailSkeleton() {
  return (
    <div className="space-y-4" aria-label="Loading trainer">
      <Skeleton className="h-40" />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <Skeleton className="h-80" />
        <div className="space-y-4">
          <Skeleton className="h-32" />
          <Skeleton className="h-40" />
        </div>
      </div>
    </div>
  );
}

const backLink = (
  <Link
    href="/admin/network/"
    className="mb-4 inline-flex items-center gap-1 text-sm text-stone-500 hover:text-stone-800"
  >
    <span aria-hidden="true">←</span> Trainer network
  </Link>
);

function Trainer() {
  const { adminKey, onUnauthorized } = useAdmin();
  const params = useSearchParams();
  const id = parseId(params.get("id"));

  const [detail, setDetail] = useState<TrainerDetail | null>(null);
  const [error, setError] = useState<{ message: string; notFound: boolean } | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(
    async (quiet = false) => {
      if (id === null) return;
      if (!quiet) {
        setLoading(true);
        setError(null);
      }
      try {
        setDetail(await getTrainer(adminKey, id));
        setError(null);
      } catch (err) {
        if (isAuthError(err)) {
          onUnauthorized();
          return;
        }
        if (quiet) return; // a background refresh failing keeps the current view
        setError({
          message: err instanceof ApiError ? err.message : "Couldn't load this trainer.",
          notFound: err instanceof ApiError && err.status === 404,
        });
      } finally {
        if (!quiet) setLoading(false);
      }
    },
    [adminKey, id, onUnauthorized],
  );

  useEffect(() => {
    void load();
  }, [load]);

  // Refresh activity (and anything else server-derived) after a write.
  const refresh = () => void load(true);

  let body: React.ReactNode;
  if (id === null) {
    body = (
      <EmptyState
        icon="🔎"
        title="No trainer selected"
        hint="Open a trainer from the Trainer network list."
        action={
          <Link href="/admin/network/" className="text-sm font-medium text-brand-700 hover:underline">
            Go to the trainer network
          </Link>
        }
      />
    );
  } else if (error) {
    body = (
      <EmptyState
        icon={error.notFound ? "🔎" : "⚠️"}
        title={error.notFound ? "Trainer not found" : "Couldn't load this trainer"}
        hint={error.message}
        action={
          error.notFound ? (
            <Link href="/admin/network/" className="text-sm font-medium text-brand-700 hover:underline">
              Back to the trainer network
            </Link>
          ) : (
            <Button variant="secondary" size="sm" onClick={() => void load()}>
              Retry
            </Button>
          )
        }
      />
    );
  } else if (loading || !detail) {
    body = <DetailSkeleton />;
  } else {
    body = (
      <div className="space-y-4">
        <TrainerSummary detail={detail} onUpdated={setDetail} onDownloaded={refresh} />
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <TrainerProfile trainer={detail.trainer} />
          <div className="space-y-4">
            <TagsEditor
              trainerId={detail.trainer.id}
              tags={detail.tags}
              onSaved={(tags) => {
                setDetail((d) => (d ? { ...d, tags, trainer: { ...d.trainer, tags } } : d));
                refresh();
              }}
            />
            <NotesPanel
              trainerId={detail.trainer.id}
              notes={detail.notes}
              onSaved={(notes) => {
                setDetail((d) => (d ? { ...d, notes } : d));
                refresh();
              }}
            />
            <TrainerActivityList items={detail.activity} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <NetworkHeader />
      {backLink}
      {body}
    </main>
  );
}

export default function AdminTrainerPage() {
  return (
    <AdminGate purpose="to manage the trainer network">
      <Suspense
        fallback={
          <main className="mx-auto max-w-7xl px-4 py-6">
            <DetailSkeleton />
          </main>
        }
      >
        <Trainer />
      </Suspense>
    </AdminGate>
  );
}
