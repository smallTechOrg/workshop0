import { Badge } from "@/components/ui/Badge";

/** Amber chip on every field the CV drafter pre-filled (capabilities.md C12). */
export function AutofillChip() {
  return (
    <Badge tone="warning" data-testid="autofill-chip">
      <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="size-3">
        <path d="M10 2a.75.75 0 0 1 .75.75v.5a.75.75 0 0 1-1.5 0v-.5A.75.75 0 0 1 10 2Zm0 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z" />
      </svg>
      From your CV — please check
    </Badge>
  );
}
