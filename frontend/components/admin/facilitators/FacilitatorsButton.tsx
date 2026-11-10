"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  ROLE_LABELS,
  getFacilitators,
  putFacilitators,
  type Facilitator,
  type FacilitatorRole,
} from "@/lib/adminFacilitators";
import { listTrainers, type PoolRow } from "@/lib/adminNetwork";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";

interface Entry {
  profile_id: number;
  role: FacilitatorRole;
  display_name: string;
  headline: string;
}

const ROLES: FacilitatorRole[] = ["lead", "co", "ta"];

/** "Facilitators" button + picker modal on an admin workshop card. */
export function FacilitatorsButton({
  workshopId,
  workshopName,
  adminKey,
  onUnauthorized,
}: {
  workshopId: number;
  workshopName: string;
  adminKey: string;
  onUnauthorized: () => void;
}) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [q, setQ] = useState("");
  const [results, setResults] = useState<PoolRow[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const handle = useCallback(
    (err: unknown, set: (m: string) => void, fallback: string) => {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      set(err instanceof ApiError && err.status !== 0 ? err.message : fallback);
    },
    [onUnauthorized],
  );

  const load = useCallback(async () => {
    setLoadError(null);
    setEntries(null);
    try {
      const { facilitators } = await getFacilitators(adminKey, workshopId);
      setEntries(
        facilitators.map((f: Facilitator) => ({
          profile_id: f.profile_id,
          role: f.role,
          display_name: f.display_name,
          headline: f.headline,
        })),
      );
    } catch (err) {
      handle(err, setLoadError, "Couldn't load facilitators — check your connection.");
    }
  }, [adminKey, workshopId, handle]);

  useEffect(() => {
    if (open) {
      setQ("");
      setResults(null);
      setSaveError(null);
      void load();
    }
  }, [open, load]);

  const search = async () => {
    setSearching(true);
    setSearchError(null);
    try {
      const page = await listTrainers(adminKey, { q: q.trim() || undefined, page_size: 8 });
      setResults(page.trainers);
    } catch (err) {
      handle(err, setSearchError, "Search failed — try again.");
    } finally {
      setSearching(false);
    }
  };

  const add = (t: PoolRow) =>
    setEntries((cur) =>
      !cur || cur.some((e) => e.profile_id === t.id) || cur.length >= 10
        ? cur
        : [...cur, { profile_id: t.id, role: "co", display_name: t.display_name, headline: t.headline }],
    );

  const setRole = (id: number, role: FacilitatorRole) =>
    setEntries((cur) =>
      (cur ?? []).map((e) => {
        if (e.profile_id === id) return { ...e, role };
        // only one lead: demote any other lead
        return role === "lead" && e.role === "lead" ? { ...e, role: "co" } : e;
      }),
    );

  const remove = (id: number) => setEntries((cur) => (cur ?? []).filter((e) => e.profile_id !== id));

  const save = async () => {
    if (!entries) return;
    setSaving(true);
    setSaveError(null);
    try {
      await putFacilitators(
        adminKey,
        workshopId,
        entries.map((e) => ({ profile_id: e.profile_id, role: e.role })),
      );
      toast.show("Facilitators saved", "success");
      setOpen(false);
    } catch (err) {
      handle(err, setSaveError, "Couldn't save facilitators — try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Button variant="secondary" size="sm" data-testid="facilitators-button" onClick={() => setOpen(true)}>
        Facilitators
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={`Facilitators — ${workshopName}`}
        widthClassName="max-w-xl"
      >
        <div data-testid="facilitators-picker" className="space-y-5 px-6 py-5">
          {loadError ? (
            <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {loadError}
              <Button variant="secondary" size="sm" onClick={() => void load()}>
                Retry
              </Button>
            </div>
          ) : entries === null ? (
            <div className="space-y-2" aria-label="Loading facilitators">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          ) : (
            <>
              {entries.length === 0 ? (
                <p data-testid="facilitators-empty" className="rounded-lg border border-dashed border-stone-200 px-4 py-3 text-sm text-stone-500">
                  No trainers linked yet. Search the network below to add one.
                </p>
              ) : (
                <ul className="divide-y divide-stone-100 rounded-lg border border-stone-200">
                  {entries.map((e) => (
                    <li key={e.profile_id} data-testid="facilitator-row" className="flex items-center gap-3 px-3 py-2">
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-stone-900">{e.display_name}</p>
                        {e.headline && <p className="truncate text-xs text-stone-500">{e.headline}</p>}
                      </div>
                      <select
                        aria-label={`Role for ${e.display_name}`}
                        value={e.role}
                        onChange={(ev) => setRole(e.profile_id, ev.target.value as FacilitatorRole)}
                        className="rounded-lg border border-stone-300 bg-white px-2 py-1 text-sm"
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {ROLE_LABELS[r]}
                          </option>
                        ))}
                      </select>
                      <Button variant="secondary" size="sm" aria-label={`Remove ${e.display_name}`} onClick={() => remove(e.profile_id)}>
                        Remove
                      </Button>
                    </li>
                  ))}
                </ul>
              )}

              <div>
                <form
                  className="flex gap-2"
                  onSubmit={(ev) => {
                    ev.preventDefault();
                    void search();
                  }}
                >
                  <input
                    aria-label="Search trainers"
                    data-testid="facilitators-search"
                    value={q}
                    onChange={(ev) => setQ(ev.target.value)}
                    placeholder="Search trainers by name or email"
                    className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-1.5 text-sm"
                  />
                  <Button type="submit" variant="secondary" size="sm" loading={searching} data-testid="facilitators-search-button">
                    Search
                  </Button>
                </form>
                {searchError && (
                  <p role="alert" className="mt-2 text-sm text-red-700">
                    {searchError}
                  </p>
                )}
                {results && results.length === 0 && (
                  <p className="mt-2 text-sm text-stone-500">No trainers match.</p>
                )}
                {results && results.length > 0 && (
                  <ul className="mt-2 divide-y divide-stone-100 rounded-lg border border-stone-200">
                    {results.map((t) => {
                      const linked = entries.some((e) => e.profile_id === t.id);
                      return (
                        <li key={t.id} data-testid="facilitators-result" className="flex items-center gap-3 px-3 py-2">
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-stone-900">{t.display_name}</p>
                            <p className="truncate text-xs text-stone-500">{t.email}</p>
                          </div>
                          <Button size="sm" variant="secondary" disabled={linked || entries.length >= 10} onClick={() => add(t)}>
                            {linked ? "Added" : "Add"}
                          </Button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            </>
          )}

          {saveError && (
            <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {saveError}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button data-testid="facilitators-save" loading={saving} disabled={entries === null} onClick={() => void save()}>
              Save
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
