"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import {
  adminListOutbox,
  adminRetryOutbox,
  type OutboxItem,
  type OutboxPage,
  type OutboxStatus,
} from "@/lib/adminOutbox";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useAdmin } from "@/components/admin/AdminGate";

const TONE: Record<OutboxStatus, BadgeTone> = {
  queued: "info",
  sent: "success",
  recorded: "neutral",
  failed: "danger",
};
const LABEL: Record<OutboxStatus, string> = {
  queued: "Queued",
  sent: "Sent",
  recorded: "Not sent",
  failed: "Failed",
};
const FILTERS: { key: OutboxStatus | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "queued", label: "Queued" },
  { key: "sent", label: "Sent" },
  { key: "recorded", label: "Not sent" },
  { key: "failed", label: "Failed" },
];

export function OutboxTable() {
  const { adminKey, onUnauthorized } = useAdmin();
  const toast = useToast();
  const [data, setData] = useState<OutboxPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<OutboxStatus | "all">("all");
  const [retrying, setRetrying] = useState<number | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await adminListOutbox(adminKey, page, filter === "all" ? undefined : filter));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setError(
        err instanceof ApiError && err.status !== 0
          ? `Couldn't load the outbox — ${err.message}`
          : "Couldn't load the outbox — check your connection and try again.",
      );
    }
  }, [adminKey, onUnauthorized, page, filter]);

  useEffect(() => {
    void load();
  }, [load]);

  const retry = async (row: OutboxItem) => {
    setRetrying(row.id);
    try {
      await adminRetryOutbox(adminKey, row.id);
      toast.show("Retry queued", "success");
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      toast.show(err instanceof ApiError ? err.message : "Retry failed.", "error");
      void load();
    } finally {
      setRetrying(null);
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      {data && !data.smtp_configured && (
        <p
          data-testid="outbox-banner"
          className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
        >
          Email sending isn&apos;t configured — messages are recorded here, not sent.
        </p>
      )}
      <div role="tablist" aria-label="Filter by status" className="mb-4 inline-flex flex-wrap gap-1 rounded-xl border border-stone-200 bg-stone-50 p-1">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            role="tab"
            aria-selected={filter === f.key}
            onClick={() => {
              setFilter(f.key);
              setPage(1);
            }}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
              filter === f.key ? "bg-white text-stone-900 shadow-sm" : "text-stone-600 hover:bg-white/70"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error ? (
        <div role="alert" className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
          <Button variant="secondary" size="sm" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      ) : !data ? (
        <div className="space-y-2" aria-label="Loading outbox">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : data.items.length === 0 ? (
        <EmptyState icon="📪" title="No messages yet." hint="Invites and application updates will be listed here." />
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-stone-200 bg-stone-50 text-xs font-semibold tracking-wide text-stone-500 uppercase">
                <tr>
                  <th className="px-4 py-3">To</th>
                  <th className="px-4 py-3">Subject</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">When</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {data.items.map((r) => (
                  <tr key={r.id} data-testid="outbox-row" data-status={r.status} className="align-top">
                    <td className="px-4 py-3 text-stone-800">{r.to}</td>
                    <td className="px-4 py-3">
                      <p className="text-stone-900">{r.subject}</p>
                      <p className="text-xs text-stone-400">{r.template}</p>
                      {r.status === "failed" && r.last_error && (
                        <p className="mt-1 text-xs text-red-600">
                          {r.last_error} ({r.attempts} attempt{r.attempts === 1 ? "" : "s"})
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={TONE[r.status]}>{LABEL[r.status]}</Badge>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-stone-500">
                      {timeAgo(r.sent_at ?? r.created_at, Date.now())}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {r.status === "failed" && (
                        <Button
                          variant="secondary"
                          size="sm"
                          data-testid="outbox-retry"
                          loading={retrying === r.id}
                          onClick={() => void retry(r)}
                        >
                          Retry
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-between text-sm text-stone-600">
              <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </Button>
              <span>
                Page {page} of {totalPages}
              </span>
              <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
