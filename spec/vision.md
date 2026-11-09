# Vision — Workshop0 (v0.2)

> This spec supersedes v0.1 entirely, including all v0.1 non-goals (notably "no React / no build step" — v0.2 is a Next.js frontend by explicit user choice). The v0.1 code in `src/` and `frontend/` is removed at scaffold; v0.2 is built fresh from this spec.

## What it is

Workshop0 is a **self-hosted workshop assistant for facilitator-led, hands-on technical labs**. A facilitator creates a workshop, shares one join link, and 100–300+ participants work through a checklist of **content-rich milestones** (full markdown instructions, links, code snippets) on their own devices. The facilitator watches a **genuinely live dashboard** — per-milestone completion, cohort distribution, a help queue — and intervenes with broadcasts, milestone controls, and answers. An **AI help-desk** (OpenRouter) triages help requests: it gathers the participant's context and past resolutions, auto-answers when confident (clearly badged, one tap to escalate to a human), and drafts a reply for facilitator review when unsure. Without an API key, the entire product works air-gapped with zero errors.

It is production-grade from day one: real workshops with external participants depend on it, so polish, resilience, and first-time-right behavior are the bar — not aspirations.

## Who it serves

- **Facilitators** (a small team, co-facilitating the same live workshop) who need to know *right now* which milestone the room is piled up on, who is stuck, and which help requests are open — and to act on it: broadcast, advance, pause, answer, undo a fat-fingered action. No accounts: unguessable token links.
- **Participants** (100–300+ per session, including external attendees) who join with near-zero friction (name at the door), get a personal link that survives device switches and browser restarts, see rich instructions per milestone, mark progress, watch a leaderboard, and get help fast — from the AI instantly when it's confident, from a human otherwise.

## Session lifecycle

Workshops are created fresh per session — from scratch or from a persistent **template library** (agenda templates + join-form templates). A live workshop ends into a **grace period** for stragglers, then becomes a **read-only archive**, browsable forever. Workshops are clonable/re-runnable. Full session archives persist indefinitely.

## Quality bar

- **First-time-right.** Every phase's tested path works the first time the user tests it. Zero rough edges on the tested path; stubs for future features are clearly labelled and never read as bugs.
- **Resilient by construction.** All state lives in the database, never only in memory. A participant who reconnects gets their exact state back. A server restart mid-session loses nothing — every client recovers on its next poll with no user action.
- **Live at scale on modest hardware.** 300+ concurrent participants on small, cheap infrastructure (a scale-to-zero container service and a shared small database from Phase 7; originally one 2 vCPU VM), near-zero running cost (see [architecture.md](architecture.md) for the versioned-polling design that achieves this).
- **Visually excellent.** A modern, polished UI with a consistent design system — this is the product's face to external participants. Every view designs its empty, loading, error, and populated states.
- **Honest AI.** AI answers are always badged as AI, always escapable to a human, always audited with the exact context the AI used, and always costed (per-workshop spend visible).

## The Trainer Network & Opportunity Board (Phases 10–13)

smallTech is building a network of freelance and in-house tech trainers — and more broadly mentors, engineers and learners — and it lives inside Workshop0 for now. Two halves:

- **A public, admin-curated Opportunity Board.** Workshop and training gigs, longer engagements (bootcamps, mentoring, curriculum design), job/contract roles, and Workshop0's own workshops needing co-facilitators or TAs — posted, edited and closed only by smallTech admins on behalf of the partner network. Partners never touch the platform; admins forward shortlisted profiles out of band. Listings expire automatically at their deadline. Internal partner names stay internal.
- **A self-serve trainer network.** People find the board, sign in with Google, drop a CV (or a LinkedIn PDF, or pasted text), review a pre-filled profile on one screen, and they are in — live instantly, with an admin "Verified" badge for vetted trainers. They apply in one click and track their status; admins search the pool, get suggested shortlists for a listing, invite trainers to apply, and run an applicant pipeline with status emails.

Who it serves, additionally: **smallTech admins** (curate listings and the pool, match, shortlist) and **network members** (discover work, apply, get matched). Quality bar is unchanged: first-time-right, visually excellent, privacy by default (the pool is private to admins; rates are always admin-only; a public directory profile is opt-in; self-serve deletion of profile and CV). Scale: hundreds of trainers, tens of listings, bursty signups (~500/day). The board is the first phase because it is valuable on its own and needs nothing external.

Network identity is deliberately an **isolated, OIDC-shaped module** so it can later move to a central smallTech identity service without touching product code. Workshop facilitators and participants keep their account-free token links — the network never becomes a prerequisite for running or joining a workshop.

## Explicit non-goals (v0.2)

> **Amended by the Trainer Network (Phases 10–13):** the network adds Google sign-in accounts (network members and admins only), transactional email (Phase 12) and the public board/directory. The non-goals below still hold for the **workshop** product — no participant or facilitator accounts, no email in the live-workshop loop.

- **No participant accounts, no facilitator accounts, no auth-provider integration** *(for workshops — the trainer network adds its own Google sign-in, see above)*. Access is via unguessable token links plus a single instance-level facilitator access key.
- **No separate concurrent-workshop isolation model.** Multiple facilitators co-run the *same* workshop; running several workshops at once is possible but not a designed-for isolation boundary (one team, one instance).
- **No lecture mode or multi-day cohort mode** — future versions, not v0.2.
- **No external integrations** (no Slack/webhooks/calendar) — the only exceptions are the trainer network's Google sign-in (Phase 11) and its transactional email over SMTP (Phase 12). Standalone otherwise.
- **No partner-facing platform access, no LinkedIn URL scraping, no calendar-grade availability** for the network — partners are served by admins out of band; profiles import from CV files/pasted text only; availability is a weekly pattern + dates.
- **No participant-to-participant chat, no breakout rooms.**
- **No WebSockets/SSE** — live updates are versioned coalesced polling (a deliberate architecture decision, see architecture.md).
- **No dark mode in v0.2** — one polished light theme; design tokens are structured so dark mode can be added later without rework.
- **No health/ops chrome in the UI** — a plain `/api/health` endpoint exists for machines; the UI stays clean.
- **No vector database** — help-request similarity uses database full-text keyword search (PostgreSQL tsvector in production, SQLite FTS5 locally; see [agent.md](agent.md)).

## The one-line test

A facilitator can go from `docker compose up` (or `uv run python -m src`) locally, or from the public production URL, to a live workshop with 300 external participants tracking milestones and getting help — without reading anything beyond the join link they share.
