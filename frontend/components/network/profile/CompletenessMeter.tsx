import { Card } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { orderedNudges, type Completeness } from "@/lib/network";

/**
 * Completeness meter (0–100 %, api.md §Completeness) with a nudge listing the
 * top three missing items.
 */
export function CompletenessMeter({ completeness }: { completeness: Completeness }) {
  const pct = Math.max(0, Math.min(100, Math.round(completeness.pct)));
  const nudges = orderedNudges(completeness.missing).slice(0, 3);
  return (
    <Card className="p-5" data-testid="completeness-meter">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-semibold text-stone-900">Profile completeness</h2>
        <span className="text-2xl font-semibold tabular-nums text-stone-900">{pct}%</span>
      </div>
      <ProgressBar
        value={pct}
        tone={pct === 100 ? "success" : "brand"}
        label="Profile completeness"
        className="mt-3"
      />
      {nudges.length > 0 ? (
        <div className="mt-4" data-testid="completeness-nudges">
          <p className="text-sm font-medium text-stone-700">
            Complete profiles get matched first. Next steps:
          </p>
          <ul className="mt-2 space-y-1.5">
            {nudges.map((n) => (
              <li key={n} className="flex items-start gap-2 text-sm text-stone-600">
                <span aria-hidden="true" className="mt-1.5 size-1.5 shrink-0 rounded-full bg-brand-500" />
                {n}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="mt-4 text-sm text-emerald-700">
          Your profile is complete — nice work.
        </p>
      )}
    </Card>
  );
}
