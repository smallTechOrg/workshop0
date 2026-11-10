"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ListShell } from "@/components/network/applications/ListShell";
import { OppSummary } from "@/components/network/applications/OppSummary";
import { formatDate } from "@/lib/format";
import {
  errorText,
  listMyApplications,
  STATUS_LABELS,
  STATUS_TONES,
  withdrawApplication,
  type MyApplication,
} from "@/lib/networkApplications";

function List() {
  const [apps, setApps] = useState<MyApplication[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [rowError, setRowError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    listMyApplications()
      .then((r) => setApps(r.applications))
      .catch((e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);

  async function withdraw(a: MyApplication) {
    if (!window.confirm(`Withdraw your application to "${a.opportunity.title}"?`)) return;
    setBusyId(a.id);
    setRowError(null);
    try {
      const r = await withdrawApplication(a.id);
      setApps((cur) => (cur ?? []).map((x) => (x.id === a.id ? r.application : x)));
    } catch (e) {
      setRowError(errorText(e));
    } finally {
      setBusyId(null);
    }
  }

  if (error) {
    return (
      <Card className="space-y-3 p-5" role="alert" data-testid="apps-error">
        <p className="text-sm text-red-700">{error}</p>
        <Button size="sm" variant="secondary" onClick={load}>
          Try again
        </Button>
      </Card>
    );
  }
  if (!apps) {
    return (
      <div aria-busy="true" aria-label="Loading applications" className="space-y-3">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-20 w-full" />
      </div>
    );
  }
  if (apps.length === 0) {
    return (
      <EmptyState
        title="No applications yet"
        hint="Apply to an open opportunity and it will show up here."
        action={
          <a href="/app/opportunities/" className="text-sm font-medium text-brand-700 underline underline-offset-4">
            Browse opportunities
          </a>
        }
      />
    );
  }
  return (
    <div className="space-y-3" data-testid="apps-list">
      {rowError && (
        <p role="alert" className="text-sm text-red-700">
          {rowError}
        </p>
      )}
      {apps.map((a) => (
        <Card key={a.id} className="space-y-2 p-4" data-testid="app-row">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <OppSummary o={a.opportunity} />
            <Badge tone={STATUS_TONES[a.status]}>{STATUS_LABELS[a.status]}</Badge>
          </div>
          {a.note && <p className="text-sm text-stone-600">Your note: {a.note}</p>}
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-stone-500">
            <span>
              Applied {formatDate(a.created_at)}
              {a.source === "invited" ? " · invited" : ""}
            </span>
            {(a.status === "applied" || a.status === "shortlisted") && (
              <Button size="sm" variant="secondary" loading={busyId === a.id} onClick={() => void withdraw(a)}>
                Withdraw
              </Button>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}

export default function MyApplicationsPage() {
  return (
    <ListShell
      title="My applications"
      intro="Every opportunity you've applied to, and where it stands."
      next="/app/network/applications/"
    >
      {() => <List />}
    </ListShell>
  );
}
