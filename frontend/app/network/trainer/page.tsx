"use client";

/**
 * Public trainer page. Served at `/trainers/{slug}` (SEO-injected export of this
 * page, outside basePath); the key comes from `?slug=` else the pathname. When
 * reached at `/app/network/trainer/?slug=…` it replaces itself with `/trainers/{slug}`.
 */

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { getTrainer, safeHref, type PublicTrainerDetail } from "@/lib/directory";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Markdown } from "@/components/ui/Markdown";
import { Skeleton } from "@/components/ui/Skeleton";
import { DirectoryShell } from "@/components/directory/DirectoryShell";
import { TrainerAvatar, VerifiedBadge } from "@/components/directory/TrainerCard";

type State =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "error" }
  | { kind: "ready"; t: PublicTrainerDetail };

const PATH_RE = /^\/trainers\/([^/]+)\/?$/;

export default function TrainerPage() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const fromQuery = new URLSearchParams(window.location.search).get("slug");
    const m = PATH_RE.exec(window.location.pathname);
    const slug = (fromQuery || (m ? decodeURIComponent(m[1]) : "")).toLowerCase();
    if (!slug) {
      setState({ kind: "missing" });
      return;
    }
    let live = true;
    setState({ kind: "loading" });
    getTrainer(slug)
      .then((t) => {
        if (!live) return;
        setState({ kind: "ready", t });
        document.title = `${t.display_name} — Workshop0`;
        if (!m) window.location.replace(`/trainers/${encodeURIComponent(t.slug)}`);
      })
      .catch((e) => {
        if (!live) return;
        setState(e instanceof ApiError && e.status === 404 ? { kind: "missing" } : { kind: "error" });
      });
    return () => {
      live = false;
    };
  }, [attempt]);

  let body: React.ReactNode;
  if (state.kind === "loading") {
    body = (
      <div aria-busy="true" aria-label="Loading trainer" className="space-y-4">
        <Skeleton className="h-16 w-2/3" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  } else if (state.kind === "missing") {
    body = (
      <div data-testid="trainer-missing" className="space-y-3 text-center">
        <h1 className="text-2xl font-semibold text-stone-900">Trainer not available</h1>
        <p className="text-stone-600">This trainer profile isn&apos;t available.</p>
        <a href="/trainers" className="underline underline-offset-4">Browse the directory</a>
      </div>
    );
  } else if (state.kind === "error") {
    body = (
      <div role="alert" data-testid="trainer-error" className="space-y-3">
        <p className="font-medium text-stone-800">Something went wrong while loading this profile.</p>
        <Button variant="secondary" onClick={() => setAttempt((n) => n + 1)}>Try again</Button>
      </div>
    );
  } else {
    const t = state.t;
    const links: [string, string][] = [];
    for (const [label, url] of [
      ["LinkedIn", t.links.linkedin],
      ["GitHub", t.links.github],
      ["Website", t.links.website],
    ] as [string, string | null][]) {
      const href = safeHref(url);
      if (href) links.push([label, href]);
    }
    const where = [t.city, t.remote_ok ? "Remote OK" : null].filter(Boolean).join(" · ");
    body = (
      <article data-testid="trainer-page" className="space-y-6">
        <header className="flex items-center gap-4">
          <TrainerAvatar name={t.display_name} url={t.avatar_url} size="size-20" />
          <div className="min-w-0 space-y-1">
            <h1 className="text-3xl font-semibold tracking-tight text-stone-900">{t.display_name}</h1>
            {t.headline && <p className="text-lg text-stone-700">{t.headline}</p>}
            <div className="flex flex-wrap items-center gap-2 text-sm text-stone-500">
              {t.verified && <VerifiedBadge />}
              {where && <span>{where}</span>}
            </div>
          </div>
        </header>
        {t.topics.length > 0 && (
          <ul className="flex flex-wrap gap-2">
            {t.topics.map((x) => (
              <li key={x.slug}>
                <Badge tone="brand">{x.name} · {x.level}</Badge>
              </li>
            ))}
          </ul>
        )}
        {t.bio_md && (
          <section>
            <h2 className="mb-2 font-semibold text-stone-900">About</h2>
            <Markdown>{t.bio_md}</Markdown>
          </section>
        )}
        {t.past_work.length > 0 && (
          <section>
            <h2 className="mb-2 font-semibold text-stone-900">Past work</h2>
            <ul className="space-y-2">
              {t.past_work.map((w, i) => (
                <li key={i} className="text-sm text-stone-700">
                  <span className="font-medium">{w.title}</span>
                  <span className="text-stone-500">
                    {" "}— {w.kind}
                    {w.org ? `, ${w.org}` : ""}
                    {w.year ? ` (${w.year})` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
        {links.length > 0 && (
          <nav aria-label="Links" className="flex flex-wrap gap-4 text-sm">
            {links.map(([label, href]) => (
              <a key={label} href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-4">
                {label}
              </a>
            ))}
          </nav>
        )}
      </article>
    );
  }

  return (
    <DirectoryShell>
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">{body}</div>
    </DirectoryShell>
  );
}
