# Capabilities — Workshop0 (v0.2)

Four core capabilities (C1–C4) carry the product; C5–C7 open it to the public in Phase 6; C8–C19 add the Trainer Network & Opportunity Board in Phases 10–13; everything else is deferred to a named phase (§Deferred). API shapes live in [api.md](api.md); schema in [data-model.md](data-model.md); phase plan in [roadmap.md](roadmap.md). This file also carries the UI specification (pages, components, states, stub placements) — there is no separate ui.md.

## Design system (applies to every page)

- Tailwind v4 design tokens in `globals.css` `@theme`: brand **indigo** (`--color-brand-*`), warm neutral scale, semantic colors (success green, warning amber, danger red, AI **violet**), one radius scale (lg cards, md controls), one shadow scale, spacing on the 4px grid. Type: Inter (via `next/font`, system fallback); body ≥16px; `text-sm` only for metadata. Light theme only (vision non-goal).
- Shared primitives in `frontend/components/ui/`: `Button` (primary/secondary/ghost/danger; loading state), `Card`, `Badge` (status pills), `ProgressBar`, `Toast`, `Modal`, `Skeleton`, `EmptyState` (icon + one-line explanation + one action), `Markdown` (react-markdown + gfm + highlight; raw HTML off), `CopyButton` (copies + "Copied" feedback), **`StubBadge`** — the labelled-stub primitive: a muted card/section with a `Coming in a later phase` pill, short description of what will live there, non-interactive. Every future feature surface renders through `StubBadge` so a stub is never mistaken for a bug.
- Every view designs all four states (empty / loading / error / populated) per `harness/patterns/ui-ux.md`. Loading = skeletons with context, never blank. Errors = human sentence + next step, never a stack trace. All interactive elements keyboard-reachable with visible focus; semantic HTML; WCAG AA contrast.
- **Connection indicator:** both live pages show a quiet "reconnecting…" pill after 2 consecutive failed polls, clearing silently on recovery. Never a modal, never data loss (state is in the DB).

---

## C1 — Workshop creation & facilitator access *(Phase 1)*

Facilitators enter once with the instance access key, then create and reach workshops via token links.

**Pages:**
- **Admin Home — `/app/`**: first visit shows a centered access-key card (one password field, "Enter"; wrong key → inline "That key doesn't match this server's `WORKSHOP0_ADMIN_KEY`"). Valid key (checked via `GET /api/admin/workshops`) is kept in `localStorage` and sent as `X-Admin-Key`. Then: workshop list grouped **Live / Upcoming / Ended** (Phase 1: everything is Live; Upcoming/Ended groups render as labelled stubs), each card showing name, participant count, open-help count, created date, buttons **Open dashboard** and **Copy join link**. Empty state: "No workshops yet — create your first." Header button **New workshop**. Stub surfaces on this page: **Template library** nav item (StubBadge, Phase 3).
- **Create workshop** (route `/app/` modal or section): name, description (markdown textarea), and a milestone builder — ordered rows of *title + markdown content editor + minutes*, add/remove/move up-down, live markdown preview per milestone (tabs Write/Preview). A **template picker** renders as a labelled stub (Phase 3). Submit → success screen presenting the two links prominently with copy buttons and a plain-language warning: *"The facilitator link is the only key to this dashboard — save it now."*

**Behavior:** `POST /api/admin/workshops`; workshop is `live` immediately; audit row written. Success criteria: create → dashboard reachable via returned `facilitator_url`; join link works; refresh of Admin Home lists the workshop with live counts.

---

## C2 — Frictionless participant identity *(Phase 1)*

Join with a name; never lose your place.

**Pages:**
- **Join — `/app/join/?s=<slug>`** (pretty link `/j/<slug>` on the door): workshop name + description (markdown), milestone count, participant count ("143 people are in"), one **name field** + **Join** button. Instant validation (1–80 chars, trimmed). If `GET /api/join/{slug}` returns `me` (cookie auto-resume), skip the form: "Welcome back, Priya" → auto-forward to the tracker. Errors: unknown slug → friendly "This workshop link isn't valid — check with your facilitator." Archived → "This workshop has ended" with a **Browse archive** link (read-only tracker).
- After join: the tracker shows a dismissible one-time callout: *"This page's link is yours — it works on any device. Save it."* with a copy button for `participant_url`.

**Identity mechanics (architecture.md §Auth):** cookie `workshop0_p_{workshop_id}` (HttpOnly, 30 d) for same-browser auto-resume; the personal link `/p/<token>` is the cross-device credential; the facilitator dashboard's participant table shows a **copy personal link** button per row — the lost-link recovery path ("what's your name? → here's your link"). Reconnect/restart restores exact state on the next poll because all state is in the DB.

**Success criteria:** join in <10 s from link tap; browser restart auto-resumes; the personal link opens the identical state on a second device; a facilitator can recover any participant's link in two clicks.

---

## C3 — Content-rich milestone tracking, live *(Phase 1)*

The heartbeat: participants work milestones; the facilitator watches the room move.

**Participant Tracker — `/app/p/?t=<token>`** (pretty `/p/<token>`):
- Sticky header: workshop name, my **progress bar** with `n / total`, connection indicator.
- **Milestone checklist**: one card per milestone in position order — checkbox + title + minutes chip + collapsible **markdown body** (instructions, links, code snippets with syntax highlighting + copy-code button). Current milestone (lowest incomplete) is auto-expanded and visually accented; completed ones collapse with a green check. **Mark complete** is optimistic (instant check, reconciled by poll); un-mark available via the checkbox ("fixed a mis-click"). Paused workshop (Phase 2) disables checkboxes with a banner — the Phase 1 payload already carries `paused`.
- **Leaderboard panel** (side on desktop, tab on mobile): the top 15 plus my own row (appended with my true rank when I am outside the top 15), full names always on, my row highlighted; top-3 subtle medals. The API caps the payload at 16 rows (see api.md).
- **Help panel**: C4 below. **Broadcast banner slot**: renders active broadcast (Phase 2 data); in Phase 1 an inline StubBadge in the panel footer notes "Announcements from your facilitator will appear here."
- Data: `state` poll 3 s (visible) / 15 s (hidden) + `content` fetch keyed by `content_version`. Loading = full-page skeleton mirroring the layout.

**Facilitator Dashboard — `/app/f/?t=<admin_token>`** (pretty `/f/<token>`), the mission-control view, 2 s poll:
- **Header**: workshop name, status pill, participant/active counts, **Copy join link**, connection indicator. Stub actions (StubBadge’d in Phase 1): **Broadcast**, **Pause**, **End workshop**, **AI toggle**, **Spend**.
- **Stat row**: participants, active (5 min), finished, median progress, open help — large-number cards.
- **Per-milestone completion**: horizontal bars per milestone (completed_count / participants, percentage), highlighting the milestone where the largest group currently sits.
- **Cohort distribution**: histogram of participants by completed-count (0…total) — the room's shape at a glance.
- **Participant table**: name, progress bar + count, per-milestone dots (done/current/todo), joined/last-seen, open-help badge, **copy personal link**. Client-side sort (progress/name/joined) and name filter. 300 rows: virtualized.
- **Help queue**: C4 below. **Proactive-intelligence rail**: stuck alerts / bottleneck / session pulse render as three labelled stub cards in Phase 1 (fields already `null` in the payload), real in Phase 2. **Audit trail** tab: StubBadge in Phase 1.

**Success criteria:** a completion on a phone is visible on the dashboard within one poll cycle (≤2 s + RTT); per-milestone bars and distribution always sum consistently with the table; 300 participants render without jank; markdown code blocks are highlighted and copyable.

---

## C4 — Help desk *(Phase 1 manual; Phase 4 adds AI in front)*

A participant raises a hand without disrupting the room; help arrives in-page.

**Participant side (tracker help panel):** "Need help?" card — one textarea ("What are you stuck on? Your facilitator sees this immediately"), submit → optimistic entry in **My help requests**: message (plain text, `pre-wrap`), status pill (`open` = amber "Waiting", `answered` = blue "Answered", `resolved` = green), timestamps. Answers render as markdown reply bubbles; a facilitator answer flashes/highlights on arrival via poll. Buttons: **Mark resolved** (own requests). Phase 4 adds: instant AI answers badged **AI** (violet) with **Get a human** escalation; Phase 1 shows no AI chrome at all (nothing to stub on the participant side — absence is the honest state).
- Empty state: "Stuck? Ask here — answers appear right on this page."

**Facilitator side (dashboard help queue):** cards newest-open-first — participant name, their current milestone chip, message (plain text), age ("4 m ago"), status pill, escalated flag (Phase 4). Inline **reply composer** (markdown textarea with preview, "Answer" button) + **Mark resolved**. Answer → participant sees it next poll; request → `answered`; stays visible until participant (or facilitator) resolves. Resolved section collapsed with count. Every answer writes an audit row. Phase 4 adds: AI draft block (violet, confidence %, editable, "Send") and the expandable **"Context the AI used"** disclosure on AI answers.
- Empty state: "No open help requests — the room is cruising."

**Success criteria:** request → visible in queue within one dashboard poll; answer → visible on tracker within one tracker poll; full loop (submit → answer → see → resolve) with zero manual refreshes; markdown answers with code render correctly; every answer audited (who/what/when).

---

## C5 — Public landing page *(Phase 6)*

The instance's front door for a stranger who has never heard of Workshop0.

**Page — `/` (also reachable at `/app/`; serving mechanism in [architecture.md](architecture.md) §Serving the landing page at `/`):** a real marketing page, not a redirect. It is the first thing a stranger sees, so it carries the same design-system bar as every other surface — same tokens, same primitives, responsive from 360px up, WCAG AA, keyboard-reachable, no layout shift.

Sections, in order:

1. **Hero** — product name + one-sentence promise + a single **primary CTA "Create your workshop — free, no signup"** → `/app/create/`, carrying `data-testid="landing-cta"` (the gate greps the served HTML for it). A secondary "See how it works" anchor-scrolls. No second competing CTA.
2. **Feature sections** — one block each, with a short honest headline and 1–2 sentences: live progress dashboard across 300+ participants · content-rich markdown/code milestones · frictionless name-only joining with cookie auto-resume and personal cross-device links · real-time help desk · broadcast / pause / advance room controls · proactive stuck-and-bottleneck alerts · audit trail · CSV export.
3. **"How it works"** — the facilitator→participant loop in numbered steps: compose milestones → share one join link → the room joins by name → watch the dashboard move → answer help in-page → export the results.
4. **"Your workshops"** — rendered **only** when the browser's `localStorage` holds entries (see C6): a list of `{name, created_at}` with **Open dashboard** and **Copy join link**, plus the line *"Remembered by this browser only — not an account. Keep your dashboard link somewhere safe."* Absent entirely on a fresh browser (no empty state, no teaser).
5. **FAQ** — the honest limits, stated plainly: no account and no login (a link is the credential) · the dashboard link is the *only* way back in — save it · clearing your browser loses the "your workshops" list but not the workshop · participants need only a browser · it is self-hosted and free · your creation email is used only so the operator can contact you, never for mail-outs.
6. **Footer** — repo/licence line. **No link to the admin console** anywhere on the page.

**Constraints (load-bearing, from architecture.md):** static server component — no router hooks, no data fetching except the client-side `localStorage` read in section 4 (which is a small `"use client"` island so the rest stays static); all outbound links are plain `<a href="/app/…">`, never `next/link`.

**Success criteria:** `GET /` returns 200 `text/html` (not 307) and renders the hero, all eight feature blocks, the how-it-works steps and the FAQ · the primary CTA navigates to `/app/create/` · CSS and fonts load (no unstyled flash — real Tailwind utilities present in the served CSS) · no "Your workshops" section on a fresh browser · no admin link present in the DOM · renders without horizontal scroll at 360px and at 1440px.

---

## C6 — Self-service workshop creation *(Phase 6)*

Anyone can create and host a workshop without ever touching an access key. **Same flow the admin already uses** — not a reduced one.

**Page — `/app/create/` (no key gate):** the identical milestone composer used by the admin console — name, description (markdown), ordered milestone rows (title + markdown editor with Write/Preview + minutes + per-milestone completion input config), add/remove/move, join-form fields. The composer is a **shared component** used by both `/app/admin/` and `/app/create/`; it is not copied.

**Final step — email, then reveal.** After the workshop is composed, the last step before anything is created asks for the creator's email: one field, inline format validation, a one-line explanation (*"So we can reach you about your workshop. We never send you mail and never share it."*), and the **Create workshop** button. Submitting calls `POST /api/public/workshops` ([api.md](api.md) §Phase 6) with the composed workshop **and** the email in one request — nothing is persisted before the email is given.

**Success screen (the reveal):** both links shown prominently with copy buttons — the **facilitator dashboard link** first, under the plain-language warning *"This link is the only key to your dashboard. Save it now — there is no account and no password reset."* — then the **join link** to share with the room. A **Open my dashboard** button goes to the facilitator dashboard. On this screen the workshop is written to the browser's `localStorage` list (C5 §4): `{name, facilitator_url, join_url, created_at}`, capped at the 20 most recent.

**Facilitator parity:** the creator lands on the normal facilitator dashboard with **every** facilitator capability — broadcast, pause, advance, reorder, edit/add/delete milestones, undo, help desk, audit tab, CSV export, settings. There is no reduced tier and no surface anywhere that behaves differently because `created_via = "public"`.

**Errors:** invalid/blank email → inline field error from `validation_error`, the composed workshop is preserved in the form (never lost) · network/500 → toast "Couldn't create your workshop — try again", form preserved.

**Success criteria:** a browser that has never sent an admin key can compose and create a workshop from `/` in one sitting · nothing is created until the email is supplied · a malformed email returns `validation_error` and creates no row · the returned facilitator link opens a dashboard with the full facilitator toolset · the join link admits a participant who then appears live on that dashboard · the created row is identical to an admin-created one apart from `creator_email` and `created_via`.

---

## C7 — Admin oversight of public workshops *(Phase 6)*

The admin keeps the only cross-workshop view, and can now see where each workshop came from.

**Page — `/app/admin/` (pretty `/admin`):** the existing Admin Home, **behaviour unchanged**, moved off `/`. The key gate, the `X-Admin-Key` handling, the grouping, the create flow and the template library all work exactly as before. Two additions to each workshop card in the list:

- an **origin badge** — `Public` (brand-tinted) or `Admin` (neutral);
- the **creator email** as metadata on public-created cards (plain text, selectable, `mailto:` link), absent on admin-created ones.

`creator_email` appears here and nowhere else — never on a facilitator, participant or public surface.

**Success criteria:** entering the key at `/admin` lists every workshop including public-created ones · a public-created workshop shows its `Public` badge and the exact email the creator entered · an admin-created workshop shows `Admin` and no email · every pre-existing admin flow still works from the new URL · `/` never exposes the admin console or its link.

---

# Trainer Network & Opportunity Board (C8–C19, Phases 10–13)

smallTech's network of freelance and in-house tech trainers — and more broadly mentors, engineers and learners — lives inside Workshop0, beside a **publicly browsable, admin-curated board of opportunities** from the partner network. Only smallTech admins post, edit and close listings; partners never touch the platform (admins forward shortlisted profiles out of band). Existing workshop/participant token-link flows are unchanged by everything in this section. Shapes: [api.md](api.md) §Phase 10–13; schema: [data-model.md](data-model.md) §Trainer Network.

**Copy rule (all network surfaces):** user-facing UI never says "AI" — drafted fields read "From your CV — please check", ranked lists read "Suggested". AI cost and token counts appear on admin surfaces only. Admin surfaces may name AI (e.g. the opportunity editor's "AI drafting not configured" state and its cost line); drafted fields there read "Drafted — please check". Opportunity `type` labels everywhere: `workshop` = **Workshop / training**, `engagement` = **Longer engagement**, `role` = **Job / contract role**, `cofacilitation` = **Workshop0 co-facilitator / TA**.

---

## C8 — Topic taxonomy *(Phase 10)*

A curated list of tech topics that listings (and, from Phase 11, trainer profiles) are tagged with, so filtering and matching speak one vocabulary.

- Ships with **40 seeded topics in 5 categories** (data-model.md §topic).
- **Admin Topics page — `/app/admin/topics/`**: table of all topics grouped by category (name, slug, active toggle, number of listings using it); an **Add topic** row (name + category, category input suggests existing categories); inline rename. Deactivating asks for confirmation and explains: "Hidden from filters and pickers; listings already tagged keep it." Slugs are shown read-only.
- Public filters list active topics only, grouped by category, with the number of open listings each (0 → shown muted).

**Success criteria:** a fresh database exposes exactly 40 active topics through the public topics endpoint · an admin-added topic appears in the public filter list immediately (with count 0) · a duplicate name (any case) is rejected with `topic_exists` and creates nothing · a deactivated topic disappears from public filters and from the editor's picker but still renders on a listing already tagged with it · every create/rename/toggle writes an audit row.

---

## C9 — Opportunity management for admins *(Phase 10; partners, paste-to-fill and compensation in Phase 11b; multiple locations in Phase 11c)*

Admins create, edit, publish and close listings; listings auto-expire at their deadline.

**Pages (same key gate as Admin Home; Admin Home's header gains a real **Opportunities** link and a **Trainer network** labelled stub):**
- **Opportunities — `/app/admin/opportunities/`**: status tabs **All · Draft · Open · Expired · Closed** with counts; search box (title / partner names); table rows: title, type pill, public partner name with the internal partner name beneath in muted text and a lock icon, topics (≤3 + "+n"), deadline (relative: "in 5 days" / "expired 2 days ago"), status pill, updated. Row click → editor. Header button **+ New opportunity**. Empty state: "No opportunities yet — post the first one." Paginated (25). Labelled stubs on this page: **Applicants** column and **Suggested trainers** action (Phase 12), **Trainer pool** nav (Phase 11), **Outbox** nav (Phase 12).
- **Editor — `/app/admin/opportunities/edit/?id=<id>`** (no `id` = new): two clearly separated groups.
  - **Public details** — title, type, summary (280 counter), description (markdown Write/Preview tabs, the existing Markdown primitive), topics (searchable multi-select grouped by category, max 8, active topics only), location mode (Remote / Onsite / Hybrid; city appears and is required for Onsite/Hybrid. From Phase 11c this is a multi-city chips input, §C9 additions — Phase 11c), start/end dates, duration, compensation (public text), **deadline** (date + time in the admin's local time zone, shown with its UTC equivalent; defaults to 30 days out at 23:59), **public partner name** (placeholder "smallTech partner network").
  - **Internal — only admins see this** (tinted panel with a lock icon) — internal partner name, internal notes.
  - A live **public card preview** renders exactly what the board will show (proving the internal fields are absent).
  - Actions by state: draft → **Save draft** / **Publish**; open → **Save** / **Close** / **Unpublish**; expired → banner "Expired — extend the deadline to reopen" + **Save** / **Close**; closed → **Reopen** (requires a future deadline) / **Save**. Field errors from `validation_error` render inline on the named field; nothing typed is ever lost on error. After save: toast + the status pill updates; **Copy public link** (the pretty `/opportunities/<id>` URL) is shown once the listing has been published.
  - **Activity** list at the bottom: the listing's audit rows (who / what / when).

**Success criteria:** create as draft → not visible publicly; publish → visible on the board within one page load · internal partner name and internal notes never appear on any public page or public API response · publishing with a past deadline is rejected inline · a listing whose deadline passes shows **Expired** in admin and disappears from the board without any action · close → gone from the board, detail page shows the closed banner · every create / update / publish / unpublish / close writes exactly one audit row visible in Activity.

### C9 additions — Phase 11b (Phase-10 feedback)

**Partners, a managed list.** **Partners — `/app/admin/partners/`** works like the Topics page.
- **Columns:** the table shows internal name (with a lock icon), default public name, notes (truncated, admin-only), number of listings and an active toggle.
- **Add partner** row: internal name (required), default public name (optional, placeholder "smallTech partner network"), notes.
- **Editing:** inline rename and edit. Deactivating asks for confirmation: "Hidden from the partner picker; listings already using it keep it."
- **Entry points:** linked from the editor's partner field (**Manage partners**) and from the admin header (**Partners**).
- **Migration:** existing free-text partner names are migrated in. One partner is created per distinct name, ignoring case and extra spaces, and every existing listing is linked to it.

**Editor changes:**
- **Partner (internal panel):** the free-text internal partner field becomes a **partner dropdown**. It is searchable, lists active partners with their default public name muted, has a **None** option, and an inline **+ Add partner** that opens a small form (internal name, default public name, notes) and selects the new partner.
- **Public partner name:** choosing a partner fills the listing's **public partner name** with the partner's default public name when that field is empty. The public partner name stays per listing and remains the **only** partner text ever shown publicly.
- **Compensation (public details):** amount **min** and **max** (one is enough; equal means a single value), **currency** (INR / USD), **unit** (per hour / per day / per course / per month), and an optional **note** (the former compensation text, e.g. "plus travel", "Pro bono"). Currency and unit are required once an amount is entered. Errors show inline.
- **Paste the forwarded description** box, at the top of a new listing and collapsed under **Draft from a forwarded description** on an existing one:
  1. The admin pastes the partner's email or post, optionally ticks **Keep the partner's name in the public text**, and clicks **Draft**. A skeleton shows while drafting (up to ~20 s).
  2. The form is pre-filled for review: title, type, summary, a **cleaned public description**, topics (**only from the curated list**), Remote / Hybrid / Onsite and the cities (every city the post names as a venue, from Phase 11c), start/end dates, duration, deadline, compensation with unit and note, the partner, the public partner name and internal notes.
     - The **partner** is either matched against the partner list or offered as "Suggested new partner: *name* — **Add**".
     - The cleaned description has the partner's identity removed (unless kept), and its contacts, emails and phone numbers moved into the internal notes.
  3. Every filled field carries an amber **"Drafted — please check"** chip, which disappears once that field is edited.
  4. **Nothing is saved or published by drafting.** The admin still clicks Save draft / Publish.
  5. A small cost line under the box reads "Drafted with claude-sonnet-5-5 · $0.0042". This is an admin surface, so naming AI and showing cost is allowed. Spend also appears in the Network AI spend card.
  6. If typed input would be overwritten, a confirm asks first.
- **Not configured:** when drafting is unavailable (no Anthropic key, or no workspace id), the box shows a neutral **"AI drafting not configured"** state with the Draft button disabled. The rest of the editor works exactly as before.
- **Failure:** a failed draft shows "Drafting failed — fill the form by hand or try again", and nothing typed is lost.

**Success criteria (11b):**
- **Migration:** on migration, N distinct free-text partner names (ignoring case and whitespace) become exactly N partners, and every named listing is linked to one.
- **Partner uniqueness:** a duplicate partner name in any case or spacing is rejected with `partner_exists` and creates nothing.
- **Deactivation:** a deactivated partner is absent from the dropdown but still shown on a listing already using it.
- **No leak:** partner internal names, partner notes and internal notes never appear in any public page or public API response.
- **Drafting the three ordinary fixture posts** against the real model:
  - fills the expected type, location, topics and compensation unit;
  - picks topics only from the curated list;
  - matches the seeded partner when the post names it, and otherwise suggests a new one;
  - leaves no partner name, email or phone in the public fields;
  - creates no listing.
- **Prompt injection:** a post containing instructions ("ignore previous instructions…") yields only curated topics and enum values, and creates no listing.
- **Usage record:** each draft writes one usage record with purpose `opportunity_draft`, the model id and a cost > 0.
- **Graceful degradation:** with drafting unavailable, the box shows "AI drafting not configured", no AI call is made, and a listing can still be created and published by hand.
- **Compensation validation:** an amount without currency or unit, or `max < min`, is rejected inline.

### C9 additions — Phase 11c (multi-location listings)

A listing can name **one or more locations**. Each location is a city with an optional country. The work mode (Remote / Onsite / Hybrid) is unchanged. Rules and storage: data-model.md §Phase 11c. Contract: api.md §Phase 11c.

**Editor — Locations (replaces the single City field).** It appears only for Onsite or Hybrid, in the same place the City field was. It is a chips input:
- a **City** text input and a narrower **Country (optional)** text input, plus an **Add** button;
- **Enter** in the City input, or clicking **Add**, adds a chip from the two inputs and clears both. If the City text contains commas, each comma-separated part becomes its own chip;
- **typing or pasting a comma** adds every part before the last comma as a chip, each with the current Country value, and clears the Country input. The text after the last comma stays in the City input. So `Pune,` adds `Pune`, and pasting `Hyderabad, pune` adds `Hyderabad` and leaves `pune` to be added with Enter;
- leaving the City input (blur) with text still in it adds that chip too, so a typed but un-added city is never silently lost on Save;
- each chip reads `City` or `City, Country` and has a **×** remove button with `aria-label="Remove <City>"`;
- chip order is the order added.

The chips input behaves as follows:
- **Duplicates:** adding a city that is already a chip, ignoring case and extra spaces with the same country, adds nothing and shows a muted hint "Already added" for about 2 s.
- **Limits:** with 10 chips, the City input is disabled and shows "Up to 10 locations". A city over 80 characters, or a country over 80, shows the inline error "City must be 80 characters or fewer" or "Country must be 80 characters or fewer", and is not added.
- **Server errors:** a `validation_error` on `locations:` or on the legacy `city:` renders inline under the chips input. For example, saving Onsite with no chips shows the server's "add at least one city for onsite or hybrid" (or "required for onsite or hybrid").
- **Switching to Remote** hides the chips but keeps them in the form. They are sent as `[]` while Remote, and switching back restores them.
- **Paste-to-fill:** drafting fills the chips with every drafted city, and the "Drafted — please check" chip on Location covers the mode and the cities. Removing or adding a chip counts as editing the field and clears the drafted chip.
- **Public card preview:** it uses the same location rule as the board card (C10).

**Success criteria (11c):**
- **Migration:** a listing saved with one city before 11c shows that city as its only location after migration. A downgrade restores `city` to the first location's city.
- **Multiple cities:** a listing saved with Bengaluru (India), Pune and Hyderabad returns them in that order, with `city = "Bengaluru"`.
- **Dedupe:** `" pune "` after `Pune` is dropped on save.
- **Limits:** 11 distinct cities are rejected with `locations: at most 10 locations`.
- **Required for onsite and hybrid:** Onsite or Hybrid with no city is rejected inline. Remote saves with no city and returns `locations: []`.
- **Legacy clients:** a write with only the legacy `city` stores exactly one location, and existing clients keep getting `city`.
- **Drafting:** a post naming three venue cities drafts all three, and cities that are only remote participants, the head office or a signature address are not drafted (agent.md fixtures).

---

## C10 — Public opportunity board *(Phase 10; compensation display Phase 11b; multi-location display Phase 11c)*

Anyone on the internet can browse what's open; applying arrives with sign-in (Phase 11–12).

**Pages (no auth; linked from the landing page footer as "Opportunities for trainers"; pretty URL `/opportunities`):**
- **Board — `/app/opportunities/`**: header strip "Opportunities from the smallTech partner network" + one-line subline; **Join our network** CTA (labelled stub in Phase 10 — real in Phase 11). Filter bar: **type** segmented chips (All + the four types), **topic** chips grouped by category with open counts (multi-select = match any), **sort** (Newest / Closing soon). Filter state lives in the URL query (`?type=&topic=&topic=&sort=&page=`) so filtered views are shareable and survive reload. **Cards** (responsive grid): type pill, title, partner display name (or "smallTech partner network"), summary, topic chips (≤4 + "+n"), location (Remote / City · Onsite / City · Hybrid; several cities per the Phase-11c rule below), compensation when present (display rule below; from Phase 11b), **"Apply by 30 Nov"** with an amber "Closes in 3 days" pill when ≤7 days remain. **Pagination**: Previous / Next + "Page 2 of 3", 12 per page. States: loading = skeleton cards; no listings at all = "No open opportunities right now — check back soon."; filters match nothing = "Nothing matches these filters" + **Clear filters**; error = human sentence + Retry.
- **Listing — `/app/opportunities/view/?id=<id>`** (pretty `/opportunities/<id>`): back link to the board (preserving filters when arriving from it), title, type pill, partner display name, meta grid (location, dates, duration, compensation, deadline in the viewer's local time), topic chips, rendered markdown description. Side card: when open — "Applications open until …" + **Sign in to apply** (labelled stub in Phase 10; real in Phase 12) + **Copy link**; when expired or closed — a neutral banner "Applications for this opportunity have closed." and no apply control. A **Join our network** stub card ("Get matched to opportunities like this — coming soon"). Draft/unknown id → friendly not-found state "This opportunity isn't available — it may have been removed." + link to the board. The browser tab title is the listing title.
- **Landing page:** one plain link "Opportunities for trainers" in the footer (no other landing change; still no admin link).
- **Compensation display (Phase 11b; the one rule for card, listing and admin preview):** the amount part uses the currency symbol (INR `₹`, en-IN digit grouping; USD `$`, en-US grouping), then ` / ` and the unit (`hour`, `day`, `course`, `month`). The note is appended after ` · `.
  - **Amount forms:**
    - min < max → `₹8,000–12,000 / day` (en dash, one symbol);
    - min = max → `₹20,000 / course`;
    - min only → `From $50 / hour`;
    - max only → `Up to ₹1,50,000 / month`.
  - **Note:**
    - amount + note → `₹20,000 / course · plus travel`;
    - note only, e.g. legacy text → `Pro bono`;
    - neither → no compensation line.

  There is no compensation filter on the board.
- **Location display (Phase 11c; one formatter, `frontend/lib/locations.ts`, used by the card, the listing page and the admin preview).** `Mode` is `Onsite` or `Hybrid`. Separators are ` · ` (space, middle dot U+00B7, space).
  - **Card and admin preview (`locationLabel`):**
    - remote → `Remote`, unchanged; any cities are ignored;
    - 0 cities (onsite/hybrid; only reachable through the read-rule edge) → `Onsite` / `Hybrid`, unchanged;
    - 1 city → `Bengaluru · Hybrid`, unchanged;
    - 2 cities → `Bengaluru · Pune · Hybrid`;
    - 3 or more → the first two, then `+N` for the rest: `Bengaluru · Pune · +1 · Hybrid`, `Bengaluru · Pune · +3 · Onsite`.
    - Countries are never shown on the card. The card's location element carries `title` = every city joined with `, ` (e.g. `Bengaluru, Pune, Hyderabad`), so the hidden cities can be read on hover.
  - **Listing page (`locationDetailLabel`):** every location in order, each as `City` or `City, Country`, then the mode, for example `Bengaluru, India · Pune · Hyderabad · Hybrid`. Remote → `Remote`.
  - There is **no location filter** on the board, before or after 11c (api.md §Phase 11c → Filters).
  - **Success (11c):** the exact strings above render on the card and the listing page for 1, 2, 4 and 5 cities and for remote, and in the preview for 2 and 3 cities and for remote (e2e). Public payloads carry `locations` items with only `city` and `country`.

**Success criteria:** the board lists only open, non-expired listings · with 30 open listings, three pages of 12/12/6 with no duplicates and no gaps · type and topic filters return exactly the matching set and persist in the URL across reload · a closed or expired listing's detail URL still renders with the closed banner · a draft's URL renders not-found · the rendered HTML of board and listing pages never contains the internal partner name · works at 360 px and 1440 px with no horizontal scroll · every stub (Join our network, Sign in to apply) carries the "Coming in a later phase" pill and is non-interactive.

---

## C11 — Network sign-in & accounts *(Phase 11)*

Near-zero-friction, self-serve identity for the network; Google sign-in only at launch.

- **Sign in — `/app/signin/`** (and wherever a sign-in is needed): one **Continue with Google** button; error banners per callback error code (e.g. "That Google account's email isn't verified"). If sign-in isn't configured on the server: a labelled, non-error state. A small header **account menu** on network pages: avatar, name, "My profile", "Sign out".
- **Admins as users:** an email on the admin allowlist who signs in is an admin; the admin console's key gate gains **Continue with Google** beside the key field. The access key keeps working exactly as before. Admin actions are attributed to the admin's email (or "admin key").
- **Invite links — `/invite/<token>`**: an admin creates an invite for an email (Phase 11: copy the link; Phase 12: emailed). The invitee signs in with that same email and lands in onboarding already **Verified**. Wrong account → "This invite was sent to as***@example.com — sign in with that Google account." Expired → "This invite has expired — ask smallTech for a new one."
- **Consent** at signup (required checkbox): "smallTech may share my profile with partner organisations for matching." The date and wording version are recorded.
- **Delete my account** (profile page, danger zone): type your email to confirm → profile, CV and account are removed immediately; signed out; confirmation screen.

**Success criteria:** first-time sign-in creates exactly one account; a second sign-in reuses it · an unverified-email ID token is refused · an allowlisted email sees the admin console without the key; removing it from the allowlist revokes access on the next request · invite + matching email → verified profile; mismatching email → refused and no profile verified · deletion removes the user, profile, CV blob and sessions (asserted in the DB and storage) and leaves an audit row with only a masked email · existing workshop/participant flows work unchanged and need no sign-in.

---

## C12 — CV-drafted trainer profile *(Phase 11)*

Sign in, drop a CV, review one screen, you're in.

- **Onboarding — `/app/network/join/`** (step 1 of 2): three ways in, as tabs — **Upload CV** (PDF/DOCX ≤5 MB, drag-and-drop), **LinkedIn PDF** (a short how-to: LinkedIn profile → More → Save to PDF, then upload it here), **Paste text** (CV or LinkedIn "About/Experience" text). A one-line note: "We can't read LinkedIn links directly — LinkedIn doesn't allow it." After submit: "Reading your CV…" skeleton (≤60 s), then step 2.
- **Review — step 2**: one screen, everything editable, pre-filled where possible; every pre-filled field shows a small amber chip **"From your CV — please check"**. Sections: headline, bio, topics (from the curated list, each with a level: Intermediate / Advanced / Expert), location (city + remote OK), links (LinkedIn / GitHub / website), past workshops & talks, rate range + currency (INR / USD) + per hour / per day / per course / per month + "open to pro-bono" (labelled "Visible to smallTech only"), availability (weekly day-part grid Mon–Sun × Morning / Afternoon / Evening, available-from date, blackout date ranges). Only headline and ≥1 topic are required. Consent checkbox. **Create my profile** → profile is live → My profile. If pre-fill wasn't possible the form starts empty with "We couldn't pre-fill from your CV — fill in the basics below; you can add the rest later."
- **My profile — `/app/network/me/`**: view/edit every field, replace CV, **completeness meter** (0–100 %, the ten checks in api.md) with a nudge listing the top 3 missing items, verified badge when granted, danger zone. Labelled stubs: **My applications** (Phase 12), **Matched for you** (Phase 12), **Saved searches & alerts** (Phase 13), **Public directory profile** toggle (Phase 13).
- Board: **Join our network** CTA becomes real (→ sign-in → onboarding); "Sign in to apply" stays a labelled stub until Phase 12.

**Success criteria:** a real multi-page PDF CV and a DOCX CV each produce a draft whose topics are only curated slugs with valid levels, and whose headline is non-empty · pasted text works identically · a scanned (image-only) PDF returns `cv_unreadable` with the paste-text suggestion · with drafting unavailable the review screen still works and the profile can be created · the review screen marks exactly the drafted fields · completeness matches the ten-check formula · rates never appear on any non-admin surface other than the owner's own profile.

---

## C13 — Admin trainer pool *(Phase 11)*

- **Trainer pool — `/app/admin/network/`**: search box, topic filter (any), verified filter, tag filter; table (25/page): name + avatar, headline, top topics with levels, city / remote, rate (admin only), verified badge, completeness %, tags, joined. **Export CSV** (current filters). **Invites** panel: create invite (email + optional name) → copyable link; list with status (pending / accepted / expired). **Network AI spend** card (total cost, calls, tokens).
- **Trainer detail — `/app/admin/network/trainer/?id=<id>`**: full profile, **Download CV**, **Verify / Unverify**, tags editor, private notes (append-only list with author + time), drafting cost for this trainer, activity (audit).
- Labelled stubs: rule-based matching filters (level, budget, availability, location) and **Suggested for a listing** (Phase 12); **Email invite** (Phase 12).

**Success criteria:** with 60 seeded profiles the search, topic and verified filters return exactly the precomputed sets across pages · CV download works on both the local and cloud storage backends and writes an audit row · verify / notes / tags each write an audit row · the CSV row count equals the filtered total.

---

## C14 — Apply & applicant pipeline *(Phase 12)*

- Listing page: **Apply** (signed-in with a profile) → optional note (≤1000) → **Send application** — one click. Signed out → sign-in → back to the listing. Signed in without a profile → onboarding (CV autofill) → back to the listing with the apply panel open. Already applied → status chip instead of the button.
- **My applications — `/app/network/applications/`**: one row per application with a status timeline **Applied → Shortlisted → Selected / Not selected** (and Withdrawn), listing link, withdraw while Applied/Shortlisted.
- **Admin pipeline — `/app/admin/opportunities/pipeline/?id=<id>`**: applicants grouped by status (Applied / Shortlisted / Selected / Not selected / Withdrawn) with trainer summary, note, source (self / invited), CV link; multi-select → **Move to…** with "Email the trainers about this change" (on by default); **Export CSV**. The Applicants column in the opportunities table becomes real counts.

**Success criteria:** one application per trainer per listing (second attempt → `already_applied`) · applying to an expired/closed listing → `opportunity_closed` · a bulk move of 12 applicants writes one audit row and enqueues exactly 12 emails (one per trainer, deduplicated on retry) · the trainer sees the new status on their next page load.

## C15 — Matching *(Phase 12)*

- **Rule filters** on the trainer pool: topic + minimum level, budget (max rate, same currency and unit), available for a date range (available-from and blackouts), location mode / city, verified, tag.
- **Suggested trainers** for a listing (button on the editor and pipeline): ranks the eligible pool and shows the top 10 with a one-sentence reason each, rule score, and the run's cost (admin only); **Invite to apply** (single or bulk) → the trainer gets an email and an "Invited" badge on the listing and in Matched for you.
- **Matched for you — `/app/network/matches/`**: up to 10 open listings ranked against the trainer's profile (topic overlap weighted by level, availability vs listing dates, location fit), invited ones first.

**Success criteria:** over a 60-profile fixture the rule filters return exactly the precomputed eligible set · every suggestion comes from the eligible set, ≤10, each with a non-empty reason; the fixture's single obvious best match ranks in the top 3 · without drafting/ranking available, suggestions fall back to rule order labelled "Ranked by rules" with zero errors.

## C16 — Email outbox & notifications *(Phase 12)*

- Emails: **network invite**, **welcome** (profile created), **application received**, **application status changed**, **invited to apply** (Phase 13 adds alerts and the weekly digest). Plain, branded, every link absolute to the public domain.
- Every email is written to the **outbox** first. With SMTP configured it is sent (retried up to 3 times); without SMTP it is **recorded** and the admin **Outbox — `/app/admin/outbox/`** page shows a prominent label "Email sending isn't configured — messages are recorded here, not sent." Outbox table: to, template, subject, status, attempts, last error, time; **Retry** on failed.

**Success criteria:** with SMTP unset no request fails and every email lands as `recorded` · with a real SMTP server configured, queued mail is delivered and marked `sent` · a duplicate enqueue with the same dedupe key creates no second row.

## C17 — Saved searches, alerts & weekly digest *(Phase 13)*

Trainers save board filters (type / topics / location) as named searches with alerts on/off; a newly opened matching listing triggers one alert email per search; a weekly digest (Monday 09:00 IST) summarises new matching listings. Email preferences page with per-kind toggles; every alert/digest email carries a one-click unsubscribe. **Success:** publishing one listing that matches 3 of 5 saved searches enqueues exactly 3 alerts; re-publishing enqueues none; the digest run twice in one week sends once.

## C18 — Public trainer directory & visibility *(Phase 13)*

Profiles are private to admins by default; a trainer may opt in to a public directory profile. **Directory — `/app/network/directory/`** (topic filter, verified badge) and **public profile — `/app/network/trainer/?id=<id>`** show name, photo, headline, topics + levels, city / remote, links, bio, past work. **Never** shown publicly: email, rates, CV, admin notes, tags. **Success:** a private profile 404s publicly; public payloads contain only the allow-listed fields (asserted on serialized JSON).

## C19 — Workshop tie-in *(Phase 13)*

Admins link network trainers to a Workshop0 workshop as lead / co-facilitator / TA (Admin Home workshop card → **Facilitators**); a linked trainer sees **My Workshop0 workshops** with the facilitator dashboard link. A `cofacilitation` listing may name its workshop; marking an applicant **Selected** offers "Link as facilitator". A **Join our network** card appears on the participant join page and on the tracker once all milestones are complete. **Success:** linking writes an audit row and shows on the trainer's page; unlinking removes access to the link from their page (the facilitator token itself is unchanged); participant pages remain account-free.

---

## Deferred capabilities (schema exists from Phase 1; features arrive at their phase)

| Capability | Phase | One-line scope |
|---|---|---|
| Broadcast announcements | 2 | Markdown composer → pinned participant banner; history; clear; undoable |
| Milestone controls | 2 | Advance all/selected, pause/resume, reorder, edit/add/delete milestones mid-session |
| Undo | 2 | 30 s inverse-operation window for advance-all/selected, pause, broadcast |
| Audit trail UI | 2 | Dashboard tab over `facilitator_action` (every facilitator + AI action, who/what/when) |
| Proactive intelligence | 2 | Stuck-participant alerts (`stuck_minutes`), bottleneck detection, session pulse (pace vs plan, % on track, projected finish) |
| Lifecycle: end / grace / archive | 3 | End workshop → straggler grace window → read-only archive, browsable forever; lazy transitions |
| Clone / re-run | 3 | New workshop from an old one: milestones copied, fresh tokens, zero participants |
| Agenda template library | 3 | CRUD + create-from-template + save-workshop-as-template; instantiation snapshots |
| Join-form templates & custom fields | 3 | Extra join fields (text/dropdown) from persistent form templates; answers on the participant record |
| Admin Home lifecycle grouping | 3 | Live / Upcoming / Ended real; `starts_at` scheduling; archive browsing |
| AI triage & auto-answer | 4 | Context-gathering → confidence-routed auto-answer/draft (see [agent.md](agent.md)) |
| AI escalation & transparency | 4 | "Get a human" one-tap; AI badge; expandable exact-context view in the queue |
| Cross-workshop learning corpus | 4 | FTS5 similarity over all past resolutions — replaces canned replies, improves with use |
| AI spend & toggle & air-gap | 4 | Per-workshop cost from OpenRouter usage; per-workshop enable; keyless = zero AI chrome errors |
| Docker Compose packaging | 5 | One-container deploy, volume-backed SQLite, multi-stage build (local dev from Phase 7) |
| CI/CD to GCP (VM) | 5 → removed 8 | GitHub Actions: tests on PR; image build + VM deploy on main; runbook. Superseded by the Cloud Run pipeline |
| Stateless multi-instance serving | 7 | PostgreSQL storage; no in-process cache; `last_seen_at` throttle is a DB-side conditional UPDATE (≤1 effective touch per participant per 60 s across all instances); snapshots built per changed poll |
| Cloud Run + Cloud SQL production deploy | 7 | WIF-authenticated GitHub Actions → Artifact Registry → migrate job → no-traffic revision → health check → traffic shift with rollback guard; idempotent `provision.sh`; scale-to-zero with a workshop-mode (`gcloud run services update --min-instances`) toggle |
| Production cutover | 8 | SQLite → PostgreSQL data import with per-table verification, `workshop0.smalltech.in` domain mapping, VM path retired, rewritten runbook |

Phases 7–8 change **no user-visible behaviour**: every capability above behaves identically; the only observable differences are a cold-start delay on the first request after idle (unless workshop mode is on) and the production URL.
