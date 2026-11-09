"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  draftOpportunity,
  getDraftConfig,
  type DraftResponse,
} from "@/lib/adminDraft";
import { useAdmin } from "@/components/admin/AdminGate";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";

const MIN = 40;
const MAX = 20000;

function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 503 || e.code === "ai_not_configured")
      return "AI drafting isn't configured on this server. You can still fill the listing in by hand.";
    if (e.status === 502 || e.code === "ai_draft_failed")
      return "The drafter couldn't read that post just now. Try again, or fill the listing in by hand.";
    if (e.status === 429)
      return "Too many drafts this hour. Please wait a bit, or fill the listing in by hand.";
    return e.message;
  }
  return "Something went wrong while drafting. Try again.";
}

/**
 * "Paste the forwarded description" panel. The editor passes whether the form
 * already holds typed input (we confirm before the draft overwrites it) and
 * receives the DraftResponse via onDraft. `defaultCollapsed` is for existing
 * listings.
 */
export function PasteToFill({
  opportunityId,
  hasUserInput,
  onDraft,
  defaultCollapsed = false,
}: {
  opportunityId: number | null;
  hasUserInput: boolean;
  onDraft: (r: DraftResponse) => void;
  defaultCollapsed?: boolean;
}) {
  const { adminKey } = useAdmin();
  const [open, setOpen] = useState(!defaultCollapsed);
  const [config, setConfig] = useState<
    { available: boolean; model: string } | "loading" | "failed"
  >("loading");
  const [text, setText] = useState("");
  const [keepPartner, setKeepPartner] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [cost, setCost] = useState<{ model: string; usd: number } | null>(null);

  useEffect(() => {
    let live = true;
    getDraftConfig(adminKey)
      .then((c) => live && setConfig(c))
      .catch(() => live && setConfig("failed"));
    return () => {
      live = false;
    };
  }, [adminKey]);

  const trimmed = text.trim().length;
  const tooShort = trimmed > 0 && trimmed < MIN;
  const tooLong = trimmed > MAX;
  const notConfigured = config !== "loading" && config !== "failed" && !config.available;

  async function run() {
    setConfirming(false);
    setBusy(true);
    setError(null);
    try {
      const r = await draftOpportunity(adminKey, {
        text: text.trim(),
        opportunity_id: opportunityId,
        keep_partner_identity: keepPartner,
      });
      setCost({ model: r.model, usd: r.cost_usd });
      onDraft(r);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function onClickDraft() {
    if (hasUserInput) setConfirming(true);
    else void run();
  }

  return (
    <section
      data-testid="paste-to-fill"
      className="rounded-xl border border-stone-200 bg-stone-50 p-4"
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between text-left"
      >
        <span className="text-sm font-semibold text-stone-800">
          Paste the forwarded description
        </span>
        <span className="text-xs text-stone-500">{open ? "Hide" : "Show"}</span>
      </button>

      {open && (
        <div className="mt-3 space-y-3">
          {notConfigured ? (
            <p
              data-testid="ai-not-configured"
              className="rounded-lg bg-stone-100 px-3 py-2 text-sm text-stone-600"
            >
              AI drafting not configured — you can still fill the listing in by hand.
            </p>
          ) : (
            <>
              <p className="text-xs text-stone-500">
                Paste the post or email you were forwarded. The fields below are
                filled in as a draft for you to check — nothing is saved until you
                save the listing.
              </p>
              <textarea
                data-testid="paste-textarea"
                aria-label="Forwarded description"
                value={text}
                onChange={(e) => setText(e.target.value)}
                disabled={busy}
                rows={6}
                className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm text-stone-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200"
                placeholder="Paste the forwarded description here…"
              />
              {(tooShort || tooLong) && (
                <p className="text-xs text-red-600">
                  {tooShort
                    ? `Paste at least ${MIN} characters.`
                    : `That's too long — keep it under ${MAX.toLocaleString()} characters.`}
                </p>
              )}
              <label className="flex items-center gap-2 text-sm text-stone-700">
                <input
                  data-testid="keep-partner-toggle"
                  type="checkbox"
                  checked={keepPartner}
                  onChange={(e) => setKeepPartner(e.target.checked)}
                  disabled={busy}
                />
                Keep the partner&apos;s name in the public text
              </label>

              {confirming && (
                <div
                  data-testid="draft-confirm"
                  role="alertdialog"
                  className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"
                >
                  <p>This will overwrite what you&apos;ve already typed in the form. Continue?</p>
                  <div className="mt-2 flex gap-2">
                    <Button size="sm" data-testid="draft-confirm-yes" onClick={() => void run()}>
                      Overwrite
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      data-testid="draft-confirm-no"
                      onClick={() => setConfirming(false)}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              {busy && (
                <div data-testid="draft-skeleton" aria-busy="true" className="space-y-2">
                  <Skeleton className="h-4 w-2/3" />
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-5/6" />
                </div>
              )}

              {error && (
                <p
                  data-testid="draft-error"
                  role="alert"
                  className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700"
                >
                  {error}
                </p>
              )}

              <div className="flex flex-wrap items-center gap-3">
                <Button
                  data-testid="draft-button"
                  onClick={onClickDraft}
                  loading={busy}
                  disabled={
                    busy || config === "loading" || trimmed < MIN || tooLong || confirming
                  }
                >
                  Draft
                </Button>
                {cost && !busy && (
                  <span data-testid="draft-cost" className="text-xs text-stone-500">
                    Drafted with {cost.model} · ${cost.usd.toFixed(4)}
                  </span>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
