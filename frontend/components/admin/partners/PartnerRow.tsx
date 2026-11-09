"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import type { AdminPartner } from "@/lib/adminPartners";

const INPUT =
  "w-full rounded-lg border border-stone-300 bg-white px-2 py-1.5 text-sm text-stone-900 focus:border-brand-500";

export function PartnerRow({
  partner,
  highlight,
  busy,
  onSave,
  onToggle,
}: {
  partner: AdminPartner;
  highlight?: boolean;
  busy?: boolean;
  /** Resolve with an error message to show inline, or null on success. */
  onSave: (
    p: AdminPartner,
    patch: { internal_name: string; display_name: string; notes: string },
  ) => Promise<string | null>;
  onToggle: (p: AdminPartner) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [internal, setInternal] = useState(partner.internal_name);
  const [display, setDisplay] = useState(partner.display_name ?? "");
  const [notes, setNotes] = useState(partner.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const start = () => {
    setInternal(partner.internal_name);
    setDisplay(partner.display_name ?? "");
    setNotes(partner.notes ?? "");
    setErr(null);
    setEditing(true);
  };

  const save = async () => {
    if (internal.trim().length < 2) {
      setErr("Internal name needs at least 2 characters.");
      return;
    }
    setSaving(true);
    const msg = await onSave(partner, { internal_name: internal, display_name: display, notes });
    setSaving(false);
    if (msg) setErr(msg);
    else setEditing(false);
  };

  return (
    <tr
      data-testid="partner-row"
      data-partner-id={partner.id}
      className={highlight ? "bg-brand-50/50 align-top" : "align-top"}
    >
      {editing ? (
        <>
          <td className="px-3 py-2">
            <input
              aria-label="Internal name"
              data-testid="partner-edit-internal"
              value={internal}
              maxLength={160}
              onChange={(e) => setInternal(e.target.value)}
              className={INPUT}
            />
            {err && (
              <p role="alert" data-testid="partner-edit-error" className="mt-1 text-xs text-red-600">
                {err}
              </p>
            )}
          </td>
          <td className="px-3 py-2">
            <input
              aria-label="Public display name"
              data-testid="partner-edit-display"
              value={display}
              maxLength={160}
              onChange={(e) => setDisplay(e.target.value)}
              className={INPUT}
            />
          </td>
          <td className="px-3 py-2">
            <textarea
              aria-label="Notes"
              data-testid="partner-edit-notes"
              value={notes}
              maxLength={5000}
              rows={2}
              onChange={(e) => setNotes(e.target.value)}
              className={INPUT}
            />
          </td>
          <td className="px-3 py-2 text-sm text-stone-600">{partner.opportunity_count}</td>
          <td className="px-3 py-2" />
          <td className="px-3 py-2">
            <div className="flex justify-end gap-1">
              <Button size="sm" loading={saving} data-testid="partner-save" onClick={() => void save()}>
                Save
              </Button>
              <Button size="sm" variant="ghost" disabled={saving} onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </div>
          </td>
        </>
      ) : (
        <>
          <td className="px-3 py-2 text-sm font-medium text-stone-900">{partner.internal_name}</td>
          <td className="px-3 py-2 text-sm text-stone-700">
            {partner.display_name || <span className="text-stone-400">—</span>}
          </td>
          <td className="max-w-xs px-3 py-2 text-sm whitespace-pre-wrap text-stone-600">
            {partner.notes || <span className="text-stone-400">—</span>}
          </td>
          <td className="px-3 py-2 text-sm text-stone-600" data-testid="partner-count">
            {partner.opportunity_count}
          </td>
          <td className="px-3 py-2">
            <button
              type="button"
              role="switch"
              aria-checked={partner.active}
              aria-label={`${partner.internal_name} active`}
              data-testid="partner-active-toggle"
              disabled={busy}
              onClick={() => onToggle(partner)}
              className="disabled:opacity-60"
            >
              <Badge tone={partner.active ? "success" : "neutral"}>
                {partner.active ? "Active" : "Inactive"}
              </Badge>
            </button>
          </td>
          <td className="px-3 py-2 text-right">
            <Button size="sm" variant="ghost" data-testid="partner-edit" onClick={start}>
              Edit
            </Button>
          </td>
        </>
      )}
    </tr>
  );
}
