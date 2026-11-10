"use client";

import { useState } from "react";
import { ApiError, adminListWorkshops, type AdminWorkshopSummary } from "@/lib/api";
import { adminGetOpportunity } from "@/lib/adminBoard";
import { addFacilitator } from "@/lib/adminFacilitators";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { useAdmin } from "@/components/admin/AdminGate";

/**
 * "Link as facilitator" on a Selected applicant. Links to the listing's
 * `workshop_id` as `co`; with none set, asks which workshop first.
 */
export function LinkFacilitatorButton({
  profileId,
  opportunityId,
}: {
  profileId: number;
  opportunityId: number;
}) {
  const { adminKey, onUnauthorized } = useAdmin();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [workshops, setWorkshops] = useState<AdminWorkshopSummary[] | null>(null);
  const [choice, setChoice] = useState("");

  const fail = (err: unknown) => {
    if (err instanceof ApiError && err.status === 401) {
      onUnauthorized();
      return;
    }
    setError(err instanceof ApiError ? err.message : "Couldn't link — try again.");
  };

  const link = async (workshopId: number, name?: string) => {
    setBusy(true);
    setError(null);
    try {
      await addFacilitator(adminKey, workshopId, { profile_id: profileId, role: "co" });
      const label = name ?? `workshop #${workshopId}`;
      setDone(label);
      setWorkshops(null);
      toast.show(`Linked as co-facilitator of ${label}`, "success");
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const { opportunity } = await adminGetOpportunity(adminKey, opportunityId);
      if (opportunity.workshop_id != null) {
        setBusy(false);
        await link(opportunity.workshop_id);
        return;
      }
      const { workshops: list } = await adminListWorkshops(adminKey);
      setWorkshops(list);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  if (done) {
    return (
      <p data-testid="link-facilitator-done" className="text-xs text-emerald-700">
        Linked to {done}
      </p>
    );
  }

  return (
    <div className="flex flex-col items-end gap-1">
      {workshops === null ? (
        <Button
          variant="secondary"
          size="sm"
          data-testid="link-facilitator-button"
          loading={busy}
          onClick={() => void start()}
        >
          Link as facilitator
        </Button>
      ) : workshops.length === 0 ? (
        <p className="text-xs text-stone-500">No workshops yet — create one on Admin Home first.</p>
      ) : (
        <div className="flex items-center gap-1">
          <select
            aria-label="Workshop to link"
            data-testid="link-facilitator-workshop"
            value={choice}
            onChange={(e) => setChoice(e.target.value)}
            className="rounded-lg border border-stone-300 bg-white px-2 py-1 text-sm"
          >
            <option value="">Choose workshop…</option>
            {workshops.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
          <Button
            size="sm"
            data-testid="link-facilitator-confirm"
            disabled={!choice}
            loading={busy}
            onClick={() => {
              const w = workshops.find((x) => String(x.id) === choice);
              if (w) void link(w.id, w.name);
            }}
          >
            Link
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-xs text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
