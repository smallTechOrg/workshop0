import { Badge, type BadgeProps, type BadgeTone } from "@/components/ui/Badge";
import { STATUS_LABELS, type OpportunityStatus } from "@/lib/adminBoard";

const TONES: Record<OpportunityStatus, BadgeTone> = {
  draft: "neutral",
  open: "success",
  expired: "warning",
  closed: "danger",
};

/** Effective-status pill for an opportunity (admin surfaces). */
export function OpportunityStatusPill({
  status,
  ...rest
}: { status: OpportunityStatus } & Omit<BadgeProps, "tone">) {
  return (
    <Badge tone={TONES[status] ?? "neutral"} {...rest}>
      {status === "open" && (
        <span aria-hidden="true" className="size-1.5 rounded-full bg-emerald-500" />
      )}
      {STATUS_LABELS[status] ?? status}
    </Badge>
  );
}
