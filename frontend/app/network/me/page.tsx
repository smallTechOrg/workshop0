"use client";

/**
 * My profile — `/app/network/me/` (capabilities.md C12).
 *
 * Completeness meter + top-3 nudges, the Verified badge when granted, every
 * field editable through the shared ProfileForm (`PATCH /api/me/profile`), the
 * owner's own CV (download + replace), the danger zone, and the labelled stubs
 * for My applications / Matched for you (Phase 12) and Saved searches / Public
 * directory profile (Phase 13).
 *
 *   signed out   → sign-in card (back here)
 *   no profile   → onboarding `/app/network/join/`
 *   deleted      → confirmation screen
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useCurrentUser } from "@/lib/networkAuth";
import {
  OWN_CV_URL,
  RATE_UNIT_LABELS,
  getProfile,
  normalizeProfileInput,
  patchProfile,
  type OwnProfile,
  type OwnProfilePayload,
  type ProfileInput,
} from "@/lib/network";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { StubCard } from "@/components/ui/StubBadge";
import { GoogleButton } from "@/components/network/auth/GoogleButton";
import { NetworkShell } from "@/components/network/profile/NetworkShell";
import { CompletenessMeter } from "@/components/network/profile/CompletenessMeter";
import { CvIntake } from "@/components/network/profile/CvIntake";
import { DeleteAccount } from "@/components/network/profile/DeleteAccount";
import { ProfileForm } from "@/components/network/profile/ProfileForm";

const ME_PATH = "/app/network/me/";

function PageSkeleton({ label }: { label: string }) {
  return (
    <div aria-busy="true" aria-label={label} className="space-y-4">
      <Skeleton className="h-28 w-full" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-72 w-full" />
    </div>
  );
}

function VerifiedBadge() {
  return (
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
  );
}

function ProfileHeader({ profile }: { profile: OwnProfile }) {
  const where = [profile.city, profile.remote_ok ? "Open to remote" : null].filter(Boolean).join(" · ");
  const rate =
    profile.rate_min !== null && profile.rate_max !== null && profile.rate_currency
      ? `${profile.rate_currency} ${profile.rate_min.toLocaleString()}–${profile.rate_max.toLocaleString()}${
          profile.rate_unit ? ` ${RATE_UNIT_LABELS[profile.rate_unit]}` : ""
        }`
      : null;
  return (
    <Card className="p-5 sm:p-6" data-testid="profile-header">
      <div className="flex flex-wrap items-start gap-4">
        {profile.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={profile.avatar_url}
            alt=""
            referrerPolicy="no-referrer"
            className="size-14 rounded-full border border-stone-200 object-cover"
          />
        ) : (
          <span
            aria-hidden="true"
            className="inline-flex size-14 items-center justify-center rounded-full bg-brand-100 text-lg font-semibold text-brand-700"
          >
            {(profile.display_name || profile.email || "?").trim().charAt(0).toUpperCase()}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-stone-700">{profile.display_name || profile.email}</p>
            {profile.verified && <VerifiedBadge />}
          </div>
          <h1
            data-testid="profile-headline-text"
            className="mt-1 text-xl font-semibold tracking-tight text-balance text-stone-900 sm:text-2xl"
          >
            {profile.headline}
          </h1>
          <p className="mt-1 text-sm text-stone-500">
            {[where, profile.email].filter(Boolean).join(" · ")}
          </p>
          {profile.topics.length > 0 && (
            <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Your topics">
              {profile.topics.map((t) => (
                <li key={t.slug}>
                  <Badge tone="brand">{t.name || t.slug}</Badge>
                </li>
              ))}
            </ul>
          )}
          {(rate || profile.pro_bono) && (
            <p className="mt-3 text-sm text-stone-600">
              {rate}
              {rate && profile.pro_bono ? " · " : ""}
              {profile.pro_bono ? "Open to pro-bono" : ""}{" "}
              <span className="text-xs text-stone-400">(visible to smallTech only)</span>
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}

function CvCard({ profile, onReplaced }: { profile: OwnProfile; onReplaced: () => Promise<void> }) {
  const [replacing, setReplacing] = useState(false);
  const [done, setDone] = useState(false);
  const cv = profile.cv;
  const name =
    cv?.original_filename || (cv?.source === "text" ? "Pasted CV text" : cv ? `cv.${cv.source}` : null);

  return (
    <section aria-labelledby="cv-card-title" data-testid="cv-card">
      <Card className="space-y-4 p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id="cv-card-title" className="font-semibold text-stone-900">
              Your CV
            </h2>
            {cv ? (
              <p className="mt-0.5 text-sm text-stone-600" data-testid="cv-on-file">
                <span className="font-medium text-stone-800">{name}</span>
                {cv.created_at ? ` · added ${formatDate(cv.created_at)}` : ""}
              </p>
            ) : (
              <p className="mt-0.5 text-sm text-stone-500" data-testid="cv-none">
                No CV on file yet — adding one completes your profile.
              </p>
            )}
            <p className="mt-1 text-xs text-stone-500">Only you and smallTech can see it.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {cv && (
              <a
                href={OWN_CV_URL}
                download
                data-testid="cv-download"
                className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 text-sm font-medium text-stone-800 shadow-sm hover:bg-stone-50"
              >
                Download my CV
              </a>
            )}
            <Button
              size="sm"
              variant={replacing ? "ghost" : "secondary"}
              data-testid="cv-replace-toggle"
              onClick={() => {
                setReplacing((r) => !r);
                setDone(false);
              }}
            >
              {replacing ? "Cancel" : cv ? "Replace CV" : "Add a CV"}
            </Button>
          </div>
        </div>
        {done && (
          <p role="status" className="text-sm text-emerald-700" data-testid="cv-replaced">
            Your CV is updated. Your profile fields are unchanged — edit them below if anything is
            new.
          </p>
        )}
        {replacing && (
          <CvIntake
            waitForDraft={false}
            replaceLabel={cv ? "Replace my CV" : "Add my CV"}
            onUploaded={() => {
              setReplacing(false);
              setDone(true);
              void onReplaced();
            }}
          />
        )}
      </Card>
    </section>
  );
}

function ComingSoon() {
  return (
    <section aria-labelledby="coming-soon-title" data-testid="profile-stubs">
      <h2 id="coming-soon-title" className="mb-3 font-semibold text-stone-900">
        More from the network
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <a
          href="/app/network/applications/"
          data-testid="link-applications"
          className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm hover:border-brand-300"
        >
          <h3 className="text-sm font-semibold text-stone-900">My applications</h3>
          <p className="mt-1.5 text-sm text-stone-600">
            Follow the status of every application and withdraw if plans change.
          </p>
        </a>
        <a
          href="/app/network/matches/"
          data-testid="link-matches"
          className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm hover:border-brand-300"
        >
          <h3 className="text-sm font-semibold text-stone-900">Matched for you</h3>
          <p className="mt-1.5 text-sm text-stone-600">
            Opportunities that fit your topics, level and availability.
          </p>
        </a>
        <StubCard
          title="Saved searches & alerts"
          description="Save a board search and get an email when a new listing matches."
        />
        <StubCard
          title="Public directory profile"
          description="Choose whether partners can find you in a public trainer directory."
        />
      </div>
    </section>
  );
}

function DeletedScreen() {
  return (
    <Card className="mx-auto max-w-md space-y-3 p-6 text-center" data-testid="account-deleted">
      <h1 className="text-xl font-semibold text-stone-900">Your account has been deleted</h1>
      <p className="text-sm text-stone-600">
        Your profile, CV and sign-in are gone, and you&apos;ve been signed out. You&apos;re welcome
        back any time.
      </p>
      <div className="flex flex-wrap justify-center gap-3 pt-2">
        <a href="/app/opportunities/" className="text-sm font-medium text-brand-700 underline underline-offset-4">
          Browse opportunities
        </a>
        <a href="/" className="text-sm font-medium text-stone-600 underline underline-offset-4">
          Home
        </a>
      </div>
    </Card>
  );
}

type Load =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; payload: OwnProfilePayload };

export default function MyProfilePage() {
  const router = useRouter();
  const { user, loading, error, refresh } = useCurrentUser();
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [deleted, setDeleted] = useState(false);

  useEffect(() => {
    document.title = "My profile — Workshop0";
  }, []);

  const fetchProfile = useCallback(async () => {
    try {
      const payload = await getProfile();
      setLoad({ kind: "ready", payload });
    } catch (err) {
      if (err instanceof ApiError && err.code === "not_found") {
        router.replace("/network/join/");
        return;
      }
      if (err instanceof ApiError && err.code === "not_signed_in") {
        await refresh();
        return;
      }
      setLoad({
        kind: "error",
        message:
          err instanceof ApiError && err.code === "network_error"
            ? "We couldn't reach the server — check your connection."
            : "We couldn't load your profile.",
      });
    }
  }, [router, refresh]);

  const userId = user?.id;
  useEffect(() => {
    if (!userId || deleted) return;
    setLoad({ kind: "loading" });
    void fetchProfile();
  }, [userId, deleted, fetchProfile]);

  const payload = load.kind === "ready" ? load.payload : null;
  const initial = useMemo(
    () => (payload ? normalizeProfileInput(payload.profile as unknown as Partial<ProfileInput>) : null),
    // The form owns its state after mount; only a different profile re-seeds it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [payload?.profile.id],
  );
  const topicNames = useMemo(
    () => Object.fromEntries((payload?.profile.topics ?? []).map((t) => [t.slug, t.name])),
    [payload?.profile.topics],
  );

  async function save(input: ProfileInput) {
    const next = await patchProfile(input);
    setLoad({ kind: "ready", payload: next });
  }

  let content: React.ReactNode;
  if (deleted) {
    content = <DeletedScreen />;
  } else if (loading && !user) {
    content = <PageSkeleton label="Checking sign-in" />;
  } else if (error && !user) {
    content = (
      <Card role="alert" data-testid="me-load-error" className="mx-auto max-w-md space-y-3 p-6">
        <p className="font-medium text-stone-800">{error}</p>
        <Button variant="secondary" onClick={() => void refresh()}>
          Try again
        </Button>
      </Card>
    );
  } else if (!user) {
    content = (
      <Card className="mx-auto max-w-md space-y-4 p-6" data-testid="me-signed-out">
        <h1 className="text-xl font-semibold text-stone-900">Sign in to see your profile</h1>
        <GoogleButton next={ME_PATH} />
      </Card>
    );
  } else if (load.kind === "loading" || !payload || !initial) {
    content =
      load.kind === "error" ? (
        <Card role="alert" data-testid="me-load-error" className="mx-auto max-w-md space-y-3 p-6">
          <p className="font-medium text-stone-800">{load.message}</p>
          <Button
            variant="secondary"
            onClick={() => {
              setLoad({ kind: "loading" });
              void fetchProfile();
            }}
          >
            Try again
          </Button>
        </Card>
      ) : (
        <PageSkeleton label="Loading your profile" />
      );
  } else {
    const { profile, completeness } = payload;
    content = (
      <div className="space-y-6" data-testid="my-profile">
        <ProfileHeader profile={profile} />
        <CompletenessMeter completeness={completeness} />
        <CvCard profile={profile} onReplaced={fetchProfile} />
        <div>
          <h2 className="mb-3 text-lg font-semibold text-stone-900">Edit your profile</h2>
          <ProfileForm
            key={profile.id}
            mode="edit"
            initial={initial}
            autofilled={profile.autofilled_fields}
            topicNames={topicNames}
            submitLabel="Save changes"
            onSubmit={(input) => save(input)}
          />
        </div>
        <ComingSoon />
        <DeleteAccount
          email={profile.email}
          onDeleted={() => {
            setDeleted(true);
            void refresh();
          }}
        />
      </div>
    );
  }

  return (
    <NetworkShell>
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-12">{content}</div>
    </NetworkShell>
  );
}
