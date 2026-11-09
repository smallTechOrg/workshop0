"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/format";
import { adminPatchTopic, type AdminTopic } from "@/lib/adminBoard";
import { Button } from "@/components/ui/Button";

export function topicErrorMessage(err: unknown, name: string): string {
  if (err instanceof ApiError) {
    if (err.code === "topic_exists") {
      return `“${name.trim()}” already exists — topic names must be unique (in any case).`;
    }
    if (err.code === "validation_error") return err.message;
    if (err.status === 0) return "Couldn't reach the server — check your connection and try again.";
    return `Couldn't save the topic — ${err.message}`;
  }
  return "Something went wrong — try again.";
}

/** One topic: name / slug / listing count, inline rename, active switch. */
export function TopicRow({
  topic,
  adminKey,
  categories,
  highlight,
  onUpdated,
  onUnauthorized,
  onRequestToggle,
  toggling,
}: {
  topic: AdminTopic;
  adminKey: string;
  categories: string[];
  highlight: boolean;
  onUpdated: (t: AdminTopic) => void;
  onUnauthorized: () => void;
  onRequestToggle: (t: AdminTopic) => void;
  toggling: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(topic.name);
  const [category, setCategory] = useState(topic.category);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEdit = () => {
    setName(topic.name);
    setCategory(topic.category);
    setError(null);
    setEditing(true);
  };

  const save = async () => {
    const body: { name?: string; category?: string } = {};
    if (name.trim() !== topic.name) body.name = name.trim();
    if (category.trim() !== topic.category) body.category = category.trim();
    if (Object.keys(body).length === 0) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await adminPatchTopic(adminKey, topic.id, body);
      onUpdated(res.topic);
      setEditing(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setError(topicErrorMessage(err, name));
    } finally {
      setSaving(false);
    }
  };

  const listId = `topic-cats-${topic.id}`;

  return (
    <li
      data-testid="topic-row"
      className={cn(
        "flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between",
        !topic.active && "bg-stone-50/80",
        highlight && "animate-flash",
      )}
    >
      {editing ? (
        <form
          className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-start"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <div className="min-w-0 flex-1">
            <label className="sr-only" htmlFor={`topic-name-${topic.id}`}>
              Topic name
            </label>
            <input
              id={`topic-name-${topic.id}`}
              data-testid="topic-rename-input"
              value={name}
              autoFocus
              maxLength={80}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setEditing(false);
              }}
              className="w-full rounded-lg border border-stone-300 px-2.5 py-1.5 text-sm text-stone-900 focus:border-brand-500"
            />
            {error && (
              <p role="alert" data-testid="topic-error" className="mt-1 text-sm text-red-600">
                {error}
              </p>
            )}
          </div>
          <div className="sm:w-44">
            <label className="sr-only" htmlFor={`topic-cat-${topic.id}`}>
              Category
            </label>
            <input
              id={`topic-cat-${topic.id}`}
              list={listId}
              value={category}
              maxLength={48}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full rounded-lg border border-stone-300 px-2.5 py-1.5 text-sm text-stone-900 focus:border-brand-500"
            />
            <datalist id={listId}>
              {categories.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </div>
          <div className="flex gap-1.5">
            <Button type="submit" size="sm" loading={saving}>
              Save
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={saving}>
              Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="min-w-0 flex-1">
          <p className={cn("font-medium break-words", topic.active ? "text-stone-900" : "text-stone-500")}>
            {topic.name}
            {!topic.active && (
              <span className="ml-2 rounded-full border border-stone-300 px-1.5 py-0.5 text-[11px] font-medium text-stone-500">
                Inactive
              </span>
            )}
          </p>
          <p className="mt-0.5 text-xs text-stone-500">
            <span className="font-mono" title="Slugs never change">
              {topic.slug}
            </span>{" "}
            · {topic.opportunity_count} listing{topic.opportunity_count === 1 ? "" : "s"}
          </p>
        </div>
      )}

      {!editing && (
        <div className="flex items-center gap-3">
          <Button size="sm" variant="ghost" onClick={startEdit} aria-label={`Rename ${topic.name}`}>
            Rename
          </Button>
          <button
            type="button"
            role="switch"
            aria-checked={topic.active}
            aria-label={`${topic.name} active`}
            data-testid="topic-active-toggle"
            disabled={toggling}
            onClick={() => onRequestToggle(topic)}
            className={cn(
              "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-60",
              topic.active ? "bg-brand-600" : "bg-stone-300",
            )}
          >
            <span
              aria-hidden="true"
              className={cn(
                "inline-block size-5 rounded-full bg-white shadow transition-transform",
                topic.active ? "translate-x-5" : "translate-x-0.5",
              )}
            />
          </button>
        </div>
      )}
    </li>
  );
}
