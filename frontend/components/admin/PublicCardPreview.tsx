import { cn } from "@/lib/format";
import { typeLabel, type LocationMode, type OpportunityType } from "@/lib/adminBoard";
import { Badge } from "@/components/ui/Badge";

/**
 * Explicit allow-list of what the public board card shows. Internal fields
 * (`partner_internal_name`, `internal_notes`) are deliberately not part of
 * this type, so the preview cannot render them.
 */
export interface PublicCardPreviewData {
  title: string;
  type: OpportunityType;
  summary: string;
  partner_display_name: string;
  topics: { slug: string; name: string }[];
  location_mode: LocationMode;
  city: string;
  compensation_text: string;
  /** ISO timestamp, or null while the deadline field is empty/invalid. */
  deadline: string | null;
}

function locationText(mode: LocationMode, city: string): string {
  const c = city.trim();
  if (mode === "remote") return "Remote";
  const label = mode === "onsite" ? "Onsite" : "Hybrid";
  return c ? `${c} · ${label}` : label;
}

/** Live preview of the board card, mirroring C10's card anatomy. */
export function PublicCardPreview({
  data,
  now = Date.now(),
}: {
  data: PublicCardPreviewData;
  now?: number;
}) {
  const shown = data.topics.slice(0, 4);
  const extra = data.topics.length - shown.length;
  const deadlineMs = data.deadline ? Date.parse(data.deadline) : NaN;
  const daysLeft = Number.isNaN(deadlineMs) ? null : (deadlineMs - now) / 86400000;
  const daysN = daysLeft === null ? 0 : Math.max(1, Math.ceil(daysLeft));

  return (
    <article
      data-testid="opp-public-preview"
      className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm"
    >
      <div className="flex items-center justify-between gap-2">
        <Badge tone="brand">{typeLabel(data.type)}</Badge>
        {daysLeft !== null && daysLeft > 0 && daysLeft <= 7 && (
          <Badge tone="warning">
            Closes in {daysN} day{daysN === 1 ? "" : "s"}
          </Badge>
        )}
      </div>
      <h3
        className={cn(
          "mt-2 text-base leading-snug font-semibold break-words",
          data.title.trim() ? "text-stone-900" : "text-stone-400 italic",
        )}
      >
        {data.title.trim() || "Untitled opportunity"}
      </h3>
      <p className="mt-0.5 text-sm text-stone-600">
        {data.partner_display_name.trim() || "smallTech partner network"}
      </p>
      <p
        className={cn(
          "mt-2 text-sm break-words",
          data.summary.trim() ? "text-stone-700" : "text-stone-400 italic",
        )}
      >
        {data.summary.trim() || "Your one-line summary appears here."}
      </p>
      {shown.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {shown.map((t) => (
            <Badge key={t.slug}>{t.name}</Badge>
          ))}
          {extra > 0 && <Badge>+{extra}</Badge>}
        </div>
      )}
      <dl className="mt-3 space-y-1 text-sm text-stone-600">
        <div className="flex gap-1.5">
          <dt className="sr-only">Location</dt>
          <dd>📍 {locationText(data.location_mode, data.city)}</dd>
        </div>
        {data.compensation_text.trim() && (
          <div className="flex gap-1.5">
            <dt className="sr-only">Compensation</dt>
            <dd>💼 {data.compensation_text.trim()}</dd>
          </div>
        )}
        <div className="flex gap-1.5">
          <dt className="sr-only">Deadline</dt>
          <dd className="font-medium text-stone-800">
            {Number.isNaN(deadlineMs)
              ? "Set a deadline"
              : `Apply by ${new Date(deadlineMs).toLocaleDateString(undefined, {
                  day: "numeric",
                  month: "short",
                })}`}
          </dd>
        </div>
      </dl>
    </article>
  );
}
