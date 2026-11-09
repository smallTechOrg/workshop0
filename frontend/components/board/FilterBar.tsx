"use client";

import { useId, useMemo, useState } from "react";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/format";
import {
  OPPORTUNITY_TYPES,
  TYPE_LABELS,
  type BoardQuery,
  type BoardSort,
  type OpportunityType,
  type PublicTopic,
} from "@/lib/board";

// ---------------------------------------------------------------------------
// Type chips + sort
// ---------------------------------------------------------------------------

export function TypeAndSortBar({
  query,
  onTypeChange,
  onSortChange,
}: {
  query: BoardQuery;
  onTypeChange: (t: OpportunityType | null) => void;
  onSortChange: (s: BoardSort) => void;
}) {
  const sortId = useId();
  const options: { value: OpportunityType | null; label: string; testId: string }[] = [
    { value: null, label: "All", testId: "type-filter-all" },
    ...OPPORTUNITY_TYPES.map((t) => ({
      value: t,
      label: TYPE_LABELS[t],
      testId: `type-filter-${t}`,
    })),
  ];

  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div role="group" aria-label="Opportunity type" className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const active = query.type === o.value;
          return (
            <button
              key={o.testId}
              type="button"
              data-testid={o.testId}
              aria-pressed={active}
              onClick={() => onTypeChange(o.value)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-sm font-medium transition-colors",
                active
                  ? "border-brand-600 bg-brand-600 text-white shadow-sm"
                  : "border-stone-300 bg-white text-stone-700 hover:border-stone-400 hover:bg-stone-50",
              )}
            >
              {o.label}
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-2">
        <label htmlFor={sortId} className="text-sm text-stone-500">
          Sort
        </label>
        <select
          id={sortId}
          data-testid="sort-select"
          value={query.sort}
          onChange={(e) => onSortChange(e.target.value === "deadline" ? "deadline" : "newest")}
          className="rounded-lg border border-stone-300 bg-white py-1.5 pr-8 pl-3 text-sm font-medium text-stone-800 shadow-sm hover:border-stone-400"
        >
          <option value="newest">Newest</option>
          <option value="deadline">Closing soon</option>
        </select>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Topic chips grouped by category (multi-select = match any)
// ---------------------------------------------------------------------------

export type TopicsState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; topics: PublicTopic[] };

function groupByCategory(topics: PublicTopic[]): [string, PublicTopic[]][] {
  const groups = new Map<string, PublicTopic[]>();
  for (const t of topics) {
    const list = groups.get(t.category);
    if (list) list.push(t);
    else groups.set(t.category, [t]);
  }
  return [...groups.entries()];
}

export function TopicFilter({
  state,
  selected,
  onToggle,
  onClear,
  onRetry,
}: {
  state: TopicsState;
  selected: string[];
  onToggle: (slug: string) => void;
  onClear: () => void;
  onRetry: () => void;
}) {
  // Collapsible on small screens only; always expanded from `lg` up.
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const groups = useMemo(
    () => (state.kind === "ready" ? groupByCategory(state.topics) : []),
    [state],
  );

  return (
    <section
      aria-labelledby={`${panelId}-h`}
      className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 id={`${panelId}-h`} className="text-sm font-semibold text-stone-900">
          Topics
          {selected.length > 0 && (
            <span className="ml-1.5 rounded-full bg-brand-50 px-1.5 py-0.5 text-xs font-medium text-brand-700">
              {selected.length} selected
            </span>
          )}
        </h2>
        <div className="flex items-center gap-2">
          {selected.length > 0 && (
            <button
              type="button"
              onClick={onClear}
              className="text-xs font-medium text-stone-500 underline underline-offset-2 hover:text-stone-800"
            >
              Clear
            </button>
          )}
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => setOpen((v) => !v)}
            className="rounded-md px-2 py-1 text-xs font-medium text-brand-700 hover:bg-brand-50 lg:hidden"
          >
            {open ? "Hide" : "Show"}
          </button>
        </div>
      </div>
      <p className="mt-1 text-xs text-stone-500">Pick any — a listing matches if it has one of them.</p>

      <div id={panelId} className={cn("mt-3", open ? "block" : "hidden", "lg:block")}>
        {state.kind === "loading" && (
          <div className="space-y-4" aria-label="Loading topics">
            {[0, 1, 2].map((g) => (
              <div key={g}>
                <Skeleton className="h-3 w-24" />
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {[16, 20, 12, 24, 14].map((w, i) => (
                    <Skeleton key={i} className="h-7 rounded-full" style={{ width: `${w * 4}px` }} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {state.kind === "error" && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-800">
            <p>Couldn&apos;t load the topic list. {state.message}</p>
            <button
              type="button"
              onClick={onRetry}
              className="mt-1 font-medium underline underline-offset-2"
            >
              Try again
            </button>
          </div>
        )}

        {state.kind === "ready" && groups.length === 0 && (
          <p className="text-sm text-stone-500">No topics yet.</p>
        )}

        {state.kind === "ready" && groups.length > 0 && (
          <div className="space-y-4">
            {groups.map(([category, topics]) => (
              <div key={category}>
                <h3 className="text-[11px] font-semibold tracking-wide text-stone-400 uppercase">
                  {category}
                </h3>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {topics.map((t) => {
                    const active = selected.includes(t.slug);
                    const empty = t.open_count === 0;
                    return (
                      <button
                        key={t.slug}
                        type="button"
                        data-testid={`topic-filter-${t.slug}`}
                        aria-pressed={active}
                        onClick={() => onToggle(t.slug)}
                        className={cn(
                          "inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-left text-xs font-medium transition-colors",
                          active
                            ? "border-brand-600 bg-brand-600 text-white"
                            : empty
                              ? "border-stone-200 bg-stone-50 text-stone-400 hover:border-stone-300"
                              : "border-stone-300 bg-white text-stone-700 hover:border-stone-400 hover:bg-stone-50",
                        )}
                      >
                        <span className="min-w-0 break-words">{t.name}</span>
                        <span
                          className={cn(
                            "tabular-nums",
                            active ? "text-brand-100" : empty ? "text-stone-400" : "text-stone-500",
                          )}
                        >
                          {t.open_count}
                          <span className="sr-only"> open</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
