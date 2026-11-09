"use client";

import { useMemo, useState } from "react";
import { cn } from "@/lib/format";
import type { AdminTopic } from "@/lib/adminBoard";

export const MAX_TOPICS = 8;

/**
 * Searchable multi-select of topics grouped by category. Only active topics
 * are offered; an inactive topic already on the listing stays visible (and
 * removable) so nothing is silently dropped.
 */
export function TopicPicker({
  topics,
  selected,
  onChange,
  invalid,
  describedBy,
}: {
  topics: AdminTopic[];
  selected: number[];
  onChange: (ids: number[]) => void;
  invalid?: boolean;
  describedBy?: string;
}) {
  const [query, setQuery] = useState("");
  const selectedSet = useMemo(() => new Set(selected), [selected]);
  const atMax = selected.length >= MAX_TOPICS;

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const visible = topics.filter(
      (t) =>
        (t.active || selectedSet.has(t.id)) &&
        (needle === "" ||
          t.name.toLowerCase().includes(needle) ||
          t.slug.includes(needle) ||
          t.category.toLowerCase().includes(needle)),
    );
    const byCat = new Map<string, AdminTopic[]>();
    for (const t of [...visible].sort((a, b) => a.position - b.position)) {
      const list = byCat.get(t.category) ?? [];
      list.push(t);
      byCat.set(t.category, list);
    }
    return [...byCat.entries()];
  }, [topics, query, selectedSet]);

  const toggle = (id: number) => {
    if (selectedSet.has(id)) onChange(selected.filter((x) => x !== id));
    else if (!atMax) onChange([...selected, id]);
  };

  const chosen = selected
    .map((id) => topics.find((t) => t.id === id))
    .filter((t): t is AdminTopic => Boolean(t));

  return (
    <div
      className={cn(
        "rounded-lg border bg-white",
        invalid ? "border-red-400" : "border-stone-300",
      )}
      aria-describedby={describedBy}
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-stone-200 p-2">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search topics…"
          aria-label="Search topics"
          className="min-w-40 flex-1 rounded-md border border-stone-200 px-2.5 py-1.5 text-sm text-stone-900 placeholder:text-stone-400 focus:border-brand-500"
        />
        <span
          className={cn(
            "text-xs tabular-nums",
            atMax ? "font-medium text-amber-700" : "text-stone-500",
          )}
        >
          {selected.length} / {MAX_TOPICS} chosen
        </span>
      </div>

      {chosen.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-b border-stone-100 px-2 py-2">
          {chosen.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => toggle(t.id)}
              aria-label={`Remove ${t.name}`}
              className={cn(
                "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
                t.active
                  ? "border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100"
                  : "border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100",
              )}
              title={t.active ? undefined : "Inactive topic — remove it to change this listing's topics"}
            >
              {t.name}
              {!t.active && " (inactive)"}
              <span aria-hidden="true">×</span>
            </button>
          ))}
        </div>
      )}

      <div className="max-h-72 space-y-3 overflow-y-auto p-3">
        {groups.length === 0 ? (
          <p className="py-4 text-center text-sm text-stone-500">
            {topics.length === 0 ? "No topics available." : `No topics match “${query}”.`}
          </p>
        ) : (
          groups.map(([category, list]) => (
            <fieldset key={category}>
              <legend className="mb-1.5 text-xs font-semibold tracking-wide text-stone-500 uppercase">
                {category}
              </legend>
              <div className="flex flex-wrap gap-1.5">
                {list.map((t) => {
                  const on = selectedSet.has(t.id);
                  const disabled = !on && atMax;
                  return (
                    <label
                      key={t.id}
                      data-testid={`opp-topic-option-${t.slug}`}
                      className={cn(
                        "inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 text-sm transition-colors select-none",
                        on
                          ? "border-brand-300 bg-brand-50 text-brand-800"
                          : "border-stone-200 bg-white text-stone-700 hover:border-stone-300 hover:bg-stone-50",
                        disabled && "cursor-not-allowed opacity-50 hover:bg-white",
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={on}
                        disabled={disabled}
                        onChange={() => toggle(t.id)}
                        className="size-3.5 accent-brand-600"
                      />
                      {t.name}
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ))
        )}
      </div>
    </div>
  );
}
