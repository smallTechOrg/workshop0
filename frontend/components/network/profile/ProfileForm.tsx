"use client";

/**
 * The shared trainer-profile form (capabilities.md C12) — the onboarding review
 * screen (`mode="create"`, with the consent checkbox) and My profile's editor
 * (`mode="edit"`). Every ProfileInput field from api.md §Phase 11 is editable;
 * only the headline (3–160) and ≥1 topic are required.
 *
 * Fields the CV drafter pre-filled carry the amber "From your CV — please check"
 * chip until the person edits them. Rates are labelled "Visible to smallTech only".
 * Validation runs inline on submit (mirroring services/profiles.py), and server
 * `validation_error`s ("<field>: <message>") land on the matching field.
 */

import { useId, useMemo, useState } from "react";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/format";
import {
  CURRENCIES,
  DAY_PARTS,
  DAY_PART_LABELS,
  MAX_BLACKOUTS,
  MAX_PAST_WORK,
  MAX_TOPICS,
  PAST_WORK_KINDS,
  PAST_WORK_KIND_LABELS,
  RATE_UNITS,
  RATE_UNIT_LABELS,
  TOPIC_LEVELS,
  TOPIC_LEVEL_LABELS,
  WEEKDAYS,
  WEEKDAY_LABELS,
  saveErrorMessage,
  splitFieldError,
  type Availability,
  type Blackout,
  type Currency,
  type DayPart,
  type PastWorkItem,
  type PastWorkKind,
  type ProfileInput,
  type RateUnit,
  type TopicLevel,
  type Weekday,
} from "@/lib/network";
import type { PublicTopic } from "@/lib/board";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { AutofillChip } from "@/components/network/profile/AutofillChip";
import { useTopics } from "@/components/network/profile/useTopics";

export const CONSENT_TEXT =
  "smallTech may share my profile with partner organisations for matching.";

type Errors = Partial<Record<string, string>>;

const INPUT =
  "block w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-base text-stone-900 shadow-sm placeholder:text-stone-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20";
const INPUT_ERR = "border-red-400 focus:border-red-500 focus:ring-red-500/20";

// ---------------------------------------------------------------------------
// Client-side rules (mirror services/profiles.py so most errors never round-trip)
// ---------------------------------------------------------------------------

function httpsUrlError(value: string | null, host: string | null): string | null {
  if (!value) return null;
  const v = value.trim();
  if (v.length > 300) return "must be at most 300 characters";
  let parsed: URL;
  try {
    parsed = new URL(v);
  } catch {
    return "must be an https:// link";
  }
  if (parsed.protocol !== "https:" || !parsed.hostname || v.includes(" ")) {
    return "must be an https:// link";
  }
  const h = parsed.hostname.toLowerCase();
  if (host && !(h === host || h.endsWith(`.${host}`))) return `must be a ${host} link`;
  return null;
}

export function validateProfile(
  input: ProfileInput,
  opts: { requireConsent: boolean; consent: boolean },
): Errors {
  const e: Errors = {};
  const headline = input.headline.trim();
  if (headline.length < 3 || headline.length > 160) {
    e.headline = "Add a headline of 3–160 characters.";
  }
  if (input.bio_md.trim().length > 4000) e.bio_md = "Keep your bio under 4000 characters.";
  if ((input.city ?? "").trim().length > 80) e.city = "Keep the city under 80 characters.";
  if (input.topics.length === 0) e.topics = "Pick at least one topic.";
  if (input.topics.length > MAX_TOPICS) e.topics = `Pick at most ${MAX_TOPICS} topics.`;
  const li = httpsUrlError(input.linkedin_url, "linkedin.com");
  if (li) e.linkedin_url = `LinkedIn ${li}.`;
  const gh = httpsUrlError(input.github_url, "github.com");
  if (gh) e.github_url = `GitHub ${gh}.`;
  const web = httpsUrlError(input.website_url, null);
  if (web) e.website_url = `Website ${web}.`;
  const thisYear = new Date().getFullYear();
  input.past_work.forEach((p) => {
    if (!p.title.trim()) e.past_work = "Give every workshop or talk a title (or remove it).";
    else if (p.year !== null && (p.year < 1980 || p.year > thisYear)) {
      e.past_work = `Years must be between 1980 and ${thisYear}.`;
    }
  });
  if (input.rate_min !== null && input.rate_max !== null && input.rate_min > input.rate_max) {
    e.rate_min = "The minimum rate can't be more than the maximum.";
  }
  if (
    (input.rate_min !== null && input.rate_min < 0) ||
    (input.rate_max !== null && input.rate_max < 0)
  ) {
    e.rate_min = "Rates must be whole numbers of at least 0.";
  }
  input.blackouts.forEach((b) => {
    if (!b.start || !b.end) e.blackouts = "Give every date range a start and an end (or remove it).";
    else if (b.end < b.start) e.blackouts = "Each date range must end on or after its start.";
  });
  if (opts.requireConsent && !opts.consent) e.consent = "Please agree to continue.";
  return e;
}

/** Trim strings and drop half-filled rows so the payload is what the person meant. */
function cleanInput(input: ProfileInput): ProfileInput {
  const s = (v: string | null) => (v && v.trim() ? v.trim() : null);
  return {
    ...input,
    headline: input.headline.trim(),
    bio_md: input.bio_md.trim(),
    city: s(input.city),
    linkedin_url: s(input.linkedin_url),
    github_url: s(input.github_url),
    website_url: s(input.website_url),
    past_work: input.past_work.map((p) => ({ ...p, title: p.title.trim(), org: s(p.org) })),
  };
}

function parseIntOrNull(raw: string): number | null {
  const t = raw.trim();
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

// ---------------------------------------------------------------------------
// Small layout pieces
// ---------------------------------------------------------------------------

function FieldError({ field, errors }: { field: string; errors: Errors }) {
  const msg = errors[field];
  if (!msg) return null;
  return (
    <p
      role="alert"
      data-testid={`profile-field-error-${field}`}
      className="mt-1.5 text-sm text-red-700"
    >
      {msg}
    </p>
  );
}

function FieldHead({
  htmlFor,
  label,
  hint,
  required,
  autofilled,
}: {
  htmlFor?: string;
  label: string;
  hint?: string;
  required?: boolean;
  autofilled?: boolean;
}) {
  return (
    <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
      {htmlFor ? (
        <label htmlFor={htmlFor} className="text-sm font-medium text-stone-800">
          {label}
          {required && <span className="text-red-600"> *</span>}
        </label>
      ) : (
        <span className="text-sm font-medium text-stone-800">
          {label}
          {required && <span className="text-red-600"> *</span>}
        </span>
      )}
      {autofilled && <AutofillChip />}
      {hint && <span className="text-xs text-stone-500">{hint}</span>}
    </div>
  );
}

function Section({
  title,
  description,
  aside,
  children,
  ...rest
}: {
  title: string;
  description?: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <section {...rest}>
      <Card className="p-5 sm:p-6">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 className="font-semibold text-stone-900">{title}</h2>
            {description && <p className="mt-0.5 text-sm text-stone-500">{description}</p>}
          </div>
          {aside}
        </div>
        <div className="space-y-5">{children}</div>
      </Card>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Topics picker
// ---------------------------------------------------------------------------

function TopicsPicker({
  value,
  onChange,
  curated,
  loading,
  error,
  retry,
  topicNames,
}: {
  value: ProfileInput["topics"];
  onChange: (next: ProfileInput["topics"]) => void;
  curated: PublicTopic[];
  loading: boolean;
  error: string | null;
  retry: () => void;
  topicNames: Record<string, string>;
}) {
  const nameOf = (slug: string) =>
    curated.find((t) => t.slug === slug)?.name ?? topicNames[slug] ?? slug;
  const selected = new Set(value.map((t) => t.slug));
  const full = value.length >= MAX_TOPICS;

  const groups = useMemo(() => {
    const m = new Map<string, PublicTopic[]>();
    for (const t of curated) {
      const key = t.category || "Other";
      m.set(key, [...(m.get(key) ?? []), t]);
    }
    return [...m.entries()];
  }, [curated]);

  function toggle(slug: string) {
    if (selected.has(slug)) onChange(value.filter((t) => t.slug !== slug));
    else if (!full) onChange([...value, { slug, level: "intermediate" }]);
  }

  return (
    <div className="space-y-4">
      {value.length > 0 ? (
        <ul className="space-y-2" aria-label="Your topics">
          {value.map((t) => (
            <li
              key={t.slug}
              data-testid={`selected-topic-${t.slug}`}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-brand-200 bg-brand-50/60 px-3 py-2"
            >
              <span className="font-medium text-stone-900">{nameOf(t.slug)}</span>
              <span className="flex items-center gap-2">
                <select
                  aria-label={`Level for ${nameOf(t.slug)}`}
                  value={t.level}
                  onChange={(e) =>
                    onChange(
                      value.map((x) =>
                        x.slug === t.slug ? { ...x, level: e.target.value as TopicLevel } : x,
                      ),
                    )
                  }
                  className="rounded-md border border-stone-300 bg-white px-2 py-1 text-sm"
                >
                  {TOPIC_LEVELS.map((l) => (
                    <option key={l} value={l}>
                      {TOPIC_LEVEL_LABELS[l]}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => toggle(t.slug)}
                  aria-label={`Remove ${nameOf(t.slug)}`}
                  className="rounded-md p-1 text-stone-500 hover:bg-white hover:text-stone-800"
                >
                  <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="size-4">
                    <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
                  </svg>
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="rounded-lg border border-dashed border-stone-300 px-3 py-2 text-sm text-stone-500">
          No topics yet — pick the ones you teach below.
        </p>
      )}

      {loading ? (
        <div aria-busy="true" aria-label="Loading topics" className="flex flex-wrap gap-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-24 rounded-full" />
          ))}
        </div>
      ) : error ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-stone-700">
          {error}
          <Button size="sm" variant="secondary" onClick={retry}>
            Try again
          </Button>
        </div>
      ) : curated.length === 0 ? (
        <p className="text-sm text-stone-500">No topics are available yet.</p>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-stone-500">
            {value.length}/{MAX_TOPICS} picked{full ? " — remove one to pick another" : ""}
          </p>
          {groups.map(([category, items]) => (
            <div key={category}>
              <p className="mb-1.5 text-xs font-semibold tracking-wide text-stone-500 uppercase">
                {category}
              </p>
              <div className="flex flex-wrap gap-2">
                {items.map((t) => {
                  const on = selected.has(t.slug);
                  return (
                    <button
                      key={t.slug}
                      type="button"
                      data-testid={`topic-option-${t.slug}`}
                      aria-pressed={on}
                      disabled={!on && full}
                      onClick={() => toggle(t.slug)}
                      className={cn(
                        "rounded-full border px-3 py-1 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                        on
                          ? "border-brand-600 bg-brand-600 text-white"
                          : "border-stone-300 bg-white text-stone-700 hover:border-stone-400",
                      )}
                    >
                      {on ? "✓ " : ""}
                      {t.name}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The form
// ---------------------------------------------------------------------------

export interface ProfileFormProps {
  mode: "create" | "edit";
  initial: ProfileInput;
  /** ProfileInput keys pre-filled by the CV drafter (drive the amber chips). */
  autofilled?: string[];
  /** Display names for topics that may not be in the active curated list. */
  topicNames?: Record<string, string>;
  submitLabel: string;
  /** Throw an ApiError to have it shown inline; resolve on success. */
  onSubmit: (input: ProfileInput, consent: boolean) => Promise<void>;
  /** Extra content rendered beside the submit button (e.g. "Use a different CV"). */
  secondaryAction?: React.ReactNode;
}

export function ProfileForm({
  mode,
  initial,
  autofilled = [],
  topicNames = {},
  submitLabel,
  onSubmit,
  secondaryAction,
}: ProfileFormProps) {
  const uid = useId();
  const id = (name: string) => `${uid}-${name}`;
  const { topics: curated, loading: topicsLoading, error: topicsError, retry } = useTopics();

  const [input, setInput] = useState<ProfileInput>(initial);
  const [filled, setFilled] = useState<Set<string>>(() => new Set(autofilled));
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  function set<K extends keyof ProfileInput>(key: K, value: ProfileInput[K]) {
    setInput((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
    if (filled.has(key)) {
      setFilled((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
    // Rates share one error slot.
    const slot = key === "rate_max" ? "rate_min" : key;
    if (errors[slot]) setErrors((prev) => ({ ...prev, [slot]: undefined }));
  }

  const chip = (key: keyof ProfileInput) => filled.has(key);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setSaved(false);
    const cleaned = cleanInput(input);
    const found = validateProfile(cleaned, { requireConsent: mode === "create", consent });
    setErrors(found);
    if (Object.values(found).some(Boolean)) {
      setFormError("Please fix the highlighted fields.");
      return;
    }
    setSaving(true);
    try {
      await onSubmit(cleaned, consent);
      if (mode === "edit") {
        setInput(cleaned);
        setFilled(new Set()); // saving from My profile counts as having reviewed the pre-fill
        setSaved(true);
      }
    } catch (err) {
      if (err instanceof ApiError && err.code === "validation_error") {
        const { field, message } = splitFieldError(err.message);
        const slot = field === "rate_max" ? "rate_min" : field;
        if (slot) {
          setErrors({ [slot]: message.charAt(0).toUpperCase() + message.slice(1) });
          setFormError("Please fix the highlighted fields.");
        } else {
          setFormError(err.message);
        }
      } else {
        setFormError(saveErrorMessage(err));
      }
    } finally {
      setSaving(false);
    }
  }

  // --- past work / blackouts / availability helpers
  const updatePast = (i: number, patch: Partial<PastWorkItem>) =>
    set(
      "past_work",
      input.past_work.map((p, j) => (j === i ? { ...p, ...patch } : p)),
    );
  const updateBlackout = (i: number, patch: Partial<Blackout>) =>
    set(
      "blackouts",
      input.blackouts.map((b, j) => (j === i ? { ...b, ...patch } : b)),
    );
  function toggleSlot(day: Weekday, part: DayPart) {
    const current = input.availability[day] ?? [];
    const nextParts = current.includes(part)
      ? current.filter((p) => p !== part)
      : DAY_PARTS.filter((p) => p === part || current.includes(p));
    const next: Availability = { ...input.availability };
    if (nextParts.length) next[day] = nextParts;
    else delete next[day];
    set("availability", next);
  }

  return (
    <form noValidate onSubmit={handleSubmit} data-testid="profile-form" className="space-y-5">
      {/* ------------------------------------------------------------ About */}
      <Section title="About you">
        <div>
          <FieldHead
            htmlFor={id("headline")}
            label="Headline"
            required
            autofilled={chip("headline")}
          />
          <input
            id={id("headline")}
            data-testid="profile-headline"
            value={input.headline}
            onChange={(e) => set("headline", e.target.value)}
            maxLength={200}
            placeholder="e.g. GenAI & Python trainer for engineering teams"
            aria-invalid={Boolean(errors.headline) || undefined}
            className={cn(INPUT, errors.headline && INPUT_ERR)}
          />
          <FieldError field="headline" errors={errors} />
        </div>
        <div>
          <FieldHead
            htmlFor={id("bio")}
            label="Bio"
            hint="Markdown is fine"
            autofilled={chip("bio_md")}
          />
          <textarea
            id={id("bio")}
            data-testid="profile-bio"
            value={input.bio_md}
            onChange={(e) => set("bio_md", e.target.value)}
            rows={5}
            maxLength={4000}
            placeholder="What you teach, who you've taught, how you like to teach."
            className={cn(INPUT, "resize-y", errors.bio_md && INPUT_ERR)}
          />
          <p className="mt-1 text-xs text-stone-500">{input.bio_md.trim().length}/4000</p>
          <FieldError field="bio_md" errors={errors} />
        </div>
      </Section>

      {/* ----------------------------------------------------------- Topics */}
      <Section
        title="Topics you teach"
        description="Pick from the curated list and set your level for each."
        data-testid="review-topics"
        aside={chip("topics") ? <AutofillChip /> : undefined}
      >
        <div>
          <TopicsPicker
            value={input.topics}
            onChange={(next) => set("topics", next)}
            curated={curated}
            loading={topicsLoading}
            error={topicsError}
            retry={retry}
            topicNames={topicNames}
          />
          <FieldError field="topics" errors={errors} />
        </div>
      </Section>

      {/* --------------------------------------------------- Location + links */}
      <Section title="Location & links">
        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <FieldHead htmlFor={id("city")} label="City" autofilled={chip("city")} />
            <input
              id={id("city")}
              data-testid="profile-city"
              value={input.city ?? ""}
              onChange={(e) => set("city", e.target.value)}
              maxLength={80}
              placeholder="e.g. Bengaluru"
              className={cn(INPUT, errors.city && INPUT_ERR)}
            />
            <FieldError field="city" errors={errors} />
          </div>
          <div className="flex items-end">
            <label className="flex items-center gap-2 py-2 text-sm text-stone-800">
              <input
                type="checkbox"
                data-testid="profile-remote"
                checked={input.remote_ok}
                onChange={(e) => set("remote_ok", e.target.checked)}
                className="size-4 rounded border-stone-300 accent-brand-600"
              />
              Open to remote work
            </label>
            {chip("remote_ok") && (
              <span className="mb-2 ml-2">
                <AutofillChip />
              </span>
            )}
          </div>
        </div>
        <div className="grid gap-5 sm:grid-cols-3">
          {(
            [
              ["linkedin_url", "LinkedIn", "https://www.linkedin.com/in/…"],
              ["github_url", "GitHub", "https://github.com/…"],
              ["website_url", "Website", "https://…"],
            ] as const
          ).map(([key, label, placeholder]) => (
            <div key={key}>
              <FieldHead htmlFor={id(key)} label={label} autofilled={chip(key)} />
              <input
                id={id(key)}
                data-testid={`profile-${key.replace("_url", "")}`}
                type="url"
                inputMode="url"
                value={input[key] ?? ""}
                onChange={(e) => set(key, e.target.value)}
                placeholder={placeholder}
                className={cn(INPUT, errors[key] && INPUT_ERR)}
              />
              <FieldError field={key} errors={errors} />
            </div>
          ))}
        </div>
      </Section>

      {/* -------------------------------------------------------- Past work */}
      <Section
        title="Past workshops & talks"
        aside={chip("past_work") ? <AutofillChip /> : undefined}
        data-testid="profile-past-work"
      >
        {input.past_work.length === 0 && (
          <p className="text-sm text-stone-500">Nothing listed yet.</p>
        )}
        <ul className="space-y-3">
          {input.past_work.map((p, i) => (
            <li
              key={i}
              data-testid="past-work-row"
              className="grid gap-2 rounded-lg border border-stone-200 p-3 sm:grid-cols-[1fr_8rem_1fr_6rem_auto]"
            >
              <input
                aria-label={`Title of item ${i + 1}`}
                value={p.title}
                onChange={(e) => updatePast(i, { title: e.target.value })}
                placeholder="Title"
                maxLength={200}
                className={INPUT}
              />
              <select
                aria-label={`Kind of item ${i + 1}`}
                value={p.kind}
                onChange={(e) => updatePast(i, { kind: e.target.value as PastWorkKind })}
                className={INPUT}
              >
                {PAST_WORK_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {PAST_WORK_KIND_LABELS[k]}
                  </option>
                ))}
              </select>
              <input
                aria-label={`Organisation of item ${i + 1}`}
                value={p.org ?? ""}
                onChange={(e) => updatePast(i, { org: e.target.value })}
                placeholder="Organisation (optional)"
                maxLength={200}
                className={INPUT}
              />
              <input
                aria-label={`Year of item ${i + 1}`}
                value={p.year ?? ""}
                onChange={(e) => updatePast(i, { year: parseIntOrNull(e.target.value) })}
                inputMode="numeric"
                placeholder="Year"
                className={INPUT}
              />
              <Button
                variant="ghost"
                size="sm"
                aria-label={`Remove item ${i + 1}`}
                onClick={() =>
                  set(
                    "past_work",
                    input.past_work.filter((_, j) => j !== i),
                  )
                }
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
        <div>
          <Button
            variant="secondary"
            size="sm"
            disabled={input.past_work.length >= MAX_PAST_WORK}
            onClick={() =>
              set("past_work", [
                ...input.past_work,
                { title: "", kind: "workshop", org: null, year: null },
              ])
            }
          >
            + Add a workshop or talk
          </Button>
          <FieldError field="past_work" errors={errors} />
        </div>
      </Section>

      {/* ------------------------------------------------------------ Rates */}
      <Section
        title="Rates"
        description="Your usual range. Partners never see it."
        data-testid="profile-rates"
        aside={
          <span className="flex flex-wrap items-center gap-2">
            {(chip("rate_min") || chip("rate_max") || chip("rate_currency") || chip("rate_unit")) && (
              <AutofillChip />
            )}
            <Badge tone="info" data-testid="rates-private">
              <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="size-3">
                <path
                  fillRule="evenodd"
                  d="M10 1a4.5 4.5 0 0 0-4.5 4.5V9H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2h-.5V5.5A4.5 4.5 0 0 0 10 1Zm3 8V5.5a3 3 0 1 0-6 0V9h6Z"
                  clipRule="evenodd"
                />
              </svg>
              Visible to smallTech only
            </Badge>
          </span>
        }
      >
        <div className="grid gap-3 sm:grid-cols-4">
          <div>
            <FieldHead htmlFor={id("rate_min")} label="From" />
            <input
              id={id("rate_min")}
              data-testid="profile-rate-min"
              inputMode="numeric"
              value={input.rate_min ?? ""}
              onChange={(e) => set("rate_min", parseIntOrNull(e.target.value))}
              placeholder="e.g. 5000"
              className={cn(INPUT, errors.rate_min && INPUT_ERR)}
            />
          </div>
          <div>
            <FieldHead htmlFor={id("rate_max")} label="To" />
            <input
              id={id("rate_max")}
              data-testid="profile-rate-max"
              inputMode="numeric"
              value={input.rate_max ?? ""}
              onChange={(e) => set("rate_max", parseIntOrNull(e.target.value))}
              placeholder="e.g. 8000"
              className={cn(INPUT, errors.rate_min && INPUT_ERR)}
            />
          </div>
          <div>
            <FieldHead htmlFor={id("rate_currency")} label="Currency" />
            <select
              id={id("rate_currency")}
              data-testid="profile-rate-currency"
              value={input.rate_currency ?? ""}
              onChange={(e) => set("rate_currency", (e.target.value || null) as Currency | null)}
              className={INPUT}
            >
              <option value="">—</option>
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div>
            <FieldHead htmlFor={id("rate_unit")} label="Per" />
            <select
              id={id("rate_unit")}
              data-testid="profile-rate-unit"
              value={input.rate_unit ?? ""}
              onChange={(e) => set("rate_unit", (e.target.value || null) as RateUnit | null)}
              className={INPUT}
            >
              <option value="">—</option>
              {RATE_UNITS.map((u) => (
                <option key={u} value={u}>
                  {RATE_UNIT_LABELS[u]}
                </option>
              ))}
            </select>
          </div>
        </div>
        <FieldError field="rate_min" errors={errors} />
        <FieldError field="rate_currency" errors={errors} />
        <FieldError field="rate_unit" errors={errors} />
        <label className="flex items-center gap-2 text-sm text-stone-800">
          <input
            type="checkbox"
            data-testid="profile-pro-bono"
            checked={input.pro_bono}
            onChange={(e) => set("pro_bono", e.target.checked)}
            className="size-4 rounded border-stone-300 accent-brand-600"
          />
          Open to pro-bono work
        </label>
      </Section>

      {/* ----------------------------------------------------- Availability */}
      <Section
        title="Availability"
        description="When you can usually teach. You can change this any time."
        data-testid="profile-availability"
      >
        <div className="overflow-x-auto">
          <table className="w-full min-w-[22rem] border-separate border-spacing-1 text-sm">
            <thead>
              <tr>
                <th scope="col" className="sr-only">
                  Time of day
                </th>
                {WEEKDAYS.map((d) => (
                  <th key={d} scope="col" className="text-center font-medium text-stone-600">
                    {WEEKDAY_LABELS[d]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DAY_PARTS.map((part) => (
                <tr key={part}>
                  <th scope="row" className="pr-2 text-left font-medium whitespace-nowrap text-stone-600">
                    {DAY_PART_LABELS[part]}
                  </th>
                  {WEEKDAYS.map((day) => {
                    const on = (input.availability[day] ?? []).includes(part);
                    return (
                      <td key={day} className="text-center">
                        <label
                          className={cn(
                            "flex h-9 cursor-pointer items-center justify-center rounded-md border transition-colors",
                            on
                              ? "border-brand-600 bg-brand-600 text-white"
                              : "border-stone-200 bg-stone-50 text-transparent hover:border-stone-300",
                          )}
                        >
                          <input
                            type="checkbox"
                            className="sr-only"
                            checked={on}
                            onChange={() => toggleSlot(day, part)}
                            aria-label={`${WEEKDAY_LABELS[day]} ${DAY_PART_LABELS[part].toLowerCase()}`}
                          />
                          <span aria-hidden="true">✓</span>
                        </label>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="max-w-xs">
          <FieldHead htmlFor={id("available_from")} label="Available from" />
          <input
            id={id("available_from")}
            data-testid="profile-available-from"
            type="date"
            value={input.available_from ?? ""}
            onChange={(e) => set("available_from", e.target.value || null)}
            className={INPUT}
          />
          <FieldError field="available_from" errors={errors} />
        </div>
        <div>
          <FieldHead label="Unavailable dates" hint="e.g. holidays or a long project" />
          {input.blackouts.length === 0 && (
            <p className="mb-2 text-sm text-stone-500">No date ranges added.</p>
          )}
          <ul className="space-y-2">
            {input.blackouts.map((b, i) => (
              <li key={i} data-testid="blackout-row" className="flex flex-wrap items-center gap-2">
                <input
                  type="date"
                  aria-label={`Start of date range ${i + 1}`}
                  value={b.start}
                  onChange={(e) => updateBlackout(i, { start: e.target.value })}
                  className={cn(INPUT, "w-auto")}
                />
                <span className="text-sm text-stone-500">to</span>
                <input
                  type="date"
                  aria-label={`End of date range ${i + 1}`}
                  value={b.end}
                  onChange={(e) => updateBlackout(i, { end: e.target.value })}
                  className={cn(INPUT, "w-auto")}
                />
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Remove date range ${i + 1}`}
                  onClick={() =>
                    set(
                      "blackouts",
                      input.blackouts.filter((_, j) => j !== i),
                    )
                  }
                >
                  Remove
                </Button>
              </li>
            ))}
          </ul>
          <Button
            variant="secondary"
            size="sm"
            className="mt-2"
            disabled={input.blackouts.length >= MAX_BLACKOUTS}
            onClick={() => set("blackouts", [...input.blackouts, { start: "", end: "" }])}
          >
            + Add a date range
          </Button>
          <FieldError field="blackouts" errors={errors} />
        </div>
      </Section>

      {/* ------------------------------------------------------- Submit row */}
      <Card className="space-y-4 p-5 sm:p-6">
        {mode === "create" && (
          <div>
            <label className="flex items-start gap-3 text-sm text-stone-800">
              <input
                type="checkbox"
                data-testid="profile-consent"
                checked={consent}
                onChange={(e) => {
                  setConsent(e.target.checked);
                  if (errors.consent) setErrors((prev) => ({ ...prev, consent: undefined }));
                }}
                className="mt-0.5 size-4 shrink-0 rounded border-stone-300 accent-brand-600"
              />
              <span>{CONSENT_TEXT}</span>
            </label>
            <FieldError field="consent" errors={errors} />
          </div>
        )}
        {formError && (
          <p
            role="alert"
            data-testid="profile-form-error"
            className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
          >
            {formError}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" loading={saving} data-testid="profile-submit">
            {submitLabel}
          </Button>
          {secondaryAction}
          <span aria-live="polite" className="text-sm text-emerald-700" data-testid="profile-saved">
            {saved ? "Saved." : ""}
          </span>
          <span className="ml-auto text-xs text-stone-500">
            <span className="text-red-600">*</span> required
          </span>
        </div>
      </Card>
    </form>
  );
}
