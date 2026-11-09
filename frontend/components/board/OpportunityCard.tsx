"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { cn } from "@/lib/format";
import {
  TYPE_LABELS,
  listingHref,
  locationLabel,
  partnerName,
  shortDeadline,
  urgencyLabel,
  type PublicOpportunityCard,
} from "@/lib/board";

const MAX_TOPICS = 4;

export function PinIcon({ className }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className={cn("size-4", className)}>
      <path
        fillRule="evenodd"
        d="m9.69 18.933.003.001C9.89 19.02 10 19 10 19s.11.02.308-.066l.002-.001.006-.003.018-.008a5.741 5.741 0 0 0 .281-.14c.186-.096.446-.24.757-.433.62-.384 1.445-.966 2.274-1.765C15.302 14.988 17 12.493 17 9A7 7 0 1 0 3 9c0 3.492 1.698 5.988 3.355 7.584a13.731 13.731 0 0 0 2.273 1.765 11.842 11.842 0 0 0 .976.544l.062.029.018.008.006.003ZM10 11.25a2.25 2.25 0 1 0 0-4.5 2.25 2.25 0 0 0 0 4.5Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

export function CalendarIcon({ className }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className={cn("size-4", className)}>
      <path
        fillRule="evenodd"
        d="M5.75 2a.75.75 0 0 1 .75.75V4h7V2.75a.75.75 0 0 1 1.5 0V4h.25A2.75 2.75 0 0 1 18 6.75v8.5A2.75 2.75 0 0 1 15.25 18H4.75A2.75 2.75 0 0 1 2 15.25v-8.5A2.75 2.75 0 0 1 4.75 4H5V2.75A.75.75 0 0 1 5.75 2Zm-1 5.5c-.69 0-1.25.56-1.25 1.25v6.5c0 .69.56 1.25 1.25 1.25h10.5c.69 0 1.25-.56 1.25-1.25v-6.5c0-.69-.56-1.25-1.25-1.25H4.75Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

export function WalletIcon({ className }: { className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className={cn("size-4", className)}>
      <path d="M1 4.25a3.733 3.733 0 0 1 2.25-.75h13.5c.844 0 1.623.279 2.25.75A2.25 2.25 0 0 0 16.75 2H3.25A2.25 2.25 0 0 0 1 4.25ZM1 7.25a3.733 3.733 0 0 1 2.25-.75h13.5c.844 0 1.623.279 2.25.75A2.25 2.25 0 0 0 16.75 5H3.25A2.25 2.25 0 0 0 1 7.25ZM7 8a1 1 0 0 1 1 1 2 2 0 1 0 4 0 1 1 0 0 1 1-1h3.75A2.25 2.25 0 0 1 19 10.25v5.5A2.25 2.25 0 0 1 16.75 18H3.25A2.25 2.25 0 0 1 1 15.75v-5.5A2.25 2.25 0 0 1 3.25 8H7Z" />
    </svg>
  );
}

/** Amber "Closes in 3 days" pill — renders nothing when > 7 days remain. */
export function UrgencyPill({ deadline, now }: { deadline: string; now: number }) {
  const label = urgencyLabel(deadline, now);
  if (!label) return null;
  return (
    <Badge tone="warning" data-testid="deadline-urgency">
      <span aria-hidden="true" className="size-1.5 rounded-full bg-amber-500" />
      {label}
    </Badge>
  );
}

export function TypePill({ type }: { type: PublicOpportunityCard["type"] }) {
  return <Badge tone="brand">{TYPE_LABELS[type] ?? type}</Badge>;
}

export function OpportunityCard({
  opportunity: o,
  boardQs,
  now,
}: {
  opportunity: PublicOpportunityCard;
  boardQs: string;
  now: number;
}) {
  const extraTopics = o.topics.length - MAX_TOPICS;
  return (
    <article
      data-testid="opportunity-card"
      className="group relative flex min-w-0 flex-col rounded-xl border border-stone-200 bg-white p-5 shadow-sm transition-shadow focus-within:ring-2 focus-within:ring-brand-500 hover:border-stone-300 hover:shadow-md"
    >
      <div className="flex flex-wrap items-center gap-2">
        <TypePill type={o.type} />
        <UrgencyPill deadline={o.deadline} now={now} />
      </div>

      <h2 className="mt-3 text-lg leading-snug font-semibold break-words text-stone-900">
        <Link
          href={listingHref(o.id, boardQs)}
          className="outline-none after:absolute after:inset-0 after:rounded-xl group-hover:text-brand-700"
        >
          {o.title}
        </Link>
      </h2>
      <p className="mt-1 text-sm font-medium break-words text-stone-500">{partnerName(o)}</p>

      <p className="mt-3 line-clamp-3 break-words text-stone-700">{o.summary}</p>

      {o.topics.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-1.5" aria-label="Topics">
          {o.topics.slice(0, MAX_TOPICS).map((t) => (
            <li
              key={t.slug}
              className="rounded-md bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-600"
            >
              {t.name}
            </li>
          ))}
          {extraTopics > 0 && (
            <li className="rounded-md px-1 py-0.5 text-xs font-medium text-stone-400">
              +{extraTopics}
            </li>
          )}
        </ul>
      )}

      <div className="mt-auto pt-4">
        <dl className="space-y-1.5 border-t border-stone-100 pt-4 text-sm text-stone-600">
          <div className="flex min-w-0 items-center gap-2">
            <dt className="sr-only">Location</dt>
            <PinIcon className="shrink-0 text-stone-400" />
            <dd className="min-w-0 truncate">{locationLabel(o)}</dd>
          </div>
          {o.compensation_text && (
            <div className="flex min-w-0 items-center gap-2">
              <dt className="sr-only">Compensation</dt>
              <WalletIcon className="shrink-0 text-stone-400" />
              <dd className="min-w-0 truncate">{o.compensation_text}</dd>
            </div>
          )}
          <div className="flex min-w-0 items-center gap-2">
            <dt className="sr-only">Deadline</dt>
            <CalendarIcon className="shrink-0 text-stone-400" />
            <dd className="font-medium text-stone-800">Apply by {shortDeadline(o.deadline, now)}</dd>
          </div>
        </dl>
      </div>
    </article>
  );
}

export function OpportunityCardSkeleton() {
  return (
    <div className="flex flex-col rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
      <Skeleton className="h-5 w-20 rounded-full" />
      <Skeleton className="mt-4 h-5 w-4/5" />
      <Skeleton className="mt-2 h-4 w-2/5" />
      <Skeleton className="mt-4 h-4 w-full" />
      <Skeleton className="mt-2 h-4 w-11/12" />
      <div className="mt-4 flex gap-1.5">
        <Skeleton className="h-5 w-16" />
        <Skeleton className="h-5 w-20" />
        <Skeleton className="h-5 w-14" />
      </div>
      <div className="mt-5 space-y-2 border-t border-stone-100 pt-4">
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-2/5" />
      </div>
    </div>
  );
}
