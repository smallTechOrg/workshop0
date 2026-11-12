/**
 * Public marketing landing page — spec/capabilities.md C5 (repositioned for
 * AI trainers, Nov 2026: the Trainer Network leads, the workshop tool is a
 * bonus toolkit further down).
 *
 * Served at `/` (FastAPI `FileResponse` over `frontend/out/index.html`) and, as
 * a harmless alias, at `/app/`. It is a STATIC server component: no router
 * hooks, no data fetching. The one dynamic bit — "Your workshops" — is a small
 * `"use client"` island. All outbound links are plain `<a href>`, never
 * `next/link`, because this HTML is also served from `/`.
 *
 * The page shows no live counts, listings or directory cards: at launch the
 * board may be empty, and joining the network works with zero content.
 *
 * There is deliberately NO link to the admin console anywhere on this page.
 */

import type { Metadata } from "next";
import { YourWorkshops } from "@/components/landing/YourWorkshops";

export const metadata: Metadata = {
  title: "Workshop0 — the Trainer Network for Gen AI & agentic AI trainers",
  description:
    "Join smallTech's Trainer Network: drop your CV, get matched to workshops, engagements and roles in Generative AI, agentic AI and modern tech, and apply in one click. Plus a free toolkit for running hands-on sessions.",
};

/** Sign-in, then onboarding — the same target as the board's "Join our network" (C12). */
const JOIN_HREF = "/app/signin/?next=%2Fapp%2Fnetwork%2Fjoin%2F";
const BOARD_HREF = "/app/opportunities/";
const CREATE_HREF = "/app/create/";

// --------------------------------------------------------------------------
// Content (data-driven so the markup stays readable)
// --------------------------------------------------------------------------

/** Real names from the curated taxonomy (spec/data-model.md §topic). */
const TOPIC_GROUPS: { icon: string; title: string; blurb: string; topics: string[] }[] = [
  {
    icon: "✨",
    title: "Generative AI",
    blurb: "LLM apps, prompting and the models underneath.",
    topics: ["Generative AI & LLMs", "Prompt Engineering", "Deep Learning", "Machine Learning"],
  },
  {
    icon: "🤖",
    title: "Agentic AI",
    blurb: "Agents, tools and the pipelines that ship them.",
    topics: ["Agentic AI (LangChain / LangGraph)", "MLOps", "Data Engineering", "Python"],
  },
  {
    icon: "🛠️",
    title: "Tech",
    blurb: "Cloud, DevOps, web and engineering practice.",
    topics: ["AWS", "Kubernetes", "System Design", "APIs & Microservices"],
  },
];

const OPPORTUNITY_TYPES = [
  "Workshop / training",
  "Longer engagement",
  "Job / contract role",
  "Workshop0 co-facilitator / TA",
];

const NETWORK_STEPS: { title: string; body: string }[] = [
  {
    title: "Sign in with Google",
    body: "One button. No forms to fill before you know whether the network is for you.",
  },
  {
    title: "Drop your CV, review one screen",
    body: "Upload a PDF or DOCX, a LinkedIn PDF, or paste the text. We pre-fill your profile — headline, topics, experience — and you check it on a single page.",
  },
  {
    title: "Get matched to real work",
    body: "smallTech matches workshops, longer engagements and roles from its partner network to the topics you teach and your level — and can invite you to apply.",
  },
  {
    title: "Apply in one click, see where you stand",
    body: "Send an application with an optional note and follow it from Applied to Shortlisted to Selected. No chasing, no guessing.",
  },
  {
    title: "Let the work come to you",
    body: "Save a search and get one email when a matching opportunity opens, plus an optional weekly digest of what you missed.",
  },
];

const TRUST: { icon: string; title: string; body: string }[] = [
  {
    icon: "🔒",
    title: "Your rates stay private",
    body: "Rates are visible to smallTech only — never to other trainers or on any public page.",
  },
  {
    icon: "👁️",
    title: "Public only if you say so",
    body: "A public directory profile is opt-in, and never shows your email, rates or CV.",
  },
  {
    icon: "✅",
    title: "Verified trainers stand out",
    body: "smallTech vets trainers and adds a Verified badge to their profile.",
  },
  {
    icon: "🗑️",
    title: "Leave any time",
    body: "Delete your account from your profile and your profile and CV are gone immediately.",
  },
];

const TOOLKIT_FEATURES: { icon: string; title: string; body: string }[] = [
  {
    icon: "📊",
    title: "A live dashboard across 300+ participants",
    body: "See every participant's progress and current step, refreshed every couple of seconds, with stuck and bottleneck alerts.",
  },
  {
    icon: "📝",
    title: "Markdown & code milestones",
    body: "Each step carries real instructions — headings, links, tables and syntax-highlighted code the room reads at its own pace.",
  },
  {
    icon: "🚪",
    title: "Name-only joining, nothing to install",
    body: "Participants open one link and type their first name. They auto-resume on refresh and get a personal link for another device.",
  },
  {
    icon: "🆘",
    title: "Help desk & room controls",
    body: "Answer raised hands in-page with the milestone context, broadcast a fix, pause the room or advance everyone past a broken step.",
  },
];

const TOOLKIT_STEPS: { title: string; body: string }[] = [
  {
    title: "Compose your milestones",
    body: "Write each step in markdown with the exact commands and code.",
  },
  {
    title: "Share one join link",
    body: "Put the link or its QR code on the projector — that is all the room needs.",
  },
  {
    title: "The room joins by name",
    body: "No accounts to create, no seats to assign.",
  },
  {
    title: "Watch the dashboard, answer help",
    body: "See who is ahead and who is stuck, and help without breaking the flow.",
  },
  {
    title: "Export the results",
    body: "Download the CSV; the workshop stays browsable as a read-only archive.",
  },
];

const FAQS: { q: string; a: React.ReactNode }[] = [
  {
    q: "Who is the Trainer Network for?",
    a: (
      <>
        Freelance and in-house trainers who teach Generative AI, agentic AI and
        modern tech — and, more broadly, mentors and engineers who run workshops,
        bootcamps or courses. You pick your topics and level from a curated list of
        40.
      </>
    ),
  },
  {
    q: "Where do the opportunities come from?",
    a: (
      <>
        smallTech curates every listing from its partner network — workshops and
        trainings, longer engagements, job and contract roles, and co-facilitator
        or TA spots on Workshop0&rsquo;s own workshops. Partners never use the
        platform; smallTech shares shortlisted profiles with them directly.
      </>
    ),
  },
  {
    q: "Who sees my profile and my rates?",
    a: (
      <>
        Your profile is private to smallTech by default.{" "}
        <strong>Your rates are only ever visible to smallTech.</strong> If you turn on a
        public directory profile, it shows your name, headline, topics and links —
        never your email, rates or CV.
      </>
    ),
  },
  {
    q: "What does joining cost?",
    a: <>Nothing. Sign in with Google, drop your CV and you are in.</>,
  },
  {
    q: "Do I need an account to run a workshop?",
    a: (
      <>
        No. The workshop toolkit has no signup and no login. When you create a
        workshop you get a private dashboard link — <strong>that link is the
        credential</strong>. <strong>Save it the moment it is shown to you</strong>: there
        is no account to recover and no password reset. Participants need only a
        browser and the join link.
      </>
    ),
  },
  {
    q: "Why do you ask for my email when I create a workshop?",
    a: (
      <>
        Purely so the person running this instance can contact you about your
        workshop if they have to.{" "}
        <strong>No mail is ever sent to you</strong> — not a confirmation, not a
        newsletter — and it is never shared. Your dashboard link is shown on screen,
        not mailed.
      </>
    ),
  },
];

// --------------------------------------------------------------------------
// Small pieces
// --------------------------------------------------------------------------

function ArrowIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="size-5">
      <path
        fillRule="evenodd"
        d="M3 10a.75.75 0 0 1 .75-.75h10.638L10.23 5.29a.75.75 0 1 1 1.04-1.08l5.5 5.25a.75.75 0 0 1 0 1.08l-5.5 5.25a.75.75 0 1 1-1.04-1.08l4.158-3.96H3.75A.75.75 0 0 1 3 10Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-sm font-semibold tracking-wide text-brand-600 uppercase">{children}</p>
  );
}

const PRIMARY_BTN =
  "inline-flex items-center gap-2 rounded-xl bg-brand-600 px-6 py-3.5 text-base font-semibold text-white shadow-lg shadow-brand-600/20 transition-colors hover:bg-brand-700 active:bg-brand-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600";

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function LandingPage() {
  return (
    <div className="min-h-screen overflow-x-hidden bg-stone-50 text-stone-900">
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
          <nav
            aria-label="Page sections"
            className="hidden items-center gap-6 text-sm text-stone-600 md:flex"
          >
            <a href="#topics" className="hover:text-stone-900">
              Topics
            </a>
            <a href="#network" className="hover:text-stone-900">
              How it works
            </a>
            <a href="#toolkit" className="hover:text-stone-900">
              Workshop toolkit
            </a>
            <a href="#faq" className="hover:text-stone-900">
              FAQ
            </a>
            <a
              href={BOARD_HREF}
              className="font-medium text-brand-700 hover:text-brand-800"
            >
              Opportunities
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
                For Gen AI, agentic AI &amp; tech trainers
              </p>
              <h1
                id="hero-heading"
                className="mt-5 text-4xl leading-[1.1] font-semibold tracking-tight text-stone-900 sm:text-5xl lg:text-6xl"
              >
                You teach AI.{" "}
                <span className="text-brand-600">We find you the rooms that need you.</span>
              </h1>
              <p className="mt-5 max-w-xl text-lg leading-relaxed text-stone-600">
                The smallTech Trainer Network matches trainers in Generative AI,
                agentic AI and modern tech with workshops, longer engagements and
                roles from our partner network. Drop your CV, check one screen, and
                you are in.
              </p>

              <div className="mt-8 flex flex-wrap items-center gap-4">
                <a data-testid="landing-cta" href={JOIN_HREF} className={PRIMARY_BTN}>
                  Join the Trainer Network
                  <ArrowIcon />
                </a>
                <a
                  data-testid="landing-browse-link"
                  href={BOARD_HREF}
                  className="text-sm font-medium text-stone-600 underline underline-offset-4 hover:text-stone-900"
                >
                  Browse opportunities
                </a>
              </div>

              <p className="mt-4 text-sm text-stone-500">
                Free to join · sign in with Google · about two minutes. Your rates
                stay private to smallTech.
              </p>
            </div>

            {/* Indicative trainer-profile vignette (static illustration, not live data) */}
            <div aria-hidden="true" className="lg:justify-self-end">
              <div className="w-full max-w-md rounded-2xl border border-stone-200 bg-white p-5 shadow-xl shadow-stone-900/5">
                <div className="flex items-center gap-3">
                  <span className="flex size-11 items-center justify-center rounded-full bg-brand-100 text-base font-semibold text-brand-700">
                    A
                  </span>
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 text-sm font-semibold text-stone-800">
                      Your profile
                      <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                        Verified
                      </span>
                    </p>
                    <p className="truncate text-xs text-stone-500">
                      Agentic AI trainer · Bengaluru · Remote OK
                    </p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {[
                    ["Agentic AI (LangChain / LangGraph)", "Expert"],
                    ["Generative AI & LLMs", "Advanced"],
                    ["Python", "Expert"],
                  ].map(([t, l]) => (
                    <span
                      key={t}
                      className="rounded-full border border-brand-100 bg-brand-50 px-2.5 py-1 text-xs text-brand-800"
                    >
                      {t} · <span className="font-medium">{l}</span>
                    </span>
                  ))}
                </div>
                <div className="mt-5 space-y-2.5">
                  <p className="text-xs font-medium tracking-wide text-stone-400 uppercase">
                    Suggested for you
                  </p>
                  {[
                    ["Workshop / training", "Agents in production — 2-day lab", "Invited"],
                    ["Longer engagement", "GenAI curriculum design", "Applied"],
                  ].map(([type, title, status]) => (
                    <div
                      key={title}
                      className="flex items-center justify-between gap-3 rounded-lg border border-stone-200 bg-stone-50 px-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="text-xs text-stone-500">{type}</p>
                        <p className="truncate text-sm font-medium text-stone-800">{title}</p>
                      </div>
                      <span className="shrink-0 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">
                        {status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------- topics */}
        <section
          id="topics"
          data-testid="landing-topics"
          aria-labelledby="topics-heading"
          className="mx-auto max-w-6xl scroll-mt-16 px-4 py-20 sm:px-6"
        >
          <Eyebrow>What our trainers teach</Eyebrow>
          <h2
            id="topics-heading"
            className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight text-stone-900 sm:text-4xl"
          >
            Built for people who teach Gen AI, agentic AI and modern tech.
          </h2>
          <p className="mt-3 max-w-2xl text-stone-600">
            Opportunities and profiles speak one vocabulary — a curated list of 40
            topics, each with a level from Intermediate to Expert — so matches are
            about what you actually teach.
          </p>

          <ul className="mt-12 grid gap-6 md:grid-cols-3">
            {TOPIC_GROUPS.map((g) => (
              <li key={g.title} className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm">
                <span
                  aria-hidden="true"
                  className="flex size-11 items-center justify-center rounded-xl border border-brand-100 bg-brand-50 text-xl"
                >
                  {g.icon}
                </span>
                <h3 className="mt-4 text-lg font-semibold text-stone-900">{g.title}</h3>
                <p className="mt-1 text-sm text-stone-600">{g.blurb}</p>
                <ul className="mt-4 flex flex-wrap gap-2">
                  {g.topics.map((t) => (
                    <li
                      key={t}
                      className="rounded-full bg-stone-100 px-2.5 py-1 text-xs font-medium text-stone-700"
                    >
                      {t}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </section>

        {/* ------------------------------------------- how the network works */}
        <section
          id="network"
          data-testid="landing-network"
          aria-labelledby="network-heading"
          className="scroll-mt-16 border-y border-stone-200 bg-white"
        >
          <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
            <Eyebrow>How the network works</Eyebrow>
            <h2
              id="network-heading"
              className="mt-2 max-w-2xl text-3xl font-semibold tracking-tight text-stone-900 sm:text-4xl"
            >
              From CV to your next engagement, without the cold emails.
            </h2>
            <p className="mt-3 max-w-2xl text-stone-600">
              Every opportunity is curated by smallTech:{" "}
              {OPPORTUNITY_TYPES.join(" · ")}.
            </p>

            <ol className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-5">
              {NETWORK_STEPS.map((s, i) => (
                <li key={s.title} className="rounded-xl border border-stone-200 bg-stone-50/70 p-5">
                  <span className="flex size-9 items-center justify-center rounded-full bg-brand-600 text-sm font-semibold text-white">
                    {i + 1}
                  </span>
                  <h3 className="mt-4 text-base font-semibold text-stone-900">{s.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-stone-600">{s.body}</p>
                </li>
              ))}
            </ol>

            <ul
              data-testid="landing-trust"
              className="mt-12 grid gap-x-10 gap-y-8 rounded-2xl border border-brand-200 bg-brand-50/60 p-6 sm:grid-cols-2 sm:p-8"
            >
              {TRUST.map((t) => (
                <li key={t.title} className="flex gap-3">
                  <span aria-hidden="true" className="text-xl">
                    {t.icon}
                  </span>
                  <div>
                    <h3 className="text-sm font-semibold text-stone-900">{t.title}</h3>
                    <p className="mt-1 text-sm leading-relaxed text-stone-600">{t.body}</p>
                  </div>
                </li>
              ))}
            </ul>

            <div className="mt-10 flex flex-wrap items-center gap-4">
              <a href={JOIN_HREF} className={PRIMARY_BTN}>
                Join the Trainer Network
                <ArrowIcon />
              </a>
              <a
                href={BOARD_HREF}
                className="text-sm font-medium text-stone-600 underline underline-offset-4 hover:text-stone-900"
              >
                See what&rsquo;s open on the board
              </a>
            </div>
          </div>
        </section>

        {/* ---------------------------------------------- bonus: toolkit */}
        <section
          id="toolkit"
          data-testid="landing-features"
          aria-labelledby="toolkit-heading"
          className="mx-auto max-w-6xl scroll-mt-16 px-4 py-20 sm:px-6"
        >
          <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
            <div>
              <Eyebrow>Bonus · free for everyone</Eyebrow>
              <h2
                id="toolkit-heading"
                className="mt-2 max-w-xl text-3xl font-semibold tracking-tight text-stone-900 sm:text-4xl"
              >
                A free toolkit for running your hands-on sessions.
              </h2>
              <p className="mt-3 max-w-xl text-stone-600">
                Workshop0 turns your agenda into live milestones your participants
                tick off in their browser — so you can see, in real time, who is
                flying, who is stuck and which step is swallowing the room. No
                signup, for you or for them.
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

          <ul className="mt-14 grid gap-x-10 gap-y-10 sm:grid-cols-2">
            {TOOLKIT_FEATURES.map((f) => (
              <li key={f.title} className="flex gap-4">
                <span
                  aria-hidden="true"
                  className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-brand-100 bg-brand-50 text-xl"
                >
                  {f.icon}
                </span>
                <div>
                  <h3 className="text-base font-semibold text-stone-900">{f.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-stone-600">{f.body}</p>
                </div>
              </li>
            ))}
          </ul>

          <div
            data-testid="landing-how-it-works"
            className="mt-14 rounded-2xl border border-stone-200 bg-white p-6 shadow-sm sm:p-8"
          >
            <h3 className="text-lg font-semibold text-stone-900">How the toolkit works</h3>
            <ol className="mt-6 grid gap-6 sm:grid-cols-2 lg:grid-cols-5">
              {TOOLKIT_STEPS.map((s, i) => (
                <li key={s.title}>
                  <span className="flex size-8 items-center justify-center rounded-full border border-brand-200 bg-brand-50 text-sm font-semibold text-brand-700">
                    {i + 1}
                  </span>
                  <p className="mt-3 text-sm font-semibold text-stone-900">{s.title}</p>
                  <p className="mt-1 text-sm leading-relaxed text-stone-600">{s.body}</p>
                </li>
              ))}
            </ol>
            <div className="mt-8 flex flex-wrap items-center gap-4 border-t border-stone-200 pt-6">
              <a
                data-testid="landing-workshop-cta"
                href={CREATE_HREF}
                className="inline-flex items-center gap-2 rounded-xl border border-brand-600 px-5 py-3 text-sm font-semibold text-brand-700 transition-colors hover:bg-brand-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
              >
                Create a workshop — free, no signup
                <ArrowIcon />
              </a>
              <p className="text-sm text-stone-500">
                Takes about two minutes. Nothing to install.
              </p>
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
          <Eyebrow>Straight answers</Eyebrow>
          <h2
            id="faq-heading"
            className="mt-2 text-3xl font-semibold tracking-tight text-stone-900 sm:text-4xl"
          >
            Frequently asked questions
          </h2>

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
              Your next room is out there.
            </h2>
            <p className="mx-auto mt-2 max-w-md text-sm text-stone-600">
              Drop your CV, check one screen, and get matched to work in Gen AI,
              agentic AI and tech.
            </p>
            <a href={JOIN_HREF} className={`mt-6 ${PRIMARY_BTN}`}>
              Join the Trainer Network
              <ArrowIcon />
            </a>
          </div>
        </section>
      </main>

      {/* ------------------------------------------------------- footer */}
      <footer className="border-t border-stone-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-8 text-sm text-stone-500 sm:px-6">
          <p>
            <span aria-hidden="true">⛵</span> Workshop0 — home of the smallTech
            Trainer Network.
          </p>
          <p className="flex flex-wrap items-center gap-4">
            <a
              href={BOARD_HREF}
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
              <svg viewBox="0 0 16 16" aria-hidden="true" className="h-5 w-5 fill-current">
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
