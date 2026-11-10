# Claude Code — Entry Point

Read this file first, then follow the instructions below.

## What This Repo Is

**Workshop0** — a self-hosted workshop tracker (FastAPI + SQLAlchemy 2 + Alembic + SQLite/PostgreSQL backend, Next.js 15 / React 19 / Tailwind v4 static export frontend), built spec-first with the zero-shot SDD harness; it also hosts the Trainer Network & Opportunity Board. One uvicorn process on port 8001 serves both `/api/*` and the built frontend at `/app/*` — single origin, no separate Node server in production. The spec in `spec/` is fully written and is the source of truth; when spec and code disagree, the spec wins (`/zero-shot-sync`).

## Your First Action Every Session

1. Read `harness/rules/ai-agents.md` — mandatory rules for all AI sessions
2. Check whether `spec/roadmap.md` has been filled in:
   - If it still contains `<!-- FILL IN -->` placeholders → the spec is not ready; do not write application code yet
   - If it is filled in → proceed to read the full spec manifest below before touching any code

## Spec Manifest (read in this order when spec is complete)

```
spec/vision.md
spec/roadmap.md
spec/architecture.md
spec/capabilities.md
spec/data-model.md
spec/api.md
spec/agent.md     ← the AI help-desk pipeline design (OpenRouter; Phase 4) + §Network AI (Anthropic; Phases 11–12)
harness/rules/ai-agents.md
harness/patterns/spec-driven.md
harness/patterns/phases.md
harness/patterns/project-layout.md
harness/patterns/engineering-practices.md
harness/patterns/test-driven.md
harness/patterns/ui-ux.md
harness/patterns/tech-stack.md     ← generic stack rules (chosen stack is in spec/architecture.md)
harness/patterns/code.md           ← generic code conventions
harness/patterns/agentic-ai.md     ← catalogue of agentic patterns (chosen graph is in spec/agent.md)
harness/rules/git.md
```

**`spec/agent.md` is mandatory** for any project using LangGraph, CrewAI, AutoGen, or any agent orchestration framework. If it does not exist when you reach Phase 2, stop and raise it as a blocker. (The reusable catalogue of agentic-AI patterns to choose from lives in `harness/patterns/agentic-ai.md`.)

## If the Spec Is Not Ready

Tell the user to run **`/zero-shot-build [their idea]`**. That skill runs one intake round — the only interactive setup step. It may ask additional clarifying questions, and asks the user to fill `.env` with the required API keys/secrets. Once intake completes, the **agent-builder** orchestrator runs design → scaffold → build, one phase per invocation. It is autonomous *within* a phase and stops at each phase boundary for a **human testing gate** — the user tests the increment before the next phase starts. Each phase delivers the smallest user-testable win, built first-time-right on the tested path.

## Skills (entry points)

These are the entry points. All are manual (`disable-model-invocation: true`). Each is invocable as a skill **and** as a slash command (`.claude/commands/<name>.md` defers to the skill — the skill is the source of truth, so the two never drift).

| Skill / command | Purpose |
|-----------------|---------|
| `/zero-shot-build [idea]` | Idea → working, verified skeleton (drives the agent-builder). Also adds a new capability. |
| `/zero-shot-fix [target]` | Diagnose + fix a bug, error, failing test, or spec/code drift, then verify. |
| `/zero-shot-sync [scope]` | Reconcile spec ↔ code so they match (spec wins), then verify. |

## Key Rules (summary — full rules in harness/rules/ai-agents.md)

- Never write application code before reading the full spec
- Never skip a phase — complete phase N before starting phase N+1
- Commit every logical unit of work; never let the working tree stay dirty
- Each phase is tested by the human before the next phase starts — stop at the phase boundary, hand off the test instructions, and wait for the user
- Tight scope, first-time-right — each phase is the smallest user-testable win and must work the first time the user tests it; zero rough edges on the tested path
- Tests and evals run against the real LLM/API using keys from `.env` — never gate the build on offline/stubbed runs
- When in doubt, ask at intake — do not guess requirements; once intake completes, build a phase autonomously and stop for the human testing gate

## The app in `src/`

`src/` is the working application, packaged as `src.workshop0.*` (booted with `uv run python -m src`) — FastAPI routers in `src/workshop0/api/` (`admin.py`, `facilitator.py`, `participant.py`, `public.py`, `health.py`, `board_public.py`, `board_admin.py`, `board_ai_admin.py`, `partners_admin.py`, `network_me.py`, `network_admin.py`, `network_public.py`, `matching_admin.py`, `pipeline_admin.py`, `outbox_admin.py`, `directory_public.py`, `seo.py`; `__init__.py` holds `create_app()`, the pretty-link redirects and the static mount), domain logic in `src/workshop0/services/`, `auth/` (Google OIDC, sessions, CSRF deps), `ai/` (Anthropic network AI: CV/opportunity drafting, shortlist ranking, pricing/usage; sends the `anthropic-workspace-id` header), `email/` (outbox, sender, SMTP, templates; prod records mail as not-sent until the SMTP secret is configured), `storage/blobstore.py` (local/GCS CVs). SEO routes: `/opportunities/{slug}`, `/trainers/{slug}`, `/sitemap.xml`, `/robots.txt`; `POST /api/cron/weekly-digest` (`X-Cron-Key`, 404 when unset). Also SQLAlchemy models in `src/workshop0/db/models.py`, DB session in `src/workshop0/db/session.py`, auth/token helpers in `src/workshop0/security.py`, settings in `src/workshop0/config/settings.py`, structlog setup in `src/workshop0/observability/logging.py`. The UI is a Next.js static export — source in `frontend/app/` + `frontend/components/` + `frontend/lib/`, built with `(cd frontend && pnpm build)` to `frontend/out/` and mounted by FastAPI at `/app`. Schema changes go through Alembic (`alembic/versions/` 0001–0012, `render_as_batch=True`). CI (`ci.yml`) runs `backend`, `frontend-build` and `e2e` jobs. Production is **Cloud Run + Cloud SQL PostgreSQL** (`DATABASE_URL` from Secret Manager; deployed by `.github/workflows/deploy-cloudrun.yml`, provisioned by `deploy/cloudrun/provision.sh`, see `deploy/RUNBOOK.md`); SQLite at `data/workshop0.db` is the local-dev default only, and tests run on PostgreSQL via `TEST_DATABASE_URL`. The LLM surface in code is the Anthropic network AI (`ai/`, spec/agent.md §Network AI); the OpenRouter AI help-desk is specified (Phase 4) but not built. There is no agent framework or tool-use loop. Generators extend the app in place — they never copy or rename — and change nothing the spec doesn't require.

## Sub-agents (the team)

`/zero-shot-build` delegates a full build to **agent-builder**, which plans and coordinates the rest and owns git/PR. `/zero-shot-fix` and `/zero-shot-sync` call the workers directly (no agent-builder) and own git themselves. Each agent is one full, self-contained definition at `.claude/agents/<name>.md` (the path is the agent slug).

| Agent | Role | Tools |
|-------|------|-------|
| agent-builder | Orchestrator — plans phases, fans out code-generator instances per slice (in parallel), and owns the git/PR surface for a build | read/bash/agent |
| spec-writer | The single design authority — writes the FULL spec (incl. architecture + agent-graph + phased plan) **and** self-reviews it | read/write |
| code-generator | Implements ONE independent slice (backend `src/`, frontend `frontend/`, or both) plus tests — spawned in parallel, one per slice | read/write/bash |
| qa-auditor | Independent review **and** run gates/tests/app **and** audit spec↔code drift; runs FIRST in fix/sync and classifies root cause SPEC-vs-CODE | read-only (bash) |

Pattern: **spec-writer** writes the whole spec and carves each phase into independent slices. **agent-builder** fans out one **code-generator** per slice in a single Agent message (max parallelism — disjoint paths, never conflict). **qa-auditor** independently gates each slice and audits drift — it never edits. The **human tests between phases**.
