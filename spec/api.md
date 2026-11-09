# API Contract — Workshop0 (v0.2)

This is the contract both generators build against **in parallel** — the backend implements it exactly; the frontend consumes it exactly. Nothing here is aspirational: field names, casing, and shapes are normative.

## Conventions (normative)

- All endpoints are under `/api/`. All bodies and responses are JSON (UTF-8). All field names are `snake_case`.
- **Timestamps:** ISO 8601 UTC with `Z`, seconds precision — `"2026-07-20T14:03:22Z"`.
- **IDs** are integers. **Tokens/slugs** are strings.
- **Success envelope:** HTTP 200 → `{"data": <payload>, "error": null}`.
- **Error envelope:** HTTP 4xx/5xx → `{"detail": {"code": "<machine_code>", "message": "<human sentence>"}}`. Pydantic validation failures are converted by an exception handler into this same shape (`code: "validation_error"`, message = first human-readable error) — the raw FastAPI 422 array shape never reaches clients.
- **Auth:** three schemes — `X-Admin-Key` header (admin surface), `admin_token` path segment (facilitator surface), `participant_token` path segment (participant surface). See architecture.md §Auth. **From Phase 11** a fourth: the `workshop0_session` cookie for the trainer network (`/api/me/*`, and admin users on `/api/admin/*` as an alternative to the key) — see architecture.md §Network identity.
- **Versioned polling:** poll endpoints take `?v=<int>` (last-seen `state_version`; default `-1` = always changed). Unchanged → `{"changed": false, "version": N, "content_version": M}`. The content endpoint uses `?cv=<int>` against `content_version` the same way. Every mutation response includes `"version"` (the new `state_version`) so clients re-poll immediately.
- **URL fields** (`join_url`, `facilitator_url`, `participant_url`) are absolute, built from `WORKSHOP0_BASE_URL` (or the request origin) + the pretty paths `/j/{slug}`, `/f/{admin_token}`, `/p/{participant_token}`.
- **Draft AI answers (`draft: true`) appear only in facilitator payloads — never in participant payloads.** `ai_context` appears only in facilitator payloads.

### Error code catalogue

| HTTP | `code` | When |
|---|---|---|
| 401 | `invalid_admin_key` | Missing/wrong `X-Admin-Key` |
| 404 | `not_found` | Unknown token/slug, or an id not in the token's scope (never distinguish wrong vs missing) |
| 409 | `workshop_paused` | Completion mark/unmark while paused (Phase 2+) |
| 409 | `workshop_not_started` | Join before `starts_at` (Phase 3) |
| 409 | `undo_expired` | Undo requested after the 30 s window (Phase 2) |
| 410 | `workshop_archived` | Any mutation on an archived workshop (Phase 3) |
| 409 | `topic_exists` | Topic slug/name collision (Phase 10) — Phase 11, 11b and 12 codes are listed in their sections |
| 422 | `validation_error` | Body/param validation failure |
| 500 | `internal_error` | Unexpected; logged with `request_id` |

### Pretty redirect routes (not JSON API)

`GET /j/{join_slug}` → `/app/join/?s=…` · `GET /p/{participant_token}` → `/app/p/?t=…` · `GET /f/{admin_token}` → `/app/f/?t=…` — all 307. **Phase 1.**
`GET /admin` → `/app/admin/` — 307. **Phase 6.**
`GET /` — **Phase 1:** 307 → `/app/`. **Phase 6:** no longer a redirect — it serves the public marketing landing page HTML directly (200, `text/html`). See architecture.md §Serving the landing page at `/`.

---

# Phase 1 endpoints

## Health

### `GET /api/health` — no auth
`{"data": {"status": "ok", "db": "ok"}, "error": null}` — `db` is `"ok"` after a real `SELECT 1`, else 500 `internal_error`.

## Admin surface (header `X-Admin-Key`)

### `GET /api/admin/workshops`
Lists all workshops (also serves as key validation for the Admin Home login). Sorted `created_at` desc.

```json
{"data": {"workshops": [{
  "id": 1, "name": "LangGraph Lab — July", "status": "live",
  "participant_count": 143, "open_help_count": 2,
  "created_at": "2026-07-20T09:00:00Z",
  "join_slug": "Ab3dEfGh", "join_url": "http://localhost:8001/j/Ab3dEfGh",
  "facilitator_url": "http://localhost:8001/f/<admin_token>"
}]}, "error": null}
```
Errors: `invalid_admin_key`.

### `POST /api/admin/workshops`
```json
{"name": "LangGraph Lab — July", "description_md": "Welcome!…",
 "milestones": [{"title": "Set up your environment", "content_md": "```bash\nuv sync\n```", "minutes": 30}]}
```
Validation: `name` 1–120 (trimmed); `description_md` ≤10000; `milestones` 1–50 items in given order; `title` 1–200; `content_md` ≤20000; `minutes` null or 1–480.
*(Phase 3 adds optional `agenda_template_id`, `join_form_template_id`, `starts_at`.)*

Response — the full workshop:
```json
{"data": {"workshop": {
  "id": 1, "name": "…", "description_md": "…", "status": "live", "paused": false, "ai_enabled": false,
  "admin_token": "<43 chars>", "join_slug": "Ab3dEfGh",
  "join_url": "…/j/Ab3dEfGh", "facilitator_url": "…/f/<admin_token>",
  "created_at": "2026-07-20T09:00:00Z"
}}, "error": null}
```
Side effects: audit row `workshop.create`. Errors: `invalid_admin_key`, `validation_error`.

## Facilitator surface (path `admin_token`)

### `GET /api/f/{admin_token}/workshop`
Initial dashboard load + milestone bodies (re-fetched when the dashboard poll reports a new `content_version`).
```json
{"data": {
  "content_version": 3,
  "workshop": {"id": 1, "name": "…", "description_md": "…", "status": "live", "paused": false,
               "ai_enabled": false, "join_slug": "Ab3dEfGh", "join_url": "…", "facilitator_url": "…",
               "created_at": "…"},
  "milestones": [{"id": 11, "position": 0, "title": "…", "content_md": "…", "minutes": 30}]
}, "error": null}
```

### `GET /api/f/{admin_token}/dashboard?v={int}` — poll (2 s)
Unchanged → `{"data": {"changed": false, "version": 42, "content_version": 3}, "error": null}`.
Changed:
```json
{"data": {
  "changed": true, "version": 42, "content_version": 3,
  "workshop": {"id": 1, "name": "…", "status": "live", "paused": false, "ai_enabled": false},
  "stats": {"participant_count": 143, "active_count": 121, "finished_count": 12,
            "median_progress_pct": 40.0, "open_help_count": 3, "answered_help_count": 5,
            "resolved_help_count": 17},
  "milestone_stats": [{"milestone_id": 11, "position": 0, "title": "…",
                        "completed_count": 130, "completed_pct": 90.9}],
  "distribution": [{"completed_count": 0, "participants": 5}, {"completed_count": 1, "participants": 20}],
  "participants": [{"id": 7, "name": "Priya", "joined_at": "…", "last_seen_at": "…",
                    "completed_milestone_ids": [11, 12], "completed_count": 2, "progress_pct": 25.0,
                    "current_milestone_id": 13, "open_help_count": 1,
                    "participant_url": "…/p/<participant_token>"}],
  "help_queue": [{"id": 9, "participant_id": 7, "participant_name": "Priya",
                  "milestone_id": 13, "milestone_title": "Configure the API key",
                  "message": "getting a 401 from…", "status": "open", "escalated": false,
                  "created_at": "…", "updated_at": "…",
                  "answers": [{"id": 3, "source": "facilitator", "answer_md": "Check `.env`…",
                                "draft": false, "created_at": "…",
                                "ai_confidence": null, "ai_model": null, "ai_context": null}]}],
  "broadcast": null,
  "alerts": null,
  "pulse": null,
  "spend": null
}, "error": null}
```
Semantics: `active_count` = participants with `last_seen_at` within 5 min. `distribution` covers every completed-count 0…total (zeros included). `participants` sorted `joined_at` asc (client re-sorts). `help_queue` = all `open` + `answered` requests (newest first within status, `open` block first) plus the 50 most recent `resolved`; totals live in `stats`. `broadcast`/`alerts`/`pulse` are `null` until Phase 2, `spend` `null` until Phase 4 — the frontend renders labelled stubs for them from day one.

### `POST /api/f/{admin_token}/help/{help_request_id}/answer`
Body: `{"answer_md": "…"}` (1–10000). Effect: append `help_answer(source="facilitator")`, request → `answered`, audit `help.answer`, bump version.
Response: `{"data": {"help_request": <help_queue row shape>, "version": 43}, "error": null}`.
Errors: `not_found` (id not in this workshop), `validation_error`. Answering a `resolved` request re-opens nothing — it appends the answer and leaves status `resolved`.

### `POST /api/f/{admin_token}/help/{help_request_id}/resolve`
Facilitator closes a request. Idempotent. Audit `help.resolve`.
Response: `{"data": {"help_request": <row>, "version": 44}, "error": null}`.

## Participant surface

### `GET /api/join/{join_slug}` — no auth; reads auto-resume cookie
```json
{"data": {
  "workshop": {"name": "…", "description_md": "…", "status": "live",
               "milestone_count": 8, "participant_count": 143},
  "me": null
}, "error": null}
```
If the browser carries a valid `workshop0_p_{workshop_id}` cookie (or, for one release after the Phase 9 rename, the legacy-named cookie for that workshop — see architecture.md §Auth model), `"me": {"participant_token": "<22 chars>", "name": "Priya"}` — the page then forwards to the tracker without re-joining. Errors: `not_found`.

### `POST /api/join/{join_slug}`
Body: `{"name": "Priya"}` (1–80 trimmed; duplicates allowed). *(Phase 3 adds `"answers": {…}` for custom join fields.)*
Effect: create participant; **set cookie** `workshop0_p_{workshop_id}=<participant_token>; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000`; bump version.
```json
{"data": {"participant_token": "<22 chars>", "participant_url": "…/p/<token>", "name": "Priya"}, "error": null}
```
Errors: `validation_error`, `workshop_archived`, `workshop_not_started` (Phase 3).

### `GET /api/p/{participant_token}/state?v={int}` — poll (3 s)
Unchanged → `{"data": {"changed": false, "version": 42, "content_version": 3}, "error": null}`.
Changed:
```json
{"data": {
  "changed": true, "version": 42, "content_version": 3,
  "workshop": {"name": "…", "status": "live", "paused": false},
  "milestones": [{"id": 11, "position": 0, "title": "…", "minutes": 30}],
  "me": {"id": 7, "name": "Priya", "completed_milestone_ids": [11],
         "completed_count": 1, "total_count": 8, "progress_pct": 12.5, "rank": 37},
  "leaderboard": [{"rank": 1, "name": "Arun", "completed_count": 6, "progress_pct": 75.0, "is_me": false}],
  "broadcast": null,
  "help_requests": [{"id": 9, "message": "getting a 401…", "status": "answered", "escalated": false,
                     "milestone_id": 13, "created_at": "…",
                     "answers": [{"id": 3, "source": "facilitator", "answer_md": "Check `.env`…",
                                   "created_at": "…"}]}]
}, "error": null}
```
Semantics: `milestones` **excludes** `content_md` (bodies come from the content endpoint). `leaderboard` is the **top 15** of the ranked list (`LEADERBOARD_TOP_N = 15`, full names, always on) **plus the caller's own row appended last when the caller is outside the top 15** (so a workshop of 300 never ships 300 rows per poll; at most 16 rows). Each row's `rank` is the participant's true 1-based position in the full ranking (the appended caller row therefore carries its real rank, e.g. 300), and `is_me` marks the caller's row. A caller inside the top 15 appears once, in place. Ranking order: `completed_count` desc → earliest timestamp of reaching that count asc → `joined_at` asc; `rank` is the 1-based position (no tie-sharing). `help_requests` = mine only, newest first; never includes drafts or `ai_context`. Side effect: throttled `last_seen_at` touch — a single DB-side conditional `UPDATE participant SET last_seen_at=:now WHERE id=:id AND last_seen_at < :now − 60 s` (stateless; at most one effective write per participant per 60 s regardless of how many instances serve the polls). The `changed:false` fast path (`v == state_version`) is unchanged. Changed payloads are built per request (no cross-request memo; see architecture.md §Live-update point 5).
Errors: `not_found`. Archived workshops still return state (read-only archive view; `workshop.status` = `"archived"`).

### `GET /api/p/{participant_token}/content?cv={int}`
Unchanged → `{"data": {"changed": false, "content_version": 3}, "error": null}`.
Changed:
```json
{"data": {"changed": true, "content_version": 3,
  "workshop": {"name": "…", "description_md": "…"},
  "milestones": [{"id": 11, "position": 0, "title": "…", "content_md": "…", "minutes": 30}]
}, "error": null}
```

### `POST /api/p/{participant_token}/milestones/{milestone_id}/complete`
Idempotent (unique constraint; re-complete is a no-op success). Blocked while paused/archived.
Response: `{"data": {"completed_milestone_ids": [11, 13], "completed_count": 2, "progress_pct": 25.0, "version": 43}, "error": null}`.
Errors: `not_found` (milestone not in my workshop), `workshop_paused`, `workshop_archived`.

### `POST /api/p/{participant_token}/milestones/{milestone_id}/uncomplete`
Deletes my completion if present (idempotent). Same response shape and errors as complete.

### `POST /api/p/{participant_token}/help`
Body: `{"message": "…"}` (1–4000; rendered as plain text everywhere). Effect: create request with `milestone_id` = my current milestone (lowest-position incomplete; null if finished); bump version. *(Phase 4: additionally triggers the AI pipeline as a background task when enabled.)*
Response: `{"data": {"help_request": <tracker row shape>, "version": 43}, "error": null}`.
Errors: `validation_error`, `workshop_archived`.

### `POST /api/p/{participant_token}/help/{help_request_id}/resolve`
Participant marks their own request resolved. Idempotent. Errors: `not_found` (not mine).
Response: `{"data": {"help_request": <row>, "version": 44}, "error": null}`.

---

# Phase 2 endpoints — Facilitator command & proactive intelligence

All under `/api/f/{admin_token}/…`; all bump `state_version`, write an audit row, and (where noted) record undo data. Undoable actions return `"undoable_action_id"`.

| Endpoint | Body → Effect |
|---|---|
| `POST …/broadcast` | `{"message_md": "…"}` (1–4000) → new active broadcast (previous one cleared). Undoable (restores previous). Response: `{"broadcast": {...}, "version": N, "undoable_action_id": 77}` |
| `POST …/broadcast/clear` | `{}` → active broadcast `cleared_at` = now |
| `POST …/pause` | `{"paused": true|false}` → freeze/unfreeze completions. Undoable |
| `POST …/milestones/advance` | `{"milestone_id": 13, "participant_ids": [7, 9]}` or `"participant_ids": null` (= all) → create missing completions with `source: "facilitator"`. Undoable (deletes created rows). Response includes `"affected_count"` |
| `POST …/milestones/reorder` | `{"milestone_ids": [12, 11, 13]}` (exact permutation) → rewrite positions; bumps `content_version` too |
| `POST …/milestones` | `{"title", "content_md", "minutes"}` → append milestone; bumps `content_version` |
| `PATCH …/milestones/{id}` | any of `{"title", "content_md", "minutes"}` → edit; bumps `content_version` |
| `DELETE …/milestones/{id}` | removes milestone + its completions (confirmation is a UI concern); bumps both versions |
| `POST …/undo/{action_id}` | `{}` → apply inverse within 30 s. Errors: `undo_expired`, `not_found` |
| `GET …/audit?before_id={int}&limit={int≤100}` | → `{"actions": [{"id", "actor", "action", "detail": {…}, "created_at", "undone_at"}], "has_more": true}` newest first |
| `PATCH …/settings` | `{"stuck_minutes": 10}` (2–120) |

Phase 2 also **activates** these dashboard-poll fields (shapes normative now):
```json
"broadcast": {"id": 5, "message_md": "…", "created_at": "…"},
"alerts": {"stuck": [{"participant_id": 7, "name": "Priya", "minutes_inactive": 14,
                       "current_milestone_id": 13}],
           "bottleneck": {"milestone_id": 13, "title": "Configure the API key", "waiting_count": 96}},
"pulse": {"pace_ratio": 0.82, "on_track_pct": 61.0, "open_help_count": 3,
          "projected_finish_at": "2026-07-20T17:40:00Z"}
```
The participant poll's `broadcast` field activates with the same shape. Definitions: *stuck* = live, not paused, not finished, no completion and no help activity for ≥ `stuck_minutes`. *Bottleneck* = the milestone that is the current milestone of the largest participant group (≥25% of active participants, else null). *pace_ratio* = median actual minutes-per-milestone ÷ planned `minutes` (1.0 = on plan; >1 = slower). *on_track_pct* = % of participants whose progress ≥ elapsed-time-proportional expectation. *projected_finish_at* = now + (median remaining planned minutes × pace_ratio).

---

# Phase 3 endpoints — Lifecycle, templates & re-run

| Endpoint | Auth | Body → Effect |
|---|---|---|
| `POST /api/f/{t}/end` | token | `{"grace_hours": 24}` (0–168) → status `grace`, `ended_at`=now, `grace_until`=now+h. `0` archives immediately |
| `POST /api/f/{t}/archive` | token | `{}` → status `archived` now (terminal, read-only) |
| `POST /api/f/{t}/reopen` | token | `{}` → `grace` → `live` (mistake recovery; not allowed from `archived`) |
| `POST /api/f/{t}/clone` | token | `{"name": "…"}` → new `live` workshop, milestones copied, fresh tokens, zero participants. Response: new workshop object |
| `POST /api/f/{t}/save-as-template` | token | `{"name": "…"}` → agenda template from current milestones |
| `GET /api/admin/templates` | key | → `{"agenda_templates": [{"id","name","description_md","milestone_count","created_at","updated_at"}], "join_form_templates": [{"id","name","field_count","created_at","updated_at"}]}` |
| `POST /api/admin/templates/agenda` | key | `{"name", "description_md", "milestones": [{"title","content_md","minutes"}]}` |
| `GET /api/admin/templates/agenda/{id}` | key | full template incl. milestones |
| `PATCH /api/admin/templates/agenda/{id}` / `DELETE` | key | edit / delete (never affects existing workshops — snapshots) |
| `POST /api/admin/templates/forms` + `GET/PATCH/DELETE …/forms/{id}` | key | same pattern; body `{"name", "fields": [<join-field shape, data-model.md>]}` |

`POST /api/admin/workshops` gains optional `agenda_template_id`, `join_form_template_id`, `starts_at`. `GET /api/join/{slug}` gains `"join_form": [<field>]` and `"starts_at"`; `POST /api/join/{slug}` gains `"answers": {…}` validated against the snapshot. Admin Home list gains `ended_at`/`starts_at` for Live/Upcoming/Ended grouping and an archived workshop's dashboard/tracker render read-only.

---

# Phase 4 endpoints — AI help-desk

| Endpoint | Auth | Body → Effect |
|---|---|---|
| `POST /api/f/{t}/ai` | token | `{"enabled": true|false}` → toggle; audit `ai.toggle`. When no `OPENROUTER_API_KEY` is configured, responds 200 with `{"enabled": false, "available": false}` — never an error (air-gapped) |
| `GET /api/f/{t}/spend` | token | → `{"total_cost_usd": 0.4312, "call_count": 57, "prompt_tokens": 91234, "completion_tokens": 18022, "by_purpose": [{"purpose": "triage_answer", "cost_usd": 0.4312, "count": 57}]}` |
| `POST /api/p/{token}/help/{id}/escalate` | token | `{}` → `escalated=true`, status → `open` (AI answers stay visible); bump version. Idempotent |

Phase 4 **activates** (shapes normative now): dashboard `"spend": {"total_cost_usd": 0.43}`; help-queue answers carry real `ai_confidence`, `ai_model`, and `ai_context` (shape = `help_answer.ai_context_json`, data-model.md) plus `draft: true` rows for review; the workshop objects' `ai_enabled` goes live; tracker answers with `"source": "ai"` are badged AI client-side with the escalate action. Facilitator sending a reviewed draft uses the existing `POST …/help/{id}/answer` (the draft row stays for audit; the sent answer is a new `facilitator` row).

---

*Phase 5 (deploy) adds no API surface.*

---

# Phase 6 endpoints — Public landing page & self-service creation

## `POST /api/public/workshops` — **no auth** (no `X-Admin-Key`, no token)

The keyless twin of `POST /api/admin/workshops`. Both routes call the **same** creation service (`src/workshop0/services/workshops.py` → `create_workshop(session, spec, *, created_via, creator_email, base_url)`), so the two paths cannot drift; the public route differs only in the auth dependency (none), the required `creator_email`, and `created_via="public"`.

Request — identical to the admin body plus `creator_email`:
```json
{"name": "LangGraph Lab — July", "description_md": "Welcome!…",
 "milestones": [{"title": "Set up your environment", "content_md": "```bash\nuv sync\n```", "minutes": 30, "input_config": null}],
 "join_form": [],
 "creator_email": "asha@example.com"}
```

Validation: `name`, `description_md`, `milestones`, `join_form` and per-milestone rules are **exactly** the admin rules (unchanged, same validators). `creator_email` — required, non-null, trimmed and lower-cased before storage, 3–254 chars, must match a single-`@` address with a dot-bearing domain and no whitespace (regex `^[^@\s]+@[^@\s]+\.[^@\s]+$`).

Response — **the same full-workshop payload as the admin create** (so the frontend reuses one type), plus the two new fields:
```json
{"data": {"workshop": {
  "id": 42, "name": "…", "description_md": "…", "status": "live", "paused": false, "ai_enabled": false,
  "admin_token": "<43 chars>", "join_slug": "Ab3dEfGh",
  "join_url": "…/j/Ab3dEfGh", "facilitator_url": "…/f/<admin_token>",
  "created_via": "public", "creator_email": "asha@example.com",
  "created_at": "2026-08-03T09:00:00Z"
}}, "error": null}
```

Side effects: identical to admin create — one `workshop` row (`created_via="public"`, `creator_email` set), its milestones, audit row `workshop.create` (`detail_json` additionally carries `{"created_via": "public"}`), log event `workshop.created` with `created_via="public"` and the email **masked** to its first 2 characters + domain (`as***@example.com`).

Errors (exact codes):

| HTTP | `code` | When |
|---|---|---|
| 422 | `validation_error` | Missing/blank `creator_email`, malformed address, >254 chars — message: `"creator_email: enter a valid email address"`. Also every existing body-validation failure, with the existing messages |
| 410 | `workshop_archived` | n/a here (listed for completeness — creation never returns it) |
| 500 | `internal_error` | Unexpected |

There is **no** `invalid_admin_key` on this route: presenting an `X-Admin-Key` header is neither required nor rejected — it is ignored.

> **Assumed:** no rate limit, no cap, no captcha, no email verification and no mail send on this endpoint — the email is a deterrent and a contact trail only. Recorded as an accepted risk in architecture.md §Auth model.

## Changes to the existing admin surface (additive only)

### `POST /api/admin/workshops`
Unchanged request. The response `workshop` object gains `"created_via": "admin"` and `"creator_email": null`. Behaviour, validation, audit row and status are otherwise identical.

### `GET /api/admin/workshops`
Unchanged request/auth/sort. Each row in `workshops[]` gains two fields:
```json
{"…existing fields…", "created_via": "public", "creator_email": "asha@example.com"}
```
`creator_email` is `null` for admin-created workshops. This is the **only** surface on which `creator_email` is ever returned — it appears in no facilitator, participant, poll or public payload.

*No other endpoint's request or response changes in Phase 6.*

---

# Phase 10 endpoints — Opportunity Board (C8–C10)

Normative: the backend slice implements exactly this; the two frontend slices and the e2e slice build against it in parallel. Schema in [data-model.md](data-model.md) §Phase 10. Two new routers: `src/workshop0/api/board_public.py` (prefix `/api/public`, no auth) and `src/workshop0/api/board_admin.py` (prefix `/api/admin`, `require_admin_key` — the same dependency as the existing admin surface).

## New error codes

| HTTP | `code` | When |
|---|---|---|
| 409 | `topic_exists` | Creating/renaming a topic whose slug or name (case-insensitive) already exists |

Every other failure uses the existing catalogue (`invalid_admin_key`, `not_found`, `validation_error`, `internal_error`).

## Shared shapes

**Enums:** `type` ∈ `workshop` \| `engagement` \| `role` \| `cofacilitation`. `location_mode` ∈ `remote` \| `onsite` \| `hybrid`. Effective `status` ∈ `draft` \| `open` \| `expired` \| `closed` (data-model.md §Effective status). Dates (`starts_on`, `ends_on`) are `"YYYY-MM-DD"`; `deadline` is an ISO 8601 UTC timestamp with `Z` (input must carry a timezone — naive → `validation_error`).

**`public_url`** = `{WORKSHOP0_BASE_URL or request origin}/opportunities/{id}` (pretty redirect below).

**PublicOpportunityCard** (list item):
```json
{"id": 12, "title": "GenAI for product teams — 2-day workshop", "type": "workshop",
 "summary": "Hands-on LLM workshop for 30 PMs in Bengaluru.",
 "partner_display_name": "A Bengaluru fintech",
 "topics": [{"slug": "generative-ai", "name": "Generative AI & LLMs"}, {"slug": "prompt-engineering", "name": "Prompt Engineering"}],
 "location_mode": "hybrid", "city": "Bengaluru",
 "starts_on": "2026-12-05", "ends_on": "2026-12-06", "duration_text": "2 days",
 "compensation_text": "Paid — day rate", "deadline": "2026-11-30T18:29:59Z",
 "published_at": "2026-11-10T09:00:00Z", "status": "open",
 "public_url": "http://localhost:8001/opportunities/12"}
```
**PublicOpportunityDetail** = card + `"description_md": "…"`. From Phase 11c the card also carries `locations` and `city` is derived from it (§Phase 11c).

**Hard rule (gate-tested):** no public response ever contains the keys `partner_internal_name`, `internal_notes`, `stored_status`, or the values of those fields. Public serializers are an explicit allow-list (the field list above), never "model minus some fields".

**AdminOpportunity** (admin list rows and admin detail):
```json
{"id": 12, "title": "…", "type": "workshop", "summary": "…", "description_md": "…",
 "topics": [{"id": 19, "slug": "generative-ai", "name": "Generative AI & LLMs", "active": true}],
 "location_mode": "hybrid", "city": "Bengaluru", "starts_on": "2026-12-05", "ends_on": "2026-12-06",
 "duration_text": "2 days", "compensation_text": "Paid — day rate", "deadline": "2026-11-30T18:29:59Z",
 "partner_display_name": "A Bengaluru fintech", "partner_internal_name": "Acme Payments Pvt Ltd",
 "internal_notes": "Contact: R. Rao", "status": "open", "stored_status": "open",
 "public_url": "…/opportunities/12", "published_at": "…", "closed_at": null,
 "created_at": "…", "updated_at": "…"}
```
(Admin list rows omit `description_md` and `internal_notes` to keep the list light.)

**Topic (admin):** `{"id": 19, "slug": "generative-ai", "name": "Generative AI & LLMs", "category": "AI & Data", "position": 18, "active": true, "opportunity_count": 4}` — `opportunity_count` counts listings of any status. **Topic (public):** `{"slug", "name", "category", "open_count"}` — `open_count` counts effective-`open` listings.

## Public surface (no auth)

### `GET /api/public/topics`
Active topics only, `position` asc: `{"data": {"topics": [<public topic>]}, "error": null}`. Topics with `open_count: 0` are included (the UI shows them muted).

### `GET /api/public/opportunities`
Query: `type` (optional, one enum value; unknown → `validation_error`) · `topic` (optional, **repeatable** slug; a listing matches if it has **any** of the given topics; unknown slugs match nothing) · `sort` = `newest` (default: `published_at` desc, `id` desc) \| `deadline` (`deadline` asc, `id` asc) · `page` ≥1 (default 1) · `page_size` 1–50 (default 12).
Only effective-`open` listings (`status='open' AND deadline > now`). Drafts, closed and expired never appear.
```json
{"data": {"opportunities": [<PublicOpportunityCard>], "page": 1, "page_size": 12, "total": 30, "total_pages": 3}, "error": null}
```
`total_pages` = `ceil(total / page_size)` (0 when total is 0). A page past the end returns an empty list with 200. Ordering is total (tie-broken by id) so pages never overlap or skip.

### `GET /api/public/opportunities/{id}`
`{"data": {"opportunity": <PublicOpportunityDetail>}, "error": null}`. Returns `open`, `expired` **and** `closed` listings (shared links keep working; the page shows a closed banner). Draft or unknown id → 404 `not_found` ("This opportunity isn't available.").

## Admin surface (header `X-Admin-Key`; from Phase 11 also an admin session)

From Phase 11 an **empty** `X-Admin-Key` header (`""`, which existing clients send when no key is stored) is treated as absent, so an admin session falls through and passes; resolution order in architecture.md §Network identity.

### `GET /api/admin/opportunities`
Query: `status` (effective; optional) · `type` · `q` (case-insensitive substring over title, partner_display_name, partner_internal_name) · `page` (default 1) · `page_size` 1–100 (default 25). Sort `updated_at` desc, `id` desc.
```json
{"data": {"opportunities": [<AdminOpportunity row>], "page": 1, "page_size": 25, "total": 39, "total_pages": 2,
          "counts": {"draft": 3, "open": 30, "expired": 3, "closed": 3}}, "error": null}
```
`counts` is over all listings (ignores the filters) — it powers the status tabs.

### `POST /api/admin/opportunities`
```json
{"title": "…", "type": "workshop", "summary": "…", "description_md": "…",
 "topic_ids": [19, 21], "location_mode": "hybrid", "city": "Bengaluru",
 "starts_on": "2026-12-05", "ends_on": "2026-12-06", "duration_text": "2 days",
 "compensation_text": "Paid — day rate", "deadline": "2026-11-30T18:29:59Z",
 "partner_display_name": "A Bengaluru fintech", "partner_internal_name": "Acme Payments Pvt Ltd",
 "internal_notes": "Contact: R. Rao", "status": "draft"}
```
Validation (all strings trimmed; blank optional strings → null): `title` 3–160 · `type` enum · `summary` 1–280 · `description_md` ≤20000 · `topic_ids` 1–8 distinct ids of **active** topics · `location_mode` enum · `city` 1–80 required when `onsite`/`hybrid` (forced null when `remote`) · `starts_on`/`ends_on` optional, `ends_on ≥ starts_on` · `duration_text` ≤80 · `compensation_text` ≤120 · `deadline` required, tz-aware · `partner_display_name`/`partner_internal_name` ≤160 · `internal_notes` ≤5000 · `status` ∈ `draft`\|`open`\|`closed` (default `draft`) · publish rule (data-model.md). Messages are `"<field>: <reason>"`, e.g. `"topic_ids: choose 1 to 8 topics"`, `"city: required for onsite or hybrid"`, `"deadline: set a future deadline to publish"`.
Response: `{"data": {"opportunity": <AdminOpportunity, full>}, "error": null}`. Side effects: rows in `opportunity` + `opportunity_topic`; `published_at` set if created `open`; audit `opportunity.create` (actor `admin`, `subject_type="opportunity"`); log event `opportunity.created`.

### `GET /api/admin/opportunities/{id}`
`{"data": {"opportunity": <AdminOpportunity, full>, "activity": [{"id": 88, "action": "opportunity.publish", "detail": {…}, "created_at": "…"}]}, "error": null}` — `activity` = the 20 newest audit rows with this subject, newest first. Unknown id → `not_found`.

### `PATCH /api/admin/opportunities/{id}`
Any subset of the POST fields (same validation; `topic_ids` replaces the set). A field that is omitted is unchanged; an optional field sent as `null` is cleared. Effects: `stored_status` transitions set `published_at` (first open) / `closed_at` (→ closed; cleared when leaving closed). Exactly **one** audit row per PATCH: `opportunity.publish` / `opportunity.unpublish` / `opportunity.close` when the stored status changed (detail carries `from_status`, `to_status`, `changed_fields`), else `opportunity.update` (no row when nothing changed). Response as POST.

There is **no delete** — closing is the end of a listing's life (audit and future applications reference it).

### `GET /api/admin/topics`
All topics including inactive, `position` asc: `{"data": {"topics": [<admin topic>]}, "error": null}`.

### `POST /api/admin/topics`
`{"name": "Elixir", "category": "Languages"}` — `name` 2–80, `category` 2–48. `slug` derived: lower-case, runs of non-`[a-z0-9]` → `-`, trimmed of `-`, ≤48 chars; empty slug → `validation_error`. Duplicate slug or case-insensitive name → 409 `topic_exists`. New topic: `active=true`, `position=max+1`. Audit `topic.create`. Response `{"data": {"topic": <admin topic>}, "error": null}`.

### `PATCH /api/admin/topics/{id}`
Any of `{"name", "category", "active"}`; slug never changes. Rename collisions → `topic_exists`. Audit `topic.update` (with `changed_fields`). Response as POST.

## Pretty routes (Phase 10)

`GET /opportunities` → 307 `/app/opportunities/` · `GET /opportunities/{id}` → 307 `/app/opportunities/view/?id={id}` (the segment is URL-quoted and passed through; a non-numeric id just renders the page's not-found state).

---

# Phase 11 endpoints — Network sign-in, CV-drafted profiles, admin pool (C11–C13)

Specified for Phase 11; shapes are normative for that phase's slices. New error codes: 401 `not_signed_in` (no/expired session on a user endpoint) · 403 `csrf_failed` (cookie-authenticated mutation without `X-Requested-With: workshop0`) · 403 `not_admin` · 409 `profile_exists` · 409 `invite_email_mismatch` · 410 `invite_expired` · 413 `file_too_large` (>5 MB) · 415 `unsupported_file` (not PDF/DOCX) · 422 `cv_unreadable` (no extractable text — "paste your CV text instead") · 429 `rate_limited` (with `Retry-After`) · 503 `signin_not_configured`.

**Auth (all in `src/workshop0/auth/routes.py`, prefix `/api/auth`):**

| Endpoint | Behaviour |
|---|---|
| `GET /api/auth/config` | `{"google_enabled": true}` — false when `WORKSHOP0_GOOGLE_CLIENT_ID`/`SECRET` unset (UI shows a labelled "Sign-in isn't set up on this server" state, never an error) |
| `GET /api/auth/google/start?next=/app/network/&invite=<token>` | 302 to the IdP authorization endpoint (scopes `openid email profile`, PKCE S256, `state`, `nonce`, `prompt=select_account`). Stores state/nonce/verifier/next/invite in a signed, HttpOnly, 10-minute cookie `workshop0_oidc`. `next` must start with `/app/` (else replaced by `/app/network/`). Rate limit 20/min/IP. 503 `signin_not_configured` when disabled |
| `GET /api/auth/google/callback?code&state` | Verifies state cookie, exchanges the code (client secret + PKCE), verifies the ID token (JWKS signature, `iss`, `aud`, `exp`, `nonce`), requires `email_verified`; if `invite` is present, checks it **first** (Invite acceptance below); upserts `app_user` by (issuer, subject) — or claims the invite-created row with the same email; applies the invite; creates a session; sets `workshop0_session` (HttpOnly, `Secure` when the base URL is https, SameSite=Lax, Path=/, 30 d); 303 → `next`. Any failure → 303 `/app/signin/?error=<code>` (plus `next`, and for the invite codes the extra params below) with codes `state_mismatch`, `email_unverified`, `idp_error`, `invite_email_mismatch`, `invite_expired`. A failure creates **no** user, **no** session and changes no invite |
| `GET /api/auth/me` | `{"user": {"id", "email", "display_name", "avatar_url", "is_admin", "has_profile", "invite_accepted"} \| null}` — never 401. `invite_accepted` (bool) = a `network_invite` row exists with `accepted_user_id` = this user and `accepted_at` set. It is the **only** signal the onboarding page uses to show **Verified** before a profile exists (server truth; the `?invite=` query param never grants it) |
| `POST /api/auth/signout` | Revokes the session, clears the cookie; idempotent |

**Invite acceptance (normative; owned by `auth/routes.py`):**
1. **Lookup** by token (unknown token → treated like no invite: normal sign-in, no error).
2. **Expired** (`expires_at ≤ now` and not yet accepted) → 303 `/app/signin/?error=invite_expired&next=<next>` (no `invite` param, so the next attempt is a plain sign-in). Sign-in page copy: "This invite has expired — ask smallTech for a new one." / "You can still join the network without an invite."
3. **Email mismatch** (verified ID-token email ≠ `network_invite.email`, case-insensitive) → 303 `/app/signin/?error=invite_email_mismatch&invite=<token>&invite_email=<masked>&next=<next>`, where `<masked>` is the invite email in the log masking form (`as***@example.com`, URL-encoded). The sign-in page renders "This invite was sent to `<invite_email>` — sign in with that Google account." (capabilities.md §C11; without `invite_email`: "This invite was sent to a different email address — sign in with that Google account.") and keeps the Continue-with-Google button carrying the same `invite`, so the user can retry with the right account. Only someone holding the invite token sees the masked address.
4. **Match** → user upsert + session as usual; if `accepted_at` is null set `accepted_at = now`, `accepted_user_id = user.id` (re-using an already accepted invite by the same user is a no-op success). Then, **if the user already has a `trainer_profile`** and it is not verified, the callback sets `verified = true`, `verified_at = now`, `verified_by = network_invite.created_by` — the one profile write allowed outside `/api/me` (no other column) — and writes audit `trainer.verify` (actor `user`, `subject_type="trainer"`, detail `{"via": "invite", "invite_id"}`). With no profile yet, `POST /api/me/profile` creates it verified (below). Log `auth.invite_accepted` (invite id, user id, `profile_verified` bool; email masked).
5. The join page (`/app/network/join/?invite=<token>`) signs in with `next=/app/network/join/` and the token; after the callback it shows **Verified** iff `user.invite_accepted`.

**Trainer self-service (`src/workshop0/api/network_me.py`, prefix `/api/me`, `require_user`; every mutation needs `X-Requested-With: workshop0`):**

| Endpoint | Behaviour |
|---|---|
| `POST /api/me/cv` (multipart `file`) | PDF/DOCX ≤5 MB → stored blob + text extract → `cv_document` (replacing any previous one **in place — same row id**, so drafting spend linked by `ai_usage.cv_document_id` keeps accumulating per trainer; old blob deleted; `draft_json` cleared) with `draft_status="pending"` → profile drafter as a BackgroundTask. Rate limit 10/h/user. Response `{"cv": {"id", "source", "original_filename", "draft_status"}}` |
| `POST /api/me/cv/text` | `{"text": "…"}` 200–30000 chars (pasted LinkedIn/CV text; no URLs are fetched) → same as above with `source="text"` |
| `GET /api/me/cv/draft` | `{"draft_status": "pending\|ready\|failed\|skipped", "draft": <ProfileInput>\|null, "autofilled_fields": ["headline", "topics", …]}` — polled by the onboarding screen every 1.5 s, ≤60 s |
| `POST /api/me/profile` | Creates the profile (live immediately). Body = **ProfileInput** + `"consent": true` (required, else `validation_error` "consent: please agree to continue"). 409 `profile_exists` if one exists. Starts `verified=true` (`verified_by` = the invite's `created_by`) when the user has an accepted invite (`invite_accepted`). `autofilled_fields` is set to the drafted fields (the current `cv_document`'s) whose submitted value still equals the drafted value — the ones the person did not touch. Sends no email in Phase 11 |
| `GET /api/me/profile` | `{"profile": <OwnProfile>, "completeness": {"pct": 70, "missing": ["availability", "past_work"]}}` — own rates included |
| `PATCH /api/me/profile` | Partial ProfileInput; the **first** (every) PATCH clears `autofilled_fields` to `[]` — saving from My profile counts as having reviewed the pre-fill |
| `GET /api/me/cv/file` | Downloads the owner's own CV |
| `DELETE /api/me` | `{"confirm_email": "<own email>"}` → deletes CV blob, cv_document, profile (cascade topics/tags/notes), sessions and the user; audit `account.delete` (actor `user`, detail holds only the masked email); clears cookie |

**ProfileInput:** `{"headline", "bio_md", "city", "remote_ok", "linkedin_url", "github_url", "website_url", "topics": [{"slug", "level"}], "past_work": [...], "rate_min", "rate_max", "rate_currency", "rate_unit", "pro_bono", "availability": {...}, "available_from", "blackouts": [...]}` — rules in data-model.md §trainer_profile; only `headline` (3–160) and ≥1 topic are required. `rate_unit` ∈ `hour` \| `day` \| `course` \| `month` (any other value → `validation_error` "rate_unit: must be one of hour, day, course, month"); `rate_currency` ∈ `INR` \| `USD`.

**Privacy (normative):** rates, email and CV fields appear only in the owner's own `/api/me/*` payloads (`GET`/`POST`/`PATCH /api/me/profile`, the CV responses and the draft poll) and in admin payloads; raw CV text (`text_extract`), `storage_key` and `sha256` are never returned to anyone (CV meta = `id`, `source`, `original_filename`, `content_type`, `size_bytes`, `draft_status`, `created_at`).

**Completeness** (one function, `services/profiles.py::completeness`): 10 weighted checks, 10 % each — headline · bio ≥80 chars · ≥3 topics · city or remote_ok · ≥1 link · ≥1 past work item · rate range + currency + unit (or pro_bono) · weekly availability non-empty · available_from set · CV on file.

**Admin pool (`src/workshop0/api/network_admin.py`, prefix `/api/admin/network`, `require_admin`):**

| Endpoint | Behaviour |
|---|---|
| `GET …/trainers?q&topic&verified&tag&page&page_size` | Paginated (25, max 100) rows `{"id", "display_name", "email", "headline", "city", "remote_ok", "topics": [{"slug","name","level"}], "rate": {...}\|null, "verified", "completeness_pct", "tags", "created_at", "updated_at"}`; `q` = case-insensitive over name/email/headline/bio; `topic` repeatable (ANY) |
| `GET …/trainers/{id}` | Full profile + `notes`, `tags`, `cv` meta, `ai_cost_usd` (drafting spend for this trainer = `SUM(ai_usage.cost_usd)` over rows whose `cv_document_id` is the trainer's `cv_document.id`, which is stable across CV replacements — data-model.md §cv_document), `activity` |
| `GET …/trainers/{id}/cv` | Local backend: streamed file with `Content-Disposition`; GCS: 307 to a 5-minute V4 signed URL. Audit `cv.download` |
| `POST …/trainers/{id}/verify` · `…/unverify` | Sets/clears the badge; audit `trainer.verify`/`trainer.unverify` |
| `POST …/trainers/{id}/notes` | `{"body"}` → admin_note; audit `trainer.note` |
| `PUT …/trainers/{id}/tags` | `{"tags": [...]}` replaces the set; audit `trainer.tag` |
| `GET …/trainers.csv?<same filters>` | CSV (UTF-8 BOM, `workshop0-trainers-YYYYMMDD.csv`), never includes CV text |
| `GET/POST …/invites` | List / create `{"email", "name"}` → `{"invite": {"id", "email", "url": "…/invite/<token>", "expires_at", "accepted_at"}}`; audit `invite.create`. Phase 11 shows the URL for copying (email send = Phase 12) |
| `GET …/ai-spend` | `{"total_cost_usd", "call_count", "prompt_tokens", "completion_tokens", "by_purpose": [...]}` over `ai_usage WHERE workshop_id IS NULL` |

Pretty routes: `GET /invite/{token}` → 307 `/app/network/join/?invite={token}` · `GET /network` → 307 `/app/network/`.

---

# Phase 11b endpoints — Phase 10 feedback (partners, paste-to-fill drafting, compensation unit)

Normative for slices F2–F9 ([roadmap.md](roadmap.md) §Phase 11b). Schema is in [data-model.md](data-model.md) §Phase 11b and the drafter in [agent.md](agent.md) §Opportunity drafter. Every endpoint here uses the admin auth (`X-Admin-Key` or an admin session, `require_admin_key`). Cookie-authenticated mutations also need `X-Requested-With: workshop0`. Routers:
- `src/workshop0/api/partners_admin.py`, prefix `/api/admin`;
- `src/workshop0/api/board_ai_admin.py`, prefix `/api/admin`;
- `src/workshop0/api/board_admin.py`, for the opportunity changes.

**New error codes:**

| HTTP | `code` | When |
|---|---|---|
| 409 | `partner_exists` | Creating or renaming a partner whose normalized internal name (case- and whitespace-insensitive) already exists |
| 503 | `ai_not_configured` | Drafting requested while network AI is unavailable (no key, or key without workspace id). Message: "AI drafting isn't configured on this server — fill the form by hand." |
| 502 | `ai_draft_failed` | The model call failed or its output failed the guardrails. Message: "Drafting failed — fill the form by hand or try again." |

`rate_limited` (429) and `validation_error` are reused from the existing catalogue.

## Partners

**AdminPartner:** `{"id": 3, "internal_name": "Zenvia Learning Pvt Ltd", "display_name": "A Pune edtech", "notes": "Contact: P. Nair", "active": true, "opportunity_count": 2, "created_at": "…", "updated_at": "…"}`. `opportunity_count` counts listings of any status. **PartnerRef** (inside opportunity payloads): `{"id", "internal_name", "display_name", "active"}`. It never contains `notes`, and `name_key` is never serialized.

| Endpoint | Behaviour |
|---|---|
| `GET /api/admin/partners` | Every partner, including inactive ones, ordered by `name_key`: `{"partners": [<AdminPartner>]}`. Not paginated, because the list holds tens of rows |
| `POST /api/admin/partners` | Body `{"internal_name": "…", "display_name": "…"\|null, "notes": "…"\|null}`. `internal_name` is trimmed and whitespace-collapsed, 2–160. `display_name` ≤160 and `notes` ≤5000; blank → null. A duplicate `name_key` → 409 `partner_exists` and no row. The new partner has `active=true`. Audit `partner.create` (`subject_type="partner"`, detail `{"internal_name", "by"}`). Log `partner.created` carries the `partner_id` only. Response `{"partner": <AdminPartner>}` |
| `PATCH /api/admin/partners/{id}` | Any of `internal_name`, `display_name`, `notes`, `active`. Omitted fields are unchanged, an optional field sent as null is cleared, and a null `internal_name` or `active` → `validation_error`. A rename collision → 409 `partner_exists`. A rename also rewrites `opportunity.partner_internal_name` on the partner's listings (the mirror). Exactly one audit `partner.update` with `changed_fields` (and none on a no-op). Log `partner.updated` carries the id only. Unknown id → 404 `not_found`. Response as POST |

There is no delete. Changing a partner's `display_name` does **not** change any listing's `partner_display_name`, because the public name is per listing.

## Opportunity changes (`board_admin.py` / `services/opportunities.py`)

**New and changed request fields** (POST and PATCH; same merge semantics as Phase 10):
- `partner_id` (int\|null) — must be an existing partner. A partner that is inactive and **not** already the listing's partner → `"partner_id: partner is inactive"`. An unknown id → `"partner_id: partner <id> does not exist"`. Null clears it.
- `partner_internal_name` (string\|null, **legacy**, still accepted so existing clients and fixtures keep working) — used only when `partner_id` is absent from the body.
  - A non-null value is normalized and matched on `name_key`. A match is used, under the same inactive rule as `partner_id`. No match → a partner is created (`display_name` = the merged `partner_display_name`) with an audit `partner.create` in the same transaction.
  - Null clears the partner.
  - If both fields are present and resolve to different partners → `"partner_id: conflicts with partner_internal_name"`.

  Resolution goes through `services/partners.py::resolve_partner`. Either way the mirror is written (data-model.md).
- `compensation_min` / `compensation_max` (int\|null) — each 0–100000000 (`"compensation_min: must be between 0 and 100000000"`). When both are set, `max ≥ min` (`"compensation_max: must be at least compensation_min"`).
- `compensation_currency` ∈ `INR` \| `USD` and `compensation_unit` ∈ `hour` \| `day` \| `course` \| `month` (enum messages as elsewhere).
  - When either amount is set, both are required (`"compensation_currency: required with an amount"`, `"compensation_unit: required with an amount"`).
  - When neither amount is set, both must be null (`"compensation_min: enter an amount, or clear the currency and unit"`).
- `compensation_text` — unchanged validation (≤120). It is now the note.

Every rule applies to the merged post-write state, as with the Phase-10 cross-field rules. `changed_fields` uses the field names `partner_id`, `compensation_min`, `compensation_max`, `compensation_currency`, `compensation_unit` and `compensation_text`. It no longer reports `partner_internal_name`, because a partner change is reported as `partner_id`.

**AdminOpportunity (rows and full) gains:**
- `"partner_id": 3`;
- `"partner": <PartnerRef>|null`;
- the four compensation fields.

`partner_internal_name` stays in admin payloads, now **derived** from `partner.internal_name` (null when there is no partner). `internal_notes` is unchanged (full only). Admin `q` matches title, `partner_display_name` and the **partner's** `internal_name` (via a join).

**PublicOpportunityCard / Detail gain** exactly `compensation_min`, `compensation_max`, `compensation_currency` and `compensation_unit`, added to the explicit allow-list. The **hard rule** from Phase 10 is extended: no public response ever contains the keys `partner_id`, `partner`, `name_key` or `notes`, or any partner row's `internal_name`/`notes` value, in addition to the Phase-10 list. Public serializers never load the partner row.

## Paste-to-fill drafting (`board_ai_admin.py`)

| Endpoint | Behaviour |
|---|---|
| `GET /api/admin/opportunity-draft/config` | `{"available": <anthropic_client.is_available()>, "model": "<WORKSHOP0_AI_NETWORK_MODEL>"}`. Never errors, and the UI uses it to show the "not configured" state before anyone pastes |
| `POST /api/admin/opportunity-draft` | Body `{"text": "…", "opportunity_id": 12\|null, "keep_partner_identity": false}` |

**POST behaviour:**
1. **Validation:** `text` is 40–20000 chars after trimming (`"text: paste between 40 and 20000 characters"`). An `opportunity_id`, if given, must exist (`"opportunity_id: no opportunity with this id"`).
2. **Rate limit:** 60/h global, bucket `opportunity_draft`. Over the limit → 429 with `Retry-After`.
3. **Call:** a synchronous call to `ai/opportunity_draft.py::run_opportunity_draft` (agent.md). It **never creates or modifies a listing.** It records one `ai_usage` row (`purpose="opportunity_draft"`, `opportunity_id` = the body's value).
4. **Errors:** unavailable → 503 `ai_not_configured`, with no I/O and no usage row. A failure → 502 `ai_draft_failed`; the usage row is still written if tokens were spent.

The response (`OpportunityDraft` = `draft`):
```json
{"data": {"draft": {"title": "GenAI & Python workshop for 30 engineers", "type": "workshop",
   "summary": "…", "description_md": "…",
   "topic_slugs": ["generative-ai", "python"], "location_mode": "hybrid", "locations": [{"city": "Pune", "country": null}],
   "starts_on": "2027-02-08", "ends_on": "2027-02-09", "duration_text": "2 days", "deadline_on": "2027-01-15",
   "compensation_min": 8000, "compensation_max": 12000, "compensation_currency": "INR", "compensation_unit": "day",
   "compensation_text": "plus travel",
   "partner_id": 3, "suggested_partner": null, "partner_display_name": "A Pune edtech",
   "internal_notes": "Contact: P. Nair, p.nair@zenvia.example, +91 98xxxxxx"},
  "drafted_fields": ["title", "type", "summary", "description_md", "topics", "location", "dates",
                     "duration_text", "deadline", "compensation", "partner", "partner_display_name", "internal_notes"],
  "cost_usd": 0.004215, "model": "claude-sonnet-5-5"}, "error": null}
```

**Response rules:**
- Every `draft` key is always present, and is null or `[]` when not drafted.
- `suggested_partner` is `{"internal_name", "display_name"}` when the post names an organisation that matches no partner (then `partner_id` is null).
- `drafted_fields` lists the keys, from the fixed set above, whose guarded value is non-empty:
  - `topics` covers `topic_slugs`;
  - `location` covers `location_mode` and `locations` (it covered `city` until Phase 11c, §Phase 11c);
  - `dates` covers `starts_on` and `ends_on`;
  - `deadline` covers `deadline_on`;
  - `compensation` covers the four structured fields and the note;
  - `partner` covers `partner_id` or `suggested_partner`.
- `cost_usd` is the recorded row's cost, a 6-dp number.

---

# Phase 11c — Multi-location opportunities (contract changes only; no new endpoint)

Normative for slices M2–M5 ([roadmap.md](roadmap.md) §Phase 11c). Schema and invariants: [data-model.md](data-model.md) §Phase 11c. Drafter: [agent.md](agent.md) §Opportunity drafter. No new router, error code, setting or environment variable.

**Location** (shared shape): `{"city": "Bengaluru", "country": "India"}`. `country` may be `null`. Serializers rebuild each item with exactly these two keys and never pass the stored JSON through.

## Request fields (POST and PATCH `/api/admin/opportunities…`; same merge semantics as Phase 10)

- **`locations`** (array of Location \| null). This is the new field, and the editor sends only this one.
  - Each item is an object with a string `city` and an optional `country` (string \| null). City and country are trimmed and internal whitespace is collapsed. A blank country becomes null.
  - Duplicates are dropped under the dedupe key in data-model.md §Phase 11c. The first occurrence wins and order is preserved.
  - `null` means `[]` (clear).
  - The list is then checked against the merged post-write state. `remote` forces `[]`, and `onsite` or `hybrid` need at least 1 entry.
- **`city`** (string \| null, **legacy**, still accepted so existing clients, fixtures and the Phase-10/11b tests keep working). It is used only when `locations` is absent from the body. If both are present, `locations` wins and `city` is ignored.
  - A non-blank value becomes `locations = [{"city": <collapsed value>, "country": null}]`. This **replaces** the whole list, including on PATCH.
  - `null` or blank becomes `locations = []`.
  - Its own bound is unchanged: `"city: must be at most 80 characters"`.

**Validation messages (exact):**

| Condition | Message |
|---|---|
| `locations` is not an array, an item is not an object, `city` is missing or not a string, or an item has a key other than `city`/`country` | `"locations: each location needs a city and an optional country"` |
| A city that is blank after trimming, or longer than 80 characters | `"locations: city must be 1–80 characters"` |
| A country longer than 80 characters, or not a string or null | `"locations: country must be at most 80 characters"` |
| More than 10 entries **after** dedupe | `"locations: at most 10 locations"` |
| Merged mode is `onsite`/`hybrid` with an empty list, and the body **contains** `locations` | `"locations: add at least one city for onsite or hybrid"` |
| Merged mode is `onsite`/`hybrid` with an empty list, and the body does **not** contain `locations` (legacy `city`, or neither field, e.g. `{"location_mode": "onsite"}`) | `"city: required for onsite or hybrid"`. This is the Phase-10 message, unchanged |

> **Assumed (legacy compatibility):** legacy `city` stays accepted on write and emitted on read indefinitely, because existing fixtures, e2e seeding and any external script use it. The required-city message depends on whether the body used `locations`, so every Phase-10 test that asserts `"city: required for onsite or hybrid"` passes unedited. The `draft` object drops `city`, because its only consumer is the editor shipped in the same change.

**Audit:** `changed_fields` reports **`locations`** for any change to the normalized list, including a reorder. It no longer reports `city`. A legacy `city` write that yields the same list as before is a no-op, with no audit row and an unchanged `updated_at`.

## Response fields

**AdminOpportunity (rows and full)** and **PublicOpportunityCard / Detail** each gain:
- `"locations": [<Location>, …]`. This is always an array (`[]` when remote), produced by the read rule (`services/locations.py::parse_stored`).
- `"city"` **stays**. It is now **derived** as `locations[0].city`, or `null` when the list is empty, so existing readers keep working. New UI code reads `locations` only.

Example (public card, the changed keys only): `"location_mode": "hybrid", "city": "Bengaluru", "locations": [{"city": "Bengaluru", "country": "India"}, {"city": "Pune", "country": null}, {"city": "Hyderabad", "country": null}]`.

`locations` is added to the explicit public allow-list. The Phase-10/11b **hard rule** is extended: no public response contains the key `locations_json`, and every Location object has exactly the keys `city` and `country`.

## Filters

Today's public board filters are `type`, `topic` and `sort` only, and the admin list filters by `status`, `type` and `q` (over title and partner names). **Neither has a city or location filter, so Phase 11c adds none.** `q` does not start matching cities. If a location filter is added later, it must match **any** listed city, case-insensitively.

## Drafting response (`POST /api/admin/opportunity-draft`)

The `draft` object replaces `"city"` with **`"locations": [<Location>, …]`** (always present, `[]` when not drafted or remote). The draft has a single consumer, the editor, so no legacy `city` key is kept there. The **`drafted_fields`** value stays **`location`**. It now covers `location_mode` and `locations` (a non-empty list), and the fixed set of values is unchanged.

---

# Phase 12 endpoints — Applications, matching, email (C14–C16)

New error codes: 409 `opportunity_closed` (apply to a non-open listing) · 409 `already_applied` · 409 `profile_required` (apply without a profile).

| Endpoint | Auth | Behaviour |
|---|---|---|
| `POST /api/me/applications` | user | `{"opportunity_id", "note"}` → `application(status="applied", source = invited if an opportunity_invite exists else self)`; email `application.received` to the trainer; rate limit 30/h/user |
| `GET /api/me/applications` | user | My applications with listing card + status + `status_changed_at`, newest first |
| `POST /api/me/applications/{id}/withdraw` | user | Only from `applied`/`shortlisted` |
| `GET /api/me/matches` | user | Top 10 effective-open listings ranked by the rule score against my profile (agent.md §Rule score) + `invited: true` flags; no LLM |
| `GET /api/admin/opportunities/{id}/applications?status&page` | admin | Pipeline rows: trainer summary + status + note + source + dates |
| `POST /api/admin/opportunities/{id}/applications/status` | admin | `{"application_ids": [...], "status": "shortlisted\|selected\|not_selected\|applied", "notify": true}` → bulk change; one audit row `application.status` listing ids; when `notify`, one `application.status_changed` email per trainer (dedupe `status:{application_id}:{status}`) |
| `GET /api/admin/opportunities/{id}/applications.csv` | admin | CSV of the pipeline |
| `GET /api/admin/network/trainers` (extended) | admin | Adds rule filters: `topic` + `min_level`, `budget_max` + `currency` + `unit` (rate_min ≤ budget_max, same currency/unit; no FX), `available_start`/`available_end` (available_from ≤ start and no blackout overlapping), `location_mode` + `city`, `verified`, `tag` |
| `POST /api/admin/opportunities/{id}/shortlist` | admin | Runs the shortlist ranker (agent.md) → `{"run_id", "ranked_by": "ai\|rules", "suggestions": [{"rank", "trainer": <row>, "rule_score", "reason"}], "cost_usd"}`; rate limit 20/h global |
| `GET /api/admin/opportunities/{id}/shortlist` | admin | Latest run |
| `POST /api/admin/opportunities/{id}/invites` | admin | `{"profile_ids": [...]}` → opportunity_invite rows + `opportunity.invite` emails (dedupe `invite:{opp}:{profile}`); audit |
| `GET /api/admin/outbox?status&page` | admin | Outbox rows + `{"smtp_configured": false}` |
| `POST /api/admin/outbox/{id}/retry` | admin | `failed` → `queued` |

The `network_invite` create endpoint now also enqueues `network.invite`; profile creation enqueues `network.welcome`. Opportunity admin payloads gain the Phase-12 budget fields (admin only) and, on admin list rows, `applicant_count` (applications not `withdrawn`) — the real value behind the Applicants column.

---

# Phase 13 endpoints — Alerts, digest, directory, workshop tie-in (C17–C19)

| Endpoint | Auth | Behaviour |
|---|---|---|
| `GET/POST /api/me/searches`, `PATCH/DELETE /api/me/searches/{id}` | user | Saved searches (≤10) |
| `GET/PATCH /api/me/email-prefs` | user | `{"alerts", "digest"}` |
| `GET /api/email/unsubscribe?t=<signed>` | signed token | One-click: turns off the named kind; 303 to `/app/network/unsubscribed/` |
| `POST /api/cron/weekly-digest` | header `X-Cron-Key` = `WORKSHOP0_CRON_KEY` | Enqueues one `network.digest` per opted-in user with ≥1 matching listing published in the last 7 days (dedupe `digest:{user}:{ISO week}`); idempotent per week |
| (internal) on any transition to effective `open` | — | Enqueue `network.alert` for each matching saved search with alerts on (dedupe `alert:{search}:{opp}`) |
| `GET /api/public/trainers?topic&page` | none | Public directory: only `visibility="public"` profiles with completeness ≥60 %; fields `{"id", "display_name", "avatar_url", "headline", "city", "remote_ok", "topics", "verified", "links"}` — **never** email, rates, CV, notes, tags |
| `GET /api/public/trainers/{id}` | none | Same allow-list + `bio_md`, `past_work`; private → 404 |
| `PATCH /api/me/profile` | user | Now accepts `visibility` |
| `GET/PUT /api/admin/workshops/{id}/facilitators` | admin | Link network trainers `{"facilitators": [{"profile_id", "role"}]}`; audit `workshop.facilitators` |
| `GET /api/me/workshops` | user | Workshops I am linked to: `{name, status, role, facilitator_url}` |

