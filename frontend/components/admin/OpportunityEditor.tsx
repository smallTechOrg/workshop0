"use client";

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@/lib/api";
import { adminListPartners, type PartnerRef } from "@/lib/adminPartners";
import type { DraftResponse, DraftedField } from "@/lib/adminDraft";
import { COMPENSATION_UNITS, CURRENCIES, type CompensationUnit, type Currency } from "@/lib/compensation";
import { cn, useNowTick } from "@/lib/format";
import {
  MIN_LEVELS,
  type MinLevel,
  LOCATION_MODES,
  OPPORTUNITY_TYPES,
  adminCreateOpportunity,
  adminPatchOpportunity,
  parseFieldError,
  type ActivityItem,
  type AdminOpportunity,
  type AdminTopic,
  type LocationMode,
  type OpportunityBody,
  type OpportunityType,
  type StoredStatus,
} from "@/lib/adminBoard";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { CopyButton } from "@/components/ui/CopyButton";
import { Markdown } from "@/components/ui/Markdown";
import { SuggestedTrainersPanel } from "@/components/admin/matching/SuggestedTrainersPanel";
import { useToast } from "@/components/ui/Toast";
import { adminListWorkshops, type AdminWorkshopSummary } from "@/lib/api";
import { useAdmin } from "@/components/admin/AdminGate";
import { ActivityList } from "@/components/admin/ActivityList";
import { PasteToFill } from "@/components/admin/drafting/PasteToFill";
import { DraftedChip } from "@/components/admin/drafting/DraftedChip";
import { PartnerSelect } from "@/components/admin/partners/PartnerSelect";
import { LockIcon } from "@/components/admin/LockIcon";
import { OpportunityStatusPill } from "@/components/admin/OpportunityStatusPill";
import { PublicCardPreview } from "@/components/admin/PublicCardPreview";
import { TopicPicker } from "@/components/admin/TopicPicker";
import { LocationsInput, type LocationsInputHandle } from "@/components/admin/LocationsInput";
import { LOCATIONS_MAX, locationsOf, type Location } from "@/lib/locations";

// ---------------------------------------------------------------------------
// Form model
// ---------------------------------------------------------------------------

interface FormState {
  title: string;
  type: OpportunityType;
  summary: string;
  description_md: string;
  topic_ids: number[];
  location_mode: LocationMode;
  /** Kept while Remote (sent as `[]`) so switching back restores the chips. */
  locations: Location[];
  starts_on: string;
  ends_on: string;
  duration_text: string;
  compensation_min: string;
  compensation_max: string;
  compensation_currency: "" | Currency;
  compensation_unit: "" | CompensationUnit;
  compensation_text: string;
  /** Phase 12 admin-only matching fields. */
  budget_min: string;
  budget_max: string;
  budget_currency: "" | Currency;
  budget_unit: "" | CompensationUnit;
  min_level: "" | MinLevel;
  /** `<input type="datetime-local">` value, in the admin's local time zone. */
  deadline_local: string;
  partner_display_name: string;
  partner: PartnerRef | null;
  internal_notes: string;
  workshop_id: number | null;
}

type BodyKey = Exclude<keyof OpportunityBody, "status">;

const BODY_KEYS: BodyKey[] = [
  "title",
  "type",
  "summary",
  "description_md",
  "topic_ids",
  "location_mode",
  "locations",
  "starts_on",
  "ends_on",
  "duration_text",
  "compensation_min",
  "compensation_max",
  "compensation_currency",
  "compensation_unit",
  "compensation_text",
  "budget_min",
  "budget_max",
  "budget_currency",
  "budget_unit",
  "min_level",
  "deadline",
  "partner_display_name",
  "partner_id",
  "workshop_id",
  "internal_notes",
];

/** Fields whose `"<field>: …"` errors render inline (api field names). */
const INLINE_FIELDS = new Set<string>(BODY_KEYS);

const pad = (n: number) => String(n).padStart(2, "0");

function toLocalInput(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function isoToLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : toLocalInput(d);
}

/** Local datetime-input value → ISO 8601 UTC with `Z`, seconds precision. */
function localInputToIso(v: string): string | null {
  if (!v.trim()) return null;
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString().replace(/\.\d{3}Z$/, "Z");
}

function defaultDeadline(): string {
  const d = new Date();
  d.setDate(d.getDate() + 30);
  d.setHours(23, 59, 0, 0);
  return toLocalInput(d);
}

function emptyForm(): FormState {
  return {
    title: "",
    type: "workshop",
    summary: "",
    description_md: "",
    topic_ids: [],
    location_mode: "remote",
    locations: [],
    starts_on: "",
    ends_on: "",
    duration_text: "",
    compensation_min: "",
    compensation_max: "",
    compensation_currency: "",
    compensation_unit: "",
    compensation_text: "",
    budget_min: "",
    budget_max: "",
    budget_currency: "",
    budget_unit: "",
    min_level: "",
    deadline_local: defaultDeadline(),
    partner_display_name: "",
    partner: null,
    workshop_id: null,
    internal_notes: "",
  };
}

function formFrom(o: AdminOpportunity): FormState {
  return {
    title: o.title ?? "",
    type: o.type,
    summary: o.summary ?? "",
    description_md: o.description_md ?? "",
    topic_ids: o.topics.map((t) => t.id),
    location_mode: o.location_mode,
    locations: locationsOf(o).map((l) => ({ city: l.city, country: l.country ?? null })),
    starts_on: o.starts_on ?? "",
    ends_on: o.ends_on ?? "",
    duration_text: o.duration_text ?? "",
    compensation_min: o.compensation_min != null ? String(o.compensation_min) : "",
    compensation_max: o.compensation_max != null ? String(o.compensation_max) : "",
    compensation_currency: o.compensation_currency ?? "",
    compensation_unit: o.compensation_unit ?? "",
    compensation_text: o.compensation_text ?? "",
    budget_min: o.budget_min != null ? String(o.budget_min) : "",
    budget_max: o.budget_max != null ? String(o.budget_max) : "",
    budget_currency: o.budget_currency ?? "",
    budget_unit: o.budget_unit ?? "",
    min_level: o.min_level ?? "",
    deadline_local: isoToLocalInput(o.deadline),
    partner_display_name: o.partner_display_name ?? "",
    partner: o.partner ?? null,
    workshop_id: o.workshop_id ?? null,
    internal_notes: o.internal_notes ?? "",
  };
}

/** "" / junk → null; otherwise the integer amount. */
function amount(s: string): number | null {
  const t = s.trim();
  if (t === "" || !/^\d+$/.test(t)) return null;
  return Number(t);
}

/** Inline budget errors (admin-only matching budget; same shape rules as compensation). */
function budgetErrors(f: FormState): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of ["budget_min", "budget_max"] as const) {
    const v = f[k].trim();
    if (v !== "" && !/^\d+$/.test(v)) out[k] = "Whole numbers only";
  }
  const mn = amount(f.budget_min);
  const mx = amount(f.budget_max);
  if (mn !== null && mx !== null && mx < mn && !out.budget_max) out.budget_max = "Maximum must be at least the minimum";
  if (f.budget_min.trim() !== "" || f.budget_max.trim() !== "") {
    if (!f.budget_currency) out.budget_currency = "Choose a currency for the budget";
    if (!f.budget_unit) out.budget_unit = "Choose a unit (per hour, day, …)";
  } else if (f.budget_currency || f.budget_unit) {
    out.budget_min = "Enter an amount, or clear the currency and unit";
  }
  return out;
}

/** Inline compensation errors (keyed by API field), mirroring api.md's rules. */
function compensationErrors(f: FormState): Record<string, string> {
  const out: Record<string, string> = {};
  const check = (key: "compensation_min" | "compensation_max") => {
    const t = f[key].trim();
    if (t === "") return;
    const n = amount(t);
    if (n === null || n > 100000000) out[key] = "Enter a whole amount between 0 and 100,000,000";
  };
  check("compensation_min");
  check("compensation_max");
  const mn = amount(f.compensation_min);
  const mx = amount(f.compensation_max);
  const hasAmount = f.compensation_min.trim() !== "" || f.compensation_max.trim() !== "";
  if (mn !== null && mx !== null && mx < mn && !out.compensation_max) {
    out.compensation_max = "Maximum must be at least the minimum";
  }
  if (hasAmount) {
    if (!f.compensation_currency) out.compensation_currency = "Choose a currency for the amount";
    if (!f.compensation_unit) out.compensation_unit = "Choose a unit (per hour, day, …)";
  } else if (f.compensation_currency || f.compensation_unit) {
    out.compensation_min = "Enter an amount, or clear the currency and unit";
  }
  return out;
}

const opt = (s: string): string | null => (s.trim() === "" ? null : s.trim());

/** Normalise the form into the API body (trimmed; blank optional → null). */
function toBody(f: FormState): Omit<OpportunityBody, "status"> {
  return {
    title: f.title.trim(),
    type: f.type,
    summary: f.summary.trim(),
    // Non-nullable string in the contract (AdminOpportunity) — send "" when blank.
    description_md: f.description_md.trim(),
    topic_ids: f.topic_ids,
    location_mode: f.location_mode,
    locations: f.location_mode === "remote" ? [] : f.locations,
    starts_on: opt(f.starts_on),
    ends_on: opt(f.ends_on),
    duration_text: opt(f.duration_text),
    compensation_min: amount(f.compensation_min),
    compensation_max: amount(f.compensation_max),
    compensation_currency: f.compensation_currency || null,
    compensation_unit: f.compensation_unit || null,
    compensation_text: opt(f.compensation_text),
    budget_min: amount(f.budget_min),
    budget_max: amount(f.budget_max),
    budget_currency: f.budget_currency || null,
    budget_unit: f.budget_unit || null,
    min_level: f.min_level || null,
    deadline: localInputToIso(f.deadline_local),
    partner_display_name: opt(f.partner_display_name),
    partner_id: f.partner?.id ?? null,
    workshop_id: f.type === "cofacilitation" ? f.workshop_id : null,
    internal_notes: opt(f.internal_notes),
  };
}

function sameValue(a: unknown, b: unknown, key?: string): boolean {
  if (key === "locations") return JSON.stringify(a) === JSON.stringify(b); // order matters
  if (Array.isArray(a) && Array.isArray(b)) {
    return [...a].sort().join(",") === [...b].sort().join(",");
  }
  return a === b;
}

/** Only the fields that changed — so e.g. an untouched deadline is never re-sent. */
function diffBody(initial: FormState, current: FormState): Partial<OpportunityBody> {
  const a = toBody(initial);
  const b = toBody(current);
  const out: Partial<OpportunityBody> = {};
  for (const k of BODY_KEYS) {
    if (!sameValue(a[k], b[k], k)) (out as Record<string, unknown>)[k] = b[k];
  }
  return out;
}

/** Form field backing each API body key (only the deadline differs). */
const FORM_KEY: Record<BodyKey, keyof FormState> = {
  title: "title",
  type: "type",
  summary: "summary",
  description_md: "description_md",
  topic_ids: "topic_ids",
  location_mode: "location_mode",
  locations: "locations",
  starts_on: "starts_on",
  ends_on: "ends_on",
  duration_text: "duration_text",
  compensation_min: "compensation_min",
  compensation_max: "compensation_max",
  compensation_currency: "compensation_currency",
  compensation_unit: "compensation_unit",
  compensation_text: "compensation_text",
  budget_min: "budget_min",
  budget_max: "budget_max",
  budget_currency: "budget_currency",
  budget_unit: "budget_unit",
  min_level: "min_level",
  deadline: "deadline_local",
  partner_display_name: "partner_display_name",
  partner_id: "partner",
  workshop_id: "workshop_id",
  internal_notes: "internal_notes",
};

const FIELD_LABEL: Record<BodyKey, string> = {
  title: "Title",
  type: "Type",
  summary: "Summary",
  description_md: "Description",
  topic_ids: "Topics",
  location_mode: "Location",
  locations: "Locations",
  starts_on: "Starts on",
  ends_on: "Ends on",
  duration_text: "Duration",
  compensation_min: "Compensation minimum",
  compensation_max: "Compensation maximum",
  compensation_currency: "Compensation currency",
  compensation_unit: "Compensation unit",
  compensation_text: "Compensation note",
  budget_min: "Budget minimum",
  budget_max: "Budget maximum",
  budget_currency: "Budget currency",
  budget_unit: "Budget unit",
  min_level: "Minimum level",
  deadline: "Application deadline",
  partner_display_name: "Public partner name",
  partner_id: "Partner",
  workshop_id: "Workshop",
  internal_notes: "Internal notes",
};

/**
 * Re-seed from a fresh server copy WITHOUT losing anything the admin typed.
 * A field keeps the admin's value when they had edited it (it differed from the
 * previous server copy) and the new server copy did not adopt that value — i.e.
 * the edit was never sent (Close / Unpublish send only the status) or was
 * refused. Every other field takes the server value.
 *
 * `discard` holds values the server explicitly refused (422). After a later
 * successful action the admin has moved on, so a field still holding its
 * refused value takes the server value instead — otherwise e.g. a refused past
 * deadline would stay "Unsaved" and ride along on the next Reopen.
 */
function rebase(
  server: FormState,
  prevInitial: FormState,
  prevForm: FormState,
  discard: RefusedValues = {},
): FormState {
  const s = toBody(server);
  const i = toBody(prevInitial);
  const f = toBody(prevForm);
  const out: FormState = { ...server };
  for (const k of BODY_KEYS) {
    const edited = !sameValue(f[k], i[k], k);
    const adopted = sameValue(f[k], s[k], k);
    const refused = k in discard && sameValue(f[k], discard[k], k);
    if (edited && !adopted && !refused) {
      const fk = FORM_KEY[k];
      (out as unknown as Record<string, unknown>)[fk] = prevForm[fk];
    }
  }
  return out;
}

/** Values the server refused with a 422, keyed by API field. */
type RefusedValues = Partial<Record<BodyKey, unknown>>;

/** API field names with unsent edits — read by `Field` to mark itself "Unsaved". */
const UnsavedFieldsContext = createContext<ReadonlySet<string>>(new Set());

/** Which drafted-chip a form field belongs to. */
const DRAFT_FIELD_OF: Partial<Record<keyof FormState, DraftedField>> = {
  title: "title",
  type: "type",
  summary: "summary",
  description_md: "description_md",
  topic_ids: "topics",
  location_mode: "location",
  locations: "location",
  starts_on: "dates",
  ends_on: "dates",
  duration_text: "duration_text",
  deadline_local: "deadline",
  compensation_min: "compensation",
  compensation_max: "compensation",
  compensation_currency: "compensation",
  compensation_unit: "compensation",
  compensation_text: "compensation",
  partner: "partner",
  partner_display_name: "partner_display_name",
  internal_notes: "internal_notes",
};

type Action = "save_draft" | "publish" | "save" | "close" | "unpublish" | "reopen";

const TARGET: Record<Action, StoredStatus | null> = {
  save_draft: "draft",
  publish: "open",
  save: null,
  close: "closed",
  unpublish: "draft",
  reopen: "open",
};

const SUCCESS: Record<Action, string> = {
  save_draft: "Draft saved",
  publish: "Published — it's on the board now",
  save: "Changes saved",
  close: "Closed — it's off the board",
  unpublish: "Unpublished — back to draft",
  reopen: "Reopened — it's back on the board",
};

// ---------------------------------------------------------------------------
// Small field helpers
// ---------------------------------------------------------------------------

const inputCls = (invalid?: boolean) =>
  cn(
    "w-full rounded-lg border bg-white px-3 py-2 text-stone-900 placeholder:text-stone-400 focus:border-brand-500",
    invalid ? "border-red-400" : "border-stone-300",
  );

function Field({
  id,
  label,
  error,
  errorField,
  hint,
  required,
  aside,
  chip,
  children,
}: {
  id: string;
  label: string;
  error?: string;
  /** API field name — the inline error carries `opp-field-error-<field>`. */
  errorField: string;
  hint?: React.ReactNode;
  required?: boolean;
  aside?: React.ReactNode;
  chip?: React.ReactNode;
  children: React.ReactNode;
}) {
  const unsaved = useContext(UnsavedFieldsContext).has(errorField);
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="block text-sm font-medium text-stone-700">
          {label}
          {required && (
            <span aria-hidden="true" className="ml-0.5 text-red-500">
              *
            </span>
          )}
          {chip}
          {unsaved && (
            <span
              data-testid={`opp-unsaved-${errorField}`}
              className="ml-2 rounded-full bg-amber-100 px-1.5 py-0.5 align-middle text-[11px] font-medium text-amber-800"
            >
              Unsaved
            </span>
          )}
        </label>
        {aside}
      </div>
      {children}
      {hint && !error && <p className="mt-1 text-xs text-stone-500">{hint}</p>}
      {error && (
        <p
          id={`${id}-error`}
          role="alert"
          data-testid={`opp-field-error-${errorField}`}
          className="mt-1 text-sm text-red-600"
        >
          {error}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Editor
// ---------------------------------------------------------------------------

export function OpportunityEditor({
  opportunity,
  activity,
  topics,
  onSaved,
}: {
  opportunity: AdminOpportunity | null;
  activity: ActivityItem[];
  topics: AdminTopic[];
  onSaved: (opp: AdminOpportunity, created: boolean) => void;
}) {
  const { adminKey, onUnauthorized } = useAdmin();
  const toast = useToast();
  const now = useNowTick(30000);

  const [initial, setInitial] = useState<FormState>(() =>
    opportunity ? formFrom(opportunity) : emptyForm(),
  );
  const [form, setForm] = useState<FormState>(initial);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<React.ReactNode>(null);
  const [busy, setBusy] = useState<Action | null>(null);
  const [drafted, setDrafted] = useState<ReadonlySet<DraftedField>>(new Set());
  const [draftApplied, setDraftApplied] = useState(false);
  const [suggestedNew, setSuggestedNew] = useState<{
    internal_name: string;
    display_name: string | null;
  } | null>(null);
  const [workshops, setWorkshops] = useState<AdminWorkshopSummary[] | null>(null);
  const [descTab, setDescTab] = useState<"write" | "preview">("write");

  // Latest form/initial, read by the re-seed effect without re-running it.
  const formRef = useRef(form);
  formRef.current = form;
  const initialRef = useRef(initial);
  initialRef.current = initial;
  const seededId = useRef<number | null>(opportunity?.id ?? null);
  // Values the server refused (422), and whether the next re-seed follows a
  // successful action (→ drop fields still holding a refused value).
  const refusedRef = useRef<RefusedValues>({});
  const dropRefusedRef = useRef(false);

  // Re-seed whenever the server copy changes (load / after an action / Activity
  // refresh). Same listing → rebase: unsent edits stay in the form, still marked
  // unsaved (nothing typed is ever lost). A different listing → fresh form.
  useEffect(() => {
    if (!opportunity) return;
    const server = formFrom(opportunity);
    const sameListing = seededId.current === opportunity.id;
    seededId.current = opportunity.id;
    const discard = sameListing && dropRefusedRef.current ? refusedRef.current : {};
    if (!sameListing || dropRefusedRef.current) {
      refusedRef.current = {};
      dropRefusedRef.current = false;
    }
    setInitial(server);
    setForm(sameListing ? rebase(server, initialRef.current, formRef.current, discard) : server);
    if (!sameListing) {
      setFieldErrors({});
      setFormError(null);
    }
  }, [opportunity]);

  const isNew = opportunity === null;
  const status = opportunity?.status ?? null;
  const pendingNow = useMemo(() => diffBody(initial, form), [initial, form]);
  const pending = pendingNow;
  const locationsRef = useRef<LocationsInputHandle>(null);
  const dirty = isNew ? true : Object.keys(pending).length > 0;
  const unsavedFields = useMemo<ReadonlySet<string>>(
    () => (isNew ? new Set() : new Set(Object.keys(pending))),
    [isNew, pending],
  );
  const unsavedLabels = (Object.keys(pending) as BodyKey[])
    .filter((k) => k in FIELD_LABEL)
    .map((k) => FIELD_LABEL[k]);

  useEffect(() => {
    if (isNew || !dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [isNew, dirty]);

  const isCofac = form.type === "cofacilitation";
  useEffect(() => {
    if (!isCofac || workshops !== null) return;
    adminListWorkshops(adminKey)
      .then((r) => setWorkshops(r.workshops))
      .catch(() => setWorkshops([]));
  }, [isCofac, workshops, adminKey]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    const chip = DRAFT_FIELD_OF[key];
    if (chip) {
      setDrafted((d) => {
        if (!d.has(chip)) return d;
        const next = new Set(d);
        next.delete(chip);
        return next;
      });
    }
    const apiKey = key === "deadline_local" ? "deadline" : key === "partner" ? "partner_id" : key;
    // Editing a refused field to a new value makes it a fresh edit again.
    delete refusedRef.current[apiKey as BodyKey];
    if (fieldErrors[apiKey]) {
      setFieldErrors((e) => {
        const next = { ...e };
        delete next[apiKey];
        return next;
      });
    }
  };

  const [compShow, setCompShow] = useState(false);
  const compErrs = compShow ? compensationErrors(form) : {};

  /** Prefill from a DraftResponse. Never touches status — the draft only fills the form. */
  const applyDraft = (r: DraftResponse) => {
    const d = r.draft;
    const has = (f: DraftedField) => r.drafted_fields.includes(f);
    const slugToId = new Map(topics.map((t) => [t.slug, t.id]));
    const patch: Partial<FormState> = {};
    if (has("title") && d.title != null) patch.title = d.title;
    if (has("type") && d.type) patch.type = d.type;
    if (has("summary") && d.summary != null) patch.summary = d.summary;
    if (has("description_md") && d.description_md != null) patch.description_md = d.description_md;
    if (has("topics")) {
      const ids = d.topic_slugs.map((sl) => slugToId.get(sl)).filter((x): x is number => x !== undefined);
      if (ids.length > 0) patch.topic_ids = ids.slice(0, 8);
    }
    if (has("location") && d.location_mode) {
      patch.location_mode = d.location_mode;
      patch.locations =
        d.location_mode === "remote"
          ? []
          : (d.locations ?? []).slice(0, LOCATIONS_MAX).map((l) => ({ city: l.city, country: l.country ?? null }));
    }
    if (has("dates")) {
      if (d.starts_on) patch.starts_on = d.starts_on;
      if (d.ends_on) patch.ends_on = d.ends_on;
    }
    if (has("duration_text") && d.duration_text != null) patch.duration_text = d.duration_text;
    if (has("deadline") && d.deadline_on && /^\d{4}-\d{2}-\d{2}$/.test(d.deadline_on)) {
      patch.deadline_local = `${d.deadline_on}T23:59`;
    }
    if (has("compensation")) {
      patch.compensation_min = d.compensation_min != null ? String(d.compensation_min) : "";
      patch.compensation_max = d.compensation_max != null ? String(d.compensation_max) : "";
      patch.compensation_currency = d.compensation_currency ?? "";
      patch.compensation_unit = d.compensation_unit ?? "";
      if (d.compensation_text != null) patch.compensation_text = d.compensation_text;
    }
    if (has("partner_display_name") && d.partner_display_name != null) {
      patch.partner_display_name = d.partner_display_name;
    }
    if (has("internal_notes") && d.internal_notes != null) patch.internal_notes = d.internal_notes;
    setForm((f) => ({ ...f, ...patch }));
    setCompShow(false);
    setFieldErrors({});
    setDrafted(new Set(r.drafted_fields));
    setDraftApplied(true);

    if (has("partner")) {
      setSuggestedNew(d.partner_id == null ? d.suggested_partner : null);
      if (d.partner_id != null) {
        const pid = d.partner_id;
        adminListPartners(adminKey)
          .then(({ partners }) => {
            const p = partners.find((x) => x.id === pid);
            if (p) setForm((f) => ({ ...f, partner: { id: p.id, internal_name: p.internal_name, display_name: p.display_name, active: p.active } }));
          })
          .catch(() => {
            /* the chip stays; the admin can pick the partner by hand */
          });
      }
    }
  };

  /** Typed input that a draft would overwrite (new listings only start empty). */
  const hasUserInput =
    form.title.trim() !== "" ||
    form.summary.trim() !== "" ||
    form.description_md.trim() !== "" ||
    form.topic_ids.length > 0 ||
    form.internal_notes.trim() !== "" ||
    form.partner !== null ||
    form.compensation_min !== "" ||
    form.compensation_max !== "" ||
    form.duration_text.trim() !== "";

  const onPartnerChange = (p: PartnerRef | null) => {
    setForm((f) => ({
      ...f,
      partner: p,
      partner_display_name:
        p && f.partner_display_name.trim() === "" && p.display_name ? p.display_name : f.partner_display_name,
    }));
    setSuggestedNew(null);
    setDrafted((d) => {
      if (!d.has("partner")) return d;
      const next = new Set(d);
      next.delete("partner");
      return next;
    });
    delete refusedRef.current.partner_id;
    setFieldErrors((e) => {
      if (!e.partner_id) return e;
      const next = { ...e };
      delete next.partner_id;
      return next;
    });
  };

  const topicById = useMemo(() => new Map(topics.map((t) => [t.id, t])), [topics]);

  const previewTopics = form.topic_ids
    .map((id) => topicById.get(id) ?? opportunity?.topics.find((t) => t.id === id))
    .filter((t): t is NonNullable<typeof t> => Boolean(t))
    .map((t) => ({ slug: t.slug, name: t.name }));

  const deadlineIso = localInputToIso(form.deadline_local);

  const run = async (action: Action) => {
    setFieldErrors({});
    setFormError(null);
    // A typed-but-unadded city is committed before anything is sent.
    const committed = locationsRef.current?.commit() ?? null;
    const sent: FormState = committed ? { ...form, locations: committed } : form;
    const pending = committed ? diffBody(initial, sent) : pendingNow;
    const target = TARGET[action];

    const statusOnlyAction = action === "close" || action === "unpublish";
    if (!statusOnlyAction) {
      const ce = compensationErrors(form);
      if (Object.keys(ce).length > 0) {
        setCompShow(true);
        setFieldErrors(ce);
        document.getElementById("opp-compensation-min")?.scrollIntoView?.({ behavior: "smooth", block: "center" });
        return;
      }
    }

    // Close / Unpublish take a listing OFF the board: they send ONLY the status
    // change, never pending edits (a refused past deadline must not ride along
    // and get saved). Save / Publish / Reopen send the pending edits too, so
    // "extend the deadline + Reopen" is one click.
    const statusOnly = action === "close" || action === "unpublish";
    let body: Partial<OpportunityBody>;
    let keptUnsent = false;
    if (isNew) {
      body = { ...toBody(sent), status: target ?? "draft" };
    } else {
      body = statusOnly ? {} : { ...pending };
      if (target && target !== opportunity.stored_status) body.status = target;
      if (Object.keys(body).length === 0) {
        toast.show("No changes to save", "info");
        return;
      }
      keptUnsent = statusOnly && Object.keys(pending).length > 0;
    }

    setBusy(action);
    try {
      const res = isNew
        ? await adminCreateOpportunity(adminKey, body as OpportunityBody)
        : await adminPatchOpportunity(adminKey, opportunity.id, body);
      // Fields still holding a value the server refused (and not sent now) are
      // reset to the saved value on the re-seed — the admin has moved on.
      const current = toBody(sent);
      const discarded = (Object.keys(refusedRef.current) as BodyKey[]).filter(
        (k) => k in pending && !(k in body) && sameValue(current[k], refusedRef.current[k], k),
      );
      const otherUnsent = Object.keys(pending).filter((k) => !discarded.includes(k as BodyKey)).length > 0;
      const notes = [SUCCESS[action]];
      if (discarded.length > 0) {
        notes.push(
          `The refused ${discarded.map((k) => FIELD_LABEL[k].toLowerCase()).join(", ")} was discarded — the saved value is back`,
        );
      }
      if (keptUnsent && otherUnsent) notes.push("Your other edits are still here, not saved yet");
      toast.show(notes.join(". ") + (notes.length > 1 ? "." : ""), "success");
      dropRefusedRef.current = true;
      onSaved(res.opportunity, isNew);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setFormError(
            <>
              Your key no longer matches this server — nothing was saved.{" "}
              <button
                type="button"
                onClick={onUnauthorized}
                className="font-medium underline underline-offset-2"
              >
                Enter it again
              </button>
            </>,
          );
        } else if (err.code === "validation_error") {
          const raw = parseFieldError(err.message);
          // The legacy `city:` message belongs to the locations chips input.
          const parsed = raw && raw.field === "city" ? { ...raw, field: "locations" } : raw;
          if (parsed && INLINE_FIELDS.has(parsed.field)) {
            setFieldErrors({ [parsed.field]: parsed.reason });
            if (!isNew) {
              const k = parsed.field as BodyKey;
              refusedRef.current[k] = toBody(sent)[k];
            }
            const el = document.getElementById(`opp-${parsed.field.replace(/_/g, "-")}`);
            el?.scrollIntoView?.({ behavior: "smooth", block: "center" });
          } else {
            setFormError(err.message);
          }
        } else if (err.code === "not_found") {
          setFormError("This opportunity no longer exists — go back to the list.");
        } else if (err.status === 0) {
          setFormError("Couldn't reach the server — your changes are still here; try again.");
        } else {
          setFormError(`Couldn't save — ${err.message}`);
        }
      } else {
        setFormError("Something went wrong — your changes are still here; try again.");
      }
    } finally {
      setBusy(null);
    }
  };

  const actionButtons = (() => {
    const b = (action: Action, label: string, testId: string, variant: "primary" | "secondary" | "danger" | "ghost") => (
      <Button
        key={action}
        data-testid={testId}
        variant={variant}
        loading={busy === action}
        disabled={busy !== null && busy !== action}
        onClick={() => void run(action)}
        className="w-full sm:w-auto"
      >
        {label}
      </Button>
    );
    if (isNew || status === "draft") {
      return [b("save_draft", "Save draft", "opp-save-draft", "secondary"), b("publish", "Publish", "opp-publish", "primary")];
    }
    if (status === "open") {
      return [
        b("save", "Save", "opp-save", "primary"),
        b("close", "Close", "opp-close", "danger"),
        b("unpublish", "Unpublish", "opp-unpublish", "secondary"),
      ];
    }
    if (status === "expired") {
      return [b("save", "Save", "opp-save", "primary"), b("close", "Close", "opp-close", "danger")];
    }
    // closed
    return [b("reopen", "Reopen", "opp-reopen", "primary"), b("save", "Save", "opp-save", "secondary")];
  })();

  const err = { ...compErrs, ...(compShow ? budgetErrors(form) : {}), ...fieldErrors };
  const chip = (f: DraftedField) => <DraftedChip field={f} show={drafted.has(f)} />;

  return (
    <UnsavedFieldsContext.Provider value={unsavedFields}>
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        void run(isNew || status === "draft" ? "save_draft" : "save");
      }}
      className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]"
    >
      {/* ------------------------------------------------ left column */}
      <div className="min-w-0 space-y-6">
        <PasteToFill
          opportunityId={opportunity?.id ?? null}
          hasUserInput={hasUserInput}
          onDraft={applyDraft}
          defaultCollapsed={!isNew}
        />
        {draftApplied && (
          <p
            role="status"
            data-testid="draft-applied"
            className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
          >
            Draft applied — check each field marked “Drafted”. Nothing is published; the listing stays a draft until you
            publish it.
          </p>
        )}
        {/* Public details */}
        <Card className="p-5 sm:p-6">
          <div className="mb-5">
            <h2 className="text-lg font-semibold text-stone-900">Public details</h2>
            <p className="text-sm text-stone-500">Shown on the public board and the listing page.</p>
          </div>
          <div className="space-y-5">
            <Field id="opp-title" label="Title" required error={err.title} errorField="title" chip={chip("title")}>
              <input
                id="opp-title"
                data-testid="opp-title-input"
                value={form.title}
                maxLength={160}
                onChange={(e) => set("title", e.target.value)}
                placeholder="GenAI for product teams — 2-day workshop"
                aria-invalid={Boolean(err.title)}
                className={inputCls(Boolean(err.title))}
              />
            </Field>

            <Field id="opp-type" label="Type" required error={err.type} errorField="type" chip={chip("type")}>
              <select
                id="opp-type"
                data-testid="opp-type-select"
                value={form.type}
                onChange={(e) => set("type", e.target.value as OpportunityType)}
                aria-invalid={Boolean(err.type)}
                className={inputCls(Boolean(err.type))}
              >
                {OPPORTUNITY_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </Field>

            <Field
              id="opp-summary"
              label="Summary"
              required
              error={err.summary}
              errorField="summary" chip={chip("summary")}
              aside={
                <span
                  className={cn(
                    "text-xs tabular-nums",
                    form.summary.length > 260 ? "text-amber-700" : "text-stone-400",
                  )}
                >
                  {form.summary.length} / 280
                </span>
              }
            >
              <textarea
                id="opp-summary"
                data-testid="opp-summary-input"
                rows={2}
                maxLength={280}
                value={form.summary}
                onChange={(e) => set("summary", e.target.value)}
                placeholder="One or two sentences for the board card."
                aria-invalid={Boolean(err.summary)}
                className={inputCls(Boolean(err.summary))}
              />
            </Field>

            <Field
              id="opp-description-md"
              label="Description"
              error={err.description_md}
              errorField="description_md" chip={chip("description_md")}
              hint="Markdown — lists, links and fenced code blocks are supported."
              aside={
                <div role="tablist" aria-label="Description mode" className="flex gap-1 text-xs">
                  {(["write", "preview"] as const).map((t) => (
                    <button
                      key={t}
                      type="button"
                      role="tab"
                      aria-selected={descTab === t}
                      onClick={() => setDescTab(t)}
                      className={cn(
                        "rounded-md px-2 py-0.5 font-medium",
                        descTab === t ? "bg-stone-800 text-white" : "text-stone-600 hover:bg-stone-100",
                      )}
                    >
                      {t === "write" ? "Write" : "Preview"}
                    </button>
                  ))}
                </div>
              }
            >
              {descTab === "write" ? (
                <textarea
                  id="opp-description-md"
                  data-testid="opp-description-input"
                  rows={10}
                  value={form.description_md}
                  onChange={(e) => set("description_md", e.target.value)}
                  placeholder={"## What you'll teach\n- …\n\n## About the audience\n…"}
                  aria-invalid={Boolean(err.description_md)}
                  className={cn(inputCls(Boolean(err.description_md)), "font-mono text-sm")}
                />
              ) : (
                <div className="min-h-40 rounded-lg border border-stone-200 bg-stone-50/50 px-4 py-3">
                  {form.description_md.trim() ? (
                    <Markdown>{form.description_md}</Markdown>
                  ) : (
                    <p className="text-sm text-stone-400 italic">Nothing to preview yet.</p>
                  )}
                </div>
              )}
            </Field>

            <Field
              id="opp-topic-ids"
              label="Topics"
              required
              error={err.topic_ids}
              errorField="topic_ids" chip={chip("topics")}
              hint="Pick 1 to 8 — trainers filter the board by these."
            >
              <div id="opp-topic-ids">
                <TopicPicker
                  topics={topics}
                  selected={form.topic_ids}
                  onChange={(ids) => set("topic_ids", ids)}
                  invalid={Boolean(err.topic_ids)}
                />
              </div>
            </Field>

            <div className="grid gap-5 sm:grid-cols-2">
              <Field id="opp-location-mode" label="Location" required error={err.location_mode} errorField="location_mode" chip={chip("location")}>
                <select
                  id="opp-location-mode"
                  data-testid="opp-location-select"
                  value={form.location_mode}
                  onChange={(e) => set("location_mode", e.target.value as LocationMode)}
                  className={inputCls(Boolean(err.location_mode))}
                >
                  {LOCATION_MODES.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </Field>
              {form.location_mode !== "remote" && (
                <div className="sm:col-span-2">
                  <Field id="opp-location-city" label="Locations" required errorField="locations">
                    <LocationsInput
                      id="opp-location-city"
                      handleRef={locationsRef}
                      value={form.locations}
                      onChange={(next) => set("locations", next)}
                      serverError={err.locations}
                    />
                  </Field>
                </div>
              )}
            </div>

            <div className="grid gap-5 sm:grid-cols-2">
              <Field id="opp-starts-on" label="Starts on" error={err.starts_on} errorField="starts_on" chip={chip("dates")}>
                <input
                  id="opp-starts-on"
                  data-testid="opp-starts-on-input"
                  type="date"
                  value={form.starts_on}
                  onChange={(e) => set("starts_on", e.target.value)}
                  className={inputCls(Boolean(err.starts_on))}
                />
              </Field>
              <Field id="opp-ends-on" label="Ends on" error={err.ends_on} errorField="ends_on">
                <input
                  id="opp-ends-on"
                  data-testid="opp-ends-on-input"
                  type="date"
                  value={form.ends_on}
                  min={form.starts_on || undefined}
                  onChange={(e) => set("ends_on", e.target.value)}
                  className={inputCls(Boolean(err.ends_on))}
                />
              </Field>
              <Field id="opp-duration-text" label="Duration" error={err.duration_text} errorField="duration_text" chip={chip("duration_text")}>
                <input
                  id="opp-duration-text"
                  data-testid="opp-duration-input"
                  value={form.duration_text}
                  maxLength={80}
                  onChange={(e) => set("duration_text", e.target.value)}
                  placeholder="2 days"
                  className={inputCls(Boolean(err.duration_text))}
                />
              </Field>
            </div>

            <fieldset
              data-testid="opp-compensation"
              className="space-y-3"
              onBlur={() => setCompShow(true)}
            >
              <legend className="mb-1 text-sm font-medium text-stone-700">
                Compensation
                {chip("compensation")}
              </legend>
              <div className="grid gap-3 sm:grid-cols-4">
                <Field id="opp-compensation-min" label="Min" error={err.compensation_min} errorField="compensation_min">
                  <input
                    id="opp-compensation-min"
                    data-testid="compensation-min"
                    inputMode="numeric"
                    value={form.compensation_min}
                    onChange={(e) => set("compensation_min", e.target.value)}
                    placeholder="8000"
                    aria-invalid={Boolean(err.compensation_min)}
                    className={inputCls(Boolean(err.compensation_min))}
                  />
                </Field>
                <Field id="opp-compensation-max" label="Max" error={err.compensation_max} errorField="compensation_max">
                  <input
                    id="opp-compensation-max"
                    data-testid="compensation-max"
                    inputMode="numeric"
                    value={form.compensation_max}
                    onChange={(e) => set("compensation_max", e.target.value)}
                    placeholder="12000"
                    aria-invalid={Boolean(err.compensation_max)}
                    className={inputCls(Boolean(err.compensation_max))}
                  />
                </Field>
                <Field
                  id="opp-compensation-currency"
                  label="Currency"
                  error={err.compensation_currency}
                  errorField="compensation_currency"
                >
                  <select
                    id="opp-compensation-currency"
                    data-testid="compensation-currency"
                    value={form.compensation_currency}
                    onChange={(e) => set("compensation_currency", e.target.value as "" | Currency)}
                    aria-invalid={Boolean(err.compensation_currency)}
                    className={inputCls(Boolean(err.compensation_currency))}
                  >
                    <option value="">—</option>
                    {CURRENCIES.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.symbol} {c.value}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field
                  id="opp-compensation-unit"
                  label="Unit"
                  error={err.compensation_unit}
                  errorField="compensation_unit"
                >
                  <select
                    id="opp-compensation-unit"
                    data-testid="compensation-unit"
                    value={form.compensation_unit}
                    onChange={(e) => set("compensation_unit", e.target.value as "" | CompensationUnit)}
                    aria-invalid={Boolean(err.compensation_unit)}
                    className={inputCls(Boolean(err.compensation_unit))}
                  >
                    <option value="">—</option>
                    {COMPENSATION_UNITS.map((u) => (
                      <option key={u.value} value={u.value}>
                        {u.label}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <Field
                id="opp-compensation-text"
                label="Note (optional)"
                error={err.compensation_text}
                errorField="compensation_text"
                hint="Shown after the amount, e.g. “plus travel”. On its own it reads as “Pro bono”."
              >
                <input
                  id="opp-compensation-text"
                  data-testid="opp-compensation-input"
                  value={form.compensation_text}
                  maxLength={120}
                  onChange={(e) => set("compensation_text", e.target.value)}
                  placeholder="plus travel"
                  className={inputCls(Boolean(err.compensation_text))}
                />
              </Field>
            </fieldset>

            <fieldset
              data-testid="opp-budget"
              className="space-y-3 rounded-lg border border-stone-200 bg-stone-50/50 p-4"
            >
              <legend className="flex items-center gap-1.5 px-1 text-sm font-medium text-stone-700">
                Matching (admin only) <LockIcon />
              </legend>
              <p className="text-xs text-stone-500">
                Never shown publicly. Used to suggest trainers whose rate fits and whose topic level is
                high enough.
              </p>
              <div className="grid gap-3 sm:grid-cols-4">
                <Field id="opp-budget-min" label="Budget min" error={err.budget_min} errorField="budget_min">
                  <input
                    id="opp-budget-min"
                    data-testid="budget-min"
                    inputMode="numeric"
                    value={form.budget_min}
                    onChange={(e) => set("budget_min", e.target.value)}
                    aria-invalid={Boolean(err.budget_min)}
                    className={inputCls(Boolean(err.budget_min))}
                  />
                </Field>
                <Field id="opp-budget-max" label="Budget max" error={err.budget_max} errorField="budget_max">
                  <input
                    id="opp-budget-max"
                    data-testid="budget-max"
                    inputMode="numeric"
                    value={form.budget_max}
                    onChange={(e) => set("budget_max", e.target.value)}
                    aria-invalid={Boolean(err.budget_max)}
                    className={inputCls(Boolean(err.budget_max))}
                  />
                </Field>
                <Field id="opp-budget-currency" label="Currency" error={err.budget_currency} errorField="budget_currency">
                  <select
                    id="opp-budget-currency"
                    data-testid="budget-currency"
                    value={form.budget_currency}
                    onChange={(e) => set("budget_currency", e.target.value as "" | Currency)}
                    className={inputCls(Boolean(err.budget_currency))}
                  >
                    <option value="">—</option>
                    {CURRENCIES.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.symbol} {c.value}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field id="opp-budget-unit" label="Unit" error={err.budget_unit} errorField="budget_unit">
                  <select
                    id="opp-budget-unit"
                    data-testid="budget-unit"
                    value={form.budget_unit}
                    onChange={(e) => set("budget_unit", e.target.value as "" | CompensationUnit)}
                    className={inputCls(Boolean(err.budget_unit))}
                  >
                    <option value="">—</option>
                    {COMPENSATION_UNITS.map((u) => (
                      <option key={u.value} value={u.value}>
                        {u.label}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <Field id="opp-min-level" label="Minimum topic level" error={err.min_level} errorField="min_level">
                <select
                  id="opp-min-level"
                  data-testid="min-level"
                  value={form.min_level}
                  onChange={(e) => set("min_level", e.target.value as "" | MinLevel)}
                  className={cn(inputCls(Boolean(err.min_level)), "sm:max-w-xs")}
                >
                  <option value="">No minimum</option>
                  {MIN_LEVELS.map((l) => (
                    <option key={l.value} value={l.value}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </Field>
            </fieldset>

            <Field
              id="opp-deadline"
              label="Application deadline"
              required
              error={err.deadline}
              errorField="deadline" chip={chip("deadline")}
              hint={
                deadlineIso
                  ? `Your local time · ${deadlineIso.replace("T", " ").replace(/:\d{2}Z$/, "")} UTC`
                  : "Your local time zone."
              }
            >
              <input
                id="opp-deadline"
                data-testid="opp-deadline-input"
                type="datetime-local"
                value={form.deadline_local}
                onChange={(e) => set("deadline_local", e.target.value)}
                aria-invalid={Boolean(err.deadline)}
                className={cn(inputCls(Boolean(err.deadline)), "sm:max-w-xs")}
              />
            </Field>

            <Field
              id="opp-partner-display-name"
              label="Public partner name"
              error={err.partner_display_name}
              errorField="partner_display_name" chip={chip("partner_display_name")}
              hint="What trainers see. Leave blank to show “smallTech partner network”."
            >
              <input
                id="opp-partner-display-name"
                data-testid="opp-partner-display-input"
                value={form.partner_display_name}
                maxLength={160}
                onChange={(e) => set("partner_display_name", e.target.value)}
                placeholder="smallTech partner network"
                className={inputCls(Boolean(err.partner_display_name))}
              />
            </Field>
          </div>
        </Card>

        {/* Internal */}
        <section
          aria-labelledby="internal-heading"
          className="rounded-xl border border-amber-200 bg-amber-50/60 p-5 shadow-sm sm:p-6"
        >
          <div className="mb-5 flex items-start gap-2">
            <LockIcon className="mt-1 size-4 text-amber-700" />
            <div>
              <h2 id="internal-heading" className="text-lg font-semibold text-stone-900">
                Internal — only admins see this
              </h2>
              <p className="text-sm text-amber-800">
                Never shown publicly — not on the board, the listing page or any public API.
              </p>
            </div>
          </div>
          <div className="space-y-5">
            <div data-testid="editor-partner-select" id="opp-partner-id">
              <span className="mb-1 block text-sm font-medium text-stone-700">Partner</span>
              <PartnerSelect
                value={form.partner}
                onChange={onPartnerChange}
                suggestedNew={suggestedNew}
                drafted={drafted.has("partner")}
                error={err.partner_id}
              />
            </div>
            {isCofac && (
              <Field
                id="opp-workshop-id"
                label="Workshop"
                error={err.workshop_id}
                errorField="workshop_id"
                hint="The workshop trainers would co-facilitate. Admin only; used to prefill Link as facilitator."
              >
                <select
                  id="opp-workshop-id"
                  data-testid="opp-workshop-select"
                  value={form.workshop_id ?? ""}
                  onChange={(e) =>
                    set("workshop_id", e.target.value === "" ? null : Number(e.target.value))
                  }
                  className={inputCls(Boolean(err.workshop_id))}
                >
                  <option value="">No workshop linked</option>
                  {(workshops ?? []).map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                  {form.workshop_id != null &&
                    !(workshops ?? []).some((w) => w.id === form.workshop_id) && (
                      <option value={form.workshop_id}>Workshop #{form.workshop_id}</option>
                    )}
                </select>
              </Field>
            )}
            <Field
              id="opp-internal-notes"
              label="Internal notes"
              error={err.internal_notes}
              errorField="internal_notes" chip={chip("internal_notes")}
            >
              <textarea
                id="opp-internal-notes"
                data-testid="opp-internal-notes-input"
                rows={4}
                maxLength={5000}
                value={form.internal_notes}
                onChange={(e) => set("internal_notes", e.target.value)}
                placeholder="Contacts, rates, context for the team…"
                className={inputCls(Boolean(err.internal_notes))}
              />
            </Field>
          </div>
        </section>

        {/* Activity */}
        <Card className="p-5 sm:p-6">
          <h2 className="mb-4 text-lg font-semibold text-stone-900">Activity</h2>
          {isNew ? (
            <p className="text-sm text-stone-500">Activity appears here once you save.</p>
          ) : (
            <ActivityList items={activity} />
          )}
        </Card>
      </div>

      {/* ------------------------------------------------ right column */}
      <aside className="min-w-0 space-y-4 lg:sticky lg:top-4 lg:self-start">
        <Card className="p-5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-stone-700">Status</h2>
            {status ? (
              <OpportunityStatusPill status={status} data-testid="opp-status-pill" />
            ) : (
              <span
                data-testid="opp-status-pill"
                className="inline-flex items-center rounded-full border border-dashed border-stone-300 px-2 py-0.5 text-xs font-medium text-stone-500"
              >
                Not saved yet
              </span>
            )}
          </div>

          {status === "expired" && (
            <p
              role="status"
              className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800"
            >
              Expired — extend the deadline to reopen.
            </p>
          )}
          {status === "closed" && (
            <p className="mt-3 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2 text-sm text-stone-600">
              Closed — off the board. Reopening needs a future deadline.
            </p>
          )}

          {formError && (
            <div
              role="alert"
              data-testid="opp-form-error"
              className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            >
              {formError}
            </div>
          )}

          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">{actionButtons}</div>
          {!isNew && (
            <p className="mt-2 text-xs text-stone-500" aria-live="polite">
              {dirty
                ? unsavedLabels.length > 0
                  ? `Unsaved changes: ${unsavedLabels.join(", ")}.`
                  : "You have unsaved changes."
                : "All changes saved."}
            </p>
          )}

          {opportunity?.published_at && (
            <div className="mt-4 border-t border-stone-100 pt-4">
              <p className="mb-1 text-xs font-medium text-stone-500">Public link</p>
              <div className="flex items-center gap-2">
                <a
                  data-testid="opp-public-link"
                  href={opportunity.public_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="min-w-0 flex-1 truncate font-mono text-sm text-brand-700 hover:underline"
                  title={opportunity.public_url}
                >
                  {opportunity.public_url}
                </a>
                <CopyButton text={opportunity.public_url} label="Copy public link" />
              </div>
            </div>
          )}
        </Card>

        <div>
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-stone-700">Public card preview</h2>
            <span className="text-xs text-stone-400">Exactly what the board shows</span>
          </div>
          <PublicCardPreview
            now={now}
            data={{
              title: form.title,
              type: form.type,
              summary: form.summary,
              partner_display_name: form.partner_display_name,
              topics: previewTopics,
              location_mode: form.location_mode,
              locations: form.locations,
              compensation: {
                compensation_min: amount(form.compensation_min),
                compensation_max: amount(form.compensation_max),
                compensation_currency: form.compensation_currency || null,
                compensation_unit: form.compensation_unit || null,
                compensation_text: form.compensation_text.trim() || null,
              },
              deadline: deadlineIso,
            }}
          />
        </div>

        {opportunity ? (
          <SuggestedTrainersPanel opportunityId={opportunity.id} />
        ) : (
          <Card className="p-4">
            <h2 className="text-sm font-semibold text-stone-900">Suggested trainers</h2>
            <p className="mt-1 text-xs text-stone-500">Save the listing first, then suggest trainers.</p>
          </Card>
        )}
      </aside>
    </form>
    </UnsavedFieldsContext.Provider>
  );
}
