"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { formatDate, timeAgo, useNowTick, cn } from "@/lib/format";
import {
  relativeDeadline,
  typeLabel,
  type AdminOpportunityRow,
} from "@/lib/adminBoard";
import { Badge } from "@/components/ui/Badge";
import { StubBadge } from "@/components/ui/StubBadge";
import { LockIcon } from "@/components/admin/LockIcon";
import { OpportunityStatusPill } from "@/components/admin/OpportunityStatusPill";

const editHref = (id: number) => `/admin/opportunities/edit/?id=${id}`;

/** Admin opportunities table — row click opens the editor. */
export function OpportunitiesTable({ rows }: { rows: AdminOpportunityRow[] }) {
  const router = useRouter();
  const now = useNowTick(60000);

  return (
    <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="border-b border-stone-200 bg-stone-50 text-xs font-semibold tracking-wide text-stone-500 uppercase">
          <tr>
            <th scope="col" className="px-4 py-3">Opportunity</th>
            <th scope="col" className="px-4 py-3">Partner</th>
            <th scope="col" className="hidden px-4 py-3 lg:table-cell">Topics</th>
            <th scope="col" className="px-4 py-3">Deadline</th>
            <th scope="col" className="px-4 py-3">Status</th>
            <th scope="col" className="hidden px-4 py-3 md:table-cell">
              <span className="inline-flex items-center gap-1.5">
                Applicants <StubBadge className="normal-case tracking-normal" />
              </span>
            </th>
            <th scope="col" className="hidden px-4 py-3 md:table-cell">Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100">
          {rows.map((o) => {
            const shown = o.topics.slice(0, 3);
            const extra = o.topics.length - shown.length;
            const expired = o.status === "expired";
            // Only live listings (open / expired) get a relative countdown;
            // closed and draft rows show a neutral date — "expired X ago" would
            // misdescribe a listing that was closed or never published.
            const live = o.status === "open" || o.status === "expired";
            return (
              <tr
                key={o.id}
                data-testid="admin-opportunity-row"
                onClick={(e) => {
                  if ((e.target as HTMLElement).closest("a")) return;
                  router.push(editHref(o.id));
                }}
                className="cursor-pointer align-top transition-colors hover:bg-brand-50/40"
              >
                <td className="px-4 py-3">
                  <Link
                    href={editHref(o.id)}
                    className="font-medium text-stone-900 hover:text-brand-700 hover:underline"
                  >
                    {o.title}
                  </Link>
                  <div className="mt-1">
                    <Badge tone="brand">{typeLabel(o.type)}</Badge>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <p className="text-stone-800">
                    {o.partner_display_name || (
                      <span className="text-stone-400">smallTech partner network</span>
                    )}
                  </p>
                  {o.partner_internal_name && (
                    <p
                      className="mt-0.5 inline-flex items-center gap-1 text-xs text-stone-500"
                      title="Internal — never shown publicly"
                    >
                      <LockIcon className="size-3" />
                      {o.partner_internal_name}
                    </p>
                  )}
                </td>
                <td className="hidden px-4 py-3 lg:table-cell">
                  <div className="flex flex-wrap gap-1">
                    {shown.map((t) => (
                      <Badge key={t.id} className={cn(!t.active && "opacity-60")}>
                        {t.name}
                      </Badge>
                    ))}
                    {extra > 0 && <Badge>+{extra}</Badge>}
                  </div>
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <span
                    className={cn(expired ? "text-amber-700" : "text-stone-700")}
                    title={new Date(o.deadline).toLocaleString()}
                  >
                    {live ? relativeDeadline(o.deadline, now) : formatDate(o.deadline)}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <OpportunityStatusPill status={o.status} />
                </td>
                <td className="hidden px-4 py-3 text-stone-400 md:table-cell" aria-disabled="true">
                  —
                </td>
                <td className="hidden px-4 py-3 whitespace-nowrap text-stone-500 md:table-cell">
                  {timeAgo(o.updated_at, now)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
