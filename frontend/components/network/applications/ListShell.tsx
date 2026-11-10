"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { NetworkShell } from "@/components/network/NetworkShell";
import { signInPageUrl, useCurrentUser, type CurrentUser } from "@/lib/networkAuth";

/** Gate + chrome shared by My applications and Matched for you. */
export function ListShell({
  title,
  intro,
  next,
  children,
}: {
  title: string;
  intro: string;
  next: string;
  children: (user: CurrentUser) => React.ReactNode;
}) {
  const router = useRouter();
  const { user, loading, error, refresh } = useCurrentUser();

  useEffect(() => {
    document.title = `${title} — Workshop0`;
  }, [title]);
  useEffect(() => {
    if (user && !user.has_profile) router.replace("/network/join/");
  }, [user, router]);

  let body: React.ReactNode;
  if (loading || (user && !user.has_profile)) {
    body = (
      <div aria-busy="true" aria-label="Loading" className="space-y-3">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  } else if (error) {
    body = (
      <Card className="space-y-3 p-5" role="alert">
        <p className="text-sm text-red-700">{error}</p>
        <button className="text-sm font-medium text-brand-700 underline" onClick={() => void refresh()}>
          Try again
        </button>
      </Card>
    );
  } else if (!user) {
    body = (
      <Card className="space-y-3 p-6 text-center" data-testid="signed-out">
        <p className="text-stone-700">Sign in to see this page.</p>
        <a
          href={signInPageUrl(next)}
          className="inline-flex rounded-lg bg-brand-600 px-4 py-2 font-medium text-white hover:bg-brand-700"
        >
          Sign in
        </a>
      </Card>
    );
  } else {
    body = children(user);
  }

  return (
    <NetworkShell>
      <div className="mx-auto max-w-3xl space-y-5 px-4 py-8 sm:px-6">
        <div>
          <a href="/app/network/me/" className="text-sm text-stone-500 hover:text-stone-800">
            ← My profile
          </a>
          <h1 className="mt-1 text-2xl font-semibold text-stone-900">{title}</h1>
          <p className="mt-1 text-sm text-stone-600">{intro}</p>
        </div>
        {body}
      </div>
    </NetworkShell>
  );
}
