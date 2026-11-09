"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import {
  adminListPartners,
  type AdminPartner,
  type PartnerRef,
} from "@/lib/adminPartners";
import { Button } from "@/components/ui/Button";
import { useAdmin } from "@/components/admin/AdminGate";
import { DraftedChip } from "@/components/admin/drafting/DraftedChip";
import { AddPartnerModal } from "@/components/admin/partners/AddPartnerModal";

export interface PartnerSelectProps {
  value: PartnerRef | null;
  onChange: (p: PartnerRef | null) => void;
  /** The drafter's `suggested_partner` — offered as a one-click "add" when set. */
  suggestedNew?: { internal_name: string; display_name: string | null } | null;
  /** Show the "Drafted" chip. */
  drafted?: boolean;
  error?: string;
}

function toRef(p: AdminPartner): PartnerRef {
  return {
    id: p.id,
    internal_name: p.internal_name,
    display_name: p.display_name,
    active: p.active,
  };
}

export function PartnerSelect({
  value,
  onChange,
  suggestedNew,
  drafted,
  error,
}: PartnerSelectProps) {
  const { adminKey, onUnauthorized } = useAdmin();
  const [partners, setPartners] = useState<AdminPartner[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [modalInitial, setModalInitial] = useState<{
    internal_name: string;
    display_name: string | null;
  } | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setPartners((await adminListPartners(adminKey)).partners);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        onUnauthorized();
        return;
      }
      setLoadError("Couldn't load partners.");
    }
  }, [adminKey, onUnauthorized]);

  useEffect(() => {
    void load();
  }, [load]);

  const options = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = (partners ?? []).filter(
      (p) =>
        (p.active || p.id === value?.id) &&
        (!q || p.internal_name.toLowerCase().includes(q)),
    );
    // Current partner may be missing from the fetched list (still loading / failed).
    if (value && !list.some((p) => p.id === value.id) && !q) {
      list.unshift({
        ...value,
        notes: null,
        opportunity_count: 0,
        created_at: "",
        updated_at: "",
      });
    }
    return list;
  }, [partners, query, value]);

  const openModal = (initial: typeof modalInitial) => {
    setModalInitial(initial);
    setModalOpen(true);
  };

  const suggestionVisible =
    !!suggestedNew &&
    !(partners ?? []).some(
      (p) => p.internal_name.toLowerCase() === suggestedNew.internal_name.toLowerCase(),
    );

  return (
    <div data-testid="partner-select" className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <label htmlFor="partner-select-input" className="text-sm font-medium text-stone-700">
          Partner <DraftedChip field="partner" show={!!drafted} />
        </label>
        <Link
          href="/admin/partners/"
          target="_blank"
          data-testid="manage-partners"
          className="text-xs font-medium text-brand-700 hover:underline"
        >
          Manage partners
        </Link>
      </div>

      <input
        type="search"
        data-testid="partner-search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search partners…"
        aria-label="Search partners"
        className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900 placeholder:text-stone-400 focus:border-brand-500"
      />
      <select
        id="partner-select-input"
        data-testid="partner-select-input"
        value={value?.id ?? ""}
        aria-invalid={error ? true : undefined}
        onChange={(e) => {
          if (e.target.value === "") {
            onChange(null);
            return;
          }
          const p = options.find((o) => o.id === Number(e.target.value));
          if (p) onChange(toRef(p));
        }}
        className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-stone-900 focus:border-brand-500"
      >
        <option value="">{partners === null && !loadError ? "Loading partners…" : "No partner"}</option>
        {options.map((p) => (
          <option key={p.id} value={p.id}>
            {p.internal_name}
            {p.active ? "" : " (inactive)"}
          </option>
        ))}
      </select>
      {partners !== null && options.length === 0 && query && (
        <p className="text-xs text-stone-500">No partner matches “{query}”.</p>
      )}
      {loadError && (
        <p role="alert" className="text-xs text-red-600">
          {loadError}{" "}
          <button type="button" className="underline" onClick={() => void load()}>
            Retry
          </button>
        </p>
      )}
      {value && !value.active && (
        <p className="text-xs text-amber-700">
          This partner is inactive — it stays on this listing but can't be chosen elsewhere.
        </p>
      )}

      {suggestionVisible && suggestedNew && (
        <div
          data-testid="suggested-partner"
          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm"
        >
          <span className="text-stone-700">
            Suggested new partner: <strong>{suggestedNew.internal_name}</strong>
          </span>
          <Button
            size="sm"
            variant="secondary"
            data-testid="suggested-partner-add"
            onClick={() => openModal(suggestedNew)}
          >
            Add “{suggestedNew.internal_name}”
          </Button>
        </div>
      )}

      <Button
        size="sm"
        variant="secondary"
        data-testid="add-partner"
        onClick={() => openModal(null)}
      >
        + Add partner
      </Button>

      {error && (
        <p role="alert" data-testid="partner-select-error" className="text-sm text-red-600">
          {error}
        </p>
      )}

      <AddPartnerModal
        open={modalOpen}
        initial={modalInitial}
        onClose={() => setModalOpen(false)}
        onCreated={(p) => {
          setPartners((prev) => [...(prev ?? []), p]);
          setModalOpen(false);
          setQuery("");
          onChange(toRef(p));
        }}
      />
    </div>
  );
}
