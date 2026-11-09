"use client";

import { useId, useState } from "react";
import { ApiError } from "@/lib/api";
import { formatDate, timeAgo, useNowTick } from "@/lib/format";
import { addNote, isAuthError, type AdminNote } from "@/lib/adminNetwork";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useAdmin } from "@/components/admin/AdminGate";

const NOTE_MAX = 4000;

/** Private, append-only admin notes — newest first, with author and time. */
export function NotesPanel({
  trainerId,
  notes,
  onSaved,
}: {
  trainerId: number;
  notes: AdminNote[];
  onSaved: (notes: AdminNote[]) => void;
}) {
  const { adminKey, onUnauthorized } = useAdmin();
  const now = useNowTick(30000);
  const fieldId = useId();
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const body = draft.trim();
    if (!body) {
      setError("Write a note first.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const res = await addNote(adminKey, trainerId, body);
      setDraft("");
      onSaved(res.notes);
    } catch (err) {
      if (isAuthError(err)) {
        onUnauthorized();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Couldn't save the note.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="p-4">
      <h2 className="text-sm font-semibold text-stone-900">Private notes</h2>
      <p className="mt-0.5 text-xs text-stone-500">Only admins see these. Notes can't be edited or deleted.</p>
      <form onSubmit={submit} className="mt-3" noValidate>
        <label htmlFor={fieldId} className="sr-only">
          New private note
        </label>
        <textarea
          id={fieldId}
          rows={3}
          value={draft}
          maxLength={NOTE_MAX}
          placeholder="Write a private note…"
          onChange={(e) => {
            setDraft(e.target.value);
            setError(null);
          }}
          aria-invalid={error ? true : undefined}
          className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-200 focus:outline-none"
        />
        <div className="mt-1.5 flex items-center justify-between gap-2">
          {error ? (
            <p className="text-xs text-red-700" role="alert">
              {error}
            </p>
          ) : (
            <span className="text-xs text-stone-400 tabular-nums">
              {draft.length > NOTE_MAX - 400 ? `${NOTE_MAX - draft.length} left` : ""}
            </span>
          )}
          <Button type="submit" size="sm" loading={saving}>
            Add note
          </Button>
        </div>
      </form>
      {notes.length === 0 ? (
        <p className="mt-3 text-xs text-stone-400">No notes yet.</p>
      ) : (
        <ol className="mt-3 space-y-3 border-t border-stone-100 pt-3" data-testid="trainer-notes">
          {notes.map((n) => (
            <li key={n.id} data-testid="trainer-note">
              <p className="text-sm whitespace-pre-wrap text-stone-800">{n.body}</p>
              <p className="mt-0.5 text-xs text-stone-400">
                <span className="text-stone-500">{n.author}</span> ·{" "}
                <time dateTime={n.created_at} title={formatDate(n.created_at)}>
                  {timeAgo(n.created_at, now)}
                </time>
              </p>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
