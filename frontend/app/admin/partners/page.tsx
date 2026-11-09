"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  adminListPartners,
  adminPatchPartner,
  partnerErrorMessage,
  type AdminPartner,
} from "@/lib/adminPartners";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { AdminGate, useAdmin } from "@/components/admin/AdminGate";
import { AdminHeader } from "@/components/admin/AdminHeader";
import { AddPartnerModal } from "@/components/admin/partners/AddPartnerModal";
import { PartnerRow } from "@/components/admin/partners/PartnerRow";

function PartnersManager() {
  const { adminKey, onUnauthorized } = useAdmin();
  const toast = useToast();

  const [partners, setPartners] = useState<AdminPartner[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [highlightId, setHighlightId] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<AdminPartner | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setPartners((await adminListPartners(adminKey)).partners);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setLoadError("Couldn't load partners — check your connection and try again.");
    }
  }, [adminKey, onUnauthorized]);

  useEffect(() => {
    void load();
  }, [load]);

  const replace = (p: AdminPartner) =>
    setPartners((prev) => (prev ? prev.map((x) => (x.id === p.id ? p : x)) : prev));

  const save = async (
    p: AdminPartner,
    patch: { internal_name: string; display_name: string; notes: string },
  ): Promise<string | null> => {
    try {
      const res = await adminPatchPartner(adminKey, p.id, {
        internal_name: patch.internal_name.trim(),
        display_name: patch.display_name.trim(),
        notes: patch.notes.trim(),
      });
      replace(res.partner);
      toast.show("Partner saved", "success");
      return null;
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return "Session expired.";
      }
      return partnerErrorMessage(err);
    }
  };

  const setActive = async (p: AdminPartner, active: boolean) => {
    setTogglingId(p.id);
    try {
      const res = await adminPatchPartner(adminKey, p.id, { active });
      replace(res.partner);
      toast.show(
        active ? `“${p.internal_name}” is active again` : `“${p.internal_name}” deactivated`,
        "success",
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      toast.show(partnerErrorMessage(err), "error");
    } finally {
      setTogglingId(null);
    }
  };

  return (
    <main data-testid="partners-page" className="mx-auto max-w-5xl px-4 py-8">
      <AdminHeader current="partners" />

      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-stone-900">Partners</h1>
          <p className="mt-1 text-sm text-stone-500">
            Organisations behind listings. Internal names are admin-only; the public name is set
            per listing.
            {partners && <> {partners.length} partners.</>}
          </p>
        </div>
        <Button data-testid="add-partner" onClick={() => setAddOpen(true)}>
          + Add partner
        </Button>
      </div>

      {loadError ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {loadError}
          <Button variant="secondary" size="sm" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      ) : partners === null ? (
        <div className="space-y-2" aria-label="Loading partners">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : partners.length === 0 ? (
        <EmptyState
          icon="🤝"
          title="No partners yet — add the first one."
          hint="Link listings to the organisation behind them."
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white shadow-sm">
          <table className="w-full text-left">
            <thead className="border-b border-stone-200 bg-stone-50 text-xs tracking-wide text-stone-500 uppercase">
              <tr>
                <th className="px-3 py-2 font-semibold">Internal name</th>
                <th className="px-3 py-2 font-semibold">Public display name</th>
                <th className="px-3 py-2 font-semibold">Notes</th>
                <th className="px-3 py-2 font-semibold">Listings</th>
                <th className="px-3 py-2 font-semibold">Status</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {partners.map((p) => (
                <PartnerRow
                  key={p.id}
                  partner={p}
                  highlight={p.id === highlightId}
                  busy={togglingId === p.id}
                  onSave={save}
                  onToggle={setConfirm}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AddPartnerModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onCreated={(p) => {
          setPartners((prev) => [...(prev ?? []), p]);
          setHighlightId(p.id);
          setAddOpen(false);
          toast.show(`Added “${p.internal_name}”`, "success");
        }}
      />

      <ConfirmDialog
        open={confirm !== null}
        title={
          confirm
            ? `${confirm.active ? "Deactivate" : "Reactivate"} “${confirm.internal_name}”?`
            : "Change partner status?"
        }
        body={
          confirm?.active
            ? "It will no longer be offered when editing other listings; listings already linked keep it."
            : "It will be offered again when editing listings."
        }
        confirmLabel={confirm?.active ? "Deactivate" : "Reactivate"}
        danger={!!confirm?.active}
        busy={confirm !== null && togglingId === confirm.id}
        onCancel={() => setConfirm(null)}
        onConfirm={async () => {
          if (!confirm) return;
          await setActive(confirm, !confirm.active);
          setConfirm(null);
        }}
      />
    </main>
  );
}

export default function AdminPartnersPage() {
  return (
    <AdminGate purpose="to manage partners">
      <PartnersManager />
    </AdminGate>
  );
}
