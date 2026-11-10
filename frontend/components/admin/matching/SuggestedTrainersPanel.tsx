"use client";

import { useCallback, useEffect, useId, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  formatRate,
  formatUsd,
  getShortlist,
  inviteToApply,
  isAuthError,
  outboxLabel,
  runShortlist,
  topTopics,
  type OppInviteResult,
  type Shortlist,
  type ShortlistSuggestion,
} from "@/lib/adminNetwork";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAdmin } from "@/components/admin/AdminGate";

function inviteOutcome(r: OppInviteResult): string {
  if (r.email === "skipped_no_consent") return "invited (no email: trainer has not consented)";
  return `invited · email ${outboxLabel(r.email).toLowerCase()}`;
}

/**
 * Suggested trainers for one saved listing: the latest shortlist (rule filters
 * then an AI ranking, falling back to rules), with reasons, the rule score and
 * the run cost, plus invite-to-apply for one trainer or a selection.
 */
export function SuggestedTrainersPanel({ opportunityId }: { opportunityId: number }) {
  const { adminKey, onUnauthorized } = useAdmin();
  const headingId = useId();
  const [data, setData] = useState<Shortlist | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);
  const [outcomes, setOutcomes] = useState<Record<number, string>>({});

  const handleErr = useCallback(
    (err: unknown, fallback: string): string | null => {
      if (isAuthError(err)) {
        onUnauthorized();
        return null;
      }
      return err instanceof ApiError ? err.message : fallback;
    },
    [onUnauthorized],
  );

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setData(await getShortlist(adminKey, opportunityId));
    } catch (err) {
      const m = handleErr(err, "Couldn't load the shortlist.");
      if (m) setLoadError(m);
    }
  }, [adminKey, opportunityId, handleErr]);

  useEffect(() => {
    setData(null);
    setSelected(new Set());
    setOutcomes({});
    void load();
  }, [load]);

  const run = async () => {
    setRunning(true);
    setRunError(null);
    try {
      setData(await runShortlist(adminKey, opportunityId));
      setSelected(new Set());
      setOutcomes({});
    } catch (err) {
      const m = handleErr(err, "Couldn't run the shortlist.");
      if (m) setRunError(m);
    } finally {
      setRunning(false);
    }
  };

  const invite = async (ids: number[]) => {
    if (ids.length === 0) return;
    setInviting(true);
    setInviteError(null);
    try {
      const res = await inviteToApply(adminKey, opportunityId, ids);
      setOutcomes((cur) => {
        const next = { ...cur };
        for (const r of res) next[r.profile_id] = inviteOutcome(r);
        return next;
      });
      setData((cur) =>
        cur
          ? {
              ...cur,
              suggestions: cur.suggestions.map((s) =>
                ids.includes(s.trainer.id) ? { ...s, invited: true } : s,
              ),
            }
          : cur,
      );
      setSelected(new Set());
    } catch (err) {
      const m = handleErr(err, "Couldn't send the invites.");
      if (m) setInviteError(m);
    } finally {
      setInviting(false);
    }
  };

  const toggle = (id: number) =>
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const suggestions = data?.suggestions ?? [];
  const hasRun = data !== null && data.run_id !== null;

  return (
    <section aria-labelledby={headingId} data-testid="suggested-trainers">
      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id={headingId} className="text-sm font-semibold text-stone-900">
            Suggested trainers
          </h2>
          <Button
            size="sm"
            variant="secondary"
            data-testid="suggest-run"
            loading={running}
            onClick={() => void run()}
          >
            {hasRun ? "Re-run" : "Suggest trainers"}
          </Button>
        </div>
        <p className="mt-1 text-xs text-stone-500">
          Matches the listing&apos;s level, budget, dates and location against consenting trainers.
        </p>

        {runError && (
          <p className="mt-2 text-xs text-red-700" role="alert" data-testid="suggest-error">
            {runError}
          </p>
        )}

        {loadError ? (
          <div className="mt-3 text-xs">
            <p className="text-red-700" role="alert">
              {loadError}
            </p>
            <Button variant="secondary" size="sm" className="mt-2" onClick={() => void load()}>
              Retry
            </Button>
          </div>
        ) : data === null ? (
          <div className="mt-3 space-y-2" aria-label="Loading shortlist">
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        ) : !hasRun ? (
          <p className="mt-3 text-xs text-stone-500" data-testid="suggest-empty">
            No shortlist yet. Choose Suggest trainers to rank the network for this listing.
          </p>
        ) : suggestions.length === 0 ? (
          <p className="mt-3 text-xs text-stone-500" data-testid="suggest-none">
            No trainers match this listing&apos;s requirements. Loosen the level or budget, or add
            topics, then run again.
          </p>
        ) : (
          <>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-stone-500">
              {data.ranked_by === "ai" ? (
                <Badge tone="ai">Ranked by AI</Badge>
              ) : (
                <Badge tone="neutral">Ranked by rules</Badge>
              )}
              <span data-testid="suggest-cost">Run cost {formatUsd(data.cost_usd)}</span>
            </div>
            <ul className="mt-2 divide-y divide-stone-100" data-testid="suggest-list">
              {suggestions.map((s: ShortlistSuggestion) => {
                const t = s.trainer;
                const rate = formatRate(t.rate);
                const out = outcomes[t.id];
                return (
                  <li key={t.id} className="py-2.5" data-testid="suggest-row">
                    <div className="flex items-start gap-2">
                      <input
                        type="checkbox"
                        aria-label={`Select ${t.display_name}`}
                        checked={selected.has(t.id)}
                        disabled={s.invited || inviting}
                        onChange={() => toggle(t.id)}
                        className="mt-1 size-4 rounded border-stone-300 text-brand-600"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="truncate text-sm font-medium text-stone-900">
                            <span className="text-stone-400">#{s.rank}</span> {t.display_name}
                          </p>
                          <span
                            className="text-xs font-medium text-stone-600"
                            title="Rule score"
                            data-testid="suggest-score"
                          >
                            Score {s.rule_score.toFixed(2)}
                          </span>
                        </div>
                        <p className="text-xs text-stone-500">
                          {t.headline}
                          {rate ? ` · ${rate}` : ""}
                          {t.topics.length
                            ? ` · ${topTopics(t.topics, 3)
                                .map((x) => x.name)
                                .join(", ")}`
                            : ""}
                        </p>
                        <p className="mt-1 text-xs text-stone-700" data-testid="suggest-reason">
                          {s.reason}
                        </p>
                        <div className="mt-1.5 flex flex-wrap items-center gap-2">
                          {s.invited ? (
                            <Badge tone="success">Invited</Badge>
                          ) : (
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled={inviting}
                              aria-label={`Invite ${t.display_name} to apply`}
                              onClick={() => void invite([t.id])}
                            >
                              Invite to apply
                            </Button>
                          )}
                          {out && (
                            <span className="text-xs text-stone-500" role="status">
                              {out}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-stone-100 pt-3">
              <Button
                size="sm"
                data-testid="suggest-invite-selected"
                disabled={selected.size === 0}
                loading={inviting}
                onClick={() => void invite([...selected])}
              >
                Invite selected ({selected.size})
              </Button>
            </div>
          </>
        )}
        {inviteError && (
          <p className="mt-2 text-xs text-red-700" role="alert" data-testid="invite-error">
            {inviteError}
          </p>
        )}
      </Card>
    </section>
  );
}

export default SuggestedTrainersPanel;
