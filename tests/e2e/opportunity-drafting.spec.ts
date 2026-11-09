import {
  test,
  expect,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import {
  ADMIN_BASE,
  ORIGIN,
  adminKey,
  fillStable,
  signInAdmin,
  waitForHydration,
} from './helpers';

/**
 * Phase 11b — AI drafting + Partners + compensation, end to end (roadmap.md
 * §Phase 11b "e2e journey", capabilities.md C9/C10, api.md §Phase 11b).
 *
 * An admin pastes a realistic forwarded post into a NEW listing, the REAL
 * drafter (Anthropic via the server's .env) prefills the form with "Drafted —
 * please check" chips, topics only from the curated list, a cost line, and the
 * listing stays a draft. The admin fixes a field (its chip clears), adds the
 * partner, sets an explicit per-day compensation range and publishes. The
 * public listing shows exactly `₹8,000–12,000 / day` and no partner internal
 * name / notes anywhere in the HTML or the public API JSON.
 *
 * The "AI not configured" state is checked by intercepting the config call in
 * the browser; the real keyless path is covered by backend tests.
 *
 * Self-seeding; every name carries RUN; the e2e DB is shared, so data is
 * cleaned up in afterAll (listing closed, partner deactivated).
 */

const RUN = `r${Date.now()
  .toString(36)
  .replace(/\d/g, (d) => 'abcdefghij'[Number(d)])}`;

const TITLE = `E2E Drafted workshop ${RUN}`;
const PARTNER_INTERNAL = `ZZ-DRAFT-PARTNER-${RUN}`;
const PARTNER_NOTE = `ZZ-DRAFT-NOTE-${RUN}`;
const LEAK_MARKERS = [PARTNER_INTERNAL, PARTNER_NOTE, 'ZZ-DRAFT-'];
const EXPECTED_COMPENSATION = '₹8,000–12,000 / day';

// Text of tests/fixtures/opportunity_posts/forwarded_genai_workshop.txt.
const POST = `From: Priya Nair <p.nair@zenvia.example>
To: partnerships@smalltech.example
Subject: Fwd: Trainer needed - GenAI + Python workshop, Pune, February

Hi team,

Forwarding the brief from our L&D side. Zenvia Learning Pvt Ltd is looking for a trainer to run a 2-day
hybrid workshop on Generative AI with Python for about 30 of our engineers. The room is in our Pune
office (Baner), and 4-5 participants from the Hyderabad team will join remotely, so the trainer should be
comfortable running a hybrid classroom.

Dates: 8 and 9 February 2027, 10:00 to 17:30 each day.

What we want covered: prompt design, calling LLM APIs from Python, building a small retrieval-augmented
app, and evaluating outputs. Participants are working engineers who already write Python daily; no ML
background needed. Hands-on labs matter more to us than slides.

Budget: Rs 8,000-12,000 per day plus travel (we cover train/flight and two nights' stay if you are
travelling in). Please send your profile and a proposed agenda by 15 January 2027.

Do not share the fee range outside your trainer network please. For questions you can reach me directly
on +91 98450 12345 or reply to this mail.

Thanks,
Priya Nair
Learning & Development Lead
Zenvia Learning Pvt Ltd | Baner Road, Pune 411045`;

const ADMIN_OPPS_URL = `${ADMIN_BASE}/opportunities/`;

const errors: string[] = [];

let api: APIRequestContext;
let adminCtx: BrowserContext;
let admin: Page;

let opportunityId = 0;
let partnerId = 0;
const createdListingIds: number[] = [];
const createdPartnerIds: number[] = [];
let editorPosts = 0;

async function openNewEditor(page: Page): Promise<void> {
  await page.goto(ADMIN_OPPS_URL);
  await expect(page.getByTestId('admin-opportunities-page')).toBeVisible({ timeout: 15_000 });
  const newBtn = page.getByTestId('new-opportunity-button');
  await waitForHydration(newBtn);
  await newBtn.click();
  await expect(page.getByTestId('opp-title-input')).toBeVisible({ timeout: 15_000 });
}

test.describe.serial('Phase 11b — AI drafting, Partners and compensation, end to end', () => {
  test.beforeAll(async ({ browser, playwright }) => {
    api = await playwright.request.newContext({
      baseURL: ORIGIN,
      extraHTTPHeaders: { 'X-Admin-Key': adminKey() },
    });
    adminCtx = await browser.newContext();
    adminCtx.setDefaultTimeout(15_000);
    adminCtx.setDefaultNavigationTimeout(30_000);
    admin = await adminCtx.newPage();
    admin.on('pageerror', (err) => errors.push(`admin: ${String(err)}`));
    // Count saves of the listing itself: a draft must not create anything.
    admin.on('request', (req) => {
      if (req.method() === 'POST' && new URL(req.url()).pathname === '/api/admin/opportunities') {
        editorPosts += 1;
      }
    });
  });

  test.afterAll(async () => {
    if (api) {
      for (const id of [...new Set([opportunityId, ...createdListingIds])].filter((i) => i > 0)) {
        const r = await api
          .patch(`/api/admin/opportunities/${id}`, { data: { status: 'closed' } })
          .catch(() => null);
        if (r && !r.ok()) console.warn(`listing ${id} cleanup → ${r.status()}`);
      }
      for (const pid of createdPartnerIds) {
        const r = await api
          .patch(`/api/admin/partners/${pid}`, { data: { active: false } })
          .catch(() => null);
        if (r && !r.ok()) console.warn(`partner ${pid} cleanup → ${r.status()}`);
      }
      await api.dispose();
    }
    if (adminCtx) await adminCtx.close();
  });

  test('paste a forwarded post and Draft — fields prefilled with chips, curated topics, cost, still a draft', async () => {
    test.setTimeout(150_000);
    await signInAdmin(admin);
    await openNewEditor(admin);

    const panel = admin.getByTestId('paste-to-fill');
    await expect(panel).toBeVisible();
    await expect(admin.getByTestId('ai-not-configured')).toHaveCount(0);
    await fillStable(admin.getByTestId('paste-textarea'), POST);

    const draftBtn = admin.getByTestId('draft-button');
    await expect(draftBtn).toBeEnabled();
    await draftBtn.click();

    // Real model call: generous timeout.
    await expect(admin.getByTestId('draft-applied')).toBeVisible({ timeout: 90_000 });
    await expect(admin.getByTestId('draft-error')).toHaveCount(0);
    await expect(admin.getByTestId('draft-cost')).toContainText('$');

    // Prefilled and flagged.
    await expect(admin.getByTestId('opp-title-input')).not.toHaveValue('');
    await expect(admin.getByTestId('opp-summary-input')).not.toHaveValue('');
    await expect(admin.getByTestId('drafted-chip-title')).toBeVisible();
    await expect(admin.getByTestId('drafted-chip-title')).toContainText('Drafted — please check');
    expect(await admin.getByTestId('drafted-chip').count()).toBeGreaterThan(1);

    // Topics only from the curated (active) list, at least one.
    const topicsRes = await api.get('/api/admin/topics');
    expect(topicsRes.ok()).toBeTruthy();
    const curated = new Set(
      ((await topicsRes.json()).data.topics as Array<{ slug: string; active?: boolean }>)
        .filter((t) => t.active !== false)
        .map((t) => t.slug),
    );
    const options = admin.locator('[data-testid^="opp-topic-option-"]');
    const checked: string[] = [];
    for (let i = 0; i < (await options.count()); i += 1) {
      const opt = options.nth(i);
      if (await opt.getByRole('checkbox').isChecked()) {
        const id = (await opt.getAttribute('data-testid')) ?? '';
        checked.push(id.replace('opp-topic-option-', ''));
      }
    }
    expect(checked.length, 'the draft ticks at least one topic').toBeGreaterThan(0);
    for (const slug of checked) expect(curated.has(slug), `topic ${slug} is curated`).toBe(true);

    // Nothing was saved or published: still a draft form, no listing POST.
    await expect(admin.getByTestId('opp-publish')).toBeVisible();
    await expect(admin.getByTestId('opp-save-draft')).toBeVisible();
    expect(editorPosts, 'drafting never creates a listing').toBe(0);
  });

  test('fixing a field clears its Drafted chip', async () => {
    await expect(admin.getByTestId('drafted-chip-title')).toBeVisible();
    await fillStable(admin.getByTestId('opp-title-input'), TITLE);
    await expect(admin.getByTestId('drafted-chip-title')).toHaveCount(0);
    // Other drafted fields keep their chip.
    expect(await admin.getByTestId('drafted-chip').count()).toBeGreaterThan(0);
  });

  test('confirm the partner, set per-day compensation, publish', async () => {
    // Add the partner via the select (deterministic whatever the drafter suggested).
    const select = admin.getByTestId('editor-partner-select');
    const addBtn = select.getByTestId('add-partner');
    await waitForHydration(addBtn);
    await addBtn.click();
    await expect(admin.getByTestId('add-partner-modal')).toBeVisible();
    await fillStable(admin.getByTestId('add-partner-internal'), PARTNER_INTERNAL);
    await fillStable(admin.getByTestId('add-partner-notes'), PARTNER_NOTE);
    const created = admin.waitForResponse(
      (r) =>
        r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/admin/partners',
    );
    await admin.getByTestId('add-partner-submit').click();
    const pres = await created;
    expect(pres.status()).toBe(200);
    partnerId = (await pres.json()).data.partner.id;
    createdPartnerIds.push(partnerId);
    await expect(admin.getByTestId('add-partner-modal')).toHaveCount(0);
    await expect(
      select.getByTestId('partner-select-input').locator('option:checked'),
    ).toHaveText(new RegExp(PARTNER_INTERNAL));

    // Explicit, deterministic compensation (overrides whatever was drafted).
    await fillStable(admin.getByTestId('compensation-min'), '8000');
    await fillStable(admin.getByTestId('compensation-max'), '12000');
    await admin.getByTestId('compensation-currency').selectOption('INR');
    await admin.getByTestId('compensation-unit').selectOption('day');
    await fillStable(admin.getByTestId('opp-compensation-input'), '');
    await expect(admin.getByTestId('opp-preview-compensation')).toContainText(
      EXPECTED_COMPENSATION,
    );

    // Make publish-critical fields deterministic regardless of the draft.
    const city = admin.getByTestId('opp-city-input');
    if ((await city.isVisible().catch(() => false)) && (await city.inputValue()) === '') {
      await fillStable(city, 'Pune');
    }
    const input = admin.getByTestId('opp-deadline-input');
    await waitForHydration(input);
    const d = new Date(Date.now() + 10 * 86_400_000);
    const p = (n: number) => String(n).padStart(2, '0');
    const day = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    await fillStable(input, (await input.getAttribute('type')) === 'date' ? day : `${day}T23:59`);

    const publishPost = admin.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        new URL(r.url()).pathname === '/api/admin/opportunities',
    );
    const publish = admin.getByTestId('opp-publish');
    await waitForHydration(publish);
    await publish.click();
    const res = await publishPost;
    expect(res.status(), `publish → ${res.status()}: ${await res.text()}`).toBe(200);
    const opp = (await res.json()).data.opportunity;
    opportunityId = opp.id;
    createdListingIds.push(opportunityId);
    expect(opp.status).toBe('open');
    expect(opp.partner_id).toBe(partnerId);
    expect(opp.compensation_min).toBe(8000);
    expect(opp.compensation_max).toBe(12000);
    expect(opp.compensation_currency).toBe('INR');
    expect(opp.compensation_unit).toBe('day');
    await expect(admin.getByTestId('opp-status-pill')).toContainText(/open/i);
  });

  test('public listing shows the exact compensation and leaks no partner internals', async ({
    browser,
  }) => {
    const ctx = await browser.newContext();
    ctx.setDefaultTimeout(15_000);
    ctx.on('request', (req) => {
      if (req.headers()['x-admin-key'] !== undefined) {
        errors.push(`public context sent X-Admin-Key to ${req.url()}`);
      }
    });
    const page = await ctx.newPage();
    page.on('pageerror', (err) => errors.push(`public: ${String(err)}`));
    try {
      await page.goto(`${ORIGIN}/opportunities/${opportunityId}`);
      await expect(page.getByTestId('opportunity-detail')).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId('opportunity-title')).toHaveText(TITLE);
      await expect(page.getByTestId('opportunity-compensation')).toHaveText(
        new RegExp(`${EXPECTED_COMPENSATION}$`),
      );
      await expect(page.getByTestId('opportunity-compensation')).toContainText(
        EXPECTED_COMPENSATION,
      );

      const html = await page.content();
      for (const m of LEAK_MARKERS) expect(html).not.toContain(m);

      const detail = await page.request.get(`${ORIGIN}/api/public/opportunities/${opportunityId}`);
      expect(detail.ok()).toBeTruthy();
      const detailText = await detail.text();
      const list = await page.request.get(`${ORIGIN}/api/public/opportunities?page_size=50`);
      expect(list.ok()).toBeTruthy();
      const listText = await list.text();
      for (const text of [detailText, listText]) {
        for (const m of LEAK_MARKERS) expect(text).not.toContain(m);
        for (const k of ['partner_internal_name', 'internal_notes', 'partner_id', 'name_key']) {
          expect(text).not.toContain(`"${k}"`);
        }
      }
      const body = JSON.parse(detailText).data.opportunity;
      expect(body.compensation_min).toBe(8000);
      expect(body.compensation_max).toBe(12000);
      expect(body.compensation_currency).toBe('INR');
      expect(body.compensation_unit).toBe('day');
    } finally {
      await ctx.close();
    }
  });

  test('"AI drafting not configured" state (config intercepted) — hand-filling still possible', async ({
    browser,
  }) => {
    const ctx = await browser.newContext();
    ctx.setDefaultTimeout(15_000);
    ctx.setDefaultNavigationTimeout(30_000);
    const page = await ctx.newPage();
    page.on('pageerror', (err) => errors.push(`not-configured: ${String(err)}`));
    try {
      await page.route('**/api/admin/opportunity-draft/config', (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ data: { available: false, model: 'none' } }),
        }),
      );
      await signInAdmin(page);
      await openNewEditor(page);
      await expect(page.getByTestId('paste-to-fill')).toBeVisible();
      await expect(page.getByTestId('ai-not-configured')).toBeVisible();
      await expect(page.getByTestId('ai-not-configured')).toContainText(/not configured/i);
      await expect(page.getByTestId('paste-textarea')).toHaveCount(0);
      await expect(page.getByTestId('draft-button')).toHaveCount(0);
      // The form is still usable by hand.
      await fillStable(page.getByTestId('opp-title-input'), `E2E by hand ${RUN}`);
    } finally {
      await ctx.close();
    }
  });

  test('no uncaught page errors and no admin key sent from public contexts', async () => {
    expect(errors).toEqual([]);
  });
});
