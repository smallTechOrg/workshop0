"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/format";
import type { PoolTopic } from "@/lib/adminNetwork";

export interface PoolFilterValues {
  q: string;
  topic: string[];
  verified: "" | "true" | "false";
  tag: string;
}

const inputCls =
  "rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-200 focus:outline-none";

/** Debounced text input — commits after the user pauses typing (or on Enter). */
function useDebounced(value: string, commit: (v: string) => void, delay = 300) {
  const [draft, setDraft] = useState(value);
  const commitRef = useRef(commit);
  commitRef.current = commit;
  const last = useRef(value);

  // External change (e.g. "Clear filters") resets the draft.
  useEffect(() => {
    if (value !== last.current) {
      last.current = value;
      setDraft(value);
    }
  }, [value]);

  useEffect(() => {
    if (draft === last.current) return;
    const id = setTimeout(() => {
      last.current = draft;
      commitRef.current(draft);
    }, delay);
    return () => clearTimeout(id);
  }, [draft, delay]);

  const flush = () => {
    if (draft !== last.current) {
      last.current = draft;
      commitRef.current(draft);
    }
  };
  return { draft, setDraft, flush };
}

function TopicFilter({
  topics,
  selected,
  onChange,
}: {
  topics: PoolTopic[] | null;
  selected: string[];
  onChange: (slugs: string[]) => void;
}) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) ref.current.open = false;
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  const toggle = (slug: string) =>
    onChange(selected.includes(slug) ? selected.filter((s) => s !== slug) : [...selected, slug]);

  return (
    <details ref={ref} className="relative">
      <summary
        className={cn(
          inputCls,
          "flex cursor-pointer list-none items-center gap-2 select-none [&::-webkit-details-marker]:hidden",
          selected.length > 0 && "border-brand-400 text-brand-700",
        )}
      >
        {selected.length === 0 ? "Any topic" : `${selected.length} topic${selected.length === 1 ? "" : "s"}`}
        <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="size-4 text-stone-400">
          <path
            fillRule="evenodd"
            d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06Z"
            clipRule="evenodd"
          />
        </svg>
      </summary>
      <div className="absolute z-20 mt-1 max-h-72 w-72 overflow-y-auto rounded-xl border border-stone-200 bg-white p-2 shadow-lg">
        <p className="px-2 pb-1 text-xs text-stone-500">Trainers with any of these topics</p>
        {topics === null ? (
          <p className="px-2 py-1 text-sm text-stone-400">Loading topics…</p>
        ) : topics.length === 0 ? (
          <p className="px-2 py-1 text-sm text-stone-400">No active topics.</p>
        ) : (
          topics.map((t) => (
            <label
              key={t.slug}
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 text-sm text-stone-700 hover:bg-stone-50"
            >
              <input
                type="checkbox"
                checked={selected.includes(t.slug)}
                onChange={() => toggle(t.slug)}
                className="size-4 rounded border-stone-300 text-brand-600"
              />
              <span className="min-w-0 flex-1 truncate">{t.name}</span>
              <span className="text-xs text-stone-400">{t.category}</span>
            </label>
          ))
        )}
        {selected.length > 0 && (
          <button
            type="button"
            onClick={() => onChange([])}
            className="mt-1 w-full rounded-md px-2 py-1 text-left text-xs font-medium text-brand-700 hover:bg-brand-50"
          >
            Clear topics
          </button>
        )}
      </div>
    </details>
  );
}

/** Search / topic (any-of) / verified / tag filters for the trainer pool. */
export function PoolFiltersBar({
  values,
  topics,
  onChange,
}: {
  values: PoolFilterValues;
  topics: PoolTopic[] | null;
  onChange: (next: Partial<PoolFilterValues>) => void;
}) {
  const q = useDebounced(values.q, (v) => onChange({ q: v }));
  const tag = useDebounced(values.tag, (v) => onChange({ tag: v }));

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        type="search"
        aria-label="Search trainers"
        placeholder="Search name, email, headline or bio…"
        value={q.draft}
        onChange={(e) => q.setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") q.flush();
        }}
        maxLength={200}
        className={cn(inputCls, "w-full min-w-0 sm:w-80")}
      />
      <TopicFilter topics={topics} selected={values.topic} onChange={(topic) => onChange({ topic })} />
      <select
        aria-label="Verified filter"
        value={values.verified}
        onChange={(e) => onChange({ verified: e.target.value as PoolFilterValues["verified"] })}
        className={inputCls}
      >
        <option value="">Verified or not</option>
        <option value="true">Verified only</option>
        <option value="false">Not verified</option>
      </select>
      <input
        type="text"
        aria-label="Filter by tag"
        placeholder="Tag"
        value={tag.draft}
        onChange={(e) => tag.setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") tag.flush();
        }}
        maxLength={40}
        className={cn(inputCls, "w-32")}
      />
    </div>
  );
}
