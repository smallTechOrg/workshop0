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
| `/app/signin/` | Trainer-network sign-in page (**Continue with Google**; shows a labelled "not set up" state when sign-in is not configured) |
| `/network` → `/app/network/` | Network home — routes you to sign-in, onboarding or your profile |
| `/app/network/join/` | Onboarding: drop a CV (PDF / DOCX / LinkedIn "Save to PDF") or paste text, review the pre-filled profile, consent |
| `/app/network/me/` | My profile — completeness meter, nudges, own-CV download, **Delete my account** |
| `/invite/<token>` → `/app/network/join/?invite=<token>` | Admin-issued invite link; signing in with the invited email starts the profile **Verified** |
| `/app/admin/network/` | Admin: the trainer pool — search and filters, CSV export, invites, **Network AI spend** card |
| `/app/admin/network/trainer/?id=<id>` | Admin: one trainer — CV download, verify, tags, notes, drafting cost, activity |
| `/api/auth/google/callback` | The OIDC redirect URI registered in the Google Console |

Listings expire on their own at their apply-by deadline (computed on read — no scheduler). Applying to a listing, matching and the email outbox are Phase 12; the UI shows them (and the other later-phase features) as labelled "Coming in a later phase" stubs.

Workshops have no accounts and no login: a link is the credential. A workshop created from the public flow has the **full** facilitator toolset — it differs from an admin-created one only by its stored creator email and origin flag. Only the trainer network (below) has accounts.

## Trainer network (Phase 11)

The trainer network is how smallTech finds trainers for the Opportunity Board. A tech person clicks **Join our network** on the board, signs in with Google, drops a CV or pastes text, and checks a profile that the AI has pre-filled from the CV on one review screen. Drafted fields are marked "From your CV — please check". They consent, and the profile is live. Admins sign in with Google (their email is on `WORKSHOP0_ADMIN_EMAILS`) or still use `WORKSHOP0_ADMIN_KEY`. They can search the pool, open a trainer, download the CV, verify the trainer, add tags and notes, invite a known trainer by link, export CSV and see what the drafting cost. A trainer can delete their account, which removes the user, the profile, the CV and the sessions.

Everything in the network is optional. With no Google client configured, the sign-in page shows a labelled "not set up" state and the rest of the app works unchanged. With no Anthropic credentials, drafting is skipped: the review screen starts empty and the trainer fills it in by hand.

### Sign-in setup: Google Console (one-time, about 5 minutes)

In the GCP Console, project `ai-agent-boilerplate0`:

1. APIs & Services → **OAuth consent screen** → User type **External** → app name **Workshop0**, support email = your smallTech email, authorized domain `smalltech.in`, scopes `openid`, `email`, `profile`.
2. Add yourself as a test user (or **Publish app** to allow anyone; these scopes need no Google verification).
3. **Credentials** → **Create credentials → OAuth client ID** → Application type **Web application**, name `workshop0-web`.
4. **Authorized JavaScript origins:** `http://localhost:8001`, `https://workshop0.smalltech.in`.
5. **Authorized redirect URIs:** `http://localhost:8001/api/auth/google/callback`, `https://workshop0.smalltech.in/api/auth/google/callback`.
6. **Create** → copy the client ID and secret.

### Local `.env` for sign-in

```bash
# in .env (never commit it; never paste these values anywhere else)
WORKSHOP0_GOOGLE_CLIENT_ID=<client id from step 6>
WORKSHOP0_GOOGLE_CLIENT_SECRET=<client secret from step 6>
WORKSHOP0_SESSION_SECRET=<output of: openssl rand -hex 32>
WORKSHOP0_ADMIN_EMAILS=<your email>          # comma-separated, case-insensitive
```

`WORKSHOP0_SESSION_SECRET` is required at startup whenever sign-in is enabled (both Google values set). Admin rights come from `WORKSHOP0_ADMIN_EMAILS`, checked on every request against Google-verified emails only, so taking an email off the list revokes access on the next request.

### Local `.env` for CV drafting (Anthropic)

The CV drafter calls Anthropic directly (not OpenRouter, which stays the workshop help-desk's provider). Set both values:

```bash
# in .env
ANTHROPIC_API_KEY=<your Anthropic API key>
ANTHROPIC_WORKSPACE_ID=<your Anthropic workspace id>
```

The key is not workspace-scoped, so every Anthropic request carries the mandatory `anthropic-workspace-id` header. Without it the API returns HTTP 400. Drafting is therefore skipped unless **both** values are set. With only the key, the app makes no Anthropic call and logs one `ai.network_misconfigured` WARNING at startup. Check the `app.startup` log line, which should show `anthropic_key_present: true, anthropic_workspace_present: true`.

Then build and run as usual: `(cd frontend && pnpm build)`, `uv run python -m src`, and open **http://localhost:8001/opportunities** → **Join our network**.

### Local fake OIDC issuer (development and tests)

You don't need Google credentials to develop or test sign-in. `tests/support/fake_oidc.py` is a local OpenID Connect issuer that speaks the same real authorization-code protocol (discovery, PKCE, RS256 ID tokens, JWKS). Its sign-in page has a single email field and approves whatever email you type.

```bash
# terminal 1 — from the repo root
uv run python tests/support/fake_oidc.py --port 8099

# terminal 2 — from the repo root; point the app at it (http:// issuers are allowed only for localhost/127.0.0.1)
export WORKSHOP0_OIDC_ISSUER=http://localhost:8099
export WORKSHOP0_GOOGLE_CLIENT_ID=test-client WORKSHOP0_GOOGLE_CLIENT_SECRET=test-secret
export WORKSHOP0_SESSION_SECRET="$(openssl rand -hex 32)" WORKSHOP0_ADMIN_EMAILS=admin@example.test
uv run python -m src
```

Sign in as `admin@example.test` to act as an admin. Any other email signs in as a trainer. `uv run python tests/support/fake_oidc.py --help` lists the failure flags the auth tests use, such as `--unverified`, `--wrong-aud`, `--expired` and `--bad-signature`.

### CV storage

CVs are stored under `data/blobs/` locally (`WORKSHOP0_BLOB_BACKEND=local`, the default, gitignored with `data/`). Production uses a private GCS bucket (`WORKSHOP0_BLOB_BACKEND=gcs`, `WORKSHOP0_GCS_BUCKET`), and downloads go through a 5-minute signed URL. Only the CV text (up to 24,000 characters) is sent to Anthropic. The file itself never leaves storage except when an admin or the owner downloads it.

> **Phase 11b** (partners list, paste-to-fill opportunity drafting, compensation units) is being specified concurrently. It will be documented here once specified.

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

### Phase 11 gate (trainer network)

The real Anthropic key and workspace id are read from your gitignored `.env` and never echoed. The gate is **blocked**, not skipped, without both. No `gcloud`, Google or SMTP credentials are needed, because sign-in runs against the local fake issuer.

```bash
# from the repo root
export TEST_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/workshop0_test"
export WORKSHOP0_ADMIN_KEY="${WORKSHOP0_ADMIN_KEY:-phase11-local-gate-key-0123}"
envval() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '"'"'"; }      # .env values are unquoted or simply quoted
export ANTHROPIC_API_KEY="$(envval ANTHROPIC_API_KEY)" ANTHROPIC_WORKSPACE_ID="$(envval ANTHROPIC_WORKSPACE_ID)"
test -n "$ANTHROPIC_API_KEY" && test -n "$ANTHROPIC_WORKSPACE_ID"                      # BLOCKED (not skipped) without both
export WORKSHOP0_GOOGLE_CLIENT_ID=test-client WORKSHOP0_GOOGLE_CLIENT_SECRET=test-secret
export WORKSHOP0_OIDC_ISSUER=http://localhost:8099 WORKSHOP0_SESSION_SECRET="$(openssl rand -hex 32)"
export WORKSHOP0_ADMIN_EMAILS=admin@example.test WORKSHOP0_BLOB_BACKEND=local
uv sync
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head && DATABASE_URL="$TEST_DATABASE_URL" uv run alembic current | grep -q '^0006'
uv run python tests/support/fake_oidc.py --port 8099 &                                 # real OIDC protocol, local issuer
sleep 2
uv run pytest tests/unit tests/integration -q                                          # incl. auth/, network/, storage/, ai/, ai_network/ (REAL Anthropic, workspace header)
! uv run pytest tests/unit/ai tests/integration/ai_network -q -rs | grep -q SKIPPED   # real-key tests ran, none skipped
! grep -rn --include='*.py' 'Anthropic(' src | grep -v '^src/workshop0/ai/anthropic_client.py:'   # one construction site
! grep -il openrouter src/workshop0/ai/{anthropic_client,pricing,usage,profile_draft}.py           # network AI never uses OpenRouter
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

GCS storage tests run only when `WORKSHOP0_GCS_BUCKET` is set.

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

The trainer network adds the CV bucket and the `workshop0-session-secret`, `workshop0-google-client-secret`, `workshop0-anthropic-api-key` and `workshop0-anthropic-workspace-id` secrets. It also adds the GitHub variables `WORKSHOP0_GOOGLE_CLIENT_ID` and `WORKSHOP0_ADMIN_EMAILS`. All of these are operator steps, covered in [deploy/RUNBOOK.md](deploy/RUNBOOK.md) "Trainer network secrets (Phase 11, operator step)".

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
| `WORKSHOP0_GOOGLE_CLIENT_ID` | no (P11) | — | Google OAuth web client id; with the secret, enables trainer-network sign-in |
| `WORKSHOP0_GOOGLE_CLIENT_SECRET` | no (P11) | — | Google OAuth client secret (Cloud Run: secret `workshop0-google-client-secret`) |
| `WORKSHOP0_OIDC_ISSUER` | no (P11) | `https://accounts.google.com` | OIDC issuer for discovery; `http://` allowed only for `localhost`/`127.0.0.1` (the fake test issuer) |
| `WORKSHOP0_SESSION_SECRET` | when sign-in is enabled (P11) | — | Signs the OIDC state cookie; generate with `openssl rand -hex 32` (Cloud Run: secret `workshop0-session-secret`, generated by `provision.sh`) |
| `WORKSHOP0_ADMIN_EMAILS` | no (P11) | `''` | Comma-separated, case-insensitive admin allowlist (verified Google emails only) |
| `WORKSHOP0_BLOB_BACKEND` | no (P11) | `local` | CV storage: `local` (`data/blobs/`) or `gcs` |
| `WORKSHOP0_GCS_BUCKET` | when `gcs` | — | CV bucket; `ai-agent-boilerplate0-workshop0-cvs` in production |
| `ANTHROPIC_API_KEY` | no (P11) | — | Anthropic key for network AI (CV drafting). Absent: drafting `skipped`, zero errors (Cloud Run: secret `workshop0-anthropic-api-key`) |
| `ANTHROPIC_WORKSPACE_ID` | with the key (P11) | — | Sent as header `anthropic-workspace-id` on every Anthropic request; key set and this empty means network AI is unavailable, plus an `ai.network_misconfigured` WARNING (Cloud Run: secret `workshop0-anthropic-workspace-id`) |
| `WORKSHOP0_AI_NETWORK_MODEL` | no (P11) | `claude-sonnet-5-5` | Anthropic model for CV extraction |
| `WORKSHOP0_AI_NETWORK_FAST_MODEL` | no (P11) | `claude-haiku-5-5` | Anthropic model for cheap calls (only the client's real-key smoke tests in Phase 11) |

## Status

The product (public landing page, keyless workshop creation, live dashboard, help desk, admin console, and — Phase 10 — the public Opportunity Board with its admin listing and topic tools) is built; Phase 11 adds the trainer network (Google sign-in, CV-drafted trainer profiles, the admin trainer pool); production runs on Cloud Run + Cloud SQL (PostgreSQL) (Phase 7), and Phase 8 moves the data and `workshop0.smalltech.in` over from the old VM. The spec in `spec/` is the source of truth.
