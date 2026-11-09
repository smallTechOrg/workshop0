"use client";

import { timeAgo, useNowTick } from "@/lib/format";
import { STATUS_LABELS, type ActivityItem, type OpportunityStatus } from "@/lib/adminBoard";

const ACTION_LABELS: Record<string, string> = {
  "opportunity.create": "Created",
  "opportunity.update": "Edited",
  "opportunity.publish": "Published",
  "opportunity.unpublish": "Unpublished",
  "opportunity.close": "Closed",
};

const ACTION_DOT: Record<string, string> = {
  "opportunity.create": "bg-brand-500",
  "opportunity.update": "bg-stone-400",
  "opportunity.publish": "bg-emerald-500",
  "opportunity.unpublish": "bg-amber-500",
  "opportunity.close": "bg-red-500",
};

function statusLabel(s: string | undefined): string {
  if (!s) return "";
  return STATUS_LABELS[s as OpportunityStatus] ?? s;
}

/** The listing's audit rows — who / what / when, newest first. */
export function ActivityList({ items }: { items: ActivityItem[] }) {
  const now = useNowTick(30000);

  if (items.length === 0) {
    return <p className="text-sm text-stone-500">No activity yet.</p>;
  }

  return (
    <ol className="space-y-3">
      {items.map((a) => {
        const d = a.detail ?? {};
        const changed = Array.isArray(d.changed_fields) ? d.changed_fields : [];
        const actor = typeof d.by === "string" && d.by ? d.by : "admin-key";
        return (
          <li key={a.id} data-testid="opp-activity-row" className="flex gap-3">
            <span
              aria-hidden="true"
              className={`mt-1.5 size-2 shrink-0 rounded-full ${ACTION_DOT[a.action] ?? "bg-stone-400"}`}
            />
            <div className="min-w-0 flex-1 text-sm">
              <p className="text-stone-800">
                <span className="font-medium">{ACTION_LABELS[a.action] ?? a.action}</span>{" "}
                <span className="text-stone-500">by</span>{" "}
                <span className="font-mono text-xs text-stone-700">{actor}</span>
                {d.from_status && d.to_status && d.from_status !== d.to_status && (
                  <span className="text-stone-500">
                    {" "}
                    · {statusLabel(d.from_status)} → {statusLabel(d.to_status)}
                  </span>
                )}
              </p>
              {changed.length > 0 && (
                <p className="mt-0.5 text-xs break-words text-stone-500">
                  Changed: {changed.join(", ")}
                </p>
              )}
              <p className="mt-0.5 text-xs text-stone-400">
                <time dateTime={a.created_at} title={new Date(a.created_at).toLocaleString()}>
                  {timeAgo(a.created_at, now)}
                </time>{" "}
                · <span className="font-mono">{a.action}</span>
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
