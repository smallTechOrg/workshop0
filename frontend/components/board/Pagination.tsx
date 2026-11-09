"use client";

import { Button } from "@/components/ui/Button";

/** Previous / Next + "Page X of Y". Hidden when everything fits on one page. */
export function Pagination({
  page,
  totalPages,
  onPage,
}: {
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
}) {
  if (totalPages <= 1) return null;
  return (
    <nav
      aria-label="Pagination"
      className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-stone-200 pt-5"
    >
      <Button
        variant="secondary"
        size="sm"
        data-testid="pagination-prev"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        <span aria-hidden="true">←</span> Previous
      </Button>
      <p data-testid="pagination-status" aria-live="polite" className="text-sm text-stone-600 tabular-nums">
        Page {page} of {totalPages}
      </p>
      <Button
        variant="secondary"
        size="sm"
        data-testid="pagination-next"
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
      >
        Next <span aria-hidden="true">→</span>
      </Button>
    </nav>
  );
}
