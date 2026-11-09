# Roadmap — Workshop0 (v0.2)

Ground-up rebuild. The old `src/` and `frontend/` are **removed at scaffold**; nothing is preserved by inertia. Canonical run path (every phase): `(cd frontend && pnpm build)` → `uv run python -m src` → open **http://localhost:8001/app/**. `pnpm dev` is inner-loop only, never the test path.

**Shared scaffold (laid down by the orchestrator BEFORE any generator runs, so slices stay disjoint):** `pyproject.toml` (full Phase-1 dependency list from architecture.md §Stack), `alembic.ini`, `.env.example` (all vars from architecture.md §Environment variables), `README.md` skeleton, `.gitignore` (`data/`, `.env`, `frontend/out/`, `node_modules/`), `data/.gitkeep`, removal of the v0.1 app code. Generators never edit another slice's files; root scaffold files are edited only by the orchestrator between fan-outs.

## Phases of Development

| Phase | Theme | Status |
|---|---|---|
| 1 | Core live loop (create, join, milestones, live dashboard, manual help desk) | delivered |
| 2 | Facilitator command & proactive intelligence | delivered |
| 3 | Lifecycle, templates & re-run | delivered |
| 4 | AI help-desk (OpenRouter) | delivered |
| 5 | Docker + CI/CD (VM path, since retired) | delivered |
| 6 | Public landing page & self-service creation | delivered |
| 7 | Cloud Run + Cloud SQL (fresh database) | delivered |
| 8 | Cutover: data import, `workshop0.smalltech.in`, retire the VM | delivered |
| 9 | Rename everything to Workshop0 (code, brand, client storage, infra, repo) | delivered (PR #7) |
| 10 | Opportunity Board: topic taxonomy, admin listings, public board (C8–C10) | specified |
| 11 | Trainer sign-in, CV-drafted profiles & admin pool (C11–C13) | specified |
| 12 | Applications, matching & email outbox (C14–C16) | specified |
| 13 | Alerts & digest, public directory, workshop tie-in (C17–C19) | specified |

**Trainer Network ordering rationale.** Phase 10 needs nothing external (no Google client, no SMTP, no LLM key) and is valuable alone. Phases 11–13 each keep their **automated** gate free of human-only steps — sign-in is gated through a real OIDC protocol run against the local test issuer, email through a real local SMTP sink, LLM calls through the production OpenRouter key read from Secret Manager — while the steps only a human can do (Google Console client, Gmail app password) are part of that phase's "How the user tests it". So no build ever stalls on an AFK user; external blockers bite only at the human testing gate, where the human is present.

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

**Shared scaffold (orchestrator, before the fan-out, one commit):** add `pyjwt[crypto]`, `itsdangerous`, `python-multipart`, `pypdf`, `python-docx`, `google-cloud-storage` to `pyproject.toml` and `uv lock`; add the Phase-11 variables to `.env.example`; create the three router modules as empty shells — `src/workshop0/auth/__init__.py`, `src/workshop0/auth/routes.py`, `src/workshop0/api/network_me.py`, `src/workshop0/api/network_admin.py`, each `router = APIRouter(prefix=…)` with the prefixes in api.md §Phase 11 — and register them in `create_app()`. Slices then only **fill** their modules, so no slice imports a module another slice has not written yet, and `api/__init__.py` is edited concurrently by nobody.

**Settings contract:** S1 owns `config/settings.py` and adds **every** Phase-11 field (architecture.md §Environment variables) under these attribute names: `workshop0_google_client_id`, `workshop0_google_client_secret`, `workshop0_oidc_issuer`, `workshop0_session_secret`, `workshop0_admin_emails`, `workshop0_blob_backend`, `workshop0_gcs_bucket`, `workshop0_ai_network_model`. S2/S3/S4 read them via `get_settings()` and build against these names; their tests need S1's settings at gate time (S2's local-disk tests construct `LocalDiskStore(root)` directly and do not).

**Slices** (S0 runs first — it is small; then S1–S3 and S5–S8 fan out concurrently; S4 starts when S1 has landed):

| Slice | Owns (exclusive paths) | Delivers | Depends on |
|---|---|---|---|
| **S0 schema** | `src/workshop0/db/models.py`, `alembic/versions/0006_trainer_network.py`, `tests/conftest.py`, `tests/integration/test_migration.py` | All Phase-11 tables + the `ai_usage` changes exactly per data-model.md; conftest fixtures `make_user(email, admin=False)` and `signed_in_client(user)` (inserts an `auth_session` row and sets the cookie — the shortcut for non-auth tests) | — |
| **S1 identity** | `src/workshop0/auth/**`, `src/workshop0/security.py`, `src/workshop0/services/ratelimit.py`, `src/workshop0/config/settings.py`, `src/workshop0/api/__init__.py`, `tests/support/**`, `tests/integration/auth/**`, `tests/unit/test_ratelimit.py` | OIDC client, sessions, `deps.py` (exact interface in architecture.md), `/api/auth/*` (fills `auth/routes.py`), admin via session in `require_admin_key`, CSRF check, open-redirect guard, invite acceptance at callback (marks the invite accepted and the profile-to-be verified via `network_invite` rows only — profile writes belong to S4), startup rules, the settings contract above; adds the `/invite/{token}` + `/network` redirects to `api/__init__.py` (router registration is already done by the scaffold); `tests/support/fake_oidc.py` (`uv run python tests/support/fake_oidc.py --port 8099`: discovery, an authorize page with an email field that auto-approves, token, JWKS; can be told to emit `email_verified=false`) | S0 |
| **S2 cv-ingest** | `src/workshop0/storage/**`, `src/workshop0/services/cv_text.py`, `tests/unit/test_cv_text.py`, `tests/integration/storage/**`, `tests/fixtures/cv/**` | `BlobStore` (local + GCS), `extract_text(data, kind) -> str` (pypdf/python-docx; raises `CvUnreadable` when <200 chars), the committed CV fixtures (incl. an image-only PDF); GCS backend tested against a real bucket only when `WORKSHOP0_GCS_BUCKET` is set (guarded) | — |
| **S3 drafter** | `src/workshop0/ai/**`, `tests/integration/ai_network/test_profile_draft.py` | `openrouter.py`, `profile_draft.py`, prompts — per agent.md; `draft_profile` is pure and is tested on the S2 fixtures (reads files only) | — (build); S2's fixtures at gate time |
| **S4 network-api** | `src/workshop0/api/{network_me,network_admin}.py`, `src/workshop0/services/{profiles,invites}.py`, `tests/integration/network/**` | Every `/api/me/*` and `/api/admin/network/*` endpoint in api.md §Phase 11, completeness, CSV, deletion (DB + blob), audit rows, rate limits wired | S0, S1 (deps + ratelimit); S2/S3 interfaces fixed above |
| **S5 frontend-network** | `frontend/app/{signin,network}/**`, `frontend/components/network/**`, `frontend/lib/network.ts`, `frontend/components/board/**` (CTA only) | Sign-in, account menu, onboarding (3 tabs + LinkedIn how-to + polling skeleton), review screen with "From your CV — please check" chips, My profile with completeness meter, delete flow, invite landing, stubs; board CTA real | — |
| **S6 frontend-admin-pool** | `frontend/app/admin/**`, `frontend/components/admin/**`, `frontend/lib/adminNetwork.ts` | Pool table + filters + CSV + invites + AI spend card, trainer detail (CV download, verify, tags, notes, activity), Google button on `AdminGate` and Admin Home's gate, nav stubs made real | — |
| **S7 e2e** | `tests/e2e/**` | `network-onboarding.spec.ts`, `admin-pool.spec.ts` (journeys below) | runtime: all |
| **S8 infra-docs** | `deploy/cloudrun/provision.sh`, `.github/workflows/{deploy-cloudrun,ci}.yml`, `deploy/RUNBOOK.md`, `README.md` | Bucket + IAM + secrets per architecture.md (SKIPPED rule), conditional secret mapping, GitHub variables documented, CI starts the fake issuer for e2e; README: sign-in setup, the Google Console steps below, new env vars | — |

**Gate (exact commands; repo root; PostgreSQL as before; operator `gcloud`-authenticated — the OpenRouter key is read from Secret Manager, never echoed; no Google or SMTP credentials needed):**

```bash
export TEST_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/workshop0_test"
export WORKSHOP0_ADMIN_KEY="${WORKSHOP0_ADMIN_KEY:-phase11-local-gate-key-0123}"
export OPENROUTER_API_KEY="$(gcloud secrets versions access latest --secret workshop0-openrouter-api-key --project ai-agent-boilerplate0)"
test -n "$OPENROUTER_API_KEY"                                                          # BLOCKED (not skipped) without it
export WORKSHOP0_GOOGLE_CLIENT_ID=test-client WORKSHOP0_GOOGLE_CLIENT_SECRET=test-secret
export WORKSHOP0_OIDC_ISSUER=http://localhost:8099 WORKSHOP0_SESSION_SECRET="$(openssl rand -hex 32)"
export WORKSHOP0_ADMIN_EMAILS=admin@example.test WORKSHOP0_BLOB_BACKEND=local
uv sync
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head && DATABASE_URL="$TEST_DATABASE_URL" uv run alembic current | grep -q '^0006'
uv run python tests/support/fake_oidc.py --port 8099 &                                 # real OIDC protocol, local issuer
sleep 2
uv run pytest tests/unit tests/integration -q                                          # incl. auth/, network/, storage/, ai_network/ (REAL OpenRouter)
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

**Gate conditions beyond the commands (tests S1/S2/S3/S4 must contain):** OIDC — state mismatch, nonce mismatch, wrong `aud`, expired token, bad signature (token signed by a second key), `email_verified=false` each refused with the documented redirect code and no session row; first sign-in creates one user, second reuses it; allowlisted email → admin endpoints succeed without the key, de-listed → 403 `not_admin` on the next request; existing admin tests still pass with the key only; every `/api/me` mutation without `X-Requested-With` → 403 `csrf_failed`; `next=https://evil.example` → lands on `/app/network/`; rate limit: the 11th CV upload in an hour → 429 with `Retry-After`, across two app instances sharing the DB. Profiles — the three drafter fixtures through the real endpoint (upload → poll → draft) with agent.md's assertions; image-only PDF → 422 `cv_unreadable`; keyless run → `draft_status="skipped"` and profile creation still works; consent missing → `validation_error`; completeness = the ten-check formula on 5 hand-built profiles; deletion removes user, profile, CV row, blob file and sessions and writes `account.delete` with a masked email only. Pool — a 60-profile fixture: `q`, `topic` (ANY), `verified`, `tag` filters return precomputed sets across 3 pages; CSV row count = filtered total; CV download (local) returns the original bytes with `Content-Disposition` and writes `cv.download`. Privacy — rates, email and CV fields are absent from every non-admin payload except the owner's own `GET /api/me/profile` (asserted on serialized JSON).

**e2e (S7):** *network-onboarding* — board → **Join our network** → sign-in page → **Continue with Google** → the local issuer's page → enter `trainer-<run>@example.test` → back on onboarding → upload `tests/fixtures/cv/genai_trainer.pdf` → "Reading your CV…" → review screen shows ≥1 "From your CV — please check" chip and the curated topics (real OpenRouter) → tick consent → **Create my profile** → My profile shows the completeness meter and nudges → sign out → sign in again → same profile → **Delete my account** → confirmation → signing in again lands on onboarding (fresh). *admin-pool* — sign in as `admin@example.test` via the issuer → Admin Home without the key → **Trainer network** → the trainer from the first spec is listed → open → **Download CV** (download event, `.pdf`) → **Verify** → badge → add tag + note → **Export CSV** → create an invite for `invitee-<run>@example.test` → open the copied `/invite/<token>` in a fresh context, sign in as that email → onboarding shows **Verified** → a different email on another invite → mismatch message. Every stub listed above shows its pill.

**How the user tests it:**
1. **One-time Google setup (manual, ~5 minutes, GCP Console, project `ai-agent-boilerplate0`):** APIs & Services → **OAuth consent screen** → User type **External** → app name **Workshop0**, support email = your smallTech email, authorized domain `smalltech.in`, scopes `openid`, `email`, `profile` → add yourself as a test user (or **Publish app** to allow anyone; these scopes need no Google verification) → **Credentials** → **Create credentials → OAuth client ID** → Application type **Web application**, name `workshop0-web` → **Authorized JavaScript origins** `http://localhost:8001`, `https://workshop0.smalltech.in` → **Authorized redirect URIs** `http://localhost:8001/api/auth/google/callback`, `https://workshop0.smalltech.in/api/auth/google/callback` → Create → copy the client ID and secret.
2. **Local:** in `.env` set `WORKSHOP0_GOOGLE_CLIENT_ID`, `WORKSHOP0_GOOGLE_CLIENT_SECRET`, `WORKSHOP0_SESSION_SECRET=$(openssl rand -hex 32)`, `WORKSHOP0_ADMIN_EMAILS=<your email>`, and `OPENROUTER_API_KEY` (`gcloud secrets versions access latest --secret workshop0-openrouter-api-key --project ai-agent-boilerplate0`). `(cd frontend && pnpm build)`, `uv run python -m src`.
3. Private window → **http://localhost:8001/opportunities** → **Join our network** → **Continue with Google** with a non-admin Google account → upload your own CV (or a LinkedIn "Save to PDF") → within a few seconds the review screen is pre-filled, drafted fields marked "From your CV — please check"; fix anything, tick consent → **Create my profile** → see completeness and the nudges.
4. Normal window → **http://localhost:8001/admin** → **Continue with Google** with your admin email (no key) → **Trainer network** → find the trainer → open → download the CV, **Verify**, add a tag and a note; check the **Network AI spend** card shows the drafting cost; **Export CSV**. Create an invite for another address you own → open the link in a third browser → sign in with that address → it starts **Verified**.
5. As the trainer, **Delete my account** → it disappears from the pool.
6. **Production** (after the merge deploys): `export WORKSHOP0_GOOGLE_CLIENT_SECRET=…; bash deploy/cloudrun/provision.sh` (creates the bucket and secrets), `gh variable set WORKSHOP0_GOOGLE_CLIENT_ID --body …`, `gh variable set WORKSHOP0_ADMIN_EMAILS --body …`, `gh workflow run deploy-cloudrun.yml --ref main`, then repeat steps 3–4 on **https://workshop0.smalltech.in** (CV download goes through a signed GCS URL).
**Labelled stubs (not bugs):** Sign in to apply, My applications, Matched for you, Saved searches, Public directory profile, matching filters, Suggested trainers, Email invite, Outbox.

---

## Phase 12 — Applications, Matching & Email Outbox

**Goal:** A signed-in trainer applies to a listing in one click and tracks the status; an admin gets a suggested shortlist for a listing, invites trainers to apply, moves applicants through the pipeline in bulk with status emails; every email goes through an outbox that sends over Gmail SMTP when configured and is recorded (and shown to admins, clearly labelled) when not.

**Capabilities delivered (3):** C14 Apply & applicant pipeline · C15 Matching (rule filters, suggested shortlist, invite to apply, matched for you) · C16 Email outbox & notifications. Design: agent.md §Shortlist ranker, architecture.md §Email, api.md §Phase 12, data-model.md §Phase 12.

**Stubs carried forward:** Saved searches & alerts, weekly digest, public directory toggle, workshop tie-in (→ 13). **Made real:** Sign in to apply, My applications, Matched for you, Applicants column, Suggested trainers, matching filters, Email invite, Outbox.

**Shared scaffold (orchestrator):** `aiosmtpd` added to the dev group + `uv lock`; Phase-12 vars in `.env.example`; empty router shell `src/workshop0/api/outbox_admin.py` (`prefix="/api/admin/outbox"`, `require_admin_key`) registered in `create_app()`; `config/settings.py` gains the Phase-12 SMTP fields (`workshop0_smtp_host`, `_port`, `_starttls`, `_user`, `_password`, `_from`) — so S3 does not edit `api/__init__.py` or settings concurrently with anyone.

| Slice | Owns (exclusive paths) | Delivers | Depends on |
|---|---|---|---|
| **S0 schema** | `src/workshop0/db/models.py`, `alembic/versions/0007_applications_matching_email.py`, `src/workshop0/email/outbox.py`, `tests/conftest.py`, `tests/integration/test_migration.py` | Phase-12 tables/columns; `enqueue(...)` (insert-only, dedupe) so S1/S2 can call it before S3 exists | — |
| **S1 applications** | `src/workshop0/services/applications.py`, `src/workshop0/api/network_me.py`, `tests/integration/applications/**` | Apply/withdraw/my-applications, pipeline list/bulk status/CSV (the admin routes are added to `network_admin.py` by **S2** — S1 provides `services/applications.py` functions S2's routes call: `list_pipeline`, `bulk_set_status`, `pipeline_csv`) | S0; S3's `schedule_drain` and S2's `matches_for` at gate time (signatures fixed here) |
| **S2 matching** | `src/workshop0/services/matching.py`, `src/workshop0/ai/shortlist_rank.py`, `src/workshop0/ai/prompts/shortlist_rank_*.md`, `src/workshop0/api/network_admin.py`, `src/workshop0/api/board_admin.py`, `src/workshop0/services/opportunities.py`, `tests/integration/matching/**`, `tests/integration/ai_network/test_shortlist_rank.py` | Rule filters, rule score, ranker, shortlist/invite endpoints, matched-for-you function (route lives in S1's `network_me.py`: S1 calls `matching.matches_for(profile)`), budget fields in the opportunity editor API, pipeline admin routes over S1's service functions | S0; S1's three service signatures (above) at test time |
| **S3 email** | `src/workshop0/email/{sender,smtp}.py`, `src/workshop0/email/templates/**`, `src/workshop0/api/outbox_admin.py`, `src/workshop0/services/invites.py`, `src/workshop0/services/profiles.py`, `tests/integration/email/**` | Sender + drain (post-commit BackgroundTask hook exposed as `email.sender.schedule_drain(background_tasks)` for S1/S2 routes) + SMTP + the 5 templates, outbox admin routes, welcome/invite enqueues | S0 |
| **S4 frontend-network** | `frontend/app/network/**`, `frontend/app/opportunities/**`, `frontend/components/{network,board}/**`, `frontend/lib/{network,board}.ts` | Apply panel, My applications timeline, Matched for you | — |
| **S5 frontend-admin** | `frontend/app/admin/**`, `frontend/components/admin/**`, `frontend/lib/{adminBoard,adminNetwork}.ts` | Pipeline page, Suggested trainers panel, matching filters, budget fields, invite-to-apply, Outbox page with the "not configured" label | — |
| **S6 e2e** | `tests/e2e/**` | `apply-pipeline.spec.ts`, `matching.spec.ts`, `outbox.spec.ts` | runtime: all |
| **S7 infra-docs** | `deploy/cloudrun/provision.sh`, `.github/workflows/**`, `deploy/RUNBOOK.md`, `README.md` | `workshop0-smtp-password` (SKIPPED rule), `WORKSHOP0_SMTP_USER` variable, conditional mapping; README email setup incl. Gmail app-password steps | — |

**Gate (repo root; as Phase 11, plus a real local SMTP sink):**

```bash
export TEST_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/workshop0_test"
export WORKSHOP0_ADMIN_KEY="${WORKSHOP0_ADMIN_KEY:-phase12-local-gate-key-0123}"
export OPENROUTER_API_KEY="$(gcloud secrets versions access latest --secret workshop0-openrouter-api-key --project ai-agent-boilerplate0)"; test -n "$OPENROUTER_API_KEY"
export WORKSHOP0_GOOGLE_CLIENT_ID=test-client WORKSHOP0_GOOGLE_CLIENT_SECRET=test-secret WORKSHOP0_OIDC_ISSUER=http://localhost:8099
export WORKSHOP0_SESSION_SECRET="$(openssl rand -hex 32)" WORKSHOP0_ADMIN_EMAILS=admin@example.test WORKSHOP0_BLOB_BACKEND=local
export WORKSHOP0_SMTP_HOST=localhost WORKSHOP0_SMTP_PORT=8025 WORKSHOP0_SMTP_STARTTLS=0 WORKSHOP0_SMTP_USER=bot@example.test WORKSHOP0_SMTP_PASSWORD=x
uv sync
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head && DATABASE_URL="$TEST_DATABASE_URL" uv run alembic current | grep -q '^0007'
uv run python tests/support/fake_oidc.py --port 8099 &
uv run python -m aiosmtpd -n -l localhost:8025 &
sleep 2
uv run pytest tests/unit tests/integration -q                                          # incl. real-OpenRouter shortlist ranking
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

**Gate conditions beyond the commands:** one application per (listing, trainer); `opportunity_closed` for expired/closed; a bulk move of 12 applicants → one audit row + exactly 12 outbox rows, re-run → still 12 (dedupe); emails are delivered to the aiosmtpd sink and marked `sent`; with `WORKSHOP0_SMTP_USER` unset every enqueue ends `recorded` and no request fails; a failing SMTP (port closed) → `failed` after 3 attempts, Retry re-queues; agent.md ranker assertions on the 60-profile fixture (eligible set of exactly 17; obvious best in top 3); keyless → "Ranked by rules"; matched-for-you ranks a 3-listing fixture in the precomputed order; every email link is absolute.

**How the user tests it:** with the Phase-11 setup: as a trainer open a listing → **Apply** with a note → My applications shows *Applied*. As admin open the listing's **Applicants** → select it → **Move to Shortlisted** (email on) → the trainer's page shows *Shortlisted* → open **Outbox**: without SMTP configured the banner reads "Email sending isn't configured — messages are recorded here, not sent" and the status email is listed as *recorded*. On a listing, **Suggested trainers** → up to 10 trainers with reasons and the run cost → **Invite to apply** → the trainer sees an *Invited* badge in **Matched for you**. **Real email (manual):** create a Gmail app password (Google Account → Security → 2-Step Verification on → App passwords → "Workshop0"), set `WORKSHOP0_SMTP_USER=<gmail address>` and `WORKSHOP0_SMTP_PASSWORD=<app password>` in `.env`, restart, move an applicant again → the email arrives in the trainer's inbox and the outbox row is *sent*. Production: `export WORKSHOP0_SMTP_PASSWORD=…; bash deploy/cloudrun/provision.sh`, `gh variable set WORKSHOP0_SMTP_USER --body …`, redeploy. **Labelled stubs:** Saved searches & alerts, weekly digest, public directory, workshop tie-in.

---

## Phase 13 — Alerts & Digest, Public Directory, Workshop Tie-in *(final requirements phase — every network capability real)*

**Goal:** Trainers save searches and get alert emails and a weekly digest (with one-click unsubscribe); trainers who opt in appear in a public directory; admins link network trainers to Workshop0 workshops as facilitators, and participants see a **Join our network** invitation. No labelled stub remains anywhere in the network.

**Capabilities delivered (3):** C17 Saved searches, alerts & weekly digest · C18 Public trainer directory & visibility · C19 Workshop tie-in.

**Shared scaffold (orchestrator):** empty router shells `src/workshop0/api/network_public.py` (unsubscribe + cron) and `src/workshop0/api/directory_public.py` (`prefix="/api/public/trainers"`) registered in `create_app()`; `config/settings.py` gains `workshop0_cron_key`.

| Slice | Owns (exclusive paths) | Delivers | Depends on |
|---|---|---|---|
| **S0 schema** | `src/workshop0/db/models.py`, `alembic/versions/0008_alerts_directory_tiein.py`, `tests/conftest.py`, `tests/integration/test_migration.py` | Phase-13 tables/columns | — |
| **S1 alerts-digest** | `src/workshop0/services/alerts.py`, `src/workshop0/email/templates/{network_alert,network_digest}.*`, `src/workshop0/api/network_public.py`, `src/workshop0/services/opportunities.py`, `tests/integration/alerts/**` | Saved-search matching, alert enqueue on transition to open, digest endpoint (cron key), signed unsubscribe | S0 |
| **S2 directory** | `src/workshop0/services/directory.py`, `src/workshop0/api/directory_public.py`, `tests/integration/directory/**` | Public directory + profile (allow-list serializer, ≥60 % completeness, private → 404) | S0 |
| **S3 tie-in + me** | `src/workshop0/services/{tiein,profiles}.py`, `src/workshop0/api/{network_me,admin}.py`, `tests/integration/tiein/**` | Facilitator links, `/api/me/workshops`, `/api/me/searches` (calls S1's `alerts.validate_criteria`), `/api/me/email-prefs`, `visibility` on profile PATCH | S0; S1's `validate_criteria(dict) -> dict` signature at gate time |
| **S4 frontend-network** | `frontend/app/network/**`, `frontend/components/network/**`, `frontend/lib/network.ts`, `frontend/app/opportunities/**`, `frontend/components/board/**` | Saved searches (from the board's current filters: "Save this search"), email prefs, unsubscribed page, directory + public profile pages, visibility toggle, My Workshop0 workshops | — |
| **S5 frontend-workshop** | `frontend/app/admin/page.tsx`, `frontend/components/facilitator/WorkshopCard.tsx`, `frontend/components/admin/**`, `frontend/app/{join,p}/page.tsx`, `frontend/components/participant/**` | Facilitators picker on admin workshop cards, Join our network card on join page and on the completed tracker | — |
| **S6 e2e** | `tests/e2e/**` | `alerts-digest.spec.ts`, `directory.spec.ts`, `tiein.spec.ts`; plus an assertion that no `stub-badge` exists on any network page | runtime: all |
| **S7 infra-docs** | `deploy/cloudrun/provision.sh`, `.github/workflows/**`, `deploy/RUNBOOK.md`, `README.md` | `workshop0-cron-key`, Cloud Scheduler job (`--schedule "0 9 * * 1" --time-zone Asia/Kolkata`, HTTP POST to `https://workshop0.smalltech.in/api/cron/weekly-digest` with the key header), RUNBOOK "network operations" section | — |

**Gate (repo root; Phase-12 environment plus `export WORKSHOP0_CRON_KEY=gate-cron-key`; no OpenRouter call is required this phase but the key stays set for the regression suite):** the Phase-12 command block with `grep -q '^0008'`, page checks `for p in network/directory network/trainer network/searches network/unsubscribed; do test -f "frontend/out/$p/index.html"; done`, and additionally, with the server up: `curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8001/api/cron/weekly-digest | grep -qx 401` and `curl -fsS -X POST -H "X-Cron-Key: $WORKSHOP0_CRON_KEY" http://localhost:8001/api/cron/weekly-digest | grep -q '"enqueued"'`, then `bash -n deploy/cloudrun/provision.sh`. **Conditions:** a listing matching 3 of 5 saved searches → exactly 3 alerts, re-publish → 0 more; digest twice in one ISO week → one email per user (fixture: 40 users, 12 opted out, precomputed recipients); unsubscribe link flips exactly one preference; directory payloads contain only allow-listed keys (serialized-JSON assertion with sentinel email/rate/note values); a private or <60 % profile 404s publicly; linking a trainer to a workshop writes an audit row and shows on `/api/me/workshops`; participant join/tracker journeys (existing e2e) still pass and require no sign-in; zero `stub-badge` elements on network pages.

**How the user tests it:** as a trainer, on the board pick filters → **Save this search** → as admin publish a matching listing → the alert email arrives (or is *recorded* in the Outbox) → click **Unsubscribe** in it → preferences show alerts off. Trigger the digest locally: `curl -X POST -H "X-Cron-Key: $WORKSHOP0_CRON_KEY" http://localhost:8001/api/cron/weekly-digest`. Turn on **Public directory profile** → visit `/app/network/directory/` in a private window → your card is there, without rates or email. As admin, on a workshop card **Facilitators** → add the trainer as co-facilitator → the trainer's **My Workshop0 workshops** shows the dashboard link. Open a workshop join link → the **Join our network** card is visible. Production: `bash deploy/cloudrun/provision.sh` (cron key + scheduler), redeploy, `gcloud scheduler jobs run workshop0-weekly-digest --location us-central1`. **Nothing is a stub.**

---

## Phase-gate constants (every phase)

Working tree clean and pushed · README updated and its commands re-run verbatim · human test-handoff published and approved before the next phase · qa-auditor sign-off per slice · no phase starts while the previous one is red.
