"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ListShell } from "@/components/network/applications/ListShell";
import { OppSummary } from "@/components/network/applications/OppSummary";
import { errorText, listMatches, type MatchedOpportunity } from "@/lib/networkApplications";

function List() {
  const [items, setItems] = useState<MatchedOpportunity[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    listMatches()
      .then((r) => setItems(r.matches))
      .catch((e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);

  if (error) {
    return (
      <Card className="space-y-3 p-5" role="alert" data-testid="matches-error">
        <p className="text-sm text-red-700">{error}</p>
        <Button size="sm" variant="secondary" onClick={load}>
          Try again
        </Button>
      </Card>
    );
  }
  if (!items) {
    return (
      <div aria-busy="true" aria-label="Loading matches" className="space-y-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <EmptyState
        title="No matches right now"
        hint="Add topics and availability to your profile, or check back when new opportunities are published."
        action={
          <a href="/app/network/me/" className="text-sm font-medium text-brand-700 underline underline-offset-4">
            Update my profile
          </a>
        }
      />
    );
  }
  return (
    <div className="space-y-3" data-testid="matches-list">
      {items.map((m) => (
        <Card key={m.opportunity.id} className="flex flex-wrap items-start justify-between gap-2 p-4" data-testid="match-row">
          <OppSummary o={m.opportunity} />
          {m.invited && <Badge tone="brand">Invited</Badge>}
        </Card>
      ))}
    </div>
  );
}

export default function MatchesPage() {
  return (
    <ListShell
      title="Matched for you"
      intro="Open opportunities that fit your topics, level and availability."
      next="/app/network/matches/"
    >
      {() => <List />}
    </ListShell>
  );
}
