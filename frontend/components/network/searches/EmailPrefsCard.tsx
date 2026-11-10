"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { getEmailPrefs, setEmailPrefs, type EmailPrefs } from "@/lib/networkSearches";
import { errorText } from "@/lib/networkApplications";

const ROWS: { key: keyof EmailPrefs; label: string; hint: string; testid: string }[] = [
  { key: "alerts", label: "New-opportunity alerts", hint: "An email when a new listing matches one of your saved searches.", testid: "email-pref-alerts" },
  { key: "digest", label: "Weekly digest", hint: "One weekly summary of matching listings.", testid: "email-pref-digest" },
];

export function EmailPrefsCard() {
  const [prefs, setPrefs] = useState<EmailPrefs | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<keyof EmailPrefs | null>(null);

  useEffect(() => {
    getEmailPrefs().then(setPrefs).catch((e) => setError(errorText(e)));
  }, []);

  async function toggle(key: keyof EmailPrefs) {
    if (!prefs) return;
    setBusy(key);
    setError(null);
    try {
      setPrefs(await setEmailPrefs({ [key]: !prefs[key] }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="space-y-3 p-5" data-testid="email-prefs">
      <h2 className="text-lg font-semibold text-stone-900">Email preferences</h2>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      {!prefs && !error && <p className="text-sm text-stone-500" aria-busy="true">Loading…</p>}
      {prefs &&
        ROWS.map((r) => (
          <label key={r.key} className="flex items-start gap-3">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4"
              data-testid={r.testid}
              checked={prefs[r.key]}
              disabled={busy === r.key}
              onChange={() => void toggle(r.key)}
            />
            <span>
              <span className="block text-sm font-medium text-stone-900">{r.label}</span>
              <span className="block text-xs text-stone-600">{r.hint}</span>
            </span>
          </label>
        ))}
    </Card>
  );
}
