import {
  test,
  expect,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Locator,
  type Page,
} from '@playwright/test';
import {
  ADMIN_BASE,
  APP_BASE,
  ORIGIN,
  adminKey,
  fillStable,
  signInAdmin,
  waitForHydration,
} from './helpers';

/**
 * Phase 10 — Opportunity Board (roadmap.md §Phase 10 "e2e journey (S4)",
 * capabilities.md C8–C10, api.md §Phase 10).
 *
 * An admin posts a real listing (public details + an internal partner name and
 * note that must never leak), saves it as a draft (invisible publicly),
 * publishes it, a stranger browses / filters / opens it on the public board,
 * the admin closes it (closed banner, off the board), a past-deadline publish
 * is refused inline, a topic is added (duplicate in another case refused) and
 * appears muted on the board, and 13 listings for a fresh topic paginate 12/1.
 *
 * The e2e database is NOT reset between runs: every name carries RUN, a
 * letters-only per-run suffix (letters only so a topic chip's open count is the
 * only digit in its text). Every public view is a FRESH browser context that
 * never sends X-Admin-Key. Waits are polling assertions — no fixed sleeps.
 */

const RUN = `r${Date.now()
  .toString(36)
  .replace(/\d/g, (d) => 'abcdefghij'[Number(d)])}`;

const TITLE = `E2E GenAI workshop ${RUN}`;
const SUMMARY = `Hands-on LLM workshop for product teams (${RUN}).`;
const PUBLIC_PARTNER = 'A Bengaluru fintech';
const INTERNAL_PARTNER = `ZZ-INTERNAL-PARTNER-${RUN}`;
const INTERNAL_NOTE = `ZZ-INTERNAL-NOTE-${RUN} contact R. Rao`;
// Phase 11b: the partner now lives in the Partners directory; its notes are
// admin-only too and must never reach any public surface.
const PARTNER_NOTE = `ZZ-PARTNER-NOTE-${RUN}`;
const LEAK_MARKERS = ['ZZ-INTERNAL', 'ZZ-PARTNER-NOTE'];
const CITY = 'Bengaluru';
const LIST_ITEM = 'Retrieval-augmented generation';
const CODE_LINE = 'def greet(name: str) -> str:';
const DESCRIPTION = [
  'Two days, hands-on. We will cover:',
  '',
  '- Prompt design basics',
  `- ${LIST_ITEM}`,
  '- Shipping an eval harness',
  '',
  '```python',
  CODE_LINE,
  '    return f"hello {name}"',
  '```',
].join('\n');

const PAST_TITLE = `E2E Past deadline ${RUN}`;

const ELIXIR_NAME = `Elixir ${RUN}`;
const ELIXIR_SLUG = `elixir-${RUN}`;

const PAGING_TOPIC_NAME = `E2E Paging ${RUN}`;
const PAGING_LISTINGS = 13;

const BOARD_URL = `${APP_BASE}/opportunities/`;
const ADMIN_OPPS_URL = `${ADMIN_BASE}/opportunities/`;

const errors: string[] = [];

let api: APIRequestContext;
let adminCtx: BrowserContext;
let admin: Page;

let opportunityId = 0;
let pagingTopicId = 0;
let pagingTopicSlug = '';
const pagingListingIds: number[] = [];
const extraListingIds: number[] = [];
const partnerIds: number[] = [];

const REOPEN_TITLE = `E2E Close reopen ${RUN}`;
const PLAIN_REOPEN_TITLE = `E2E Plain reopen ${RUN}`;
const STEP5_TITLE = `E2E Step five ${RUN}`;
const KEEP_EDIT_TITLE = `E2E Keep edit ${RUN}`;
const KEEP_EDIT_SUMMARY = `Unsent summary edit kept across Close (${RUN}).`;

// ---------------------------------------------------------------- helpers

function isoDaysFromNow(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/** A fresh, keyless browser context for a public view (optionally narrow). */
async function publicPage(
  browser: Browser,
  label: string,
  viewport?: { width: number; height: number },
): Promise<{ ctx: BrowserContext; page: Page }> {
  const ctx = await browser.newContext(viewport ? { viewport } : {});
  ctx.setDefaultTimeout(15_000);
  ctx.setDefaultNavigationTimeout(30_000);
  ctx.on('request', (req) => {
    if (req.headers()['x-admin-key'] !== undefined) {
      errors.push(`${label}: public context sent X-Admin-Key to ${req.url()}`);
    }
  });
  const page = await ctx.newPage();
  page.on('pageerror', (err) => errors.push(`${label}: ${String(err)}`));
  return { ctx, page };
}

/** Board finished loading: a card or the (empty / no-match) state is shown. */
async function waitForBoard(page: Page): Promise<void> {
  await expect(page.getByTestId('board-page')).toBeVisible();
  await expect(
    page.locator('[data-testid="opportunity-card"], [data-testid="board-empty"]').first(),
  ).toBeVisible();
}

function card(page: Page, title: string): Locator {
  return page.getByTestId('opportunity-card').filter({ hasText: title });
}

/** Click a filter chip and wait until the URL reflects it (retry pre-hydration). */
async function clickUntilUrl(page: Page, chip: Locator, urlPattern: RegExp): Promise<void> {
  await waitForHydration(chip);
  await expect(async () => {
    // Only (re-)click while the URL does not reflect the chip yet: a chip that
    // already toggled must not be clicked again (that would toggle it off).
    if (!urlPattern.test(page.url())) await chip.click();
    await expect(page).toHaveURL(urlPattern, { timeout: 2_000 });
  }).toPass({ timeout: 15_000 });
}

/** Pick a value in a `<select>` or a segmented control carrying the test id. */
async function choose(control: Locator, value: string, label: string): Promise<void> {
  await waitForHydration(control);
  const tag = await control.evaluate((el) => el.tagName);
  if (tag === 'SELECT') {
    await control.selectOption(value);
    await expect(control).toHaveValue(value);
    return;
  }
  const option = control
    .getByRole('radio', { name: label })
    .or(control.getByRole('button', { name: label }))
    .or(control.getByText(label, { exact: true }))
    .first();
  await option.click();
}

/**
 * Tick a topic in the editor picker. The picker renders every active topic as a
 * visible `<label>` checkbox; if the option is not on screen, narrow the list
 * with the picker's OWN search box (scoped by its accessible name, so it can
 * never match another control such as opp-type-select).
 */
async function pickTopic(page: Page, slug: string, searchText: string): Promise<void> {
  const option = page.getByTestId(`opp-topic-option-${slug}`);
  if (!(await option.isVisible().catch(() => false))) {
    const search = page.getByRole('searchbox', { name: 'Search topics' });
    if (await search.isVisible().catch(() => false)) {
      await fillStable(search, searchText);
    }
  }
  await expect(option).toBeVisible();
  const checkbox = option.getByRole('checkbox');
  await waitForHydration(checkbox);
  await expect(async () => {
    if (!(await checkbox.isChecked())) await option.click();
    await expect(checkbox).toBeChecked({ timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
}

/** Local (browser = runner machine) date + time parts of `d`, zero-padded. */
function localParts(d: Date): { date: string; time: string } {
  const p = (n: number) => String(n).padStart(2, '0');
  return {
    date: `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`,
    time: `${p(d.getHours())}:${p(d.getMinutes())}`,
  };
}

/** Fill the editor's deadline input `daysFromNow` days out, whatever its input type. */
async function fillDeadline(page: Page, daysFromNow: number): Promise<void> {
  const input = page.getByTestId('opp-deadline-input');
  await waitForHydration(input);
  const { date } = localParts(new Date(Date.now() + daysFromNow * 86_400_000));
  const type = (await input.getAttribute('type')) ?? 'text';
  const value = type === 'date' ? date : `${date}T23:59`;
  await fillStable(input, value);
}

/** Fill the deadline input with an exact local moment (datetime-local input). */
async function fillDeadlineAt(page: Page, at: Date): Promise<string> {
  const input = page.getByTestId('opp-deadline-input');
  await waitForHydration(input);
  const { date, time } = localParts(at);
  const type = (await input.getAttribute('type')) ?? 'text';
  const value = type === 'date' ? date : `${date}T${time}`;
  await fillStable(input, value);
  return value;
}

/** Create an OPEN listing through the admin API; returns its id. */
async function createOpenListing(title: string, deadlineDays: number): Promise<number> {
  // Tag with the seeded `python` topic (never the paging topic — its 13-card
  // count is asserted below).
  const topicsRes = await api.get('/api/admin/topics');
  expect(topicsRes.ok(), `GET /api/admin/topics → ${topicsRes.status()}`).toBeTruthy();
  const python = ((await topicsRes.json()).data.topics as Array<{ id: number; slug: string }>).find(
    (t) => t.slug === 'python',
  );
  expect(python, 'seeded topic `python` must exist').toBeTruthy();
  const res = await api.post('/api/admin/opportunities', {
    data: {
      title,
      type: 'workshop',
      summary: `Close/reopen fixture (${RUN}).`,
      description_md: 'Fixture listing.',
      topic_ids: [python!.id],
      location_mode: 'remote',
      deadline: isoDaysFromNow(deadlineDays),
      status: 'open',
    },
  });
  expect(res.ok(), `POST /api/admin/opportunities → ${res.status()}`).toBeTruthy();
  const id = (await res.json()).data.opportunity.id as number;
  extraListingIds.push(id);
  return id;
}

/** Open the admin editor for an existing listing and wait for it to load. */
async function openEditor(page: Page, id: number, title: string): Promise<void> {
  await page.goto(`${ADMIN_OPPS_URL}edit/?id=${id}`);
  const titleInput = page.getByTestId('opp-title-input');
  await expect(titleInput).toBeVisible({ timeout: 15_000 });
  await expect(titleInput).toHaveValue(title);
  await waitForHydration(page.getByTestId('opp-status-pill'));
}

/** The admin's view of a listing (server truth), via the admin API. */
async function adminListing(
  id: number,
): Promise<{ status: string; deadline: string; summary: string }> {
  const res = await api.get(`/api/admin/opportunities/${id}`);
  expect(res.ok(), `GET /api/admin/opportunities/${id} → ${res.status()}`).toBeTruthy();
  return (await res.json()).data.opportunity;
}

/**
 * The deadline input's current value, asserted to be the SERVER deadline as
 * the editor renders it (local datetime-local, minute precision — browser and
 * runner share a machine, so the runner's local zone is the browser's).
 */
async function expectServerDeadlineShown(page: Page, serverIso: string): Promise<string> {
  const { date, time } = localParts(new Date(serverIso));
  const expected = `${date}T${time}`;
  await expect(page.getByTestId('opp-deadline-input')).toHaveValue(expected);
  return expected;
}

/** Fresh keyless context: the listing is public and open (detail, no banner, on the board). */
async function expectPubliclyOpen(browser: Browser, id: number, title: string, label: string) {
  const { ctx, page } = await publicPage(browser, label);
  try {
    await page.goto(`${ORIGIN}/opportunities/${id}`);
    await expect(page.getByTestId('opportunity-detail')).toBeVisible();
    await expect(page.getByTestId('opportunity-title')).toHaveText(title);
    await expect(page.getByTestId('closed-banner')).toHaveCount(0);
    await page.goto(BOARD_URL);
    await waitForBoard(page);
    await expect(card(page, title)).toHaveCount(1);
  } finally {
    await ctx.close();
  }
}

/** Fresh keyless context: the listing shows the closed banner and is off the board. */
async function expectPubliclyClosed(browser: Browser, id: number, title: string, label: string) {
  const { ctx, page } = await publicPage(browser, label);
  try {
    await page.goto(`${ORIGIN}/opportunities/${id}`);
    await expect(page.getByTestId('opportunity-detail')).toBeVisible();
    await expect(page.getByTestId('closed-banner')).toBeVisible();
    await page.goto(BOARD_URL);
    await waitForBoard(page);
    await expect(card(page, title)).toHaveCount(0);
  } finally {
    await ctx.close();
  }
}

/** Click an editor action button (after hydration) and wait for its PATCH reply. */
async function clickAction(page: Page, id: number, testId: string): Promise<number> {
  const btn = page.getByTestId(testId);
  await waitForHydration(btn);
  const patched = page.waitForResponse(
    (r) =>
      r.request().method() === 'PATCH' &&
      new URL(r.url()).pathname === `/api/admin/opportunities/${id}`,
  );
  await btn.click();
  return (await patched).status();
}

/** Phase 11b: pick a partner via PartnerSelect's "+ Add partner" modal. */
async function addPartnerInEditor(page: Page, internal: string, notes?: string): Promise<void> {
  const select = page.getByTestId('editor-partner-select');
  const addBtn = select.getByTestId('add-partner');
  await waitForHydration(addBtn);
  await addBtn.click();
  await expect(page.getByTestId('add-partner-modal')).toBeVisible();
  await fillStable(page.getByTestId('add-partner-internal'), internal);
  if (notes) await fillStable(page.getByTestId('add-partner-notes'), notes);
  const created = page.waitForResponse(
    (r) =>
      r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/admin/partners',
  );
  await page.getByTestId('add-partner-submit').click();
  const res = await created;
  expect(res.status(), 'POST /api/admin/partners must succeed').toBe(200);
  partnerIds.push((await res.json()).data.partner.id as number);
  await expect(page.getByTestId('add-partner-modal')).toHaveCount(0);
  await expect(
    select.getByTestId('partner-select-input').locator('option:checked'),
  ).toHaveText(new RegExp(internal));
}

/** No internal marker in the page HTML (admin-only names/notes never leak). */
async function expectNoLeak(page: Page): Promise<void> {
  const html = await page.content();
  for (const m of LEAK_MARKERS) expect(html).not.toContain(m);
}

/** No internal marker or admin-only key in the public API JSON for a listing. */
async function expectNoLeakInPublicApi(request: APIRequestContext, id: number): Promise<void> {
  const list = await request.get(`${ORIGIN}/api/public/opportunities?page_size=50`);
  const detail = await request.get(`${ORIGIN}/api/public/opportunities/${id}`);
  expect(detail.ok(), 'public detail must be readable once open').toBeTruthy();
  for (const text of [await list.text(), await detail.text()]) {
    for (const m of LEAK_MARKERS) expect(text).not.toContain(m);
    for (const k of ['partner_internal_name', 'internal_notes', 'partner_id', 'name_key']) {
      expect(text).not.toContain(`"${k}"`);
    }
  }
}

/** Fill the editor's public + internal fields for a new listing. */
async function fillEditor(
  page: Page,
  opts: {
    title: string;
    summary: string;
    description?: string;
    topics: Array<{ slug: string; search: string }>;
    location: 'hybrid' | 'remote';
    city?: string;
    deadlineDays: number;
    partnerDisplay?: string;
    partnerInternal?: string;
    partnerNote?: string;
    internalNotes?: string;
  },
): Promise<void> {
  await fillStable(page.getByTestId('opp-title-input'), opts.title);
  await choose(page.getByTestId('opp-type-select'), 'workshop', 'Workshop / training');
  await fillStable(page.getByTestId('opp-summary-input'), opts.summary);
  if (opts.description) {
    await fillStable(page.getByTestId('opp-description-input'), opts.description);
  }
  for (const t of opts.topics) await pickTopic(page, t.slug, t.search);
  await choose(
    page.getByTestId('opp-location-select'),
    opts.location,
    opts.location === 'hybrid' ? 'Hybrid' : 'Remote',
  );
  if (opts.city) {
    // Phase 11c: the single City input is now a chips input (type + Enter).
    const cityInput = page.getByTestId('opp-location-city-input');
    await fillStable(cityInput, opts.city);
    await cityInput.press('Enter');
    await expect(page.getByTestId('opp-location-chip')).toHaveCount(1);
    await expect(page.getByTestId('opp-location-chip-label')).toHaveText(opts.city);
  }
  await fillDeadline(page, opts.deadlineDays);
  if (opts.partnerDisplay) {
    await fillStable(page.getByTestId('opp-partner-display-input'), opts.partnerDisplay);
  }
  if (opts.partnerInternal) {
    await addPartnerInEditor(page, opts.partnerInternal, opts.partnerNote);
  }
  if (opts.internalNotes) {
    await fillStable(page.getByTestId('opp-internal-notes-input'), opts.internalNotes);
  }
}

/** Every open listing id on the public board (all pages, via the public API). */
async function publicOpenIds(request: APIRequestContext): Promise<number[]> {
  const ids: number[] = [];
  for (let pageNo = 1; pageNo <= 100; pageNo += 1) {
    const res = await request.get(
      `${ORIGIN}/api/public/opportunities?page_size=50&page=${pageNo}`,
    );
    expect(res.ok(), 'GET /api/public/opportunities must succeed').toBeTruthy();
    const body = await res.json();
    for (const o of body.data.opportunities as Array<{ id: number }>) ids.push(o.id);
    if (pageNo >= body.data.total_pages) break;
  }
  return ids;
}

// ---------------------------------------------------------------- journey

test.describe.serial('Phase 10 — Opportunity Board, end to end', () => {
  test.beforeAll(async ({ browser, playwright }) => {
    api = await playwright.request.newContext({
      baseURL: ORIGIN,
      extraHTTPHeaders: { 'X-Admin-Key': adminKey() },
    });

    // Fixture for pagination: one fresh topic + 13 open listings tagged with it.
    const topicRes = await api.post('/api/admin/topics', {
      data: { name: PAGING_TOPIC_NAME, category: 'E2E fixtures' },
    });
    expect(topicRes.ok(), `POST /api/admin/topics → ${topicRes.status()}`).toBeTruthy();
    const topic = (await topicRes.json()).data.topic;
    pagingTopicId = topic.id;
    pagingTopicSlug = topic.slug;

    for (let i = 1; i <= PAGING_LISTINGS; i += 1) {
      const res = await api.post('/api/admin/opportunities', {
        data: {
          title: `E2E Paging listing ${i} ${RUN}`,
          type: 'engagement',
          summary: `Pagination fixture ${i} for ${RUN}.`,
          description_md: 'Fixture listing.',
          topic_ids: [pagingTopicId],
          location_mode: 'remote',
          deadline: isoDaysFromNow(10),
          status: 'open',
        },
      });
      expect(res.ok(), `POST /api/admin/opportunities → ${res.status()}`).toBeTruthy();
      pagingListingIds.push((await res.json()).data.opportunity.id);
    }

    adminCtx = await browser.newContext();
    adminCtx.setDefaultTimeout(15_000);
    adminCtx.setDefaultNavigationTimeout(30_000);
    admin = await adminCtx.newPage();
    admin.on('pageerror', (err) => errors.push(`admin: ${String(err)}`));
    // Accept a native confirm() should the editor use one for Close.
    admin.on('dialog', (d) => d.accept().catch(() => undefined));
  });

  test.afterAll(async () => {
    // Best-effort hygiene (the e2e DB is shared across runs): close the paging
    // fixture and hide this run's topics so the public board does not grow.
    if (api) {
      for (const id of [...pagingListingIds, ...extraListingIds]) {
        await api
          .patch(`/api/admin/opportunities/${id}`, { data: { status: 'closed' } })
          .catch(() => undefined);
      }
      const topics = await api
        .get('/api/admin/topics')
        .then((r) => r.json())
        .catch(() => null);
      for (const t of (topics?.data?.topics ?? []) as Array<{ id: number; slug: string }>) {
        if (t.slug === pagingTopicSlug || t.slug === ELIXIR_SLUG) {
          await api
            .patch(`/api/admin/topics/${t.id}`, { data: { active: false } })
            .catch(() => undefined);
        }
      }
      for (const pid of partnerIds) {
        const r = await api
          .patch(`/api/admin/partners/${pid}`, { data: { active: false } })
          .catch(() => null);
        if (r && !r.ok()) console.warn(`partner ${pid} cleanup → ${r.status()}`);
      }
      await api.dispose();
    }
    if (adminCtx) await adminCtx.close();
  });

  test('pretty /opportunities is a 307 into the app', async ({
    request,
  }) => {
    const board = await request.get(`${ORIGIN}/opportunities`, { maxRedirects: 0 });
    expect(board.status()).toBe(307);
    expect(board.headers()['location']).toMatch(/\/app\/opportunities\/$/);
  });

  test('admin creates a draft from the editor — Draft pill', async () => {
    await signInAdmin(admin);
    const nav = admin.getByTestId('nav-opportunities');
    await expect(nav).toBeVisible();
    await waitForHydration(nav);
    await nav.click();
    await expect(admin.getByTestId('admin-opportunities-page')).toBeVisible({ timeout: 15_000 });
    expect(new URL(admin.url()).pathname).toBe('/app/admin/opportunities/');

    const newBtn = admin.getByTestId('new-opportunity-button');
    await waitForHydration(newBtn);
    await newBtn.click();
    await expect(admin.getByTestId('opp-title-input')).toBeVisible({ timeout: 15_000 });

    await fillEditor(admin, {
      title: TITLE,
      summary: SUMMARY,
      description: DESCRIPTION,
      topics: [
        { slug: 'generative-ai', search: 'Generative' },
        { slug: 'python', search: 'Python' },
      ],
      location: 'hybrid',
      city: CITY,
      deadlineDays: 10,
      partnerDisplay: PUBLIC_PARTNER,
      partnerInternal: INTERNAL_PARTNER,
      partnerNote: PARTNER_NOTE,
      internalNotes: INTERNAL_NOTE,
    });

    const created = admin.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        new URL(r.url()).pathname === '/api/admin/opportunities',
    );
    await admin.getByTestId('opp-save-draft').click();
    const res = await created;
    expect(res.status(), 'POST /api/admin/opportunities must succeed').toBe(200);
    const body = await res.json();
    opportunityId = body.data.opportunity.id;
    expect(opportunityId).toBeGreaterThan(0);
    expect(body.data.opportunity.status).toBe('draft');
    expect(body.data.opportunity.partner_internal_name).toBe(INTERNAL_PARTNER);
    expect(body.data.opportunity.partner_id, 'listing is linked to the added partner').toBe(
      partnerIds[0],
    );
    expect(
      (body.data.opportunity.topics as Array<{ slug: string }>).map((t) => t.slug).sort(),
    ).toEqual(['generative-ai', 'python']);

    await expect(admin.getByTestId('opp-status-pill')).toContainText(/draft/i);
  });

  test('a draft is not visible publicly — fresh context shows not-found', async ({
    browser,
  }) => {
    const { ctx, page } = await publicPage(browser, 'draft-view');
    try {
      // Phase 11e: a draft's id is a server-side 404 (no redirect to a slug —
      // a draft's slug must never be disclosed), so the URL stays as typed.
      const res = await page.goto(`${ORIGIN}/opportunities/${opportunityId}`);
      expect(res?.status()).toBe(404);
      expect(new URL(page.url()).pathname).toBe(`/opportunities/${opportunityId}`);
      await expect(page.getByTestId('opportunity-not-found')).toBeVisible();
      await expect(page.getByTestId('opportunity-detail')).toHaveCount(0);
      expect(await page.content()).not.toContain(TITLE);
    } finally {
      await ctx.close();
    }
  });

  test('admin publishes — Open pill, public link, Activity shows create + publish', async () => {
    const publish = admin.getByTestId('opp-publish');
    await waitForHydration(publish);
    await publish.click();
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/open/i);

    await expect(admin.getByTestId('opp-public-link')).toBeVisible();
    // Phase 11e: public_url is the slug URL.
    await expect(admin.getByTestId('opp-public-link')).toContainText(
      /\/opportunities\/[a-z0-9-]+-[0-9a-f]{4,6}$/,
    );

    const rows = admin.getByTestId('opp-activity-row');
    await expect.poll(() => rows.count()).toBeGreaterThanOrEqual(2);
    await expect.poll(() => rows.allInnerTexts().then((t) => t.join('\n'))).toMatch(/creat/i);
    await expect.poll(() => rows.allInnerTexts().then((t) => t.join('\n'))).toMatch(/publish/i);
  });

  test('stranger browses the board — card present, no internal data, filters persist', async ({
    browser,
  }) => {
    const { ctx, page } = await publicPage(browser, 'board');
    try {
      const nav = await page.goto(`${ORIGIN}/opportunities`);
      const redirect = await nav?.request().redirectedFrom()?.response();
      expect(redirect?.status(), 'pretty /opportunities must 307').toBe(307);
      expect(new URL(page.url()).pathname).toBe('/app/opportunities/');

      await waitForBoard(page);
      const mine = card(page, TITLE);
      await expect(mine).toHaveCount(1);
      await expect(mine).toContainText(PUBLIC_PARTNER);
      // Phase 11: the Join-network stub is now the real CTA.
      await expect(page.getByTestId('join-network-stub')).toHaveCount(0);
      await expect(page.getByTestId('join-network-cta')).toBeVisible();
      await expectNoLeak(page);

      // Type filter that excludes it.
      await clickUntilUrl(page, page.getByTestId('type-filter-role'), /[?&]type=role(&|$)/);
      await waitForBoard(page);
      await expect(card(page, TITLE)).toHaveCount(0);

      // Type + topic filters that include it.
      await clickUntilUrl(
        page,
        page.getByTestId('type-filter-workshop'),
        /[?&]type=workshop(&|$)/,
      );
      await clickUntilUrl(
        page,
        page.getByTestId('topic-filter-generative-ai'),
        /[?&]topic=generative-ai(&|$)/,
      );
      await waitForBoard(page);
      await expect(card(page, TITLE)).toHaveCount(1);
      expect(page.url()).toMatch(/[?&]type=workshop(&|$)/);

      // Reload keeps the filters (URL is the source of truth).
      const filteredUrl = page.url();
      await page.reload();
      expect(page.url()).toBe(filteredUrl);
      await waitForBoard(page);
      await expect(card(page, TITLE)).toHaveCount(1);
      expect(page.url()).toMatch(/[?&]type=workshop(&|$)/);
      expect(page.url()).toMatch(/[?&]topic=generative-ai(&|$)/);
      await expectNoLeak(page);

      // Open the listing from its card.
      const target = card(page, TITLE);
      await waitForHydration(target);
      const link = target.getByRole('link').first();
      if ((await link.count()) > 0) await link.click();
      else await target.click();

      const detail = page.getByTestId('opportunity-detail');
      await expect(detail).toBeVisible({ timeout: 15_000 });
      expect(new URL(page.url()).pathname).toMatch(/^\/opportunities\/[a-z0-9-]+-[0-9a-f]{4,6}$/);
      expect(new URL(page.url()).searchParams.get('from')).toMatch(/type=workshop/);
      await expect(page.getByTestId('opportunity-title')).toHaveText(TITLE);
      await expect(detail).toContainText(PUBLIC_PARTNER);
      await expect(page).toHaveTitle(new RegExp(TITLE));

      // Markdown is rendered: a real list and a highlighted fenced code block.
      await expect(detail.locator('li', { hasText: LIST_ITEM })).toBeVisible();
      const code = detail.locator('pre code');
      await expect(code).toBeVisible();
      await expect(code).toContainText(CODE_LINE);
      await expect(code).toHaveClass(/language-|hljs/);
      await expect.poll(() => code.locator('span[class*="hljs-"]').count()).toBeGreaterThan(0);
      await expect(detail).not.toContainText('```');

      // Phase 12: signed-out visitors get a real sign-in-to-apply link; join CTA stays.
      await expect(page.getByTestId('join-network-cta')).toBeVisible();
      const applySignin = page.getByTestId('apply-signin');
      await expect(applySignin).toBeVisible();
      await expect(applySignin).toContainText('Sign in to apply');
      await expect(applySignin).toHaveAttribute('href', /.+/);
      await expect(page.getByTestId('closed-banner')).toHaveCount(0);
      await expectNoLeak(page);
      await expectNoLeakInPublicApi(page.request, opportunityId);
    } finally {
      await ctx.close();
    }
  });

  test('admin closes it — closed banner on the listing, gone from the board', async ({
    browser,
    request,
  }) => {
    const close = admin.getByTestId('opp-close');
    await waitForHydration(close);
    await close.click();
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/closed/i);

    const { ctx, page } = await publicPage(browser, 'closed-view');
    try {
      await page.goto(`${ORIGIN}/opportunities/${opportunityId}`);
      await expect(page.getByTestId('opportunity-detail')).toBeVisible();
      await expect(page.getByTestId('closed-banner')).toBeVisible();
      await expect(page.getByTestId('apply-signin')).toHaveCount(0);
      await expectNoLeak(page);

      await page.goto(BOARD_URL);
      await waitForBoard(page);
      await expect(card(page, TITLE)).toHaveCount(0);
    } finally {
      await ctx.close();
    }
    expect(await publicOpenIds(request)).not.toContain(opportunityId);
  });

  test('publishing with a past deadline is refused inline and creates nothing', async ({
    request,
  }) => {
    await admin.goto(ADMIN_OPPS_URL);
    await expect(admin.getByTestId('admin-opportunities-page')).toBeVisible({ timeout: 15_000 });
    const newBtn = admin.getByTestId('new-opportunity-button');
    await waitForHydration(newBtn);
    await newBtn.click();
    await expect(admin.getByTestId('opp-title-input')).toBeVisible({ timeout: 15_000 });

    await fillEditor(admin, {
      title: PAST_TITLE,
      summary: `Past-deadline publish attempt (${RUN}).`,
      topics: [{ slug: 'python', search: 'Python' }],
      location: 'remote',
      deadlineDays: -1,
    });
    const publish = admin.getByTestId('opp-publish');
    await waitForHydration(publish);
    await publish.click();

    const fieldError = admin.getByTestId('opp-field-error-deadline');
    await expect(fieldError).toBeVisible();
    await expect(fieldError).toContainText(/future deadline/i);
    // Nothing typed is lost on error.
    await expect(admin.getByTestId('opp-title-input')).toHaveValue(PAST_TITLE);

    const found = await api.get(
      `/api/admin/opportunities?q=${encodeURIComponent(PAST_TITLE)}`,
    );
    expect(found.ok()).toBeTruthy();
    expect((await found.json()).data.total, 'a refused publish creates no listing').toBe(0);
    const pub = await request.get(`${ORIGIN}/api/public/opportunities?page_size=50`);
    expect(await pub.text()).not.toContain(PAST_TITLE);
  });

  test('regression: a past-deadline Save is refused; Close still works; Reopen with a future deadline', async ({
    browser,
    request,
  }) => {
    const id = await createOpenListing(REOPEN_TITLE, 10);
    const before = await adminListing(id);
    expect(before.status).toBe('open');
    await openEditor(admin, id, REOPEN_TITLE);
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/open/i);

    // 1. Save with a deadline one hour in the past → inline refusal, nothing changes.
    const pastValue = await fillDeadlineAt(admin, new Date(Date.now() - 3_600_000));
    const saveStatus = await clickAction(admin, id, 'opp-save');
    expect(saveStatus, 'a past-deadline save is a validation error').toBe(422);
    const fieldError = admin.getByTestId('opp-field-error-deadline');
    await expect(fieldError).toBeVisible();
    await expect(fieldError).toContainText(/future deadline/i);
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/open/i);
    const afterSave = await adminListing(id);
    expect(afterSave.status).toBe('open');
    expect(afterSave.deadline, 'a refused save leaves the deadline untouched').toBe(
      before.deadline,
    );
    expect(await publicOpenIds(request)).toContain(id);
    await expectPubliclyOpen(browser, id, REOPEN_TITLE, 'reopen-still-open');

    // 2. Close sends only the status — the unsent past deadline must not block it.
    const closeStatus = await clickAction(admin, id, 'opp-close');
    expect(closeStatus, 'Close must succeed despite an unsent past deadline').toBe(200);
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/closed/i);
    await expect(admin.getByTestId('opp-field-error-deadline')).toHaveCount(0);
    // The refused past deadline is discarded: the input shows the server's
    // (unchanged, future) deadline again, with no Unsaved marker.
    await expect(admin.getByTestId('opp-deadline-input')).not.toHaveValue(pastValue);
    await expectServerDeadlineShown(admin, before.deadline);
    await expect(admin.getByTestId('opp-unsaved-deadline')).toHaveCount(0);
    expect((await adminListing(id)).status).toBe('closed');
    await expectPubliclyClosed(browser, id, REOPEN_TITLE, 'reopen-closed');
    expect(await publicOpenIds(request)).not.toContain(id);

    // 3. A future deadline (+5 days) and Reopen → Open, back on the public board.
    await fillDeadlineAt(admin, new Date(Date.now() + 5 * 86_400_000));
    const reopenStatus = await clickAction(admin, id, 'opp-reopen');
    expect(reopenStatus, 'Reopen with a future deadline must succeed').toBe(200);
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/open/i);
    const reopened = await adminListing(id);
    expect(reopened.status).toBe('open');
    expect(Date.parse(reopened.deadline)).toBeGreaterThan(Date.now() + 4 * 86_400_000);
    expect(await publicOpenIds(request)).toContain(id);
    await expectPubliclyOpen(browser, id, REOPEN_TITLE, 'reopen-open-again');
  });

  test('regression (roadmap Phase 10 step 5): refused past deadline → Close → Reopen with no further edits → Open', async ({
    browser,
    request,
  }) => {
    const id = await createOpenListing(STEP5_TITLE, 10);
    const before = await adminListing(id);
    expect(before.status).toBe('open');
    await openEditor(admin, id, STEP5_TITLE);
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/open/i);
    const serverValue = await expectServerDeadlineShown(admin, before.deadline);
    await expect(admin.getByTestId('opp-unsaved-deadline')).toHaveCount(0);

    // Set the deadline to one hour ago and Save → 422, inline "future deadline".
    const pastValue = await fillDeadlineAt(admin, new Date(Date.now() - 3_600_000));
    expect(pastValue).not.toBe(serverValue);
    expect(await clickAction(admin, id, 'opp-save'), 'a past-deadline save is refused').toBe(422);
    const fieldError = admin.getByTestId('opp-field-error-deadline');
    await expect(fieldError).toBeVisible();
    await expect(fieldError).toContainText(/future deadline/i);
    expect((await adminListing(id)).deadline, 'a refused save changes nothing').toBe(
      before.deadline,
    );

    // Close → 200, Closed; the refused value is discarded (server deadline back,
    // no Unsaved marker, no stale inline error).
    expect(await clickAction(admin, id, 'opp-close'), 'Close must succeed').toBe(200);
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/closed/i);
    await expect(admin.getByTestId('opp-field-error-deadline')).toHaveCount(0);
    await expect(admin.getByTestId('opp-deadline-input')).toHaveValue(serverValue);
    await expect(admin.getByTestId('opp-unsaved-deadline')).not.toBeVisible();
    const closed = await adminListing(id);
    expect(closed.status).toBe('closed');
    expect(closed.deadline, 'Close does not touch the deadline').toBe(before.deadline);

    // Reopen WITHOUT any further edits → 200, Open, deadline still the original.
    expect(
      await clickAction(admin, id, 'opp-reopen'),
      'Reopen right after Close (no edits) must succeed',
    ).toBe(200);
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/open/i);
    await expect(admin.getByTestId('opp-field-error-deadline')).toHaveCount(0);
    await expect(admin.getByTestId('opp-deadline-input')).toHaveValue(serverValue);
    const reopened = await adminListing(id);
    expect(reopened.status).toBe('open');
    expect(reopened.deadline, 'Reopen keeps the original deadline').toBe(before.deadline);
    expect(await publicOpenIds(request)).toContain(id);
    await expectPubliclyOpen(browser, id, STEP5_TITLE, 'step5-open-again');
  });

  test('Close discards only the refused deadline — an unrelated unsent summary edit survives', async ({
    browser,
  }) => {
    const id = await createOpenListing(KEEP_EDIT_TITLE, 10);
    const before = await adminListing(id);
    await openEditor(admin, id, KEEP_EDIT_TITLE);
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/open/i);
    const serverValue = await expectServerDeadlineShown(admin, before.deadline);

    await fillDeadlineAt(admin, new Date(Date.now() - 3_600_000));
    expect(await clickAction(admin, id, 'opp-save'), 'a past-deadline save is refused').toBe(422);
    await expect(admin.getByTestId('opp-field-error-deadline')).toContainText(/future deadline/i);

    // An edit typed AFTER the refusal was never sent, so never refused.
    await fillStable(admin.getByTestId('opp-summary-input'), KEEP_EDIT_SUMMARY);
    await expect(admin.getByTestId('opp-unsaved-summary')).toBeVisible();

    expect(await clickAction(admin, id, 'opp-close'), 'Close must succeed').toBe(200);
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/closed/i);
    // Refused deadline discarded …
    await expect(admin.getByTestId('opp-deadline-input')).toHaveValue(serverValue);
    await expect(admin.getByTestId('opp-unsaved-deadline')).toHaveCount(0);
    // … the unrelated unsent summary edit survives, still marked Unsaved.
    await expect(admin.getByTestId('opp-summary-input')).toHaveValue(KEEP_EDIT_SUMMARY);
    await expect(admin.getByTestId('opp-unsaved-summary')).toBeVisible();
    // Close sent only the status: the server summary is unchanged.
    const closed = await adminListing(id);
    expect(closed.status).toBe('closed');
    expect(closed.summary).toBe(before.summary);
    await expectPubliclyClosed(browser, id, KEEP_EDIT_TITLE, 'keep-edit-closed');
  });

  test('Close then Reopen with the untouched future deadline → Open again', async ({
    browser,
    request,
  }) => {
    const id = await createOpenListing(PLAIN_REOPEN_TITLE, 10);
    const before = await adminListing(id);
    await openEditor(admin, id, PLAIN_REOPEN_TITLE);
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/open/i);

    expect(await clickAction(admin, id, 'opp-close'), 'Close must succeed').toBe(200);
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/closed/i);
    expect((await adminListing(id)).status).toBe('closed');
    await expectPubliclyClosed(browser, id, PLAIN_REOPEN_TITLE, 'plain-closed');

    expect(await clickAction(admin, id, 'opp-reopen'), 'Reopen must succeed').toBe(200);
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/open/i);
    const reopened = await adminListing(id);
    expect(reopened.status).toBe('open');
    expect(reopened.deadline, 'Reopen does not touch the deadline').toBe(before.deadline);
    expect(await publicOpenIds(request)).toContain(id);
    await expectPubliclyOpen(browser, id, PLAIN_REOPEN_TITLE, 'plain-open-again');
  });

  test('admin adds a topic; a case-insensitive duplicate is refused', async () => {
    await admin.goto(`${ADMIN_BASE}/topics/`);
    await expect(admin.getByTestId('admin-topics-page')).toBeVisible({ timeout: 15_000 });

    await fillStable(admin.getByTestId('topic-name-input'), ELIXIR_NAME);
    await fillStable(admin.getByTestId('topic-category-input'), 'Languages');
    await admin.getByTestId('topic-add-button').click();
    await expect(admin.getByTestId('topic-row').filter({ hasText: ELIXIR_NAME })).toHaveCount(1);
    await expect(admin.getByTestId('topic-error')).toHaveCount(0);

    await fillStable(admin.getByTestId('topic-name-input'), ELIXIR_NAME.toLowerCase());
    await fillStable(admin.getByTestId('topic-category-input'), 'Languages');
    await admin.getByTestId('topic-add-button').click();
    await expect(admin.getByTestId('topic-error')).toBeVisible();
    await expect(
      admin.getByTestId('topic-row').filter({ hasText: new RegExp(`elixir ${RUN}`, 'i') }),
    ).toHaveCount(1);

    const all = await api.get('/api/admin/topics');
    const slugs = ((await all.json()).data.topics as Array<{ slug: string }>).filter(
      (t) => t.slug === ELIXIR_SLUG,
    );
    expect(slugs, 'exactly one topic row for the name').toHaveLength(1);
  });

  test('the new topic shows on the public board filters, muted with 0', async ({ browser }) => {
    const { ctx, page } = await publicPage(browser, 'topic-chip');
    try {
      await page.goto(BOARD_URL);
      await waitForBoard(page);
      const chip = page.getByTestId(`topic-filter-${ELIXIR_SLUG}`);
      await expect(chip).toBeVisible();
      await expect(chip).toContainText(new RegExp(`Elixir ${RUN}`, 'i'));
      // RUN has no digits, so the only number in the chip is its open count.
      await expect(chip).toHaveText(/(^|\D)0(\D*)$/);
    } finally {
      await ctx.close();
    }
  });

  test('pagination — 13 listings for one topic → 12 + 1 over 2 pages', async ({ browser }) => {
    const { ctx, page } = await publicPage(browser, 'pagination');
    try {
      await page.goto(BOARD_URL);
      await waitForBoard(page);
      await clickUntilUrl(
        page,
        page.getByTestId(`topic-filter-${pagingTopicSlug}`),
        new RegExp(`[?&]topic=${pagingTopicSlug}(&|$)`),
      );

      const cards = page.getByTestId('opportunity-card');
      const pagingCardsOnly = async () => {
        const texts = await cards.allInnerTexts();
        return texts.length > 0 && texts.every((t) => t.includes(`E2E Paging listing`) && t.includes(RUN));
      };
      // Wait for the FILTERED result (the unfiltered board may also hold 12 cards).
      await expect.poll(pagingCardsOnly).toBe(true);
      await expect(cards).toHaveCount(12);
      await expect(page.getByTestId('pagination-status')).toHaveText(/Page 1 of 2/);

      const next = page.getByTestId('pagination-next');
      await waitForHydration(next);
      await next.click();
      await expect(page.getByTestId('pagination-status')).toHaveText(/Page 2 of 2/);
      await expect(cards).toHaveCount(1);
      await expect(cards.first()).toContainText(RUN);
      expect(page.url()).toMatch(/[?&]page=2(&|$)/);
      expect(page.url()).toMatch(new RegExp(`[?&]topic=${pagingTopicSlug}(&|$)`));
    } finally {
      await ctx.close();
    }
  });

  test('the board has no horizontal scroll at 360 px', async ({ browser }) => {
    const { ctx, page } = await publicPage(browser, 'narrow', { width: 360, height: 800 });
    try {
      await page.goto(BOARD_URL);
      await waitForBoard(page);
      await expect
        .poll(() =>
          page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth),
        )
        .toBeLessThanOrEqual(0);
    } finally {
      await ctx.close();
    }
  });

  test('no uncaught page errors and no admin key sent from public contexts', async () => {
    expect(errors).toEqual([]);
  });
});
