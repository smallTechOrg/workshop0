"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { signInPageUrl, useCurrentUser } from "@/lib/networkAuth";
import { createSearch } from "@/lib/networkSearches";

function defaultName(type: string, topics: string[]): string {
  const parts = [type ? type.replace(/_/g, " ") : "", ...topics].filter(Boolean);
  return (parts.join(", ") || "My search").slice(0, 80);
}

/** "Save this search" on the board: saves the active type + topic filters as an alert search. */
export function SaveSearchButton({ type, topics }: { type: string; topics: string[] }) {
  const { user, loading } = useCurrentUser();
  const [name, setName] = useState(() => defaultName(type, topics));
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const active = !!type || topics.length > 0;
  const key = `${type}|${topics.join(",")}`;

  // A changed filter is a new search: reset the name and any previous result.
  useEffect(() => {
    setName(defaultName(type, topics));
    setSaved(false);
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (loading) return null;

  const wrap = "mt-4 rounded-xl border border-stone-200 bg-white p-3 text-sm";

  if (!user) {
    const search = typeof window !== "undefined" ? window.location.search : "";
    const path =
      typeof window !== "undefined" && window.location.pathname.startsWith("/app/")
        ? window.location.pathname
        : "/app/opportunities/";
    const target = path + search;
    return (
      <div className={wrap}>
        <a
          href={signInPageUrl(target)}
          data-testid="save-search-button"
          aria-disabled={!active}
          className={`inline-flex items-center justify-center rounded-lg px-3 py-1.5 font-medium shadow-sm ${
            active
              ? "bg-brand-600 text-white hover:bg-brand-700"
              : "pointer-events-none bg-stone-100 text-stone-400"
          }`}
        >
          Save this search
        </a>
        <p className="mt-2 text-xs text-stone-500">
          {active ? "Sign in to get email alerts for this search." : "Pick a type or topic to save a search."}
        </p>
      </div>
    );
  }

  if (!user.has_profile) {
    return (
      <div className={wrap} data-testid="save-search-no-profile">
        <p className="text-stone-700">Create your trainer profile to save searches and get alerts.</p>
        <a
          href="/app/network/join/"
          className="mt-2 inline-flex items-center rounded-lg bg-brand-600 px-3 py-1.5 font-medium text-white hover:bg-brand-700"
        >
          Create your profile
        </a>
      </div>
    );
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await createSearch({
        name: name.trim() || defaultName(type, topics),
        criteria: {
          types: type ? [type] : [],
          topic_slugs: topics,
          location_modes: [],
          cities: [],
        },
        alerts_enabled: true,
      });
      setSaved(true);
    } catch (e) {
      const code = (e as { code?: string }).code;
      setError(
        code === "search_limit"
          ? "You've reached the limit of 10 saved searches. Delete one to save another."
          : e instanceof Error
            ? e.message
            : "Couldn't save this search.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={wrap}>
      <label htmlFor="save-search-name" className="block text-xs font-medium text-stone-600">
        Search name
      </label>
      <input
        id="save-search-name"
        data-testid="save-search-name"
        value={name}
        maxLength={80}
        disabled={!active || busy}
        onChange={(e) => setName(e.target.value)}
        className="mt-1 w-full rounded-lg border border-stone-300 px-2 py-1.5 text-sm disabled:bg-stone-50"
      />
      <Button
        className="mt-2 w-full"
        size="sm"
        loading={busy}
        disabled={!active || saved}
        onClick={() => void save()}
        data-testid="save-search-button"
      >
        Save this search
      </Button>
      {!active && <p className="mt-2 text-xs text-stone-500">Pick a type or topic to save a search.</p>}
      {saved && (
        <p role="status" data-testid="save-search-saved" className="mt-2 text-xs text-green-700">
          Saved — we&apos;ll email you new matches.{" "}
          <a href="/app/network/searches/" className="font-medium underline underline-offset-2">
            Manage saved searches
          </a>
        </p>
      )}
      {error && (
        <p role="alert" data-testid="save-search-error" className="mt-2 text-xs text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
