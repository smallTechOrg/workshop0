"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import {
  MOVE_TARGETS,
  PIPELINE_STATUSES,
  adminDownloadApplicationsCsv,
  adminListApplications,
  adminMoveApplications,
  type AppStatus,
  type PipelineData,
} from "@/lib/adminPipeline";
import { adminGetOpportunity } from "@/lib/adminBoard";
import { LinkFacilitatorButton } from "@/components/admin/facilitators/LinkFacilitatorButton";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useAdmin } from "@/components/admin/AdminGate";

export function PipelineBoard({ opportunityId }: { opportunityId: number }) {
  const { adminKey, onUnauthorized } = useAdmin();
  const toast = useToast();
  const [data, setData] = useState<PipelineData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [target, setTarget] = useState<AppStatus | "">("");
  const [notify, setNotify] = useState(true);
  const [moving, setMoving] = useState(false);
  const [moveError, setMoveError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [cofac, setCofac] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await adminListApplications(adminKey, opportunityId));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setError(
        err instanceof ApiError && err.status !== 0
          ? `Couldn't load applicants — ${err.message}`
          : "Couldn't load applicants — check your connection and try again.",
      );
    }
  }, [adminKey, onUnauthorized, opportunityId]);

  useEffect(() => {
    void load();
  }, [load]);

  // "Link as facilitator" only applies to co-facilitation listings.
  useEffect(() => {
    adminGetOpportunity(adminKey, opportunityId)
      .then((r) => setCofac(r.opportunity.type === "cofacilitation"))
      .catch(() => setCofac(false));
  }, [adminKey, opportunityId]);

  const toggle = (id: number) =>
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const move = async () => {
    if (!target || selected.size === 0) return;
    setMoving(true);
    setMoveError(null);
    try {
      const res = await adminMoveApplications(adminKey, opportunityId, {
        application_ids: [...selected],
        status: target,
        notify,
      });
      const q = Number(res.emails_queued ?? 0);
      toast.show(
        `Moved ${selected.size} to ${MOVE_TARGETS.find((s) => s.key === target)?.label}` +
          (q > 0 ? ` — ${q} email${q === 1 ? "" : "s"} queued` : ""),
        "success",
      );
      setSelected(new Set());
      setTarget("");
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setMoveError(
        err instanceof ApiError ? err.message : "Couldn't move applicants — try again.",
      );
      // A withdrawn/missing row may have changed under us — refresh.
      void load();
    } finally {
      setMoving(false);
    }
  };

  const exportCsv = async () => {
    setExporting(true);
    try {
      await adminDownloadApplicationsCsv(adminKey, opportunityId);
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "CSV export failed.", "error");
    } finally {
      setExporting(false);
    }
  };

  if (error) {
    return (
      <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        {error}
        <Button variant="secondary" size="sm" onClick={() => void load()}>
          Retry
        </Button>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="space-y-2" aria-label="Loading applicants">
        <Skeleton className="h-10" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    );
  }

  const total = Object.values(data.counts).reduce((a, b) => a + b, 0);
  if (total === 0) {
    return (
      <EmptyState
        icon="📭"
        title="No applicants yet."
        hint="Trainers who apply to this listing will appear here, grouped by status."
      />
    );
  }

  return (
    <div data-testid="pipeline-board" className="space-y-5">
      <div className="sticky top-0 z-10 flex flex-wrap items-center gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3 shadow-sm">
        <span className="text-sm text-stone-600" data-testid="pipeline-selected-count">
          {selected.size} selected
        </span>
        <label className="sr-only" htmlFor="move-to">
          Move to
        </label>
        <select
          id="move-to"
          data-testid="pipeline-move-select"
          value={target}
          onChange={(e) => setTarget(e.target.value as AppStatus | "")}
          className="rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 text-sm"
        >
          <option value="">Move to…</option>
          {MOVE_TARGETS.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
        <label className="inline-flex items-center gap-2 text-sm text-stone-700">
          <input
            type="checkbox"
            data-testid="pipeline-notify"
            checked={notify}
            onChange={(e) => setNotify(e.target.checked)}
          />
          Email the trainers
        </label>
        <Button
          size="sm"
          data-testid="pipeline-move-button"
          disabled={!target || selected.size === 0}
          loading={moving}
          onClick={() => void move()}
        >
          Move
        </Button>
        <Button
          variant="secondary"
          size="sm"
          className="ml-auto"
          data-testid="pipeline-csv"
          loading={exporting}
          onClick={() => void exportCsv()}
        >
          Download CSV
        </Button>
      </div>
      {moveError && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
          {moveError}
        </p>
      )}

      {PIPELINE_STATUSES.map((s) => {
        const rows = data.applications.filter((a) => a.status === s.key);
        return (
          <section key={s.key} data-testid={`pipeline-group-${s.key}`} aria-label={s.label}>
            <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold tracking-wide text-stone-500 uppercase">
              {s.label}
              <span className="rounded-full bg-stone-200 px-1.5 text-xs text-stone-600 tabular-nums">
                {data.counts[s.key] ?? 0}
              </span>
            </h2>
            {rows.length === 0 ? (
              <p className="rounded-lg border border-dashed border-stone-200 px-4 py-3 text-sm text-stone-400">
                Nobody here.
              </p>
            ) : (
              <ul className="divide-y divide-stone-100 rounded-xl border border-stone-200 bg-white shadow-sm">
                {rows.map((a) => {
                  const withdrawn = a.status === "withdrawn";
                  return (
                    <li key={a.id} data-testid="pipeline-row" className="flex items-start gap-3 px-4 py-3">
                      <input
                        type="checkbox"
                        aria-label={`Select ${a.trainer.display_name}`}
                        disabled={withdrawn}
                        checked={selected.has(a.id)}
                        onChange={() => toggle(a.id)}
                        className="mt-1"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-stone-900">
                          {a.trainer.display_name}{" "}
                          {a.trainer.verified && <Badge tone="success">Verified</Badge>}
                        </p>
                        <p className="text-xs text-stone-500">
                          {a.trainer.email}
                          {a.trainer.city ? ` · ${a.trainer.city}` : ""}
                          {a.trainer.remote_ok ? " · remote OK" : ""}
                        </p>
                        {a.trainer.headline && (
                          <p className="mt-0.5 text-sm text-stone-700">{a.trainer.headline}</p>
                        )}
                        {a.note && (
                          <p className="mt-1 rounded bg-stone-50 px-2 py-1 text-sm whitespace-pre-wrap text-stone-700">
                            {a.note}
                          </p>
                        )}
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1.5">
                        <span className="text-xs whitespace-nowrap text-stone-400">
                          {a.source === "invite" ? "Invited · " : ""}
                          applied {timeAgo(a.created_at, Date.now())}
                        </span>
                        {cofac && a.status === "selected" && (
                          <LinkFacilitatorButton profileId={a.trainer.id} opportunityId={opportunityId} />
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
