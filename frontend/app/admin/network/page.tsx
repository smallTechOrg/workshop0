"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import {
  downloadCsv,
  isAuthError,
  listPoolTopics,
  listTrainers,
  type PoolFilters,
  type PoolPage,
  type PoolTopic,
} from "@/lib/adminNetwork";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { AdminGate, useAdmin } from "@/components/admin/AdminGate";
import { NetworkHeader } from "@/components/admin/network/NetworkHeader";
import { PoolTable } from "@/components/admin/network/PoolTable";
import { PoolFiltersBar, type PoolFilterValues } from "@/components/admin/network/PoolFiltersBar";
import { InvitesPanel } from "@/components/admin/network/InvitesPanel";
import { SpendCard } from "@/components/admin/network/SpendCard";
import { Card } from "@/components/ui/Card";

const PAGE_SIZE = 25;

function pick<T extends string>(v: string | null, allowed: T[]): T | "" {
  return v && (allowed as string[]).includes(v) ? (v as T) : "";
}

function isoDate(v: string | null): string {
  return v && /^\d{4}-\d{2}-\d{2}$/.test(v) ? v : "";
}

function readFilters(params: URLSearchParams): PoolFilterValues & { page: number } {
  const verified = params.get("verified");
  return {
    q: params.get("q") ?? "",
    topic: params.getAll("topic").filter(Boolean),
    verified: verified === "true" || verified === "false" ? verified : "",
    tag: params.get("tag") ?? "",
    min_level: pick(params.get("min_level"), ["intermediate", "advanced", "expert"]),
    budget_max: (params.get("budget_max") ?? "").replace(/\D/g, ""),
    currency: pick(params.get("currency"), ["INR", "USD"]),
    unit: pick(params.get("unit"), ["hour", "day", "course", "month"]),
    available_start: isoDate(params.get("available_start")),
    available_end: isoDate(params.get("available_end")),
    location_mode: pick(params.get("location_mode"), ["remote", "onsite", "hybrid"]),
    city: params.get("city") ?? "",
    page: Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1),
  };
}

function toQuery(v: PoolFilterValues & { page: number }): string {
  const sp = new URLSearchParams();
  if (v.q.trim()) sp.set("q", v.q.trim());
  for (const t of v.topic) sp.append("topic", t);
  if (v.verified) sp.set("verified", v.verified);
  if (v.tag.trim()) sp.set("tag", v.tag.trim());
  if (v.min_level) sp.set("min_level", v.min_level);
  if (v.budget_max) sp.set("budget_max", v.budget_max);
  if (v.currency) sp.set("currency", v.currency);
  if (v.unit) sp.set("unit", v.unit);
  if (v.available_start) sp.set("available_start", v.available_start);
  if (v.available_end) sp.set("available_end", v.available_end);
  if (v.location_mode) sp.set("location_mode", v.location_mode);
  if (v.city.trim()) sp.set("city", v.city.trim());
  if (v.page > 1) sp.set("page", String(v.page));
  const s = sp.toString();
  return s ? `?${s}` : "";
}

function TableSkeleton() {
  return (
    <div className="space-y-2" aria-label="Loading trainers">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-16" />
      ))}
    </div>
  );
}

function Pool() {
  const { adminKey, onUnauthorized } = useAdmin();
  const toast = useToast();
  const router = useRouter();
  const params = useSearchParams();
  const values = useMemo(() => readFilters(new URLSearchParams(params.toString())), [params]);
  const filterKey = toQuery(values);

  const [data, setData] = useState<PoolPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [topics, setTopics] = useState<PoolTopic[] | null>(null);
  const [exporting, setExporting] = useState(false);

  const apiFilters: PoolFilters = useMemo(
    () => ({
      q: values.q,
      topic: values.topic,
      verified: values.verified || undefined,
      tag: values.tag,
      min_level: values.min_level || undefined,
      // Budget needs currency + unit together (server 422 otherwise).
      budget_max: values.budget_max && values.currency && values.unit ? Number(values.budget_max) : undefined,
      currency: values.budget_max && values.currency && values.unit ? values.currency : undefined,
      unit: values.budget_max && values.currency && values.unit ? values.unit : undefined,
      available_start: values.available_start && values.available_end && values.available_end < values.available_start ? undefined : values.available_start || undefined,
      available_end: values.available_start && values.available_end && values.available_end < values.available_start ? undefined : values.available_end || undefined,
      location_mode: values.location_mode || undefined,
      city: values.city,
      page: values.page,
      page_size: PAGE_SIZE,
    }),
    // filterKey captures every field of `values`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filterKey],
  );

  const setFilters = useCallback(
    (next: Partial<PoolFilterValues & { page: number }>) => {
      const merged = { ...values, page: 1, ...next };
      router.replace(`/admin/network/${toQuery(merged)}`, { scroll: false });
    },
    [values, router],
  );

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await listTrainers(adminKey, apiFilters));
    } catch (err) {
      if (isAuthError(err)) {
        onUnauthorized();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Couldn't load the trainer pool.");
    } finally {
      setLoading(false);
    }
  }, [adminKey, apiFilters, onUnauthorized]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    listPoolTopics(adminKey)
      .then((t) => {
        if (!cancelled) setTopics(t);
      })
      .catch((err) => {
        if (cancelled) return;
        if (isAuthError(err)) onUnauthorized();
        else setTopics([]);
      });
    return () => {
      cancelled = true;
    };
  }, [adminKey, onUnauthorized]);

  const exportCsv = async () => {
    setExporting(true);
    try {
      await downloadCsv(adminKey, apiFilters);
    } catch (err) {
      if (isAuthError(err)) {
        onUnauthorized();
        return;
      }
      toast.show(err instanceof ApiError ? err.message : "Couldn't export the CSV.", "error");
    } finally {
      setExporting(false);
    }
  };

  const hasFilters = Boolean(values.q.trim() || values.topic.length || values.verified || values.tag.trim() ||
      values.min_level || values.budget_max || values.currency || values.unit || values.available_start ||
      values.available_end || values.location_mode || values.city.trim());
  const totalPages = data?.total_pages ?? 0;

  return (
    <main className="mx-auto max-w-7xl px-4 py-6">
      <NetworkHeader />

      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-stone-900">Trainer network</h1>
          <p className="mt-1 text-sm text-stone-500">
            Everyone who has joined the network. Rates, emails, notes and tags are visible to admins
            only.
          </p>
        </div>
        <Button variant="secondary" onClick={() => void exportCsv()} loading={exporting}>
          Export CSV
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 space-y-4">
          <PoolFiltersBar values={values} topics={topics} onChange={setFilters} />

          {error ? (
            <EmptyState
              icon="⚠️"
              title="Couldn't load the trainer pool"
              hint={error}
              action={
                <Button variant="secondary" size="sm" onClick={() => void load()}>
                  Retry
                </Button>
              }
            />
          ) : loading && !data ? (
            <TableSkeleton />
          ) : data && data.trainers.length === 0 ? (
            hasFilters ? (
              <EmptyState
                icon="🔍"
                title="No trainers match these filters"
                hint="Try a broader search, or clear the filters."
                action={
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => router.replace("/admin/network/", { scroll: false })}
                  >
                    Clear filters
                  </Button>
                }
              />
            ) : (
              <EmptyState
                icon="🧑‍🏫"
                title="No trainers yet"
                hint="Trainers appear here once they join from the Opportunity Board or an invite link. Create an invite on the right to get started."
              />
            )
          ) : data ? (
            <div className={loading ? "opacity-60 transition-opacity" : undefined}>
              <p className="mb-2 text-xs text-stone-500" data-testid="pool-total">
                {data.total.toLocaleString()} trainer{data.total === 1 ? "" : "s"}
                {hasFilters ? " match" : ""}
              </p>
              <PoolTable rows={data.trainers} />
              {totalPages > 1 && (
                <nav
                  aria-label="Pool pages"
                  className="mt-3 flex items-center justify-between gap-2 text-sm text-stone-600"
                >
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={values.page <= 1 || loading}
                    onClick={() => setFilters({ page: values.page - 1 })}
                  >
                    Previous
                  </Button>
                  <span>
                    Page {data.page} of {totalPages}
                  </span>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={values.page >= totalPages || loading}
                    onClick={() => setFilters({ page: values.page + 1 })}
                  >
                    Next
                  </Button>
                </nav>
              )}
            </div>
          ) : null}
        </div>

        <aside className="space-y-4">
          <SpendCard />
          <InvitesPanel />
          <Card className="p-4" data-testid="suggest-hint">
            <h2 className="text-sm font-semibold text-stone-900">Suggested trainers</h2>
            <p className="mt-1 text-xs text-stone-500">
              Open a saved listing in the opportunity editor and choose Suggest trainers to get a
              ranked shortlist with reasons.
            </p>
          </Card>
        </aside>
      </div>
    </main>
  );
}

export default function AdminNetworkPage() {
  return (
    <AdminGate purpose="to manage the trainer network">
      <Suspense fallback={<main className="mx-auto max-w-7xl px-4 py-6"><TableSkeleton /></main>}>
        <Pool />
      </Suspense>
    </AdminGate>
  );
}
