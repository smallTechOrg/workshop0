"use client";

/**
 * Network home — `/app/network/` (also the target of the pretty `/network`).
 *
 * Routes by sign-in state (spec/capabilities.md C11/C12):
 *   signed out            → a sign-in call to action (rendered here)
 *   signed in, no profile → onboarding  `/app/network/join/`
 *   signed in, profile    → My profile  `/app/network/me/`
 * Loading shows a skeleton; a failed sign-in check shows a retry.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { signInPageUrl, useCurrentUser } from "@/lib/networkAuth";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { GoogleButton } from "@/components/network/auth/GoogleButton";
import { NetworkShell } from "@/components/network/NetworkShell";

const BENEFITS: { title: string; body: string }[] = [
  {
    title: "Drop your CV, we draft the profile",
    body: "Upload a PDF or DOCX (or a LinkedIn PDF) and review a pre-filled profile on one screen.",
  },
  {
    title: "Get found for the right work",
    body: "smallTech matches partner workshops, engagements and roles to the topics you teach.",
  },
  {
    title: "You stay in control",
    body: "Your rates are visible to smallTech only, and you can delete your account at any time.",
  },
];

function RoutingSkeleton({ label }: { label: string }) {
  return (
    <div aria-busy="true" aria-label={label} className="mx-auto max-w-3xl space-y-4 px-4 py-12">
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}

export default function NetworkHomePage() {
  const router = useRouter();
  const { user, loading, error, refresh } = useCurrentUser();

  useEffect(() => {
    document.title = "Trainer network — Workshop0";
  }, []);

  const target = user ? (user.has_profile ? "/network/me/" : "/network/join/") : null;

  useEffect(() => {
    // basePath "/app" is prepended by the router.
    if (target) router.replace(target);
  }, [target, router]);

  let content: React.ReactNode;
  if (loading && !user) {
    content = <RoutingSkeleton label="Checking sign-in" />;
  } else if (error && !user) {
    content = (
      <div className="mx-auto max-w-md px-4 py-16">
        <Card role="alert" data-testid="network-load-error" className="space-y-3 p-6">
          <p className="font-medium text-stone-800">{error}</p>
          <Button variant="secondary" onClick={() => void refresh()}>
            Try again
          </Button>
        </Card>
      </div>
    );
  } else if (user) {
    content = (
      <div data-testid="network-redirecting">
        <RoutingSkeleton
          label={user.has_profile ? "Opening your profile" : "Opening onboarding"}
        />
        <p className="text-center text-sm text-stone-500">
          {user.has_profile ? "Opening your profile…" : "Let's set up your profile…"}{" "}
          <a
            className="underline underline-offset-4"
            href={user.has_profile ? "/app/network/me/" : "/app/network/join/"}
          >
            Continue
          </a>
        </p>
      </div>
    );
  } else {
    content = (
      <section data-testid="network-signed-out" className="mx-auto max-w-5xl px-4 py-12 sm:px-6 sm:py-16">
        <div className="grid items-start gap-10 lg:grid-cols-[1fr_22rem]">
          <div>
            <p className="text-sm font-semibold tracking-wide text-brand-700 uppercase">
              For tech trainers
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-balance text-stone-900 sm:text-4xl">
              Join the smallTech trainer network
            </h1>
            <p className="mt-3 text-lg text-stone-600">
              Sign in, drop your CV, check one screen — and you&apos;re in. It takes about two
              minutes.
            </p>
            <ul className="mt-8 space-y-4">
              {BENEFITS.map((b) => (
                <li key={b.title} className="flex gap-3">
                  <span
                    aria-hidden="true"
                    className="mt-1 inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-700"
                  >
                    ✓
                  </span>
                  <div>
                    <p className="font-medium text-stone-900">{b.title}</p>
                    <p className="text-sm text-stone-600">{b.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <Card className="space-y-4 p-6">
            <h2 className="font-semibold text-stone-900">Get started</h2>
            <GoogleButton next="/app/network/" />
            <p className="text-xs text-stone-500">
              Already a member? The same button takes you to your profile.{" "}
              <a className="underline underline-offset-4" href={signInPageUrl("/app/network/")}>
                Open the sign-in page
              </a>
            </p>
          </Card>
        </div>
      </section>
    );
  }

  return (
    <NetworkShell variant="entry">
      {content}
      <p className="pb-8 text-center text-sm text-stone-500">
        <a data-testid="link-directory" className="underline underline-offset-4" href="/trainers">
          Browse the trainer directory
        </a>
      </p>
    </NetworkShell>
  );
}
