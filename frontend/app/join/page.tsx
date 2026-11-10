"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, joinInfo, joinWorkshop, type JoinInfo } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { JoinNetworkCard } from "@/components/participant/JoinNetworkCard";
import { Markdown } from "@/components/ui/Markdown";

function JoinSkeleton() {
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-lg p-8">
        <Skeleton className="mx-auto h-7 w-56" />
        <Skeleton className="mx-auto mt-4 h-4 w-72" />
        <Skeleton className="mt-8 h-10 w-full" />
        <Skeleton className="mt-3 h-10 w-full" />
      </Card>
    </main>
  );
}

function ErrorCard({ title, hint }: { title: string; hint: string }) {
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-lg p-8 text-center">
        <p aria-hidden="true" className="text-3xl">
          🧭
        </p>
        <h1 className="mt-2 text-xl font-semibold text-stone-900">{title}</h1>
        <p className="mt-2 text-stone-500">{hint}</p>
      </Card>
    </main>
  );
}

function JoinInner() {
  const params = useSearchParams();
  const router = useRouter();
  const slug = params.get("s");

  const [info, setInfo] = useState<JoinInfo | null>(null);
  const [loadError, setLoadError] = useState<"not_found" | "network" | null>(null);
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    joinInfo(slug)
      .then((res) => {
        if (!cancelled) setInfo(res);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(
          err instanceof ApiError && err.status === 404 ? "not_found" : "network",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  // Cookie auto-resume: this browser already joined — forward to the tracker.
  useEffect(() => {
    if (!info?.me) return;
    const token = info.me.participant_token;
    const timer = setTimeout(() => {
      router.replace(`/p/?t=${encodeURIComponent(token)}`);
    }, 1400);
    return () => clearTimeout(timer);
  }, [info, router]);

  if (!slug) {
    return (
      <ErrorCard
        title="This workshop link isn't valid"
        hint="The link is missing its workshop code — check with your facilitator for the right one."
      />
    );
  }
  if (loadError === "not_found") {
    return (
      <ErrorCard
        title="This workshop link isn't valid"
        hint="Check with your facilitator — the link may have been mistyped."
      />
    );
  }
  if (loadError === "network") {
    return (
      <ErrorCard
        title="Couldn't reach the workshop"
        hint="Check your connection and reload this page."
      />
    );
  }
  if (!info) return <JoinSkeleton />;

  const { workshop, me } = info;

  if (me) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4">
        <Card className="w-full max-w-lg p-8 text-center">
          <p aria-hidden="true" className="text-3xl">
            👋
          </p>
          <h1 className="mt-2 text-xl font-semibold text-stone-900">
            Welcome back, {me.name}
          </h1>
          <p className="mt-1 text-stone-500">
            Taking you to your tracker for “{workshop.name}”…
          </p>
          <Button
            className="mt-5"
            onClick={() =>
              router.replace(`/p/?t=${encodeURIComponent(me.participant_token)}`)
            }
          >
            Continue
          </Button>
        </Card>
      </main>
    );
  }

  if (workshop.status === "archived") {
    return (
      <ErrorCard
        title="This workshop has ended"
        hint="The session is over and new joins are closed. If you took part, open your personal link to browse the archive."
      />
    );
  }

  const submit = async () => {
    const trimmed = name.trim();
    if (trimmed.length < 1) {
      setNameError("Enter your name so the room knows who you are.");
      return;
    }
    if (trimmed.length > 80) {
      setNameError("That name is too long — keep it under 80 characters.");
      return;
    }
    const fields = info?.workshop.join_form ?? [];
    const errors: Record<string, string> = {};
    for (const f of fields) {
      if (f.required && !(answers[f.key] ?? "").trim()) {
        errors[f.key] = `${f.label} is required.`;
      }
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    setNameError(null);
    setJoinError(null);
    setJoining(true);
    try {
      const res = await joinWorkshop(slug, trimmed, answers);
      router.replace(`/p/?t=${encodeURIComponent(res.participant_token)}`);
    } catch (err) {
      setJoining(false);
      setJoinError(
        err instanceof ApiError
          ? err.message
          : "Couldn't join — check your connection and try again.",
      );
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-8">
      <Card className="w-full max-w-lg p-8">
        <h1 className="text-center text-2xl font-semibold text-stone-900">
          {workshop.name}
        </h1>
        <p className="mt-2 text-center text-sm text-stone-500">
          {workshop.milestone_count}{" "}
          {workshop.milestone_count === 1 ? "milestone" : "milestones"} ·{" "}
          {workshop.participant_count === 0
            ? "be the first to join"
            : `${workshop.participant_count} ${
                workshop.participant_count === 1 ? "person is" : "people are"
              } in`}
        </p>

        {workshop.description_md.trim() !== "" && (
          <div className="mt-5 rounded-lg bg-stone-50 px-4 py-3">
            <Markdown className="text-sm">{workshop.description_md}</Markdown>
          </div>
        )}

        <form
          className="mt-6"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <label
            htmlFor="join-name"
            className="mb-1 block text-sm font-medium text-stone-700"
          >
            Your name
          </label>
          <input
            id="join-name"
            data-testid="join-name-input"
            type="text"
            autoComplete="name"
            maxLength={80}
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (nameError) setNameError(null);
            }}
            placeholder="e.g. Priya"
            className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-stone-900 placeholder:text-stone-400 focus:border-brand-500"
          />
          {nameError && (
            <p role="alert" className="mt-1.5 text-sm text-red-600">
              {nameError}
            </p>
          )}
          {(info?.workshop.join_form ?? []).map((f) => (
            <div key={f.key} className="mt-4" data-testid="join-custom-field">
              <label
                htmlFor={`join-f-${f.key}`}
                className="mb-1 block text-sm font-medium text-stone-700"
              >
                {f.label}
                {f.required ? (
                  <span className="ml-0.5 text-red-500" aria-hidden>*</span>
                ) : (
                  <span className="ml-1.5 font-normal text-stone-400">(optional)</span>
                )}
              </label>
              {f.type === "dropdown" ? (
                <select
                  id={`join-f-${f.key}`}
                  data-testid={`join-field-${f.key}`}
                  value={answers[f.key] ?? ""}
                  onChange={(e) => {
                    setAnswers((a) => ({ ...a, [f.key]: e.target.value }));
                    setFieldErrors((fe) => ({ ...fe, [f.key]: "" }));
                  }}
                  className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-stone-900 focus:border-brand-500"
                >
                  <option value="">Choose…</option>
                  {(f.options ?? []).map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id={`join-f-${f.key}`}
                  data-testid={`join-field-${f.key}`}
                  type="text"
                  maxLength={500}
                  value={answers[f.key] ?? ""}
                  onChange={(e) => {
                    setAnswers((a) => ({ ...a, [f.key]: e.target.value }));
                    setFieldErrors((fe) => ({ ...fe, [f.key]: "" }));
                  }}
                  className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2.5 text-stone-900 placeholder:text-stone-400 focus:border-brand-500"
                />
              )}
              {fieldErrors[f.key] ? (
                <p role="alert" className="mt-1.5 text-sm text-red-600">
                  {fieldErrors[f.key]}
                </p>
              ) : null}
            </div>
          ))}
          {joinError && (
            <p role="alert" className="mt-1.5 text-sm text-red-600">
              {joinError}
            </p>
          )}
          <Button
            type="submit"
            data-testid="join-submit"
            loading={joining}
            className="mt-4 w-full"
          >
            Join workshop
          </Button>
        </form>
        <div className="mt-6">
          <JoinNetworkCard />
        </div>
      </Card>
    </main>
  );
}

export default function JoinPage() {
  return (
    <Suspense fallback={<JoinSkeleton />}>
      <JoinInner />
    </Suspense>
  );
}
