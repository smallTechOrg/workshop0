/**
 * Public marketing landing page — spec/capabilities.md C5.
 *
 * Served at `/` (FastAPI `FileResponse` over `frontend/out/index.html`) and, as
 * a harmless alias, at `/app/`. It is a STATIC server component: no router
 * hooks, no data fetching. The one dynamic bit — "Your workshops" — is a small
 * `"use client"` island. All outbound links are plain `<a href>`, never
 * `next/link`, because this HTML is also served from `/`.
 *
 * There is deliberately NO link to the admin console anywhere on this page.
 */

import type { Metadata } from "next";
import { YourWorkshops } from "@/components/landing/YourWorkshops";

export const metadata: Metadata = {
  title: "Workshop0 — run a hands-on workshop without losing the room",
  description:
    "Free, self-hosted workshop tracker. Compose markdown milestones, share one join link, and watch 300+ participants move in real time. No signup, no accounts.",
};

const CREATE_HREF = "/app/create/";

// --------------------------------------------------------------------------
// Content (data-driven so the markup stays readable)
// --------------------------------------------------------------------------

const FEATURES: {
  icon: string;
  title: string;
  body: string;
}[] = [
  {
    icon: "📊",
    title: "A live dashboard across 300+ participants",
    body: "Every participant, their progress and their current milestone, refreshed every couple of seconds. Median progress, the completion distribution and per-milestone counts tell you whether to slow down or push on.",
  },
  {
    icon: "📝",
    title: "Content-rich markdown & code milestones",
    body: "Each milestone carries real instructions — headings, lists, links, tables and syntax-highlighted fenced code blocks. Write it once in the composer; the room reads it in their own browser at their own pace.",
  },
  {
    icon: "🚪",
    title: "Name-only joining, nothing to install",
    body: "Participants open one link and type their first name. No account, no download, no app. A cookie auto-resumes them if they refresh or close the tab, and everyone gets a personal link that carries their progress to another device.",
  },
  {
    icon: "🆘",
    title: "A real-time help desk",
    body: "A stuck participant raises a hand from the milestone they are on. It lands in your queue with their name and that milestone's context, you answer in markdown in-page, and the answer appears on their screen — no hands up, no shouting across the room.",
  },
  {
    icon: "📣",
    title: "Broadcast, pause and advance — room controls",
    body: "Pin an announcement to every screen, pause the room while you demo at the front, or advance everyone (or a chosen few) past a milestone that broke. Every one of those actions is undoable for 30 seconds.",
  },
  {
    icon: "🚨",
    title: "Proactive stuck & bottleneck alerts",
    body: "Workshop0 watches the shape of the room for you: who has not moved for too long, which milestone is quietly swallowing everyone, and whether your pace is on track against the plan.",
  },
  {
    icon: "🧾",
    title: "A full audit trail",
    body: "Every facilitator action — broadcasts, advances, pauses, edits, help answers — is recorded with who, what and when, and browsable in a tab on the dashboard. Nothing about the session is a mystery afterwards.",
  },
  {
    icon: "⬇️",
    title: "CSV export of everything",
    body: "One click gives you every participant, their join answers, their completion times and their milestone-by-milestone progress — ready for your follow-up mail-out, your grading sheet or your retro.",
  },
];

const STEPS: { title: string; body: string }[] = [
  {
    title: "Compose your milestones",
    body: "Name the workshop, write each step in markdown with the exact commands and code, and set an optional time budget per step.",
  },
  {
    title: "Share one join link",
    body: "Put the link (or its QR code) on the projector. That single link is everything the room needs.",
  },
  {
    title: "The room joins by name",
    body: "Participants type a first name and are straight into the first milestone. No accounts to create, no seats to assign.",
  },
  {
    title: "Watch the dashboard move",
    body: "Tick counts climb live. You can see instantly who has raced ahead, who is stuck, and where the whole room has bunched up.",
  },
  {
    title: "Answer help without breaking the flow",
    body: "Questions arrive with their milestone context. Answer in-page, broadcast the fix if three people hit it, or advance everyone past a bad step.",
  },
  {
    title: "Export the results",
    body: "When it ends, download the CSV. The workshop stays browsable as a read-only archive at the same link.",
  },
];

const FAQS: { q: string; a: React.ReactNode }[] = [
  {
    q: "Do I need an account?",
    a: (
      <>
        No. There is no signup, no password and no login anywhere in
        Workshop0. When you create a workshop you are given a private facilitator
        link — <strong>that link is the credential</strong>. Anyone holding it can run
        that workshop; anyone without it cannot see it.
      </>
    ),
  },
  {
    q: "What happens if I lose my dashboard link?",
    a: (
      <>
        You lose your way back in. There is no account to recover and no password
        reset, so <strong>save the dashboard link the moment it is shown to you</strong> —
        bookmark it, paste it into your notes, mail it to yourself. The reveal screen
        gives you a copy button and says the same thing.
      </>
    ),
  },
  {
    q: "Then what is the “Your workshops” list?",
    a: (
      <>
        A convenience, not an account. Your browser remembers the workshops you made
        here so you can jump back in from this page. Clear your browser data, switch
        browsers or use a private window and the list is gone — the workshop itself is
        untouched and still reachable at its link.
      </>
    ),
  },
  {
    q: "What do participants need?",
    a: (
      <>
        A browser and the join link. Nothing to install, no account, no extension.
        It works on a laptop or a phone, and their progress survives a refresh, a
        closed tab or a move to another device via their personal link.
      </>
    ),
  },
  {
    q: "Is it really free? Where does my data live?",
    a: (
      <>
        Yes — Workshop0 is free and open, and it is self-hosted: the workshop
        data lives in this instance's own database, on the machine serving this page.
        No third party gets your participants' names.
      </>
    ),
  },
  {
    q: "Why do you ask for my email at the end?",
    a: (
      <>
        Purely so the person running this instance can contact you about your
        workshop if they have to, and as a light deterrent against abuse.{" "}
        <strong>No mail is ever sent to you</strong> — not a confirmation, not a
        newsletter — and it is never shared. Your dashboard link is shown on screen,
        not mailed.
      </>
    ),
  },
  {
    q: "How many people can join one workshop?",
    a: (
      <>
        It is built and tested for rooms of 300+ concurrent participants on modest
        hardware. A typical lab of 20–60 will not make it break a sweat.
      </>
    ),
  },
];

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:text-sm focus:shadow"
      >
        Skip to content
      </a>

      {/* ------------------------------------------------------------ nav */}
      <header className="border-b border-stone-200/80 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3.5 sm:px-6">
          <span className="flex items-center gap-2 font-semibold tracking-tight">
            <span aria-hidden="true" className="text-xl">
              ⛵
            </span>
            Workshop0
            <a
              href="https://smalltech.in"
              rel="noopener noreferrer"
              className="ml-1 flex items-center gap-1.5 rounded-full border border-stone-300 py-0.5 pl-1.5 pr-2.5 text-xs font-medium text-stone-500 transition-colors hover:border-stone-400 hover:text-stone-800"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/app/smalltech-logo.png"
                alt=""
                width={121}
                height={128}
                className="h-5 w-auto"
              />
              by smallTech
            </a>
          </span>
          <nav aria-label="Page sections" className="hidden items-center gap-6 text-sm text-stone-600 sm:flex">
            <a href="#features" className="hover:text-stone-900">
              Features
            </a>
            <a href="#how-it-works" className="hover:text-stone-900">
              How it works
            </a>
            <a href="#faq" className="hover:text-stone-900">
              FAQ
            </a>
          </nav>
        </div>
      </header>

      <main id="main">
        {/* --------------------------------------------------------- hero */}
        <section
          data-testid="landing-hero"
          aria-labelledby="hero-heading"
          className="relative overflow-hidden border-b border-stone-200 bg-gradient-to-b from-brand-50 via-white to-stone-50"
        >
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-24 -right-24 size-96 rounded-full bg-brand-200/40 blur-3xl"
          />
          <div className="relative mx-auto grid max-w-6xl gap-12 px-4 py-16 sm:px-6 sm:py-24 lg:grid-cols-2 lg:items-center">
            <div>
              <p className="inline-flex items-center gap-2 rounded-full border border-brand-200 bg-white/80 px-3 py-1 text-xs font-medium text-brand-700">
                <span aria-hidden="true">●</span>
                Free · self-hosted · no signup
              </p>
              <h1
                id="hero-heading"
                className="mt-5 text-4xl leading-[1.1] font-semibold tracking-tight text-stone-900 sm:text-5xl lg:text-6xl"
              >
                Run a hands-on workshop{" "}
                <span className="text-brand-600">without losing the room.</span>
              </h1>
              <p className="mt-5 max-w-xl text-lg leading-relaxed text-stone-600">
                Workshop0 turns your agenda into live milestones your
                participants tick off in their browser — so you can see, in real time,
                exactly who is flying, who is stuck and which step is quietly
                swallowing everybody.
              </p>

              <div className="mt-8 flex flex-wrap items-center gap-4">
                <a
                  data-testid="landing-cta"
                  href={CREATE_HREF}
                  className="inline-flex items-center gap-2 rounded-xl bg-brand-600 px-6 py-3.5 text-base font-semibold text-white shadow-lg shadow-brand-600/20 transition-colors hover:bg-brand-700 active:bg-brand-800"
                >
                  Create your workshop — free, no signup
                  <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="size-5">
                    <path fillRule="evenodd" d="M3 10a.75.75 0 0 1 .75-.75h10.638L10.23 5.29a.75.75 0 1 1 1.04-1.08l5.5 5.25a.75.75 0 0 1 0 1.08l-5.5 5.25a.75.75 0 1 1-1.04-1.08l4.158-3.96H3.75A.75.75 0 0 1 3 10Z" clipRule="evenodd" />
                  </svg>
                </a>
                <a
                  href="#how-it-works"
                  className="text-sm font-medium text-stone-600 underline underline-offset-4 hover:text-stone-900"
                >
                  See how it works
                </a>
              </div>

              <p className="mt-4 text-sm text-stone-500">
                Takes about two minutes. Nothing to install — for you or for the room.
              </p>
            </div>

            {/* Indicative dashboard vignette (static illustration, not live data) */}
            <div aria-hidden="true" className="lg:justify-self-end">
              <div className="w-full max-w-md rounded-2xl border border-stone-200 bg-white p-5 shadow-xl shadow-stone-900/5">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-stone-800">LangGraph Lab</p>
                  <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                    live
                  </span>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-3 text-center">
                  {[
                    ["143", "joined"],
                    ["121", "active"],
                    ["40%", "median"],
                  ].map(([n, l]) => (
                    <div key={l} className="rounded-lg bg-stone-50 py-2.5">
                      <p className="text-lg font-semibold text-stone-900">{n}</p>
                      <p className="text-xs text-stone-500">{l}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-5 space-y-3">
                  {[
                    ["Set up your environment", 96],
                    ["Build the graph", 71],
                    ["Add a tool node", 34],
                    ["Ship it", 9],
                  ].map(([label, pct]) => (
                    <div key={label as string}>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="text-stone-600">{label}</span>
                        <span className="tabular-nums text-stone-400">{pct}%</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-stone-100">
                        <div
                          className="h-full rounded-full bg-brand-500"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  ⚠ 4 participants stuck on “Add a tool node” for 12+ min
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ----------------------------------------------------- features */}
        <section
          id="features"
          data-testid="landing-features"
          aria-labelledby="features-heading"
          className="mx-auto max-w-6xl scroll-mt-16 px-4 py-20 sm:px-6"
        >
          <p className="text-sm font-semibold tracking-wide text-brand-600 uppercase">
            What you get
          </p>
          <h2
            id="features-heading"
            className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight text-stone-900 sm:text-4xl"
          >
            Everything you need to run the room, and nothing you don't.
          </h2>
          <p className="mt-3 max-w-2xl text-stone-600">
            One tool, built for the awkward middle of a workshop — when half the room
            is ahead, a quarter is stuck, and you cannot tell which is which.
          </p>

          <ul className="mt-12 grid gap-x-10 gap-y-10 sm:grid-cols-2">
            {FEATURES.map((f) => (
              <li key={f.title} className="flex gap-4">
                <span
                  aria-hidden="true"
                  className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-brand-100 bg-brand-50 text-xl"
                >
                  {f.icon}
                </span>
                <div>
                  <h3 className="text-base font-semibold text-stone-900">{f.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-stone-600">
                    {f.body}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        {/* -------------------------------------------------- how it works */}
        <section
          id="how-it-works"
          data-testid="landing-how-it-works"
          aria-labelledby="how-heading"
          className="scroll-mt-16 border-y border-stone-200 bg-white"
        >
          <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
            <p className="text-sm font-semibold tracking-wide text-brand-600 uppercase">
              How it works
            </p>
            <h2
              id="how-heading"
              className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight text-stone-900 sm:text-4xl"
            >
              The facilitator → participant loop, end to end.
            </h2>

            <ol className="mt-12 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
              {STEPS.map((s, i) => (
                <li key={s.title} className="relative rounded-xl border border-stone-200 bg-stone-50/70 p-6">
                  <span className="flex size-9 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white">
                    {i + 1}
                  </span>
                  <h3 className="mt-4 text-base font-semibold text-stone-900">
                    {s.title}
                  </h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-stone-600">
                    {s.body}
                  </p>
                </li>
              ))}
            </ol>

            <div className="mt-12 flex flex-wrap items-center gap-4 rounded-xl border border-brand-200 bg-brand-50 px-6 py-5">
              <p className="text-sm text-stone-700">
                That is the whole loop. Your first workshop takes about two minutes to
                compose.
              </p>
              <a
                href={CREATE_HREF}
                className="ml-auto text-sm font-semibold text-brand-700 underline underline-offset-4 hover:text-brand-800"
              >
                Start composing →
              </a>
            </div>
          </div>
        </section>

        {/* ------------------------------------------------ your workshops */}
        <YourWorkshops />

        {/* ---------------------------------------------------------- FAQ */}
        <section
          id="faq"
          data-testid="landing-faq"
          aria-labelledby="faq-heading"
          className="mx-auto max-w-3xl scroll-mt-16 px-4 py-20 sm:px-6"
        >
          <p className="text-sm font-semibold tracking-wide text-brand-600 uppercase">
            Straight answers
          </p>
          <h2
            id="faq-heading"
            className="mt-2 text-3xl font-semibold tracking-tight text-stone-900 sm:text-4xl"
          >
            Frequently asked questions
          </h2>
          <p className="mt-3 text-stone-600">
            Including the limits — they are real, and better known before you start
            than after.
          </p>

          <dl className="mt-10 divide-y divide-stone-200 border-y border-stone-200">
            {FAQS.map((f) => (
              <div key={f.q} className="py-5">
                <dt className="text-base font-semibold text-stone-900">{f.q}</dt>
                <dd className="mt-2 text-sm leading-relaxed text-stone-600">{f.a}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-12 rounded-2xl border border-stone-200 bg-white p-8 text-center shadow-sm">
            <h2 className="text-2xl font-semibold tracking-tight text-stone-900">
              Ready when you are.
            </h2>
            <p className="mx-auto mt-2 max-w-md text-sm text-stone-600">
              Compose your milestones, share the link, watch the room move.
            </p>
            <a
              href={CREATE_HREF}
              className="mt-6 inline-flex items-center gap-2 rounded-xl bg-brand-600 px-6 py-3.5 text-base font-semibold text-white shadow-lg shadow-brand-600/20 transition-colors hover:bg-brand-700"
            >
              Create your workshop — free, no signup
            </a>
          </div>
        </section>
      </main>

      {/* ------------------------------------------------------- footer */}
      <footer className="border-t border-stone-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-8 text-sm text-stone-500 sm:px-6">
          <p>
            <span aria-hidden="true">⛵</span> Workshop0 — free and
            self-hosted, run by whoever operates this instance.
          </p>
          <p className="flex flex-wrap items-center gap-4">
            <a
              href="/app/opportunities/"
              className="underline underline-offset-4 hover:text-stone-800"
            >
              Opportunities for trainers
            </a>
            <a
              href="https://smalltech.in"
              rel="noopener noreferrer"
              className="group flex items-center gap-2 hover:text-stone-900"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/app/smalltech-logo.png"
                alt="smallTech"
                width={121}
                height={128}
                className="h-6 w-auto"
              />
              <span>
                Built by{" "}
                <span className="font-medium text-stone-700 underline underline-offset-4 group-hover:text-stone-900">
                  smallTech
                </span>
              </span>
            </a>
            <a
              href="https://github.com/smallTechOrg/workshop0"
              rel="noopener noreferrer"
              className="group flex items-center gap-2 hover:text-stone-800"
            >
              <svg
                viewBox="0 0 16 16"
                aria-hidden="true"
                className="h-5 w-5 fill-current"
              >
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
              </svg>
              <span className="underline underline-offset-4">Source on GitHub</span>
            </a>
          </p>
        </div>
      </footer>
    </div>
  );
}
