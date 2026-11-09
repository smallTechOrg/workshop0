"use client";

import { formatDate, timeAgo, useNowTick } from "@/lib/format";
import { ACTIVITY_LABELS, type TrainerActivity } from "@/lib/adminNetwork";
import { Card } from "@/components/ui/Card";

const DOT: Record<string, string> = {
  "trainer.verify": "bg-emerald-500",
  "trainer.unverify": "bg-amber-500",
  "trainer.note": "bg-brand-500",
  "trainer.tag": "bg-stone-400",
  "cv.download": "bg-sky-500",
};

function describe(item: TrainerActivity): string | null {
  if (item.action !== "trainer.tag") return null;
  const added = Array.isArray(item.detail.added) ? (item.detail.added as string[]) : [];
  const removed = Array.isArray(item.detail.removed) ? (item.detail.removed as string[]) : [];
  const parts = [
    added.length ? `+${added.join(", +")}` : "",
    removed.length ? `−${removed.join(", −")}` : "",
  ].filter(Boolean);
  return parts.length ? parts.join(" ") : null;
}

/** Audit rows for this trainer — who / what / when, newest first (latest 20). */
export function TrainerActivityList({ items }: { items: TrainerActivity[] }) {
  const now = useNowTick(30000);
  return (
    <Card className="p-4">
      <h2 className="text-sm font-semibold text-stone-900">Activity</h2>
      {items.length === 0 ? (
        <p className="mt-2 text-xs text-stone-400">No admin activity yet.</p>
      ) : (
        <ol className="mt-3 space-y-2.5" data-testid="trainer-activity">
          {items.map((item) => {
            const by = typeof item.detail.by === "string" ? item.detail.by : null;
            const extra = describe(item);
            return (
              <li key={item.id} className="flex gap-2.5 text-sm">
                <span
                  aria-hidden="true"
                  className={`mt-1.5 size-2 shrink-0 rounded-full ${DOT[item.action] ?? "bg-stone-300"}`}
                />
                <div className="min-w-0">
                  <p className="text-stone-800">
                    {ACTIVITY_LABELS[item.action] ?? item.action}
                    {extra && <span className="text-stone-500"> · {extra}</span>}
                  </p>
                  <p className="text-xs text-stone-400">
                    {by ? `${by} · ` : ""}
                    <time dateTime={item.created_at} title={formatDate(item.created_at)}>
                      {timeAgo(item.created_at, now)}
                    </time>
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
