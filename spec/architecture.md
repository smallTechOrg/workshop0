# Architecture — Workshop0 (v0.2)

## Stack

| Layer | Choice | Version / notes |
|-------|--------|-----------------|
| Language (backend) | Python | 3.12+ |
| Package manager (Python) | uv | all commands `uv run …` from repo root |
| Web framework | FastAPI | ≥0.115 |
| ASGI server | uvicorn | single process, single worker (see Process model) |
| ORM | SQLAlchemy | 2.x, sync engine, `Mapped`/`mapped_column` declarative |
| Migrations | Alembic | ≥1.13, `render_as_batch=True` (needed for SQLite ALTER; harmless no-op on PostgreSQL). Migrations must apply cleanly on **both** engines (Phase 7 proves PostgreSQL) |
| Database (production, Phase 7+) | **PostgreSQL 17 on Cloud SQL** | existing shared instance `ai-agent-db` (connection `ai-agent-boilerplate0:us-central1:ai-agent-db`, PRIVATE IP `10.110.112.7:5432`, TLS enforced, `max_connections=90`, db-f1-micro). Workshop0 owns **only** database `workshop0` + user `workshop0_app`; it never touches other apps' databases, users or secrets |
| Database (local dev / `deploy/docker-compose.yml`) | SQLite (WAL) | file `data/workshop0.db`, the `DATABASE_URL` default; no SQLite-only SQL in app code (the Phase-4 FTS5 corpus is the one documented exception, PostgreSQL variant in agent.md) |
| DB driver | psycopg 3 (`psycopg[binary]`) | URL scheme `postgresql+psycopg://…?sslmode=require`; added to `pyproject.toml` + `uv.lock` in Phase 7 |
| Test database | PostgreSQL 17 (harness Rule 5) | `TEST_DATABASE_URL` (local Homebrew `postgresql@17`, CI service container); tests never fall back to SQLite |
| Settings | pydantic-settings | v2, loads `.env` |
| Logging | structlog | JSON to stdout |
| HTTP client (help-desk LLM) | httpx | OpenRouter REST, 30s timeout (Phase-4 help-desk only) |
| Frontend framework | Next.js | 15.x, App Router, **static export** (`output: 'export'`, `basePath: '/app'`) |
| UI library | React | 19.x |
| Language (frontend) | TypeScript | 5.x, strict |
| Styling | Tailwind CSS | v4 (via `@tailwindcss/postcss` + `@source "../";` in globals.css — never removed). Chosen for the polish bar: design tokens via `@theme`, consistent spacing/type scales, zero runtime cost in a static export |
| Markdown | react-markdown + remark-gfm + rehype-highlight | raw HTML disabled (no rehype-raw) — see Security |
| Package manager (frontend) | pnpm | frontend deps in `frontend/`, e2e deps in root `package.json` |
| E2E testing | Playwright | `@playwright/test`, chromium, config at repo root, tests in `tests/e2e/` |
| Backend testing | pytest | `tests/unit/`, `tests/integration/` |
| LLM provider — help-desk (Phase 4) | OpenRouter | key: `OPENROUTER_API_KEY` (exact name — project convention); default model `anthropic/claude-sonnet-4-6` via `WORKSHOP0_AI_MODEL`. Unchanged by the trainer network; not migrated (§Key decisions). **Code truth (grep of `src/`, 2026-11-09):** only the settings fields and the `ai_usage`/`ai_state` schema exist — the pipeline module is absent (agent.md header) |
| LLM provider — trainer network (Phase 11+) | **Anthropic, direct** (user decision) | `anthropic` Python SDK; key `ANTHROPIC_API_KEY` + `ANTHROPIC_WORKSPACE_ID`, the latter sent on **every** request as header `anthropic-workspace-id` (hard requirement — agent.md §Provider); models `claude-sonnet-5-5` (`WORKSHOP0_AI_NETWORK_MODEL`, CV extraction, opportunity drafting (P11b) + ranking) and `claude-haiku-5-5` (`WORKSHOP0_AI_NETWORK_FAST_MODEL`, cheap calls); cost = tokens × `ai/pricing.py` table |
| LLM SDK (Phase 11) | `anthropic` ≥2.6.0 (brings its own httpx fork, `httpx2`) | Added to `pyproject.toml` + `uv.lock` in the Phase-11 scaffold (Phase 10 adds no dependency). Constructed only in `src/workshop0/ai/anthropic_client.py`; structured output via `output_config` json_schema (agent.md §Shared client) |
| Deploy (production, Phase 7+) | **Cloud Run + Cloud SQL**, GitHub Actions + Workload Identity Federation | see §Production topology. Supersedes the Phase-5 VM path (Docker Compose + Caddy + SQLite on GCE), removed from the repo in Phase 8 (recoverable from git tag `vm-deploy-final`) |
| Deploy (local) | Docker Compose (`deploy/docker-compose.yml`) | SQLite + volume; kept for local dev and self-hosters |
| OIDC / sessions (Phase 11) | `pyjwt[crypto]` ≥2.9 (ID-token + JWKS verification via `PyJWKClient`), `itsdangerous` ≥2.2 (signed short-lived OIDC state cookie), httpx (discovery + code exchange) | No auth SDK: a ~300-line OIDC client inside `src/workshop0/auth/` keeps the module swappable for a central smallTech identity service |
| File uploads & CV text (Phase 11) | `python-multipart` ≥0.0.9 (FastAPI `UploadFile`), `pypdf` ≥5.0 (PDF text), `python-docx` ≥1.1 (DOCX text) | Image-only PDFs yield no text → `cv_unreadable`; no OCR |
| Blob storage (Phase 11) | `google-cloud-storage` ≥2.18 in production (private bucket, V4 signed URLs); local disk `data/blobs/` in dev/tests | One `BlobStore` interface, backend chosen by `WORKSHOP0_BLOB_BACKEND` |
| Email (Phase 12) | stdlib `smtplib` (STARTTLS, Gmail SMTP `smtp.gmail.com:587` + app password) behind an outbox table; `aiosmtpd` (dev dependency) as the real local SMTP sink for tests/e2e | No email SaaS SDK |
| Test OIDC issuer (Phase 11) | `tests/support/fake_oidc.py` — a tiny standalone FastAPI app implementing discovery / authorize / token / JWKS with a generated RSA key | Exercises the real OIDC protocol path end-to-end without a Google account; real Google is verified in the human test |

> **Assumed (Phase 11+):** these dependencies are added to `pyproject.toml` + `uv.lock` by the orchestrator **before** the Phase-11 fan-out (shared-scaffold rule, roadmap.md), so no slice edits the lockfile. `aiosmtpd` lands in the dev group before Phase 12.

> **Assumed:** Node LTS (22.x) pinned via `frontend/.nvmrc` and `engines`; all frontend `dev`/`build` scripts carry `NODE_OPTIONS=--no-experimental-webstorage` (harness Node ≥25 safety rule).

## Repo layout

```
workshop0/                  ← repo root IS the project; all commands run from here
├── src/
│   ├── __init__.py
│   ├── __main__.py                 ← boots uvicorn on 0.0.0.0:$PORT (default 8001)
│   └── workshop0/
│       ├── __init__.py             ← __version__ = "0.2.0"
│       ├── config/settings.py      ← pydantic-settings; reads .env
│       ├── security.py             ← token generation + auth dependencies
│       ├── db/
│       │   ├── models.py           ← all SQLAlchemy models (spec/data-model.md)
│       │   └── session.py          ← engine (SQLite pragmas | PostgreSQL pool), session dependency
│       ├── api/
│       │   ├── __init__.py         ← create_app(): routers, static mount, pretty-link redirects
│       │   ├── _common.py          ← ok(), api_error()
│       │   ├── health.py           ← GET /api/health
│       │   ├── admin.py            ← admin-key surface (create/list workshops, templates)
│       │   ├── public.py           ← Phase 6: keyless POST /api/public/workshops
│       │   ├── facilitator.py      ← /api/f/{admin_token}/… surface
│       │   └── participant.py      ← /api/join/…, /api/p/{token}/… surface
│       ├── services/
│       │   ├── snapshots.py        ← versioned poll-payload builders (stateless; in-process memo dropped in Phase 7)
│       │   ├── lifecycle.py        ← lazy status transitions (Phase 3)
│       │   ├── intelligence.py     ← stuck / bottleneck / pulse computation (Phase 2)
│       │   ├── undo.py             ← undoable-action record/replay (Phase 2)
│       │   ├── templates.py        ← template instantiate/save-as (Phase 3)
│       │   └── workshops.py        ← Phase 6: the ONE creation service both admin.py and public.py call
│       ├── ai/                     ← AI help-desk pipeline (Phase 4; see spec/agent.md) — NOT YET IN CODE (verified 2026-11-09); Phase 11 creates the package with the network-AI modules below
│       │   ├── pipeline.py         ← run_help_desk(help_request_id)
│       │   ├── context.py          ← context gathering
│       │   ├── corpus.py           ← FTS5 corpus maintenance + similarity search
│       │   ├── openrouter.py       ← httpx client, usage/cost capture
│       │   └── prompts/            ← *.md prompt templates
│       └── observability/
│           └── logging.py          ← structlog config + request-logging middleware
├── frontend/
│   ├── package.json                ← pnpm; NODE_OPTIONS safety in scripts
│   ├── next.config.ts              ← output: 'export', basePath: '/app', trailingSlash: true
│   ├── postcss.config.mjs          ← @tailwindcss/postcss (never removed)
│   ├── tsconfig.json
│   ├── app/
│   │   ├── layout.tsx              ← fonts, shell
│   │   ├── globals.css             ← Tailwind v4 + @source "../"; + design tokens (@theme)
│   │   ├── page.tsx                ← Phase 1–5: Admin Home · Phase 6: PUBLIC LANDING PAGE (served at / only)
│   │   ├── admin/page.tsx          ← Phase 6: Admin Home moved here (access key + workshop list/create) — pretty /admin
│   │   ├── create/page.tsx         ← Phase 6: public keyless create flow (/app/create/)
│   │   ├── f/page.tsx              ← Facilitator Dashboard   (?t=<admin_token>)
│   │   ├── join/page.tsx           ← Participant Join        (?s=<join_slug>)
│   │   └── p/page.tsx              ← Participant Tracker     (?t=<participant_token>)
│   ├── components/
│   │   ├── ui/                     ← shared primitives (Button, Card, Badge, Toast, Modal, Markdown, Skeleton, StubBadge)
│   │   ├── facilitator/            ← dashboard components
│   │   └── participant/            ← tracker/join components
│   └── lib/
│       ├── api.ts                  ← typed API client (contract: spec/api.md)
│       └── poll.ts                 ← versioned polling hook (visibility-aware)
├── alembic/                        ← env.py, script.py.mako, versions/
├── tests/
│   ├── conftest.py
│   ├── unit/                       ← pytest, no network
│   ├── integration/                ← pytest, real HTTP (TestClient) + real DB file; Phase 4: tests/integration/ai against real OpenRouter key
│   └── e2e/                        ← Playwright specs (TypeScript)
├── playwright.config.ts            ← baseURL http://localhost:8001/app
├── package.json                    ← root: @playwright/test only
├── pyproject.toml                  ← uv-managed; testpaths = ["tests"]
├── alembic.ini
├── .env.example
├── data/                           ← SQLite file at runtime, local dev only (gitignored)
├── scripts/                        ← Phase 8: sqlite_to_postgres.py (one-off cutover import)
├── deploy/
│   ├── Dockerfile                  ← multi-stage image (shared by compose + Cloud Run)
│   ├── entrypoint.sh               ← `migrate` subcommand; boot-time migrations opt-in via WORKSHOP0_MIGRATE_ON_BOOT
│   ├── docker-compose.yml          ← local dev (SQLite) — kept
│   ├── cloudrun/                   ← Phase 7: provision.sh, dbinit.py · Phase 8: import-data.sh, domain-map.sh
│   └── RUNBOOK.md                  ← Phase 8: rewritten for Cloud Run (topology, cutover, rollback, VM decommission)
└── .github/workflows/
    ├── ci.yml                      ← PR/push: tests on a PostgreSQL 17 service container
    └── deploy-cloudrun.yml         ← production deploy (WIF → AR → migrate job → revision → traffic); push to main + workflow_dispatch (any branch ref)
```

> The Phase-5 VM deploy path (`docker-compose.prod.yml`, the reverse-proxy config, `deploy.yml`) was deleted in Phase 8; it remains recoverable from git tag `vm-deploy-final`.

**Trainer Network additions (Phases 10–13)** — new paths only; existing files change only where a phase's slice table says so:

```
src/workshop0/
├── api/
│   ├── board_public.py        ← P10: /api/public/topics, /api/public/opportunities[/{id}]
│   ├── board_admin.py         ← P10: /api/admin/opportunities…, /api/admin/topics…
│   ├── partners_admin.py      ← P11b: /api/admin/partners…
│   ├── board_ai_admin.py      ← P11b: /api/admin/opportunity-draft[/config] (paste-to-fill)
│   ├── network_me.py          ← P11: /api/me/* (profile, CV, deletion); P12 applications/matches; P13 searches/prefs/workshops
│   ├── network_admin.py       ← P11: /api/admin/network/* (pool, invites, CSV, ai-spend); P12 pipeline/shortlist/outbox
│   ├── outbox_admin.py        ← P12: /api/admin/outbox…
│   ├── network_public.py      ← P13: /api/email/unsubscribe, /api/cron/weekly-digest
│   ├── directory_public.py    ← P13: /api/public/trainers[/{slug}]
│   └── seo.py                 ← P11e: /opportunities/{key}, /sitemap.xml, /robots.txt · P13: /trainers, /trainers/{slug}
├── auth/                      ← P11: THE identity module (swap seam) — oidc.py, sessions.py, deps.py, routes.py
├── services/
│   ├── topics.py · opportunities.py   ← P10 (effective_status lives here) · partners.py ← P11b
│   ├── profiles.py · invites.py · ratelimit.py · cv_text.py   ← P11
│   ├── applications.py · matching.py  ← P12
│   ├── slugs.py · locations.py · seo.py · invites.py   ← P11c–11e (slugs: P13 adds a `fallback` keyword)
│   └── alerts.py · listing_text.py · digest.py · unsubscribe.py · email_prefs.py · saved_searches.py · directory.py · tiein.py   ← P13
├── storage/                   ← P11: blobstore.py (BlobStore, LocalDiskStore, GcsStore)
├── ai/                        ← P11: anthropic_client.py (the only Anthropic client), pricing.py, usage.py, profile_draft.py, prompts/profile_draft_*.md · P11b: opportunity_draft.py, prompts/opportunity_draft_*.md · P12: shortlist_rank.py, prompts/shortlist_rank_*.md (network AI = Anthropic; the help-desk's openrouter.py is a separate, future Phase-4 file)
└── email/                     ← P12: outbox.py (enqueue — P12 schema slice), sender.py, smtp.py, templates/*.txt|*.html
frontend/
├── app/opportunities/{page,view/page}.tsx        ← P10 public board
├── app/admin/{opportunities/{page,edit/page},topics/page}.tsx   ← P10 admin · app/admin/partners/page.tsx ← P11b
├── components/admin/{partners,drafting}/        ← P11b (PartnerSelect; PasteToFill, DraftedChip)
├── app/signin/page.tsx, app/network/{page,join/page,me/page}.tsx   ← P11 (P12: applications/, matches/; P13: directory/, trainer/, searches/, unsubscribed/; trainer/ is the client page behind the server-rendered `/trainers/{slug}`)
├── app/admin/network/{page,trainer/page}.tsx     ← P11 (P12: app/admin/outbox/, app/admin/opportunities/pipeline/)
├── components/{board,admin,network}/
└── lib/{board,adminBoard}.ts (P10) · lib/{network,adminNetwork}.ts (P11) · lib/{adminPartners,adminDraft,compensation}.ts (P11b; compensation.ts is the only compensation formatter)
tests/support/fake_oidc.py     ← P11
```

Import convention: the application package is `src.workshop0.*` (the `src` package exists so `uv run python -m src` boots — harness contract).

## Process model & single-origin serving

**One process serves everything.** `uv run python -m src` starts one uvicorn worker on port **8001**:

- `/api/*` — JSON API (FastAPI routers, sync `def` handlers on the threadpool).
- `/app/*` — the built Next.js static export (`frontend/out/`), mounted with `StaticFiles(html=True)`. Note `/app` and `/app/` themselves are **not** served by the mount from Phase 6 — they 307 to `/` (see below); every deeper path (`/app/create/`, `/app/admin/`, `/app/f/`, `/app/join/`, `/app/p/`, `/app/_next/…`) is served by the mount as normal.
- **Pretty share links** (tiny FastAPI redirect routes, because a static export cannot serve dynamic path segments):
  - `GET /j/{join_slug}` → 307 → `/app/join/?s={join_slug}` (the link on the door)
  - `GET /p/{participant_token}` → 307 → `/app/p/?t={participant_token}` (personal link)
  - `GET /f/{admin_token}` → 307 → `/app/f/?t={admin_token}` (facilitator link)
  - `GET /` → 307 → `/app/` **(Phase 1–5 only; replaced in Phase 6 — see below)**
  - `GET /app` and `GET /app/` → 307 → `/` (Phase 6; the landing page has exactly one URL)
  - `GET /admin` → 307 → `/app/admin/` (Phase 6; the pretty admin-console link)
- No separate Node server in production. `pnpm dev` (port 3000) is inner-loop only and is never the documented test path.

**One uvicorn worker per container is a deliberate choice**: the load profile (below) fits one asyncio process + threadpool. **From Phase 7 the process is fully stateless** — no in-process cache, no per-process throttle state — so Cloud Run may run 0–3 instances concurrently and every instance is interchangeable; the DB is the only shared state. (Phases 1–6 had an in-process snapshot memo that relied on a single process; it is removed — see §Live-update mechanism point 5.) Behind Cloud Run's TLS-terminating front end uvicorn must run with `proxy_headers=True, forwarded_allow_ips="*"` so `request.base_url` is `https://…` and generated share links are correct.

## Public landing page & routing (Phase 6)

From Phase 6 the instance is publicly reachable: `/` is a marketing landing page and anyone can create a workshop without a key. The route map becomes:

| Path | Serves | Auth |
|---|---|---|
| `/` | Public marketing landing page (200 HTML) — its **only** URL | none |
| `/app`, `/app/` | 307 → `/` (no duplicate landing page) | none |
| `/app/create/` | Public create flow (same composer as admin) | none |
| `/app/admin/` (pretty: `/admin`) | Admin console — key gate + all-workshops list, **behaviour unchanged**, only the URL moved off `/` | `X-Admin-Key` |
| `/app/f/`, `/f/{admin_token}` | Facilitator dashboard | admin_token |
| `/app/join/`, `/j/{join_slug}` | Join page | join_slug |
| `/app/p/`, `/p/{participant_token}` | Participant tracker | participant_token |

`/app/admin/` is **not linked from the landing page** (no nav item, no footer link) — it is reached only by someone who knows the URL.

### Serving the landing page at `/` (decision — implement exactly this)

**Decision: the landing page is a normal route of the existing Next.js static export — it becomes `frontend/app/page.tsx` (the export root, `frontend/out/index.html`) — and FastAPI serves that one file's bytes at `/` with a `FileResponse`.** The admin console moves from `frontend/app/page.tsx` to `frontend/app/admin/page.tsx`, the create flow is a new `frontend/app/create/page.tsx`.

Concretely, replacing the Phase-1 `GET /` redirect in `src/workshop0/api/__init__.py`:

```python
LANDING_HTML = FRONTEND_OUT_DIR / "index.html"

@app.get("/", include_in_schema=False)
def _landing():
    if not LANDING_HTML.is_file():          # frontend not built (dev/CI without pnpm build)
        return PlainTextResponse("frontend not built — run `pnpm build` in frontend/",
                                 status_code=503)
    return FileResponse(LANDING_HTML, media_type="text/html",
                        headers={"Cache-Control": "no-cache"})

# Declared BEFORE app.mount("/app", StaticFiles(...)) so the routes take
# precedence over the mount, which would otherwise serve index.html here.
@app.get("/app", include_in_schema=False)
@app.get("/app/", include_in_schema=False)
def _app_root_redirect():
    return RedirectResponse(url="/", status_code=307)
```

Why this shape and no other:

- **One export, one mount, one process, one origin.** No second Next app, no second static mount, no build-output copying, no rewrite proxy.
- **Assets keep working unchanged.** With `basePath: '/app'`, every asset URL Next emits into that HTML is already absolute (`/app/_next/…`), so the identical bytes render correctly when fetched at `/`.
- **`FileResponse`, not a redirect,** because the brief requires `/` itself to *be* the page (a stranger's first impression, shareable, indexable).
- **Exactly one URL for the landing page.** The export root is also addressable at `/app/` through the mount; that duplication is removed by 307-ing `/app` and `/app/` to `/`. Because `/app/` no longer serves anything, the unbuilt-export branch of `GET /` must **not** redirect there (it would loop) — it returns a plain-text **503 "frontend not built"** instead.

Two constraints the frontend slice must honour so this is safe (a generator must not guess here):

1. **The landing page is a static server component** — no `useRouter`/`usePathname`/`useSearchParams`, no data fetching. It hydrates correctly when served at `/`.
2. **Every link out of the landing page is a plain `<a href="/app/create/">`, not `next/link`** — so navigation off `/` is a full document load into the properly-based route, and the App Router never attempts a client-side RSC fetch for a path outside its `basePath`. (`next/link` remains the norm *inside* `/app/*`, where it is correct.)

## Trainer Network & Opportunity Board (Phases 10–13)

### Routes added

| Path | Serves | Auth | Phase |
|---|---|---|---|
| `/opportunities` → 307 `/app/opportunities/` | Public board | none | 10 |
| `/opportunities/{key}` — server-rendered HTML (numeric id → 301 to the slug); was 307 `/app/opportunities/view/?id={id}` | Public listing | none | 10, 11e |
| `/sitemap.xml`, `/robots.txt` | Crawler files (listings; from 13 also `/trainers` and listed trainers) | none | 11e, 13 |
| `/app/admin/opportunities/`, `/app/admin/opportunities/edit/`, `/app/admin/topics/` | Admin board tooling | admin key (P11+: or admin session) | 10 |
| `/app/admin/partners/` | Partner list | admin | 11b |
| `/app/signin/`, `/app/network/`, `/app/network/join/`, `/app/network/me/` | Sign-in, network home, onboarding, my profile | session | 11 |
| `/invite/{token}` → 307 `/app/network/join/?invite={token}`; `/network` → 307 `/app/network/` | Invite + pretty network link | none | 11 |
| `/app/admin/network/`, `/app/admin/network/trainer/` | Trainer pool | admin | 11 |
| `/api/auth/google/callback` | OIDC redirect URI | — | 11 |
| `/app/network/applications/`, `/app/network/matches/`, `/app/admin/opportunities/pipeline/`, `/app/admin/outbox/` | Applications, matched listings, pipeline, outbox | session / admin | 12 |
| `/trainers` → 307 `/app/network/directory/` · `/trainers/{slug}` server-rendered (SEO block, `Person` JSON-LD) | Public trainer directory and profile | none | 13 |
| `/app/network/directory/`, `/app/network/trainer/` (client route behind `/trainers/{slug}`), `/app/network/searches/`, `/app/network/unsubscribed/` | Directory, trainer view, saved searches + email preferences, unsubscribe result | none / session / none | 13 |
| `GET /api/email/unsubscribe`, `POST /api/cron/weekly-digest` | One-click unsubscribe (signed token), weekly digest trigger (`X-Cron-Key`; 404 when the key is unset) | token / cron key | 13 |

Pretty redirects live in `src/workshop0/api/__init__.py` with the existing ones (declared before the `/app` mount). Every new page is a static-export route; dynamic ids travel as query params (`?id=`), exactly like `?t=` on the workshop pages. Pages under `/app/opportunities/` read their query with `useSearchParams` inside a `<Suspense>` boundary (required for static export). Public board pages fetch from the browser (no build-time data), so the export stays data-free.

### Board (Phase 10) — design decisions

- **Expiry is computed on read** (`effective_status`, data-model.md) — no scheduler, restart-proof, identical across instances. Public list queries use the SQL predicate `status='open' AND deadline > :now` with `:now` bound from the app clock (portable to SQLite).
- **Allow-list serializers.** `board_public.py` builds public payloads from an explicit field list; the internal partner name and notes are structurally unreachable from public code. The gate proves it on serialized JSON and rendered HTML.
- **Admin actions are audited in the existing `facilitator_action` table** (actor `admin`, `workshop_id` null, `subject_type`/`subject_id` set) — one audit store for the whole instance.
- **No caching, no search engine.** Tens of listings: indexed filters + offset pagination are instant on db-f1-micro.
- **Partners (Phase 11b).** `partner` is an admin-only table. A listing's public partner text is still its own `partner_display_name`, which the editor copies from the partner's default when the partner is chosen. Public serializers never join or load `partner`, so a partner's internal name and notes are structurally unreachable from public code, like the Phase-10 internal fields. `opportunity.partner_internal_name` is kept as a write-only mirror for rollback safety (data-model.md §Phase 11b).
- **Paste-to-fill (Phase 11b)** is a synchronous admin call through the shared Anthropic client (agent.md §Opportunity drafter). It is rate-limited at 60/h globally, and it writes nothing except its `ai_usage` row.

### Network identity (Phase 11) — the swap seam

- **One module owns identity: `src/workshop0/auth/`.** `oidc.py` (discovery from `WORKSHOP0_OIDC_ISSUER`, default `https://accounts.google.com`; authorization URL with PKCE S256 + state + nonce; code exchange; ID-token verification against the issuer's JWKS — RS256, `iss`, `aud` = client id, `exp` with 60 s leeway, `nonce`), `sessions.py` (opaque 256-bit cookie token, SHA-256 hash stored in `auth_session`, 30-day expiry, revocation), `deps.py`, `routes.py`. **Product code may import only `auth.deps`**: `current_user(request) -> CurrentUser | None`, `require_user` (401 `not_signed_in`; on non-GET also checks the CSRF header), `require_admin` (valid `X-Admin-Key` **or** a session whose user is an admin; returns an `AdminActor(by="admin-key" | <email>)`). `CurrentUser` = `{id, email, display_name, avatar_url, is_admin}`. Nothing outside `auth/` reads `auth_session` or OIDC claims. Moving to a central smallTech identity service later = replacing `oidc.py`/`sessions.py` behind the same `deps.py`.
- **`security.require_admin_key` delegates to `auth.deps.require_admin`** from Phase 11, so every existing admin router (workshops, templates, board) accepts an admin session with no router edits; key behaviour is byte-for-byte unchanged and `WORKSHOP0_ADMIN_KEY` is still required at startup.
- **Empty key header = absent.** Existing frontend clients always send `X-Admin-Key`, as `""` when no key is stored. `require_admin` treats an empty `X-Admin-Key` exactly like a missing header, so a session admin falls through and passes. Order: (1) non-empty header matching `WORKSHOP0_ADMIN_KEY` → `AdminActor(by="admin-key")`; (2) else an admin session → `AdminActor(by=<email>)` (CSRF header required on non-GET); (3) else a signed-in non-admin with no/empty key → 403 `not_admin`; (4) else (no session, or a non-empty wrong key) → 401 `invalid_admin_key`.
- **Admin role** is derived per request from `WORKSHOP0_ADMIN_EMAILS` (comma-separated, case-insensitive) and `email_verified` — no stored role.
- **Cookies:** `workshop0_session` (HttpOnly, SameSite=Lax, Path=/, Max-Age 30 d, `Secure` when the effective base URL is https) and `workshop0_oidc` (signed with `WORKSHOP0_SESSION_SECRET` via itsdangerous, 10 min, cleared at callback).
- **CSRF (changes the old rationale):** until Phase 10 no endpoint was cookie-authenticated. From Phase 11 every cookie-authenticated mutation requires the header `X-Requested-With: workshop0` (a custom header forces a CORS preflight, and the app serves no CORS headers, so a cross-site page cannot send it) in addition to SameSite=Lax. Missing → 403 `csrf_failed`. The frontend network client always sends it.
- **Open-redirect guard:** `next` must start with `/app/`; anything else becomes `/app/network/`.
- **Dev/test issuer:** `WORKSHOP0_OIDC_ISSUER` may be `http://` **only** for `localhost`/`127.0.0.1` (the test issuer, `tests/support/fake_oidc.py`); any other `http://` issuer fails startup.
- **Sign-in disabled** when `WORKSHOP0_GOOGLE_CLIENT_ID` or `WORKSHOP0_GOOGLE_CLIENT_SECRET` is empty: `/api/auth/config` says so, `start` returns 503 `signin_not_configured`, the UI shows a labelled state. `WORKSHOP0_SESSION_SECRET` is required at startup only when sign-in is enabled.
- **Rate limiting (stateless):** `services/ratelimit.py::hit(session, bucket, limit, window_s)` over `rate_limit_hit` (data-model.md) — the DB is the only shared state, so limits hold across Cloud Run instances. Limits: OIDC start 20/min/IP; CV upload/paste 10/h/user; profile drafting additionally 600/h global (cost guard); opportunity drafting 60/h global (P11b, bucket `opportunity_draft`); apply 30/h/user (P12); shortlist 20/h global (P12). Client IP = `request.client.host` (uvicorn already runs with `proxy_headers=True`).

### CV storage (Phase 11)

`storage/blobstore.py`: `put(key, data, content_type)`, `get(key) -> bytes`, `delete(key)`, `download_response(key, filename)` (local: streamed `Response` with `Content-Disposition: attachment`; GCS: 307 to a V4 signed URL, 5 min, signed via the IAM `signBlob` API using the runtime SA's own token — no key files). Backend from `WORKSHOP0_BLOB_BACKEND` (`local` default; `gcs` in production with `WORKSHOP0_GCS_BUCKET`). Local root `data/blobs/` (gitignored with `data/`). The bucket is private: uniform bucket-level access, public access prevention enforced, no lifecycle deletion. CV text (≤24000 chars) goes to Anthropic's API for drafting (accepted); CV files never leave the bucket except via admin/owner download.

### Email (Phase 12)

Transactional outbox: `email/outbox.py::enqueue(session, *, to, template, context, dedupe_key=None)` inserts a row **in the caller's transaction** (unique `dedupe_key` → silently no second row). After commit, a BackgroundTask runs `email/sender.py::drain(limit=20)`: claims `queued` rows (`FOR UPDATE SKIP LOCKED` on PostgreSQL), renders `email/templates/<template>.{txt,html}` (subject on the first line of the `.txt`), sends via `smtp.py`, marks `sent`, or increments `attempts` and marks `failed` after 3. Without SMTP host/user/password, rows are marked `recorded` (shown as "not sent") and logged (`email.recorded`, recipient masked); production boots and runs this way when the SMTP secret is absent. Messages are multipart (plain text + simple HTML), one footer line, no tracking pixels. Per-recipient (10/h) and global (100/h) rate limits are applied at drain time (excess → `recorded`, `rate_limited`). Links use `WORKSHOP0_BASE_URL`, and listing links the slug URL. The password is never logged. Tests use an in-process `aiosmtpd` fake only. Admin page load of the outbox also triggers a drain (self-healing after restarts — no scheduler).

**Phase 13 additions.** Two templates join the allow-list: `network.alert` and `network.digest`. `render` gains one construct, a repeat section `{{#listings}}…{{/listings}}` over a list of flat dicts (inner variables resolve from the item first and are HTML-escaped in the `.html` part; no nesting), so the digest needs no HTML built outside the template. `email_pref` (alerts, digest) is consulted when the row is **enqueued**, never at drain time, and applies to those two templates only; transactional mail ignores it. Listing text for `opportunity.invite`, `network.alert` and `network.digest` comes from one helper, `services/listing_text.py::listing_fields` (partner display name, compensation with unit, every city, slug URL). Unsubscribe links are `{base}/api/email/unsubscribe?t=<token>` with the token signed by `WORKSHOP0_SESSION_SECRET`, which production already has, so Phase 13 needs **no new secret**. Bursts (a publish matching many searches, the weekly digest) drain through `schedule_drain(background, limit=100)`; SMTP unset still ends every row `recorded`.

### Scheduled work (Phase 13)

The only scheduled job is the **optional** weekly digest. `POST /api/cron/weekly-digest` requires header `X-Cron-Key` equal to `WORKSHOP0_CRON_KEY`; with the setting blank the path answers **404**, which is the production default until an operator opts in (deploy/RUNBOOK.md: store a secret `workshop0-cron-key`, apply the proposed conditional mapping, create the Cloud Scheduler job `workshop0-weekly-digest`, Mondays 09:00 `Asia/Kolkata`). The endpoint is idempotent per ISO week (dedupe keys `digest:{user}:{YYYY-Www}`), so a retry or double fire sends nothing twice, and it works on any instance because the dedupe lives in the database. Alerts are not scheduled: they are enqueued inside the transaction that makes a listing open (in a SAVEPOINT, so a failure never blocks publishing), and expire-on-read means a listing that reopens through a later deadline is treated as a new open transition, de-duplicated by `alert:{opportunity}:{user}`.

### Public directory (Phase 13)

Opt-in and allow-listed, mirroring the board: `services/directory.py` is the only code that builds a public trainer payload, from an explicit field list (like `opportunities.public_card`), so rates, email, CV, notes and tags are structurally unreachable. A profile is listed when `visibility = 'public'`, completeness ≥ 60 % and a `public_slug` exists. Completeness is evaluated in Python with batch-loaded topic counts and CV presence; at hundreds of trainers that is cheaper than a second source of truth in SQL. URLs are `/trainers/{slug}` (server-rendered in `api/seo.py` with the exported `network/trainer` page as template, as listings are), never numeric ids. The sitemap and robots extensions are in api.md §Phase 13.

## Live-update mechanism: versioned coalesced polling (decision + justification)

**Decision: short polling with per-workshop version counters and an in-process snapshot cache. No SSE, no WebSockets.**

Load profile: 300+ participants + 1–3 facilitator dashboards on modest hardware (originally a 2 vCPU VM + SQLite; from Phase 7, up to 3 Cloud Run instances + a shared db-f1-micro PostgreSQL), and a hard resilience rule (reconnect/restart must recover purely from the DB).

Why polling beats SSE here:

1. **Resilience is free.** Polling is stateless — after a server restart, every client's next poll simply succeeds with full state. SSE requires reconnect logic, `Last-Event-ID` replay, server-side fan-out state, and produces a thundering-herd reconnect after every restart or deploy. The resilience requirement ("restart loses nothing, reconnect restores exact state") is the polling model's native behavior.
2. **The arithmetic is trivial.** 300 participants polling every 3 s = 100 req/s. Each poll does **one indexed point-read** (the workshop's version row) and, when nothing changed (the overwhelming steady state), returns a ~60-byte `{"changed": false}` response. SQLite in WAL mode serves tens of thousands of point-reads/s; uvicorn serves 100 req/s of this without noticing. SSE's 300 idle connections would also fit in memory — but buys nothing over this, at real complexity cost (proxy buffering config, keepalive pings, per-event fan-out code).
3. **SQLite write contention stays negligible.** Peak write load is a completion burst (~5–10 writes/s) plus joins and help requests. WAL readers never block the writer; each write is a short transaction that also bumps the workshop's version counter. Polling adds almost no writes: the `last_seen_at` touch is a **DB-side conditional UPDATE** (`UPDATE participant SET last_seen_at=:now WHERE id=:id AND last_seen_at < :now - 60s`) — stateless and correct across instances; it matches a row at most once per 60 s per participant (≈ 5 real writes/s at 300 participants) and is a no-match no-op otherwise. (On PostgreSQL the multi-writer model replaces the SQLite WAL single-writer reasoning above; the writes are tiny either way.)
4. **Bandwidth is controlled by two version counters.** Each workshop row carries:
   - `state_version` — bumped on any activity change (join, completion, help, answer, broadcast, pause, advance, reorder…)
   - `content_version` — bumped only when milestone content/order changes.
   Clients send their last-seen `state_version`; unchanged → tiny response. Changed → the poll payload (**without** milestone `content_md` — leaderboard, progress, help state; ~10–15 KB at 300 participants). Milestone bodies are fetched from a separate content endpoint only when `content_version` changes. Worst-case burst (a completion every second, all 300 clients refreshing full payloads) ≈ 1–1.5 MB/s — comfortably inside a modest VM's budget; steady state is ~10 KB/s total.
5. **Snapshot builds are NOT coalesced (changed in Phase 7).** Phases 1–6 memoized the changed-payload per `(workshop_id, state_version)` in-process (TTL 2 s) so 300 pollers shared one build. That memo is **dropped**: it is per-process, so it is incorrect/ineffective once Cloud Run runs several instances, and it is not needed for the steady state (the `{"changed": false}` fast path still costs one indexed point-read). Every poll whose `v` differs from the current `state_version` now builds its own snapshot (a handful of indexed queries). Per-request personal data ("me") is 2–3 indexed point-queries per poll.

   > **REVISIT-IF (memo):** revisit if load testing shows snapshot build is a bottleneck; key was `(workshop_id, state_version)`. Exposure: a completion burst makes up to ~300 clients rebuild the same payload within one poll interval against a db-f1-micro. Candidate fixes, in order: a per-instance memo again (safe because the key includes the version, so it can never serve stale data — only the old 2 s TTL was the safety net for un-versioned `last_seen_at`), then a payload cache table keyed by `(workshop_id, state_version)`. Not built now (no gold-plating); a code comment at the removal site in `services/snapshots.py` carries the same note.

Poll intervals (client, via the `lib/poll.ts` hook): participant tracker **3 s** visible / **15 s** hidden (Page Visibility API); facilitator dashboard **2 s** visible / **10 s** hidden. Every mutation response includes the new `state_version`, and the client polls immediately after any of its own mutations, so the actor always sees their effect within one round-trip (plus optimistic UI, see Error handling).

## Auth model

No accounts anywhere. Three credentials, all generated with `secrets`:

| Credential | Format | Entropy | Carried in | Grants |
|---|---|---|---|---|
| Facilitator access key | operator-chosen string in `.env` (`WORKSHOP0_ADMIN_KEY`, recommend ≥16 chars) | n/a | `X-Admin-Key` request header (entered once on Admin Home, kept in `localStorage`) | Admin Home: list/create workshops, template library |
| Workshop admin token | `secrets.token_urlsafe(32)` → 43 chars | 256 bits | URL path (`/f/{token}`, `/api/f/{token}/…`) | Full facilitator control of one workshop; shareable to co-facilitators |
| Participant token | `secrets.token_urlsafe(16)` → 22 chars | 128 bits | URL path (`/p/{token}`, `/api/p/{token}/…`) **and** cookie | One participant's identity, cross-device |
| Join slug | `secrets.token_urlsafe(6)` → 8 chars | 48 bits (public, not a secret) | URL (`/j/{slug}`) | The join page only |

- Key comparison uses `secrets.compare_digest`. Unknown token/key → 404 (`not_found`) for workshop tokens, 401 (`invalid_admin_key`) for the admin key — never distinguish "wrong" from "missing" for tokens.
- **Participant cookie (auto-resume):** on join, the server sets `workshop0_p_{workshop_id}={participant_token}`; `HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000` (30 days). **One-release compatibility (Phase 9):** if that cookie is absent the server also accepts the legacy-named cookie for the same workshop (same token value) and re-sets it under the new name; only the new name is ever written. The fallback line is marked `LEGACY-COMPAT` in code. `GET /api/join/{slug}` reads it server-side and returns the participant's token if recognized, so the join page silently forwards a returning browser to its tracker. The personal link `/p/{token}` needs no cookie — it *is* the cross-device credential. The facilitator dashboard shows each participant's personal link (copy button) — the lost-link recovery path.
- Structured logs mask all tokens to their first 6 characters.

### Public self-service creation (Phase 6) — what does and does not change

The credential table above is **unchanged**. Creation simply stops requiring the instance key:

- **A public creator's only credential is the workshop's `admin_token`** (their `/f/{admin_token}` link). The facilitator surface is already fully scoped to a single workshop by that token, so a public creator structurally cannot see or touch any other workshop — no new scoping code is needed or permitted.
- **Full facilitator parity, no reduced tier.** On their own workshop a public creator gets every facilitator capability an admin-created workshop has (broadcast, pause, advance, reorder, edit/add/delete milestones, undo, help desk, audit, CSV export, settings). `created_via` is a provenance label; **no endpoint may branch on it for authorization**. The only thing a public creator lacks is the cross-workshop admin list, which lives behind `WORKSHOP0_ADMIN_KEY`.
- **`WORKSHOP0_ADMIN_KEY` keeps exactly one meaning:** the cross-workshop view (list every workshop, public-created included, with creator email and origin) plus the template library. It is still required at startup.
- **Browser `localStorage` is convenience, not auth.** Keys: `workshop0_admin_key` (the admin key typed on Admin Home) and `workshop0_my_workshops` ("your workshops"). **One-release migrate-on-read (Phase 9):** if the new key is absent, read the legacy-named key, write its value under the new key, return it; the legacy key is never deleted in this release (marker `LEGACY-COMPAT`). On successful public creation the browser stores `{name, facilitator_url, join_url, created_at}` locally so the landing page can offer quick links back. It grants nothing — the links it holds are the credential. Clearing the browser loses them permanently, and the landing page, the creation success screen and the FAQ must say so plainly and push the creator to copy/save the facilitator link.
- **The email is the abuse deterrent and contact trail, nothing more.** Format-validated, stored on the workshop, visible only to the admin. No verification, no mail sent (there is no mail infrastructure), and it is not a credential — losing the dashboard link cannot be recovered by proving the email.
- **Accepted risk (explicit):** with no key, no rate limit, no cap and no captcha, this endpoint can be spammed into unbounded workshop rows by a determined actor. Accepted for this phase: the instance is small and self-hosted, workshop rows are cheap, the admin can see and delete every row, and the email requirement raises the effort floor. Rate limiting / caps / captcha are the documented next lever if abuse actually occurs — they are deliberately **not** in this phase.

## Error-handling strategy

- **Envelope (exact, both directions in spec/api.md):** success → HTTP 200, `{"data": …, "error": null}`. Failure → HTTP 4xx/5xx, `{"detail": {"code": "<machine_code>", "message": "<human sentence>"}}` (FastAPI `HTTPException` shape via `api_error()`). One catalogue of `code` values lives in api.md.
- **Fail fast at the boundary.** Request bodies are validated by Pydantic models; domain validation (lengths, state rules like "workshop is archived") raises `api_error` with a specific code. Invalid data never propagates.
- **Optimistic UI with reconciliation.** Mutations (mark complete, send answer) update the UI immediately, fire the request, and reconcile on the response + next poll. On failure: the UI reverts and shows a toast naming the cause and next step ("Couldn't save — retrying in 3 s" / "This workshop is paused").
- **The poll loop is self-healing.** A failed poll (server restarting, network blip) shows a quiet "reconnecting…" indicator after 2 consecutive failures, backs off (3 s → 6 s → 12 s, cap 30 s), and recovers automatically — full state comes from the DB on the first successful poll. No data is ever lost because no data lives only in the client or the process.
- **Startup fails hard** on unrecoverable config (missing `WORKSHOP0_ADMIN_KEY`, unreadable `DATABASE_URL`) with a clear message. A missing `OPENROUTER_API_KEY` is *not* an error — the AI surface reports "AI off (no API key)" and everything else runs (air-gapped guarantee). Likewise a missing `ANTHROPIC_API_KEY` or `ANTHROPIC_WORKSPACE_ID` is not an error: network drafting is `skipped` and shortlists are "Ranked by rules" (key without workspace id additionally logs `ai.network_misconfigured` once at startup).
- **AI failures degrade to manual.** Any AI-pipeline failure (timeout, 5xx, malformed output) logs ERROR and leaves the help request in the normal facilitator queue — the participant experience is identical to AI-off (see agent.md).

## Observability (wired in Phase 1, never deferred)

- **structlog → JSON on stdout.** Every line: `timestamp`, `level`, `event`, `request_id`, plus context.
- **Request middleware:** method, token-masked path, status, `duration_ms`, `request_id` for every API request (poll endpoints log at DEBUG to keep INFO readable).
- **Domain events at INFO:** `workshop.created`, `participant.joined`, `milestone.completed`, `help.created`, `help.answered`, `broadcast.sent`, `workshop.paused`, `undo.applied`, `ai.triage`, `ai.auto_answered`, `ai.draft_created`, `ai.failed` — each with ids and (for AI) latency, token counts, cost.
- **Network events at INFO (Phases 10–13):** `opportunity.created`, `opportunity.updated`, `opportunity.status_changed`, `topic.created`, `topic.updated`, `auth.signin`, `auth.signin_failed` (with reason code), `auth.invite_accepted`, `auth.signout`, `profile.created`, `cv.uploaded`, `account.deleted`, `ai.profile_draft` and `ai.shortlist_rank` (model, latency, tokens, cost — the same `ai.*` shape as the help-desk events, emitted only by `ai/usage.py::record_usage`), `ai.call_failed` (ERROR: purpose, cause, HTTP status, Anthropic request-id), `ai.network_misconfigured` / `ai.pricing_unknown` (WARNING), `ratelimit.blocked`, `application.created`, `application.status_changed`, `email.sent`/`email.recorded`/`email.failed`. Emails masked; CV text never logged.
- **No metrics endpoint, no ops UI** (vision non-goal). `GET /api/health` returns `{"status":"ok","db":"ok"}` for machines.

## Database configuration

- **Production = PostgreSQL** (`DATABASE_URL=postgresql+psycopg://workshop0_app:…@10.110.112.7:5432/workshop0?sslmode=require`, injected from a Secret Manager secret). **Local default = SQLite** (`sqlite:///data/workshop0.db`), pragmas applied per-connection via a `connect` listener: `PRAGMA journal_mode=WAL; synchronous=NORMAL; busy_timeout=5000; foreign_keys=ON;`.
- SQLAlchemy: sync engine, `pool_pre_ping=True`. SQLite: `connect_args={"check_same_thread": False}`. **PostgreSQL pool is sized for a shared 90-connection instance:** `pool_size=3`, `max_overflow=2`, `pool_timeout=10`, `pool_recycle=1800` (all env-tunable, below). Budget rule: `max-instances × (pool_size + max_overflow) ≤ ~15` → 3 × 5 = 15, plus 1 for the migrate job. Never raise Cloud Run `max-instances` without recomputing this.
- A scheme of `postgres://` or `postgresql://` is normalised to `postgresql+psycopg://` at settings load. Models use portable types only (Integer/Text/Boolean/DateTime(timezone=True)/Numeric + JSON as Text). Integer PKs are PostgreSQL identity/serial columns (relevant to the Phase-8 import: sequences are reset). The FTS5 help corpus (Phase 4) is SQLite-only; **in production the PostgreSQL variant (tsvector + GIN) is the build target** — see agent.md.
- Any query that is only correct on SQLite (unordered `LIMIT`, case-insensitive-by-accident matching, loose `GROUP BY`, naive-datetime assumptions) is an app bug to fix, not a test to weaken.
- All timestamps stored UTC; serialized as ISO 8601 `Z` (`2026-07-20T14:03:22Z`).
- Transactions are short: one request = one transaction (commit in the session dependency). Any state-changing write bumps the workshop's `state_version` in the same transaction.
- **Lazy lifecycle transitions (Phase 3):** no cron/background scheduler. Every workshop-scoped request first applies due transitions (`grace_until` passed → `archived`) inside the request transaction — restart-proof by construction.

## Security notes

- **XSS:** all facilitator/AI-authored markdown (milestones, broadcasts, answers) renders through react-markdown with **raw HTML disabled** — HTML in markdown source is not injected. Participant-authored text (names, help messages) is rendered as **plain text** (React text nodes, `whitespace-pre-wrap`), never as markdown or HTML.
- **SQL injection:** SQLAlchemy ORM/parameterized queries only. The FTS5 `MATCH` query string is built from sanitized, quoted tokens (see agent.md).
- **CSRF:** workshop state-changing endpoints are authenticated by unguessable URL tokens or the `X-Admin-Key` header — not by cookies — so cross-site form posts cannot forge them. The participant cookie is only ever *read* to resolve auto-resume on `GET /api/join/{slug}`. **From Phase 11** the network session cookie authenticates mutations, which therefore also require `X-Requested-With: workshop0` (§Network identity).
- **Network privacy (Phases 10–13):** internal partner fields (incl. the Phase-11b `partner` table's internal name and notes, and `opportunity.partner_id`), trainer rates, emails, CV files/text, admin notes and tags are admin-only (rates, email and CV metadata also appear in the owner's own `/api/me/*` payloads; raw CV text, blob key and hash are returned to no one — api.md §Phase 11 → Privacy). Every public serializer is an allow-list; gates assert absence on serialized JSON and rendered HTML. Logs mask emails (`as***@example.com`) and never contain CV text.
- **Secrets:** only in `.env` (gitignored). Logs and API responses never contain `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_WORKSPACE_ID` or `WORKSHOP0_ADMIN_KEY`; key presence is logged as a boolean (`app.startup` gains `anthropic_key_present` and `anthropic_workspace_present` in Phase 11).
- **Rate limiting:** none on the workshop surface (self-hosted, unguessable tokens, trusted room); the trainer network's sign-in, upload, drafting, apply and shortlist endpoints are rate-limited from Phase 11 (§Network identity). > **Assumed:** acceptable for a single-team instance; revisit if ever exposed as SaaS. From Phase 6 this extends to the keyless `POST /api/public/workshops` — see §Auth model → Accepted risk.
- **Creator email (Phase 6):** stored, returned only on the admin list, masked in logs (`as***@example.com`), never rendered on a participant- or public-facing surface.

## Environment variables (complete list)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | no | `sqlite:///data/workshop0.db` | SQLAlchemy URL; **PostgreSQL in production** (Cloud Run gets it from secret `workshop0-database-url`) |
| `WORKSHOP0_DB_POOL_SIZE` | no | `3` | PostgreSQL pool size (ignored on SQLite) |
| `WORKSHOP0_DB_MAX_OVERFLOW` | no | `2` | PostgreSQL pool overflow |
| `WORKSHOP0_MIGRATE_ON_BOOT` | no | `1` | `1` → container entrypoint runs `alembic upgrade head` before serving (local compose). **Cloud Run sets `0`**: migrations run only in the `workshop0-migrate` job |
| `TEST_DATABASE_URL` | tests only | — | PostgreSQL URL of a throwaway `*_test` database; the suite refuses any database whose name does not end in `_test` |
| `PORT` | no | `8001` | HTTP port (Cloud Run injects `8080`) |
| `WORKSHOP0_ADMIN_KEY` | **yes** | — | Facilitator access key for Admin Home |
| `WORKSHOP0_BASE_URL` | no | derived from request | Absolute base for generated share links (set behind a proxy) |
| `WORKSHOP0_LOG_LEVEL` | no | `INFO` | structlog level |
| `OPENROUTER_API_KEY` | no | — | AI help-desk; absent → fully air-gapped, zero errors |
| `WORKSHOP0_AI_MODEL` | no | `anthropic/claude-sonnet-4-6` | OpenRouter model id |
| `WORKSHOP0_AI_CONFIDENCE` | no | `0.75` | Auto-answer confidence threshold (see agent.md) |
| `ANTHROPIC_API_KEY` | no (P11) | — | Anthropic key for network AI (drafter, ranker). Absent ⇒ drafting `skipped`, shortlists "Ranked by rules", zero errors. Local: `.env`; Cloud Run: secret `workshop0-anthropic-api-key` |
| `ANTHROPIC_WORKSPACE_ID` | with the key (P11) | — | Sent as header `anthropic-workspace-id` on **every** Anthropic request (the key is not workspace-scoped; without it the API returns 400). Key set + this empty ⇒ network AI treated as unavailable + `ai.network_misconfigured` WARNING. Cloud Run: secret `workshop0-anthropic-workspace-id` |
| `WORKSHOP0_AI_NETWORK_MODEL` | no (P11) | `claude-sonnet-5-5` | Anthropic model for CV extraction, opportunity drafting (P11b) and shortlist ranking (agent.md §Network AI) |
| `WORKSHOP0_AI_NETWORK_FAST_MODEL` | no (P11) | `claude-haiku-5-5` | Anthropic model for cheap calls (only the client smoke tests in Phases 11–13) |
| `WORKSHOP0_GOOGLE_CLIENT_ID` | no (P11) | — | Google OAuth web client id; with the secret, enables sign-in |
| `WORKSHOP0_GOOGLE_CLIENT_SECRET` | no (P11) | — | Google OAuth client secret (Cloud Run: secret `workshop0-google-client-secret`) |
| `WORKSHOP0_OIDC_ISSUER` | no (P11) | `https://accounts.google.com` | OIDC issuer for discovery; `http://localhost:*` allowed for the test issuer only |
| `WORKSHOP0_SESSION_SECRET` | when sign-in enabled (P11) | — | Signs the OIDC state cookie and unsubscribe tokens (Cloud Run: secret `workshop0-session-secret`, generated by `provision.sh`) |
| `WORKSHOP0_ADMIN_EMAILS` | no (P11) | `''` | Comma-separated admin allowlist |
| `WORKSHOP0_BLOB_BACKEND` | no (P11) | `local` | `local` (`data/blobs/`) or `gcs` |
| `WORKSHOP0_GCS_BUCKET` | when `gcs` | — | `ai-agent-boilerplate0-workshop0-cvs` in production |
| `WORKSHOP0_SMTP_HOST` / `_PORT` / `_STARTTLS` | no (P12) | `smtp.gmail.com` / `587` / `1` | SMTP server; tests use a local `aiosmtpd` sink with STARTTLS `0` |
| `WORKSHOP0_SMTP_USER` / `WORKSHOP0_SMTP_PASSWORD` | no (P12) | — | Gmail address + app password; either empty ⇒ outbox records, never sends; never logged. Not in Secret Manager until the operator runs `provision.sh --rotate workshop0-smtp-password` and applies the proposed workflow mapping (RUNBOOK) |
| `WORKSHOP0_SMTP_FROM` | no (P12) | `Workshop0 <SMTP_USER>` | From header |
| `WORKSHOP0_CRON_KEY` | no (P13) | — | Shared secret for `/api/cron/*` (header `X-Cron-Key`); empty ⇒ cron endpoints return 404. Optional: production runs without it (digest off) until the operator follows the RUNBOOK; CI passes a test value to the `:8001` and `:8013` e2e instances and leaves it empty on `:8014` |

## Deploy shape

### Local / image (Phase 5, still valid)

- `deploy/Dockerfile` — multi-stage: (1) Node stage builds the frontend export, (2) Python stage with uv installs the app and copies `frontend/out/`. Same image for compose and Cloud Run.
- `deploy/entrypoint.sh` — `entrypoint.sh migrate` runs `alembic upgrade head` and exits (used by the Cloud Run job). With no argument it serves; **before serving it runs `alembic upgrade head` only if `WORKSHOP0_MIGRATE_ON_BOOT` is `1`/`true`** (default `1`, so local compose is unchanged; Cloud Run sets `0`). It should exec the venv interpreter directly (not `uv run`) to keep cold starts short.
- `deploy/docker-compose.yml` — local dev: one service, named volume for `data/` (SQLite), `env_file: .env`, port 8001. Kept after Phase 8.
- `.github/workflows/ci.yml` — on PR/push: backend job with a **`postgres:17` service container** (`POSTGRES_PASSWORD=postgres`, `POSTGRES_DB=workshop0_test`, `--health-cmd pg_isready`), `TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/workshop0_test`, then `uv run pytest tests/unit tests/integration -q`; frontend build; e2e job also runs the app against a Postgres service container (`DATABASE_URL` set, `alembic upgrade head` first). Real-key tests run only where secrets exist (guarded skip).

### Production topology (Phase 7+) — Cloud Run + Cloud SQL

```
GitHub Actions ──WIF (no keys)──▶ workshop0-deployer SA
   build image ─▶ Artifact Registry us-central1/workshop0 ─▶ Cloud Run Job workshop0-migrate (alembic upgrade head)
        └─▶ Cloud Run service workshop0: new revision --no-traffic (tag candidate) ─▶ health check ─▶ shift 100% ─▶ health check ─▶ (fail ⇒ roll back)

Browser ─HTTPS─▶ Cloud Run (workshop0, 0–3 instances, run.app URL; workshop0.smalltech.in via Cloud Run domain mapping, Phase 8)
                   └─ Direct VPC egress (network default, subnet default, private-ranges-only) ─TLS─▶ Cloud SQL ai-agent-db 10.110.112.7:5432 / db workshop0
Secrets: Secret Manager workshop0-* ─(--set-secrets, runtime SA workshop0-run)─▶ env
```

| Concern | Decision |
|---|---|
| Project / region | `ai-agent-boilerplate0` (number `870371939888`) / **`us-central1`** |
| Region trade-off (deliberate) | Co-located with the database. Putting the service in `asia-south1` (nearer the India-based participants) would put every DB query across ~200 ms of inter-region latency — a poll that does 3 queries would cost ~600 ms and a full snapshot build seconds. Co-location instead costs India users one ~200 ms network round-trip per request, paid once and in parallel, not per query. Chosen: DB-adjacent. Revisit only if the database moves. |
| Service | Cloud Run service `workshop0`, image `us-central1-docker.pkg.dev/ai-agent-boilerplate0/workshop0/workshop0:<sha12>`, public via an `allUsers` -> `roles/run.invoker` binding made by `provision.sh` on a pre-created placeholder service (the workflow never passes `--allow-unauthenticated`; the deployer has no setIamPolicy), port 8080 |
| Sizing | `--cpu 1 --memory 512Mi --concurrency 40 --timeout 60 --max-instances 3 --min-instances 0 --cpu-boost --no-cpu-throttling`. `--no-cpu-throttling` (CPU allocated outside requests) is required because the Phase-4 AI pipeline runs as a post-response `BackgroundTask`, which request-billed Cloud Run would starve. With min-instances 0 an instance still scales to zero when idle. |
| Scale-to-zero | Default `min-instances=0` → first request after idle pays a cold start (a few seconds). Before a workshop the operator runs **workshop mode** (`min-instances=1`) and turns it off after (see below). |
| VPC egress | Direct VPC egress: `--network=default --subnet=default --vpc-egress=private-ranges-only` (sets annotations `run.googleapis.com/network-interfaces: [{"network":"default","subnetwork":"default"}]` and `run.googleapis.com/vpc-access-egress: private-ranges-only`). Internet egress (OpenRouter; from Phase 11 `api.anthropic.com`) goes direct, not through the VPC. |
| TLS to DB | Instance is `ENCRYPTED_ONLY`; URL carries `sslmode=require` (encrypted; server cert not verified — private IP, accepted). |
| Migrations | Cloud Run Job **`workshop0-migrate`** (same image + env + secrets + VPC egress, `--command entrypoint.sh --args migrate`, `--max-retries 0`) executed with `--wait` **before** the new revision receives traffic. Revisions run with `WORKSHOP0_MIGRATE_ON_BOOT=0`. Migrations must stay backward-compatible with the previous revision for the one-deploy overlap window (additive first, destructive in a later release). |
| Traffic shift + rollback guard | `gcloud run deploy workshop0 --no-traffic --tag candidate --revision-suffix sha-<sha12>`; `GET https://candidate---…run.app/api/health` must return `{"status":"ok","db":"ok"}` (retry up to 60 s); then `update-traffic --to-revisions NEW=100`; health-check the service URL again; **any failure ⇒ `update-traffic --to-revisions <PREV>=100`** (PREV captured before the deploy) and the job exits non-zero. First-ever deploy (no service yet) deploys directly. |
| Secrets (Secret Manager, prefix `workshop0-`) | `workshop0-database-url` (full URL incl. password), `workshop0-openrouter-api-key`, `workshop0-admin-key`; mounted via `--set-secrets DATABASE_URL=workshop0-database-url:latest,OPENROUTER_API_KEY=…,WORKSHOP0_ADMIN_KEY=…`. Created only by `provision.sh`, value via stdin (`gcloud secrets versions add --data-file=-`), never in argv, logs or the repo. |
| Service accounts | `workshop0-run` (runtime): `roles/secretmanager.secretAccessor` bound **per secret** on the three `workshop0-*` secrets only; no project-level roles. `workshop0-deployer` (CI): `roles/run.developer`, `roles/artifactregistry.writer` (on repo `workshop0`), `roles/iam.serviceAccountUser` on `workshop0-run`, `roles/secretmanager.viewer` on the three secrets (> **Assumed:** needed for `--set-secrets` validation; if the gate shows it is not required, drop it). Public-invoker IAM (`allUsers` → `roles/run.invoker`) is granted once by `provision.sh`, not by CI. |
| Workload Identity Federation | Existing pool `projects/870371939888/locations/global/workloadIdentityPools/github`; **new provider `workshop0-github`** (OIDC issuer `https://token.actions.githubusercontent.com`, mapping `google.subject=assertion.sub, attribute.repository=assertion.repository, attribute.ref=assertion.ref`, **attributeCondition `assertion.repository=='smallTechOrg/workshop0'`**). `roles/iam.workloadIdentityUser` on `workshop0-deployer` for `principalSet://…/attribute.repository/smallTechOrg/workshop0`. The provider/pool IDs are not secrets and are written in the workflow. Other apps' providers are never modified. |
| Artifact Registry | docker repo `workshop0`, `us-central1`; images tagged by 12-char git SHA (+ `latest`) |
| Database bootstrap | `provision.sh` creates DB `workshop0` and user `workshop0_app` via the Cloud SQL Admin API (`gcloud sql databases/users create`), password generated locally (`openssl rand -hex 24`, hex ⇒ URL-safe) and stored **only** in `workshop0-database-url`; on re-run the password is read back from Secret Manager and re-applied, never regenerated. The instance is private-IP-only, so schema privileges cannot be granted from the operator's laptop: `provision.sh` runs `deploy/cloudrun/dbinit.py` as a one-off Cloud Run Job `workshop0-dbinit` (VPC-attached) that probes whether `workshop0_app` can `CREATE TABLE` in `public` and, if not, runs `GRANT workshop0_app TO postgres; ALTER DATABASE workshop0 OWNER TO workshop0_app;` using the instance's `postgres` password supplied once via an interactive no-echo prompt → a temporary secret `workshop0-tmp-pgadmin` (stdin) that is deleted (trap) before the script exits. The `postgres` password is never stored. |
| Logging | structlog JSON on stdout is ingested by Cloud Logging; each line also carries `severity` (mapped from `level`) so Cloud Logging colours/filters correctly. |
| Phase-4 AI on Cloud Run | `OPENROUTER_API_KEY` from Secret Manager; absent/empty secret value ⇒ air-gapped as before. The FTS5 corpus is SQLite-only; the PostgreSQL tsvector variant (agent.md) is what Phase 4 builds in production. |
| Trainer network on Cloud Run (Phases 11–13) | `provision.sh` gains (idempotent, `CREATED`/`EXISTS`): the CV bucket + its two IAM bindings, `workshop0-session-secret` (generated `openssl rand -hex 32`), `workshop0-google-client-secret` (from the operator's `WORKSHOP0_GOOGLE_CLIENT_SECRET` env/.env; absent ⇒ prints `SKIPPED … (set WORKSHOP0_GOOGLE_CLIENT_SECRET and re-run)`), `workshop0-anthropic-api-key` + `workshop0-anthropic-workspace-id` (from the operator's `ANTHROPIC_API_KEY` / `ANTHROPIC_WORKSPACE_ID` env/.env, values via stdin; each absent ⇒ `SKIPPED`, never `die` — unlike the Phase-7 OpenRouter secret), P12 `workshop0-smtp-password` (same SKIPPED rule), P13 `workshop0-cron-key` + the Cloud Scheduler job (API `cloudscheduler` enabled). Per-secret `secretAccessor` for `workshop0-run` and `secretmanager.viewer` for `workshop0-deployer`, as for the existing secrets. `deploy-cloudrun.yml` passes `WORKSHOP0_BLOB_BACKEND=gcs`, `WORKSHOP0_GCS_BUCKET`, the GitHub variables, and maps each optional secret **only if it has an enabled version** (`gcloud secrets versions list --filter=state=ENABLED --limit=1`), so a not-yet-created Google/SMTP/Anthropic secret never breaks a deploy — the feature simply stays in its labelled "not configured" state. The two Anthropic secrets are mapped **as a pair** (`ANTHROPIC_API_KEY=workshop0-anthropic-api-key:latest,ANTHROPIC_WORKSPACE_ID=workshop0-anthropic-workspace-id:latest`) only when **both** have an enabled version. **Creating any of these secrets in GCP is an operator step** (the human runs `provision.sh` with the values exported); agents write and syntax-check `provision.sh` but never run it against the project — it is escalated in the phase's "How the user tests it". |

**Workshop mode (scale control).** The deploy workflow ends by routing traffic to `LATEST` (`update-traffic --to-latest`, asserted equal to the deployed revision), so the service is not pinned to a named revision and a plain `gcloud run services update workshop0 --min-instances 1|0` creates a revision that serves 100% immediately (proven on the live service; a subsequent deploy preserves the value). There is no helper script. After a manual rollback or the rollback guard, traffic is pinned to a named revision; run `update-traffic --to-latest` (or any successful deploy) to resume. The workflow's `workflow_dispatch` input `min_instances` (`""` = leave unchanged, `0`, `1`) can set it; a normal deploy never changes min-instances (omitting the flag preserves the live value).

**Backup / restore.** Cloud SQL automated backups + PITR are an instance-level setting owned by the instance's owner (shared with other apps) — Workshop0 does not alter them. Per-database logical backup: `gcloud sql export sql ai-agent-db gs://<bucket>/workshop0-$(date +%F).sql --database=workshop0` (documented in RUNBOOK, requires a bucket the operator owns).

**Phase status.** Phase 7 (Cloud Run + Cloud SQL) is delivered and merged in its PR; Phase 8 (cutover) retires the VM path. **Snapshot memo:** dropped in Phase 7; revisit (shared, not per-process) only if load testing shows snapshot build is a bottleneck; key was `(workshop_id, state_version)`. The poll `leaderboard` is capped to the top 15 plus the caller's own row.

**Domain.** `workshop0.smalltech.in` is mapped to the service in Phase 8 (Cloud Run domain mapping, supported in `us-central1`; Google-managed certificate). Until then the `*.run.app` URL is the product URL. DNS is at GoDaddy and is a manual human step (exact records in the Phase 8 section of the roadmap). At cutover the operator sets the GitHub repository variable `WORKSHOP0_BASE_URL=https://workshop0.smalltech.in`, which the deploy workflow passes to the service, so share links use the pretty domain even if opened via `run.app`.

**Retired VM.** The legacy GCE VM, its disk and its static IP were deleted on 2026-10-29 after a verified backup of its SQLite database; the `DEPLOY_*` GitHub secrets were removed. Rollback of a bad release is Cloud Run revision rollback; data recovery is Cloud SQL export/restore. The old VM deploy path stays in git tag `vm-deploy-final`.

**Rename (Phase 9).** All cloud resources, the repo and the code carry the Workshop0 names fixed in §Naming (Workshop0) below. The cutover (new database copied from the old one, new service deployed beside the old, domain mapping moved, old resources deleted last) is specified in [roadmap.md](roadmap.md) Phase 9.

## Naming (Workshop0)

Single source of truth for every name (Phase 9). Each entry replaces the same-kind resource that carried the previous product name; no other spec file restates these. Nothing is derived from the old name: DB table/column names, stored tokens and their derivation, the admin-key value and the public domain are unchanged.

| Kind | Name |
|---|---|
| Product / brand (UI, docs, emails, CSV filenames) | **Workshop0** |
| GitHub repository | `smallTechOrg/workshop0` (GitHub redirects the old URL; git history and tag `vm-deploy-final` are not rewritten) |
| Local checkout directory / harness skill directory | `workshop0/` · `harness/skills/workshop0/` |
| Python package / import path | `src/workshop0/` · `src.workshop0.*` (the `src` package and `uv run python -m src` stay) |
| pyproject project name | `workshop0` |
| Frontend package name (`frontend/package.json`) | `workshop0-frontend` |
| Environment-variable prefix | every legacy-prefixed variable becomes `WORKSHOP0_*`: `WORKSHOP0_ADMIN_KEY`, `WORKSHOP0_BASE_URL`, `WORKSHOP0_DOMAIN`, `WORKSHOP0_LOG_LEVEL`, `WORKSHOP0_AI_MODEL`, `WORKSHOP0_AI_CONFIDENCE`, `WORKSHOP0_DB_POOL_SIZE`, `WORKSHOP0_DB_MAX_OVERFLOW`, `WORKSHOP0_MIGRATE_ON_BOOT`. `OPENROUTER_API_KEY`, `DATABASE_URL`, `TEST_DATABASE_URL`, `PORT` are unchanged. The old prefix is **not** read |
| Default SQLite file | `data/workshop0.db` |
| Logger names | `workshop0` / `workshop0.<module>` |
| Participant cookie | `workshop0_p_{workshop_id}` (legacy-named cookie read as a one-release fallback) |
| `localStorage` keys | `workshop0_admin_key`, `workshop0_my_workshops` (legacy-named keys read-migrated for one release, never deleted) |
| Cloud Run service | `workshop0` |
| Cloud Run jobs | `workshop0-migrate`, `workshop0-dbinit` (plus transient `workshop0-import` from `import-data.sh`) |
| Artifact Registry repo / image | repo `workshop0`; image `us-central1-docker.pkg.dev/ai-agent-boilerplate0/workshop0/workshop0:<sha12>` |
| Service accounts | `workshop0-deployer`, `workshop0-run` (`@ai-agent-boilerplate0.iam.gserviceaccount.com`) |
| Secret Manager secrets | `workshop0-database-url`, `workshop0-openrouter-api-key`, `workshop0-admin-key` (transient `workshop0-tmp-pgadmin`) |
| Cloud SQL (shared instance `ai-agent-db`, untouched otherwise) | database `workshop0`, user `workshop0_app`; local/CI test database `workshop0_test` |
| Workload Identity Federation | provider `workshop0-github` in the existing pool `github`, attribute condition `assertion.repository=='smallTechOrg/workshop0'`, `workloadIdentityUser` on `workshop0-deployer` for `attribute.repository/smallTechOrg/workshop0` |
| GitHub Actions variable | `WORKSHOP0_BASE_URL` |
| Import bucket (transient) | `ai-agent-boilerplate0-workshop0-import-<rand>` |
| CV bucket (Phase 11) | `ai-agent-boilerplate0-workshop0-cvs` (`us-central1`, private, uniform access, public-access prevention); `workshop0-run` has `roles/storage.objectAdmin` on it only, plus `roles/iam.serviceAccountTokenCreator` on itself (V4 signed URLs) |
| Network secrets | `workshop0-google-client-secret` (P11, value from the operator), `workshop0-session-secret` (P11, generated), `workshop0-anthropic-api-key` + `workshop0-anthropic-workspace-id` (P11, values from the operator), `workshop0-smtp-password` (P12, Gmail app password, optional), `workshop0-cron-key` (P13, **optional**, operator-chosen value; `provision.sh` skips it when no value is given and never generates one, so a fresh Phase-13 deploy needs no new secret) |
| GitHub Actions variables (network) | `WORKSHOP0_GOOGLE_CLIENT_ID`, `WORKSHOP0_ADMIN_EMAILS` (P11), `WORKSHOP0_SMTP_USER` (P12; proposal only, workflow unchanged in Phase 12) |
| Cloud Scheduler job (Phase 13, optional) | `workshop0-weekly-digest` (`us-central1`), created by the operator from the RUNBOOK, not by `provision.sh` or the workflow |

The three permitted survivals of the previous name in the repository are: the git tag `vm-deploy-final` (it contains no legacy word), the operator's local backup directory path and one historical sentence ("Workshop0 was previously called Workshop <previous name>") in `deploy/RUNBOOK.md`, plus the `LEGACY-COMPAT` shim lines described above.

## Key architectural decisions (summary)

| Decision | Rationale |
|---|---|
| Versioned coalesced polling, no SSE | Restart/reconnect resilience for free; ~100 req/s of point-reads is trivial; no fan-out state, no proxy pitfalls |
| Two version counters (`state_version` / `content_version`) | Keeps steady-state polls at ~60 bytes and burst payloads ~10–15 KB; milestone bodies transfer only when edited |
| Stateless instances; no in-process snapshot memo (Phase 7) | Cloud Run runs several interchangeable instances; the DB is the sole shared state. Memo dropped (revisit note in §Live-update point 5) and `last_seen_at` throttle moved into the UPDATE's WHERE clause |
| Cloud Run + shared Cloud SQL Postgres in `us-central1` (Phase 7) | No VM to patch, scale-to-zero cost, automated pipeline with rollback guard; region co-located with the DB because per-query cross-region latency is worse than one user round-trip |
| Pool budget `max-instances × (pool_size+max_overflow) ≈ 15` | The Cloud SQL instance (max_connections=90) is shared with other apps; Workshop0 must never be able to exhaust it |
| Milestones as a real table (not JSON blob) | Per-milestone stats for 300 participants via indexed GROUP BY; FTS/context queries for the AI phase |
| Static Next.js export served by FastAPI at `/app/` + pretty-link redirects | Single origin, one process, harness gate path; dynamic tokens carried in query params where the static router needs them, pretty in shared URLs |
| Lazy lifecycle transitions on access | No scheduler process to crash or restart; correctness derives from the DB clock check |
| Audit + undo share one table (`facilitator_action`) | One write per action serves the audit trail, the undo window, and AI-answer logging |
| Landing page = the export root, served at `/` by `FileResponse` (Phase 6) | Public `/` without a second app, second mount or proxy; `basePath: '/app'` already makes every asset URL absolute, so the same bytes render at `/`; `/app` and `/app/` 307 to `/` so the page has one URL |
| Listing expiry computed on read, allow-list public serializers (Phase 10) | No scheduler to fail; internal partner data structurally unreachable from public code |
| Identity isolated in `src/workshop0/auth/`, product code sees only `auth.deps` (Phase 11) | Google today, a central smallTech identity service later, without touching product code |
| Network AI calls Anthropic directly; two LLM providers coexist (Phase 11+) | User decision: the drafter and ranker use the official `anthropic` SDK with `ANTHROPIC_API_KEY` + the mandatory `anthropic-workspace-id` header, while the Phase-4 help-desk stays on OpenRouter (not migrated; its pipeline module is not yet in code). Separate modules and separate secrets keep the two from interfering, and both write the same `ai_usage` rows and `ai.*` events, so spend reporting is uniform. **Possible later item:** migrate the help-desk to the same Anthropic client and retire `OPENROUTER_API_KEY` / `workshop0-openrouter-api-key`. Not scheduled |
| DB-backed rate limits and email outbox (Phases 11–12) | Stateless Cloud Run instances share only the DB; nothing is lost on restart and limits hold across instances |
| One creation service called by both the admin and public routes (Phase 6) | Admin- and public-created workshops are identical records apart from `creator_email` + `created_via`; validation cannot drift between two copies |
