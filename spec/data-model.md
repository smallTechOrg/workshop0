# Data Model — Workshop0 (v0.2)

> Phases 10–13 (Trainer Network & Opportunity Board) add tables incrementally — see the section of that name at the end of this file.

SQLAlchemy 2.x declarative models in `src/workshop0/db/models.py`; schema managed by Alembic (the `0001_initial` migration creates the **full v0.2 schema below**, even though later phases activate some tables). All state lives here — never only in process memory (resilience rule). All `DateTime` columns are timezone-aware UTC. JSON payloads are stored as `Text` (portable across SQLite/PostgreSQL). **Production engine is PostgreSQL 17 (Phase 7+)**; SQLite remains the local-dev default. Integer primary keys are identity/serial columns on PostgreSQL — any bulk load that inserts explicit ids (the Phase-8 import) must reset each table's sequence to `max(id)`.

**Phase activation:** the "Phase" column says when the app first *writes/uses* the field — the schema itself exists from Phase 1 so later phases never migrate-and-backfill mid-season.

Conventions: integer autoincrement PKs; `created_at` default now; `updated_at` onupdate now where noted; FK columns always indexed.

---

## workshop

The unit of a live session. One row per run.

| Column | Type | Constraints | Phase | Notes |
|---|---|---|---|---|
| id | Integer | PK | 1 | |
| name | String(120) | not null | 1 | |
| description_md | Text | not null, default `''` | 1 | Shown on join page; markdown |
| admin_token | String(64) | not null, **unique, indexed** | 1 | `token_urlsafe(32)` |
| join_slug | String(16) | not null, **unique, indexed** | 1 | `token_urlsafe(6)` |
| status | String(16) | not null, default `'live'` | 1 (`live`), 3 (rest) | `upcoming` \| `live` \| `grace` \| `archived` |
| starts_at | DateTime | nullable | 3 | Set → `upcoming` until reached (lazy transition) |
| ended_at | DateTime | nullable | 3 | Facilitator pressed "End workshop" |
| grace_until | DateTime | nullable | 3 | End of straggler window; passed → `archived` (lazy) |
| grace_hours | Integer | not null, default `24` | 3 | Chosen at end time |
| paused | Boolean | not null, default false | 2 | Blocks milestone completions |
| state_version | Integer | not null, default `0` | 1 | Bumped (same transaction) on ANY change a poller can see |
| content_version | Integer | not null, default `0` | 1 | Bumped only on milestone content/order changes |
| ai_enabled | Boolean | not null, default `false` | 4 | Per-workshop AI toggle |
| join_form_json | Text | not null, default `'[]'` | 3 | Snapshot of extra join fields (see JSON shapes) |
| stuck_minutes | Integer | not null, default `10` | 2 | Stuck-alert threshold (per workshop) |
| cloned_from_id | Integer | FK workshop.id, nullable | 3 | Provenance of a clone |
| agenda_template_id | Integer | FK agenda_template.id (SET NULL), nullable | 3 | Which template instantiated it |
| creator_email | String(254) | **nullable** | 6 | Email the public creator gave at the end of the create flow. `null` for admin-created workshops and for every row that existed before the Phase-6 migration. Never shown on any participant or facilitator surface — admin list only |
| created_via | String(16) | not null, default `'admin'`, server_default `'admin'` | 6 | Origin flag: `admin` \| `public`. Existing rows backfill to `'admin'` by the server default |
| created_at | DateTime | not null | 1 | |
| updated_at | DateTime | not null, onupdate | 1 | |

Indexes: unique(admin_token), unique(join_slug), ix(status).

**Phase-6 migration (`0004_public_creation`, `down_revision = "0003"`):** adds the two columns above inside `with op.batch_alter_table("workshop") as batch:` (`render_as_batch=True` is already configured — required for SQLite ALTER). `creator_email` is `sa.String(254), nullable=True`; `created_via` is `sa.String(16), nullable=False, server_default="admin"` so existing rows backfill in place with no data migration step. `downgrade()` drops both columns in the same batch block. No other table changes.

> **Assumed:** 254 chars for `creator_email` (RFC 5321 practical maximum) and no uniqueness constraint — one person may create several workshops, and the email is a contact trail, not an identity.

**`created_via` semantics:** set to `'public'` exactly when the workshop was created through the keyless public endpoint, `'admin'` when created through the admin-key endpoint. It carries no permission meaning — a `public` workshop is byte-for-byte an `admin` workshop apart from these two columns (see [capabilities.md](capabilities.md) §C5).

**Status lifecycle (Phase 3):** `upcoming` → (starts_at reached) → `live` → (End workshop) → `grace` → (grace_until passed or Archive-now) → `archived`. Transitions are applied lazily inside any workshop-scoped request; `archived` is terminal and read-only (every mutation returns `workshop_archived`). Phase 1–2 workshops are created directly `live` and stay `live`.

---

## milestone

A real table (not JSON): per-milestone stats over 300 participants need indexed GROUP BYs, and the AI phase needs per-milestone content lookup.

| Column | Type | Constraints | Phase | Notes |
|---|---|---|---|---|
| id | Integer | PK | 1 | |
| workshop_id | Integer | FK workshop.id CASCADE, not null | 1 | |
| position | Integer | not null | 1 | 0-based display order; reordering rewrites positions |
| title | String(200) | not null | 1 | |
| content_md | Text | not null, default `''` | 1 | Rich markdown: instructions, links, code snippets. ≤20,000 chars |
| minutes | Integer | nullable | 1 | Facilitator's time estimate; feeds pulse/projection (Phase 2) |
| created_at | DateTime | not null | 1 | |
| updated_at | DateTime | not null, onupdate | 1 | |

Indexes: ix(workshop_id, position).

**Semantics:** checklist, any order — participants may complete milestones in any sequence (no gating). A participant's **current milestone** = lowest-position incomplete milestone (used for help context, bottleneck detection). **Progress** = completed ÷ total milestones.

---

## participant

| Column | Type | Constraints | Phase | Notes |
|---|---|---|---|---|
| id | Integer | PK | 1 | |
| workshop_id | Integer | FK workshop.id CASCADE, not null | 1 | |
| name | String(80) | not null | 1 | Trimmed; duplicates allowed (disambiguated by join time in UI) |
| token | String(32) | not null, **unique, indexed** | 1 | `token_urlsafe(16)` — personal link + cookie value |
| answers_json | Text | not null, default `'{}'` | 3 | Custom join-form answers `{field_key: value}` |
| joined_at | DateTime | not null | 1 | |
| last_seen_at | DateTime | not null | 1 (write), 2 (read) | Touched by polls via a DB-side conditional UPDATE (`… WHERE last_seen_at < now − 60 s`), so ≤1 effective write/60 s per participant across all instances; feeds presence + stuck alerts |

Indexes: unique(token), ix(workshop_id).

---

## milestone_completion

| Column | Type | Constraints | Phase | Notes |
|---|---|---|---|---|
| id | Integer | PK | 1 | |
| participant_id | Integer | FK participant.id CASCADE, not null | 1 | |
| milestone_id | Integer | FK milestone.id CASCADE, not null | 1 | |
| source | String(16) | not null, default `'participant'` | 1 (`participant`), 2 (`facilitator`) | Who marked it (advance-all/selected writes `facilitator`) |
| completed_at | DateTime | not null | 1 | |

Indexes: **unique(participant_id, milestone_id)** (idempotent completes), ix(milestone_id) (per-milestone stats), ix(participant_id).

Un-marking deletes the row (participants may fix a mis-click; history of the fix lives in the log stream, not the table).

---

## help_request

| Column | Type | Constraints | Phase | Notes |
|---|---|---|---|---|
| id | Integer | PK | 1 | |
| workshop_id | Integer | FK workshop.id CASCADE, not null | 1 | Denormalized for queue + cross-workshop learning queries |
| participant_id | Integer | FK participant.id CASCADE, not null | 1 | |
| milestone_id | Integer | FK milestone.id (SET NULL), nullable | 1 | The participant's current milestone at submit time |
| message | Text | not null | 1 | 1–4000 chars; participant-authored → rendered as plain text |
| status | String(16) | not null, default `'open'` | 1 | `open` \| `answered` \| `resolved` |
| escalated | Boolean | not null, default false | 4 | Participant tapped "get a human" after an AI answer → back to `open`, flagged |
| ai_state | String(16) | nullable | 4 | `pending` \| `answered` \| `draft` \| `failed` \| `skipped` — pipeline observability |
| created_at | DateTime | not null | 1 | |
| updated_at | DateTime | not null, onupdate | 1 | |

Indexes: ix(workshop_id, status, created_at) (queue), ix(participant_id).

**Status semantics:** `open` = awaiting an answer (facilitator queue). `answered` = an answer is visible to the participant (AI auto-answer or facilitator reply) — stays that way until the **participant** marks `resolved` (or the facilitator closes it). `escalated=true` returns status to `open` with the flag set; prior AI answers remain visible.

---

## help_answer

One request can accumulate answers (AI draft → AI answer → facilitator follow-up), so answers are rows, not columns.

| Column | Type | Constraints | Phase | Notes |
|---|---|---|---|---|
| id | Integer | PK | 1 | |
| help_request_id | Integer | FK help_request.id CASCADE, not null | 1 | |
| source | String(16) | not null | 1 (`facilitator`), 4 (`ai`) | `facilitator` \| `ai` |
| answer_md | Text | not null | 1 | Markdown; rendered with code blocks |
| draft | Boolean | not null, default false | 4 | true = AI draft awaiting facilitator review — never shown to the participant |
| ai_confidence | Numeric(4,3) | nullable | 4 | Model-reported, post-guardrail (0–1) |
| ai_model | String(120) | nullable | 4 | OpenRouter model id used |
| ai_context_json | Text | nullable | 4 | Exact context the AI used (see JSON shapes) — expandable in the queue |
| created_at | DateTime | not null | 1 | |

Indexes: ix(help_request_id, created_at).

---

## broadcast

| Column | Type | Constraints | Phase | Notes |
|---|---|---|---|---|
| id | Integer | PK | 2 | |
| workshop_id | Integer | FK workshop.id CASCADE, not null | 2 | |
| message_md | Text | not null | 2 | Markdown; ≤4000 chars |
| created_at | DateTime | not null | 2 | |
| cleared_at | DateTime | nullable | 2 | null = the active pinned banner (at most one: sending a new one clears the previous) |

Indexes: ix(workshop_id, cleared_at).

---

## facilitator_action — audit trail + undo + AI answer log

Every facilitator action and every AI-sent answer, forever.

| Column | Type | Constraints | Phase | Notes |
|---|---|---|---|---|
| id | Integer | PK | 1 | |
| workshop_id | Integer | FK workshop.id CASCADE, nullable | 1 | null for instance-level actions (workshop.create logs on the new row) |
| actor | String(16) | not null | 1 | `facilitator` \| `ai` \| `system` |
| action | String(48) | not null | 1 | Code, e.g. `workshop.create`, `help.answer`, `help.resolve`, `broadcast.send`, `workshop.pause`, `workshop.resume`, `milestone.advance_all`, `milestone.advance_selected`, `milestone.reorder`, `milestone.edit`, `workshop.end`, `workshop.archive`, `workshop.clone`, `ai.auto_answer`, `ai.draft`, `ai.toggle`, `undo.apply` |
| detail_json | Text | not null, default `'{}'` | 1 | Human-renderable specifics (who/what: participant ids, milestone ids, message excerpt ≤200 chars) |
| undo_data_json | Text | nullable | 2 | Inverse-operation data for undoable actions (see below) |
| undone_at | DateTime | nullable | 2 | Set when undone; undoable within 30 s of created_at |
| created_at | DateTime | not null, **indexed** | 1 | |

Indexes: ix(workshop_id, created_at).

**Undo (Phase 2):** undoable actions = `broadcast.send` (undo_data: previous active broadcast id or null), `workshop.pause`/`workshop.resume` (previous paused state), `milestone.advance_all`/`milestone.advance_selected` (list of created milestone_completion ids → deleted on undo). Undo applies the inverse in one transaction, sets `undone_at`, logs `undo.apply`, bumps `state_version`. Window: 30 seconds, enforced server-side.

Phase 1 writes audit rows for `workshop.create`, `help.answer`, `help.resolve` (the actions that exist); the audit-trail UI arrives in Phase 2.

---

## agenda_template + agenda_template_milestone (Phase 3)

Templates persist forever, independent of workshops. Instantiation **snapshots** milestones into the workshop — later template edits never mutate past or running sessions.

**agenda_template:** id (PK) · name String(120) not null · description_md Text default `''` · created_at · updated_at.

**agenda_template_milestone:** id (PK) · template_id (FK agenda_template.id CASCADE, not null) · position Integer not null · title String(200) not null · content_md Text not null default `''` · minutes Integer nullable. Index: ix(template_id, position).

"Save current workshop as template" copies the workshop's milestones into a new template.

---

## join_form_template (Phase 3)

**join_form_template:** id (PK) · name String(120) not null · fields_json Text not null default `'[]'` · created_at · updated_at.

Fields stay JSON (low query need; schema in JSON shapes below). Creating a workshop from a form template snapshots `fields_json` into `workshop.join_form_json`. Phase 1–2 join collects **name only** (`join_form_json = '[]'`).

---

## ai_usage (Phase 4)

One row per OpenRouter call. Per-workshop spend = `SUM(cost_usd)`.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | Integer | PK | |
| workshop_id | Integer | FK workshop.id CASCADE, not null | |
| help_request_id | Integer | FK help_request.id (SET NULL), nullable | |
| purpose | String(16) | not null | `triage_answer` (single combined call; see agent.md) |
| model | String(120) | not null | |
| prompt_tokens | Integer | not null, default 0 | |
| completion_tokens | Integer | not null, default 0 | |
| cost_usd | Numeric(10,6) | not null, default 0 | From OpenRouter `usage.cost` (`usage: {include: true}`); 0 if unavailable, tokens still recorded |
| latency_ms | Integer | not null, default 0 | |
| created_at | DateTime | not null | |

Indexes: ix(workshop_id, created_at).

---

## help_corpus (Phase 4 — SQLite FTS5 virtual table locally; PostgreSQL tsvector table in production)

The cross-workshop learning corpus for similarity retrieval (see agent.md). **Not** a SQLAlchemy model — created by an Alembic migration guarded by `dialect == "sqlite"`; maintained by application code (no triggers), rebuildable at any time from `help_request` + `help_answer` (it is derived data, so the resilience rule holds).

```sql
CREATE VIRTUAL TABLE help_corpus USING fts5(
  message,              -- participant's help text
  resolution,           -- the final human-visible answer (facilitator-sent, or AI answer the participant resolved)
  milestone_title,      -- indexed: milestone titles carry strong topical signal
  help_request_id UNINDEXED,
  workshop_id UNINDEXED
);
```

A row is inserted when a request reaches `resolved`, or `answered` by a facilitator (facilitator answers are trusted resolutions). PostgreSQL deployments: the equivalent is a `tsvector` GIN index on the same derived table — documented in agent.md, built only if/when a PostgreSQL deployment needs Phase 4.

---

## JSON shapes (stored in Text columns)

**workshop.join_form_json / join_form_template.fields_json** — array of:
```json
{"key": "role", "type": "text|dropdown", "label": "Your role", "required": false, "options": ["Student", "Engineer"]}
```
(`options` only for `dropdown`; `key` is `^[a-z][a-z0-9_]{0,39}$`.)

**participant.answers_json** — `{"role": "Engineer"}` (keys from the workshop's join form).

**help_answer.ai_context_json** — exactly what the AI saw (see agent.md §Context):
```json
{
  "progress": {"completed_count": 3, "total": 8, "completed_titles": ["…"]},
  "milestone": {"id": 12, "title": "Configure the API key", "content_excerpt": "first 2000 chars…"},
  "similar": [{"help_request_id": 41, "workshop_id": 2, "message_excerpt": "…", "resolution_excerpt": "…", "rank": 1}]
}
```

**facilitator_action.detail_json** — action-specific, human-renderable, e.g. `{"help_request_id": 7, "participant_name": "Priya", "excerpt": "Answered: check your .env…"}`.

**facilitator_action.undo_data_json** — inverse-op data, e.g. `{"completion_ids": [911, 912, 913]}`.

---

## Version-bump rules (the contract every write follows)

Bump `workshop.state_version` (same transaction) on: participant join, completion create/delete, help request create/answer/resolve/escalate, broadcast send/clear, pause/resume, advance, reorder, milestone edit, AI answer/draft, undo, status transition, ai toggle. Additionally bump `content_version` on: milestone create/edit/delete/reorder (and workshop name/description edit). Nothing else writes these counters.

## Indexing strategy for 300-participant polling

- Poll hot path: single point-read of `workshop` by unique token (admin_token/join_slug) or `participant` by unique token → covered by the unique indexes.
- Snapshot build (per changed poll; not memoized since Phase 7 — see architecture.md REVISIT-IF note): `milestone_completion` GROUP BY milestone_id filtered via ix(milestone_id) join on workshop's milestones; leaderboard from ix(workshop_id) participants + their completion counts; help queue via ix(workshop_id, status, created_at).
- "Me" section per poll: unique(token) point-read + ix(participant_id) on completions + ix(participant_id) on help_requests — 2–3 sub-ms indexed queries.
- No composite index tuning beyond the above is warranted at ≤1000 rows/table/session scale; the unique constraints double as the lookup indexes.

---

# Trainer Network & Opportunity Board (Phases 10–13)

Capabilities C8–C19 ([capabilities.md](capabilities.md)). Unlike the core v0.2 schema (created up front by `0001`), these tables are **added phase by phase** — each phase has exactly one migration, owned by exactly one slice (see [roadmap.md](roadmap.md)): `0005` (Phase 10), `0006` (Phase 11), `0007` (Phase 12), `0008` (Phase 13). Each `down_revision` is the previous one; every migration uses `batch_alter_table` for ALTERs and has a working `downgrade()`. Scale target: hundreds of trainers, tens of listings, ~500 signups/day bursts — every list endpoint is paginated, no table needs more indexing than listed.

## Phase 10 — migration `0005_opportunity_board` (`down_revision = "0004"`)

### topic — the curated, admin-maintained taxonomy

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | Integer | PK | |
| slug | String(48) | not null, **unique** | Lower-case `^[a-z0-9]+(-[a-z0-9]+)*$`; **immutable** after creation (used in public filter URLs) |
| name | String(80) | not null, **unique** | Display name; uniqueness is also enforced case-insensitively by the service |
| category | String(48) | not null | Grouping label for filter UIs |
| position | Integer | not null | Display order (asc); new topics get `max(position)+1` |
| active | Boolean | not null, default true, server_default true | Inactive topics are hidden from public filters and from pickers for new attachments; listings already carrying one keep displaying it |
| created_at / updated_at | DateTime | not null | |

**Seed (data migration inside `0005`, via `op.bulk_insert` with explicit `created_at`/`updated_at`/`active=True`, positions 0–39 in this order):**

| Category | Topics (`slug` — name) |
|---|---|
| Languages | `python` Python · `javascript` JavaScript · `typescript` TypeScript · `java` Java · `go` Go · `rust` Rust · `dotnet` C# / .NET · `kotlin` Kotlin |
| Web & Mobile | `react` React · `nextjs` Next.js · `nodejs` Node.js · `angular` Angular · `vuejs` Vue.js · `flutter` Flutter · `android` Android · `ios-swift` iOS / Swift |
| AI & Data | `machine-learning` Machine Learning · `deep-learning` Deep Learning · `generative-ai` Generative AI & LLMs · `agentic-ai` Agentic AI (LangChain / LangGraph) · `prompt-engineering` Prompt Engineering · `data-engineering` Data Engineering · `sql-analytics` SQL & Data Analysis · `mlops` MLOps |
| Cloud & DevOps | `aws` AWS · `gcp` Google Cloud · `azure` Azure · `docker` Docker · `kubernetes` Kubernetes · `ci-cd` CI/CD · `terraform` Terraform · `linux` Linux |
| Engineering Practice | `system-design` System Design · `apis-microservices` APIs & Microservices · `testing-qa` Testing & QA · `git-github` Git & GitHub · `cybersecurity` Cybersecurity · `agile-scrum` Agile & Scrum · `product-management` Product Management · `ux-design` UI / UX Design |

Exactly 40 rows, 5 categories, 8 each. `downgrade()` drops the table (seed included).

### opportunity — one admin-curated listing

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | Integer | PK | Public URLs use it (`/opportunities/{id}`); ids are not secrets — drafts are protected by returning 404 publicly |
| title | String(160) | not null | 3–160 |
| type | String(24) | not null | `workshop` (workshop / training gig) · `engagement` (bootcamp, mentoring, curriculum design) · `role` (job / contract role) · `cofacilitation` (Workshop0 co-facilitator / TA) |
| summary | String(280) | not null | Card blurb, plain text |
| description_md | Text | not null, default `''` | ≤20000; markdown, raw HTML disabled when rendered |
| location_mode | String(16) | not null, default `'remote'` | `remote` \| `onsite` \| `hybrid` |
| city | String(80) | nullable | Required when `onsite`/`hybrid`; forced `null` when `remote` |
| starts_on / ends_on | Date | nullable | Engagement dates; `ends_on ≥ starts_on` when both set |
| duration_text | String(80) | nullable | Free text, e.g. "2 days", "6 weeks · 4 h/week" |
| compensation_text | String(120) | nullable | **Public** free text, e.g. "Paid — day rate", "Pro bono" |
| deadline | DateTime(tz) | not null | Apply-by instant (UTC). Drives auto-expiry |
| partner_display_name | String(160) | nullable | **Public**; null → UI shows "smallTech partner network" |
| partner_internal_name | String(160) | nullable | **Admin-only. Never serialized by any public endpoint** |
| internal_notes | Text | nullable | **Admin-only**, ≤5000 (contacts, terms) |
| status | String(16) | not null, default `'draft'` | Stored status: `draft` \| `open` \| `closed` |
| published_at | DateTime(tz) | nullable | Set the first time the stored status becomes `open`; never cleared |
| closed_at | DateTime(tz) | nullable | Set when stored status becomes `closed`; cleared on reopen |
| created_at / updated_at | DateTime(tz) | not null | |

Indexes: ix(status, deadline), ix(published_at).

**Effective status (computed on read, never stored — no scheduler):** `draft` → `draft`; `closed` → `closed`; `open` and `deadline > now` → `open`; `open` and `deadline ≤ now` → **`expired`**. One function, `services/opportunities.py::effective_status(opportunity, now)`, is the only implementation; every list filter on effective status is the equivalent SQL predicate (`status='open' AND deadline > :now`, etc.). Extending an expired listing's deadline into the future makes it `open` again with no other action.

**Publish rule:** a write whose result is stored `open` **and** which sets `status: "open"` or changes `deadline` must leave `deadline > now`; otherwise `validation_error` (`"deadline: set a future deadline to publish"`). Editing other fields of an already-expired listing is allowed.

### opportunity_topic

| Column | Type | Constraints |
|---|---|---|
| opportunity_id | Integer | FK opportunity.id CASCADE, PK part |
| topic_id | Integer | FK topic.id (RESTRICT), PK part |

Index: ix(topic_id). 1–8 topics per listing (service-enforced).

### facilitator_action — additions (same migration)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| subject_type | String(32) | nullable | `opportunity` \| `topic` (Phase 10); `trainer` \| `invite` \| `user` (Phase 11); `application` (Phase 12). Null for every pre-existing workshop-scoped row |
| subject_id | Integer | nullable | Id of the subject row (no FK — the audit row outlives the subject, e.g. after account deletion) |

Index: ix(subject_type, subject_id, created_at). `actor` gains the value **`admin`** (Phase 10, admin-console actions; `workshop_id` is null) and **`user`** (Phase 11, a signed-in network user acting on their own account). New `action` codes: `opportunity.create`, `opportunity.update`, `opportunity.publish` (→ open from draft/closed), `opportunity.unpublish` (→ draft), `opportunity.close` (→ closed), `topic.create`, `topic.update`. `detail_json` for these: `{"title": "…", "changed_fields": ["deadline", "summary"], "from_status": "draft", "to_status": "open", "by": "admin-key"}` (`by` becomes the admin user's email from Phase 11). `services/audit.py::record_action` gains optional keyword args `subject_type`, `subject_id` (existing callers unchanged).

### Test-harness consequence (normative)

`tests/conftest.py` truncates every app table before each test. Because `topic` is migration-seeded reference data, the session fixture captures the `topic` rows right after `alembic upgrade head`, and the per-test fixture re-inserts them (explicit ids) after the TRUNCATE and resets the `topic` id sequence to `max(id)`. Likewise `scripts/sqlite_to_postgres.py` treats `topic` as a **reference table**: it is excluded from the "target already has data" check and is always truncated and re-copied from the source (same alembic revision ⇒ same seed plus the admin's edits).

## Phase 11 — migration `0006_trainer_network` (`down_revision = "0005"`)

### app_user — a network account (OIDC-shaped; owned by `src/workshop0/auth/`)

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | Integer | PK | |
| email | String(254) | not null, **unique** | Lower-cased; from the verified `email` claim |
| email_verified | Boolean | not null | Sign-in is refused when the IdP says false |
| display_name | String(120) | not null | From `name` claim (fallback: email local part) |
| avatar_url | String(500) | nullable | `picture` claim |
| oidc_issuer | String(200) | nullable | e.g. `https://accounts.google.com`; null for an invite-created placeholder not yet signed in |
| oidc_subject | String(255) | nullable | `sub` claim |
| created_at / last_login_at | DateTime | not null / nullable | |

Unique(oidc_issuer, oidc_subject). **No role column** — admin-ness is derived on every request: `email_verified and email ∈ WORKSHOP0_ADMIN_EMAILS` (removing an email from the setting revokes admin immediately).

### auth_session

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | Integer | PK | |
| token_hash | String(64) | not null, **unique** | SHA-256 hex of the cookie value (`token_urlsafe(32)`); the raw token is never stored |
| user_id | Integer | FK app_user.id CASCADE, not null, indexed | |
| created_at / expires_at | DateTime | not null | 30-day lifetime |
| last_seen_at | DateTime | not null | Conditional-UPDATE touch, ≤1 effective write / 5 min |
| revoked_at | DateTime | nullable | Sign-out |
| user_agent | String(300) | nullable | |

### rate_limit_hit — stateless fixed-window limiter (instances share nothing but the DB)

bucket String(120) + window_start DateTime → composite PK; count Integer not null. Incremented with a dialect `INSERT … ON CONFLICT (bucket, window_start) DO UPDATE SET count = count + 1 RETURNING count`. Rows older than 24 h are deleted opportunistically (1 in 100 hits).

### trainer_profile — 1:1 with app_user; live the moment it is saved

| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| user_id | FK app_user.id CASCADE, **unique** | |
| headline | String(160) not null | e.g. "GenAI trainer · ex-Flipkart" |
| bio_md | Text not null default `''` | ≤4000 |
| city | String(80) null · remote_ok Boolean default true | |
| linkedin_url / github_url / website_url | String(300) null | `https://` only; LinkedIn must be a `linkedin.com` host, GitHub a `github.com` host |
| past_work_json | Text default `'[]'` | ≤30 items `{"title": "…", "kind": "workshop\|talk\|course\|other", "org": "…"\|null, "year": 2025\|null}` |
| rate_min / rate_max | Integer null | **Admin-only** (never in any non-admin payload except the owner's own profile); `rate_min ≤ rate_max` |
| rate_currency | String(3) null | `INR` \| `USD` |
| rate_unit | String(8) null | `hour` \| `day` |
| pro_bono | Boolean default false | Open to unpaid community work |
| availability_json | Text default `'{}'` | Weekly pattern `{"mon": ["morning","afternoon","evening"], …}` (keys `mon`…`sun`, values ⊆ the three day-parts) |
| available_from | Date null | |
| blackout_json | Text default `'[]'` | ≤20 ranges `{"start": "2026-12-20", "end": "2027-01-02"}` |
| visibility | String(16) default `'private'` | `private` \| `public` — activated in Phase 13 (C18) |
| verified | Boolean default false · verified_at DateTime null · verified_by String(254) null | Admin "Verified" badge; invite-created trainers start verified |
| consent_at | DateTime **not null** · consent_version String(16) not null | Consent to share the profile with partners for matching; current version `2026-11` |
| autofilled_fields_json | Text default `'[]'` | Field keys pre-filled from the CV and not yet reviewed (drives "From your CV — please check"); cleared on the first save of the review screen |
| created_at / updated_at | DateTime | |

### trainer_topic

profile_id FK trainer_profile.id CASCADE + topic_id FK topic.id → composite PK; `level` String(16) not null ∈ `intermediate` \| `advanced` \| `expert`. ≤15 topics per profile.

### cv_document — the trainer's current CV (exactly one per user; a new upload replaces it)

| Column | Type | Notes |
|---|---|---|
| id | Integer PK | |
| user_id | FK app_user.id CASCADE, **unique** | |
| source | String(16) | `pdf` \| `docx` \| `text` (pasted LinkedIn/CV text) |
| original_filename | String(200) null | |
| storage_key | String(300) null | Blob key `cv/{user_id}/{uuid}.{pdf\|docx}`; null for pasted text |
| content_type / size_bytes | String(100) null / Integer | ≤5 MB |
| sha256 | String(64) | |
| text_extract | Text | Extracted text, truncated to 60000 chars |
| draft_status | String(16) | `pending` \| `ready` \| `failed` \| `skipped` (no key) |
| draft_json | Text null | The drafter's validated output ([agent.md](agent.md) §Profile drafter) |
| created_at | DateTime | |

### network_invite

id PK · token String(43) unique (`token_urlsafe(32)`) · email String(254) not null (lower-cased) · name String(120) null · created_by String(254) · created_at · expires_at (14 days) · accepted_at null · accepted_user_id FK app_user.id SET NULL null. Accepting = signing in with the **same** email; it creates/marks the profile `verified=true`.

### trainer_tag / admin_note (admin-private)

`trainer_tag`: profile_id FK CASCADE + tag String(40) (lower-cased, `^[a-z0-9][a-z0-9 -]{0,39}$`) → composite PK; ≤20 per trainer. `admin_note`: id PK · profile_id FK CASCADE · body Text (1–4000, plain text) · author String(254) · created_at.

### ai_usage — changes (same migration)

`workshop_id` becomes **nullable**; add `cv_document_id` FK cv_document.id SET NULL null and `opportunity_id` FK opportunity.id SET NULL null (Phase 12 shortlist). New `purpose` values: `profile_draft` (Phase 11), `shortlist_rank` (Phase 12). Network spend = `SUM(cost_usd) WHERE workshop_id IS NULL`. For these network rows the provider is Anthropic (agent.md §Network AI): `model` holds the Anthropic model id (e.g. `claude-sonnet-5-5`), `prompt_tokens`/`completion_tokens` are the response's `usage.input_tokens`/`output_tokens`, and `cost_usd` = those tokens × the `ai/pricing.py` table (0 for an unpriced model) — the OpenRouter `usage.cost` rule above applies to help-desk rows only. No schema change follows from the provider choice.

## Phase 12 — migration `0007_applications_matching_email` (`down_revision = "0006"`)

- **opportunity** gains admin-only matching fields: `budget_min`/`budget_max` Integer null, `budget_currency` String(3) null (`INR`\|`USD`), `budget_unit` String(8) null (`hour`\|`day`), `min_level` String(16) null (`intermediate`\|`advanced`\|`expert`). Never in public payloads.
- **application**: id PK · opportunity_id FK CASCADE · profile_id FK trainer_profile CASCADE · status String(16) ∈ `applied` \| `shortlisted` \| `selected` \| `not_selected` \| `withdrawn` · note Text null (≤1000, plain text) · source String(16) `self` \| `invited` · status_changed_at · created_at · updated_at. **Unique(opportunity_id, profile_id)**; ix(opportunity_id, status), ix(profile_id).
- **opportunity_invite** (admin "invite to apply"): id PK · opportunity_id FK CASCADE · profile_id FK CASCADE · created_by · created_at · Unique(opportunity_id, profile_id).
- **match_suggestion** (one row per ranked trainer per shortlist run): id PK · opportunity_id FK CASCADE · profile_id FK CASCADE · run_id String(22) · rank Integer · rule_score Numeric(6,3) · reason String(300) null (null when ranked by rules only) · ranked_by String(8) `ai` \| `rules` · created_at. ix(opportunity_id, run_id, rank). Only the latest run is shown.
- **email_outbox**: id PK · to_email String(254) · template String(48) · context_json Text · subject String(200) null (rendered at send) · status String(16) ∈ `queued` \| `sent` \| `failed` \| `recorded` · attempts Integer default 0 · last_error String(500) null · dedupe_key String(120) **unique** null · created_at · sent_at null. ix(status, created_at). `recorded` = SMTP not configured; the message is kept for the admin outbox view and never retried.

## Phase 13 — migration `0008_alerts_directory_tiein` (`down_revision = "0007"`)

- **saved_search**: id PK · user_id FK app_user CASCADE · name String(80) · criteria_json Text `{"types": [...], "topic_slugs": [...], "location_modes": [...]}` · alerts_enabled Boolean default true · created_at · updated_at. ≤10 per user.
- **email_pref**: user_id FK app_user CASCADE PK · alerts Boolean default true · digest Boolean default true · updated_at.
- **workshop_facilitator**: workshop_id FK workshop CASCADE + profile_id FK trainer_profile CASCADE → composite PK · role String(8) `lead` \| `co` \| `ta` · linked_by String(254) · created_at.
- **opportunity** gains `workshop_id` FK workshop.id SET NULL null (a `cofacilitation` listing names the Workshop0 workshop it staffs).

