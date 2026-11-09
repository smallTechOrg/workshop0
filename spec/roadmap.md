# Roadmap — Workshop0 (v0.2)

Ground-up rebuild. The old `src/` and `frontend/` are **removed at scaffold**; nothing is preserved by inertia. Canonical run path (every phase): `(cd frontend && pnpm build)` → `uv run python -m src` → open **http://localhost:8001/app/**. `pnpm dev` is inner-loop only, never the test path.

**Shared scaffold (laid down by the orchestrator BEFORE any generator runs, so slices stay disjoint):** `pyproject.toml` (full Phase-1 dependency list from architecture.md §Stack), `alembic.ini`, `.env.example` (all vars from architecture.md §Environment variables), `README.md` skeleton, `.gitignore` (`data/`, `.env`, `frontend/out/`, `node_modules/`), `data/.gitkeep`, removal of the v0.1 app code. Generators never edit another slice's files; root scaffold files are edited only by the orchestrator between fan-outs.

## Phases of Development

| Phase | Theme | Status |
|---|---|---|
| 1 | Core live loop (create, join, milestones, live dashboard, manual help desk) | delivered |
| 2 | Facilitator command & proactive intelligence | delivered |
| 3 | Lifecycle, templates & re-run | delivered |
| 4 | AI help-desk (OpenRouter) | delivered — but see the code-truth note below |
| 5 | Docker + CI/CD (VM path, since retired) | delivered |
| 6 | Public landing page & self-service creation | delivered |
| 7 | Cloud Run + Cloud SQL (fresh database) | delivered |
| 8 | Cutover: data import, `workshop0.smalltech.in`, retire the VM | delivered |
| 9 | Rename everything to Workshop0 (code, brand, client storage, infra, repo) | delivered (PR #7) |
| 10 | Opportunity Board: topic taxonomy, admin listings, public board (C8–C10) | specified |
| 11 | Trainer sign-in, CV-drafted profiles & admin pool (C11–C13) + **11b** Phase-10 feedback: managed partners, paste-to-fill drafting, compensation unit (C9/C10 extended) | specified |
| 11c | Multi-location opportunities: several cities per listing, editor chips, compact card display, multi-city drafting (C9/C10 extended; SMA-9) | specified |
| 12 | Applications, matching & email outbox (C14–C16) | specified |
| 13 | Alerts & digest, public directory, workshop tie-in (C17–C19) | specified |

> **Code truth — Phase 4 (verified 2026-11-09 by grepping `src/`):** the help-desk pipeline is not in code. There is no `src/workshop0/ai/`; only its schema (`ai_usage`, `help_request.ai_state`), the settings `openrouter_api_key`/`workshop0_ai_model` and the startup key-presence log exist. This is drift for `/zero-shot-sync`; Phases 10–13 neither repair it nor depend on it. Phase 11 creates `src/workshop0/ai/` for the **Anthropic**-backed network AI.

**Trainer Network ordering rationale.** Phase 10 needs nothing external (no Google client, no SMTP, no LLM key) and is valuable alone. Phases 11–13 each keep their **automated** gate free of human-only steps — sign-in is gated through a real OIDC protocol run against the local test issuer, email through a real local SMTP sink, network-AI calls through the real **Anthropic** key + workspace id read from the gitignored local `.env` (already present) — while the steps only a human can do (Google Console client, Gmail app password, creating Secret Manager secrets) are part of that phase's "How the user tests it". So no build ever stalls on an AFK user; external blockers bite only at the human testing gate, where the human is present.

**Parallel fan-out rule (Phases 11–13).** Each phase's scaffold commit (orchestrator, before the fan-out) creates **every cross-slice registration point and interface stub** listed in that phase: router shells registered in `create_app()`, new settings fields, `.env.example` lines, dependency/lockfile changes, and **signature stubs** for every module that another slice imports. Python stubs declare the fixed interface and have bodies that `raise NotImplementedError`, except where noted, e.g. a no-op startup hook. TypeScript stubs have the exact exported types/signatures with placeholder bodies that type-check. The app therefore imports, and `pnpm build` passes, at every point of the fan-out. The slice that owns a stubbed file replaces its bodies and keeps the stubbed signatures; it may add, never rename. No two slices own the same path. "Build" dependencies are therefore always none. A **test** dependency means the slice's tests pass only once the named slices have landed, and agent-builder orders verification, not writing, accordingly. When a phase has more slices than the fan-out cap (~min(16, cores−2)), agent-builder runs them in waves in table order: backend → frontend → e2e → infra/docs.

---

## Phase 1 — Core Live Loop *(scope fixed; smallest user-testable win, first-time-right)*

**Goal:** A facilitator creates a workshop, shares the join link; 300 participants join with just a name, work content-rich milestones; the dashboard is genuinely live; one help request is submitted, answered, and seen — beautiful and rock-solid, with every future surface present as a clearly-labelled stub.

**Capabilities delivered:** C1 Workshop creation & facilitator access · C2 Frictionless participant identity (cookie auto-resume, personal links, lost-link recovery) · C3 Content-rich milestone tracking + live dashboard · C4 Help desk (manual). Plus cross-cutting: versioned coalesced polling, structured JSON logging to stdout, resilience (restart-safe, reconnect-safe), labelled stubs for broadcast/pause/AI/templates/intelligence/audit/spend.

**Independent slices (all three fan out in parallel — disjoint paths, no build dependencies):**

| Slice | Owns (exclusive paths) | Notes |
|---|---|---|
| **S1 backend** | `src/**`, `alembic/**`, `tests/conftest.py`, `tests/unit/**`, `tests/integration/**` | Full Phase-1 API per api.md; models are the **full v0.2 schema** (data-model.md) in migration `0001_initial`; snapshot cache + version counters; structlog middleware; static mount + pretty redirects; audit rows for `workshop.create`/`help.answer`/`help.resolve` |
| **S2 frontend** | `frontend/**` | All four pages + design system + StubBadge surfaces per capabilities.md; typed client + polling hook per api.md (contract-first — no backend needed to build) |
| **S3 e2e** | `tests/e2e/**`, `playwright.config.ts`, `package.json` (root), `pnpm-lock.yaml` (root) | Playwright specs written from api.md + capabilities.md. No build dependency; **runtime dependency on S1+S2 at gate time only** (specs run against the live server) |

**Key surfaces/files:** see architecture.md §Repo layout — S1: `api/{admin,facilitator,participant,health}.py`, `services/snapshots.py`, `db/models.py`, `security.py`, `observability/logging.py`; S2: `app/{page,f/page,join/page,p/page}.tsx`, `components/{ui,facilitator,participant}/`, `lib/{api,poll}.ts`; S3: `tests/e2e/core-loop.spec.ts`.

**Gate (exact commands, from repo root; once beforehand: `cp .env.example .env` and set `WORKSHOP0_ADMIN_KEY`):**

```bash
uv sync
(cd frontend && pnpm install) && pnpm install && pnpm exec playwright install chromium
uv run alembic upgrade head
uv run alembic current            # MUST print a revision hash — blank output = gate failed
uv run pytest tests/unit tests/integration -q
(cd frontend && pnpm build)
grep -q '\.flex' frontend/out/_next/static/css/*.css         # styled-render: real utilities present
! grep -q '@source' frontend/out/_next/static/css/*.css      # …and no unexpanded Tailwind directives
uv run python -m src &            # live server on :8001 (leave running)
pnpm exec playwright test tests/e2e --reporter=line
kill %1
```

The e2e smoke covers the full loop against the live single-origin app: create workshop (3 milestones incl. a code block) → join as two participants in separate contexts → tracker renders styled markdown → mark complete → dashboard reflects it within one poll → help request → answer from queue → answer visible on tracker → participant resolves → **browser reload restores state (cookie)** and **the personal link opens identical state in a fresh context (cross-device)** → labelled stubs are visible and non-interactive. Integration tests additionally cover: idempotent complete/uncomplete, version-counter bumps, unchanged-poll short-circuit, server-restart state survival (new process, same DB file), and every documented error code.

**How the user tests it:** run the three commands above (sync/build/serve), open `http://localhost:8001/app/` → enter your `WORKSHOP0_ADMIN_KEY` → **New workshop** → add 3 milestones with markdown + a code snippet → create → copy the join link → open it in a private window → join as "Priya" → read a milestone, mark it complete → watch the dashboard bars move within ~2 s → submit a help request from the tracker → answer it from the dashboard queue (use markdown + code) → see the badged answer appear on the tracker → mark resolved → close and reopen the private window (auto-resume) and paste the personal link into another browser (same state). **Labelled stubs (not bugs):** Broadcast, Pause, End workshop, AI toggle, Spend, stuck/bottleneck/pulse cards, Audit tab, Template library, Upcoming/Ended groups — all carry a "Coming in a later phase" pill.

---

## Phase 2 — Facilitator Command & Proactive Intelligence

**Goal:** The facilitator can steer the room — broadcast, pause, advance, reorder/edit, undo a fat-fingered action — and the dashboard tells them proactively who is stuck, where the pile-up is, and how the session is pacing.

**Capabilities delivered:** Broadcast announcements · Milestone controls (advance all/selected, pause/resume, reorder, edit/add/delete) · Undo (30 s window) · Audit trail UI · Proactive intelligence (stuck alerts, bottleneck, session pulse).

**Independent slices (parallel; no intra-phase dependencies):**

| Slice | Owns |
|---|---|
| **S1 backend** | `src/**` (facilitator endpoints, `services/{undo,intelligence}.py`, snapshot additions), `tests/unit/**`, `tests/integration/**` additions |
| **S2 frontend** | `frontend/**` — broadcast composer w/ preview + undo toast, pause states, advance controls w/ confirmation, reorder UI, audit tab, alerts/pulse cards replacing their stubs; participant banner + paused lock |
| **S3 e2e** | `tests/e2e/**` additions (command flows + undo + banner) |

**Gate (repo root; same setup):** `uv run alembic upgrade head && uv run alembic current` · `uv run pytest tests/unit tests/integration -q` · `(cd frontend && pnpm build)` · server up → `pnpm exec playwright test tests/e2e --reporter=line`. Integration tests must cover: undo inside/after the window (`undo_expired`), advance-all creating only missing completions (`source: "facilitator"`), pause blocking complete *and* uncomplete, audit rows for every action, stuck/bottleneck/pulse computed against a seeded 40-participant fixture whose expected alert set is pre-computed (not a trivially-empty fixture).

**How the user tests it:** with a live workshop + a few joined participants: send a markdown broadcast → banner appears on trackers within a poll → **Undo** within 30 s → banner gone. Pause → participant checkboxes lock with a banner. Advance-all on milestone 1 → bars jump → Undo → they revert. Reorder milestones → tracker order updates. Leave one participant idle past the stuck threshold → stuck alert card names them; the pulse card shows pace + projected finish. Open the Audit tab → every action listed who/what/when.

---

## Phase 3 — Lifecycle, Templates & Re-run

**Goal:** Workshops become sessions with a life: created from persistent templates (agenda + join form), ended into a grace period, archived read-only forever, and clonable for the next run.

**Capabilities delivered:** End/grace/archive lifecycle (lazy transitions, read-only archive views) · Clone/re-run · Agenda template library (+ save-as-template) · Join-form templates & custom join fields · Admin Home lifecycle grouping (Live/Upcoming/Ended, `starts_at`).

**Independent slices (parallel):**

| Slice | Owns |
|---|---|
| **S1 backend** | `src/**` (`services/{lifecycle,templates}.py`, admin/facilitator/participant endpoint additions), `tests/**` (py) additions |
| **S2 frontend** | `frontend/**` — template library page + pickers (replacing stubs), end-workshop dialog w/ grace hours, archive read-only styling, clone, join-form custom fields, Admin Home grouping |
| **S3 e2e** | `tests/e2e/**` additions |

**Gate (repo root):** same command sequence as Phase 2. Integration tests must cover: lazy transition on access (set `grace_until` in the past → next request archives), archived rejects every mutation with `workshop_archived` while reads still serve, template edit never mutating an instantiated workshop (snapshot proof), clone = fresh tokens + zero participants, join-form validation against the snapshot.

**How the user tests it:** save the running workshop as a template → create a new workshop from it (milestones pre-filled) → add a custom dropdown join field via a form template → join page shows it → **End workshop** with a 1-hour grace → tracker shows the grace banner, completions still work → **Archive now** → tracker and dashboard flip to read-only archive views; Admin Home shows it under Ended → **Clone** → a fresh Live workshop with the same agenda and new links.

---

## Phase 4 — AI Help-Desk

**Goal:** Help requests are triaged by AI that knows the participant's context and every past resolution: confident → instant badged auto-answer with one-tap human escalation; unsure → draft for facilitator review — fully audited, costed per workshop, per-workshop toggleable, and a zero-error no-op without an API key.

**Capabilities delivered:** AI triage & auto-answer pipeline · Escalation & transparency (AI badge, "Get a human", exact-context disclosure) · Cross-workshop learning corpus (FTS5) · Spend tracking + per-workshop toggle + air-gapped guarantee. Design is fixed in [agent.md](agent.md).

**Independent slices (parallel; S1↔S2 share only the `run_help_desk(help_request_id)` interface fixed in agent.md — no serialization needed):**

| Slice | Owns |
|---|---|
| **S1 ai-pipeline** | `src/workshop0/ai/**` (pipeline, context, corpus, openrouter client, prompts), `tests/integration/ai/**`, corpus migration (`alembic/versions/` addition) |
| **S2 backend-api** | `src/workshop0/api/**` (toggle/spend/escalate endpoints, BackgroundTask hookup in participant help POST), `src/workshop0/services/snapshots.py` (spend + AI fields), `tests/unit/**` + non-AI integration additions |
| **S3 frontend** | `frontend/**` — AI badge + escalate on tracker; draft-review block, context disclosure, spend card, AI toggle (replacing stubs) |
| **S4 e2e** | `tests/e2e/**` additions (AI auto-answer flow, escalation, air-gapped run) |

**Gate (repo root; requires the real `OPENROUTER_API_KEY` in `.env` — the gate is BLOCKED, not skipped, without it):** `uv run alembic upgrade head && uv run alembic current` · `uv run pytest tests/unit tests/integration -q` (now includes `tests/integration/ai` against the **real OpenRouter API**; the similarity fixture seeds 25+ resolved requests across ≥3 workshops with exactly one strong match asserted at rank 1 — per agent.md §Testing) · `(cd frontend && pnpm build)` · server up → `pnpm exec playwright test tests/e2e --reporter=line` (includes the real-key auto-answer journey **and** the keyless air-gapped journey with zero errors and zero AI chrome).

**How the user tests it:** with `OPENROUTER_API_KEY` set: toggle AI on → as a participant, ask something answered by the milestone content → an **AI-badged** answer appears in seconds → tap **Get a human** → request returns to the queue flagged, AI answer still visible → in the queue, expand **Context the AI used** → see progress/milestone/similar-resolutions exactly → ask something ambiguous → a violet **draft** waits in the queue; edit and send it → spend card shows real dollars. Then remove the key, restart: everything works, AI surfaces show a labelled off state, zero errors anywhere.

---

## Phase 5 — Ship It: Docker + CI/CD to GCP

**Goal:** One-command production deploy and an automated path from merge to the VM.

**Capabilities delivered:** Docker Compose packaging (multi-stage image, volume-backed SQLite, migrations on boot) · CI on GitHub Actions (tests on PR; real-key jobs guarded to runners with secrets) · CD to the GCP VM (image build → registry → compose deploy) + `deploy/RUNBOOK.md` (backup/restore of `data/`, TLS proxy note).

**Independent slices (parallel):** **S1 deploy** — `deploy/**` (Dockerfile, docker-compose.yml, RUNBOOK.md) + README deploy section · **S2 ci-cd** — `.github/workflows/**` (ci.yml, deploy.yml).

**Gate (repo root):** `docker compose -f deploy/docker-compose.yml up -d --build` · `curl -fsS http://localhost:8001/api/health` · `pnpm exec playwright test tests/e2e --reporter=line` against the container · `docker compose -f deploy/docker-compose.yml down` (volume persists; re-`up` retains data — verified by the e2e re-run finding the same workshop) · CI workflow green on the PR.

**How the user tests it:** `cp .env.example .env`, set the key(s), `docker compose -f deploy/docker-compose.yml up -d` → open `http://localhost:8001/app/` → run the Phase-1 manual loop → `docker compose restart` mid-session → participants reconnect with nothing lost. Merge a PR → watch Actions deploy it to the VM.

---

## Phase 6 — Public Landing Page & Self-Service Workshop Creation

**Goal:** A stranger lands on `/`, understands the product, and creates and runs their own workshop with full facilitator powers — never touching an access key — while the admin keeps the only cross-workshop view and can see who created what.

**Capabilities delivered:** C5 Public landing page · C6 Self-service workshop creation (keyless, email as the last step before the link reveal, localStorage "your workshops") · C7 Admin oversight of public workshops (origin badge + creator email; console moves to `/app/admin/` with a pretty `/admin`).

**Non-goals for this phase (explicit):** no accounts, no login, no email sending or verification, no rate limiting, no creation cap, no captcha, no reduced facilitator tier for public creators. Accepted risk recorded in [architecture.md](architecture.md) §Auth model.

**Independent slices (all three fan out in parallel — disjoint owned paths, no build dependencies):**

| Slice | Owns (exclusive paths) | Delivers |
|---|---|---|
| **S1 backend** | `src/**`, `alembic/versions/0004_public_creation.py`, `tests/unit/**`, `tests/integration/**` | New `services/workshops.py` creation service extracted from `api/admin.py` (single implementation, both callers); new `api/public.py` with keyless `POST /api/public/workshops`; `creator_email` + `created_via` on the model and on both admin responses; `GET /` serves `frontend/out/index.html` via `FileResponse` (307 fallback when unbuilt) + `GET /admin` → 307 `/app/admin/`; migration `0004` (batch mode) |
| **S2 frontend** | `frontend/**` | Landing page at `frontend/app/page.tsx` (C5); Admin Home relocated to `frontend/app/admin/page.tsx` unchanged in behaviour (C7 badges + email added); new `frontend/app/create/page.tsx` (C6) reusing the composer extracted into `frontend/components/create/` shared by both; `lib/localWorkshops.ts`; `lib/api.ts` gains `createPublicWorkshop` |
| **S3 e2e** | `tests/e2e/**` (whole directory) | New `landing.spec.ts` + `public-creation.spec.ts` (keyless create→join→live journey and the admin-sees-it check); plus the **mechanical URL migration** of the existing specs — `smoke.spec.ts` (`GET /` is now 200 HTML, not a redirect into `/app/`) and every `goto(\`${APP_BASE}/\`)` Admin-Home navigation in `core-loop.spec.ts` and `facilitator-command.spec.ts` → `` `${APP_BASE}/admin/` ``. No build dependency; **runtime dependency on S1+S2 at gate time only** |

> **Assumed:** S3 owns the entire `tests/e2e/` directory this phase, because the Admin-Home relocation and the `/` behaviour change mechanically touch three existing specs (`smoke`, `core-loop`, `facilitator-command`) plus `helpers.ts`. No other slice may edit anything under `tests/e2e/`. These are the **only** permitted changes to existing e2e specs — assertions and journeys stay identical apart from the URL.

**Key surfaces/files** — S1: `src/workshop0/services/workshops.py`, `src/workshop0/api/{public,admin,__init__}.py`, `src/workshop0/db/models.py` (Workshop), `alembic/versions/0004_public_creation.py`, `tests/integration/test_public_creation.py`, `tests/unit/test_creator_email.py`. S2: `frontend/app/{page,admin/page,create/page}.tsx`, `frontend/components/create/WorkshopComposer.tsx`, `frontend/components/landing/*`, `frontend/lib/{api,localWorkshops}.ts`. S3: `tests/e2e/{landing,public-creation}.spec.ts`.

**Gate (exact commands, from repo root; `.env` already has `WORKSHOP0_ADMIN_KEY`):**

```bash
uv sync
(cd frontend && pnpm install) && pnpm install && pnpm exec playwright install chromium
uv run alembic upgrade head
uv run alembic current            # MUST print 0004 — blank output or 0003 = gate failed
uv run pytest tests/unit tests/integration -q   # ALL pre-existing tests must still pass
(cd frontend && pnpm build)
test -f frontend/out/index.html                              # landing page is the export root
test -f frontend/out/create/index.html                       # public create route exported
test -f frontend/out/admin/index.html                        # admin console relocated
grep -q '\.flex' frontend/out/_next/static/css/*.css         # styled-render: real utilities present
! grep -q '@source' frontend/out/_next/static/css/*.css      # …and no unexpanded Tailwind directives
uv run python -m src &            # live server on :8001 (leave running)
sleep 3
curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:8001/ | grep -qx 200   # / is the page, not a 307
curl -fsS http://localhost:8001/ | grep -q 'data-testid="landing-cta"'             # hero CTA present in the served HTML
curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:8001/admin | grep -qx 307
pnpm exec playwright test tests/e2e --reporter=line          # includes ALL pre-existing specs
kill %1
```

**Gate conditions beyond the commands:** every pre-existing unit and integration test passes with exactly **one** permitted Python edit — `tests/integration/test_redirects.py`, whose parametrized redirect list drops `("/", "/app/")` (no longer a redirect) and gains `("/admin", "/app/admin/")`; the same file gains a `/` case asserting 200 `text/html` when `frontend/out/index.html` exists and the documented 307 `/app/` fallback when it does not. No other Python test may be edited. Every pre-existing e2e spec passes with only the mechanical URL migration described in the S3 row (Admin Home `/app/` → `/app/admin/`, and `GET /` now 200 HTML); no e2e assertion or journey may be weakened or deleted. Integration tests must cover: public create with a valid email → row with `created_via="public"` and the stored email · the same body with a missing / blank / malformed email (`"a@b"`, `"no-at.example.com"`, `" "`) → 422 `validation_error` **and zero rows created** · public create with no `X-Admin-Key` header succeeds while `POST /api/admin/workshops` without it still returns 401 `invalid_admin_key` · a public-created workshop's `admin_token` exercises three facilitator mutations (broadcast, pause, milestone advance) successfully — parity proof · that token returns 404 for a *different* workshop's ids — isolation proof · `GET /api/admin/workshops` returns `created_via` and `creator_email` for both origins · admin create still returns `created_via="admin"`, `creator_email: null` · the email never appears in any facilitator/participant/poll payload (assert on the serialized JSON) · `GET /` returns 200 HTML and `GET /admin` returns 307.

**How the user tests it:** run the build and server commands above, then open **http://localhost:8001/** in a fresh private window — read the marketing page top to bottom (hero, features, how-it-works, FAQ; there is no "Your workshops" section yet and no admin link anywhere). Click **"Create your workshop — free, no signup"** → compose a workshop with 3 milestones including a markdown list and a fenced code block → on the last step enter your email (try a bad one first: it is rejected inline and nothing is created) → **Create workshop** → the success screen shows your dashboard link (with the "this is the only key — save it" warning) and your join link. Copy the join link, open it in a *second* browser, join as "Priya", mark a milestone complete → back in the first browser, open your dashboard: Priya is there and her progress moves within ~2 s. Confirm you have the full toolset — send a broadcast, pause, advance, open the audit tab, export CSV — nothing is locked. Return to **http://localhost:8001/** in the first browser: **Your workshops** now lists it with working quick links. Finally open **http://localhost:8001/admin**, enter your `WORKSHOP0_ADMIN_KEY`, and see that same workshop in the full list with a **Public** badge and the email you typed. You never entered an access key at any point before that. **Nothing on this phase is a stub** — every surface it adds is real.

---

## Phase 7 — Workshop0 runs on Cloud Run + Cloud SQL (fresh database)

> **Status: delivered; merged via PR into `feature/v0.1`/`main`.** Deployed and drilled on Cloud Run (pipeline, rollback guard, workshop mode). **Snapshot-memo revisit note:** the in-process snapshot memo was removed (stateless instances); the code carries the comment `revisit if load testing shows snapshot build is a bottleneck; key was (workshop_id, state_version)`. `tests/integration/test_poll_burst.py` (300 participants, 300 polls) is the evidence it is not needed at the stated scale; re-introduce a shared (not per-process) cache only if load testing contradicts that. The poll `leaderboard` is the top 15 plus the caller's row (see api.md), not the full list.

**Goal:** The same product, unchanged, runs in production on Cloud Run against the shared Cloud SQL PostgreSQL instance (own database `workshop0`, empty), deployed by a fully automated, keyless GitHub Actions pipeline with a rollback guard. Reachable at the `*.run.app` URL; `workshop0.smalltech.in` and the VM keep serving real traffic untouched.

**Capabilities delivered:** Stateless multi-instance serving (PostgreSQL storage, memo dropped, DB-side `last_seen_at` throttle) · PostgreSQL parity for tests and migrations (Rule 5) · Cloud Run + Cloud SQL deploy pipeline (idempotent provisioning, WIF, migrate job, no-traffic revision, health-checked traffic shift, rollback) · Workshop mode (`min-instances` toggle). Architecture in [architecture.md](architecture.md) §Production topology.

**Non-goals:** no data migration (Phase 8), no domain mapping (Phase 8), no VM changes, no behaviour change, no new UI (nothing in this phase is a stub — there is no UI work; the existing UI is exercised by the existing e2e suite).

**Spec-level behaviour changes (implement exactly):**
1. `services/snapshots.py`: delete `_cache`, `_memoized`, `clear_snapshot_cache`, `SNAPSHOT_TTL_SECONDS`, `_monotonic`; `participant_shared_snapshot` / `dashboard_snapshot` call their builders directly. Leave a comment at the removal site containing the literal sentence: `revisit if load testing shows snapshot build is a bottleneck; key was (workshop_id, state_version)`. `bump_*_version` and the `v == state_version → {"changed": false}` fast path are untouched.
2. `api/participant.py::_touch_last_seen(session, participant_id)` becomes one Core statement: `UPDATE participant SET last_seen_at=:now WHERE id=:id AND last_seen_at < :now - LAST_SEEN_TOUCH_SECONDS` (`now` = app UTC clock, bound as a parameter so it is portable to SQLite). No read-then-write.
3. `db/session.py`: PostgreSQL engine with `pool_size/max_overflow` from `WORKSHOP0_DB_POOL_SIZE` (3) / `WORKSHOP0_DB_MAX_OVERFLOW` (2), `pool_timeout=10`, `pool_recycle=1800`, `pool_pre_ping=True`; SQLite branch unchanged. `settings.py` normalises `postgres://`/`postgresql://` → `postgresql+psycopg://` and adds the two pool settings. `psycopg[binary]>=3.2` added to `pyproject.toml` and `uv.lock`.
4. `src/__main__.py`: `uvicorn.run(..., proxy_headers=True, forwarded_allow_ips="*")`; `observability/logging.py`: add a `severity` key (mapped from level) to every JSON line.
5. `deploy/entrypoint.sh`: `migrate` subcommand; boot-time `alembic upgrade head` only when `WORKSHOP0_MIGRATE_ON_BOOT` is `1`/`true` (default `1`).

**Independent slices** (all fan out concurrently, disjoint exclusive paths; the only true dependency is marked):

| Slice | Owns (exclusive paths) | Delivers |
|---|---|---|
| **S1a db-engine** | `src/workshop0/db/session.py`, `src/workshop0/config/settings.py`, `src/__main__.py`, `src/workshop0/observability/logging.py`, `pyproject.toml`, `uv.lock`, `tests/unit/test_settings.py`, new `tests/unit/test_db_engine.py` | Spec items 3, 4; unit tests for URL normalisation, pool kwargs on PG vs none on SQLite, `severity` key |
| **S1b stateless-serving** | `src/workshop0/services/snapshots.py`, `src/workshop0/api/participant.py`, `tests/unit/test_snapshot_helpers.py`, `tests/unit/test_last_seen_throttle.py`, `tests/integration/test_dashboard_details.py` | Spec items 1, 2; tests rewritten without the cache/clock hooks: two consecutive snapshot builds both see a data change made without a version bump; throttle: poll with `last_seen_at` 30 s old → row unchanged, 90 s old → advanced, two instances' sessions polling at once → exactly one effective update |
| **S1c postgres-test-harness** | `tests/conftest.py`, `alembic/**`, `tests/integration/test_migration.py`, `tests/integration/test_restart_survival.py`, `tests/integration/test_public_creation.py`, `tests/integration/test_intelligence_fixture.py`, `.github/workflows/ci.yml` | `conftest.py`: requires `TEST_DATABASE_URL` (clear error pointing at the README if unset; **refuses any database whose name does not end in `_test`**; no SQLite fallback); session-scoped fixture drops/recreates schema `public` and runs `alembic upgrade head`; per-test autouse `TRUNCATE … RESTART IDENTITY CASCADE` over all app tables; no `clear_snapshot_cache` call. `test_migration.py` runs the same assertions on a scratch database it creates/drops (`<name>_mig_<uuid>`), plus PostgreSQL-specific: `alembic upgrade head` twice is a no-op, `downgrade base` then `upgrade head` round-trips. Other listed tests: replace SQLite-file URLs with `TEST_DATABASE_URL`. `alembic/env.py`/versions fixed if any migration fails on PostgreSQL. `ci.yml`: `postgres:17` service container + `TEST_DATABASE_URL` + e2e job on Postgres (architecture.md §Deploy shape); add `feature/cloud-run-v0.1` to the push branches |
| **S1d postgres-parity-fixes** *(serialized: starts after S1a + S1c land; needs a runnable PG suite)* | `src/workshop0/api/**` **except** `participant.py`, `src/workshop0/services/**` **except** `snapshots.py`, `src/workshop0/db/models.py` | Fix every app defect the PostgreSQL suite exposes (ordering, case-sensitivity, GROUP BY strictness, aware/naive datetimes, boolean/int coercion). Tests are never weakened to pass |
| **S2a provisioning** | `deploy/cloudrun/provision.sh`, `deploy/cloudrun/dbinit.py` | Idempotent (check-then-create) `provision.sh` for, in order: required APIs (`run`, `artifactregistry`, `secretmanager`, `sqladmin`, `iamcredentials`) · Artifact Registry repo `workshop0` · SAs `workshop0-run`, `workshop0-deployer` · WIF provider `workshop0-github` (+ attribute condition) and `workloadIdentityUser` binding · DB `workshop0` + user `workshop0_app` · secrets `workshop0-database-url`, `workshop0-openrouter-api-key`, `workshop0-admin-key` (stdin only; values from the operator's exported `WORKSHOP0_ADMIN_KEY` / `OPENROUTER_API_KEY`, else read from `.env` without echoing; an existing secret is never overwritten unless `--rotate <name>`) · per-secret IAM · dbinit job (schema privilege probe + grant, see architecture.md) · placeholder Cloud Run service `workshop0` created if absent (image `us-docker.pkg.dev/cloudrun/container/hello`, runtime SA `workshop0-run`, min 0 / max 3; an existing service is never modified) · public invoker IAM binding (`allUsers` → `roles/run.invoker` on service `workshop0`) applied by `provision.sh` itself, guarded by an "already bound" check; the **workflow never passes `--allow-unauthenticated`** (the deployer has only `run.developer`, no setIamPolicy) and always takes the no-traffic candidate path (if an org policy blocks `allUsers`, provisioning fails loudly with that cause). Every created thing prints `CREATED <what>`; every pre-existing thing prints `EXISTS <what>`; exit non-zero on any failure; `--dry-run` prints what it would do. Never reads or modifies resources not prefixed/owned `workshop0`. Workshop mode is a plain `gcloud run services update --min-instances=N` (traffic routes to LATEST) |
| **S2b image** | `deploy/Dockerfile`, `deploy/entrypoint.sh`, `deploy/docker-compose.yml` | Spec item 5; Dockerfile copies `deploy/cloudrun/dbinit.py`; image works for both compose and Cloud Run (listens on `$PORT`). `docker-compose.yml` is today the *Caddy production* compose (requires `WORKSHOP0_DOMAIN`/`ACME_EMAIL`): it is rewritten here to the **local-dev** shape — `app` service only, no Caddy service/volumes, no `WORKSHOP0_DOMAIN`/`ACME_EMAIL` requirement, `WORKSHOP0_BASE_URL` optional, SQLite volume, `WORKSHOP0_MIGRATE_ON_BOOT=1`, port `8001:8001` published. (The separate `docker-compose.prod.yml` + `Caddyfile` used by the VM workflow were left untouched in Phase 7 and deleted in Phase 8.) |
| **S2c workflows** | `.github/workflows/deploy-cloudrun.yml`, `.github/workflows/deploy.yml` | New workflow (below). `deploy.yml` (VM) triggers reduced to `workflow_dispatch` only (so a push to `main` deploys **only** Cloud Run; the VM path was manual-only until Phase 8 deleted it) |
| **S2d docs-env** | `README.md`, `.env.example`, `deploy/RUNBOOK.md` | README: Postgres test setup (`brew install postgresql@17`, `createdb workshop0_test`, `TEST_DATABASE_URL`), every command `uv run`-prefixed with explicit working directory, "Deploying to Cloud Run" + workshop-mode (`gcloud run services update --min-instances`) one-liners; `.env.example` gains `TEST_DATABASE_URL`, `WORKSHOP0_DB_POOL_SIZE`, `WORKSHOP0_DB_MAX_OVERFLOW`, `WORKSHOP0_MIGRATE_ON_BOOT`; RUNBOOK gains a top-level "Cloud Run (current production path from Phase 7)" section pointing at provision/deploy/workshop mode (full rewrite is Phase 8; VM sections stay, marked legacy) |

**`deploy-cloudrun.yml` contract (S2c):** name `Deploy (Cloud Run)`; triggers `push: branches: [main, feature/cloud-run-v0.1]` (the feature branch was a Phase-7-only trigger so the real deploy could be gated before merge; Phase 8 removed it; `workflow_dispatch` stays so any branch ref can still be deployed by hand) and `workflow_dispatch` with inputs `min_instances` (choice `""`/`0`/`1`, default unchanged) and `drill_rollback` (boolean, default false); `permissions: {contents: read, id-token: write}`; `concurrency: {group: deploy-cloudrun, cancel-in-progress: false}`; env `PROJECT_ID=ai-agent-boilerplate0`, `REGION=us-central1`, `SERVICE=workshop0`. Jobs in order: **test** (Postgres service container, `uv run pytest tests/unit tests/integration -q`) → **deploy** (`google-github-actions/auth@v2` with the WIF provider `projects/870371939888/locations/global/workloadIdentityPools/github/providers/workshop0-github` + SA `workshop0-deployer@ai-agent-boilerplate0.iam.gserviceaccount.com`; `setup-gcloud`; `gcloud auth configure-docker us-central1-docker.pkg.dev`; docker buildx build+push `…/workshop0/workshop0:${GITHUB_SHA::12}`; capture `PREV` revision; deploy/update job `workshop0-migrate`; `gcloud run jobs execute workshop0-migrate --wait`; `gcloud run deploy workshop0 --no-traffic --tag candidate --revision-suffix sha-${GITHUB_SHA::12}` with the sizing, VPC and `--set-secrets` flags from architecture.md and env `WORKSHOP0_MIGRATE_ON_BOOT=0`; health-check candidate URL (path `/api/health`, or `/api/health-drill-404` when `drill_rollback`); shift traffic; health-check service URL; `if: failure()` step restores `PREV=100` and removes the `candidate` tag). No stored GCP keys anywhere; no secret values in logs. The real-key tests in the `test` job are skipped when their secrets are absent (guarded), PostgreSQL ones never are.

**Key surfaces/files:** listed per slice above.

**Gate (exact commands; from repo root; operator is `gcloud`- and `gh`-authenticated; `.env` holds `WORKSHOP0_ADMIN_KEY` and `OPENROUTER_API_KEY`; never echo them):**

```bash
# --- one-time local prerequisite (PostgreSQL 17, harness Rule 5) ---
brew install postgresql@17 && brew services start postgresql@17
createdb workshop0_test
export TEST_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/workshop0_test"

# --- backend on PostgreSQL ---
uv sync
uv run python -c "import psycopg"
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic current      # MUST print a revision hash (head) — blank = failed
uv run pytest tests/unit tests/integration -q                  # whole suite, on PostgreSQL, zero failures, no test weakened
! grep -nE '_memoized|clear_snapshot_cache|SNAPSHOT_TTL_SECONDS|_cache:' src/workshop0/services/snapshots.py
grep -q 'revisit if load testing shows snapshot build is a bottleneck; key was (workshop_id, state_version)' src/workshop0/services/snapshots.py
! git grep -nE 'workshop0_app:[A-Za-z0-9]{16,}@'                # no committed credentials

# --- frontend + e2e locally on PostgreSQL ---
(cd frontend && pnpm install && pnpm build) && pnpm install && pnpm exec playwright install chromium
DATABASE_URL="$TEST_DATABASE_URL" uv run python -m src &
sleep 3 && pnpm exec playwright test tests/e2e --reporter=line ; kill %1

# --- script hygiene ---
bash -n deploy/cloudrun/provision.sh  && (command -v shellcheck >/dev/null && shellcheck deploy/cloudrun/*.sh || true)
docker compose -f deploy/docker-compose.yml config -q          # local compose is valid with no WORKSHOP0_DOMAIN/ACME_EMAIL set
! grep -qi caddy deploy/docker-compose.yml

# --- real provisioning, twice (idempotency proof) ---
bash deploy/cloudrun/provision.sh                              # first run creates; may prompt once (no echo) for the shared instance's postgres password
bash deploy/cloudrun/provision.sh | tee /dev/stderr | grep -c '^CREATED' | grep -qx 0   # second run creates nothing

# --- real deploy through the pipeline ---
git push origin HEAD
gh workflow run deploy-cloudrun.yml --ref feature/cloud-run-v0.1
sleep 10; RUN=$(gh run list --workflow=deploy-cloudrun.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN" --exit-status
URL=$(gcloud run services describe workshop0 --region us-central1 --project ai-agent-boilerplate0 --format='value(status.url)')
curl -fsS "$URL/api/health" | grep -q '"db":"ok"'              # proves VPC egress + TLS + secrets + migrations
set -a; . ./.env; set +a                                       # WORKSHOP0_ADMIN_KEY only needs to equal the value provisioned into workshop0-admin-key
BASE_URL="$URL" pnpm exec playwright test tests/e2e --reporter=line   # full e2e journey against the REAL deployment

# --- rollback-guard drill: a failing candidate must leave the old revision serving ---
PREV=$(gcloud run services describe workshop0 --region us-central1 --project ai-agent-boilerplate0 --format='value(status.traffic[0].revisionName)')
gh workflow run deploy-cloudrun.yml --ref feature/cloud-run-v0.1 -f drill_rollback=true
sleep 10; RUN=$(gh run list --workflow=deploy-cloudrun.yml --limit 1 --json databaseId -q '.[0].databaseId')
! gh run watch "$RUN" --exit-status                            # run MUST fail
test "$(gcloud run services describe workshop0 --region us-central1 --project ai-agent-boilerplate0 --format='value(status.traffic[0].revisionName)')" = "$PREV"
curl -fsS "$URL/api/health" | grep -q '"db":"ok"'              # old revision still serves

# --- workshop mode ---
# traffic routes to LATEST, so a plain update serves immediately (verified live 2026-10-29)
gcloud run services update workshop0 --region us-central1 --project ai-agent-boilerplate0 --min-instances=1 --quiet
test "$(gcloud run services describe workshop0 --region us-central1 --project ai-agent-boilerplate0 --format='value(spec.template.metadata.annotations."autoscaling.knative.dev/minScale")')" = 1
gcloud run services update workshop0 --region us-central1 --project ai-agent-boilerplate0 --min-instances=0 --quiet

# --- VM path must not deploy on push ---
! grep -nE '^\s*push:' .github/workflows/deploy.yml
```

**Gate conditions beyond the commands:** the PostgreSQL suite must include (and S1b/S1c must have written) — the throttle test with 30 s/90 s fixtures and a concurrent double-poll proving a single effective update; snapshot freshness without a version bump; `alembic upgrade head` idempotency and downgrade round-trip on PostgreSQL; a poll-burst integration test (≥ 300 participants seeded, 300 sequential state polls after one completion, all payloads identical in `leaderboard` and `version`, proving the memo-free path is correct at the stated scale — the fixture is large enough that a truncated/sampled leaderboard would be observably different). The e2e journey against the real deployment is the Rule-6 golden path and asserts rendered content.

**How the user tests it:** open the `*.run.app` URL the workflow prints (or `gcloud run services describe workshop0 --region us-central1 --project ai-agent-boilerplate0 --format='value(status.url)'`). The very first load after idle may take a few seconds (cold start, `min-instances=0`) — expected, not a bug. Then the normal loop: landing page → **Create your workshop** → 3 milestones → copy the join link → join as "Priya" in a private window → complete a milestone → dashboard moves within ~2 s → help request → answer → join link and personal link shown are `https://…run.app/…` (not `http://`, not `localhost`). Reload and open the personal link in another browser: same state. Open `/admin` with your admin key: the workshop is listed. Stop and re-open the page after a few minutes idle to see scale-to-zero recover with all data intact (it is in Cloud SQL). `workshop0.smalltech.in` still shows the old VM — that is intentional until Phase 8. **Labelled stubs: none** (no UI changes this phase). Data created here is throw-away: Phase 8 replaces it.

---

## Phase 8 — Cutover: data import, `workshop0.smalltech.in`, retire the VM path

**Goal:** Production traffic and data move from the VM to Cloud Run: the VM's SQLite data is imported into Cloud SQL with verified counts, `workshop0.smalltech.in` serves from Cloud Run, the Caddy/VM deploy path is removed from the repo, and docs describe the new reality. The VM itself is left running and untouched until the user decommissions it.

**Capabilities delivered:** SQLite → PostgreSQL data import with per-table verification and sequence reset · Domain mapping with exact DNS instructions (human gate) · VM deploy path retirement + rewritten RUNBOOK/README + rollback plan.

**Independent slices (all concurrent; disjoint paths; the only coupling is at gate time, marked):**

| Slice | Owns (exclusive paths) | Delivers |
|---|---|---|
| **S1 import-script** | `scripts/sqlite_to_postgres.py`, `scripts/make_import_fixture.py`, `tests/integration/test_sqlite_to_postgres.py` | CLI `uv run python scripts/sqlite_to_postgres.py --sqlite PATH [--target-url URL \| env TARGET_DATABASE_URL] [--replace] [--batch-size 500]`. Behaviour: opens the source **read-only** (`file:PATH?mode=ro`, `uri=True`); aborts unless the source's `alembic_version` equals the target's (print how to upgrade the scratch copy); aborts if the target has rows in any app table unless `--replace` (which prints per-table counts it will delete, then `TRUNCATE … RESTART IDENTITY CASCADE`); copies every app table in FK order (`Base.metadata.sorted_tables`) in batches, naive SQLite datetimes interpreted as UTC, ints → bool; in **one transaction** (all-or-nothing); then resets each serial/identity sequence to `max(id)` (`setval(pg_get_serial_sequence(t,'id'), COALESCE(max(id),1), max(id) IS NOT NULL)`); then verifies per-table `COUNT(*)` source vs target and FK orphan checks, prints a table, exits non-zero on any mismatch (and rolls back). Never prints row data (PII). `make_import_fixture.py --out PATH` builds a SQLite DB through the real app: 3 workshops, **≥ 300 participants** in one, ≥ 900 completions, help requests with answers, broadcasts, audit rows — more rows than one batch, so batching/ordering bugs change the counts. Tests (PostgreSQL via `TEST_DATABASE_URL`): counts equal per table; a spot-checked workshop's leaderboard payload from the API over the imported DB equals the same payload over the SQLite source; a fresh insert after import gets an id greater than the max imported id (sequence reset proof); non-empty target without `--replace` aborts and changes nothing; mismatching alembic revision aborts; forced mid-copy failure leaves the target empty (atomicity) |
| **S2 import-tooling** | `deploy/cloudrun/import-data.sh`, `deploy/Dockerfile` | Dockerfile adds `COPY scripts/ ./scripts/`. `import-data.sh --sqlite PATH [--db workshop0] [--replace] [--drop-after]`: (1) creates a temporary private GCS bucket `ai-agent-boilerplate0-workshop0-import-<rand>` (uniform access, deleted on exit via trap) and uploads the SQLite file; (2) creates/updates Cloud Run Job `workshop0-import` from the **currently deployed image** with VPC egress, runtime SA `workshop0-run` (granted `objectViewer` on that bucket only, revoked with the bucket), the bucket mounted read-only at `/import` (`--add-volume type=cloud-storage`), `DATABASE_URL` from `workshop0-database-url` with the database name swapped when `--db` ≠ `workshop0` (for scratch DBs, which the script creates through `workshop0_app` and `--drop-after` removes), command `scripts/sqlite_to_postgres.py --sqlite /import/<file>` (+ `--replace`); (3) executes with `--wait`, streams the verification table from the job logs, exits non-zero on failure; (4) deletes bucket + job. **Historical, removed in Phase 9:** Phase 8 originally also shipped `--pull-from-vm` / `--pull-to` (a read-only online SQLite backup of the legacy VM copied down via `gcloud compute ssh/scp`). The VM is deleted, so the script now accepts **only `--sqlite PATH`** (plus `--db`, `--replace`, `--drop-after`); do not re-add VM pulling |
| **S3 domain-mapping** | `deploy/cloudrun/domain-map.sh` | `domain-map.sh [--wait]`: checks `gcloud domains list-user-verified` includes `smalltech.in` (else prints the Search Console TXT verification step and exits 2); creates the mapping if absent (`gcloud beta run domain-mappings create --service workshop0 --domain workshop0.smalltech.in --region us-central1`); prints the DNS records exactly as returned by `domain-mappings describe` (`resourceRecords`); `--wait` polls (10 s, 90 min cap) until `Ready=True`/`CertificateProvisioned=True`, then `curl -fsS https://workshop0.smalltech.in/api/health` |
| **S4 retire-vm-path** | `deploy/docker-compose.prod.yml` (delete), `deploy/Caddyfile` (delete), `.github/workflows/deploy.yml` (delete), `.github/workflows/deploy-cloudrun.yml` | Orchestrator first tags the commit `vm-deploy-final` (so the VM path stays recoverable from git). `deploy-cloudrun.yml`: remove the `feature/cloud-run-v0.1` push trigger (**`workflow_dispatch` is kept**, so `gh workflow run deploy-cloudrun.yml --ref <branch>` still deploys a branch); pass `WORKSHOP0_BASE_URL=${{ vars.WORKSHOP0_BASE_URL }}` (GitHub repository *variable*; passed to the service deploy **only when non-empty**, otherwise links derive from the request) — a variable rather than a hard-coded value so share links never point at `workshop0.smalltech.in` before the DNS flip; the user sets it in cutover step 5 |
| **S5 docs** | `README.md`, `deploy/RUNBOOK.md`, `.env.example` | RUNBOOK rewritten end-to-end for Cloud Run: topology diagram, `provision.sh`, the pipeline, **workshop mode** (before/after one-liners using `gcloud run services update --min-instances`, and the advice to run `on` at least 10 minutes before a workshop and rehearse with the actual participant count), cold-start expectation, logs (`gcloud run services logs read workshop0 …`), DB backup (`gcloud sql export sql …`), connection-budget rule (never raise `max-instances` without recomputing), cutover procedure (below), rollback plan, VM decommission checklist (user-owned: snapshot the disk, then delete VM + static IP). README: Cloud Run production section; compose documented as local-only; all commands `uv run`-prefixed with explicit working directories; no mention of Caddy/GHCR as the production path |

**Cutover procedure (documented in RUNBOOK; the human gate):**

1. *Day before:* in GoDaddy note that the host is `workshop0.smalltech.in` (the user created `CNAME workshop0 -> ghs.googlehosted.com`, TTL 600, directly; the old `workshops` A record is gone). Choose a window with **no live workshop** (the DNS flip and certificate issuance cause a short HTTPS gap, up to ~30–60 min, and writes landing on the VM after the final import are not carried over).
2. *(Historical: executed 2026-10 as `import-data.sh --pull-from-vm --replace`; that flag was removed in Phase 9 after the VM was deleted.)* Current form: `bash deploy/cloudrun/import-data.sh --sqlite PATH --replace` with a local SQLite copy — imports into Cloud SQL (wiping existing data), prints the verification table; every row must say `OK`.
3. `bash deploy/cloudrun/domain-map.sh` — creates the mapping and prints the records to set.
4. **GoDaddy DNS for `smalltech.in` (manual):** ensure **`CNAME` · Host `workshop0` · Points to `ghs.googlehosted.com` · TTL 600** exists (already created by the user; delete any `A`/`AAAA` for `workshop0`, which a CNAME cannot coexist with). If `domain-map.sh` reports the domain is unverified, first add the `TXT` record at host `@` that it prints (`google-site-verification=…`) and re-run it. If `domain-mappings describe` ever shows different `resourceRecords`, those win.
5. `bash deploy/cloudrun/domain-map.sh --wait` until the certificate is provisioned and the HTTPS health check passes. Then `gh variable set WORKSHOP0_BASE_URL --body https://workshop0.smalltech.in` and `gh workflow run deploy-cloudrun.yml --ref main` (merge the PR first) so share links use the pretty domain.
6. Smoke on the real domain (user test below). (Phase 9 later renamed all Cloud Run resources.)
7. **Done 2026-10-29:** the legacy VM, its disk and the static IP were deleted after a verified backup of its SQLite database; `DEPLOY_*` secrets removed. Rollback of a bad release is Cloud Run revision rollback; data recovery is Cloud SQL export/restore (RUNBOOK).

**Gate (exact commands; repo root; `TEST_DATABASE_URL` as in Phase 7; operator authenticated to `gcloud`/`gh`; the Phase-7 pipeline has deployed the Phase-8 branch so the image contains `scripts/`):**

```bash
uv sync
uv run pytest tests/unit tests/integration -q                                  # whole suite incl. test_sqlite_to_postgres.py, on PostgreSQL
bash -n deploy/cloudrun/import-data.sh && bash -n deploy/cloudrun/domain-map.sh && (command -v shellcheck >/dev/null && shellcheck deploy/cloudrun/*.sh || true)
test ! -e deploy/Caddyfile && test ! -e deploy/docker-compose.prod.yml && test ! -e .github/workflows/deploy.yml
! grep -rnIiE 'ghcr\.io|appleboy|caddy' README.md deploy .github .env.example | grep -v 'COPY --from=ghcr.io/astral-sh/uv'   # the uv build-stage image is the only permitted ghcr reference
grep -q 'ghs.googlehosted.com' deploy/RUNBOOK.md && grep -q 'min-instances' deploy/RUNBOOK.md
! grep -n 'feature/cloud-run-v0.1' .github/workflows/deploy-cloudrun.yml
git ls-files | grep -qx 'deploy/docker-compose.yml'                            # local compose is kept
docker compose -f deploy/docker-compose.yml config -q
# deploy the Phase-8 branch so the image contains scripts/ (Phase 7 is merged, so dispatch on a branch ref works)
git push origin HEAD && gh workflow run deploy-cloudrun.yml --ref "$(git rev-parse --abbrev-ref HEAD)"
sleep 10; RUN=$(gh run list --workflow=deploy-cloudrun.yml --limit 1 --json databaseId -q '.[0].databaseId'); gh run watch "$RUN" --exit-status
# real end-to-end rehearsal of the import path on a SCRATCH database (never touches `workshop0`):
SCRATCH=$(mktemp -d) && uv run python scripts/make_import_fixture.py --out "$SCRATCH/fixture.db"
bash deploy/cloudrun/import-data.sh --sqlite "$SCRATCH/fixture.db" --db workshop0_import_check --drop-after   # must print all tables OK and exit 0
```

(After the automated gate passes, the user runs the cutover procedure above; the phase is accepted only on the user's "Yes" after the smoke test.)

**How the user tests it:** follow the cutover procedure in `deploy/RUNBOOK.md`. After DNS settles, open **https://workshop0.smalltech.in/** in a private window: the landing page loads over HTTPS from Cloud Run (response header `server: Google Frontend`; `curl -sI https://workshop0.smalltech.in/ | grep -i '^server: Google Frontend'`). Open `/admin` with your admin key: **every workshop that existed on the VM is listed with the same names, statuses and participant counts** you noted before the cutover (the import's verification table printed the same numbers). Open an old facilitator link (`/f/<admin_token>`) and an old personal participant link (`/p/<token>`) saved from before: both open with identical state — tokens survive the migration. Create a new workshop, join it from a second browser, complete a milestone: the dashboard updates within ~2 s and the links shown start with `https://workshop0.smalltech.in/`. Before a real workshop run `gcloud run services update workshop0 --region us-central1 --min-instances=1`; afterwards `--min-instances=0`. **Nothing is a stub.** Rollback of a bad release is a Cloud Run revision rollback (RUNBOOK).

---

## Phase 9 — Rename to Workshop0

> **Naming decision (user, explicit):** "Drop the old naming everywhere" — the user-visible brand, the code, the environment variables, every cloud resource and the GitHub repository all become **Workshop0**. The single source of truth for every new name is the table in [architecture.md](architecture.md) §Naming (Workshop0). This spec, `CLAUDE.md` and the `harness/` markdown were already rewritten by the spec step; the slices below bring the code, UI, infra scripts and remaining docs into line. To keep this file itself free of the legacy name, the legacy identifiers are referred to here as "legacy-named"/"the legacy prefix"; gates build the literal at run time (`LEGACY`).

**Goal:** One coherent identity. After this phase nothing a user, operator or developer sees is called by the old name, the product behaves exactly as before (same data, same tokens, same links, same admin key, same domain), and live participants and facilitators are not logged out by the change.

**Capabilities delivered (3):**

1. **C-R1 Code & configuration rename** — Python package `src/workshop0` (imports `src.workshop0.*`), project/entrypoint names, env prefix `WORKSHOP0_*` for every setting, logger names, default SQLite file `data/workshop0.db`, error/log/email strings, CSV/export filenames, cookie name `workshop0_p_{workshop_id}`.
2. **C-R2 Brand & client-storage migration** — every UI string, title, landing copy, footer and GitHub link (`https://github.com/smallTechOrg/workshop0`) says Workshop0 (bare "Workshop" brand mentions excepted where they already mean a workshop event); `localStorage` keys `workshop0_admin_key` and `workshop0_my_workshops`, with a **one-release read fallback** to the legacy keys so nobody is logged out.
3. **C-R3 Infra, delivery & docs rename** — Cloud Run service/jobs, Artifact Registry, service accounts, secrets, Cloud SQL database + user, WIF provider, GitHub Actions variable, repo name, Docker/compose/scripts/workflows, README/RUNBOOK/skill docs; a zero-data-loss cutover (below).

**Invariants (must not change):** DB table and column names (none contain the legacy name); all stored tokens (`admin_token`, `join_slug`, `participant_token`) and their derivation — links, personal links and facilitator links minted before the rename keep working; the admin key value; the public domain `workshop0.smalltech.in`; the API contract (paths, shapes, error codes); the DB schema/migrations. Git history and tag `vm-deploy-final` are not rewritten. The Cloud SQL instance `ai-agent-db` is shared and untouched except for adding database `workshop0` and user `workshop0_app` and (after verification) dropping the legacy ones.

**Compatibility shims (the only places the legacy literal may survive in code):**
- Frontend: reading the legacy `localStorage` keys. **Migrate-on-read:** `get(newKey)`; if absent, `get(legacyKey)`; if found, write it under `newKey` and return it. The legacy key is **never deleted** in this release (a later release removes the shim).
- Backend: the participant cookie. Reads `workshop0_p_{id}`; if absent, reads the legacy-named cookie for the same workshop (same token value); a successful resolve re-sets the cookie under the new name. 30-day cookies therefore keep auto-resume working across the deploy. Writes only ever use the new name.
- Every line carrying a legacy literal for these shims (constant definition, test seed, assertion) ends with the marker comment `LEGACY-COMPAT` so the gate can allow-list them mechanically; no other legacy literal may exist.

> **Assumed:** renaming the cookie (its *name* contains the legacy word) is in scope with a server-side read fallback, since leaving it would violate "drop the old naming everywhere" and a hard rename would silently drop auto-resume for live participants (their personal link would still work).
> **Assumed:** the local default SQLite file moves to `data/workshop0.db` with no automatic fallback; a developer upgrading a checkout moves their existing local file (README says so without naming the old file). Production is PostgreSQL and unaffected.
> **Assumed:** root-level `synthesis_brief*.md` are historical notes owned by S3 and are rewritten like any other doc.

**Independent slices (all three fan out concurrently; disjoint exclusive paths; no build dependencies — the naming table is the only shared contract):**

| Slice | Owns (exclusive paths) | Delivers |
|---|---|---|
| **S1 backend** | `src/**` (the legacy-named package dir is renamed to `src/workshop0`; `src/__main__.py`), `pyproject.toml`, `uv.lock`, `alembic/**`, `alembic.ini`, `scripts/**`, `tests/conftest.py`, `tests/unit/**`, `tests/integration/**` | Package rename and every import (`src.workshop0.*`); `pyproject.toml` project name `workshop0` + entrypoints; `uv.lock` regenerated; alembic env/ini; scripts; env prefix `WORKSHOP0_*` in `config/settings.py` (**no dual-read of the legacy prefix** — deployment env is set explicitly by the pipeline/compose); logger names; default `sqlite:///data/workshop0.db`; error-message strings, CSV/export filenames, email text; cookie rename + read fallback; test DB defaults/docs (`workshop0_test`); unit/integration tests renamed and extended with: settings read `WORKSHOP0_*` and ignore the legacy prefix, cookie fallback resolves a legacy-named cookie and re-sets the new one, CSV `Content-Disposition` uses the new name, no `src/` file or logger name contains the legacy word apart from `LEGACY-COMPAT` lines |
| **S2 frontend + e2e** | `frontend/**`, `tests/e2e/**`, `playwright.config.ts`, `package.json` (root), `pnpm-lock.yaml` (root) | All UI strings, `<title>`/metadata, landing, footer, GitHub link; `frontend/package.json` name; `lib/localWorkshops.ts` and the admin-key helper use `workshop0_admin_key` / `workshop0_my_workshops` with migrate-on-read fallback; e2e specs/helpers use `WORKSHOP0_ADMIN_KEY` and new strings; **new Playwright spec `storage-migration.spec.ts`**: seed only the legacy keys (marker `LEGACY-COMPAT`) → open Admin Home / landing "Your workshops" → still logged in / list present → assert the new keys now exist and the legacy keys are still there |
| **S3 deploy / IaC / docs** | `deploy/**`, `.github/**`, `.env.example`, `README.md`, `synthesis_brief*.md`, `harness/skills/**` (directory renamed `workshop-<legacy>` → `harness/skills/workshop0`; its contents were already updated by the spec step), verification of `CLAUDE.md` and `harness/**/*.md` | `deploy/Dockerfile`, `entrypoint.sh` (`WORKSHOP0_MIGRATE_ON_BOOT`), `docker-compose.yml`, `deploy/cloudrun/{provision.sh,dbinit.py,import-data.sh,domain-map.sh}` using exactly the names in the table (incl. `--service workshop0`, image `…/workshop0/workshop0:<sha12>`); `provision.sh` creates the WIF provider `workshop0-github` in the existing pool `github` with attribute condition for repo `smallTechOrg/workshop0` and the `workloadIdentityUser` binding for `workshop0-deployer`; `.github/workflows/*` (`SERVICE=workshop0`, provider path ending `providers/workshop0-github`, SA `workshop0-deployer@ai-agent-boilerplate0.iam.gserviceaccount.com`, variable `WORKSHOP0_BASE_URL`, `WORKSHOP0_MIGRATE_ON_BOOT=0`, job `workshop0-migrate`, CI test DB `workshop0_test`); `.env.example`; README; `deploy/RUNBOOK.md` rewritten with the new names, the Phase-9 cutover procedure as an appendix, and **exactly one** historical note: "Workshop0 was previously called Workshop <legacy name>" (the RUNBOOK may also keep the operator's local backup directory path under its original name, since it lives outside the repo; nothing else may carry the legacy name) |

> **Assumed:** CLAUDE.md and the `harness/**/*.md` files are rewritten by the spec step (this step), not by a generator; S3 only verifies them with the gate and renames the skill directory with `git mv`.

**Key surfaces/files:** S1: `src/workshop0/{api,services,db,config,observability,ai}/**`, `src/workshop0/security.py`, `alembic/env.py`, `pyproject.toml`. S2: `frontend/app/{layout,page,admin/page,create/page}.tsx`, `frontend/components/**`, `frontend/lib/{localWorkshops,api}.ts`, `tests/e2e/*.spec.ts`. S3: `deploy/cloudrun/provision.sh`, `.github/workflows/deploy-cloudrun.yml`, `deploy/RUNBOOK.md`.

**Infra cutover (performed by the orchestrator, not a slice; strictly in this order — old service keeps serving until step 9):**

1. **Backup.** Cloud SQL export of the legacy database to a bucket the operator owns, plus a local copy to the operator's existing local backup directory; record baseline numbers from the live service with the count script in the gate (11 workshops / 135 participants / 572 completions) and save one old participant link and one old facilitator link for later checks.
2. **New database + user.** As the instance admin: create user `workshop0_app` (new generated password, stdin only); then in a no-live-workshop window create the database as a copy of the old one, with no downtime for the old service beyond a sub-second reconnect:
   `ALTER DATABASE "$LEGACY" ALLOW_CONNECTIONS false; SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '<legacy db>' AND pid <> pg_backend_pid(); CREATE DATABASE workshop0 TEMPLATE "<legacy db>" OWNER workshop0_app; ALTER DATABASE "<legacy db>" ALLOW_CONNECTIONS true;`
   (`CREATE DATABASE … TEMPLATE` requires zero sessions on the template; the old service's pooled connections reconnect transparently through `pool_pre_ping`.) Then, connected to `workshop0`, re-own every table, sequence and view in schema `public` (including `alembic_version` and the corpus table) to `workshop0_app` with `ALTER … OWNER TO` (a per-object `DO` loop; **not** `REASSIGN OWNED`, which would also touch the old database's objects). The old database and user are untouched.
3. **New secrets** (values via stdin, never argv/logs): `workshop0-database-url` (URL for `workshop0_app` → database `workshop0`), `workshop0-openrouter-api-key` and `workshop0-admin-key` (**copied byte-for-byte from the legacy secrets** so every saved admin key keeps working).
4. **Provision.** `bash deploy/cloudrun/provision.sh` from the Phase-9 branch: creates the repository `workshop0`, SAs, WIF provider `workshop0-github`, dbinit job, placeholder service `workshop0`, invoker binding; prints `EXISTS` for the DB, user and secrets created above; second run prints zero `CREATED`.
5. **New WIF provider BEFORE the repo rename.** Confirm provider `workshop0-github` exists with the new attribute condition, and that the `workloadIdentityUser` binding exists for the `smallTechOrg/workshop0` principal. Only then: `gh repo rename workshop0 --repo smallTechOrg/workshop-<legacy>` (GitHub redirects the old URL; update local `origin`). The legacy provider stops matching after the rename — expected.
6. **Variable + merge.** Leave `WORKSHOP0_BASE_URL` unset until step 9 (share links must not point at the domain before it moves) and delete the legacy-named variable. Merge the Phase-9 PR to `main`; the push triggers `deploy-cloudrun.yml`, which deploys the **new service `workshop0`** (image in the new repository, migrate job `workshop0-migrate` → no-op on the copied schema, no-traffic candidate, health check, shift). The old service is still bound to the domain and keeps serving.
7. **Verify the new service** at its own `*.run.app` URL with the full gate below (health, counts, old participant link, admin key, e2e, rollback drill, `--min-instances`).
8. **Move the domain mapping.** Delete the mapping for the old service, create it for `workshop0` (`bash deploy/cloudrun/domain-map.sh --wait`; DNS CNAME to `ghs.googlehosted.com` is unchanged). Expect a short HTTPS gap (minutes; up to ~30–60 min if the certificate re-provisions) — do it in a window with no live workshop.
9. **Pretty links.** `gh variable set WORKSHOP0_BASE_URL --body https://workshop0.smalltech.in` and `gh workflow run deploy-cloudrun.yml --ref main`; re-run the domain checks.
10. **Delete old resources** only after step 9 verifies and the user says "Yes": legacy Cloud Run service and jobs (`-migrate`, `-dbinit`), Artifact Registry repository, SAs, secrets, WIF provider, then `DROP DATABASE` and `DROP ROLE` for the legacy database/user on `ai-agent-db`. A rollback before this step is simply "re-map the domain to the legacy service".

**Gate (exact commands; repo root; `TEST_DATABASE_URL` points at a PostgreSQL database named `workshop0_test` — `createdb workshop0_test`, `export TEST_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/workshop0_test"`; `.env` holds `WORKSHOP0_ADMIN_KEY` and `OPENROUTER_API_KEY`; never echo them):**

```bash
# --- naming allow-list (the legacy literal is built at run time so this spec stays clean) ---
LEGACY="$(printf '%s%s' helms man)"; LEGACY_CAP="$(printf '%s%s' Helms man)"
! git ls-files | grep -i "$LEGACY"                                   # no file or directory is still named with it
# allow-list: (a) lines marked LEGACY-COMPAT; (b) exactly two non-code lines in deploy/RUNBOOK.md, matched by path + pattern:
#   the single "previously called ..." sentence and the local backup path "~/Backups/<legacy>/" (outside the repo)
! git grep -inI "$LEGACY" | grep -v 'LEGACY-COMPAT' \
    | grep -viE '^deploy/RUNBOOK\.md:[0-9]+:.*(previously called|Backups/)'   # empty output = only allowed hits remain
test "$(git grep -inI "$LEGACY" -- deploy/RUNBOOK.md | wc -l)" -le 2          # RUNBOOK carries at most those two lines
test "$(git grep -ic "previously called Workshop ${LEGACY_CAP}" -- deploy/RUNBOOK.md | cut -d: -f2)" = 1  # exactly one historical note
test "$(git grep -I 'LEGACY-COMPAT' | wc -l)" -le 12                  # shims stay small: ~2 constants + tests per surface
git rev-parse -q --verify refs/tags/vm-deploy-final                   # history/tag untouched

# --- backend on PostgreSQL ---
uv sync
uv run python -c "import src.workshop0; from src.workshop0.config.settings import get_settings"
! test -e src/${LEGACY}
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic current            # MUST print a revision hash — blank = failed
uv run pytest tests/unit tests/integration -q                        # whole suite, PostgreSQL, zero failures, no test weakened

# --- frontend + e2e ---
(cd frontend && pnpm install && pnpm build)
grep -rIq 'smallTechOrg/workshop0' frontend/out                       # footer link rebranded
! grep -rIl "Workshop ${LEGACY_CAP}" frontend/out                     # old brand string gone from the built UI
pnpm install && pnpm exec playwright install chromium
set -a; . ./.env; set +a
DATABASE_URL="$TEST_DATABASE_URL" uv run python -m src &
sleep 3 && pnpm exec playwright test tests/e2e --reporter=line ; kill %1   # includes storage-migration.spec.ts

# --- script/compose hygiene ---
bash -n deploy/cloudrun/provision.sh && bash -n deploy/cloudrun/import-data.sh && bash -n deploy/cloudrun/domain-map.sh && bash -n deploy/entrypoint.sh
(command -v shellcheck >/dev/null && shellcheck deploy/cloudrun/*.sh deploy/entrypoint.sh || true)
docker compose -f deploy/docker-compose.yml config -q
```

**Gate — infrastructure verification (run by the orchestrator after the Phase-9 PR is deployed from `main`; steps 7 and 10):**

```bash
P=ai-agent-boilerplate0; R=us-central1
LEGACY="$(printf '%s%s' helms man)"
URL=$(gcloud run services describe workshop0 --region $R --project $P --format='value(status.url)')

# --- no legacy-named resource remains (run after step 10; each must print 0) ---
gcloud run services list --region $R --project $P --format='value(metadata.name)' | grep -ci "$LEGACY" | grep -qx 0
gcloud run jobs list --region $R --project $P --format='value(metadata.name)' | grep -ci "$LEGACY" | grep -qx 0
gcloud artifacts repositories list --location $R --project $P --format='value(name)' | grep -ci "$LEGACY" | grep -qx 0
gcloud iam service-accounts list --project $P --format='value(email)' | grep -ci "$LEGACY" | grep -qx 0
gcloud secrets list --project $P --format='value(name)' | grep -ci "$LEGACY" | grep -qx 0
gcloud iam workload-identity-pools providers list --workload-identity-pool=github --location=global --project $P --format='value(name)' | grep -ci "$LEGACY" | grep -qx 0
gcloud sql databases list --instance ai-agent-db --project $P --format='value(name)' | grep -ci "$LEGACY" | grep -qx 0
gcloud sql users list --instance ai-agent-db --project $P --format='value(name)' | grep -ci "$LEGACY" | grep -qx 0
gh variable list --repo smallTechOrg/workshop0 | grep -ci "$LEGACY" | grep -qx 0
# new names exist
gcloud iam workload-identity-pools providers describe workshop0-github --workload-identity-pool=github --location=global --project $P --format='value(attributeCondition)' | grep -q 'smallTechOrg/workshop0'
gcloud run jobs describe workshop0-migrate --region $R --project $P --format='value(metadata.name)' | grep -qx workshop0-migrate
gcloud beta run domain-mappings list --region $R --project $P --format='value(metadata.name,spec.routeName)' | grep -q 'workshop0.smalltech.in.*workshop0'

# --- health ---
curl -fsS "$URL/api/health" | grep -q '"db":"ok"'
curl -fsS https://workshop0.smalltech.in/api/health | grep -q '"db":"ok"'          # after step 8

# --- data integrity: 11 workshops / 135 participants / 572 completions, via the admin + dashboard APIs ---
set -a; . ./.env; set +a
BASE="https://workshop0.smalltech.in" uv run python -I - <<'PY'
import json, os, re, urllib.request as u
base = os.environ["BASE"]
def get(path, hdr=None):
    return json.load(u.urlopen(u.Request(base + path, headers=hdr or {})))["data"]
ws = get("/api/admin/workshops", {"X-Admin-Key": os.environ["WORKSHOP0_ADMIN_KEY"]})["workshops"]
participants = sum(w["participant_count"] for w in ws)
completions = 0
for w in ws:
    tok = re.search(r"/f/([^/?#]+)", w["facilitator_url"]).group(1)
    d = get(f"/api/f/{tok}/dashboard?v=0")
    completions += sum(p["completed_count"] for p in d["participants"])
print(len(ws), participants, completions)
assert (len(ws), participants, completions) == (11, 135, 572), "counts differ from baseline"
PY

# --- an old participant link (saved in step 1) still resolves with identical state ---
curl -fsS "https://workshop0.smalltech.in/api/p/$OLD_PARTICIPANT_TOKEN/state?v=0" | grep -q '"changed": *true'
curl -fsS -o /dev/null -w '%{http_code}\n' "https://workshop0.smalltech.in/p/$OLD_PARTICIPANT_TOKEN" | grep -qx '307\|200'

# --- real e2e against the deployed service ---
BASE_URL="$URL" pnpm exec playwright test tests/e2e --reporter=line

# --- deploy from main succeeded through the renamed pipeline ---
gh run list --repo smallTechOrg/workshop0 --workflow=deploy-cloudrun.yml --branch main --limit 1 --json conclusion -q '.[0].conclusion' | grep -qx success

# --- workshop mode still takes effect (plain min-instances update, traffic routes to LATEST) ---
gcloud run services update workshop0 --region $R --project $P --min-instances=1 --quiet
test "$(gcloud run services describe workshop0 --region $R --project $P --format='value(spec.template.metadata.annotations."autoscaling.knative.dev/minScale")')" = 1
gcloud run services update workshop0 --region $R --project $P --min-instances=0 --quiet

# --- rollback drill: a failing candidate must leave the previous revision serving ---
PREV=$(gcloud run services describe workshop0 --region $R --project $P --format='value(status.traffic[0].revisionName)')
gh workflow run deploy-cloudrun.yml --repo smallTechOrg/workshop0 --ref main -f drill_rollback=true
sleep 10; RUN=$(gh run list --repo smallTechOrg/workshop0 --workflow=deploy-cloudrun.yml --limit 1 --json databaseId -q '.[0].databaseId')
! gh run watch "$RUN" --repo smallTechOrg/workshop0 --exit-status        # run MUST fail
test "$(gcloud run services describe workshop0 --region $R --project $P --format='value(status.traffic[0].revisionName)')" = "$PREV"
curl -fsS "$URL/api/health" | grep -q '"db":"ok"'
```

`OLD_PARTICIPANT_TOKEN` is the token saved in step 1; the count script prints counts only (no tokens, no names). The completion count is the sum of `completed_count` over every participant in every workshop's dashboard (`milestone_completion` rows). The same script with `BASE` set to the legacy service's URL, run in step 1, produces the baseline; the numbers 11 / 135 / 572 are that baseline and must be re-confirmed in step 1 before the cutover (if the live numbers have moved, the new baseline replaces them — what matters is old equals new).

**How the user tests it:**
1. Local: `cp .env.example .env`, set `WORKSHOP0_ADMIN_KEY`, `(cd frontend && pnpm build)`, `uv run python -m src`, open `http://localhost:8001/`. Read the landing page, footer and browser tab title: every mention says **Workshop0**; the footer GitHub link goes to `https://github.com/smallTechOrg/workshop0`. Open `/admin` and create a workshop; the exported CSV downloads with a Workshop0-named file.
2. **Logged-in-stays-logged-in:** in the browser where you were already using the old app (admin key saved, "Your workshops" populated), open the new deployment: you are still signed in to Admin Home and your workshops are listed (the keys migrated on read).
3. **Old links survive:** open a facilitator link (`/f/<token>`) and a personal participant link (`/p/<token>`) saved before the cutover: both open with identical state. A browser that still has an old participant cookie resumes without re-joining.
4. **Production:** `https://workshop0.smalltech.in/` serves from the new Cloud Run service `workshop0`; `/admin` with the same admin key lists the same 11 workshops (135 participants); health is ok; the repo lives at `github.com/smallTechOrg/workshop0` (the old URL redirects); a merge to `main` deploys; `gcloud run services list` and the console show no legacy-named resource. **Nothing is a stub.**

---

## Phase 10 — Opportunity Board *(smallest testable win of the Trainer Network; zero external blockers)*

**Goal:** A smallTech admin posts a real opportunity from the admin console — public details plus an internal partner name that never leaks — publishes it, and a stranger browses it on a public, filterable, paginated board and opens its detail page; closing it or letting its deadline pass takes it off the board automatically. Everything that needs sign-in (apply, profiles, matching, email) is visibly a labelled stub.

**Capabilities delivered (3):** C8 Topic taxonomy (40 seeded topics, admin add/rename/deactivate) · C9 Opportunity management for admins (create/edit/publish/unpublish/close, deadline auto-expiry, internal vs public partner name, audited) · C10 Public opportunity board (board + listing pages, type/topic filters, sort, pagination, pretty URLs). Contract: [api.md](api.md) §Phase 10; schema: [data-model.md](data-model.md) §Phase 10; UI: [capabilities.md](capabilities.md) §C8–C10.

**Non-goals (explicit):** no sign-in, no applying, no trainer profiles, no email, no AI, no rate limiting, no listing deletion, no join/tracker page changes, no new dependencies (Python or npm).

**Labelled stubs (rendered with the existing `StubBadge` / `StubCard` / `StubAction` primitives in `frontend/components/ui/StubBadge.tsx` — "Coming in a later phase" pill, non-interactive):** board **Join our network** CTA (→ Phase 11) · listing **Sign in to apply** (→ Phase 12) · listing **Join our network** card (→ Phase 11) · admin **Trainer network** nav on Admin Home and **Trainer pool** nav on the opportunities page (→ Phase 11) · admin **Applicants** column and **Suggested trainers** action (→ Phase 12) · admin **Outbox** nav (→ Phase 12). **Real on the tested path:** every admin editor/list/topics surface, the board, the listing page, filters, pagination, expiry, audit Activity.

**Independent slices (all four fan out concurrently — disjoint exclusive paths, no build dependencies; the frontend slices build against api.md §Phase 10, the e2e slice against api.md + the test ids below):**

| Slice | Owns (exclusive paths) | Delivers |
|---|---|---|
| **S1 backend** | `src/workshop0/db/models.py`, `alembic/versions/0005_opportunity_board.py`, `src/workshop0/services/{topics,opportunities,audit}.py`, `src/workshop0/api/{board_public,board_admin,__init__}.py`, `scripts/sqlite_to_postgres.py`, `tests/conftest.py`, `tests/unit/test_board_*.py`, `tests/integration/test_board_*.py`, `tests/integration/test_migration.py`, `tests/integration/test_sqlite_to_postgres.py`, `tests/integration/test_redirects.py`, `README.md` | Models `Topic`, `Opportunity`, `OpportunityTopic` + `FacilitatorAction.subject_type/subject_id`; migration `0005` with the 40-topic seed and a working downgrade; `record_action(..., subject_type=None, subject_id=None)`; `effective_status`; both routers registered in `create_app()`; pretty redirects `/opportunities` and `/opportunities/{id}` (before the static mount); conftest topic capture/restore (data-model.md §Test-harness consequence); `topic` as a reference table in the import script; README: new URLs (board, admin opportunities/topics) and the Phase-10 gate's no-`.env` key export |
| **S2 frontend-board** | `frontend/app/opportunities/**`, `frontend/components/board/**`, `frontend/lib/board.ts`, `frontend/app/page.tsx` (footer link only) | Board page + listing page per C10 (URL-synced filters inside `<Suspense>`, skeletons, empty/error/not-found states, pagination, deadline urgency pill, markdown via the existing `Markdown` primitive), stubs as listed; `lib/board.ts` = typed client + types for the **public** endpoints only (its own small fetch helper; imports `ApiError` from `lib/api.ts`, does not edit it); landing footer link "Opportunities for trainers" (plain `<a href="/app/opportunities/">`) |
| **S3 frontend-admin** | `frontend/app/admin/**` (incl. `admin/page.tsx` — header nav only), `frontend/components/admin/**`, `frontend/lib/adminBoard.ts` | `components/admin/AdminGate.tsx` (key gate reusing the `workshop0_admin_key` storage via `lib/storageCompat.ts`, same messages as Admin Home) used by the three new pages; Opportunities list (tabs + counts, search, pagination), Editor (public/internal groups, live public-card preview, state-dependent actions, inline field errors, Activity), Topics page; Admin Home header gains a real **Opportunities** link and the **Trainer network** stub; `lib/adminBoard.ts` = typed client + types for the **admin** endpoints (own fetch helper, sends `X-Admin-Key`) |
| **S4 e2e** | `tests/e2e/**` (new `opportunity-board.spec.ts`; additions to `helpers.ts` allowed) | The journey below. **Runtime dependency on S1+S2+S3 at gate time only** |

> **Assumed:** the two frontend slices each carry a ~30-line fetch helper rather than sharing one via an edit to `frontend/lib/api.ts`, so neither slice touches a shared file; `frontend/components/ui/**`, `frontend/lib/{api,format,storageCompat}.ts` and `frontend/app/globals.css` are **read-only** this phase. A later phase may consolidate (not gold-plated now).
> **Assumed:** one backend slice (not split into schema + API) because every API test needs the new models and migration — splitting would only serialize two halves of the same small surface.

**Test-id contract (S2/S3 render these exactly; S4 asserts on them):** board — `board-page`, `opportunity-card` (one per card, contains the title), `type-filter-all` / `type-filter-<type>`, `topic-filter-<slug>`, `sort-select`, `pagination-prev`, `pagination-next`, `pagination-status` (text "Page X of Y"), `board-empty`, `join-network-stub`; listing — `opportunity-detail`, `opportunity-title`, `apply-stub`, `closed-banner`, `opportunity-not-found`, `copy-link`; admin — `nav-opportunities` (Admin Home), `admin-opportunities-page`, `status-tab-<status>` (text includes the count), `admin-opportunity-row`, `new-opportunity-button`, `opp-title-input`, `opp-type-select`, `opp-summary-input`, `opp-description-input`, `opp-topic-option-<slug>`, `opp-location-select`, `opp-city-input`, `opp-deadline-input`, `opp-partner-display-input`, `opp-partner-internal-input`, `opp-internal-notes-input`, `opp-save-draft`, `opp-publish`, `opp-save`, `opp-close`, `opp-unpublish`, `opp-reopen`, `opp-status-pill`, `opp-public-link`, `opp-field-error-<field>`, `opp-activity-row`; topics — `admin-topics-page`, `topic-row` (contains the name), `topic-name-input`, `topic-category-input`, `topic-add-button`, `topic-active-toggle`, `topic-error`.

**Key surfaces/files:** S1 `services/opportunities.py` (validation, effective status, serializers: `public_card`, `public_detail`, `admin_row`, `admin_full`), `api/board_public.py`, `api/board_admin.py`, `alembic/versions/0005_opportunity_board.py`; S2 `app/opportunities/page.tsx`, `app/opportunities/view/page.tsx`, `components/board/{OpportunityCard,FilterBar,Pagination,ListingSidebar}.tsx`; S3 `app/admin/opportunities/page.tsx`, `app/admin/opportunities/edit/page.tsx`, `app/admin/topics/page.tsx`, `components/admin/{AdminGate,OpportunityEditor,TopicPicker,PublicCardPreview}.tsx`; S4 `tests/e2e/opportunity-board.spec.ts`.

**Integration tests S1 must write (PostgreSQL, `tests/integration/test_board_*.py`; fixture sizes are chosen so a sampled or truncated result differs observably):**
- **Seed:** exactly 40 active topics, 5 categories × 8, unique slugs, matching the data-model table; `/api/public/topics` returns them in position order with `open_count`.
- **Board fixture:** 30 open listings (spread over all 4 types and ≥6 topics, distinct `published_at`), plus 3 drafts, 3 closed and 3 expired (deadline moved into the past directly in the DB). Assertions: `total == 30`; `page_size=12` → pages of 12/12/6, `total_pages == 3`, the union of ids over the three pages is exactly the 30 open ids with no duplicates, for **both** sorts; page 4 → empty list; each `type` filter and a two-slug `topic` filter return exactly the precomputed id sets (ANY semantics); an unknown slug returns 0; unknown `type` → `validation_error`.
- **Expiry boundary:** deadline `now − 1 s` → `expired` everywhere (admin `status`, excluded from the public list, detail 200 with `"status": "expired"`), `now + 60 s` → `open`; extending an expired listing's deadline makes it open again with no other change.
- **Leak proof:** with `partner_internal_name = "ZZ-INTERNAL-PARTNER-7f3a"` and `internal_notes = "ZZ-INTERNAL-NOTE-9c1d"` set on listings in the fixture, the raw response text of every public endpoint (topics, list for every type, detail of open/expired/closed) contains neither sentinel nor the keys `partner_internal_name`, `internal_notes`, `stored_status`.
- **Public detail:** draft → 404 `not_found`; unknown id → 404; closed → 200 with `"status": "closed"`.
- **Admin:** every admin endpoint returns 401 `invalid_admin_key` without the key; create/patch validation for every rule in api.md with the exact `"<field>: …"` message (incl. `topic_ids` 0 and 9, inactive topic, missing city for onsite, `ends_on < starts_on`, naive deadline, publish with a past deadline); `counts` correct over the fixture; `q` matches internal partner name case-insensitively.
- **Audit:** create, update, publish, unpublish, close, reopen each write exactly one `facilitator_action` row with `actor="admin"`, `workshop_id IS NULL`, `subject_type="opportunity"`, the right `action` and `changed_fields`; a no-op PATCH writes none; topic create/update write `topic.*` rows; `activity` returns them newest first.
- **Topics:** slug derivation (`"C# / .NET 2"` → `c-net-2`), duplicate name in another case → 409 `topic_exists` and no row, rename collision → 409, deactivated topic hidden from public topics and rejected in new `topic_ids` but still serialized on an existing listing.
- **Migration:** `test_migration.py` extended — after `upgrade head` the topic seed is present; `downgrade 0004` removes the three new tables and the two audit columns; `upgrade head` again re-seeds 40.
- **Import script:** `test_sqlite_to_postgres.py` still passes with the seeded `topic` table on both sides (reference-table handling); an admin-added topic in the source is present in the target after import.
- **Observability:** publishing a listing emits structured log events `opportunity.created` and `opportunity.status_changed` (captured in the test) with the opportunity id and no internal partner name.
- **Redirects:** `test_redirects.py` gains `("/opportunities", "/app/opportunities/")` and `("/opportunities/12", "/app/opportunities/view/?id=12")`. No other existing Python test may be edited except `conftest.py`, `test_migration.py`, `test_sqlite_to_postgres.py` and `test_redirects.py` as described.

**e2e journey (S4, `tests/e2e/opportunity-board.spec.ts`, live single-origin app; every name carries a per-run suffix because the e2e database is not reset):** sign in at `/app/admin/` → `nav-opportunities` → **New** → fill title, type `workshop`, summary, a markdown description with a list and a fenced code block, two topics (`generative-ai`, `python`), location Hybrid + city, deadline +10 days, public partner "A Bengaluru fintech", internal partner "ZZ-INTERNAL-PARTNER-<run>" and an internal note → **Save draft** → status pill Draft → in a **fresh browser context**, open `/opportunities/<id>` → not-found state → back as admin **Publish** → pill Open, Activity shows create + publish → fresh context: `GET /opportunities` (pretty, follows the 307) → the card is present with "A Bengaluru fintech" → `page.content()` contains no `ZZ-INTERNAL` → click `type-filter-role` → card absent → `type-filter-workshop` + `topic-filter-generative-ai` → card present, URL carries the filters, **reload** keeps them → open the card → markdown renders (list + highlighted code), `apply-stub` and `join-network-stub` visible with the "Coming in a later phase" pill, no `ZZ-INTERNAL` in the page → admin **Close** → fresh context: the listing page shows `closed-banner` and no apply control; the board no longer lists it → admin: publishing a second listing with a past deadline shows `opp-field-error-deadline` and creates nothing public → **Topics**: add "Elixir <run>" in "Languages" → appears as a `topic-row`; adding it again in lower case shows `topic-error` → the public board's topic filters show it (muted, 0) → **pagination**: the spec creates 13 open listings for one fresh topic via the admin API (`request` fixture with `X-Admin-Key`) in `beforeAll`, filters the board by that topic → `pagination-status` reads "Page 1 of 2", 12 cards; **Next** → 1 card, "Page 2 of 2". Also asserts at 360 px width that the board has no horizontal scroll.

**Gate (exact commands, from the repo root; PostgreSQL 17 running as in README "Postgres test setup"; this phase needs **no** `.env` and no external credentials):**

```bash
createdb workshop0_test 2>/dev/null || true
export TEST_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/workshop0_test"
export WORKSHOP0_ADMIN_KEY="${WORKSHOP0_ADMIN_KEY:-phase10-local-gate-key-0123}"   # any value; read by the server and the e2e helpers
uv sync
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic current | grep -q '^0005'          # blank or 0004 = gate failed
uv run pytest tests/unit tests/integration -q                                          # whole suite, PostgreSQL, zero failures, no test weakened
(cd frontend && pnpm install && pnpm build)
test -f frontend/out/opportunities/index.html && test -f frontend/out/opportunities/view/index.html
test -f frontend/out/admin/opportunities/index.html && test -f frontend/out/admin/opportunities/edit/index.html && test -f frontend/out/admin/topics/index.html
grep -q '\.flex' frontend/out/_next/static/css/*.css                                  # styled-render
! grep -q '@source' frontend/out/_next/static/css/*.css
pnpm install && pnpm exec playwright install chromium
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head                          # pytest leaves the schema at head; re-assert before serving
DATABASE_URL="$TEST_DATABASE_URL" uv run python -m src &                               # canonical run path, :8001
sleep 3
curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:8001/opportunities | grep -qx 307
curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:8001/opportunities/1 | grep -qx 307
curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:8001/api/admin/opportunities | grep -qx 401
curl -fsS http://localhost:8001/api/public/topics | uv run python -c 'import json,sys; t=json.load(sys.stdin)["data"]["topics"]; s={x["slug"] for x in t}; assert len(t)>=40 and {"python","generative-ai","kubernetes","ux-design"}<=s, len(t)'
! curl -fsS 'http://localhost:8001/api/public/opportunities?page_size=50' | grep -q 'partner_internal_name'
pnpm exec playwright test tests/e2e --reporter=line                                    # new spec + ALL pre-existing specs
kill %1
```

**How the user tests it:** from the repo root: `export WORKSHOP0_ADMIN_KEY=<any key you like>` (or keep your `.env`), `(cd frontend && pnpm build)`, `uv run python -m src`, then:
1. Open **http://localhost:8001/admin**, enter the key → Admin Home now has an **Opportunities** link (and a "Trainer network" pill marked *Coming in a later phase*). Click it → the tabs show 0 everywhere.
2. **+ New opportunity** → fill the public details (pick two topics, Hybrid + Bengaluru, a deadline next week), public partner "A Bengaluru fintech", internal partner "Acme Payments" and an internal note. Watch the **public card preview** — "Acme" is not on it. **Save draft** → status Draft.
3. **Publish** → status Open; copy the public link shown.
4. In a private window open **http://localhost:8001/opportunities** → your card is there with "A Bengaluru fintech", nowhere "Acme". Try the type chips, a topic chip, "Closing soon"; reload — filters stay. Open the listing → description renders; **Sign in to apply** and **Join our network** carry *Coming in a later phase* pills (stubs, not bugs).
5. Back in admin, change the open listing's deadline to an hour ago and **Save** → refused inline under the deadline field ("set a future deadline to publish"), nothing changes publicly. Click **Close** instead → the private window's listing page now says applications have closed, and the board no longer lists it. **Reopen** (deadline still in the future) → back on the board.
6. **Topics** (link on the opportunities page) → add "Elixir" under Languages → it appears in the public board's topic chips (muted, 0). Add "elixir" again → rejected.
7. The editor's **Activity** list shows every action you took, with "admin-key" as the actor.
**Labelled stubs (not bugs):** Join our network, Sign in to apply, Trainer network / Trainer pool, Applicants, Suggested trainers, Outbox. **Expiry by time** is proven by the automated tests (a listing whose deadline passes shows *Expired* in admin and leaves the board with no action); to see it yourself, publish a listing with a deadline a few minutes out and reload after it passes.

---

## Phase 11 — Trainer Sign-in, CV-drafted Profiles & Admin Pool

**Goal:** A tech person finds the board, clicks **Join our network**, signs in with Google, drops a CV (PDF/DOCX/LinkedIn PDF) or pastes text, reviews a pre-filled profile on one screen, consents and is live; an admin signs in with Google (or the key), searches the pool, opens a trainer, downloads their CV, verifies them, tags and notes them, invites a known trainer by link, exports CSV and sees drafting cost. A trainer can delete their account.

**Capabilities delivered (3):** C11 Network sign-in & accounts · C12 CV-drafted trainer profile · C13 Admin trainer pool. Design: [architecture.md](architecture.md) §Network identity / §CV storage, [agent.md](agent.md) §Profile drafter, [api.md](api.md) §Phase 11, [data-model.md](data-model.md) §Phase 11.

**Stubs carried forward (labelled):** Sign in to apply, My applications, Matched for you, matching filters, Suggested trainers, Email invite, Outbox (→ 12); Saved searches, Public directory toggle (→ 13). **Made real:** board Join our network CTA, Admin Home Trainer network nav, opportunities-page Trainer pool nav.

**Shared scaffold (orchestrator, before the fan-out, one commit; see §Parallel fan-out rule):**
- **Dependencies:** add `pyjwt[crypto]`, `itsdangerous`, `python-multipart`, `pypdf`, `python-docx`, `google-cloud-storage` **and `anthropic`** to `pyproject.toml`, then run `uv lock`.
- **`.env.example`:** add every Phase-11 variable (architecture.md §Environment variables), including the Anthropic block.
- **`config/settings.py`:** the orchestrator, not a slice, adds every Phase-11 field under these attribute names: `workshop0_google_client_id`, `workshop0_google_client_secret`, `workshop0_oidc_issuer` (default `https://accounts.google.com`), `workshop0_session_secret`, `workshop0_admin_emails`, `workshop0_blob_backend` (`local`), `workshop0_gcs_bucket`, `anthropic_api_key` (`""`), `anthropic_workspace_id` (`""`), `workshop0_ai_network_model` (`claude-sonnet-5-5`), `workshop0_ai_network_fast_model` (`claude-haiku-5-5`). Field declarations only. Validation logic belongs to S1's `auth/startup.py`.
- **`api/__init__.py` (edited once, here):** register the router shells `auth/routes.py` (`/api/auth`), `api/network_me.py` (`/api/me`) and `api/network_admin.py` (`/api/admin/network`, `require_admin_key`). Add the pretty redirects `/invite/{token}` → `/app/network/join/?invite={token}` and `/network` → `/app/network/` before the static mount. Call `auth.startup.validate_settings(settings)` before routes are built. Add `anthropic_key_present` / `anthropic_workspace_present` booleans to `app.startup`, plus the one-time `ai.network_misconfigured` WARNING when the key is set and the workspace id is empty.
- **Python interface stubs** (bodies `raise NotImplementedError` unless noted; signatures from architecture.md §Network identity / §CV storage and agent.md §Shared client / §Profile drafter):
  - `auth/__init__.py`.
  - `auth/deps.py`: `CurrentUser`, `AdminActor`, `current_user`, `require_user`, `require_admin`.
  - `auth/startup.py`: `validate_settings(settings) -> None`. The stub is a no-op.
  - `services/ratelimit.py`: `RateResult(allowed: bool, retry_after_s: int)`, `hit(session, bucket, limit, window_s) -> RateResult`, `enforce(session, bucket, limit, window_s) -> None` (raises 429 `rate_limited` with `Retry-After`).
  - `storage/blobstore.py`: `BlobStore` protocol, `LocalDiskStore(root)`, `GcsStore(bucket)`, `get_blobstore() -> BlobStore`.
  - `services/cv_text.py`: `CvUnreadable`, `extract_text(data: bytes, kind: Literal["pdf", "docx"]) -> str`.
  - `ai/__init__.py`.
  - `ai/anthropic_client.py`: `LLMUnavailable`, `LLMError`, `LLMResult`, `is_available`, `build_client`, `get_client`, `reset_client`, `call_json`. The `is_available` stub returns `False` and the `reset_client` stub is a no-op.
  - `ai/pricing.py`: `PRICING_USD_PER_MTOK`, `cost_usd`.
  - `ai/usage.py`: `record_usage`.
  - `ai/profile_draft.py`: `TopicRef`, `DraftResult`, `DraftRejected`, `draft_profile`, `run_profile_draft`.
  - `services/profiles.py`: `Completeness(pct: int, missing: list[str])`, `completeness(profile) -> Completeness`.
- **TypeScript interface stubs:**
  - `frontend/lib/networkAuth.ts` exports `type CurrentUser = {id, email, display_name, avatar_url, is_admin, has_profile}` (S9 adds `invite_accepted: boolean`), `getAuthConfig(): Promise<{google_enabled: boolean}>`, `getMe(): Promise<CurrentUser | null>`, `signInUrl(next: string, invite?: string): string`, `signOut(): Promise<void>`, `useCurrentUser(): {user, loading, refresh}` and `NETWORK_HEADERS = {"X-Requested-With": "workshop0"}`.
  - `frontend/components/network/AccountMenu.tsx` is a default export with no props. The stub renders `null`.

**Slices.** S0 runs first because it is small and every DB test needs it. S1–S17 then fan out concurrently, in waves if over the cap. Every slice builds independently against the stubs above. "Tests need" lists the slices that must have landed before that slice's tests can pass.

| Slice | Owns (exclusive paths) | Delivers | Tests need |
|---|---|---|---|
| **S0 schema** | `src/workshop0/db/models.py`, `alembic/versions/0006_trainer_network.py`, `tests/conftest.py`, `tests/integration/test_migration.py` | All Phase-11 tables and the `ai_usage` changes, exactly per data-model.md. Conftest fixtures: `make_user(email, admin=False)`; `signed_in_client(user)`, which inserts an `auth_session` row and sets the cookie (the shortcut for non-auth tests); and `network_ai_disabled(which="key"\|"workspace")`, which monkeypatches the settings field to `""` and calls `anthropic_client.reset_client()`. This is the only sanctioned keyless switch, because `.env` holds real keys | — |
| **S1 auth** | `src/workshop0/auth/{oidc,sessions,deps,routes,startup}.py` (fills the stubs), `src/workshop0/security.py`, `tests/integration/auth/**`, `tests/integration/test_redirects.py` | OIDC client, sessions, `deps.py` (exact interface in architecture.md), `/api/auth/*`, admin via session in `require_admin_key`, CSRF check, open-redirect guard. Invite acceptance at the callback per api.md §Phase 11 → Invite acceptance: mismatch/expired checks **before** any user or session write, the masked-email redirect, `network_invite.accepted_*`, `invite_accepted` on `/api/auth/me`, and — the one sanctioned profile write outside S7 — setting `trainer_profile.verified*` when the accepting user **already has** a profile (no other profile column; a not-yet-created profile is verified by S7 at create). Also: issuer/secret startup rules in `startup.py`, and redirect tests for `/invite/{token}` and `/network` | S0, S2, S3 |
| **S2 ratelimit** | `src/workshop0/services/ratelimit.py`, `tests/unit/test_ratelimit.py`, `tests/integration/test_ratelimit_db.py` | `hit` / `enforce` over `rate_limit_hit`. Includes the two-app-instances-sharing-one-DB test | S0 |
| **S3 test-issuer** | `tests/support/**` | `tests/support/fake_oidc.py`, run as `uv run python tests/support/fake_oidc.py --port 8099`. Provides discovery, an authorize page with an email field that auto-approves, a token endpoint and JWKS. A flag makes it emit `email_verified=false`, a wrong `aud`, an expired token, or a token signed by a second key | — |
| **S4 cv-ingest** | `src/workshop0/storage/**`, `src/workshop0/services/cv_text.py`, `tests/unit/test_cv_text.py`, `tests/integration/storage/**`, `tests/fixtures/cv/**` | `BlobStore` (local + GCS). `extract_text` uses pypdf/python-docx and raises `CvUnreadable` below 200 chars. The committed CV fixtures, including an image-only PDF and the prompt-injection CV. GCS tests run only when `WORKSHOP0_GCS_BUCKET` is set (guarded) | — |
| **S5 ai-client** | `src/workshop0/ai/{__init__,anthropic_client,pricing,usage}.py`, `tests/unit/ai/**`, `tests/integration/ai_network/test_anthropic_client.py` | The Anthropic client exactly per agent.md §Provider / §Shared client: the mandatory `anthropic-workspace-id` default header, the availability rule (key **and** workspace id), structured-output `call_json` (`output_config` json_schema, `normalize_schema`, no tools / `tool_choice`) with one re-ask, error mapping (incl. `connection`, `status`, `request_id`), the pricing table, and `record_usage` plus its `ai.<purpose>` event. Also the header unit tests (`httpx2.MockTransport`), the real cheap-model call and the header-less-400 negative test | S0 (usage row) |
| **S6 profile-drafter** | `src/workshop0/ai/profile_draft.py`, `src/workshop0/ai/prompts/profile_draft_{system,user}.md`, `tests/integration/ai_network/test_profile_draft.py` | `draft_profile` (pure) and `run_profile_draft` (BackgroundTask: DB in, DB out), with the guardrails per agent.md §Profile drafter. Tested on S4's fixtures against the real API | S0, S4 (fixtures), S5 |
| **S7 me-api** | `src/workshop0/api/network_me.py`, `src/workshop0/services/profiles.py` (fills the stub), `tests/integration/network/me/**` | Every `/api/me/*` endpoint in api.md §Phase 11: CV upload/paste through the BackgroundTask drafter, draft polling, profile create/patch, completeness, own-CV download, deletion (DB + blob + sessions), invite-verified flag on create (from the user's accepted `network_invite`), `autofilled_fields` lifecycle (create keeps the untouched drafted fields, first PATCH clears), CV replacement in place (same `cv_document.id`), audit rows, the CV and drafting rate limits | S0, S1, S2, S4, S6 |
| **S8 pool-api** | `src/workshop0/api/network_admin.py`, `src/workshop0/services/{pool,invites}.py`, `tests/integration/network/admin/**` | Every `/api/admin/network/*` endpoint: the paginated and filtered pool, trainer detail with `ai_cost_usd`, CV download + audit, verify/notes/tags, CSV, invites, and `ai-spend` over network `ai_usage` rows. Ships the 60-profile pool fixture | S0, S1, S4, S7 (`completeness`) |
| **S9 fe-network-auth** | `frontend/app/signin/**`, `frontend/app/network/page.tsx`, `frontend/components/network/AccountMenu.tsx` + `frontend/components/network/auth/**`, `frontend/lib/networkAuth.ts` (fills both stubs), `frontend/components/board/**` (Join-our-network CTA only), `frontend/app/opportunities/page.tsx` (board-header CTA only) | Sign-in page (Google button, "not set up" state, error codes incl. the invite mismatch/expired copy in api.md §Phase 11 → Invite acceptance), account menu, network home routing (signed out / no profile / profile), and the real board CTA. `CurrentUser` gains `invite_accepted: boolean` (api.md `GET /api/auth/me`) | — |
| **S10 fe-network-profile** | `frontend/app/network/join/**`, `frontend/app/network/me/**`, `frontend/components/network/profile/**`, `frontend/lib/network.ts` | Onboarding (3 tabs, LinkedIn how-to, polling skeleton, invite landing with Verified state — signed out with `?invite=` → sign-in link `signInUrl("/app/network/join/", invite)`; signed in → the **Verified** badge renders iff `user.invite_accepted` (server truth from `/api/auth/me`, never the query param)) and the review screen with "From your CV — please check" chips. My profile with the completeness meter and nudges, delete flow, and stubs. The shared profile form lives here | — (imports S9's stubs) |
| **S11 fe-admin-pool** | `frontend/app/admin/network/**`, `frontend/components/admin/network/**`, `frontend/lib/adminNetwork.ts` | Pool table with filters, CSV, invites and the Network AI spend card. Trainer detail with CV download, verify, tags, notes, drafting cost and activity | — |
| **S12 fe-admin-gate** | `frontend/components/admin/AdminGate.tsx`, `frontend/app/admin/page.tsx`, `frontend/app/admin/opportunities/page.tsx` (nav only), `frontend/components/admin/AdminHeader.tsx` (the Trainer-pool nav only — handed to F5 once S12 is VERIFIED) | Google button on `AdminGate` and on Admin Home's gate. A session admin passes without a key; key behaviour is unchanged. Admin Home **Trainer network** and opportunities-page **Trainer pool** nav become real. The opportunities-page Trainer pool nav **is** the header's: in `AdminHeader.tsx` (rendered by the opportunities, editor and topics pages) the one-line change replaces `<StubAction label="Trainer pool" />` with a real `Link` to `/admin/network/` carrying `data-testid="nav-trainer-pool"`, and the inline "Trainer pool" link S12 added to the `opportunities/page.tsx` subtitle is removed, so exactly one `nav-trainer-pool` renders per screen (the e2e locator is strict). The header's `Outbox` stub stays | — |
| **S13 e2e-onboarding** | `tests/e2e/network-onboarding.spec.ts` | Journey below. Its sign-in helper is private to the spec file; `tests/e2e/helpers.ts` is read-only this phase | runtime: all |
| **S14 e2e-admin-pool** | `tests/e2e/admin-pool.spec.ts` | Journey below. **Self-seeding:** it creates its own trainer in `beforeAll` (fake-issuer sign-in, upload of `tests/fixtures/cv/genai_trainer.pdf`, profile create) and never depends on another spec's data | runtime: all |
| **S15 infra-provision** | `deploy/cloudrun/provision.sh` | CV bucket + IAM, `workshop0-session-secret`, `workshop0-google-client-secret`, **`workshop0-anthropic-api-key` + `workshop0-anthropic-workspace-id`**, all per architecture.md (stdin values, SKIPPED rule, per-secret IAM). `--rotate` accepts the new names. The script is written and `bash -n`-checked only and is never run by an agent | — |
| **S16 infra-workflows** | `.github/workflows/{deploy-cloudrun,ci}.yml` | Conditional secret mapping (the Anthropic pair maps only when both secrets have enabled versions), `WORKSHOP0_BLOB_BACKEND`/`WORKSHOP0_GCS_BUCKET`, the GitHub variables, and the CI fake issuer for e2e. CI passes `ANTHROPIC_API_KEY`/`ANTHROPIC_WORKSPACE_ID` from GitHub secrets when present (guarded skip otherwise) | — |
| **S17 docs** | `README.md`, `deploy/RUNBOOK.md` | README: sign-in setup, the Google Console steps below, Anthropic `.env` setup (both values; the workspace header requirement in one sentence), and new env vars. RUNBOOK: the operator step for the Anthropic secrets, a note on two LLM providers, and how to confirm model pricing | — |

> **Assumed:** splitting identity into S1 auth / S2 ratelimit / S3 test-issuer, and the API into S7 me-api / S8 pool-api, is safe because their only shared surfaces are the stubbed interfaces above. The e2e helper duplication (~20 lines of fake-issuer sign-in per spec) is accepted so that `helpers.ts` stays untouched.

**Gate (exact commands; repo root; PostgreSQL as before. The real Anthropic key and workspace id are read from the gitignored local `.env` and never echoed. No `gcloud`, Google or SMTP credentials are needed):**

```bash
export TEST_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/workshop0_test"
export WORKSHOP0_ADMIN_KEY="${WORKSHOP0_ADMIN_KEY:-phase11-local-gate-key-0123}"
envval() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '"'"'"; }      # .env values are unquoted or simply quoted
export ANTHROPIC_API_KEY="$(envval ANTHROPIC_API_KEY)" ANTHROPIC_WORKSPACE_ID="$(envval ANTHROPIC_WORKSPACE_ID)"
test -n "$ANTHROPIC_API_KEY" && test -n "$ANTHROPIC_WORKSPACE_ID"                      # BLOCKED (not skipped) without both
export WORKSHOP0_GOOGLE_CLIENT_ID=test-client WORKSHOP0_GOOGLE_CLIENT_SECRET=test-secret
export WORKSHOP0_OIDC_ISSUER=http://localhost:8099 WORKSHOP0_SESSION_SECRET="$(openssl rand -hex 32)"
export WORKSHOP0_ADMIN_EMAILS=admin@example.test WORKSHOP0_BLOB_BACKEND=local
uv sync
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head && DATABASE_URL="$TEST_DATABASE_URL" uv run alembic current | grep -q '^0007'   # 0007 = Phase 11b's F1 (lands in the same phase)
uv run python tests/support/fake_oidc.py --port 8099 &                                 # real OIDC protocol, local issuer
sleep 2
uv run pytest tests/unit tests/integration -q                                          # incl. auth/, network/, storage/, ai/, ai_network/ (REAL Anthropic, workspace header)
! uv run pytest tests/unit/ai tests/integration/ai_network -q -rs | grep -q SKIPPED   # real-key tests ran, none skipped
! grep -rn --include='*.py' 'Anthropic(' src | grep -v '^src/workshop0/ai/anthropic_client.py:'   # one construction site
! grep -il openrouter src/workshop0/ai/{anthropic_client,pricing,usage,profile_draft,opportunity_draft}.py   # network AI never uses OpenRouter
(cd frontend && pnpm install && pnpm build)
for p in signin network network/join network/me admin/network admin/network/trainer; do test -f "frontend/out/$p/index.html"; done
grep -q '\.flex' frontend/out/_next/static/css/*.css && ! grep -q '@source' frontend/out/_next/static/css/*.css
pnpm install && pnpm exec playwright install chromium
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" uv run python -m src &
sleep 3
curl -sS -o /dev/null -w '%{http_code}\n' http://localhost:8001/invite/abc | grep -qx 307
curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8001/api/me/cv/text | grep -qx 401
pnpm exec playwright test tests/e2e --reporter=line
kill %2 %1
bash -n deploy/cloudrun/provision.sh
```

**Gate conditions beyond the commands (tests in S1/S2/S5/S6/S7/S8 must contain):** Network AI (S5/S6), per agent.md §Testing:
- every Anthropic request carries `anthropic-workspace-id` (MockTransport, including the re-ask);
- key without workspace id, and no key at all, each send zero requests;
- a real cheap call records tokens and `cost_usd > 0`;
- a header-less raw client gets HTTP 400;
- pricing math and the unknown-model rule hold;
- the drafter fixtures and prompt-injection CV pass against the real `claude-sonnet-5-5`, and each drafting call writes one `ai_usage` row whose `model` is the configured id.

OIDC — state mismatch, nonce mismatch, wrong `aud`, expired token, bad signature (token signed by a second key), `email_verified=false` each refused with the documented redirect code and no session row; first sign-in creates one user, second reuses it; allowlisted email → admin endpoints succeed without the key, de-listed → 403 `not_admin` on the next request; existing admin tests still pass with the key only; every `/api/me` mutation without `X-Requested-With` → 403 `csrf_failed`; `next=https://evil.example` → lands on `/app/network/`; rate limit: the 11th CV upload in an hour → 429 with `Retry-After`, across two app instances sharing the DB. Profiles — the three drafter fixtures through the real endpoint (upload → poll → draft) with agent.md's assertions; image-only PDF → 422 `cv_unreadable`; keyless run and key-without-workspace run (both via the `network_ai_disabled` fixture) → `draft_status="skipped"` and profile creation still works; consent missing → `validation_error`; completeness = the ten-check formula on 5 hand-built profiles; deletion removes user, profile, CV row, blob file and sessions and writes `account.delete` with a masked email only. Pool — a 60-profile fixture: `q`, `topic` (ANY), `verified`, `tag` filters return precomputed sets across 3 pages; CSV row count = filtered total; CV download (local) returns the original bytes with `Content-Disposition` and writes `cv.download`; `ai-spend` and the trainer's `ai_cost_usd` equal the sums of the seeded network `ai_usage` rows (help-desk rows with a `workshop_id` excluded). Privacy — rates, email and CV fields appear only in the owner's own `/api/me/*` payloads and in admin payloads; raw CV text, `storage_key` and `sha256` are never returned to anyone (asserted on serialized JSON of every `/api/me/*`, `/api/admin/network/*` and public response). Invites — matching email → `invite_accepted: true` on `/api/auth/me`, an existing profile becomes verified at the callback, a later profile create starts verified; mismatching email → 303 to `/app/signin/?error=invite_email_mismatch&invite=<token>&invite_email=<masked>`, no user created, no session, invite untouched; expired → `error=invite_expired`, no user created, no session.

**e2e (S13 / S14):** *network-onboarding* — board → **Join our network** → sign-in page → **Continue with Google** → the local issuer's page → enter `trainer-<run>@example.test` → back on onboarding → upload `tests/fixtures/cv/genai_trainer.pdf` → "Reading your CV…" → review screen shows ≥1 "From your CV — please check" chip and the curated topics (real Anthropic call, via the server's `.env`) → tick consent → **Create my profile** → My profile shows the completeness meter and nudges → sign out → sign in again → same profile → **Delete my account** → confirmation → signing in again lands on onboarding (fresh). *admin-pool* — sign in as `admin@example.test` via the issuer → Admin Home without the key → **Trainer network** → the trainer this spec seeded in `beforeAll` is listed → open → **Download CV** (download event, `.pdf`) → **Verify** → badge → add tag + note → **Export CSV** → create an invite for `invitee-<run>@example.test` → open the copied `/invite/<token>` in a fresh context, sign in as that email → onboarding shows **Verified** → a different email on another invite → mismatch message. Every stub listed above shows its pill.

**How the user tests it:**
1. **One-time Google setup (manual, ~5 minutes, GCP Console, project `ai-agent-boilerplate0`):** APIs & Services → **OAuth consent screen** → User type **External** → app name **Workshop0**, support email = your smallTech email, authorized domain `smalltech.in`, scopes `openid`, `email`, `profile` → add yourself as a test user (or **Publish app** to allow anyone; these scopes need no Google verification) → **Credentials** → **Create credentials → OAuth client ID** → Application type **Web application**, name `workshop0-web` → **Authorized JavaScript origins** `http://localhost:8001`, `https://workshop0.smalltech.in` → **Authorized redirect URIs** `http://localhost:8001/api/auth/google/callback`, `https://workshop0.smalltech.in/api/auth/google/callback` → Create → copy the client ID and secret.
2. **Local:** in `.env` set `WORKSHOP0_GOOGLE_CLIENT_ID`, `WORKSHOP0_GOOGLE_CLIENT_SECRET`, `WORKSHOP0_SESSION_SECRET=$(openssl rand -hex 32)`, `WORKSHOP0_ADMIN_EMAILS=<your email>`. `ANTHROPIC_API_KEY` and `ANTHROPIC_WORKSPACE_ID` are already in your `.env`; drafting needs both, and with only the key the review screen starts empty and the log shows `ai.network_misconfigured`. Run `(cd frontend && pnpm build)`, then `uv run python -m src`. The `app.startup` log line should show `anthropic_key_present: true, anthropic_workspace_present: true`.
3. Private window → **http://localhost:8001/opportunities** → **Join our network** → **Continue with Google** with a non-admin Google account → upload your own CV (or a LinkedIn "Save to PDF") → within a few seconds the review screen is pre-filled, drafted fields marked "From your CV — please check"; fix anything, tick consent → **Create my profile** → see completeness and the nudges.
4. Normal window → **http://localhost:8001/admin** → **Continue with Google** with your admin email (no key) → **Trainer network** → find the trainer → open → download the CV, **Verify**, add a tag and a note; check the **Network AI spend** card shows the drafting cost; **Export CSV**. Create an invite for another address you own → open the link in a third browser → sign in with that address → it starts **Verified**.
5. As the trainer, **Delete my account** → it disappears from the pool.
6. **Production (operator step — escalated, agents never run this against GCP)** (after the merge deploys): `set -a; . ./.env; set +a` (or export `WORKSHOP0_GOOGLE_CLIENT_SECRET`, `ANTHROPIC_API_KEY`, `ANTHROPIC_WORKSPACE_ID` by hand), then `bash deploy/cloudrun/provision.sh --dry-run` → review → `bash deploy/cloudrun/provision.sh` (creates the bucket and the secrets incl. `workshop0-anthropic-api-key` + `workshop0-anthropic-workspace-id`; each absent value prints `SKIPPED`), `gh variable set WORKSHOP0_GOOGLE_CLIENT_ID --body …`, `gh variable set WORKSHOP0_ADMIN_EMAILS --body …`, `gh workflow run deploy-cloudrun.yml --ref main`, then repeat steps 3–4 on **https://workshop0.smalltech.in** (CV download goes through a signed GCS URL; drafting works only once both Anthropic secrets exist). Also confirm the two prices in `src/workshop0/ai/pricing.py` against Anthropic's pricing page (Assumed values — agent.md §Shared client).
**Labelled stubs (not bugs):** Sign in to apply, My applications, Matched for you, Saved searches, Public directory profile, matching filters, Suggested trainers, Email invite, Outbox.

### Phase 11b — Phase 10 feedback

*A sub-step of Phase 11. It is built concurrently with S1–S17 and handed off in the same human test. The Phase-11 gate **and** the addendum below must both pass before the Phase-11 handoff.*

**Goal:** An admin pastes the description a partner forwarded into the opportunity editor and clicks **Draft**. Every field is pre-filled and marked "Drafted — please check": topics come only from the curated list, the partner is matched against a managed partner list, and compensation is structured with a unit. The admin fixes anything wrong and publishes. Nothing is ever saved or published automatically. The public card then reads "₹8,000–12,000 / day" and never shows the partner's internal identity. Partners are a managed list that admins can add, rename and deactivate. Existing free-text partner names are migrated into it.

**Capabilities extended (no new numbers):** C9 gains **Partners**, **paste-to-fill drafting** and **structured compensation**. C10 gains the **compensation display**. Contract: [api.md](api.md) §Phase 11b. Schema: [data-model.md](data-model.md) §Phase 11b. Drafter: [agent.md](agent.md) §Opportunity drafter. UI: [capabilities.md](capabilities.md) §C9/§C10.

> **Assumed:** this is feedback on delivered capabilities, so C9/C10 are extended instead of adding C20+. The Phase-10 capability count is unchanged.

**Non-goals (explicit):**
- no compensation filter on the board or the admin list;
- no parsing of legacy `compensation_text` into the structured fields;
- no partner deletion and no partner-facing or public partner surface;
- no back-linking of a new listing's draft usage to the listing it becomes;
- no new dependency, setting or environment variable.

**Mini-scaffold (orchestrator, one commit, before the F fan-out; needs only S0, which is committed; see §Parallel fan-out rule):**
- **`src/workshop0/api/__init__.py`:** add `partners_admin` and `board_ai_admin` to the `from src.workshop0.api import (...)` list. Add `app.include_router(partners_admin.router)` and `app.include_router(board_ai_admin.router)` directly after `app.include_router(board_admin.router)`. No other change.
- **Router shells:** `api/partners_admin.py` and `api/board_ai_admin.py`. Each is just `router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin_key)])`.
- **Python stub `src/workshop0/services/partners.py`.** Bodies `raise NotImplementedError`. Signatures:
  - `PARTNER_EXISTS_MESSAGE: str`;
  - `normalize_name(name: str) -> tuple[str, str]`, which returns `(collapsed, name_key)`;
  - `partner_ref(partner: Partner) -> dict`, which returns `{"id", "internal_name", "display_name", "active"}`;
  - `active_partners(session) -> list[Partner]`;
  - `resolve_partner(session, *, partner_id: int | None, partner_id_given: bool, internal_name: str | None, internal_name_given: bool, display_name_hint: str | None, current_partner_id: int | None, by: str) -> Partner | None`. It flushes but never commits. Rules are in api.md §Phase 11b.
- **TypeScript stubs.** Each has exact exported types and signatures, with placeholder bodies that type-check:
  - `frontend/lib/compensation.ts`:
    - `type CompensationUnit = "hour" | "day" | "course" | "month"` and `type Currency = "INR" | "USD"`;
    - `COMPENSATION_UNITS: {value: CompensationUnit; label: string}[]` and `CURRENCIES: {value: Currency; symbol: string}[]`, both real in the stub;
    - `interface CompensationFields {compensation_min: number | null; compensation_max: number | null; compensation_currency: Currency | null; compensation_unit: CompensationUnit | null; compensation_text: string | null}`;
    - `formatCompensation(c: CompensationFields): string | null`. The stub returns `c.compensation_text`.
  - `frontend/lib/adminPartners.ts`:
    - `interface PartnerRef {id; internal_name; display_name: string | null; active}`;
    - `interface AdminPartner extends PartnerRef {notes: string | null; opportunity_count: number; created_at; updated_at}`;
    - `adminListPartners(adminKey): Promise<{partners: AdminPartner[]}>`;
    - `adminCreatePartner(adminKey, body: {internal_name; display_name?; notes?}): Promise<{partner: AdminPartner}>`;
    - `adminPatchPartner(adminKey, id, body: Partial<{internal_name; display_name; notes; active}>): Promise<{partner: AdminPartner}>`.
  - `frontend/lib/adminDraft.ts`:
    - `type DraftedField`, the union of the api.md `drafted_fields` values;
    - `interface OpportunityDraft`, the api.md `draft` object;
    - `interface DraftResponse {draft: OpportunityDraft; drafted_fields: DraftedField[]; cost_usd: number; model: string}`;
    - `getDraftConfig(adminKey): Promise<{available: boolean; model: string}>`;
    - `draftOpportunity(adminKey, body: {text: string; opportunity_id: number | null; keep_partner_identity: boolean}): Promise<DraftResponse>`.
  - `frontend/components/admin/partners/PartnerSelect.tsx`: `export function PartnerSelect(props: {value: PartnerRef | null; onChange: (p: PartnerRef | null) => void; suggestedNew?: {internal_name: string; display_name: string | null} | null; drafted?: boolean; error?: string})`. The stub renders `null`.
  - `frontend/components/admin/drafting/PasteToFill.tsx`: `export function PasteToFill(props: {opportunityId: number | null; hasUserInput: boolean; onDraft: (r: DraftResponse) => void})`. The stub renders `null`.
  - `frontend/components/admin/drafting/DraftedChip.tsx`: `export function DraftedChip(props: {field: DraftedField; show: boolean})`. The stub renders `null`.

  Components get the admin key from `useAdmin()` (`components/admin/AdminGate.tsx`, read-only for every F slice).

> **Assumed:** the partner endpoints get their own router, `partners_admin.py`, and the drafter gets `board_ai_admin.py`, instead of both living in `board_admin.py`. This lets F2, F3 and F4 own disjoint files. Paths stay under `/api/admin`.

**Slices.** F1 runs first. It is small, and every other backend F slice's tests need its models. F2–F10 then fan out concurrently with S1–S17, joining the Phase-11 waves in table order. **11b exception to "build dependencies are always none":** three slices each have one **deferred edit** on a file that an in-flight S slice owns. The slice writes everything else at once and applies the deferred edit only after the named S slice is **VERIFIED** by qa-auditor. At that point the path transfers, as listed below.

| Slice | Owns (exclusive paths) | Delivers | Tests need | Build dependency |
|---|---|---|---|---|
| **F1 schema-partners** | `src/workshop0/db/models.py` (transferred from S0, which is done), `alembic/versions/0007_partners_compensation.py`, `tests/integration/test_migration.py` (transferred from S0) | `Partner` model, the new `Opportunity` columns, and `AiUsage.purpose` widened to `String(32)`, exactly per data-model.md §Phase 11b. Migration `0007` (`down_revision = "0006"`) includes the free-text-partner data migration with the dedupe rules and a working downgrade. `test_migration.py`: head is now `0007`; `EXPECTED_TABLES` gains `partner`; the existing 0006 tests stop asserting that 0006 is head; plus the new 0007 tests below. `tests/integration/test_sqlite_to_postgres.py` must stay green **without being edited** | — | — (runs first) |
| **F2 partners-api** | `src/workshop0/services/partners.py` (fills the stub), `src/workshop0/api/partners_admin.py` (fills the shell), `tests/integration/test_partners_admin.py` | `GET/POST /api/admin/partners` and `PATCH /api/admin/partners/{id}` per api.md: normalized-name uniqueness → 409 `partner_exists`, deactivate/reactivate, `opportunity_count`, audit `partner.create`/`partner.update` (actor `admin`, `subject_type="partner"`, `by` from `AdminActor`), and the opportunity mirror rewrite on rename. Also `resolve_partner` and `normalize_name` for F3/F4. Log events `partner.created`/`partner.updated` carry the id only, never names or notes | F1, S1 (`AdminActor`) | — |
| **F3 opportunity-api** | `src/workshop0/services/opportunities.py`, `src/workshop0/services/topics.py`, `src/workshop0/api/board_admin.py`, `tests/unit/test_board_rules.py`, `tests/integration/test_board_{admin,public,leak,audit,observability}.py` (edited only where the contract changed), `tests/integration/test_board_partner_link.py`, `tests/integration/test_board_compensation.py` | Opportunity writes accept `partner_id`, plus the legacy `partner_internal_name` resolved through `resolve_partner`. They write the mirror. Admin payloads gain `partner_id`/`partner`, with `partner_internal_name` derived from the partner row. Structured compensation fields have their validation, and are added explicitly to the public allow-list. Admin `q` matches `partner.internal_name` through a join. Audit `by` is the `AdminActor.by` for opportunity and topic writes (data-model.md §facilitator_action). `board_public.py` is read-only: public serializers never read the partner row | F1, F2, S1 | — |
| **F4 opportunity-drafter** | `src/workshop0/ai/opportunity_draft.py`, `src/workshop0/ai/prompts/opportunity_draft_{system,user}.md`, `src/workshop0/api/board_ai_admin.py` (fills the shell), `tests/unit/test_opportunity_draft_guardrails.py`, `tests/integration/ai_network/test_opportunity_draft.py`, `tests/integration/ai_network/test_opportunity_draft_api.py`, `tests/fixtures/opportunity_posts/**` | `draft_opportunity` (pure) and `run_opportunity_draft`, exactly per agent.md §Opportunity drafter. Endpoints `GET /api/admin/opportunity-draft/config` and `POST /api/admin/opportunity-draft`: rate limit, `record_usage(purpose="opportunity_draft", opportunity_id=…)`, 503 `ai_not_configured`, 502 `ai_draft_failed`. Also the four committed fixtures, including the prompt-injection post. Unit tests for the guardrails need no network. The real-API tests run on `claude-sonnet-5-5` | F1, F2 (`normalize_name`), S2 (ratelimit), S5 (client + usage) | — |
| **F5 fe-partners** | `frontend/app/admin/partners/**`, `frontend/components/admin/partners/**` (fills `PartnerSelect`), `frontend/lib/adminPartners.ts` (fills the stub); **deferred:** `frontend/components/admin/AdminHeader.tsx` | Partners page (C9): table, add row, inline rename/edit of the public name and notes, active toggle with confirm. `PartnerSelect`: a searchable dropdown of active partners plus the listing's current partner if it is inactive; **+ Add partner** modal; a "Suggested new partner" offer; a "Manage partners" link. Own fetch helper, which sends `X-Admin-Key` and `X-Requested-With: workshop0`. **Deferred edit:** `AdminHeader.tsx` gains `"partners"` in `Section` and a `nav-partners` link after Topics | — | the AdminHeader edit waits until **S12 is VERIFIED** (S12 makes the header's Trainer-pool nav real; F5 keeps that link and adds Partners after Topics) |
| **F6 fe-drafter** | `frontend/components/admin/drafting/**` (fills both stubs), `frontend/lib/adminDraft.ts` (fills the stub) | `PasteToFill`, the "Paste the forwarded description" panel: textarea, "Keep the partner's name in the public text" toggle, **Draft**, drafting skeleton, error state, **not-configured** state from `/config`, a confirm before overwriting typed input, and the cost line "Drafted with <model> · $0.0042" (admin-only, so naming AI is fine). `DraftedChip` shows an amber "Drafted — please check" chip | — | — |
| **F7 fe-editor** | `frontend/components/admin/OpportunityEditor.tsx`, `frontend/components/admin/PublicCardPreview.tsx`, `frontend/app/admin/opportunities/edit/page.tsx`, `frontend/lib/adminBoard.ts` | The editor embeds `PasteToFill` at the top of a new listing (and collapsed on an existing one). It maps a `DraftResponse` into the form (slug → topic id; `deadline_on` → that date at 23:59 local) and shows `DraftedChip` on each drafted field until that field is edited. The internal partner text input is replaced by `PartnerSelect`; choosing a partner fills an **empty** public-name field with its default public name. Compensation becomes min / max / currency / unit plus the note, with inline errors. The preview uses `formatCompensation`. `adminBoard.ts` gains the new fields and sends `X-Requested-With: workshop0` | — | — |
| **F8 fe-board-compensation** | `frontend/lib/compensation.ts` (fills the stub; the **only** compensation formatter), `frontend/lib/board.ts`, `frontend/app/opportunities/view/page.tsx`; **deferred:** `frontend/components/board/OpportunityCard.tsx` | The display rules in capabilities.md §C10. The listing meta grid shows `formatCompensation(o)` with `data-testid="opportunity-compensation"`. Public types gain the four fields. **Deferred edit:** the card's compensation line uses `formatCompensation(o)` with the same test id | — | the OpportunityCard edit waits until **S9 is VERIFIED** |
| **F9 e2e-drafting** | `tests/e2e/opportunity-drafting.spec.ts` (new), `tests/e2e/opportunity-board.spec.ts` (update: the internal-partner text fill becomes the `PartnerSelect` **+ Add partner** flow with a run-suffixed internal name and a `ZZ-PARTNER-NOTE-<run>` note, plus a no-leak assertion for that note; its API seeding is unchanged because the legacy `partner_internal_name` still resolves. **Also owned by F9:** the Phase-10 assertions that expect `join-network-stub` — on the board (`toBeVisible` + "Coming in a later phase") and in the listing-page stub loop `['apply-stub', 'join-network-stub']` — become: board → `join-network-stub` count 0 and `join-network-cta` visible (S9's real CTA, same assertion shape as `network-onboarding.spec.ts`); listing page → the stub loop keeps only `apply-stub` (still a Phase-12 stub) and `join-network-cta` is asserted visible instead) | Journey below. `helpers.ts` stays read-only. Self-seeding | runtime: all (F1–F8 including their deferred edits, and S1–S12) | — |
| **F10 docs** | **deferred:** `README.md` | The README "Opportunity Board" section gains the Partners page URL, paste-to-fill (needs both Anthropic values; without them the box says "AI drafting not configured"), and the compensation units | — | waits until **S17 is VERIFIED** |

**Path transfers (effective the moment the named slice is VERIFIED; until then the F slice must not touch the file):**
- `frontend/components/board/OpportunityCard.tsx`: S9 → **F8**. S9 keeps the rest of `components/board/**` until Phase 11 closes.
- `frontend/components/admin/AdminHeader.tsx`: S12 → **F5**. S12 owns it for the one-line Trainer-pool change (S12 row); S11 never touches it.
- `frontend/app/opportunities/page.tsx`: owned by **S9** (board-header CTA) for the rest of Phase 11; no F slice touches it.
- `README.md`: S17 → **F10**.
- Committed S0 paths: `src/workshop0/db/models.py` and `tests/integration/test_migration.py` → **F1** (immediately).
- F7 does **not** touch `frontend/app/admin/opportunities/page.tsx` (S12) and F8 does not touch `frontend/app/opportunities/page.tsx` (S9). Neither file needs a change for 11b, because the admin list keeps its `partner_internal_name` key and the board gets no new filter.

> **Assumed:** the pieces of the editor (partner picker, paste box, chips) are separate slices behind TS stubs, and F7 integrates them. This way four frontend slices run in parallel instead of one 1000-line file serializing the work.
> **Assumed:** `tests/conftest.py` stays read-only in 11b. Truncation is metadata-driven, so `partner` is truncated automatically. `opportunity_body` keeps sending the legacy `partner_internal_name`, which still resolves to a partner, so every existing board fixture remains valid.

**Test-id contract (F5–F8 render these; F9 asserts them):**

| Surface | Test ids |
|---|---|
| Partners page | `admin-partners-page`, `partner-row` (contains the internal name), `partner-internal-input`, `partner-display-input`, `partner-notes-input`, `partner-add-button`, `partner-active-toggle`, `partner-error`, `nav-partners` (header, after the deferred edit), `partners-link` (editor) |
| `PartnerSelect` | `opp-partner-select`, `opp-partner-option-<id>`, `opp-partner-add`, `partner-add-internal-input`, `partner-add-display-input`, `partner-add-notes-input`, `partner-add-save`, `partner-suggested-new` |
| Paste box | `paste-box`, `paste-input`, `paste-keep-partner-toggle`, `paste-draft-button`, `paste-drafting`, `paste-error`, `paste-not-configured`, `draft-cost-line` |
| Drafted chips | `drafted-chip-<field>`, one per `drafted_fields` value |
| Compensation (editor) | `opp-comp-min-input`, `opp-comp-max-input`, `opp-comp-currency-select`, `opp-comp-unit-select`, `opp-compensation-input` (the note; existing id kept) |
| Compensation (card + listing) | `opportunity-compensation` |
| Removed | `opp-partner-internal-input` |

**Tests the backend slices must write (PostgreSQL; real Anthropic where stated):**
- **Migration (F1):**
  - *Fixture:* at revision `0006`, insert six listings: `"Acme Payments"` (updated oldest), `"  acme   PAYMENTS "`, `"ACME payments"` (updated newest), `"Globex"`, one with `null` and one with `"   "`. Display names: `"A fintech"` ×2, `"Fintech partner"` ×1 on the Acme group, `null` on Globex.
  - *Upgrade:* `upgrade head` → exactly **2** partner rows. Acme has `internal_name="ACME payments"` (the newest variant, collapsed), `display_name="A fintech"` (the most frequent) and `name_key="acme payments"`. The 4 named listings carry the right `partner_id`; the 2 blank ones are `null`. Their `partner_internal_name` values are unchanged. The compensation columns are null. `ai_usage.purpose` accepts `'opportunity_draft'`.
  - *Downgrade:* `downgrade 0006` restores the pre-0007 schema. Listings whose `compensation_text` was null but had amounts get the plain-text fallback. `opportunity_draft` usage rows are deleted. `partner_internal_name` equals the partner's name.
  - *Re-upgrade:* `upgrade head` again → the same 2 partners (idempotent, with no duplicates).
- **Partners (F2):**
  - 401 without the key;
  - create, list with `opportunity_count`;
  - duplicate under case or whitespace variants → 409 `partner_exists` with no row; rename collision → 409;
  - bounds: `internal_name` 2–160, `display_name` ≤160, `notes` ≤5000;
  - deactivate → absent from `active_partners`;
  - every write → exactly one audit row, and a no-op PATCH → none;
  - rename rewrites `opportunity.partner_internal_name` on that partner's listings;
  - captured log events contain neither the internal name nor the notes.
- **Partner link (F3):**
  - `partner_id` set, changed and cleared;
  - an unknown id or an inactive partner on a new attachment → `validation_error` with the exact message; an inactive partner already attached is kept;
  - the legacy `partner_internal_name` reuses a case-variant match, or creates a partner plus a `partner.create` audit in the same transaction;
  - a conflicting `partner_id` with `partner_internal_name` → `validation_error`;
  - `changed_fields` reports `partner_id`;
  - `q` finds a listing by a renamed partner's new name.
- **Compensation (F3):** every rule in api.md, including:
  - amount without currency or unit;
  - currency or unit without an amount;
  - `max < min`;
  - an out-of-range value;
  - each of the 4 units;
  - PATCH partial merges.
  The public card and detail carry the 4 fields.
- **Leak (F3, extends `test_board_leak.py`):** the board fixture's partners get `notes = "ZZ-PARTNER-NOTE-4b2e"`. The raw text of every public response (topics, list for every type, detail of open, expired and closed listings) contains:
  - neither the partner sentinel (`ZZ-INTERNAL-PARTNER-7f3a`) nor the note sentinel;
  - none of the keys `partner_id`, `"partner"`, `name_key`, `notes`, `partner_internal_name`, `internal_notes`, `stored_status`.
- **Drafter (F4):** per agent.md §Opportunity drafter → Testing, including the prompt-injection fixture, the curated-topics-only assertion, partner matching, the keyless/no-workspace paths, `ai_usage` + cost, and the rate limit.

**e2e journey (F9, `tests/e2e/opportunity-drafting.spec.ts`, live single-origin app, the server's `.env` provides the real Anthropic key + workspace id; per-run suffixes because the e2e DB is not reset):**
1. **Seed (`beforeAll`, admin API):** ensure the partner `Zenvia Learning Pvt Ltd` exists. Its default public name is `A Pune edtech` and its notes are `ZZ-PARTNER-NOTE-<run>`. Look it up first and create it only if absent.
2. **Partners page:** sign in at `/app/admin/` → open the Partners page (`partners-link` from the editor, or `nav-partners`). Add `ZZ-Partner-<run>` → it shows a `partner-row`. Adding `zz-partner-<run>` → `partner-error`. Deactivating it → it is gone from `opp-partner-select`.
3. **Draft:** **New opportunity** → fill `paste-input` with `tests/fixtures/opportunity_posts/forwarded_genai_workshop.txt` → **Draft**. Within 45 s:
   - title is non-empty;
   - `opp-topic-option-generative-ai` and `opp-topic-option-python` are selected;
   - location is Hybrid, and from Phase 11c the location chips are exactly `Pune` (the single-city input was replaced by the chips input in §Phase 11c);
   - comp min 8000, max 12000, INR, unit `day`;
   - `opp-partner-select` shows Zenvia, and the public partner name is `A Pune edtech`;
   - at least 5 `drafted-chip-*` are visible, and `draft-cost-line` contains `$`;
   - the description textarea contains no `Zenvia`, no `@` email and no phone number;
   - the status is still unsaved, and the public board has no new card.
4. **Publish:** edit the title → its chip disappears → **Publish** → Open.
5. **Public check (fresh context):** the card's `opportunity-compensation` reads exactly `₹8,000–12,000 / day`, and so does the listing's. The partner is shown as `A Pune edtech`. `page.content()` contains neither `Zenvia` nor `ZZ-PARTNER-NOTE`.
6. **Format vectors:** three more listings are created via the admin API, and each listing page shows the exact string:
   - `{50, null, USD, hour}` → `From $50 / hour`;
   - `{null, 150000, INR, month}` → `Up to ₹1,50,000 / month`;
   - `{20000, 20000, INR, course, note "plus travel"}` → `₹20,000 / course · plus travel`.
7. **Not-configured state:** in a fresh page, `page.route('**/api/admin/opportunity-draft/config')` answers `{"data":{"available":false,"model":"claude-sonnet-5-5"},"error":null}`. This mocks the UI state only; the real keyless path is proven by F4's integration tests. Then `paste-not-configured` is visible, `paste-draft-button` is disabled, and a listing can still be typed, saved as a draft and published.

**Gate addendum (run after the Phase-11 block, in the same shell with the same exports, and with the Phase-11 server already killed):**

```bash
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic current | grep -q '^0007'
uv run pytest tests/integration/test_migration.py tests/integration/test_partners_admin.py tests/integration/test_board_partner_link.py tests/integration/test_board_compensation.py tests/integration/test_board_leak.py tests/unit/test_opportunity_draft_guardrails.py -q
! uv run pytest tests/integration/ai_network/test_opportunity_draft.py tests/integration/ai_network/test_opportunity_draft_api.py -q -rs | grep -q SKIPPED   # real Anthropic, none skipped
uv run pytest tests/integration/ai_network/test_opportunity_draft.py tests/integration/ai_network/test_opportunity_draft_api.py -q          # zero failures
! grep -il openrouter src/workshop0/ai/opportunity_draft.py
! grep -nE 'Partner|partner_id|partners' src/workshop0/api/board_public.py           # public router never touches partners
test -f src/workshop0/ai/prompts/opportunity_draft_system.md && test -f src/workshop0/ai/prompts/opportunity_draft_user.md
test -f frontend/out/admin/partners/index.html
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" uv run python -m src &
sleep 3
for u in /api/admin/partners /api/admin/opportunity-draft/config; do curl -sS -o /dev/null -w '%{http_code}\n' "http://localhost:8001$u" | grep -qx 401; done
curl -fsS -H "X-Admin-Key: $WORKSHOP0_ADMIN_KEY" http://localhost:8001/api/admin/opportunity-draft/config | uv run python -c 'import json,sys; d=json.load(sys.stdin)["data"]; assert d["available"] is True and d["model"]=="claude-sonnet-5-5", d'
pnpm exec playwright test tests/e2e/opportunity-drafting.spec.ts tests/e2e/opportunity-board.spec.ts --reporter=line
curl -fsS 'http://localhost:8001/api/public/opportunities?page_size=50' > /tmp/w0-public.json             # after e2e: published listings with sentinel partners exist
uv run python -c 'import json; d=json.load(open("/tmp/w0-public.json"))["data"]; assert d["total"]>=1; assert any(o.get("compensation_unit")=="day" for o in d["opportunities"]), "no structured compensation on the board"'
! grep -qE 'ZZ-INTERNAL|ZZ-PARTNER-NOTE|Zenvia|partner_internal_name|"partner_id"|"partner"|name_key|internal_notes' /tmp/w0-public.json
kill %1
```

**Addendum conditions (tests in F1–F4 must contain, beyond the commands):**
- *Migration:* existing free-text partners migrate into deduplicated partner rows with the exact grouping above, and the downgrade works.
- *No leak:* `partner_internal_name`, partner notes, `name_key`, `partner_id` and `internal_notes` never appear in any public payload, nor in the rendered public HTML (e2e).
- *Drafter, against the real `claude-sonnet-5-5`:* the four fixtures' expectations hold; the **prompt-injection** post still yields only curated slugs, enum values, no internal partner name in public fields and no listing row created; topics always come from the curated active list; each call writes one `ai_usage` row with `purpose="opportunity_draft"`, `model` = the configured id, nonzero tokens, `cost_usd == pricing.cost_usd(...) > 0`, `opportunity_id` = the request's id or null, and the event `ai.opportunity_draft`.
- *Keyless:* keyless and key-without-workspace runs (`network_ai_disabled`) → config `available: false`, POST → 503 `ai_not_configured`, zero HTTP requests and no `ai_usage` row, and manual create/publish still works.
- *Compensation display:* the exact strings in capabilities.md §C10, checked by e2e.

**How the user tests it (11b, during the Phase-11 handoff, same setup):**
1. **http://localhost:8001/admin** → **Opportunities** → open any listing → next to the partner field click **Manage partners** (the header also gains **Partners** once the Trainer-network nav lands). Your Phase-10 free-text partner names are already there, one row per distinct name (case and extra spaces merged), with listing counts.
2. **Add partner** "Zenvia Learning Pvt Ltd", default public name "A Pune edtech", and a note. Add "zenvia learning pvt ltd" again → rejected. Rename one partner and deactivate another → the deactivated one disappears from the editor's dropdown, but listings that already use it still show it.
3. **+ New opportunity** → paste a real forwarded email from a partner into **Paste the forwarded description** (or use `tests/fixtures/opportunity_posts/forwarded_genai_workshop.txt`) → **Draft**. Within ~15 s:
   - the form fills in: title, type, Remote/Hybrid/Onsite and city, dates and deadline, topics (only from your list), compensation with its unit, and the partner (matched, or offered as "Suggested new partner — Add");
   - every filled field shows an amber **Drafted — please check** chip;
   - a cost line shows the model and the cost;
   - the public description no longer names the partner and has no email or phone; those details are in the internal notes;
   - nothing is saved yet.
   Fix anything, then **Save draft** → **Publish**.
4. Private window → **http://localhost:8001/opportunities** → the card and the listing show e.g. "₹8,000–12,000 / day" and "A Pune edtech", and never the partner's real name or your note.
5. Compensation: set **per course**, then **per month**. Enter an amount without a currency → an inline error.
6. **Not configured:** comment out `ANTHROPIC_WORKSPACE_ID` in `.env` and restart → the paste box says **AI drafting not configured**, and typing a listing by hand, saving and publishing all still work. Restore the line and restart.
7. **Trainer network → Network AI spend** (S11's card) now includes the `opportunity_draft` calls.

**Labelled stubs (not bugs):** none new in 11b.

### Phase 11c — Multi-location opportunities

*An incremental sub-phase after Phase 11/11b, which are built and on `main`. It has its own human test. Linear SMA-9. It does not change the scope of Phase 12 or 13. The only knock-on effects are that their migrations are renumbered `0009`/`0010` and that Phase-12 "same city" matching means "any listed city" (agent.md §Shortlist ranker).*

**Goal:** An admin gives a listing several cities. For example, a Hybrid workshop runs in **Bengaluru (India), Pune and Hyderabad**. The admin adds them as chips in the editor, with the country optional, and duplicates are ignored. The public card reads **`Bengaluru · Pune · +1 · Hybrid`** and the listing page lists every location. Pasting a partner post that names several venue cities drafts all of them, and leaves out the cities that are only where remote participants, the head office or the signature are. Existing single-city listings, clients and tests keep working unchanged.

**Capabilities extended (no new numbers):** C9 gains **multi-location listings** (the editor chips input, the rules and the multi-city drafting). C10 gains the **multi-location display**. Contract: [api.md](api.md) §Phase 11c. Schema: [data-model.md](data-model.md) §Phase 11c. Drafter: [agent.md](agent.md) §Opportunity drafter. UI and exact strings: [capabilities.md](capabilities.md) §C9 additions — Phase 11c / §C10 → Location display.

> **Assumed:** this is feedback on delivered capabilities, so C9/C10 are extended and no C20 is added. The capability count is unchanged, and the Phase-11b precedent applies.

**Non-goals (explicit):**
- **No location or city filter.** None exists today on the public board (`type`, `topic`, `sort`) or the admin list (`status`, `type`, `q`), so none is added, and admin `q` does not start matching cities (api.md §Phase 11c → Filters);
- **trainer profiles keep a single `city`** (`trainer_profile.city`, the profile form, the pool, the CV drafter). Trainer locations are out of scope;
- no country list, autocomplete, geocoding or city normalization beyond trim, collapsing whitespace and case-insensitive dedupe;
- no per-location dates, capacity or work mode. `location_mode` stays one value per listing, and remote listings carry no cities;
- no change to Phase 12/13 scope, and the `city` column is not dropped (it stays as a mirror);
- no new endpoint, error code, dependency, setting or environment variable.

**Mini-scaffold (orchestrator, one commit, before the fan-out; see §Parallel fan-out rule):**
- **Python stub `src/workshop0/services/locations.py`**, owned and filled by M2. The constants are real in the stub, and function bodies `raise NotImplementedError`:
  - `CITY_MAX = 80`, `COUNTRY_MAX = 80`, `LOCATIONS_MAX = 10`;
  - `class Location(TypedDict): city: str; country: str | None`;
  - `collapse(text: str) -> str`: trims and collapses internal whitespace to single spaces;
  - `location_key(city: str, country: str | None) -> tuple[str, str]`: returns `(collapse(city).casefold(), collapse(country or "").casefold())`;
  - `dedupe(locations: list[Location]) -> list[Location]`: order-preserving, first wins, and every item rebuilt with exactly `city`/`country`;
  - `parse_stored(locations_json: str | None, city: str | None, location_mode: str) -> list[Location]`: the read rule in data-model.md §Phase 11c;
  - `dump(locations: list[Location]) -> str`: `json.dumps(locations, ensure_ascii=False)`.

No TypeScript stub is needed, because one slice owns all of the frontend.

**Slices.** M1 runs first. It is small, and every DB test needs its column. M2, M3 and M4 then fan out concurrently, which is 3 slots. M5 is written in the same wave if a 4th slot is free, otherwise right after. Its verification waits for M1–M4. Build dependencies are none, because M3 builds against the `locations.py` stub.

| Slice | Owns (exclusive paths) | Delivers | Tests need |
|---|---|---|---|
| **M1 schema-locations** | `src/workshop0/db/models.py`, `alembic/versions/0008_multi_location.py`, `tests/integration/test_migration.py` | `Opportunity.locations_json` (`Text`, not null, `default="[]"`, `server_default="[]"`) and migration `0008` (`revision = "0008"`, `down_revision = "0007"`, `batch_alter_table`) with the data migration and downgrade, exactly per data-model.md §Phase 11c. `test_migration.py`: every "0007 is head" assertion becomes `0008`; `EXPECTED_TABLES` is unchanged (no new table); plus the 0008 tests below. `tests/integration/test_sqlite_to_postgres.py` must stay green **without being edited** | — |
| **M2 opportunity-api** | `src/workshop0/services/locations.py` (fills the stub), `src/workshop0/services/opportunities.py`, `tests/unit/test_locations.py` (new), `tests/unit/test_board_rules.py`, `tests/integration/test_board_locations.py` (new), `tests/integration/test_board_{admin,public,leak,audit}.py` (edited only where the contract changed: the payload key sets gain `locations`, and the leak test adds the `locations_json` key and the item-shape check) | The `locations` request field with the validation and messages in api.md §Phase 11c, legacy `city` → one-element list (`locations` wins when both are sent), merged-state mode rules with the body-dependent required message, and the `city` mirror written on every write. `FIELDS` reports `locations` instead of `city` in `changed_fields`, comparing order-sensitive normalized lists. `locations` is added to `public_card`, `admin_row` and `admin_full` through `parse_stored`, with `city` derived from it. `api/board_admin.py`, `api/board_public.py` and `tests/conftest.py` stay **read-only**: the shared `opportunity_body` fixture keeps sending the legacy `city`, which still works | M1 |
| **M3 opportunity-drafter** | `src/workshop0/ai/opportunity_draft.py`, `src/workshop0/ai/prompts/opportunity_draft_{system,user}.md`, `tests/unit/test_opportunity_draft_guardrails.py`, `tests/integration/ai_network/test_opportunity_draft.py`, `tests/integration/ai_network/test_opportunity_draft_api.py`, `tests/fixtures/opportunity_posts/**` | Schema `locations` array (replacing `city`), the location prompt rules, the location guardrail (using `locations.location_key`/`collapse`) and contact scrub, the `draft.locations` key and `drafted_fields` → `location` coverage, all per agent.md §Opportunity drafter and api.md §Phase 11c → Drafting response. New fixture `multi_city_bootcamp.{txt,expected.json}`. The four existing `*.expected.json` swap `"city"` for `"location_cities"` (+ `"location_cities_exclude": ["hyderabad"]` on the forwarded GenAI post). **`injection.txt` is not edited**, and its new assertions are in agent.md. The `DRAFT_KEYS` sets in both test files swap `city` for `locations` | M2 (`locations.py`), M1 (the API test creates a listing) |
| **M4 frontend** | `frontend/lib/locations.ts` (new; the **only** location formatter), `frontend/lib/board.ts`, `frontend/lib/adminBoard.ts`, `frontend/lib/adminDraft.ts`, `frontend/components/admin/LocationsInput.tsx` (new), `frontend/components/admin/OpportunityEditor.tsx`, `frontend/components/admin/PublicCardPreview.tsx`, `frontend/components/board/OpportunityCard.tsx`, `frontend/app/opportunities/view/page.tsx` | `lib/locations.ts` exports `interface Location {city: string; country: string \| null}`, `LOCATIONS_MAX`/`CITY_MAX`/`COUNTRY_MAX`, `locationKey(l)`, `addLocations(current, cityInput, countryInput): {next: Location[]; duplicate: boolean; error: string \| null}` (comma-splits, collapses, dedupes, caps at 10; errors `"City must be 80 characters or fewer"` / `"Country must be 80 characters or fewer"`), `locationLabel(o)`, `locationDetailLabel(o)` and `locationTitle(locations)`, with the exact strings in capabilities.md §C10. `board.ts` loses its `locationLabel`, and every importer switches to `lib/locations.ts`. The public and admin types gain `locations: Location[]` and keep `city` as read-only. `OpportunityBody` sends `locations` and no longer sends `city`. `OpportunityDraft.city` is replaced by `locations`. Editor: the `LocationsInput` chips UI replaces the City input (capabilities.md §C9 additions — Phase 11c), `FormState.city` becomes `locations: Location[]`, `toBody` sends `[]` while Remote, `diffBody`/`rebase` compare `locations` **in order** (JSON equality, not the sorted compare used for `topic_ids`), `locations:` and `city:` server errors map to `opp-locations-error`, and a draft maps `d.locations` into the chips. `PublicCardPreviewData.city` becomes `locations`. The card, the listing meta grid and the preview use the shared formatter | runtime only (M1–M3) |
| **M5 e2e-docs** | `tests/e2e/opportunity-locations.spec.ts` (new), `tests/e2e/opportunity-board.spec.ts`, `tests/e2e/opportunity-drafting.spec.ts`, `README.md` | The journey below. In `opportunity-board.spec.ts`, the editor helper's `opp-city-input` fill becomes "type the city into `opp-location-city-input`, press Enter, expect one `opp-location-chip`", and its API seeding keeps the legacy `city`. In `opportunity-drafting.spec.ts`, the `opp-city-input` fallback becomes: after the draft, `opp-location-select` has the value `hybrid`, `opp-location-chip` has a count of 1 with the text `Pune`, and no chip contains `Hyderabad`; the chip-based "add Pune if empty" fallback is kept only for the publish step. `tests/e2e/helpers.ts` stays read-only. README: the Opportunity Board section gains one paragraph on multiple locations (chips, the card rule, drafting), and its gate snippet's `grep -q '^0007'` becomes `'^0008'` | runtime: all |

> **Assumed:** M4 is one frontend slice rather than an editor/board split. The board edits are about 30 lines, and one owner of `lib/locations.ts` avoids a TS stub. This keeps the fan-out within the 3–4 concurrent generators available.

**Test-id contract (M4 renders these; M5 asserts them):**

| Surface | Test ids |
|---|---|
| Editor locations | `opp-locations` (wrapper, shown only for Onsite/Hybrid), `opp-location-city-input`, `opp-location-country-input`, `opp-location-add`, `opp-location-chip` (one per chip, in order), `opp-location-chip-label` (inside each chip; text exactly `City` or `City, Country`, which is what e2e compares), `opp-location-chip-remove` (inside each chip; an icon button whose only name is its `aria-label`), `opp-locations-hint` (`Already added` / `Up to 10 locations`), `opp-locations-error` |
| Admin preview | `opp-preview-location` (the location text, e.g. `Bengaluru · Pune · +1 · Hybrid`) |
| Card + listing | `opportunity-location`: the card's location `dd` (with the `title` attribute) and the listing meta-grid value |
| Kept | `opp-location-select`, `drafted-chip-location` |
| Removed | `opp-city-input` |

**Tests the backend slices must write (PostgreSQL; real Anthropic where stated):**
- **Migration (M1):**
  - *Fixture at `0007`:* five listings: onsite `"Pune"`; hybrid `"  Navi   Mumbai "`; remote with `city` null; onsite `"   "`; hybrid `"Zürich"`.
  - *Upgrade:* `upgrade head` → parsed `locations_json` is `[{"city":"Pune","country":null}]`, `[{"city":"Navi Mumbai","country":null}]`, `[]`, `[]` and `[{"city":"Zürich","country":null}]`, and every `city` value is unchanged. Head is `0008`.
  - *Downgrade:* set one row's `locations_json` to Bengaluru/Pune/Hyderabad with `city = "Stale"` → `downgrade 0007` → that row's `city == "Bengaluru"`, the column is gone, and the other rows' `city` is unchanged.
  - *Re-upgrade:* that row comes back as `[{"city":"Bengaluru","country":null}]`, which is the documented loss.
- **Locations unit (M2, `test_locations.py`):**
  - `collapse`;
  - `location_key` (case, whitespace, country in the key);
  - `dedupe` (first wins, order, exact keys);
  - `parse_stored` returns the list when it is non-empty;
  - with `[]` + city + onsite it returns the fallback;
  - with `[]` + city + remote it returns `[]`;
  - with invalid JSON + city + hybrid it returns the fallback;
  - with `None` + no city it returns `[]`.
- **API (M2, `test_board_locations.py`):**
  - *Round trip:* POST hybrid with `[{Bengaluru, India}, {Pune}, {Hyderabad}]` → admin and public payloads have exactly that list in order and `city == "Bengaluru"`; the DB `city` mirror is `"Bengaluru"`.
  - *Normalization and dedupe:* `[" pune ", "PUNE", {"Pune","India"}]` → 2 entries; `"  New   Delhi "` → `"New Delhi"`.
  - *Bounds:* 10 is accepted; 11 distinct → `locations: at most 10 locations`; 11 with one duplicate is accepted with 10 stored; an 81-char city or a blank city → `locations: city must be 1–80 characters`; an 81-char country → the country message; an extra key `state`, a string instead of an array, or `[{"country": "India"}]` → `locations: each location needs a city and an optional country`. Nothing is written on any rejection.
  - *Mode rules:* onsite + `locations: []` → `locations: add at least one city for onsite or hybrid`; onsite with neither field → `city: required for onsite or hybrid`; remote + 2 locations → stored `[]` and `city` null; PATCH hybrid→remote → `[]`; PATCH remote→onsite with no locations → `city: required for onsite or hybrid`.
  - *Legacy:* POST onsite `city: "Pune"` → `[{"city":"Pune","country":null}]`; PATCH `city: "Mumbai"` on a 3-location listing → `[{Mumbai}]` with `changed_fields == ["locations"]`; both fields sent → `locations` wins.
  - *Audit:* a reorder → one `opportunity.update` with `changed_fields == ["locations"]`; the same list again, or a legacy `city` equal to the sole location → no audit row and `updated_at` unchanged.
  - *Read rule:* a row written by raw SQL with `locations_json='[]'`, `city='Pune'`, `location_mode='onsite'` → the public card has `locations == [{"city":"Pune","country":null}]`.
- **Leak (M2, extends `test_board_leak.py`):** every public response (topics, list for every type, detail of open, expired and closed listings) still contains none of the Phase-10/11b sentinels or keys, and now also no `locations_json` key; every `locations` item has exactly the keys `{"city", "country"}`.
- **Drafter (M3):** the agent.md §Opportunity drafter → Testing additions: the location guardrail unit cases; all five fixtures against the real `claude-sonnet-5-5`, including the exact `["pune"]` (Hyderabad excluded) and the three-city bootcamp with Mumbai and Chennai excluded; and the unchanged prompt-injection fixture with its new `locations` shape assertions. Every call still writes one `ai_usage` row with `purpose="opportunity_draft"` and `cost_usd > 0`.

**e2e journey (M5, `tests/e2e/opportunity-locations.spec.ts`, `test.describe.serial`, live single-origin app, admin key from the env as in the existing specs, per-run suffixes because the e2e DB is not reset; `workers: 1`):**
1. **Chips:** sign in at `/app/admin/` → **New opportunity**. Fill the required fields with title `Multi-city <run>` and internal notes `ZZ-INTERNAL-<run>`, then choose Hybrid.
   - In `opp-location-city-input` type `Bengaluru`, in `opp-location-country-input` type `India`, and press Enter. Then type `Pune,` (the comma adds it), fill `Hyderabad, pune` (the comma adds `Hyderabad` and leaves `pune` in the input), and press Enter.
   - The chips are exactly [`Bengaluru, India`, `Pune`, `Hyderabad`], `opp-locations-hint` shows `Already added`, and the City input is empty.
   - `opp-preview-location` reads `Bengaluru · Pune · +1 · Hybrid`.
2. **Remove and re-add:** remove `Pune` → the preview reads `Bengaluru · Hyderabad · Hybrid`. Re-add `Pune` → the chips are [`Bengaluru, India`, `Hyderabad`, `Pune`].
3. **Remote toggle:** switch to Remote → `opp-locations` is hidden and the preview reads `Remote`. Switch back to Hybrid → the same 3 chips are back.
4. **Blur commit and publish:** type `Chennai` without pressing Enter, then click **Publish**. The POST response has `locations` = Bengaluru (India), Hyderabad, Pune, Chennai in that order, and `city == "Bengaluru"`.
5. **Public check (fresh context):** on `/app/opportunities/?sort=newest`, the card with this title has `opportunity-location` text exactly `Bengaluru · Hyderabad · +2 · Hybrid` and `title` = `Bengaluru, Hyderabad, Pune, Chennai`. Its listing page has `opportunity-location` = `Bengaluru, India · Hyderabad · Pune · Chennai · Hybrid`. `page.content()` contains neither `ZZ-INTERNAL` nor `locations_json`.
6. **Format vectors:** published via the admin API, each checked on its card (page 1, newest) and its listing page:
   - legacy body `{onsite, city: "Pune"}` → card `Pune · Onsite`, listing `Pune · Onsite`;
   - `{hybrid, [Bengaluru, Pune]}` → `Bengaluru · Pune · Hybrid`;
   - `{onsite, [Delhi, Noida, Gurugram, Jaipur, Agra]}` → card `Delhi · Noida · +3 · Onsite`, listing `Delhi · Noida · Gurugram · Jaipur · Agra · Onsite`;
   - remote → `Remote` on both.
7. **Errors:**
   - on a new Onsite listing with no chips → **Save draft** → `opp-locations-error` contains `add at least one city`, and nothing typed is lost;
   - adding 10 chips → `opp-location-city-input` is disabled and `opp-locations-hint` reads `Up to 10 locations`;
   - an 81-char city + Enter → `opp-locations-error` reads `City must be 80 characters or fewer` and no chip is added.
8. **Editing a legacy listing:** open the step-6 legacy `Pune` listing in the editor → one chip, `Pune`.

**Gate (exact commands, serial; working directory = the repo root `/Users/sai/workspace/code/workshop0`; PostgreSQL via `TEST_DATABASE_URL`. The real Anthropic key and workspace id are read from the gitignored `.env` by `envval` and never echoed. Background processes are tracked by explicit PIDs and killed at the end, and also on any early exit):**

```bash
export TEST_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/workshop0_test"
export WORKSHOP0_ADMIN_KEY="${WORKSHOP0_ADMIN_KEY:-phase11c-local-gate-key-0123}"
envval() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '"'"'"; }      # .env values are unquoted or simply quoted; never echoed
export ANTHROPIC_API_KEY="$(envval ANTHROPIC_API_KEY)" ANTHROPIC_WORKSPACE_ID="$(envval ANTHROPIC_WORKSPACE_ID)"
test -n "$ANTHROPIC_API_KEY" && test -n "$ANTHROPIC_WORKSPACE_ID"                      # BLOCKED (not skipped) without both
export WORKSHOP0_GOOGLE_CLIENT_ID=test-client WORKSHOP0_GOOGLE_CLIENT_SECRET=test-secret
export WORKSHOP0_OIDC_ISSUER=http://localhost:8099 WORKSHOP0_SESSION_SECRET="$(openssl rand -hex 32)"
export WORKSHOP0_ADMIN_EMAILS=admin@example.test WORKSHOP0_BLOB_BACKEND=local
OIDC_PID=""; SERVER_PID=""
cleanup() { for p in $SERVER_PID $OIDC_PID; do kill "$p" 2>/dev/null; wait "$p" 2>/dev/null; done; OIDC_PID=""; SERVER_PID=""; true; }
trap cleanup EXIT
uv sync
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head && DATABASE_URL="$TEST_DATABASE_URL" uv run alembic current | grep -q '^0008'   # 0008 = Phase 11c's M1
uv run python tests/support/fake_oidc.py --port 8099 & OIDC_PID=$!                    # real OIDC protocol, local issuer (Phase-11 e2e specs need it)
sleep 2
uv run pytest tests/unit tests/integration -q                                          # full regression, incl. ai_network/ (REAL Anthropic)
! uv run pytest tests/unit/ai tests/integration/ai_network -q -rs | grep -q SKIPPED   # real-key tests ran, none skipped
uv run pytest tests/integration/test_migration.py tests/integration/test_board_locations.py tests/integration/test_board_leak.py tests/integration/test_sqlite_to_postgres.py tests/unit/test_locations.py tests/unit/test_opportunity_draft_guardrails.py tests/integration/ai_network/test_opportunity_draft.py tests/integration/ai_network/test_opportunity_draft_api.py -q   # the 11c files exist and pass (a missing file fails)
test -f tests/fixtures/opportunity_posts/multi_city_bootcamp.txt && test -f tests/fixtures/opportunity_posts/multi_city_bootcamp.expected.json
! grep -l '"city"' tests/fixtures/opportunity_posts/*.expected.json                   # the single-city expectation key is gone
git diff --quiet "$(git merge-base HEAD origin/main)" -- tests/fixtures/opportunity_posts/injection.txt   # prompt-injection fixture untouched
grep -q 'locations' src/workshop0/ai/prompts/opportunity_draft_system.md
! grep -il openrouter src/workshop0/ai/opportunity_draft.py
! grep -nE 'Partner|partner_id|partners|locations_json' src/workshop0/api/board_public.py
! grep -rn 'opp-city-input' frontend/app frontend/components frontend/lib tests/e2e   # the single-city input is gone everywhere
grep -qF "'^0008'" README.md
(cd frontend && ASDF_NODEJS_VERSION=23.11.0 pnpm install && ASDF_NODEJS_VERSION=23.11.0 pnpm build)
for p in opportunities opportunities/view admin/opportunities/edit; do test -f "frontend/out/$p/index.html"; done
ASDF_NODEJS_VERSION=23.11.0 pnpm install && ASDF_NODEJS_VERSION=23.11.0 pnpm exec playwright install chromium
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" uv run python -m src & SERVER_PID=$!
sleep 3
curl -fsS http://localhost:8001/api/health > /dev/null
curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8001/api/admin/opportunities | grep -qx 401
ASDF_NODEJS_VERSION=23.11.0 pnpm exec playwright test tests/e2e --reporter=line        # every e2e spec, incl. opportunity-locations/-board/-drafting
PUB_JSON="$(mktemp)"
curl -fsS 'http://localhost:8001/api/public/opportunities?page_size=50' > "$PUB_JSON"   # after e2e: multi-city + legacy + remote listings are published
uv run python - "$PUB_JSON" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))["data"]
ops = d["opportunities"]
assert d["total"] >= 1 and ops, "empty board"
for o in ops:
    locs = o["locations"]
    assert isinstance(locs, list) and len(locs) <= 10, o["id"]
    assert all(set(l) == {"city", "country"} for l in locs), o["id"]
    assert o["city"] == (locs[0]["city"] if locs else None), o["id"]
    assert o["location_mode"] != "remote" or locs == [], o["id"]
assert any(len(o["locations"]) >= 3 for o in ops), "no multi-city listing on the board"
PY
! grep -qE 'locations_json|ZZ-INTERNAL|ZZ-PARTNER-NOTE|Zenvia|partner_internal_name|"partner_id"|"partner"|name_key|internal_notes' "$PUB_JSON"   # public no-leak
rm -f "$PUB_JSON"
kill "$SERVER_PID" "$OIDC_PID"; wait "$SERVER_PID" "$OIDC_PID" 2>/dev/null || true; SERVER_PID=""; OIDC_PID=""
sleep 1
! curl -s -o /dev/null --max-time 2 http://localhost:8001/api/health                  # server really stopped
! curl -s -o /dev/null --max-time 2 http://localhost:8099/.well-known/openid-configuration   # fake issuer really stopped
trap - EXIT
```

**Gate conditions (beyond the commands; tests in M1–M3 must contain):**
- *Migration:* every pre-0008 single-city listing becomes exactly one location; remote and blank-city rows become `[]`; the downgrade restores `city` = the first location's city; `test_sqlite_to_postgres.py` passes unedited.
- *Compatibility:* legacy `city` writes and the `city` read field behave exactly as api.md §Phase 11c says, and every pre-11c board test still passes. The only edits to existing tests are the documented key-set additions and the moved expectation keys.
- *No leak:* `locations_json` and every Phase-10/11b internal key or sentinel are absent from every public payload and from the rendered public HTML (e2e). Location items have exactly `city` and `country`.
- *Drafter, against the real `claude-sonnet-5-5`:* all five fixtures' location expectations hold, including the excluded distractor cities. The prompt-injection post still yields only curated slugs and enum values, no internal partner name in public fields (locations included), well-shaped `locations` and no listing row.
- *Display:* the exact strings in capabilities.md §C10 → Location display, checked by e2e on the card and the listing page for 1, 2, 4 and 5 cities and for remote, and in the preview for 2 and 3 cities and for remote.

**How the user tests it (repo root; local SQLite as usual):**
1. `uv run alembic upgrade head`, then `uv run alembic current` prints `0008`. Then run `(cd frontend && pnpm build)` and `uv run python -m src`.
2. **http://localhost:8001/admin** → **Opportunities** → open an existing Onsite or Hybrid listing → its old city is now a single chip. Save → nothing changes on the board.
3. **+ New opportunity** → Hybrid → type `Bengaluru`, Country `India`, Enter → `Pune,` → `Hyderabad` Enter. Type `pune` again → "Already added". The preview reads **Bengaluru · Pune · +1 · Hybrid**. Remove a chip with **×** and add it back. Switch to Remote and back, and the chips survive. **Publish**.
4. Private window → **http://localhost:8001/opportunities** → the card reads **Bengaluru · Pune · +1 · Hybrid**, and hovering shows all three cities. Open it → Location reads **Bengaluru, India · Pune · Hyderabad · Hybrid**.
5. Make a listing Onsite and remove every chip → Save → the inline error asks for at least one city. A Remote listing saves with no city and shows **Remote**.
6. **Paste-to-fill:** in a new listing, paste `tests/fixtures/opportunity_posts/multi_city_bootcamp.txt` → **Draft** → Onsite with the chips **Bengaluru, Pune, Hyderabad** (not Mumbai or Chennai), with an amber "Drafted — please check" on Location. Paste `forwarded_genai_workshop.txt` → only **Pune** (the remote Hyderabad team is not a venue).
7. **Production:** no operator step. After the merge deploys, the `workshop0-migrate` job applies `0008`, and existing listings show their single city as before.

**Labelled stubs (not bugs):** none new in 11c. The existing ones are unchanged.

---

### Phase 11d — Invite flow fixes

*A fix-up of Phase 11's invites (C11/C13 extended, no new capability numbers). Branch `fix/invite-flow-v0.1`. Contract: [api.md](api.md) §Invite acceptance + §Phase 11d. Schema + status rules: [data-model.md](data-model.md) §network_invite. UI copy: [capabilities.md](capabilities.md) §C11/§C13.*

**Goal:** An admin can revoke a pending invite and never sees duplicate actionable invites; a trainer who is already signed in (even with a profile) can open an invite and apply it in one click, landing **Verified**; a used or revoked invite says so plainly instead of being silently ignored.

**Fixes:** (1) signed-in user with a profile opening an un-applied invite gets the **Use my invite** path, not a redirect (CODE bug — the join page redirects on `has_profile` before looking at the invite); (2) `invite_used` instead of silent ignore (`auth/routes.py::_check_invite`); (3) admin **Revoke** + `invite_revoked`; (4a) direct accept `POST /api/me/invite/accept` and corrected card copy; (4b) "sent" → "created"; (4c) one pending invite per email (re-use + refresh) and `superseded` status.

> **Assumed:** direct accept without a second Google round-trip is safe: the session already proves an IdP-verified email (`email_verified` was required at sign-in), and the endpoint applies exactly the callback's checks to that email.
> **Assumed:** `superseded` is derived (no column), so no data migration is needed for it; only `revoked_at`/`revoked_by` need migration `0008`.
> **Assumed:** revoking does not unverify anyone and accepted invites cannot be revoked (verification is managed by the existing Verify/Unverify buttons).
> **Assumed:** re-creating for an email with a pending invite renews the **same** token (the link the admin may already have shared keeps working) rather than rotating it.

**Migration / rebase flag:** `alembic/versions/0008_invite_revoke.py` (`revision = "0008"`, `down_revision = "0007"`) chains from the current head on `origin/main`. PR #10 (multi-location, another branch) also adds a `0008`. **Whichever merges second must renumber its migration to `0009` with `down_revision = "0008"`** (and bump the `alembic current | grep '^0008'` checks and `test_migration.py`'s head assertion to `0009`). Do not touch any multi-location file on this branch.

**Non-goals:** no invite email (Phase 12); no unverify-on-revoke; no invite deletion; no bulk revoke; no new settings or dependencies.

**Slices** (disjoint paths; F1/F2/E1 build against the api.md contract with **no build dependency**, so B1, F1, F2, E1 fan out concurrently):

| Slice | Owns (exclusive paths) | Delivers | Tests need | Build dependency |
|---|---|---|---|---|
| **B1 backend** | `src/workshop0/services/invites.py`, `src/workshop0/auth/routes.py`, `src/workshop0/api/network_admin.py` (invite routes only), `src/workshop0/api/network_me.py` (new accept route only), `src/workshop0/db/models.py` (two `NetworkInvite` columns), `alembic/versions/0008_invite_revoke.py`, `tests/integration/test_migration.py`, `tests/integration/auth/test_auth_invites.py`, `tests/integration/network/admin/test_invites_11d.py`, `tests/integration/network/test_invite_accept.py` | One shared `check_invite(session, token, email, user_id)` + `accept_invite(...)` in `services/invites.py` (moved from `auth/routes.py`, which now calls them) with the api.md ordering; `invite_used`/`invite_revoked` callback codes; `POST /api/me/invite/accept`; `POST /api/admin/network/invites/{id}/revoke`; create re-use/refresh + `invite_already_accepted`; `invite_status` with `revoked`/`superseded`; payload `revoked_at`/`revoked_by`; audit `invite.revoke`/`invite.refresh`; migration 0008 with downgrade; head assertion → `0008` | — | — |
| **F1 fe-join** | `frontend/app/network/join/page.tsx`, `frontend/components/network/auth/signinErrors.ts`, `frontend/lib/networkAuth.ts` (adds `acceptInvite(token): Promise<{invite_accepted: boolean; profile_verified: boolean}>`) | Join page: with an `invite` param and `!user.invite_accepted`, never redirect on `has_profile`; the invite card per capabilities.md §C11 (`data-testid="invite-card"`, button `invite-use`, error `invite-card-error` with `data-code`, `invite-go-profile`, existing `invite-verified`); `signinErrorMessage` gains `invite_used` and `invite_revoked` with the exact wording | runtime: B1 | — |
| **F2 fe-admin-invites** | `frontend/components/admin/network/InvitesPanel.tsx`, `frontend/lib/adminNetwork.ts` (InviteStatus + `revoked`/`superseded`, `revoked_at`/`revoked_by`, `reused`; `adminRevokeInvite(id)`) | "created … · expires …" copy; status badges Revoked (neutral) / Superseded (neutral); link + **Revoke** only on pending rows (`invite-revoke`, confirm `invite-revoke-confirm`); reused notice `invite-reused`; `invite_already_accepted` inline error | runtime: B1 | — |
| **E1 e2e-invites** | `tests/e2e/invite-flow.spec.ts` (new; `helpers.ts` and other specs read-only; private sign-in helper copied from `network-onboarding.spec.ts`) | Self-seeding, run-suffixed journeys via the fake OIDC issuer: (a) sign in as `t-<run>@example.test`, create a profile (Fill in the form yourself, no CV), admin creates an invite for that email, open `/invite/<token>` in the same context → `invite-card` visible (no redirect) → `invite-use` → `invite-verified` → `invite-go-profile` → My profile shows the verified badge; (b) a second account opens that accepted invite via a fresh context sign-in → `/app/signin/` `signin-error[data-code=invite_used]` with "This invite has already been used."; (c) admin creates an invite, **Revoke** in the panel → row shows Revoked with no link → open the link and sign in as the invited email → `signin-error[data-code=invite_revoked]`; (d) creating the same email twice shows `invite-reused` and the same URL; panel text contains "created" and no "sent" | runtime: all (B1, F1, F2) | — |

**Tests B1 must write (PostgreSQL):** callback: revoked → `error=invite_revoked`, no user/session; accepted by user A, then user B (any email) → `error=invite_used` (checked **before** email mismatch), no session; same user re-using → success no-op; superseded opened by the sibling's acceptor → success, row not stamped; superseded opened by a different email → `invite_email_mismatch`. Direct accept: 401 without session, 403 `csrf_failed` without the header, each error code above, success verifies an unverified profile + one `trainer.verify` audit, second call no-op. Revoke: pending → revoked + one `invite.revoke` audit, repeat → no new audit, accepted → 409, unknown → 404, without key → 401, cookie admin without header → 403. Create: pending twice → same id/token, `expires_at` renewed, `reused: true`, one `invite.refresh` audit; after acceptance → 409 `invite_already_accepted`; after revoke → a new row. Status: a sibling of an accepted invite lists as `superseded`. Migration: `upgrade head` → head `0008`, columns present; `downgrade 0007` drops them; re-upgrade works.

**Gate (exact; repo root; same exports as the Phase-11 gate block — `TEST_DATABASE_URL` PostgreSQL, admin key, Google test client id/secret, `WORKSHOP0_OIDC_ISSUER=http://localhost:8099`, session secret, `WORKSHOP0_ADMIN_EMAILS=admin@example.test`, local blobs, Anthropic values from `.env`):**

```bash
export TEST_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/workshop0_test"
uv sync
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head && DATABASE_URL="$TEST_DATABASE_URL" uv run alembic current | grep -q '^0008'
uv run python tests/support/fake_oidc.py --port 8099 &
sleep 2
uv run pytest tests/integration/test_migration.py tests/integration/auth tests/integration/network -q
uv run pytest tests/unit tests/integration -q                                   # full regression
(cd frontend && ASDF_NODEJS_VERSION=23.11.0 pnpm build)
DATABASE_URL="$TEST_DATABASE_URL" uv run python -m src &
sleep 3
curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8001/api/me/invite/accept | grep -qx 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8001/api/admin/network/invites/1/revoke | grep -qx 401
pnpm exec playwright test tests/e2e/invite-flow.spec.ts tests/e2e/admin-pool.spec.ts tests/e2e/network-onboarding.spec.ts --reporter=line
! grep -rn 'sent \${' frontend/components/admin/network/InvitesPanel.tsx
kill %2 %1
```

**How the user tests it:** same local setup as Phase 11 (`(cd frontend && pnpm build)`, `uv run python -m src`).
1. Sign in at **http://localhost:8001/network** with account A and create a profile (not verified). As admin (**/admin → Trainer network → Invites**) create an invite for A's email → the row says "created just now". Create it again → "An invite for this email already existed…", same link.
2. In A's browser open the link → the invite card (no jump to My profile) → **Use my invite** → **Verified** → **Go to My profile** shows the badge.
3. Open the same link in a private window signed in as account B → "This invite has already been used."
4. Create an invite for a third address → **Revoke** → confirm → row reads Revoked with no link; opening the link and signing in → "This invite has been withdrawn — ask smallTech for a new one."

**Labelled stubs (not bugs):** Email invite (Phase 12), unchanged.

---

## Phase 12 — Applications, Matching & Email Outbox

**Goal:** A signed-in trainer applies to a listing in one click and tracks the status; an admin gets a suggested shortlist for a listing, invites trainers to apply, moves applicants through the pipeline in bulk with status emails; every email goes through an outbox that sends over Gmail SMTP when configured and is recorded (and shown to admins, clearly labelled) when not.

**Capabilities delivered (3):** C14 Apply & applicant pipeline · C15 Matching (rule filters, suggested shortlist, invite to apply, matched for you) · C16 Email outbox & notifications. Design: agent.md §Shortlist ranker, architecture.md §Email, api.md §Phase 12, data-model.md §Phase 12.

**Stubs carried forward:** Saved searches & alerts, weekly digest, public directory toggle, workshop tie-in (→ 13). **Made real:** Sign in to apply, My applications, Matched for you, Applicants column, Suggested trainers, matching filters, Email invite, Outbox.

**Shared scaffold (orchestrator, one commit; §Parallel fan-out rule):**
- **Dependencies:** add `aiosmtpd` to the dev group, then run `uv lock`. No runtime dependency is added, because the Anthropic SDK is already present from Phase 11.
- **`.env.example` and `config/settings.py`:** add the Phase-12 variables to `.env.example`. Add the SMTP fields to `config/settings.py`: `workshop0_smtp_host`, `_port`, `_starttls`, `_user`, `_password`, `_from`.
- **Router shells:** register these in `create_app()`. `api/outbox_admin.py` (`prefix="/api/admin/outbox"`). `api/pipeline_admin.py` (`prefix="/api/admin/opportunities"`, applications routes). `api/matching_admin.py` (`prefix="/api/admin/opportunities"`, shortlist + invite-to-apply routes). All three use `require_admin_key`. The two routers share a prefix, but their paths are disjoint (`/{id}/applications…` vs `/{id}/shortlist`, `/{id}/invites`).
- **Python interface stubs** (agent.md §Shortlist ranker / architecture.md §Email):
  - `email/__init__.py` (empty package).
  - `email/sender.py`: `schedule_drain(background_tasks) -> None` (stub no-op) and `drain(limit: int = 20) -> int`.
  - `email/render.py`: `Rendered(subject, text, html)` and `render(template: str, context: dict) -> Rendered`.
  - `services/matching.py`: `Candidate`, `Match`, `eligible`, `rule_score`, `matches_for`.
  - `ai/shortlist_rank.py`: `ShortlistRun` and `run_shortlist(session, opportunity_id) -> ShortlistRun`.
- **TypeScript stub:** `frontend/components/admin/matching/SuggestedTrainersPanel.tsx` (`{opportunityId: number}`, renders `null`). It is used by both the editor and the pipeline page.

**Slices.** S0 runs first. S1–S18 then fan out concurrently, in waves over the cap. All of them build against the stubs.

| Slice | Owns (exclusive paths) | Delivers | Tests need |
|---|---|---|---|
| **S0 schema** | `src/workshop0/db/models.py`, `alembic/versions/0009_applications_matching_email.py`, `src/workshop0/email/outbox.py`, `tests/conftest.py`, `tests/integration/test_migration.py` | Phase-12 tables/columns, plus `enqueue(...)` (insert-only, with dedupe) | — |
| **S1 applications** | `src/workshop0/services/applications.py`, `src/workshop0/api/network_me.py`, `src/workshop0/api/pipeline_admin.py`, `tests/integration/applications/**` | Apply/withdraw/my-applications (`/api/me/applications…`), `/api/me/matches` (calls `matching.matches_for`), and the pipeline list, bulk status (one audit row, notify emails) and CSV routes. Every route here that enqueues email, including profile create in `network_me.py` (welcome enqueue lives in S7's `profiles.py`), calls `sender.schedule_drain(background_tasks)` | S0, S2, S6 |
| **S2 matching-rules** | `src/workshop0/services/matching.py` (fills the stub), `tests/integration/matching/**`, `tests/fixtures/network_pool.py` | Prefilter, rule score, `eligible`, `matches_for`. The shared 60-profile fixture `seed_pool()` has an eligible set of exactly 17 and one obvious best | S0 |
| **S3 shortlist-ranker** | `src/workshop0/ai/shortlist_rank.py` (fills the stub), `src/workshop0/ai/prompts/shortlist_rank_{system,user}.md`, `tests/integration/ai_network/test_shortlist_rank.py` | `run_shortlist`: top 40 by rule score → one real Anthropic call (`claude-sonnet-5-5`, Phase-11 client, `record_usage`) → guardrails → `match_suggestion` rows. Falls back to ranking by rules | S0, S2 |
| **S4 matching-admin-api** | `src/workshop0/api/matching_admin.py`, `src/workshop0/api/network_admin.py`, `tests/integration/admin_matching/**` | `POST/GET …/{id}/shortlist` (rate limit 20/h global), `POST …/{id}/invites` (rows + `opportunity.invite` emails), and the extended trainer-pool rule filters on `/api/admin/network/trainers`. The invite-create route in `network_admin.py` and the invite-to-apply route call `schedule_drain` | S0, S2, S3, S6 |
| **S5 opportunity-budget** | `src/workshop0/api/board_admin.py`, `src/workshop0/services/opportunities.py`, `tests/integration/test_board_budget.py` | Admin budget + `min_level` fields (validation, admin-only serialization, leak test on public payloads) and `applicant_count` on admin rows (api.md §Phase 12) | S0 |
| **S6 email-sender** | `src/workshop0/email/{sender,smtp}.py` (fills the stub), `src/workshop0/api/outbox_admin.py`, `tests/integration/email/**` | Drain (claims rows with `SKIP LOCKED`, sends via SMTP, retries 3× then `failed`, or `recorded` when SMTP is unset), `schedule_drain`, the outbox list/retry routes, and drain-on-page-load | S0, S7 |
| **S7 email-content** | `src/workshop0/email/render.py` (fills the stub), `src/workshop0/email/templates/**`, `src/workshop0/services/{invites,profiles}.py`, `tests/unit/test_email_templates.py`, `tests/integration/email_enqueue/**` | `render` plus the 5 templates. Every link is absolute and the subject comes from the first line. Adds the `network.invite` enqueue on invite create and `network.welcome` on profile create | S0, S6 |
| **S8 fe-apply** | `frontend/app/opportunities/**`, `frontend/components/board/**`, `frontend/lib/apply.ts` | The listing's apply panel: signed-out, no-profile and applied states, the note field, and the status chip. **Sign in to apply** becomes real | — |
| **S9 fe-my-network** | `frontend/app/network/{applications,matches}/**`, `frontend/app/network/me/**` (stub cards → real links only), `frontend/components/network/applications/**`, `frontend/lib/networkApplications.ts` | My applications timeline + withdraw, and Matched for you with Invited badges | — |
| **S10 fe-admin-pipeline** | `frontend/app/admin/opportunities/pipeline/**`, `frontend/app/admin/opportunities/page.tsx` (Applicants column), `frontend/components/admin/pipeline/**`, `frontend/lib/adminPipeline.ts` | Pipeline grouped by status, multi-select **Move to…** with the email toggle, CSV, and the embedded `SuggestedTrainersPanel` (stub import) | — |
| **S11 fe-admin-matching** | `frontend/components/admin/matching/**` (fills the stub), `frontend/components/admin/OpportunityEditor.tsx`, `frontend/app/admin/opportunities/edit/**`, `frontend/app/admin/network/**`, `frontend/components/admin/network/**`, `frontend/lib/{adminBoard,adminNetwork}.ts` | The Suggested trainers panel (reasons, rule score, run cost, "Ranked by rules" label, invite single/bulk), editor budget/min-level fields and the Suggested button, and the pool's matching filters + Email invite | — |
| **S12 fe-admin-outbox** | `frontend/app/admin/outbox/**`, `frontend/components/admin/outbox/**`, `frontend/lib/adminOutbox.ts`, `frontend/app/admin/page.tsx` (Outbox nav only) | The Outbox page with the "not configured" banner and Retry. The Outbox nav becomes real | — |
| **S13 e2e-apply-pipeline** | `tests/e2e/apply-pipeline.spec.ts` | Apply → pipeline bulk move → status visible to the trainer (self-seeding) | runtime: all |
| **S14 e2e-matching** | `tests/e2e/matching.spec.ts` | Suggested trainers (real Anthropic) → invite → Invited badge in Matched for you (self-seeding) | runtime: all |
| **S15 e2e-outbox** | `tests/e2e/outbox.spec.ts` | Outbox rows `sent` via the aiosmtpd sink, and Retry on a failed row (self-seeding) | runtime: all |
| **S16 infra-provision** | `deploy/cloudrun/provision.sh` | `workshop0-smtp-password` (SKIPPED rule, per-secret IAM). Written and `bash -n` only | — |
| **S17 infra-workflows** | `.github/workflows/**` | The `WORKSHOP0_SMTP_USER` variable and conditional SMTP secret mapping. CI starts aiosmtpd for e2e | — |
| **S18 docs** | `README.md`, `deploy/RUNBOOK.md` | README email setup, including the Gmail app-password steps | — |

> **Assumed:** applications and matching each get their own router shell instead of sharing `network_admin.py`, so no two slices edit one router file. Pipeline/shortlist URLs are unchanged from api.md. Each e2e spec seeds its own data through the API and keeps its helpers private.

**Gate (repo root; as Phase 11, plus a real local SMTP sink):**

```bash
export TEST_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/workshop0_test"
export WORKSHOP0_ADMIN_KEY="${WORKSHOP0_ADMIN_KEY:-phase12-local-gate-key-0123}"
envval() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '"'"'"; }
export ANTHROPIC_API_KEY="$(envval ANTHROPIC_API_KEY)" ANTHROPIC_WORKSPACE_ID="$(envval ANTHROPIC_WORKSPACE_ID)"
test -n "$ANTHROPIC_API_KEY" && test -n "$ANTHROPIC_WORKSPACE_ID"                      # BLOCKED (not skipped) without both
export WORKSHOP0_GOOGLE_CLIENT_ID=test-client WORKSHOP0_GOOGLE_CLIENT_SECRET=test-secret WORKSHOP0_OIDC_ISSUER=http://localhost:8099
export WORKSHOP0_SESSION_SECRET="$(openssl rand -hex 32)" WORKSHOP0_ADMIN_EMAILS=admin@example.test WORKSHOP0_BLOB_BACKEND=local
export WORKSHOP0_SMTP_HOST=localhost WORKSHOP0_SMTP_PORT=8025 WORKSHOP0_SMTP_STARTTLS=0 WORKSHOP0_SMTP_USER=bot@example.test WORKSHOP0_SMTP_PASSWORD=x
uv sync
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head && DATABASE_URL="$TEST_DATABASE_URL" uv run alembic current | grep -q '^0009'   # 0008 = Phase 11c
uv run python tests/support/fake_oidc.py --port 8099 &
uv run python -m aiosmtpd -n -l localhost:8025 &
sleep 2
uv run pytest tests/unit tests/integration -q                                          # incl. real-Anthropic shortlist ranking
! uv run pytest tests/unit/ai tests/integration/ai_network -q -rs | grep -q SKIPPED   # real-key tests ran, none skipped
! grep -rn --include='*.py' 'Anthropic(' src | grep -v '^src/workshop0/ai/anthropic_client.py:'
! grep -il openrouter src/workshop0/ai/shortlist_rank.py
(cd frontend && pnpm install && pnpm build)
for p in network/applications network/matches admin/opportunities/pipeline admin/outbox; do test -f "frontend/out/$p/index.html"; done
grep -q '\.flex' frontend/out/_next/static/css/*.css && ! grep -q '@source' frontend/out/_next/static/css/*.css
pnpm install && pnpm exec playwright install chromium
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" uv run python -m src &
sleep 3 && pnpm exec playwright test tests/e2e --reporter=line
kill %3 %2 %1
bash -n deploy/cloudrun/provision.sh
```

**Gate conditions beyond the commands:** one application per (listing, trainer); `opportunity_closed` for expired/closed; a bulk move of 12 applicants → one audit row + exactly 12 outbox rows, re-run → still 12 (dedupe); emails are delivered to the aiosmtpd sink and marked `sent`; with `WORKSHOP0_SMTP_USER` unset every enqueue ends `recorded` and no request fails; a failing SMTP (port closed) → `failed` after 3 attempts, Retry re-queues; agent.md ranker assertions on the 60-profile fixture against the real `claude-sonnet-5-5` (eligible set of exactly 17; obvious best in top 3; one `ai_usage` row with `cost_usd > 0` and the shortlist response's `cost_usd` equal to it); keyless and key-without-workspace (`network_ai_disabled`) → "Ranked by rules", zero requests, `cost_usd` 0; matched-for-you ranks a 3-listing fixture in the precomputed order; every email link is absolute.

**How the user tests it:** with the Phase-11 setup: as a trainer open a listing → **Apply** with a note → My applications shows *Applied*. As admin open the listing's **Applicants** → select it → **Move to Shortlisted** (email on) → the trainer's page shows *Shortlisted* → open **Outbox**: without SMTP configured the banner reads "Email sending isn't configured — messages are recorded here, not sent" and the status email is listed as *recorded*. On a listing, **Suggested trainers** → up to 10 trainers with reasons and the run cost → **Invite to apply** → the trainer sees an *Invited* badge in **Matched for you**. **Real email (manual):** create a Gmail app password (Google Account → Security → 2-Step Verification on → App passwords → "Workshop0"), set `WORKSHOP0_SMTP_USER=<gmail address>` and `WORKSHOP0_SMTP_PASSWORD=<app password>` in `.env`, restart, move an applicant again → the email arrives in the trainer's inbox and the outbox row is *sent*. Production: `export WORKSHOP0_SMTP_PASSWORD=…; bash deploy/cloudrun/provision.sh`, `gh variable set WORKSHOP0_SMTP_USER --body …`, redeploy. **Labelled stubs:** Saved searches & alerts, weekly digest, public directory, workshop tie-in.

---

## Phase 13 — Alerts & Digest, Public Directory, Workshop Tie-in *(final requirements phase — every network capability real)*

**Goal:** Trainers save searches and get alert emails and a weekly digest (with one-click unsubscribe); trainers who opt in appear in a public directory; admins link network trainers to Workshop0 workshops as facilitators, and participants see a **Join our network** invitation. No labelled stub remains anywhere in the network.

**Capabilities delivered (3):** C17 Saved searches, alerts & weekly digest · C18 Public trainer directory & visibility · C19 Workshop tie-in.

**Shared scaffold (orchestrator, one commit; §Parallel fan-out rule):**
- **Settings and `.env.example`:** `config/settings.py` gains `workshop0_cron_key`, and `.env.example` gains its line.
- **Router shells:** register `api/network_public.py` (unsubscribe + cron, no prefix beyond its paths) and `api/directory_public.py` (`prefix="/api/public/trainers"`) in `create_app()`.
- **Python interface stubs:**
  - `services/alerts.py`: `validate_criteria(criteria: dict) -> dict` (raises `validation_error`), `matches(criteria: dict, opportunity) -> bool`, `enqueue_alerts_for(session, opportunity) -> int`.
  - `services/unsubscribe.py`: `make_token(user_id: int, kind: Literal["alerts", "digest"]) -> str`, `read_token(token: str) -> tuple[int, str]`.
  - `services/tiein.py`: `workshops_for(session, profile_id: int) -> list[dict]`.
- **TypeScript stub:** `frontend/components/admin/facilitators/LinkFacilitatorButton.tsx` (`{profileId: number, opportunityId: number}`, renders `null`). It is used on the pipeline's Selected rows.
- **No new dependency. No AI call is added this phase.**

**Slices.** S0 runs first. S1–S17 then fan out concurrently, in waves over the cap.

| Slice | Owns (exclusive paths) | Delivers | Tests need |
|---|---|---|---|
| **S0 schema** | `src/workshop0/db/models.py`, `alembic/versions/0010_alerts_directory_tiein.py`, `tests/conftest.py`, `tests/integration/test_migration.py` | Phase-13 tables/columns | — |
| **S1 alerts** | `src/workshop0/services/alerts.py` (fills the stub), `src/workshop0/services/opportunities.py` (hook on every transition to effective `open`), `src/workshop0/api/board_admin.py` (adds `schedule_drain` after publish/reopen/patch only), `src/workshop0/email/templates/network_alert.*`, `tests/integration/alerts/**` | Saved-search matching and alert enqueue with dedupe `alert:{search}:{opp}`, written in the transaction that makes the listing open. The alert email carries an unsubscribe link via `unsubscribe.make_token` | S0, S2 |
| **S2 digest-unsubscribe** | `src/workshop0/services/{digest,unsubscribe}.py`, `src/workshop0/api/network_public.py`, `src/workshop0/email/templates/network_digest.*`, `tests/integration/digest/**` | The `/api/cron/weekly-digest` endpoint (cron key, 404 when unset, idempotent per ISO week, using `alerts.matches`) and the signed one-click `/api/email/unsubscribe` | S0, S1 |
| **S3 directory** | `src/workshop0/services/directory.py`, `src/workshop0/api/directory_public.py`, `tests/integration/directory/**` | Public directory + profile: allow-list serializer, ≥60 % completeness, private → 404 | S0 |
| **S4 tiein** | `src/workshop0/services/tiein.py` (fills the stub), `src/workshop0/api/admin.py`, `tests/integration/tiein/**` | `GET/PUT /api/admin/workshops/{id}/facilitators` with audit `workshop.facilitators`, and `workshops_for` | S0 |
| **S5 me-prefs** | `src/workshop0/api/network_me.py`, `src/workshop0/services/profiles.py`, `tests/integration/me_prefs/**` | `/api/me/searches` (≤10, via `alerts.validate_criteria`), `/api/me/email-prefs`, `visibility` on profile PATCH, and `/api/me/workshops` (via `tiein.workshops_for`) | S0, S1, S4 |
| **S6 fe-saved-searches** | `frontend/app/opportunities/**`, `frontend/components/board/**`, `frontend/app/network/{searches,unsubscribed}/**`, `frontend/components/network/searches/**`, `frontend/lib/networkSearches.ts` | "Save this search" from the board's current filters, the Saved searches page with alert toggles, and the unsubscribed page | — |
| **S7 fe-directory** | `frontend/app/network/{directory,trainer}/**`, `frontend/components/directory/**`, `frontend/lib/directory.ts` | Directory (topic filter, verified badge) and the public trainer page | — |
| **S8 fe-my-profile** | `frontend/app/network/me/**`, `frontend/components/network/profile/**`, `frontend/lib/network.ts` | Public directory toggle, email-preference toggles, **My Workshop0 workshops**, and the last profile stubs removed | — |
| **S9 fe-admin-facilitators** | `frontend/app/admin/page.tsx`, `frontend/components/facilitator/WorkshopCard.tsx`, `frontend/components/admin/facilitators/**` (fills the stub), `frontend/components/admin/pipeline/**` (Selected-row action only), `frontend/lib/adminFacilitators.ts` | The Facilitators picker on admin workshop cards, and "Link as facilitator" on Selected applicants | — |
| **S10 fe-participant-cta** | `frontend/app/{join,p}/page.tsx`, `frontend/components/participant/**` | The Join our network card on the join page and on the completed tracker. No sign-in is introduced | — |
| **S11 e2e-alerts-digest** | `tests/e2e/alerts-digest.spec.ts` | Save search → publish matching → alert in Outbox → unsubscribe; digest via the cron endpoint | runtime: all |
| **S12 e2e-directory** | `tests/e2e/directory.spec.ts` | Opt in → visible publicly without rates/email; private → not found | runtime: all |
| **S13 e2e-tiein** | `tests/e2e/tiein.spec.ts` | Link a trainer → My Workshop0 workshops shows the dashboard link; the participant CTA is visible with no sign-in | runtime: all |
| **S14 e2e-no-stubs** | `tests/e2e/network-no-stubs.spec.ts` | Visits every network page (trainer + admin) and asserts zero `stub-badge` elements | runtime: all |
| **S15 infra-provision** | `deploy/cloudrun/provision.sh` | `workshop0-cron-key` (generated) and the Cloud Scheduler job (`--schedule "0 9 * * 1" --time-zone Asia/Kolkata`, HTTP POST to `https://workshop0.smalltech.in/api/cron/weekly-digest` with the key header). Written and `bash -n` only | — |
| **S16 infra-workflows** | `.github/workflows/**` | Conditional `WORKSHOP0_CRON_KEY` secret mapping | — |
| **S17 docs** | `README.md`, `deploy/RUNBOOK.md` | RUNBOOK "network operations" section (digest, scheduler, the secrets list including both Anthropic secrets, the two-provider note) | — |

**Gate (repo root; the Phase-12 environment, including the Anthropic key + workspace id from `.env` because the regression suite re-runs the Phase-11/12 real-key tests, plus `export WORKSHOP0_CRON_KEY=gate-cron-key`):** the Phase-12 command block with `grep -q '^0010'`, page checks `for p in network/directory network/trainer network/searches network/unsubscribed; do test -f "frontend/out/$p/index.html"; done`, and additionally, with the server up: `curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8001/api/cron/weekly-digest | grep -qx 401` and `curl -fsS -X POST -H "X-Cron-Key: $WORKSHOP0_CRON_KEY" http://localhost:8001/api/cron/weekly-digest | grep -q '"enqueued"'`, then `bash -n deploy/cloudrun/provision.sh`. **Conditions:** a listing matching 3 of 5 saved searches → exactly 3 alerts, re-publish → 0 more; digest twice in one ISO week → one email per user (fixture: 40 users, 12 opted out, precomputed recipients); unsubscribe link flips exactly one preference; directory payloads contain only allow-listed keys (serialized-JSON assertion with sentinel email/rate/note values); a private or <60 % profile 404s publicly; linking a trainer to a workshop writes an audit row and shows on `/api/me/workshops`; participant join/tracker journeys (existing e2e) still pass and require no sign-in; zero `stub-badge` elements on network pages.

**How the user tests it:** as a trainer, on the board pick filters → **Save this search** → as admin publish a matching listing → the alert email arrives (or is *recorded* in the Outbox) → click **Unsubscribe** in it → preferences show alerts off. Trigger the digest locally: `curl -X POST -H "X-Cron-Key: $WORKSHOP0_CRON_KEY" http://localhost:8001/api/cron/weekly-digest`. Turn on **Public directory profile** → visit `/app/network/directory/` in a private window → your card is there, without rates or email. As admin, on a workshop card **Facilitators** → add the trainer as co-facilitator → the trainer's **My Workshop0 workshops** shows the dashboard link. Open a workshop join link → the **Join our network** card is visible. Production: `bash deploy/cloudrun/provision.sh` (cron key + scheduler), redeploy, `gcloud scheduler jobs run workshop0-weekly-digest --location us-central1`. **Nothing is a stub.**

---

## Phase-gate constants (every phase)

Working tree clean and pushed · README updated and its commands re-run verbatim · human test-handoff published and approved before the next phase · qa-auditor sign-off per slice · no phase starts while the previous one is red.
