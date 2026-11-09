"use client";

import { useId, useState } from "react";
import { ApiError } from "@/lib/api";
import { isAuthError, MAX_TAGS, normalizeTag, setTags, TAG_RE } from "@/lib/adminNetwork";
import { Card } from "@/components/ui/Card";
import { useAdmin } from "@/components/admin/AdminGate";

/** Admin-only tags — add on Enter, remove with ×. Each change replaces the whole set. */
export function TagsEditor({
  trainerId,
  tags,
  onSaved,
}: {
  trainerId: number;
  tags: string[];
  onSaved: (tags: string[]) => void;
}) {
  const { adminKey, onUnauthorized } = useAdmin();
  const inputId = useId();
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const save = async (next: string[], clearDraft: boolean) => {
    setSaving(true);
    setError(null);
    try {
      const res = await setTags(adminKey, trainerId, next);
      onSaved(res.tags);
      if (clearDraft) setDraft("");
    } catch (err) {
      if (isAuthError(err)) {
        onUnauthorized();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Couldn't save the tags.");
    } finally {
      setSaving(false);
    }
  };

  const add = () => {
    const tag = normalizeTag(draft);
    if (!tag) return;
    if (!TAG_RE.test(tag)) {
      setError("Use 1–40 lower-case letters, digits, spaces or '-', starting with a letter or digit.");
      return;
    }
    if (tags.includes(tag)) {
      setDraft("");
      return;
    }
    if (tags.length >= MAX_TAGS) {
      setError(`At most ${MAX_TAGS} tags per trainer.`);
      return;
    }
    void save([...tags, tag], true);
  };

  return (
    <Card className="p-4">
      <h2 className="text-sm font-semibold text-stone-900">Tags</h2>
      <p className="mt-0.5 text-xs text-stone-500">Private to admins. Filter the pool by tag.</p>
      <div className="mt-3">
        <label htmlFor={inputId} className="sr-only">
          Add a tag
        </label>
        <div className="flex gap-2">
          <input
            id={inputId}
            type="text"
            value={draft}
            maxLength={40}
            disabled={saving}
            placeholder="Add a tag and press Enter"
            onChange={(e) => {
              setDraft(e.target.value);
              setError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
            aria-invalid={error ? true : undefined}
            className="min-w-0 flex-1 rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-200 focus:outline-none disabled:opacity-60"
          />
        </div>
        {error && (
          <p className="mt-1 text-xs text-red-700" role="alert">
            {error}
          </p>
        )}
      </div>
      {tags.length === 0 ? (
        <p className="mt-3 text-xs text-stone-400">No tags yet.</p>
      ) : (
        <ul className="mt-3 flex flex-wrap gap-1.5" data-testid="trainer-tags">
          {tags.map((tag) => (
            <li
              key={tag}
              className="inline-flex items-center gap-1 rounded-full border border-stone-200 bg-stone-100 py-0.5 pr-1 pl-2.5 text-xs font-medium text-stone-700"
            >
              <span data-testid="trainer-tag">{tag}</span>
              <button
                type="button"
                disabled={saving}
                onClick={() => void save(tags.filter((t) => t !== tag), false)}
                aria-label={`Remove ${tag}`}
                title="Remove"
                className="inline-flex size-4 items-center justify-center rounded-full text-stone-400 hover:bg-stone-200 hover:text-stone-700 disabled:opacity-50"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
