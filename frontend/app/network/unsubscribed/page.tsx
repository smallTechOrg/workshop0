"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { NetworkShell } from "@/components/network/NetworkShell";

type Kind = "alerts" | "digest";

const LABEL: Record<Kind, string> = {
  alerts: "new-opportunity alerts",
  digest: "the weekly digest",
};

const INVALID =
  "This unsubscribe link isn't valid. Sign in and use Email preferences to manage what you receive.";

function isKind(v: string | null): v is Kind {
  return v === "alerts" || v === "digest";
}

type View =
  | { step: "loading" }
  | { step: "confirm"; kind: Kind; token: string }
  | { step: "working"; kind: Kind; token: string }
  | { step: "done"; kind: Kind }
  | { step: "error"; text: string };

export default function UnsubscribedPage() {
  const [view, setView] = useState<View>({ step: "loading" });

  useEffect(() => {
    document.title = "Unsubscribe — Workshop0";
    const p = new URLSearchParams(window.location.search);
    const confirm = p.get("confirm");
    const token = p.get("t");
    const kind = p.get("kind");
    if (p.get("error") === "invalid_link") setView({ step: "error", text: INVALID });
    else if (isKind(confirm) && token) setView({ step: "confirm", kind: confirm, token });
    else if (isKind(kind)) setView({ step: "done", kind });
    else
      setView({
        step: "error",
        text: "Nothing to show here. Sign in and use Email preferences to manage what you receive.",
      });
  }, []);

  async function confirmUnsubscribe(kind: Kind, token: string) {
    setView({ step: "working", kind, token });
    try {
      const res = await fetch("/api/email/unsubscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "workshop0" },
        body: JSON.stringify({ t: token }),
      });
      if (!res.ok) {
        setView({ step: "error", text: INVALID });
        return;
      }
      // Drop the token from the address bar once it has been used.
      window.history.replaceState(null, "", `?kind=${kind}`);
      setView({ step: "done", kind });
    } catch {
      setView({ step: "error", text: "Something went wrong. Check your connection and try again." });
    }
  }

  return (
    <NetworkShell>
      <div className="mx-auto max-w-xl px-4 py-12 sm:px-6">
        <Card className="space-y-4 p-6 text-center">
          {view.step === "loading" && (
            <p className="text-sm text-stone-500" aria-busy="true">Loading…</p>
          )}
          {(view.step === "confirm" || view.step === "working") && (
            <>
              <p data-testid="unsubscribe-question" className="text-stone-800">
                Stop receiving {LABEL[view.kind]}?
              </p>
              <button
                type="button"
                data-testid="unsubscribe-confirm"
                disabled={view.step === "working"}
                onClick={() => confirmUnsubscribe(view.kind, view.token)}
                className="rounded-md bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-800 disabled:opacity-60"
              >
                {view.step === "working" ? "Unsubscribing…" : "Unsubscribe"}
              </button>
            </>
          )}
          {view.step === "done" && (
            <p data-testid="unsubscribed-message" className="text-stone-800" role="status">
              You're unsubscribed from {LABEL[view.kind]}.
            </p>
          )}
          {view.step === "error" && (
            <p data-testid="unsubscribed-message" className="text-red-700" role="alert">
              {view.text}
            </p>
          )}
          <a
            href="/app/network/searches/"
            className="inline-block text-sm font-medium text-brand-700 underline underline-offset-4"
          >
            Manage email preferences
          </a>
        </Card>
      </div>
    </NetworkShell>
  );
}
