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
| purpose | String(16) → **String(32)** from `0007` | not null | `triage_answer` (single combined call; see agent.md); network values in §Phase 11 / §Phase 11b |
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

Capabilities C8–C19 ([capabilities.md](capabilities.md)). Unlike the core v0.2 schema (created up front by `0001`), these tables are **added phase by phase** — each phase (or sub-step) has exactly one migration, owned by exactly one slice (see [roadmap.md](roadmap.md)): `0005` (Phase 10), `0006` (Phase 11), `0007` (Phase 11b), `0008` (Phase 11c), `0009` (invite revoke, separate PR), `0010` (Phase 11e), `0011` (Phase 12), `0012` (Phase 13). Each `down_revision` is the previous one; every migration uses `batch_alter_table` for ALTERs and has a working `downgrade()`. Scale target: hundreds of trainers, tens of listings, ~500 signups/day bursts — every list endpoint is paginated, no table needs more indexing than listed.

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
| id | Integer | PK | Ids are not secrets — drafts are protected by returning 404 publicly. Until Phase 11e public URLs used it; from 11e they use `slug` and `/opportunities/{id}` is a legacy 301 (§Phase 11e) |
| title | String(160) | not null | 3–160 |
| type | String(24) | not null | `workshop` (workshop / training gig) · `engagement` (bootcamp, mentoring, curriculum design) · `role` (job / contract role) · `cofacilitation` (Workshop0 co-facilitator / TA) |
| summary | String(280) | not null | Card blurb, plain text |
| description_md | Text | not null, default `''` | ≤20000; markdown, raw HTML disabled when rendered |
| location_mode | String(16) | not null, default `'remote'` | `remote` \| `onsite` \| `hybrid` |
| city | String(80) | nullable | Required when `onsite`/`hybrid`; forced `null` when `remote`. From Phase 11c a legacy **mirror** of the first entry of `locations_json` (§Phase 11c) |
| starts_on / ends_on | Date | nullable | Engagement dates; `ends_on ≥ starts_on` when both set |
| duration_text | String(80) | nullable | Free text, e.g. "2 days", "6 weeks · 4 h/week" |
| compensation_text | String(120) | nullable | **Public** free text, e.g. "Paid — day rate", "Pro bono". From Phase 11b this is the optional **note** beside the structured compensation fields (§Phase 11b) |
| deadline | DateTime(tz) | not null | Apply-by instant (UTC). Drives auto-expiry |
| partner_display_name | String(160) | nullable | **Public**; null → UI shows "smallTech partner network" |
| partner_internal_name | String(160) | nullable | **Admin-only. Never serialized by any public endpoint.** From Phase 11b it is a legacy **mirror** of `partner.internal_name` (§Phase 11b) |
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
| subject_type | String(32) | nullable | `opportunity` \| `topic` (Phase 10); `trainer` \| `invite` \| `user` (Phase 11); `partner` (Phase 11b); `application` (Phase 12). Null for every pre-existing workshop-scoped row |
| subject_id | Integer | nullable | Id of the subject row (no FK — the audit row outlives the subject, e.g. after account deletion) |

Index: ix(subject_type, subject_id, created_at). `actor` gains the value **`admin`** (Phase 10, admin-console actions; `workshop_id` is null) and **`user`** (Phase 11, a signed-in network user acting on their own account). New `action` codes: `opportunity.create`, `opportunity.update`, `opportunity.publish` (→ open from draft/closed), `opportunity.unpublish` (→ draft), `opportunity.close` (→ closed), `topic.create`, `topic.update`. `detail_json` for these: `{"title": "…", "changed_fields": ["deadline", "summary"], "from_status": "draft", "to_status": "open", "by": "admin-key"}`. From Phase 11, `by` is `AdminActor.by` (`"admin-key"` or the admin user's email). Phase 11b wires this into the opportunity, topic and partner writes. Phase 11b adds the actions `partner.create` and `partner.update`. `services/audit.py::record_action` gains optional keyword args `subject_type`, `subject_id` (existing callers unchanged).

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
| rate_min / rate_max | Integer null | **Admin-only** (only in admin payloads and the owner's own `/api/me/*` payloads — api.md §Phase 11 → Privacy); `rate_min ≤ rate_max` |
| rate_currency | String(3) null | `INR` \| `USD` |
| rate_unit | String(8) null | `hour` \| `day` \| `course` \| `month` — the same four-value enum as `opportunity.compensation_unit` (§Phase 11b). Enforced by `services/profiles.py` validation, not by a DB constraint, so the 0006 column needs no migration |
| pro_bono | Boolean default false | Open to unpaid community work |
| availability_json | Text default `'{}'` | Weekly pattern `{"mon": ["morning","afternoon","evening"], …}` (keys `mon`…`sun`, values ⊆ the three day-parts) |
| available_from | Date null | |
| blackout_json | Text default `'[]'` | ≤20 ranges `{"start": "2026-12-20", "end": "2027-01-02"}` |
| visibility | String(16) default `'private'` | `private` \| `public`. Set by the owner (Phase 13, C18). A profile is **listed** publicly only when `public` **and** completeness ≥ 60 % **and** `public_slug` is set (§Phase 13) |
| public_slug | String(80) null, unique | *(Phase 13, `0012`)* Public URL key `/trainers/{slug}`; server-generated the first time `visibility` becomes `public`, frozen afterwards; never accepted from a request |
| verified | Boolean default false · verified_at DateTime null · verified_by String(254) null | Admin "Verified" badge; invite-created trainers start verified |
| consent_at | DateTime **not null** · consent_version String(16) not null | Consent to share the profile with partners for matching; current version `2026-11`. The `consent_at` checks in the email gate are defensive only (the column is NOT NULL) |
| autofilled_fields_json | Text default `'[]'` | Field keys pre-filled from the CV and not yet reviewed (drives "From your CV — please check"). Set at create (`POST /api/me/profile`) to the drafted fields the person left unchanged on the review screen; cleared to `[]` by the first `PATCH /api/me/profile` |
| created_at / updated_at | DateTime | |

### trainer_topic

profile_id FK trainer_profile.id CASCADE + topic_id FK topic.id → composite PK; `level` String(16) not null ∈ `intermediate` \| `advanced` \| `expert`. ≤15 topics per profile.

### cv_document — the trainer's current CV (exactly one per user; a new upload replaces it **in place**)

A replacement upload or paste updates the existing row — **same `id`** — overwriting source, filename, blob key, size, hash, text, `draft_status="pending"`, `draft_json=null` and `created_at`; the old blob is deleted. Because `ai_usage.cv_document_id` points at this stable id, a trainer's drafting spend (`ai_cost_usd`, api.md §Phase 11 admin pool) accumulates across replacements.

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

id PK · token String(43) unique (`token_urlsafe(32)`) · email String(254) not null (lower-cased) · name String(120) null · created_by String(254) · created_at · expires_at (14 days) · accepted_at null · accepted_user_id FK app_user.id SET NULL null. Accepting = signing in with the **same** email (sets `accepted_at`/`accepted_user_id`); an existing profile is marked `verified=true` at the callback, a profile created later starts verified. Exact rules: api.md §Phase 11 → Invite acceptance.

**Phase 11d (migration `0008_invite_revoke`, `down_revision = "0007"`):** adds `revoked_at` DateTime null · `revoked_by` String(254) null (the admin's email, or `"admin key"`, same attribution as `created_by`). Both nullable, no backfill; downgrade drops them. No other column changes.

**Status** (derived, never stored; one function `services/invites.py::invite_status`), first match wins:
1. `revoked` — `revoked_at` set (an accepted invite can never be revoked, so 1 and 2 never overlap);
2. `accepted` — `accepted_at` set;
3. `superseded` — not accepted, and **another** invite with the same `email` is accepted (the person is already in via a sibling link; this one is no longer actionable);
4. `expired` — `expires_at ≤ now`;
5. `pending` — otherwise. Only `pending` is actionable (copyable link, Revoke button).

**At most one pending invite per email:** creating an invite for an email that already has a `pending` one re-uses that row (rules: api.md §Phase 11d). This is enforced in the service, not by a DB constraint (status is derived).

### trainer_tag / admin_note (admin-private)

`trainer_tag`: profile_id FK CASCADE + tag String(40) (lower-cased, `^[a-z0-9][a-z0-9 -]{0,39}$`) → composite PK; ≤20 per trainer. `admin_note`: id PK · profile_id FK CASCADE · body Text (1–4000, plain text) · author String(254) · created_at.

### ai_usage — changes (same migration)

`workshop_id` becomes **nullable**; add `cv_document_id` FK cv_document.id SET NULL null and `opportunity_id` FK opportunity.id SET NULL null (Phase 12 shortlist). New `purpose` values: `profile_draft` (Phase 11), `opportunity_draft` (Phase 11b; this needs the `0007` widening), `shortlist_rank` (Phase 12). Network spend = `SUM(cost_usd) WHERE workshop_id IS NULL`. For these network rows the provider is Anthropic (agent.md §Network AI): `model` holds the Anthropic model id (e.g. `claude-sonnet-5-5`), `prompt_tokens`/`completion_tokens` are the response's `usage.input_tokens`/`output_tokens`, and `cost_usd` = those tokens × the `ai/pricing.py` table (0 for an unpriced model) — the OpenRouter `usage.cost` rule above applies to help-desk rows only. No schema change follows from the provider choice.

## Phase 11b — migration `0007_partners_compensation` (`down_revision = "0006"`)

This migration is owned by F1 ([roadmap.md](roadmap.md) §Phase 11b). It is purely additive, apart from widening one column, so the previous revision keeps working during the one-deploy overlap (architecture.md §Production topology → Migrations).

### partner — the admin-managed partner list

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | Integer | PK | |
| internal_name | String(160) | not null | **Admin-only.** Trimmed, internal whitespace collapsed to single spaces, 2–160 chars. The real organisation name |
| name_key | String(200) | not null, **unique** | `casefold()` of the collapsed `internal_name` (`services/partners.py::normalize_name`). The DB enforces case- and whitespace-insensitive uniqueness, so it is race-safe. Never serialized anywhere |
| display_name | String(160) | nullable | **Default** public display name (e.g. "A Bengaluru fintech"). The editor copies it into a listing's `partner_display_name` when the partner is chosen and that field is empty. **No public code reads this column** |
| notes | Text | nullable | **Admin-only**, ≤5000 (contacts, terms). Never in any opportunity payload |
| active | Boolean | not null, default true, server_default true | Inactive partners are hidden from the editor's picker for new attachments. Listings that already have one keep it, as with topics |
| created_at / updated_at | DateTime(tz) | not null | |

There is no delete. Deactivating is the end of a partner's life, because listings and audit rows reference it.

### opportunity — additions

| Column | Type | Constraints | Notes |
|---|---|---|---|
| partner_id | Integer | FK partner.id (**RESTRICT**), nullable; index `ix_opportunity_partner_id` | The listing's partner. **Admin-only. Never in public payloads** |
| compensation_min | Integer | nullable | **Public.** 0–100 000 000, whole currency units |
| compensation_max | Integer | nullable | **Public.** Same range; `compensation_min ≤ compensation_max` when both are set; equal is allowed (a single value) |
| compensation_currency | String(3) | nullable | **Public.** `INR` \| `USD`, the same set as `trainer_profile.rate_currency`. Required when an amount is set; must be null when neither amount is set |
| compensation_unit | String(8) | nullable | **Public.** `hour` \| `day` \| `course` \| `month`, the same enum as `trainer_profile.rate_unit`. Required when an amount is set; must be null when neither amount is set |

`compensation_text` stays as the optional free-text **note** (≤120, public), e.g. "plus travel", "Pro bono" or a legacy "Paid — day rate". The single display rule that combines the fields lives in capabilities.md §C10. Validation lives in api.md §Phase 11b.

**`partner_internal_name` becomes a mirror.** New code never reads it. Every write that sets or changes a listing's partner also writes `partner_internal_name = partner.internal_name` (`null` when the partner is cleared), and a partner rename rewrites the mirror on all of that partner's listings. As a result, a rollback to the Phase-10/11 revision still shows the right internal names. Dropping the column is left to a future cleanup migration and is not scheduled.

### ai_usage — change

`purpose` is widened from `String(16)` to **`String(32)`**, because `opportunity_draft` is 17 characters. The new purpose value is `opportunity_draft` (Phase 11b). Each row has `opportunity_id` set when the draft was made from an existing listing and null for a new one, and `cv_document_id` null. Network-spend sums are unchanged (`workshop_id IS NULL`).

### Data migration inside `0007` (normative; Python inside the migration, portable to SQLite and PostgreSQL; the migration does not import app code)

1. Read every `opportunity` row's `(id, partner_internal_name, partner_display_name, updated_at)`.
2. Skip rows whose `partner_internal_name` is null or blank after trimming. They keep `partner_id = null`.
3. `collapsed = " ".join(name.split())`, then `key = collapsed.casefold()`. Group the rows by `key`.
4. Insert one `partner` per group, in `key` order:
   - `internal_name` = the `collapsed` value of the group's row with the greatest `(updated_at, id)`;
   - `display_name` = the most frequent collapsed, non-blank `partner_display_name` in the group (a tie goes to the value on the greatest `(updated_at, id)` row; null if none);
   - `notes` = null, `active` = true, `created_at` = `updated_at` = migration time.
5. Set `partner_id` on every row of the group. `partner_internal_name` is left as it was, because the mirror is refreshed by the next write.

**`downgrade()`:**
1. Set `partner_internal_name = (SELECT internal_name FROM partner WHERE partner.id = opportunity.partner_id)` where `partner_id` is not null.
2. For rows whose `compensation_text` is null but which have an amount, set `compensation_text` to the plain-ASCII fallback `"{currency} {min}-{max} / {unit}"`, truncated to 120. A missing min or max is omitted together with its dash.
3. Drop the index, FK and the five opportunity columns, then drop `partner`.
4. Run `DELETE FROM ai_usage WHERE length(purpose) > 16`, then narrow `purpose` back to `String(16)`.

All ALTERs use `batch_alter_table`.

> **Assumed:** existing free-text names are matched case- and whitespace-insensitively only, with no fuzzy merging ("Acme" and "Acme Pvt Ltd" stay two partners). Admins can rename one of them or deactivate it later.

## Phase 11c — migration `0008_multi_location` (`down_revision = "0007"`)

Owned by M1 ([roadmap.md](roadmap.md) §Phase 11c). Purely additive: the previous revision keeps working during the one-deploy overlap (architecture.md §Production topology → Migrations), because `city` stays and is kept current as a mirror.

### opportunity — addition

| Column | Type | Constraints | Notes |
|---|---|---|---|
| locations_json | Text | not null, default `'[]'`, server_default `'[]'` | **Public data, private column name.** A JSON array of `{"city": str, "country": str \| null}` objects, in the admin's order. The column name `locations_json` is never serialized; payloads expose the parsed list as `locations` (api.md §Phase 11c) |

**Invariants (enforced by `services/opportunities.py`, not by the DB):**
- 0–10 entries. `city` is trimmed with internal whitespace collapsed to single spaces, 1–80 chars. `country` is trimmed and collapsed the same way, ≤80 chars, and blank becomes `null`. Case is kept as entered.
- **No duplicates.** The dedupe key is `(city.casefold(), (country or "").casefold())`, so `"Pune"` and `" PUNE "` are one location, while `{"Pune", null}` and `{"Pune", "India"}` are two. The first occurrence wins, and order is otherwise preserved.
- `location_mode = 'remote'` → `[]`. `onsite` / `hybrid` → at least 1 entry.
- **`city` becomes a mirror.** Every write sets `city = locations[0].city`, or `null` when the list is empty. New code reads only `locations_json` (through the read rule below). The mirror keeps a rollback to revision `0007` showing the right first city.

**Read rule (one function, `services/locations.py::parse_stored(locations_json, city, location_mode) -> list[dict]`):** parse `locations_json`. If it is a non-empty list, return it. If it is `[]` (or unparseable), `city` is non-blank and the mode is not `remote`, return `[{"city": collapsed city, "country": null}]`. This covers a row written by the `0007` revision during the deploy overlap. Otherwise return `[]`.

There is no index, because no API filters on location (api.md §Phase 11c → Filters). JSON-in-`Text` matches the existing `*_json` columns (`past_work_json`, `availability_json`) and behaves the same on SQLite and PostgreSQL.

### Data migration inside `0008` (normative; plain Python in the migration, portable to SQLite and PostgreSQL, no app imports)

**`upgrade()`:**
1. `batch_alter_table("opportunity")`: add `locations_json` Text, not null, `server_default='[]'`.
2. For every row where `location_mode != 'remote'` and `city` is non-blank after trimming: set `locations_json = json.dumps([{"city": " ".join(city.split()), "country": None}], ensure_ascii=False)`.
3. Leave every other row at `'[]'`. That includes remote rows, which have `city = null` by the Phase-10 rule.

**`downgrade()`:**
1. For every row whose parsed `locations_json` is non-empty: set `city = locations[0]["city"][:80]`. Rows with an empty list keep their `city`, which is already the mirror.
2. `batch_alter_table("opportunity")`: drop `locations_json`.

The second and later cities are lost on downgrade. That is accepted and documented in the migration docstring.

> **Assumed (storage):** a JSON `Text` column on `opportunity` is used, not an `opportunity_location` child table. Locations are always read and written with their listing, the list is capped at 10, nothing filters on them, and a child table would add a join to every list query plus delete-and-reinsert writes for no benefit. If a location filter is ever needed, a child table (or a PostgreSQL JSONB index) is the upgrade path.
> **Assumed (remote):** a remote listing carries no cities, as in Phase 10, where `city` was forced null. A "remote, for candidates in X" constraint belongs in the description.
> **Assumed (dedupe key includes the country):** `{"Pune", null}` and `{"Pune", "India"}` are kept as two entries, so same-named cities in different countries are possible. The editor shows both chips, so the admin can see and remove one.
> **Assumed (numbering):** Phase 11c takes `0008`. The not-yet-built Phase 12 and 13 migrations are renumbered `0009` and `0010`, with no change to their content. *(Superseded: after invite revoke `0009` and Phase 11e `0010`, they are `0011` and `0012`.)*

## Phase 11e — migration `0010_opportunity_slugs` (`down_revision = "0009"`)

`0009` (invite revoke) lands from a separate PR first; 11e does not touch it. Head after 11e is `0010`.

### opportunity — addition

| Column | Type | Constraints | Notes |
|---|---|---|---|
| slug | String(80) | not null, **unique** (`uq_opportunity_slug`) | Public URL key, e.g. `genai-workshop-bengaluru-a3f9`. Generated by the server, never accepted from a request body |

### Slug rule (one implementation: `src/workshop0/services/slugs.py`; the migration carries a frozen copy, with no app imports)
1. **`slug_base(title, first_city)`:** join `title` and the first location's city (from `locations.parse_stored`; omitted when there are no cities, so remote listings use only the title) with a space. Then apply NFKD normalization, drop every non-ASCII code point (so `Zürich` → `zurich` and `São Paulo` → `sao-paulo`; scripts with no ASCII decomposition drop out), lower-case, turn each run of characters outside `[a-z0-9]` into one `-`, and trim `-` from both ends. Truncate to **60** characters, cutting back to the last `-` when the cut falls inside a word, and trim `-` again. An empty result becomes `opportunity`.
2. **`new_suffix()`:** 4 lower-case hex characters from a cryptographically secure source (`secrets.token_hex(2)`).
3. **slug** = `f"{base}-{suffix}"`. Every slug contains a `-` and at least one letter or `opportunity`, so it can never be all digits. This keeps it disjoint from legacy numeric ids, which match `^\d{1,12}$`.
4. **Uniqueness:** before inserting, check for an existing slug and draw a new suffix on a collision. After 5 collisions, use 6 hex characters (`token_hex(3)`). The unique constraint is the backstop: an `IntegrityError` on `slug` retries the write once with a new suffix.

### Lifecycle: frozen on first publish (no alias table)
- **Created** with a slug on POST, whatever the status.
- **While `published_at` is null** (the listing has never been public), a write that changes `title` or the first location's city recomputes the **base** and **keeps the suffix**. A draft's URL has never been shared, so nothing can break.
- **From the first publish on** (`published_at` set, and it is never cleared) the slug is **frozen forever**. Later title or city edits, unpublishing, closing and reopening never change it.
- Slug changes are not audited and are not in `changed_fields`, because they are derived and not an admin edit.

> **Assumed (freeze over alias table):** freezing on publish is the simpler robust option. Every public URL that was ever valid stays valid, with no `opportunity_slug_alias` table, no redirect chains and no rename UI. The cost is that a published listing whose title is later edited keeps its old wording in the URL. This is accepted: the suffix makes the slug unique and the canonical tag carries the current title. An alias table is the upgrade path if renaming ever matters.
> **Assumed (no admin slug editing):** admins cannot set or edit slugs in 11e.
> **Assumed (transliteration):** Unicode NFKD plus dropping non-ASCII, from the standard library, with no new dependency. Latin-script accents transliterate. Devanagari and other non-Latin titles fall back to the city, or to `opportunity`. That is acceptable for this board, whose listings are written in English.

### Data migration inside `0010` (normative; plain Python in the migration, portable to SQLite and PostgreSQL, no app imports)
1. `batch_alter_table("opportunity")`: add `slug` String(80) **nullable**.
2. For every row, ordered by `id`: first city = the first `city` in `locations_json` when that parses to a non-empty list, else the `city` column, else none. Then compute `slug_base` with the frozen copy of the rule, plus a random suffix that is unique among the slugs already assigned in this run (retry as in rule 4). `UPDATE` the row. Every existing row is treated as frozen, published or not, because the migration cannot know whether a link was shared.
3. `batch_alter_table("opportunity")`: make `slug` not null and create the unique constraint `uq_opportunity_slug`.

**Downgrade:** `batch_alter_table`, then drop the constraint and the column. Slugs are lost. On re-upgrade they get new suffixes, which is documented in the docstring.

## Phase 12 — migration `0011_applications_matching_email` (`down_revision = "0010"`)

- **opportunity** gains admin-only matching fields: `budget_min`/`budget_max` Integer null, `budget_currency` String(3) null (`INR`\|`USD`), `budget_unit` String(8) null (`hour`\|`day`\|`course`\|`month`, the same enum as `compensation_unit`/`rate_unit`), `min_level` String(16) null (`intermediate`\|`advanced`\|`expert`). Never in public payloads. When the budget is unset, matching uses the public `compensation_max`/`_currency`/`_unit` as the budget (agent.md §Shortlist ranker).
- **application**: id PK · opportunity_id FK CASCADE · profile_id FK trainer_profile CASCADE · status String(16) ∈ `applied` \| `shortlisted` \| `selected` \| `not_selected` \| `withdrawn` · note Text null (≤1000, plain text) · source String(16) `self` \| `invited` · status_changed_at · created_at · updated_at. **Unique(opportunity_id, profile_id)**; ix(opportunity_id, status), ix(profile_id).
- **opportunity_invite** (admin "invite to apply"): id PK · opportunity_id FK CASCADE · profile_id FK CASCADE · created_by · created_at · Unique(opportunity_id, profile_id).
- **match_suggestion** (one row per ranked trainer per shortlist run): id PK · opportunity_id FK CASCADE · profile_id FK CASCADE · run_id String(22) · rank Integer · rule_score Numeric(6,3) · reason String(300) null (null when ranked by rules only) · ranked_by String(8) `ai` \| `rules` · created_at. ix(opportunity_id, run_id, rank). Only the latest run is shown.
- **email_outbox**: id PK · to_email String(254) · template String(48) · context_json Text · subject String(200) null (rendered at send) · status String(16) ∈ `queued` \| `sent` \| `failed` \| `recorded` · attempts Integer default 0 · last_error String(500) null · dedupe_key String(120) **unique** null · created_at · sent_at null. ix(status, created_at). `recorded` = not sent (SMTP not configured, or per-recipient/global rate limit hit with `last_error="rate_limited"`); the message is kept for the admin outbox view and never retried automatically. `last_error` never contains credentials.

## Phase 13 — migration `0012_alerts_directory_tiein` (`down_revision = "0011"`)

Owned by S0 ([roadmap.md](roadmap.md) §Phase 13). **Purely additive** (new tables plus nullable columns), so the Phase-12 revision keeps working during the one-deploy overlap (architecture.md §Production topology → Migrations). All ALTERs use `batch_alter_table`; `downgrade()` drops the new columns, indexes and tables in reverse order. Written against head `0011` (Phase 12), the code state on 2026-11-10.

### saved_search

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | Integer | PK | |
| user_id | Integer | FK app_user.id **CASCADE**, not null; index `ix_saved_search_user_id` | Owner. Account deletion removes the searches |
| name | String(80) | not null | Trimmed, 1–80 chars, plain text |
| criteria_json | Text | not null | Normalised object `{"types": [...], "topic_slugs": [...], "location_modes": [...], "cities": [...]}`; every key always present, empty list = no constraint. `types` ⊆ the four listing types, `topic_slugs` ⊆ existing topic slugs (≤10), `location_modes` ⊆ `remote\|onsite\|hybrid`, `cities` ≤5 entries, each collapsed whitespace, 1–80 chars, de-duplicated case-insensitively. At least one list is non-empty. Matching rules: api.md §Phase 13 |
| alerts_enabled | Boolean | not null, default true, server_default true | Per-search alert switch (the digest ignores it) |
| created_at / updated_at | DateTime(tz) | not null | |

≤10 per user (enforced by `services/saved_searches.py`, not by the DB). A user needs a `trainer_profile` to create one (its `consent_at` is the consent for these emails).

### email_pref

`user_id` Integer PK, FK app_user.id **CASCADE** · `alerts` Boolean not null default true · `digest` Boolean not null default true · `updated_at` DateTime(tz). **A missing row means both true**; rows are created lazily by the first `PATCH /api/me/email-prefs` or unsubscribe. Applies only to the `network.alert` and `network.digest` templates; transactional mail (`network.invite`, `network.welcome`, `opportunity.invite`, `application.*`) is not controlled by it.

### workshop_facilitator

`workshop_id` FK workshop.id **CASCADE** + `profile_id` FK trainer_profile.id **CASCADE** → composite PK · `role` String(8) not null (`lead` \| `co` \| `ta`) · `linked_by` String(254) not null (admin email or `"admin-key"`, same attribution as `created_by` elsewhere) · `created_at` DateTime(tz). Index `ix_workshop_facilitator_profile_id` (the trainer's "My Workshop0 workshops" lookup). At most one `lead` per workshop, ≤10 rows per workshop (service-enforced). Deleting a trainer account removes their links; deleting a workshop removes its links. Linking never changes the workshop's `admin_token`.

### trainer_profile — addition

`public_slug` String(80) **nullable**, unique constraint `uq_trainer_profile_public_slug`. Rule (implemented by `services/directory.py::ensure_slug`, reusing `services/slugs.py`):
1. Generated the **first time** `visibility` is set to `public` (whether or not the profile is yet listed). Never generated at profile creation.
2. `base = slugs.slug_base(app_user.display_name, None)` with the fallback `trainer` instead of `opportunity` when the name has no ASCII letters or digits (so `Zoë Müller` → `zoe-muller`, a Devanagari-only name → `trainer`). `slug = f"{base}-{suffix}"`, suffix `secrets.token_hex(2)`, after 5 collisions `token_hex(3)`, with the same IntegrityError retry as listings. The slug never contains the email, the numeric id or any other field.
3. **Frozen forever** once set: toggling to private and back, renaming the Google display name, or editing the profile never changes it, so a shared link stays valid. Private or under-60 % profiles keep their slug but resolve to 404.
4. The numeric `trainer_profile.id` and `app_user.id` are never used in a public URL or public payload.

### opportunity — addition

`workshop_id` Integer FK workshop.id **SET NULL**, nullable; index `ix_opportunity_workshop_id`. **Admin-only** (admin payloads, never public payloads, never the SEO block, sitemap or emails). Allowed only on `type = 'cofacilitation'` listings (service validation, 422 otherwise); it names the Workshop0 workshop the listing staffs and is the default target of **Link as facilitator**.

### Outbox usage (no schema change)

`email_outbox` already has everything Phase 13 needs. New templates `network.alert` and `network.digest` (added to `email/render.py::TEMPLATES`). Dedupe keys: `alert:{opportunity_id}:{user_id}` and `digest:{user_id}:{YYYY-Www}` (≤ 120 chars). Contexts hold only display strings and URLs (listing title, partner **display** name, formatted compensation, joined cities, slug URL, search names, unsubscribe and manage URLs), never ids that map to admin-only data.

