"use client";

/**
 * CV intake (capabilities.md C12, onboarding step 1) — three ways in, as tabs:
 * **Upload CV** (PDF/DOCX ≤5 MB, drag-and-drop), **LinkedIn PDF** (Save-to-PDF
 * how-to + upload) and **Paste text** (200–30000 chars). After submit the
 * "Reading your CV…" skeleton polls `GET /api/me/cv/draft` every 1.5 s for up
 * to 60 s, then hands the outcome to the page:
 *   ready            → the drafted ProfileInput + its autofilled fields
 *   failed / skipped → no draft (the page shows an empty form with a calm note)
 *   still pending    → treated like failed after 60 s (never an endless spinner)
 *
 * `waitForDraft={false}` (My profile → Replace CV) only uploads and reports back.
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { cn } from "@/lib/format";
import {
  DRAFT_POLL_LIMIT_MS,
  DRAFT_POLL_MS,
  MAX_CV_BYTES,
  PASTE_MAX,
  PASTE_MIN,
  cvErrorMessage,
  getDraft,
  submitCvText,
  uploadCv,
  type CvSummary,
  type DraftPayload,
  type DraftStatus,
} from "@/lib/network";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

export type IntakeOutcome = {
  status: Exclude<DraftStatus, "pending"> | "timeout";
  draft: DraftPayload["draft"];
  autofilled: string[];
};

type Tab = "upload" | "linkedin" | "paste";

const TABS: { id: Tab; label: string }[] = [
  { id: "upload", label: "Upload CV" },
  { id: "linkedin", label: "LinkedIn PDF" },
  { id: "paste", label: "Paste text" },
];

function fileProblem(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!name.endsWith(".pdf") && !name.endsWith(".docx")) {
    return "We can read PDF and DOCX files only — save your CV as one of those, or paste the text.";
  }
  if (file.size > MAX_CV_BYTES) {
    return "That file is larger than 5 MB — try a smaller export, or paste the text instead.";
  }
  if (file.size === 0) return "That file is empty — pick another one.";
  return null;
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** The "Reading your CV…" skeleton — mirrors the review form's shape. */
export function ReadingSkeleton() {
  return (
    <Card className="p-6" data-testid="cv-reading" aria-busy="true">
      <div className="flex items-center gap-3">
        <span
          aria-hidden="true"
          className="inline-block size-5 animate-spin rounded-full border-2 border-brand-600 border-t-transparent"
        />
        <p role="status" className="font-medium text-stone-900">
          Reading your CV…
        </p>
      </div>
      <p className="mt-1 text-sm text-stone-500">
        We're drafting your profile — this usually takes a few seconds.
      </p>
      <div className="mt-6 space-y-4">
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-24 w-full" />
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-24 rounded-full" />
          ))}
        </div>
      </div>
    </Card>
  );
}

function DropZone({
  file,
  onFile,
  disabled,
  hint,
}: {
  file: File | null;
  onFile: (f: File) => void;
  disabled: boolean;
  hint: string;
}) {
  const inputId = useId();
  const [over, setOver] = useState(false);
  return (
    <label
      htmlFor={inputId}
      data-testid="cv-dropzone"
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f && !disabled) onFile(f);
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors",
        over ? "border-brand-500 bg-brand-50" : "border-stone-300 bg-stone-50 hover:border-stone-400",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <input
        id={inputId}
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="sr-only"
        disabled={disabled}
        data-testid="cv-file-input"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="size-8 text-stone-400">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V3m0 0L7.5 7.5M12 3l4.5 4.5M3 15v3.75A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V15" />
      </svg>
      {file ? (
        <span className="text-sm text-stone-800" data-testid="cv-selected-file">
          <span className="font-medium">{file.name}</span>{" "}
          <span className="text-stone-500">({formatSize(file.size)}) — choose another</span>
        </span>
      ) : (
        <span className="text-sm text-stone-700">
          <span className="font-medium text-brand-700 underline underline-offset-4">Choose a file</span>{" "}
          or drop it here
        </span>
      )}
      <span className="text-xs text-stone-500">{hint}</span>
    </label>
  );
}

export function CvIntake({
  onOutcome,
  onUploaded,
  waitForDraft = true,
  resumePolling = false,
  replaceLabel = "Replace my CV",
}: {
  /** Submit label when `waitForDraft` is false (My profile). */
  replaceLabel?: string;
  /** Called once drafting has finished (or timed out). */
  onOutcome?: (outcome: IntakeOutcome) => void;
  /** Called as soon as the CV is stored (before drafting). */
  onUploaded?: (cv: CvSummary) => void;
  waitForDraft?: boolean;
  /** Start in the polling state (a CV was already submitted, e.g. after a reload). */
  resumePolling?: boolean;
}) {
  const [tab, setTab] = useState<Tab>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [polling, setPolling] = useState(resumePolling);
  const pasteId = useId();
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({
    upload: null,
    linkedin: null,
    paste: null,
  });
  const outcomeRef = useRef(onOutcome);
  outcomeRef.current = onOutcome;

  // Poll the draft until it leaves `pending` (≤60 s).
  useEffect(() => {
    if (!polling) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();
    let networkFailures = 0;

    const finish = (o: IntakeOutcome) => {
      if (cancelled) return;
      setPolling(false);
      outcomeRef.current?.(o);
    };

    const tick = async () => {
      try {
        const d = await getDraft();
        networkFailures = 0;
        if (d.draft_status !== "pending") {
          finish({
            status: d.draft_status,
            draft: d.draft_status === "ready" ? d.draft : null,
            autofilled: d.draft_status === "ready" ? d.autofilled_fields : [],
          });
          return;
        }
      } catch {
        // A blip while polling is not fatal; give up after a few in a row.
        networkFailures += 1;
        if (networkFailures >= 4) {
          finish({ status: "failed", draft: null, autofilled: [] });
          return;
        }
      }
      if (Date.now() - started >= DRAFT_POLL_LIMIT_MS) {
        finish({ status: "timeout", draft: null, autofilled: [] });
        return;
      }
      if (!cancelled) timer = setTimeout(tick, DRAFT_POLL_MS);
    };

    timer = setTimeout(tick, DRAFT_POLL_MS);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [polling]);

  const afterSubmit = useCallback(
    (cv: CvSummary) => {
      onUploaded?.(cv);
      if (!waitForDraft) return;
      if (cv.draft_status === "pending") setPolling(true);
      else
        outcomeRef.current?.({
          status: cv.draft_status === "ready" ? "failed" : cv.draft_status,
          draft: null,
          autofilled: [],
        });
    },
    [onUploaded, waitForDraft],
  );

  async function submitFile() {
    if (!file) return;
    const problem = fileProblem(file);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { cv } = await uploadCv(file);
      setFile(null);
      afterSubmit(cv);
    } catch (err) {
      setError(cvErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitText() {
    const trimmed = text.trim();
    if (trimmed.length < PASTE_MIN) {
      setError(`Please paste at least ${PASTE_MIN} characters — a full CV or your LinkedIn "About" and "Experience" sections.`);
      return;
    }
    if (trimmed.length > PASTE_MAX) {
      setError(`Please paste at most ${PASTE_MAX} characters.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { cv } = await submitCvText(trimmed);
      setText("");
      afterSubmit(cv);
    } catch (err) {
      setError(cvErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function chooseFile(f: File) {
    setFile(f);
    setError(fileProblem(f));
  }

  function onTabKey(e: React.KeyboardEvent, current: Tab) {
    const i = TABS.findIndex((t) => t.id === current);
    let next: number | null = null;
    if (e.key === "ArrowRight") next = (i + 1) % TABS.length;
    if (e.key === "ArrowLeft") next = (i - 1 + TABS.length) % TABS.length;
    if (next === null) return;
    e.preventDefault();
    const t = TABS[next].id;
    setTab(t);
    setError(null);
    tabRefs.current[t]?.focus();
  }

  // While uploading (text extraction is synchronous) or polling, show the skeleton.
  if ((busy || polling) && waitForDraft) return <ReadingSkeleton />;

  const tabId = (t: Tab) => `cv-tab-${t}`;
  const panelId = (t: Tab) => `cv-panel-${t}`;
  const fileButtonLabel = tab === "linkedin" ? "Read my LinkedIn PDF" : "Read my CV";

  return (
    <Card className="overflow-hidden" data-testid="cv-intake">
      <div role="tablist" aria-label="How to add your CV" className="flex border-b border-stone-200 bg-stone-50/60">
        {TABS.map((t) => {
          const on = tab === t.id;
          return (
            <button
              key={t.id}
              ref={(el) => {
                tabRefs.current[t.id] = el;
              }}
              id={tabId(t.id)}
              type="button"
              role="tab"
              aria-selected={on}
              aria-controls={panelId(t.id)}
              tabIndex={on ? 0 : -1}
              data-testid={`cv-tab-${t.id}`}
              onClick={() => {
                setTab(t.id);
                setError(null);
              }}
              onKeyDown={(e) => onTabKey(e, t.id)}
              className={cn(
                "flex-1 border-b-2 px-3 py-3 text-sm font-medium transition-colors",
                on
                  ? "border-brand-600 bg-white text-brand-700"
                  : "border-transparent text-stone-600 hover:text-stone-900",
              )}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={panelId(tab)}
        aria-labelledby={tabId(tab)}
        className="space-y-4 p-5 sm:p-6"
      >
        {tab === "upload" && (
          <>
            <p className="text-sm text-stone-600">
              Your CV as a PDF or Word (.docx) file, up to 5 MB.
            </p>
            <DropZone file={file} onFile={chooseFile} disabled={busy} hint="PDF or DOCX · max 5 MB" />
          </>
        )}

        {tab === "linkedin" && (
          <>
            <div className="rounded-lg border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900" data-testid="linkedin-howto">
              <p className="font-medium">Save your LinkedIn profile as a PDF:</p>
              <ol className="mt-2 list-decimal space-y-1 pl-5">
                <li>Open your profile on linkedin.com (on a computer).</li>
                <li>
                  Click <strong>More</strong> (or <strong>Resources</strong>) under your name.
                </li>
                <li>
                  Choose <strong>Save to PDF</strong> — LinkedIn downloads the file.
                </li>
                <li>Upload that PDF here.</li>
              </ol>
            </div>
            <DropZone file={file} onFile={chooseFile} disabled={busy} hint="The PDF LinkedIn saved for you" />
          </>
        )}

        {tab === "paste" && (
          <div>
            <label htmlFor={pasteId} className="mb-1.5 block text-sm font-medium text-stone-800">
              Your CV or LinkedIn text
            </label>
            <textarea
              id={pasteId}
              data-testid="cv-paste-text"
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                if (error) setError(null);
              }}
              rows={10}
              maxLength={PASTE_MAX + 1000}
              placeholder={'Paste your CV, or your LinkedIn "About" and "Experience" sections.'}
              className="block w-full resize-y rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900 shadow-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
            />
            <p
              className={cn(
                "mt-1 text-xs",
                text.trim().length > PASTE_MAX ? "text-red-700" : "text-stone-500",
              )}
            >
              {text.trim().length.toLocaleString()} characters
              {text.trim().length < PASTE_MIN ? ` · at least ${PASTE_MIN}` : ""}
            </p>
          </div>
        )}

        <p className="text-sm text-stone-500" data-testid="linkedin-links-note">
          We can't read LinkedIn links directly — LinkedIn doesn't allow it.
        </p>

        {error && (
          <p
            role="alert"
            data-testid="cv-error"
            className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
          >
            {error}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-3">
          {tab === "paste" ? (
            <Button
              onClick={() => void submitText()}
              loading={busy}
              disabled={text.trim().length === 0}
              data-testid="cv-submit"
            >
              {waitForDraft ? "Read my text" : "Use this text as my CV"}
            </Button>
          ) : (
            <Button
              onClick={() => void submitFile()}
              loading={busy}
              disabled={!file || Boolean(file && fileProblem(file))}
              data-testid="cv-submit"
            >
              {waitForDraft ? fileButtonLabel : replaceLabel}
            </Button>
          )}
          {busy && !waitForDraft && <span className="text-sm text-stone-500">Uploading…</span>}
        </div>
      </div>
    </Card>
  );
}
