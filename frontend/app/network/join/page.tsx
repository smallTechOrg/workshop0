"use client";

/**
 * Onboarding — `/app/network/join/` (capabilities.md C12; the target of the
 * pretty `/invite/<token>` link).
 *
 *   signed out          → sign-in card (`signInUrl("/app/network/join/", invite)`)
 *   has a profile       → My profile  `/app/network/me/`
 *   step 1 (CV intake)  → three tabs → "Reading your CV…" (polls ≤60 s)
 *   step 2 (review)     → the shared ProfileForm, pre-filled where possible,
 *                         consent → **Create my profile** → My profile
 *
 * **Verified** is shown ONLY from `user.invite_accepted` (server truth from
 * `/api/auth/me`) — the `?invite=` query parameter never grants it.
 */

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import { useCurrentUser, type CurrentUser } from "@/lib/networkAuth";
import {
  createProfile,
  emptyProfileInput,
  getDraft,
  normalizeProfileInput,
  type ProfileInput,
} from "@/lib/network";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { GoogleButton } from "@/components/network/auth/GoogleButton";
import { NetworkShell } from "@/components/network/profile/NetworkShell";
import { CvIntake, type IntakeOutcome } from "@/components/network/profile/CvIntake";
import { ProfileForm } from "@/components/network/profile/ProfileForm";

const JOIN_PATH = "/app/network/join/";

/** `invite_accepted` is part of `/api/auth/me` (api.md §Phase 11); read defensively. */
function inviteAccepted(user: CurrentUser | null): boolean {
  return (user as (CurrentUser & { invite_accepted?: boolean }) | null)?.invite_accepted === true;
}

type Step =
  | { kind: "checking" }
  | { kind: "intake" }
  | { kind: "polling" }
  | {
      kind: "review";
      initial: ProfileInput;
      autofilled: string[];
      note: "none" | "no_prefill" | "skipped_by_user";
      key: number;
    };

function PageSkeleton({ label }: { label: string }) {
  return (
    <div aria-busy="true" aria-label={label} className="space-y-4">
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function VerifiedBanner() {
  return (
    <Card
      data-testid="invite-verified"
      className="flex flex-wrap items-center gap-3 border-emerald-200 bg-emerald-50/70 p-4"
    >
      <Badge tone="success" data-testid="verified-badge">
        <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="size-3.5">
          <path
            fillRule="evenodd"
            d="M16.403 12.652a3 3 0 0 0 0-5.304 3 3 0 0 0-3.75-3.751 3 3 0 0 0-5.305 0 3 3 0 0 0-3.751 3.75 3 3 0 0 0 0 5.305 3 3 0 0 0 3.75 3.751 3 3 0 0 0 5.305 0 3 3 0 0 0 3.751-3.75Zm-2.546-4.46a.75.75 0 0 0-1.214-.883l-3.483 4.79-1.88-1.88a.75.75 0 1 0-1.06 1.061l2.5 2.5a.75.75 0 0 0 1.137-.089l4-5.5Z"
            clipRule="evenodd"
          />
        </svg>
        Verified
      </Badge>
      <p className="text-sm text-emerald-900">
        You joined through a smallTech invite — your profile starts out verified.
      </p>
    </Card>
  );
}

function StepHeader({ step, title, body }: { step: 1 | 2; title: string; body: string }) {
  return (
    <div>
      <p className="text-sm font-semibold tracking-wide text-brand-700 uppercase">
        Step {step} of 2
      </p>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight text-stone-900 sm:text-3xl">
        {title}
      </h1>
      <p className="mt-2 text-stone-600">{body}</p>
    </div>
  );
}

function JoinContent() {
  const router = useRouter();
  const params = useSearchParams();
  const invite = params.get("invite") ?? undefined;
  const { user, loading, error, refresh } = useCurrentUser();
  const [step, setStep] = useState<Step>({ kind: "checking" });

  useEffect(() => {
    document.title = "Join the trainer network — Workshop0";
  }, []);

  // Already a member → My profile (basePath "/app" is prepended by the router).
  useEffect(() => {
    if (user?.has_profile) router.replace("/network/me/");
  }, [user?.has_profile, router]);

  // Signed in without a profile: resume a CV that's already in (reload-safe).
  const userId = user?.id;
  const hasProfile = user?.has_profile;
  useEffect(() => {
    if (!userId || hasProfile) return;
    let cancelled = false;
    getDraft()
      .then((d) => {
        if (cancelled) return;
        if (d.draft_status === "pending") setStep({ kind: "polling" });
        else if (d.draft_status === "ready" && d.draft)
          setStep({
            kind: "review",
            initial: normalizeProfileInput(d.draft),
            autofilled: d.autofilled_fields,
            note: "none",
            key: Date.now(),
          });
        else setStep({ kind: "intake" });
      })
      .catch(() => {
        // 404 = no CV yet (the normal first visit); anything else → just start at step 1.
        if (!cancelled) setStep({ kind: "intake" });
      });
    return () => {
      cancelled = true;
    };
  }, [userId, hasProfile]);

  const onOutcome = useCallback((o: IntakeOutcome) => {
    if (o.status === "ready" && o.draft) {
      setStep({
        kind: "review",
        initial: normalizeProfileInput(o.draft),
        autofilled: o.autofilled,
        note: "none",
        key: Date.now(),
      });
    } else {
      setStep({
        kind: "review",
        initial: emptyProfileInput(),
        autofilled: [],
        note: "no_prefill",
        key: Date.now(),
      });
    }
  }, []);

  async function handleCreate(input: ProfileInput, consent: boolean) {
    try {
      await createProfile(input, consent);
    } catch (err) {
      if (err instanceof ApiError && err.code === "profile_exists") {
        await refresh();
        router.replace("/network/me/");
        return;
      }
      throw err;
    }
    await refresh();
    router.replace("/network/me/");
  }

  // ------------------------------------------------------------- render
  if (loading && !user) return <PageSkeleton label="Checking sign-in" />;

  if (error && !user) {
    return (
      <Card role="alert" data-testid="join-load-error" className="mx-auto max-w-md space-y-3 p-6">
        <p className="font-medium text-stone-800">{error}</p>
        <Button variant="secondary" onClick={() => void refresh()}>
          Try again
        </Button>
      </Card>
    );
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-md" data-testid="join-signed-out">
        <Card className="space-y-4 p-6">
          {invite ? (
            <>
              <h1 className="text-xl font-semibold text-stone-900">
                You&apos;re invited to the smallTech trainer network
              </h1>
              <p className="text-sm text-stone-600">
                Sign in with the Google account for the email the invite was sent to — your
                profile will start out verified.
              </p>
            </>
          ) : (
            <>
              <h1 className="text-xl font-semibold text-stone-900">
                Join the smallTech trainer network
              </h1>
              <p className="text-sm text-stone-600">
                Sign in, drop your CV, check one screen — and you&apos;re in.
              </p>
            </>
          )}
          <GoogleButton next={JOIN_PATH} invite={invite} />
          <p className="text-xs text-stone-500">
            We only use your Google account to sign you in. You can delete your account at any
            time.
          </p>
        </Card>
      </div>
    );
  }

  if (user.has_profile) return <PageSkeleton label="Opening your profile" />;

  const verified = inviteAccepted(user);

  return (
    <div className="space-y-6">
      {verified && <VerifiedBanner />}
      {!verified && invite && (
        <Card data-testid="invite-not-applied" className="space-y-3 p-4">
          <p className="text-sm text-stone-700">
            You opened an invite link, but it hasn&apos;t been applied to this account. If the
            invite was sent to a different email, sign in with that Google account.
          </p>
          <GoogleButton next={JOIN_PATH} invite={invite} label="Use my invite" className="sm:w-auto" />
        </Card>
      )}

      {step.kind === "checking" && <PageSkeleton label="Loading onboarding" />}

      {(step.kind === "intake" || step.kind === "polling") && (
        <>
          <StepHeader
            step={1}
            title="Add your CV"
            body="We'll draft your profile from it — you check everything on the next screen."
          />
          {step.kind === "polling" ? (
            <CvIntake onOutcome={onOutcome} resumePolling />
          ) : (
            <CvIntake onOutcome={onOutcome} />
          )}
          {step.kind === "intake" && (
            <p className="text-sm text-stone-500">
              No CV to hand?{" "}
              <button
                type="button"
                data-testid="skip-cv"
                onClick={() =>
                  setStep({
                    kind: "review",
                    initial: emptyProfileInput(),
                    autofilled: [],
                    note: "skipped_by_user",
                    key: Date.now(),
                  })
                }
                className="font-medium text-brand-700 underline underline-offset-4 hover:text-brand-800"
              >
                Fill in the form yourself
              </button>{" "}
              — you can add a CV later from My profile.
            </p>
          )}
        </>
      )}

      {step.kind === "review" && (
        <>
          <StepHeader
            step={2}
            title="Review your profile"
            body="Everything is editable. Only a headline and one topic are required — you can add the rest later."
          />
          {step.note === "none" && step.autofilled.length > 0 && (
            <p className="text-sm text-stone-600" data-testid="review-prefilled-note">
              We pre-filled what we found. Fields with an amber chip came from your CV — give
              them a quick check.
            </p>
          )}
          {step.note === "no_prefill" && (
            <Card
              data-testid="review-no-prefill"
              className="border-amber-200 bg-amber-50/70 p-4 text-sm text-amber-900"
            >
              We couldn&apos;t pre-fill from your CV — fill in the basics below; you can add the
              rest later.
            </Card>
          )}
          <ProfileForm
            key={step.key}
            mode="create"
            initial={step.initial}
            autofilled={step.autofilled}
            submitLabel="Create my profile"
            onSubmit={handleCreate}
            secondaryAction={
              <Button
                variant="ghost"
                data-testid="review-use-different-cv"
                onClick={() => setStep({ kind: "intake" })}
              >
                Use a different CV
              </Button>
            }
          />
        </>
      )}
    </div>
  );
}

export default function JoinPage() {
  return (
    <NetworkShell>
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
        <Suspense fallback={<ReadingSkeletonFallback />}>
          <JoinContent />
        </Suspense>
      </div>
    </NetworkShell>
  );
}

function ReadingSkeletonFallback() {
  return <PageSkeleton label="Loading onboarding" />;
}
