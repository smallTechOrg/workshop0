"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { formatDate } from "@/lib/format";
import {
  formatRate,
  LEVEL_LABELS,
  topTopics,
  type PoolRow,
} from "@/lib/adminNetwork";
import { Badge } from "@/components/ui/Badge";
import { TrainerAvatar } from "./TrainerAvatar";
import { VerifiedBadge } from "./VerifiedBadge";

export const trainerHref = (id: number) => `/admin/network/trainer/?id=${id}`;

function CompletenessCell({ pct }: { pct: number }) {
  const v = Math.max(0, Math.min(100, Math.round(pct)));
  const tone = v >= 80 ? "bg-emerald-500" : v >= 50 ? "bg-amber-500" : "bg-stone-400";
  return (
    <div className="flex items-center gap-2" title={`${v}% complete`}>
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-stone-200">
        <div className={`h-full ${tone}`} style={{ width: `${v}%` }} />
      </div>
      <span className="text-xs tabular-nums text-stone-600">{v}%</span>
    </div>
  );
}

/** The trainer pool table — row click opens the trainer detail. */
export function PoolTable({ rows }: { rows: PoolRow[] }) {
  const router = useRouter();
  return (
    <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
      <table className="w-full min-w-[820px] text-left text-sm">
        <thead className="border-b border-stone-200 bg-stone-50 text-xs font-semibold tracking-wide text-stone-500 uppercase">
          <tr>
            <th scope="col" className="px-4 py-3">Trainer</th>
            <th scope="col" className="px-4 py-3">Top topics</th>
            <th scope="col" className="px-4 py-3">Location</th>
            <th scope="col" className="px-4 py-3">
              Rate <span className="normal-case tracking-normal text-stone-400">(admin only)</span>
            </th>
            <th scope="col" className="px-4 py-3">Complete</th>
            <th scope="col" className="hidden px-4 py-3 lg:table-cell">Tags</th>
            <th scope="col" className="hidden px-4 py-3 md:table-cell">Joined</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100">
          {rows.map((t) => {
            const topics = topTopics(t.topics ?? [], 3);
            const extra = (t.topics?.length ?? 0) - topics.length;
            const rate = formatRate(t.rate);
            const location = [t.city, t.remote_ok ? "Remote OK" : null].filter(Boolean).join(" · ");
            return (
              <tr
                key={t.id}
                data-testid="pool-row"
                onClick={(e) => {
                  if ((e.target as HTMLElement).closest("a")) return;
                  router.push(trainerHref(t.id));
                }}
                className="cursor-pointer align-top transition-colors hover:bg-brand-50/40"
              >
                <td className="px-4 py-3">
                  <div className="flex items-start gap-3">
                    <TrainerAvatar name={t.display_name} src={t.avatar_url} />
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Link
                          href={trainerHref(t.id)}
                          className="font-medium text-stone-900 hover:text-brand-700 hover:underline"
                        >
                          {t.display_name}
                        </Link>
                        {t.verified && <VerifiedBadge />}
                      </div>
                      <p className="max-w-xs truncate text-xs text-stone-500" title={t.email}>
                        {t.email}
                      </p>
                      <p className="mt-0.5 max-w-xs text-xs text-stone-600">{t.headline}</p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  {topics.length === 0 ? (
                    <span className="text-xs text-stone-400">—</span>
                  ) : (
                    <div className="flex max-w-[16rem] flex-wrap gap-1">
                      {topics.map((tp) => (
                        <Badge key={tp.slug} tone="brand" title={LEVEL_LABELS[tp.level] ?? tp.level}>
                          {tp.name}
                          <span className="text-brand-500">· {LEVEL_LABELS[tp.level] ?? tp.level}</span>
                        </Badge>
                      ))}
                      {extra > 0 && <Badge>+{extra}</Badge>}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3 text-xs text-stone-600">{location || "—"}</td>
                <td className="px-4 py-3 text-xs whitespace-nowrap text-stone-700">
                  {rate ?? <span className="text-stone-400">Not set</span>}
                </td>
                <td className="px-4 py-3">
                  <CompletenessCell pct={t.completeness_pct ?? 0} />
                </td>
                <td className="hidden px-4 py-3 lg:table-cell">
                  {(t.tags ?? []).length === 0 ? (
                    <span className="text-xs text-stone-400">—</span>
                  ) : (
                    <div className="flex max-w-[12rem] flex-wrap gap-1">
                      {t.tags.map((tag) => (
                        <Badge key={tag} data-testid="pool-row-tag">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  )}
                </td>
                <td className="hidden px-4 py-3 text-xs whitespace-nowrap text-stone-500 md:table-cell">
                  {formatDate(t.created_at)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
