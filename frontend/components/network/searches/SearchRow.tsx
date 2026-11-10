"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  deleteSearch,
  updateSearch,
  type SavedSearch,
} from "@/lib/networkSearches";
import { errorText } from "@/lib/networkApplications";

const MODES = ["remote", "onsite", "hybrid"] as const;

export function describe(s: SavedSearch): string {
  const c = s.criteria;
  const parts = [
    c.types.length ? c.types.join(", ") : "",
    c.topic_slugs.length ? `topics: ${c.topic_slugs.join(", ")}` : "",
    c.location_modes.length ? c.location_modes.join(" / ") : "",
    c.cities.length ? `in ${c.cities.join(", ")}` : "",
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Any listing";
}

export function SearchRow({
  search,
  onChange,
  onDelete,
}: {
  search: SavedSearch;
  onChange: (s: SavedSearch) => void;
  onDelete: (id: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(search.name);
  const [modes, setModes] = useState<string[]>(search.criteria.location_modes);
  const [cities, setCities] = useState(search.criteria.cities.join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const toggleAlerts = () =>
    run(async () => onChange(await updateSearch(search.id, { alerts_enabled: !search.alerts_enabled })));

  const save = () =>
    run(async () => {
      const cityList = cities.split(",").map((c) => c.trim()).filter(Boolean);
      onChange(
        await updateSearch(search.id, {
          name: name.trim(),
          criteria: { ...search.criteria, location_modes: modes, cities: cityList },
        }),
      );
      setEditing(false);
    });

  const remove = () => {
    if (!window.confirm(`Delete the saved search "${search.name}"?`)) return Promise.resolve();
    return run(async () => {
      await deleteSearch(search.id);
      onDelete(search.id);
    });
  };

  return (
    <Card className="space-y-3 p-4" data-testid="search-row">
      {editing ? (
        <div className="space-y-3">
          <label className="block text-sm">
            <span className="font-medium text-stone-800">Name</span>
            <input
              className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2"
              aria-label="Search name"
              value={name}
              maxLength={80}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <fieldset className="flex flex-wrap gap-4 text-sm">
            <legend className="font-medium text-stone-800">Location</legend>
            {MODES.map((m) => (
              <label key={m} className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={modes.includes(m)}
                  onChange={() => setModes((cur) => (cur.includes(m) ? cur.filter((x) => x !== m) : [...cur, m]))}
                />
                {m}
              </label>
            ))}
          </fieldset>
          <label className="block text-sm">
            <span className="font-medium text-stone-800">Cities (comma separated, up to 5)</span>
            <input
              className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2"
              aria-label="Cities"
              value={cities}
              onChange={(e) => setCities(e.target.value)}
            />
          </label>
          <div className="flex gap-2">
            <Button size="sm" loading={busy} disabled={!name.trim()} onClick={() => void save()}>
              Save
            </Button>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="font-medium text-stone-900" data-testid="search-name">
              {search.name}
            </h3>
            <p className="text-sm text-stone-600">{describe(search)}</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1.5 text-sm text-stone-700">
              <input
                type="checkbox"
                data-testid="search-alerts-toggle"
                checked={search.alerts_enabled}
                disabled={busy}
                onChange={() => void toggleAlerts()}
              />
              Email alerts
            </label>
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => void remove()}>
              Delete
            </Button>
          </div>
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
    </Card>
  );
}
