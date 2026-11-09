"use client";

/**
 * Public listing page — spec/capabilities.md C10. `/app/opportunities/view/?id=<id>`
 * (pretty `/opportunities/<id>`). Open, expired and closed listings render;
 * drafts and unknown ids get a friendly not-found state.
 */

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import { formatCompensation } from "@/lib/compensation";
import { useNowTick } from "@/lib/format";
import { locationDetailLabel } from "@/lib/locations";
import {
  boardHref,
  dateRangeLabel,
  getPublicOpportunity,
  partnerName,
  sanitizeFromParam,
  type PublicOpportunityDetail,
} from "@/lib/board";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Markdown } from "@/components/ui/Markdown";
import { Skeleton } from "@/components/ui/Skeleton";
import { BoardShell } from "@/components/board/BoardShell";
import { ListingSidebar } from "@/components/board/ListingSidebar";
import { TypePill } from "@/components/board/OpportunityCard";

type LoadState =
  | { kind: "loading" }
  | { kind: "not_found" }
  | { kind: "error"; message: string }
  | { kind: "ready"; opportunity: PublicOpportunityDetail };

function parseId(raw: string | null): number | null {
  if (!raw || !/^\d{1,12}$/.test(raw.trim())) return null;
  const n = Number(raw.trim());
  return n >= 1 ? n : null;
}

function BackLink({ fromQs }: { fromQs: string }) {
  return (
    <Link
      href={boardHref(fromQs)}
      className="inline-flex items-center gap-1 text-sm font-medium text-stone-500 hover:text-stone-900"
    >
      <span aria-hidden="true">←</span> All opportunities
    </Link>
  );
}

function ListingSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading opportunity" className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="mt-6 h-5 w-24 rounded-full" />
      <Skeleton className="mt-3 h-9 w-3/4" />
      <Skeleton className="mt-3 h-4 w-48" />
      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-4 w-2/3" />
        </div>
        <Skeleton className="h-48 w-full" />
      </div>
    </div>
  );
}

function NotFound({ fromQs }: { fromQs: string }) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      <Card data-testid="opportunity-not-found" className="mx-auto max-w-lg p-8 text-center">
        <p aria-hidden="true" className="text-3xl">
          🧭
        </p>
        <h1 className="mt-2 text-xl font-semibold text-stone-900">
          This opportunity isn&apos;t available — it may have been removed.
        </h1>
        <p className="mt-2 text-stone-500">
          The link may be mistyped, or the listing isn&apos;t public. Have a look at what&apos;s open
          instead.
        </p>
        <Link
          href={boardHref(fromQs)}
          className="mt-5 inline-flex items-center justify-center rounded-lg bg-brand-600 px-4 py-2 font-medium text-white shadow-sm hover:bg-brand-700"
        >
          Browse open opportunities
        </Link>
      </Card>
    </div>
  );
}

function MetaItem({ label, value, testId }: { label: string; value: string; testId?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs font-medium tracking-wide text-stone-400 uppercase">{label}</dt>
      <dd data-testid={testId} className="mt-0.5 break-words text-stone-800">
        {value}
      </dd>
    </div>
  );
}

function ListingInner() {
  const params = useSearchParams();
  const id = parseId(params.get("id"));
  const fromQs = sanitizeFromParam(params.get("from"));
  const now = useNowTick(30_000);

  const [state, setState] = useState<LoadState>(id === null ? { kind: "not_found" } : { kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (id === null) {
      setState({ kind: "not_found" });
      return;
    }
    let cancelled = false;
    setState({ kind: "loading" });
    getPublicOpportunity(id)
      .then((res) => {
        if (!cancelled) setState({ kind: "ready", opportunity: res.opportunity });
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setState({ kind: "not_found" });
        } else {
          setState({
            kind: "error",
            message:
              err instanceof ApiError && err.code === "network_error"
                ? "We couldn't reach the server — check your connection."
                : "Something went wrong on our side while loading this opportunity.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  useEffect(() => {
    if (state.kind === "ready") document.title = `${state.opportunity.title} — Workshop0`;
    else if (state.kind === "not_found") document.title = "Opportunity not available — Workshop0";
    else document.title = "Opportunity — Workshop0";
  }, [state]);

  if (state.kind === "loading") return <ListingSkeleton />;
  if (state.kind === "not_found") return <NotFound fromQs={fromQs} />;
  if (state.kind === "error") {
    return (
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <Card role="alert" className="mx-auto max-w-lg p-8 text-center">
          <h1 className="text-xl font-semibold text-stone-900">Couldn&apos;t load this opportunity</h1>
          <p className="mt-2 text-stone-500">{state.message} Please try again.</p>
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            <Button onClick={() => setAttempt((n) => n + 1)}>Retry</Button>
            <Link
              href={boardHref(fromQs)}
              className="inline-flex items-center justify-center rounded-lg border border-stone-300 bg-white px-4 py-2 font-medium text-stone-800 shadow-sm hover:bg-stone-50"
            >
              Back to the board
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  const o = state.opportunity;
  const dates = dateRangeLabel(o.starts_on, o.ends_on);
  const compensation = formatCompensation(o);
  const meta: { label: string; value: string; testId?: string }[] = [
    { label: "Location", value: locationDetailLabel(o), testId: "opportunity-location" },
    ...(dates ? [{ label: "Dates", value: dates }] : []),
    ...(o.duration_text ? [{ label: "Duration", value: o.duration_text }] : []),
    ...(compensation
      ? [{ label: "Compensation", value: compensation, testId: "opportunity-compensation" }]
      : []),
  ];

  return (
    <article data-testid="opportunity-detail" className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <BackLink fromQs={fromQs} />

      <header className="mt-6">
        <TypePill type={o.type} />
        <h1
          data-testid="opportunity-title"
          className="mt-3 text-3xl font-semibold tracking-tight break-words text-balance text-stone-900 sm:text-4xl"
        >
          {o.title}
        </h1>
        <p className="mt-2 text-lg break-words text-stone-600">{partnerName(o)}</p>
      </header>

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <aside className="min-w-0 lg:sticky lg:top-4 lg:order-last lg:self-start">
          <ListingSidebar opportunity={o} now={now} />
        </aside>

        <div className="min-w-0 space-y-6">
          <Card className="p-5">
            <p className="break-words text-stone-700">{o.summary}</p>
            <dl className="mt-5 grid gap-4 border-t border-stone-100 pt-5 sm:grid-cols-2">
              {meta.map((m) => (
                <MetaItem key={m.label} label={m.label} value={m.value} testId={m.testId} />
              ))}
            </dl>
            {o.topics.length > 0 && (
              <div className="mt-5 border-t border-stone-100 pt-5">
                <h2 className="text-xs font-medium tracking-wide text-stone-400 uppercase">Topics</h2>
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {o.topics.map((t) => (
                    <li key={t.slug}>
                      <Link
                        href={boardHref(`topic=${encodeURIComponent(t.slug)}`)}
                        className="inline-block rounded-md bg-stone-100 px-2 py-0.5 text-sm font-medium text-stone-700 hover:bg-brand-50 hover:text-brand-700"
                      >
                        {t.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          {o.description_md.trim() !== "" && (
            <section aria-label="Description" className="min-w-0">
              <Card className="p-5 sm:p-6">
                <Markdown>{o.description_md}</Markdown>
              </Card>
            </section>
          )}
        </div>
      </div>
    </article>
  );
}

export default function OpportunityListingPage() {
  return (
    <BoardShell>
      <Suspense fallback={<ListingSkeleton />}>
        <ListingInner />
      </Suspense>
    </BoardShell>
  );
}
