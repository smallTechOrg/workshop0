"use client";

/**
 * Public opportunity board — spec/capabilities.md C10.
 *
 * Filter state lives in the URL (`?type=&topic=&topic=&sort=&page=`) so a
 * filtered view is shareable and survives reload; the URL is the single source
 * of truth and every fetch is derived from it. `useSearchParams` sits inside
 * `<Suspense>` (static export requirement).
 */

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import { useNowTick } from "@/lib/format";
import {
  boardHref,
  boardQueryString,
  hasActiveFilters,
  listPublicOpportunities,
  listPublicTopics,
  parseBoardQuery,
  type BoardQuery,
  type PublicOpportunityPage,
} from "@/lib/board";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { BoardShell } from "@/components/board/BoardShell";
import { JoinNetworkCta } from "@/components/board/JoinNetworkCta";
import { OpportunityCard, OpportunityCardSkeleton } from "@/components/board/OpportunityCard";
import { TopicFilter, TypeAndSortBar, type TopicsState } from "@/components/board/FilterBar";
import { Pagination } from "@/components/board/Pagination";

type ListState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: PublicOpportunityPage };

function errorMessage(err: unknown): string {
  if (err instanceof ApiError && err.code === "network_error") {
    return "We couldn't reach the server — check your connection.";
  }
  return "Something went wrong on our side while loading opportunities.";
}

function CardGridSkeleton() {
  return (
    <div
      aria-busy="true"
      aria-label="Loading opportunities"
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
    >
      {Array.from({ length: 6 }, (_, i) => (
        <OpportunityCardSkeleton key={i} />
      ))}
    </div>
  );
}

function BoardHeader() {
  return (
    <section className="border-b border-stone-200 bg-gradient-to-b from-brand-50/70 to-stone-50">
      <div className="mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-5 px-4 py-10 sm:px-6 sm:py-12">
        <div className="max-w-2xl min-w-0">
          <p className="text-sm font-semibold tracking-wide text-brand-700 uppercase">
            For tech trainers
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-balance text-stone-900 sm:text-4xl">
            Opportunities from the smallTech partner network
          </h1>
          <p className="mt-3 text-lg text-stone-600">
            Workshops, engagements, roles and co-facilitation gigs from teams looking for
            trainers — browse what&apos;s open right now.
          </p>
        </div>
        <JoinNetworkCta />
      </div>
    </section>
  );
}

function BoardInner() {
  const router = useRouter();
  const params = useSearchParams();
  const now = useNowTick(60_000);

  // The URL is the source of truth; normalise it once per change.
  const query = useMemo(() => parseBoardQuery(params), [params]);
  const qs = boardQueryString(query);

  const [topics, setTopics] = useState<TopicsState>({ kind: "loading" });
  const [topicsAttempt, setTopicsAttempt] = useState(0);
  const [list, setList] = useState<ListState>({ kind: "loading" });
  const [listAttempt, setListAttempt] = useState(0);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.title = "Opportunities for trainers — Workshop0";
  }, []);

  useEffect(() => {
    let cancelled = false;
    setTopics({ kind: "loading" });
    listPublicTopics()
      .then((res) => {
        if (!cancelled) setTopics({ kind: "ready", topics: res.topics });
      })
      .catch((err) => {
        if (!cancelled) setTopics({ kind: "error", message: errorMessage(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [topicsAttempt]);

  useEffect(() => {
    let cancelled = false;
    setList({ kind: "loading" });
    listPublicOpportunities(parseBoardQuery(new URLSearchParams(qs)))
      .then((data) => {
        if (!cancelled) setList({ kind: "ready", data });
      })
      .catch((err) => {
        if (!cancelled) setList({ kind: "error", message: errorMessage(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [qs, listAttempt]);

  const navigate = useCallback(
    (next: BoardQuery, mode: "replace" | "push" = "replace") => {
      const href = boardHref(boardQueryString(next));
      if (mode === "push") router.push(href, { scroll: false });
      else router.replace(href, { scroll: false });
    },
    [router],
  );

  const goToPage = (page: number) => {
    navigate({ ...query, page }, "push");
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const toggleTopic = (slug: string) => {
    const topicsNext = query.topics.includes(slug)
      ? query.topics.filter((t) => t !== slug)
      : [...query.topics, slug];
    navigate({ ...query, topics: topicsNext, page: 1 });
  };

  const clearFilters = () => navigate({ type: null, topics: [], sort: query.sort, page: 1 });

  const filtered = hasActiveFilters(query);

  let results: React.ReactNode;
  if (list.kind === "loading") {
    results = <CardGridSkeleton />;
  } else if (list.kind === "error") {
    results = (
      <div
        role="alert"
        className="flex flex-col items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center"
      >
        <p className="font-medium text-red-800">Couldn&apos;t load opportunities</p>
        <p className="max-w-sm text-sm text-red-700">{list.message} Please try again.</p>
        <Button variant="secondary" onClick={() => setListAttempt((n) => n + 1)}>
          Retry
        </Button>
      </div>
    );
  } else {
    const { data } = list;
    if (data.opportunities.length === 0) {
      if (data.total > 0) {
        results = (
          <EmptyState
            icon="📄"
            title="There's nothing on this page"
            hint={`The results end at page ${data.total_pages}.`}
            action={
              <Button variant="secondary" onClick={() => navigate({ ...query, page: 1 })}>
                Go to the first page
              </Button>
            }
          />
        );
      } else if (filtered) {
        results = (
          <div data-testid="board-empty">
            <EmptyState
              icon="🔎"
              title="Nothing matches these filters"
              hint="Try another type or fewer topics — or clear the filters to see everything that's open."
              action={
                <Button variant="secondary" onClick={clearFilters}>
                  Clear filters
                </Button>
              }
            />
          </div>
        );
      } else {
        results = (
          <div data-testid="board-empty">
            <EmptyState
              icon="🌱"
              title="No open opportunities right now — check back soon."
              hint="New listings from the smallTech partner network appear here as soon as they're published."
            />
          </div>
        );
      }
    } else {
      results = (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {data.opportunities.map((o) => (
              <OpportunityCard key={o.id} opportunity={o} boardQs={qs} now={now} />
            ))}
          </div>
          <Pagination page={data.page} totalPages={data.total_pages} onPage={goToPage} />
        </>
      );
    }
  }

  const total = list.kind === "ready" ? list.data.total : null;

  return (
    <main data-testid="board-page">
      <BoardHeader />
      <div className="mx-auto grid max-w-6xl gap-6 px-4 py-8 sm:px-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <aside className="min-w-0 lg:sticky lg:top-4 lg:self-start">
          <TopicFilter
            state={topics}
            selected={query.topics}
            onToggle={toggleTopic}
            onClear={() => navigate({ ...query, topics: [], page: 1 })}
            onRetry={() => setTopicsAttempt((n) => n + 1)}
          />
        </aside>

        <div ref={resultsRef} className="min-w-0 scroll-mt-4">
          <TypeAndSortBar
            query={query}
            onTypeChange={(type) => navigate({ ...query, type, page: 1 })}
            onSortChange={(sort) => navigate({ ...query, sort, page: 1 })}
          />
          <div className="mt-4 mb-4 flex min-h-6 flex-wrap items-center justify-between gap-2 text-sm text-stone-500">
            <p aria-live="polite">
              {total === null || total === 0
                ? "\u00a0"
                : total === 1
                  ? `1 open opportunity${filtered ? " matches your filters" : ""}`
                  : `${total} open opportunities${filtered ? " match your filters" : ""}`}
            </p>
            {filtered && (
              <button
                type="button"
                onClick={clearFilters}
                className="font-medium text-stone-600 underline underline-offset-2 hover:text-stone-900"
              >
                Clear filters
              </button>
            )}
          </div>
          {results}
        </div>
      </div>
    </main>
  );
}

function BoardFallback() {
  return (
    <main data-testid="board-page">
      <BoardHeader />
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        <CardGridSkeleton />
      </div>
    </main>
  );
}

export default function OpportunitiesBoardPage() {
  return (
    <BoardShell>
      <Suspense fallback={<BoardFallback />}>
        <BoardInner />
      </Suspense>
    </BoardShell>
  );
}
