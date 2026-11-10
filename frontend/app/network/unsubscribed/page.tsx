"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { NetworkShell } from "@/components/network/profile/NetworkShell";

function messageFor(kind: string | null, error: string | null): { text: string; ok: boolean } {
  if (error === "invalid_link") {
    return { ok: false, text: "This unsubscribe link isn't valid. Sign in and use Email preferences to manage what you receive." };
  }
  if (kind === "alerts") return { ok: true, text: "You're unsubscribed from new-opportunity alerts." };
  if (kind === "digest") return { ok: true, text: "You're unsubscribed from the weekly digest." };
  return { ok: false, text: "Nothing to show here. Sign in and use Email preferences to manage what you receive." };
}

export default function UnsubscribedPage() {
  const [state, setState] = useState<{ kind: string | null; error: string | null } | null>(null);
  useEffect(() => {
    document.title = "Unsubscribed — Workshop0";
    const p = new URLSearchParams(window.location.search);
    setState({ kind: p.get("kind"), error: p.get("error") });
  }, []);

  const m = state ? messageFor(state.kind, state.error) : null;
  return (
    <NetworkShell>
      <div className="mx-auto max-w-xl px-4 py-12 sm:px-6">
        <Card className="space-y-4 p-6 text-center">
          {m ? (
            <p
              data-testid="unsubscribed-message"
              className={m.ok ? "text-stone-800" : "text-red-700"}
              role={m.ok ? "status" : "alert"}
            >
              {m.text}
            </p>
          ) : (
            <p className="text-sm text-stone-500" aria-busy="true">Loading…</p>
          )}
          <a href="/app/network/searches/" className="inline-block text-sm font-medium text-brand-700 underline underline-offset-4">
            Manage email preferences
          </a>
        </Card>
      </div>
    </NetworkShell>
  );
}
