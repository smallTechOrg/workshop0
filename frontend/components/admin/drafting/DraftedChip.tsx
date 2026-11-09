"use client";

import type { DraftedField } from "@/lib/adminDraft";

/** Amber "Drafted — please check" chip; render next to a field the AI filled. */
export function DraftedChip({ field, show }: { field: DraftedField; show: boolean }) {
  if (!show) return null;
  return (
    <span
      data-testid={`drafted-chip-${field}`}
      className="ml-2 rounded-full bg-amber-100 px-1.5 py-0.5 align-middle text-[11px] font-medium text-amber-800"
    >
      <span data-testid="drafted-chip">Drafted — please check</span>
    </span>
  );
}
