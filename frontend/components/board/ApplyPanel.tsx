"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { signInToApplyHref } from "@/lib/apply";
import { useCurrentUser } from "@/lib/networkAuth";
import {
  applyTo,
  errorText,
  listMyApplications,
  NOTE_MAX,
  STATUS_LABELS,
  STATUS_TONES,
  withdrawApplication,
  type MyApplication,
} from "@/lib/networkApplications";

/** Apply control for an OPEN listing: signed-out / no-profile / apply form / applied states. */
export function ApplyPanel({ opportunityId, slug }: { opportunityId: number; slug: string }) {
  const { user, loading, error: authError, refresh } = useCurrentUser();
  const [app, setApp] = useState<MyApplication | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signedIn = !!user;
  const hasProfile = !!user?.has_profile;

  useEffect(() => {
    if (!signedIn || !hasProfile) return;
    let live = true;
    setLoadError(null);
    listMyApplications()
      .then((r) => {
        if (!live) return;
        setApp(r.applications.find((a) => a.opportunity_id === opportunityId) ?? null);
        setLoaded(true);
      })
      .catch((e) => {
        if (live) setLoadError(errorText(e));
      });
    return () => {
      live = false;
    };
  }, [signedIn, hasProfile, opportunityId]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const r = await applyTo(opportunityId, note);
      setApp(r.application);
    } catch (e) {
      const code = (e as { code?: string }).code;
      if (code === "already_applied") {
        try {
          const r = await listMyApplications();
          setApp(r.applications.find((a) => a.opportunity_id === opportunityId) ?? null);
        } catch {
          setError(errorText(e));
        }
      } else {
        setError(errorText(e));
      }
    } finally {
      setBusy(false);
    }
  }

  async function withdraw() {
    if (!app) return;
    setBusy(true);
    setError(null);
    try {
      const r = await withdrawApplication(app.id);
      setApp(r.application);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <Skeleton data-testid="apply-loading" className="h-10 w-full" />;
  }
  if (authError) {
    return (
      <div data-testid="apply-error" role="alert" className="space-y-2 text-sm text-red-700">
        <p>{authError}</p>
        <Button size="sm" variant="secondary" onClick={() => void refresh()}>
          Try again
        </Button>
      </div>
    );
  }
  if (!user) {
    return (
      <div className="space-y-2" data-testid="apply-signed-out">
        <a
          href={signInToApplyHref(slug)}
          data-testid="apply-signin"
          className="inline-flex w-full items-center justify-center rounded-lg bg-brand-600 px-4 py-2 font-medium text-white shadow-sm hover:bg-brand-700"
        >
          Sign in to apply
        </a>
        <p className="text-xs text-stone-500">Sign in with Google to apply with your trainer profile.</p>
      </div>
    );
  }
  if (!hasProfile) {
    return (
      <div className="space-y-2" data-testid="apply-no-profile">
        <p className="text-sm text-stone-700">Create your trainer profile to apply.</p>
        <a
          href="/app/network/join/"
          className="inline-flex w-full items-center justify-center rounded-lg bg-brand-600 px-4 py-2 font-medium text-white shadow-sm hover:bg-brand-700"
        >
          Create your profile
        </a>
      </div>
    );
  }
  if (loadError) {
    return (
      <p data-testid="apply-error" role="alert" className="text-sm text-red-700">
        {loadError}
      </p>
    );
  }
  if (!loaded) return <Skeleton data-testid="apply-loading" className="h-10 w-full" />;

  if (app) {
    const canWithdraw = app.status === "applied" || app.status === "shortlisted";
    return (
      <div className="space-y-2" data-testid="apply-applied">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-stone-800">
            {app.status === "withdrawn" ? "You withdrew your application" : "You've applied"}
          </span>
          <Badge tone={STATUS_TONES[app.status]} data-testid="apply-status">
            {STATUS_LABELS[app.status]}
          </Badge>
        </div>
        {app.note && <p className="text-xs text-stone-500">Your note: {app.note}</p>}
        <div className="flex items-center gap-3 text-sm">
          <a href="/app/network/applications/" className="font-medium text-brand-700 underline underline-offset-4">
            My applications
          </a>
          {canWithdraw && (
            <Button size="sm" variant="secondary" loading={busy} onClick={() => void withdraw()}>
              Withdraw
            </Button>
          )}
        </div>
        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <form
      data-testid="apply-form"
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <label htmlFor="apply-note" className="block text-sm font-medium text-stone-700">
        Note to smallTech <span className="font-normal text-stone-400">(optional)</span>
      </label>
      <textarea
        id="apply-note"
        value={note}
        maxLength={NOTE_MAX}
        onChange={(e) => setNote(e.target.value)}
        rows={3}
        className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-200"
        placeholder="Why you're a fit, availability…"
      />
      <p className="text-right text-xs text-stone-400">
        {note.length}/{NOTE_MAX}
      </p>
      <Button type="submit" loading={busy} className="w-full" data-testid="apply-submit">
        Apply
      </Button>
      {error && (
        <p role="alert" data-testid="apply-error" className="text-sm text-red-700">
          {error}
        </p>
      )}
    </form>
  );
}
