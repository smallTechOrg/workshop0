"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { SearchRow } from "@/components/network/searches/SearchRow";
import { listSearches, type SavedSearch } from "@/lib/networkSearches";
import { errorText } from "@/lib/networkApplications";

export function SearchList() {
  const [searches, setSearches] = useState<SavedSearch[] | null>(null);
  const [limit, setLimit] = useState(10);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    listSearches()
      .then((r) => {
        setSearches(r.searches);
        setLimit(r.limit);
      })
      .catch((e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);

  if (error) {
    return (
      <Card className="space-y-3 p-5" role="alert" data-testid="searches-error">
        <p className="text-sm text-red-700">{error}</p>
        <Button size="sm" variant="secondary" onClick={load}>
          Try again
        </Button>
      </Card>
    );
  }
  if (!searches) {
    return (
      <div aria-busy="true" aria-label="Loading saved searches" className="space-y-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }
  if (searches.length === 0) {
    return (
      <div data-testid="searches-list">
        <EmptyState
          title="No saved searches yet"
          hint="On the opportunities board, pick filters and click Save this search to get alerts."
          action={
            <a href="/app/opportunities/" className="text-sm font-medium text-brand-700 underline underline-offset-4">
              Browse opportunities
            </a>
          }
        />
      </div>
    );
  }
  return (
    <div className="space-y-3" data-testid="searches-list">
      <p className="text-xs text-stone-500">
        {searches.length} of {limit} saved searches
      </p>
      {searches.map((s) => (
        <SearchRow
          key={s.id}
          search={s}
          onChange={(u) => setSearches((cur) => (cur ?? []).map((x) => (x.id === u.id ? u : x)))}
          onDelete={(id) => setSearches((cur) => (cur ?? []).filter((x) => x.id !== id))}
        />
      ))}
    </div>
  );
}
