"use client";

/** Public trainer directory — `/app/network/directory/` (also reached via `/trainers`). */

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { listTrainers, type PublicTrainer } from "@/lib/directory";
import { listPublicTopics, type PublicTopic } from "@/lib/board";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Pagination } from "@/components/board/Pagination";
import { DirectoryShell } from "@/components/directory/DirectoryShell";
import { TrainerCard } from "@/components/directory/TrainerCard";

type State =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "ready"; items: PublicTrainer[]; page: number; pageSize: number; total: number };

function DirectoryInner() {
  const router = useRouter();
  const params = useSearchParams();
  const topic = params.get("topic") ?? "";
  const pageNum = Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [topics, setTopics] = useState<PublicTopic[]>([]);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    document.title = "Trainers — Workshop0";
  }, []);

  useEffect(() => {
    let live = true;
    listPublicTopics()
      .then((r) => live && setTopics(r.topics))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    let live = true;
    setState({ kind: "loading" });
    listTrainers(topic || undefined, pageNum)
      .then((r) => live && setState({ kind: "ready", items: r.items, page: r.page, pageSize: r.page_size, total: r.total }))
      .catch(() => live && setState({ kind: "error" }));
    return () => {
      live = false;
    };
  }, [topic, pageNum, attempt]);

  const go = useCallback(
    (t: string, p: number) => {
      const q = new URLSearchParams();
      if (t) q.set("topic", t);
      if (p > 1) q.set("page", String(p));
      const qs = q.toString();
      router.push(`/network/directory/${qs ? `?${qs}` : ""}`);
    },
    [router],
  );

  let body: React.ReactNode;
  if (state.kind === "loading") {
    body = (
      <div aria-busy="true" aria-label="Loading trainers" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-36 w-full" />
        ))}
      </div>
    );
  } else if (state.kind === "error") {
    body = (
      <div role="alert" data-testid="directory-error" className="space-y-3 rounded-xl border border-red-200 bg-red-50 p-5">
        <p className="font-medium text-stone-800">Something went wrong while loading trainers.</p>
        <Button variant="secondary" onClick={() => setAttempt((n) => n + 1)}>Try again</Button>
      </div>
    );
  } else if (state.items.length === 0) {
    body = (
      <EmptyState
        icon="🧑‍🏫"
        title={topic ? "No trainers listed for this topic yet" : "No trainers are listed yet"}
        hint="Trainers appear here once they switch on their public profile."
        action={topic ? <Button variant="secondary" onClick={() => go("", 1)}>Clear filter</Button> : undefined}
      />
    );
  } else {
    const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
    body = (
      <>
        <div data-testid="directory-grid" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {state.items.map((t) => (
            <TrainerCard key={t.slug} trainer={t} />
          ))}
        </div>
        <Pagination page={state.page} totalPages={totalPages} onPage={(p) => go(topic, p)} />
      </>
    );
  }

  return (
    <DirectoryShell>
      <section className="border-b border-stone-200 bg-gradient-to-b from-brand-50/70 to-stone-50">
        <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
          <h1 className="text-3xl font-semibold tracking-tight text-stone-900">Trainer directory</h1>
          <p className="mt-2 text-stone-600">Tech trainers from the smallTech network.</p>
          <label className="mt-5 flex max-w-xs flex-col gap-1 text-sm font-medium text-stone-700">
            Topic
            <select
              data-testid="directory-topic-filter"
              value={topic}
              onChange={(e) => go(e.target.value, 1)}
              className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm"
            >
              <option value="">All topics</option>
              {topics.map((t) => (
                <option key={t.slug} value={t.slug}>{t.name}</option>
              ))}
              {topic && !topics.some((t) => t.slug === topic) && <option value={topic}>{topic}</option>}
            </select>
          </label>
        </div>
      </section>
      <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">{body}</div>
    </DirectoryShell>
  );
}

export default function DirectoryPage() {
  return (
    <Suspense fallback={null}>
      <DirectoryInner />
    </Suspense>
  );
}
