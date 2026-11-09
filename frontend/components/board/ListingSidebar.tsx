"use client";

import { CopyButton } from "@/components/ui/CopyButton";
import { StubAction } from "@/components/ui/StubBadge";
import { longDeadline, type PublicOpportunityDetail } from "@/lib/board";
import { UrgencyPill } from "@/components/board/OpportunityCard";
import { JoinNetworkCta } from "@/components/board/JoinNetworkCta";

/**
 * The listing page's side card. Open → deadline + "Sign in to apply" (labelled
 * stub until Phase 12) + Copy link. Expired/closed → a neutral closed banner
 * and no apply control.
 */
export function ListingSidebar({
  opportunity: o,
  now,
}: {
  opportunity: PublicOpportunityDetail;
  now: number;
}) {
  // A listing can expire while the page is open — trust the clock as well.
  const isOpen = o.status === "open" && Date.parse(o.deadline) > now;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
        {isOpen ? (
          <>
            <p className="text-sm text-stone-500">Applications open until</p>
            <p className="mt-0.5 font-semibold text-stone-900">{longDeadline(o.deadline)}</p>
            <div className="mt-2">
              <UrgencyPill deadline={o.deadline} now={now} />
            </div>
            <div className="mt-4 space-y-2">
              <div data-testid="apply-stub" className="[&>span]:w-full [&>span]:flex-wrap [&>span]:justify-between [&>span]:whitespace-nowrap">
                <StubAction label="Sign in to apply" />
              </div>
              <p className="text-xs text-stone-500">
                Applying arrives with trainer sign-in. Until then, share this listing.
              </p>
            </div>
            <div className="mt-4 flex items-center gap-2 border-t border-stone-100 pt-4">
              <CopyButton
                data-testid="copy-link"
                text={o.public_url}
                label="Copy link"
                className="px-3 py-1.5 text-sm"
              />
              <span className="min-w-0 truncate text-xs text-stone-400">{o.public_url}</span>
            </div>
          </>
        ) : (
          <div
            data-testid="closed-banner"
            role="status"
            className="rounded-lg border border-stone-200 bg-stone-50 px-4 py-3"
          >
            <p className="font-medium text-stone-800">
              Applications for this opportunity have closed.
            </p>
            <p className="mt-1 text-sm text-stone-500">
              Deadline was {longDeadline(o.deadline)}. Browse the board for what&apos;s open now.
            </p>
          </div>
        )}
      </div>

      <JoinNetworkCta variant="card" />
    </div>
  );
}
