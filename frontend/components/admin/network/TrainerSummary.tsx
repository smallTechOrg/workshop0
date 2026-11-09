"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import {
  downloadCv,
  formatRate,
  formatUsd,
  isAuthError,
  verifyTrainer,
  type TrainerDetail,
} from "@/lib/adminNetwork";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { useToast } from "@/components/ui/Toast";
import { useAdmin } from "@/components/admin/AdminGate";
import { TrainerAvatar } from "./TrainerAvatar";
import { VerifiedBadge } from "./VerifiedBadge";

const DRAFT_LABELS: Record<string, string> = {
  pending: "Draft in progress",
  ready: "Drafted by AI",
  failed: "AI draft failed",
  skipped: "AI drafting skipped",
};

const MISSING_LABELS: Record<string, string> = {
  headline: "headline",
  bio: "bio (80+ characters)",
  topics: "3+ topics",
  location: "city or remote",
  link: "a profile link",
  past_work: "past work",
  rate: "rate",
  availability: "weekly availability",
  available_from: "available-from date",
  cv: "CV",
};

function formatBytes(n: number | null): string {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** Trainer header: identity, verify, CV download, rate, completeness and drafting cost. */
export function TrainerSummary({
  detail,
  onUpdated,
  onDownloaded,
}: {
  detail: TrainerDetail;
  onUpdated: (next: TrainerDetail) => void;
  /** Called after a CV download starts, so the page can refresh its activity. */
  onDownloaded?: () => void;
}) {
  const { adminKey, onUnauthorized } = useAdmin();
  const toast = useToast();
  const { trainer: t, cv } = detail;
  const [verifying, setVerifying] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const fail = (err: unknown, fallback: string) => {
    if (isAuthError(err)) {
      onUnauthorized();
      return;
    }
    toast.show(err instanceof ApiError ? err.message : fallback, "error");
  };

  const toggleVerified = async () => {
    setVerifying(true);
    try {
      const next = await verifyTrainer(adminKey, t.id, !t.verified);
      onUpdated(next);
      toast.show(next.trainer.verified ? "Trainer verified." : "Verification removed.", "success");
    } catch (err) {
      fail(err, "Couldn't change verification.");
    } finally {
      setVerifying(false);
    }
  };

  const getCv = async () => {
    if (!cv) return;
    setDownloading(true);
    try {
      const fallback = cv.original_filename ?? `cv-${t.id}.${cv.has_file ? cv.source : "txt"}`;
      await downloadCv(adminKey, t.id, fallback);
      onDownloaded?.();
    } catch (err) {
      fail(err, "Couldn't download the CV.");
    } finally {
      setDownloading(false);
    }
  };

  const rate = formatRate(t.rate);
  const location = [t.city, t.remote_ok ? "Remote OK" : null].filter(Boolean).join(" · ");
  const pct = Math.max(0, Math.min(100, Math.round(t.completeness.pct)));

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-4">
          <TrainerAvatar name={t.display_name} src={t.avatar_url} size="lg" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold text-stone-900">{t.display_name}</h1>
              {t.verified && <VerifiedBadge />}
              {t.visibility === "public" && <Badge tone="info">In public directory</Badge>}
            </div>
            <p className="mt-0.5 text-sm text-stone-700">{t.headline}</p>
            <p className="mt-1 text-xs text-stone-500">
              <a href={`mailto:${t.email}`} className="hover:text-brand-700 hover:underline">
                {t.email}
              </a>
              {location ? ` · ${location}` : ""}
            </p>
            <p className="mt-0.5 text-xs text-stone-400">
              Joined {formatDate(t.created_at)}
              {t.last_login_at ? ` · last sign-in ${formatDate(t.last_login_at)}` : ""}
              {t.verified && t.verified_by
                ? ` · verified by ${t.verified_by}${t.verified_at ? ` on ${formatDate(t.verified_at)}` : ""}`
                : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => void getCv()}
            disabled={!cv}
            loading={downloading}
            title={cv ? undefined : "This trainer has no CV on file"}
          >
            Download CV
          </Button>
          <Button
            variant={t.verified ? "secondary" : "primary"}
            onClick={() => void toggleVerified()}
            loading={verifying}
          >
            {t.verified ? "Unverify" : "Verify"}
          </Button>
        </div>
      </div>

      <dl className="mt-5 grid gap-4 border-t border-stone-100 pt-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-xs text-stone-500">
            Rate <span className="text-stone-400">(admin only)</span>
          </dt>
          <dd className="mt-0.5 text-stone-800">{rate ?? <span className="text-stone-400">Not set</span>}</dd>
        </div>
        <div>
          <dt className="text-xs text-stone-500">Profile completeness</dt>
          <dd className="mt-1 flex items-center gap-2">
            <div className="h-1.5 w-24 overflow-hidden rounded-full bg-stone-200">
              <div
                className={pct >= 80 ? "h-full bg-emerald-500" : pct >= 50 ? "h-full bg-amber-500" : "h-full bg-stone-400"}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs tabular-nums text-stone-700">{pct}%</span>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-stone-500">CV</dt>
          <dd className="mt-0.5 text-stone-800">
            {cv ? (
              <>
                <span className="block truncate" title={cv.original_filename ?? undefined}>
                  {cv.original_filename ?? (cv.has_file ? `${cv.source.toUpperCase()} file` : "Pasted text")}
                </span>
                <span className="text-xs text-stone-400">
                  {[formatBytes(cv.size_bytes), cv.draft_status ? DRAFT_LABELS[cv.draft_status] ?? cv.draft_status : null, formatDate(cv.created_at)]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </>
            ) : (
              <span className="text-stone-400">No CV on file</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-stone-500">AI drafting cost</dt>
          <dd className="mt-0.5 tabular-nums text-stone-800" data-testid="trainer-ai-cost">
            {formatUsd(detail.ai_cost_usd)}
          </dd>
        </div>
      </dl>
      {t.completeness.missing.length > 0 && (
        <p className="mt-3 text-xs text-stone-400">
          Profile is missing: {t.completeness.missing.map((m) => MISSING_LABELS[m] ?? m).join(", ")}
        </p>
      )}
    </Card>
  );
}
