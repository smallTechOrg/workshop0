"use client";

import Link from "next/link";
import {
  tokenFromFacilitatorUrl,
  type AdminWorkshopSummary,
} from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Badge, WorkshopStatusBadge } from "@/components/ui/Badge";
import { FacilitatorsButton } from "@/components/admin/facilitators/FacilitatorsButton";
import { CopyButton } from "@/components/ui/CopyButton";
import { cn, formatDate } from "@/lib/format";

export function WorkshopCard({
  workshop,
  justCreated = false,
}: {
  workshop: AdminWorkshopSummary;
  justCreated?: boolean;
}) {
  const adminToken = tokenFromFacilitatorUrl(workshop.facilitator_url);
  // Phase 6 (C7): origin + creator email — admin surface only. Servers that
  // predate the field are treated as admin-created.
  const isPublic = workshop.created_via === "public";
  const creatorEmail = workshop.creator_email ?? null;

  return (
    <Card
      data-testid="workshop-card"
      className={cn("p-5", justCreated && "ring-2 ring-brand-500")}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold text-stone-900">{workshop.name}</h3>
          <p className="mt-0.5 text-sm text-stone-500">
            Created {formatDate(workshop.created_at)} · {workshop.participant_count}{" "}
            {workshop.participant_count === 1 ? "participant" : "participants"} ·{" "}
            {workshop.open_help_count} open help
          </p>
          {creatorEmail && (
            <p className="mt-1 text-sm text-stone-500">
              Created by{" "}
              <a
                data-testid="workshop-creator-email"
                href={`mailto:${creatorEmail}`}
                className="text-stone-700 underline underline-offset-2 hover:text-stone-900"
              >
                {creatorEmail}
              </a>
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge
            data-testid="workshop-origin-badge"
            tone={isPublic ? "brand" : "neutral"}
            title={
              isPublic
                ? "Created by a member of the public from the landing page"
                : "Created from this admin console"
            }
          >
            {isPublic ? "Public" : "Admin"}
          </Badge>
          <WorkshopStatusBadge status={workshop.status} />
        </div>
      </div>

      {justCreated && (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          The facilitator link is the only key to this dashboard — save it now.
        </p>
      )}

      <dl className="mt-4 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <dt className="w-24 shrink-0 text-xs font-medium tracking-wide text-stone-500 uppercase">
            Join link
          </dt>
          <dd className="flex min-w-0 flex-1 items-center gap-2">
            <span
              data-testid="join-link"
              className="min-w-0 flex-1 truncate font-mono text-sm text-stone-700"
            >
              {workshop.join_url}
            </span>
            <CopyButton text={workshop.join_url} aria-label="Copy join link" />
          </dd>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <dt className="w-24 shrink-0 text-xs font-medium tracking-wide text-stone-500 uppercase">
            Facilitator
          </dt>
          <dd className="flex min-w-0 flex-1 items-center gap-2">
            <span
              data-testid="facilitator-link"
              className="min-w-0 flex-1 truncate font-mono text-sm text-stone-700"
            >
              {workshop.facilitator_url}
            </span>
            <CopyButton
              text={workshop.facilitator_url}
              aria-label="Copy facilitator link"
            />
          </dd>
        </div>
      </dl>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Link
          href={`/f/?t=${encodeURIComponent(adminToken)}`}
          className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 text-sm font-medium text-stone-800 shadow-sm transition-colors hover:bg-stone-50"
        >
          Open dashboard
          <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="size-4">
            <path fillRule="evenodd" d="M3 10a.75.75 0 0 1 .75-.75h10.638L10.23 5.29a.75.75 0 1 1 1.04-1.08l5.5 5.25a.75.75 0 0 1 0 1.08l-5.5 5.25a.75.75 0 1 1-1.04-1.08l4.158-3.96H3.75A.75.75 0 0 1 3 10Z" clipRule="evenodd" />
          </svg>
        </Link>
        <FacilitatorsButton workshopId={workshop.id} workshopName={workshop.name} />
      </div>
    </Card>
  );
}
