"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  formatUsd,
  getSpend,
  isAuthError,
  PURPOSE_LABELS,
  type NetworkSpend,
} from "@/lib/adminNetwork";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAdmin } from "@/components/admin/AdminGate";

/** "Network AI spend" — totals over network `ai_usage` rows (help-desk spend excluded). */
export function SpendCard() {
  const { adminKey, onUnauthorized } = useAdmin();
  const [spend, setSpend] = useState<NetworkSpend | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSpend(await getSpend(adminKey));
    } catch (err) {
      if (isAuthError(err)) {
        onUnauthorized();
        return;
      }
      setError(err instanceof ApiError ? err.message : "Couldn't load the AI spend.");
    } finally {
      setLoading(false);
    }
  }, [adminKey, onUnauthorized]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Card className="p-4" data-testid="network-ai-spend">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-stone-900">Network AI spend</h2>
        <span className="text-xs text-stone-400">All time</span>
      </div>

      {loading && !spend ? (
        <div className="mt-3 space-y-2" aria-label="Loading AI spend">
          <Skeleton className="h-7 w-24" />
          <Skeleton className="h-4 w-40" />
        </div>
      ) : error ? (
        <div className="mt-3 text-sm">
          <p className="text-red-700" role="alert">
            {error}
          </p>
          <Button variant="secondary" size="sm" className="mt-2" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      ) : spend ? (
        <>
          <p className="mt-2 text-2xl font-semibold tabular-nums text-stone-900" data-testid="network-ai-spend-total">
            {formatUsd(spend.total_cost_usd)}
          </p>
          <p className="mt-0.5 text-xs text-stone-500">
            {spend.call_count.toLocaleString()} {spend.call_count === 1 ? "call" : "calls"} ·{" "}
            {spend.prompt_tokens.toLocaleString()} in / {spend.completion_tokens.toLocaleString()} out
            tokens
          </p>
          {spend.by_purpose.length === 0 ? (
            <p className="mt-3 text-xs text-stone-400">
              No AI calls yet — CV drafts will show up here.
            </p>
          ) : (
            <ul className="mt-3 space-y-1 border-t border-stone-100 pt-2 text-xs">
              {spend.by_purpose.map((p) => (
                <li key={p.purpose} className="flex items-center justify-between gap-2">
                  <span className="text-stone-600">{PURPOSE_LABELS[p.purpose] ?? p.purpose}</span>
                  <span className="tabular-nums text-stone-700">
                    {formatUsd(p.cost_usd)}{" "}
                    <span className="text-stone-400">
                      ({p.count} {p.count === 1 ? "call" : "calls"})
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      ) : null}
    </Card>
  );
}
