# Workshop0

Self-hosted workshop assistant for facilitator-led hands-on technical labs: a facilitator creates a workshop with content-rich milestones, participants join with just a name, and a genuinely live dashboard tracks the whole room — with a built-in help desk.

> **All commands run from the repo root.** Every Python command is prefixed with `uv run` — bare commands will fail.

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 22 and [pnpm](https://pnpm.io/)
- PostgreSQL 17 (tests run against PostgreSQL, never SQLite — see "Run the tests")

## Setup (once)

```bash
# from the repo root
cp .env.example .env          # then set WORKSHOP0_ADMIN_KEY (any strong string, >=16 chars)
uv sync
(cd frontend && pnpm install)
pnpm install                  # root: Playwright for e2e tests
pnpm exec playwright install chromium   # only needed to run the e2e suite
```

## Database

Local development defaults to SQLite (`data/workshop0.db`); production runs on PostgreSQL (Cloud SQL).

```bash
# from the repo root
uv run alembic upgrade head
uv run alembic current        # MUST print a revision hash — blank output means no migration was applied
```

To run the app against PostgreSQL instead, set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db` in `.env`.

## Build the UI and run

```bash
# from the repo root
(cd frontend && pnpm build)
uv run python -m src
```

Open **http://localhost:8001/** — the public landing page. From there, **Create your workshop** needs no access key: compose the workshop, give your email at the last step, and you are handed your facilitator dashboard link and the join link to share.

### URLs

| URL | What it is |
|---|---|
| `/` | Public landing page — its **only** URL (served from the static export's `index.html`; returns 503 "frontend not built" if you have not run `pnpm build`). `/app` and `/app/` 307 back here |
| `/app/create/` | Keyless self-service workshop creation |
| `/admin` → `/app/admin/` | Admin console — enter your `WORKSHOP0_ADMIN_KEY` to see **every** workshop, with its origin (`Admin`/`Public`) and the public creator's email. Not linked from the landing page |
| `/j/<slug>` | Join link — share with the room |
| `/p/<token>` | Participant personal link |
| `/f/<token>` | Facilitator dashboard link — the only credential for a workshop; save it |
| `/opportunities` → `/app/opportunities/` | Public **Opportunity Board** — open listings from the smallTech partner network, filterable by type and topic (filters live in the URL), 12 per page. No sign-in |
| `/opportunities/<id>` → `/app/opportunities/view/?id=<id>` | One listing's public page (closed/expired listings show a "closed" banner; drafts are not found) |
| `/app/admin/opportunities/` | Admin: post, edit, publish, unpublish, close and reopen listings (same `WORKSHOP0_ADMIN_KEY` gate as Admin Home). Internal partner name and notes are admin-only — never on a public page or API |
| `/app/admin/topics/` | Admin: the topic taxonomy (40 seeded topics in 5 categories; add, rename, deactivate) |

Listings expire on their own at their apply-by deadline (computed on read — no scheduler). Signing in, applying and trainer profiles are later phases; the board shows them as labelled "Coming in a later phase" stubs.

There are no accounts and no login: a link is the credential. A workshop created from the public flow has the **full** facilitator toolset — it differs from an admin-created one only by its stored creator email and origin flag.

## Run the tests

The suite runs against **PostgreSQL 17** (the production driver). It refuses any database whose name does not end in `_test`.

```bash
# one-time PostgreSQL setup (macOS, from any directory)
brew install postgresql@17 && brew services start postgresql@17
createdb workshop0_test
```

```bash
# from the repo root
export TEST_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/workshop0_test"
uv run pytest tests/unit tests/integration -q
```

If your PostgreSQL listens on another port or needs a password, adjust the URL accordingly (`postgresql+psycopg://user:pass@host:port/workshop0_test`).

The Opportunity Board tests and gate need **no `.env`** and no external credentials. Without a `.env`, export an admin key first — any value works; the server and the e2e helpers both read it:

```bash
# from the repo root
export WORKSHOP0_ADMIN_KEY="${WORKSHOP0_ADMIN_KEY:-phase10-local-gate-key-0123}"
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic current     # must print 0005 (head)
```

```bash
# e2e — from the repo root; build the UI first, then run the server in one terminal ...
(cd frontend && pnpm build)
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" uv run python -m src

# ... and the suite in another (from the repo root)
pnpm exec playwright test tests/e2e --reporter=line
# target a deployed origin instead of localhost:8001 (no local server needed):
# BASE_URL=https://your-host pnpm exec playwright test tests/e2e --reporter=line
```

## Run with Docker (local dev)

```bash
# from the repo root (needs .env with WORKSHOP0_ADMIN_KEY)
docker compose -f deploy/docker-compose.yml up --build
```

App-only, SQLite in a named volume, migrations applied on boot; open http://localhost:8001/.

## Deploying to Cloud Run

Production is Cloud Run + Cloud SQL (project `ai-agent-boilerplate0`, region `us-central1`), served at https://workshop0.smalltech.in/ after the Phase 8 cutover. Pushes to `main` run `.github/workflows/deploy-cloudrun.yml`: PostgreSQL tests, image build, migrate job, no-traffic candidate revision, health check, traffic shift, health check, automatic rollback on failure. Authentication is keyless (Workload Identity Federation). Any branch can be deployed by hand with `gh workflow run deploy-cloudrun.yml --ref <branch>`. The Docker Compose file is for local development only. Full detail (topology, cutover from the old VM, rollback, backups): [deploy/RUNBOOK.md](deploy/RUNBOOK.md).

```bash
# from the repo root — one-time, idempotent provisioning (operator must be gcloud-authenticated;
# WORKSHOP0_ADMIN_KEY and OPENROUTER_API_KEY are read from the environment or .env, never echoed)
bash deploy/cloudrun/provision.sh
```

Workshop mode keeps one instance warm (no cold start). Traffic always follows the latest revision, so a plain update is enough:

```bash
gcloud run services update workshop0 --region us-central1 --project ai-agent-boilerplate0 --min-instances=1   # before the workshop
gcloud run services update workshop0 --region us-central1 --project ai-agent-boilerplate0 --min-instances=0   # after
```

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | no | `sqlite:///data/workshop0.db` | SQLAlchemy URL; **PostgreSQL in production** |
| `WORKSHOP0_DB_POOL_SIZE` | no | `3` | PostgreSQL pool size (ignored on SQLite) |
| `WORKSHOP0_DB_MAX_OVERFLOW` | no | `2` | PostgreSQL pool overflow |
| `WORKSHOP0_MIGRATE_ON_BOOT` | no | `1` | `1` → the container entrypoint runs `alembic upgrade head` before serving; Cloud Run sets `0` (migrations run in the `workshop0-migrate` job) |
| `TEST_DATABASE_URL` | tests only | — | PostgreSQL URL of a throwaway `*_test` database |
| `PORT` | no | `8001` | HTTP port (Cloud Run injects `8080`) |
| `WORKSHOP0_ADMIN_KEY` | **yes** | — | Facilitator access key for Admin Home |
| `WORKSHOP0_BASE_URL` | no | derived from request | Absolute base for generated share links |
| `WORKSHOP0_LOG_LEVEL` | no | `INFO` | Log level (structlog, JSON to stdout) |
| `OPENROUTER_API_KEY` | no | — | AI help-desk (Phase 4); absent = fully air-gapped |
| `WORKSHOP0_AI_MODEL` | no | `anthropic/claude-sonnet-4-6` | OpenRouter model id |
| `WORKSHOP0_AI_CONFIDENCE` | no | `0.75` | AI auto-answer confidence threshold |

## Status

The product (public landing page, keyless workshop creation, live dashboard, help desk, admin console, and — Phase 10 — the public Opportunity Board with its admin listing and topic tools) is built; production runs on Cloud Run + Cloud SQL (PostgreSQL) (Phase 7), and Phase 8 moves the data and `workshop0.smalltech.in` over from the old VM. The spec in `spec/` is the source of truth.
