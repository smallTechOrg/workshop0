import { TYPE_LABELS, shortDeadline, listingHref, type PublicOpportunityCard } from "@/lib/board";

/** Title (slug link), type, partner and deadline of a listing card. */
export function OppSummary({ o }: { o: PublicOpportunityCard }) {
  return (
    <div className="min-w-0">
      {/* Plain <a>: slug URLs live outside the /app basePath. */}
      <a
        href={listingHref(o.slug, "")}
        className="font-semibold text-stone-900 hover:text-brand-700 hover:underline"
      >
        {o.title}
      </a>
      <p className="mt-0.5 text-sm text-stone-500">
        {TYPE_LABELS[o.type]}
        {o.partner_display_name ? ` · ${o.partner_display_name}` : ""}
        {o.status === "open" ? ` · ${shortDeadline(o.deadline)}` : " · Closed"}
      </p>
    </div>
  );
}
