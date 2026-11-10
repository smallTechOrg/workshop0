"use client";

/**
 * Sign-in — `/app/signin/` (spec/capabilities.md C11, api.md §Phase 11 Auth).
 *
 * Query params: `next` (where to land after sign-in; guarded to `/app/…`),
 * `invite` (an invite token carried through the OIDC round-trip — kept on the
 * Google button after `invite_email_mismatch` so the user can retry), `error`
 * (a callback failure code), `invite_email` (the masked invite address sent
 * with `invite_email_mismatch`) and `signed_out=1` (just signed out).
 *
 * States: loading · server unreachable (retry) · sign-in not configured
 * (labelled, non-error) · already signed in (continue / switch account) ·
 * ready (Continue with Google), with an error banner when `error` is set.
 */

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import { getAuthConfig, safeNext, useCurrentUser } from "@/lib/networkAuth";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { Avatar } from "@/components/network/auth/Avatar";
import { GoogleButton } from "@/components/network/auth/GoogleButton";
import { NetworkShell } from "@/components/network/NetworkShell";
import { signinErrorMessage } from "@/components/network/auth/signinErrors";

type ConfigState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; googleEnabled: boolean };

function SigninSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading sign-in" className="space-y-4">
      <Skeleton className="h-7 w-2/3" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-11 w-full" />
    </div>
  );
}

function ErrorBanner({ code, inviteEmail }: { code: string; inviteEmail: string | null }) {
  const msg = signinErrorMessage(code, inviteEmail);
  return (
    <div
      role="alert"
      data-testid="signin-error"
      data-code={code}
      className="rounded-lg border border-red-200 bg-red-50 px-4 py-3"
    >
      <p className="font-medium text-red-800">{msg.title}</p>
      {msg.hint && <p className="mt-0.5 text-sm text-red-700">{msg.hint}</p>}
    </div>
  );
}

function SigninInner() {
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const invite = params.get("invite") ?? undefined;
  const errorCode = params.get("error");
  const inviteEmail = params.get("invite_email");
  const signedOut = params.get("signed_out") === "1";

  const { user, loading: userLoading } = useCurrentUser();
  const [config, setConfig] = useState<ConfigState>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    document.title = "Sign in — Workshop0";
  }, []);

  useEffect(() => {
    let cancelled = false;
    setConfig({ kind: "loading" });
    getAuthConfig()
      .then((c) => {
        if (!cancelled) setConfig({ kind: "ready", googleEnabled: c.google_enabled });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setConfig({
          kind: "error",
          message:
            err instanceof ApiError && err.code === "network_error"
              ? "We couldn't reach the server — check your connection."
              : "Something went wrong on our side while loading sign-in.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);

  let body: React.ReactNode;
  if (config.kind === "loading" || (config.kind === "ready" && config.googleEnabled && userLoading)) {
    body = <SigninSkeleton />;
  } else if (config.kind === "error") {
    body = (
      <div role="alert" data-testid="signin-load-error" className="space-y-3">
        <p className="font-medium text-stone-800">{config.message}</p>
        <Button variant="secondary" onClick={retry}>
          Try again
        </Button>
      </div>
    );
  } else if (!config.googleEnabled) {
    body = (
      <div data-testid="signin-not-configured" className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold text-stone-900">
            Sign-in isn&apos;t set up yet
          </h1>
          <Badge tone="neutral">Not configured on this server</Badge>
        </div>
        <p className="text-stone-600">
          Google sign-in hasn&apos;t been enabled on this Workshop0 server, so trainer accounts
          aren&apos;t available here yet. Nothing is broken — the operator just needs to add
          the Google sign-in credentials.
        </p>
        <p className="text-sm text-stone-500">
          Running a workshop? Facilitators and participants don&apos;t need to sign in, and the
          admin console still opens with its access key.
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <a
            href="/app/opportunities/"
            className="rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-sm font-medium text-stone-800 shadow-sm hover:bg-stone-50"
          >
            Browse opportunities
          </a>
          <a
            href="/app/admin/"
            className="rounded-lg px-3 py-1.5 text-sm font-medium text-stone-600 hover:bg-stone-100"
          >
            Admin console
          </a>
        </div>
      </div>
    );
  } else if (user && !errorCode) {
    const name = user.display_name?.trim() || user.email;
    body = (
      <div data-testid="signin-already" className="space-y-4">
        <h1 className="text-xl font-semibold text-stone-900">You&apos;re signed in</h1>
        <div className="flex items-center gap-3 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5">
          <Avatar user={user} className="size-10" />
          <div className="min-w-0">
            <p className="truncate font-medium text-stone-900">{name}</p>
            <p className="truncate text-sm text-stone-500">{user.email}</p>
          </div>
        </div>
        {invite && (
          <p className="text-sm text-stone-600">
            To accept your invite, continue with the Google account it was sent to.
          </p>
        )}
        <a
          href={next}
          data-testid="signin-continue"
          className="inline-flex w-full items-center justify-center rounded-lg bg-brand-600 px-4 py-2.5 font-medium text-white shadow-sm hover:bg-brand-700"
        >
          Continue
        </a>
        <GoogleButton next={next} invite={invite} label="Use a different Google account" />
      </div>
    );
  } else {
    body = (
      <div className="space-y-5">
        <div>
          <h1 className="text-xl font-semibold text-stone-900">
            Sign in to the trainer network
          </h1>
          <p className="mt-1.5 text-stone-600">
            One click with Google — no password to remember. New here? Your account is created
            the first time you sign in.
          </p>
        </div>
        {errorCode && <ErrorBanner code={errorCode} inviteEmail={inviteEmail} />}
        {signedOut && !errorCode && (
          <p
            role="status"
            data-testid="signin-signed-out"
            className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-800"
          >
            You&apos;ve signed out.
          </p>
        )}
        {invite && !errorCode && (
          <p
            data-testid="signin-invite-note"
            className="rounded-lg border border-brand-200 bg-brand-50 px-4 py-2.5 text-sm text-brand-800"
          >
            You&apos;ve been invited to join. Sign in with the Google account the invite was
            sent to and your profile starts out verified.
          </p>
        )}
        <GoogleButton next={next} invite={invite} />
        <p className="text-xs text-stone-500">
          We only use your name, email and profile picture from Google.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md px-4 py-12 sm:py-16">
      <Card className="p-6 sm:p-8">{body}</Card>
    </div>
  );
}

export default function SigninPage() {
  return (
    <NetworkShell showAccount={false} variant="entry">
      <Suspense
        fallback={
          <div className="mx-auto max-w-md px-4 py-12 sm:py-16">
            <Card className="p-6 sm:p-8">
              <SigninSkeleton />
            </Card>
          </div>
        }
      >
        <SigninInner />
      </Suspense>
    </NetworkShell>
  );
}
