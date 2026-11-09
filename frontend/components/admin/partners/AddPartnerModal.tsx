"use client";

import { useEffect, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/lib/api";
import {
  adminCreatePartner,
  partnerErrorMessage,
  type AdminPartner,
} from "@/lib/adminPartners";
import { useAdmin } from "@/components/admin/AdminGate";

const INPUT =
  "w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-stone-900 placeholder:text-stone-400 focus:border-brand-500";

export function AddPartnerModal({
  open,
  onClose,
  onCreated,
  initial,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (p: AdminPartner) => void;
  initial?: { internal_name: string; display_name: string | null } | null;
}) {
  const { adminKey, onUnauthorized } = useAdmin();
  const [internal, setInternal] = useState("");
  const [display, setDisplay] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setInternal(initial?.internal_name ?? "");
      setDisplay(initial?.display_name ?? "");
      setNotes("");
      setError(null);
    }
  }, [open, initial]);

  const submit = async () => {
    const n = internal.trim();
    if (n.length < 2) {
      setError("Enter the partner's internal name (at least 2 characters).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body: { internal_name: string; display_name?: string; notes?: string } = {
        internal_name: n,
      };
      if (display.trim()) body.display_name = display.trim();
      if (notes.trim()) body.notes = notes.trim();
      const res = await adminCreatePartner(adminKey, body);
      onCreated(res.partner);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setError(partnerErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Add partner" widthClassName="max-w-lg">
      <form
        data-testid="add-partner-modal"
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div>
          <label htmlFor="ap-internal" className="mb-1 block text-sm font-medium text-stone-700">
            Internal name
          </label>
          <input
            id="ap-internal"
            data-testid="add-partner-internal"
            value={internal}
            maxLength={160}
            onChange={(e) => setInternal(e.target.value)}
            placeholder="Zenvia Learning Pvt Ltd"
            className={INPUT}
          />
          <p className="mt-1 text-xs text-stone-500">Admin-only — never shown publicly.</p>
        </div>
        <div>
          <label htmlFor="ap-display" className="mb-1 block text-sm font-medium text-stone-700">
            Default public name
          </label>
          <input
            id="ap-display"
            data-testid="add-partner-display"
            value={display}
            maxLength={160}
            onChange={(e) => setDisplay(e.target.value)}
            placeholder="A Pune edtech"
            className={INPUT}
          />
          <p className="mt-1 text-xs text-stone-500">
            Optional. Each listing keeps its own public name.
          </p>
        </div>
        <div>
          <label htmlFor="ap-notes" className="mb-1 block text-sm font-medium text-stone-700">
            Notes
          </label>
          <textarea
            id="ap-notes"
            data-testid="add-partner-notes"
            value={notes}
            maxLength={5000}
            rows={3}
            onChange={(e) => setNotes(e.target.value)}
            className={INPUT}
          />
        </div>
        {error && (
          <p role="alert" data-testid="add-partner-error" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" data-testid="add-partner-submit" loading={busy}>
            Add partner
          </Button>
        </div>
      </form>
    </Modal>
  );
}
