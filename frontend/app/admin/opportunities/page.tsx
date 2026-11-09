"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/format";
import {
  adminListOpportunities,
  type AdminOpportunityList,
  type OpportunityStatus,
} from "@/lib/adminBoard";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { AdminGate, useAdmin } from "@/components/admin/AdminGate";
import { AdminHeader } from "@/components/admin/AdminHeader";
import { OpportunitiesTable } from "@/components/admin/OpportunitiesTable";

const PAGE_SIZE = 25;

type Tab = "all" | OpportunityStatus;
const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "All" },
  { key: "draft", label: "Draft" },
  { key: "open", label: "Open" },
  { key: "expired", label: "Expired" },
  { key: "closed", label: "Closed" },
];

function isTab(v: string | null): v is Tab {
  return TABS.some((t) => t.key === v);
}

function ListSkeleton() {
  return (
    <div className="space-y-2" aria-label="Loading opportunities">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-16" />
      ))}
    </div>
  );
}

function OpportunitiesList() {
  const { adminKey, onUnauthorized } = useAdmin();
  const router = useRouter();
  const params = useSearchParams();

  const statusParam = params.get("status");
  const tab: Tab = isTab(statusParam) ? statusParam : "all";
  const q = params.get("q") ?? "";
  const page = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);

  const [search, setSearch] = useState(q);
  const [data, setData] = useState<AdminOpportunityList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const setQuery = useCallback(
    (next: { status?: Tab; q?: string; page?: number }) => {
      const sp = new URLSearchParams();
      const s = next.status ?? tab;
      const qq = next.q ?? q;
      const p = next.page ?? 1;
      if (s !== "all") sp.set("status", s);
      if (qq.trim()) sp.set("q", qq.trim());
      if (p > 1) sp.set("page", String(p));
      const str = sp.toString();
      router.replace(`/admin/opportunities/${str ? `?${str}` : ""}`, { scroll: false });
    },
    [router, tab, q],
  );

  // Debounce the search box into the URL.
  useEffect(() => {
    if (search.trim() === q.trim()) return;
    const id = setTimeout(() => setQuery({ q: search, page: 1 }), 300);
    return () => clearTimeout(id);
  }, [search, q, setQuery]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await adminListOpportunities(adminKey, {
        status: tab === "all" ? undefined : tab,
        q: q.trim() || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setData(res);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setError(
        err instanceof ApiError && err.status !== 0
          ? `Couldn't load opportunities — ${err.message}`
          : "Couldn't load opportunities — check your connection and try again.",
      );
    } finally {
      setLoading(false);
    }
  }, [adminKey, onUnauthorized, tab, q, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = data?.counts;
  const countFor = (t: Tab) =>
    counts
      ? t === "all"
        ? counts.draft + counts.open + counts.expired + counts.closed
        : counts[t]
      : null;
  const totalAll = countFor("all");
  const rows = data?.opportunities ?? [];

  return (
    <main data-testid="admin-opportunities-page" className="mx-auto max-w-6xl px-4 py-8">
      <AdminHeader current="opportunities" />

      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-stone-900">Opportunities</h1>
          <p className="mt-1 text-sm text-stone-500">
            Listings on the public board. Internal partner names and notes stay admin-only.{" "}
            <Link href="/admin/topics/" className="font-medium text-brand-700 hover:underline">
              Manage topics
            </Link>
          </p>
        </div>
        <Link
          href="/admin/opportunities/edit/"
          data-testid="new-opportunity-button"
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2 font-medium text-white shadow-sm transition-colors hover:bg-brand-700"
        >
          + New opportunity
        </Link>
      </div>

      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div
          role="tablist"
          aria-label="Filter by status"
          className="flex flex-wrap gap-1 rounded-xl border border-stone-200 bg-stone-50 p-1"
        >
          {TABS.map((t) => {
            const active = t.key === tab;
            const c = countFor(t.key);
            return (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={active}
                data-testid={`status-tab-${t.key}`}
                onClick={() => setQuery({ status: t.key, page: 1 })}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  active
                    ? "bg-white text-stone-900 shadow-sm"
                    : "text-stone-600 hover:bg-white/70 hover:text-stone-900",
                )}
              >
                {t.label}
                <span
                  className={cn(
                    "rounded-full px-1.5 text-xs tabular-nums",
                    active ? "bg-brand-100 text-brand-700" : "bg-stone-200 text-stone-600",
                  )}
                >
                  {c ?? "–"}
                </span>
              </button>
            );
          })}
        </div>
        <div className="relative w-full md:w-80">
          <label htmlFor="opp-search" className="sr-only">
            Search opportunities
          </label>
          <input
            id="opp-search"
            data-testid="opp-search-input"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title or partner…"
            className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-stone-900 placeholder:text-stone-400 focus:border-brand-500"
          />
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700"
        >
          {error}
          <Button variant="secondary" size="sm" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      )}

      {loading && !data ? (
        <ListSkeleton />
      ) : rows.length === 0 && !error ? (
        totalAll === 0 ? (
          <EmptyState
            icon="📌"
            title="No opportunities yet — post the first one."
            hint="Write the public details, keep the real partner name internal, and publish it to the board."
            action={
              <Link
                href="/admin/opportunities/edit/"
                className="inline-flex items-center rounded-lg bg-brand-600 px-4 py-2 font-medium text-white hover:bg-brand-700"
              >
                + New opportunity
              </Link>
            }
          />
        ) : (
          <EmptyState
            icon="🔎"
            title="Nothing matches this view."
            hint={q ? `No ${tab === "all" ? "" : `${tab} `}opportunities match “${q}”.` : "No opportunities in this status."}
            action={
              <Button
                variant="secondary"
                onClick={() => {
                  setSearch("");
                  setQuery({ status: "all", q: "", page: 1 });
                }}
              >
                Show all
              </Button>
            }
          />
        )
      ) : (
        <div className={cn(loading && "opacity-60 transition-opacity")}>
          <OpportunitiesTable rows={rows} />
        </div>
      )}

      {data && data.total_pages > 1 && (
        <nav
          aria-label="Pagination"
          className="mt-4 flex items-center justify-between gap-3 text-sm text-stone-600"
        >
          <Button
            variant="secondary"
            size="sm"
            disabled={page <= 1 || loading}
            onClick={() => setQuery({ page: page - 1 })}
          >
            ← Previous
          </Button>
          <span data-testid="admin-pagination-status">
            Page {data.page} of {data.total_pages} · {data.total} total
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={page >= data.total_pages || loading}
            onClick={() => setQuery({ page: page + 1 })}
          >
            Next →
          </Button>
        </nav>
      )}
    </main>
  );
}

export default function AdminOpportunitiesPage() {
  return (
    <AdminGate purpose="to manage opportunities">
      <Suspense fallback={<main className="mx-auto max-w-6xl px-4 py-8"><ListSkeleton /></main>}>
        <OpportunitiesList />
      </Suspense>
    </AdminGate>
  );
}
