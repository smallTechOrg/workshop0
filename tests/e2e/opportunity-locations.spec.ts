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
 * Phase 11c — Multi-location opportunities (roadmap.md §Phase 11c "e2e journey
 * (M5)", capabilities.md §C9 additions — Phase 11c / §C10 → Location display,
 * api.md §Phase 11c).
 *
 * The e2e database is NOT reset between runs: every title carries RUN, a
 * letters-only per-run suffix. Public views use a FRESH keyless context.
 */

const RUN = `r${Date.now()
  .toString(36)
  .replace(/\d/g, (d) => 'abcdefghij'[Number(d)])}`;

const TITLE = `Multi-city ${RUN}`;
const INTERNAL_NOTES = `ZZ-INTERNAL-${RUN}`;
const BOARD_NEWEST = `${APP_BASE}/opportunities/?sort=newest`;
const ADMIN_OPPS_URL = `${ADMIN_BASE}/opportunities/`;

const errors: string[] = [];
const createdIds: number[] = [];

let api: APIRequestContext;
let adminCtx: BrowserContext;
let admin: Page;
let pythonTopicId = 0;
let multiId = 0;
let legacyId = 0;

// ---------------------------------------------------------------- helpers

function isoDaysFromNow(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

function chips(page: Page): Locator {
  return page.getByTestId('opp-location-chip');
}

async function expectChips(page: Page, labels: string[]): Promise<void> {
  await expect(chips(page)).toHaveCount(labels.length);
  await expect(page.getByTestId('opp-location-chip-label')).toHaveText(labels);
}

async function openNewEditor(page: Page): Promise<void> {
  await page.goto(ADMIN_OPPS_URL);
  await expect(page.getByTestId('admin-opportunities-page')).toBeVisible({ timeout: 15_000 });
  const newBtn = page.getByTestId('new-opportunity-button');
  await waitForHydration(newBtn);
  await expect(async () => {
    if (!(await page.getByTestId('opp-title-input').isVisible())) await newBtn.click();
    await expect(page.getByTestId('opp-title-input')).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 15_000 });
}

async function setMode(page: Page, mode: 'onsite' | 'hybrid' | 'remote'): Promise<void> {
  const select = page.getByTestId('opp-location-select');
  await waitForHydration(select);
  await select.selectOption(mode);
  await expect(select).toHaveValue(mode);
}

async function pickPython(page: Page): Promise<void> {
  const option = page.getByTestId('opp-topic-option-python');
  if (!(await option.isVisible().catch(() => false))) {
    const search = page.getByRole('searchbox', { name: 'Search topics' });
    if (await search.isVisible().catch(() => false)) await fillStable(search, 'Python');
  }
  await expect(option).toBeVisible();
  const checkbox = option.getByRole('checkbox');
  await waitForHydration(checkbox);
  await expect(async () => {
    if (!(await checkbox.isChecked())) await option.click();
    await expect(checkbox).toBeChecked({ timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
}

async function fillDeadline(page: Page, daysFromNow: number): Promise<void> {
  const input = page.getByTestId('opp-deadline-input');
  await waitForHydration(input);
  const d = new Date(Date.now() + daysFromNow * 86_400_000);
  const p = (n: number) => String(n).padStart(2, '0');
  const day = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  await fillStable(input, (await input.getAttribute('type')) === 'date' ? day : `${day}T23:59`);
}

/** Required public fields + internal notes (location handled by the caller). */
async function fillRequired(page: Page, title: string, notes?: string): Promise<void> {
  await fillStable(page.getByTestId('opp-title-input'), title);
  const type = page.getByTestId('opp-type-select');
  await waitForHydration(type);
  if ((await type.evaluate((el) => el.tagName)) === 'SELECT') {
    await type.selectOption('workshop');
  } else {
    await type.getByText('Workshop / training', { exact: true }).first().click();
  }
  await fillStable(page.getByTestId('opp-summary-input'), `Multi-location e2e (${RUN}).`);
  await pickPython(page);
  await fillDeadline(page, 10);
  if (notes) await fillStable(page.getByTestId('opp-internal-notes-input'), notes);
}

/** Type into an input with real keystrokes (so a typed comma fires per char). */
async function typeInto(input: Locator, text: string): Promise<void> {
  await waitForHydration(input);
  await input.click();
  await input.pressSequentially(text);
}

async function publicPage(browser: Browser, label: string): Promise<{ ctx: BrowserContext; page: Page }> {
  const ctx = await browser.newContext();
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

function card(page: Page, title: string): Locator {
  return page.getByTestId('opportunity-card').filter({ hasText: title });
}

async function gotoBoardNewest(page: Page): Promise<void> {
  await page.goto(BOARD_NEWEST);
  await expect(page.getByTestId('board-page')).toBeVisible();
  await expect(
    page.locator('[data-testid="opportunity-card"], [data-testid="board-empty"]').first(),
  ).toBeVisible();
}

async function expectListing(page: Page, id: number, title: string, detail: string): Promise<void> {
  await page.goto(`${ORIGIN}/opportunities/${id}`);
  await expect(page.getByTestId('opportunity-detail')).toBeVisible();
  await expect(page.getByTestId('opportunity-title')).toHaveText(title);
  await expect(page.getByTestId('opportunity-location')).toHaveText(detail);
}

async function publishViaApi(title: string, body: Record<string, unknown>): Promise<number> {
  const res = await api.post('/api/admin/opportunities', {
    data: {
      title,
      type: 'workshop',
      summary: `Format vector (${RUN}).`,
      description_md: 'Fixture listing.',
      topic_ids: [pythonTopicId],
      deadline: isoDaysFromNow(10),
      status: 'open',
      ...body,
    },
  });
  expect(res.ok(), `POST /api/admin/opportunities → ${res.status()}: ${await res.text()}`).toBeTruthy();
  const id = (await res.json()).data.opportunity.id as number;
  createdIds.push(id);
  return id;
}

// ---------------------------------------------------------------- journey

test.describe.serial('Phase 11c — multi-location opportunities, end to end', () => {
  test.beforeAll(async ({ browser, playwright }) => {
    api = await playwright.request.newContext({
      baseURL: ORIGIN,
      extraHTTPHeaders: { 'X-Admin-Key': adminKey() },
    });
    const topicsRes = await api.get('/api/admin/topics');
    expect(topicsRes.ok()).toBeTruthy();
    const python = ((await topicsRes.json()).data.topics as Array<{ id: number; slug: string }>).find(
      (t) => t.slug === 'python',
    );
    expect(python, 'seeded topic `python` must exist').toBeTruthy();
    pythonTopicId = python!.id;

    adminCtx = await browser.newContext();
    adminCtx.setDefaultTimeout(15_000);
    adminCtx.setDefaultNavigationTimeout(30_000);
    admin = await adminCtx.newPage();
    admin.on('pageerror', (err) => errors.push(`admin: ${String(err)}`));
    admin.on('dialog', (d) => d.accept().catch(() => undefined));
  });

  test.afterAll(async () => {
    // The roadmap gate checks the public payload after e2e for multi-city,
    // legacy and remote listings, so these are deliberately left open.
    if (api) await api.dispose();
    if (adminCtx) await adminCtx.close();
  });

  test('1. chips: Enter, comma, dedupe, country; preview shows +1', async () => {
    await signInAdmin(admin);
    await openNewEditor(admin);
    await fillRequired(admin, TITLE, INTERNAL_NOTES);
    await setMode(admin, 'hybrid');

    const city = admin.getByTestId('opp-location-city-input');
    const country = admin.getByTestId('opp-location-country-input');
    await fillStable(city, 'Bengaluru');
    await fillStable(country, 'India');
    await country.press('Enter');
    await expectChips(admin, ['Bengaluru, India']);

    await typeInto(city, 'Pune,');
    await expectChips(admin, ['Bengaluru, India', 'Pune']);

    await city.fill('Hyderabad, pune');
    await expectChips(admin, ['Bengaluru, India', 'Pune', 'Hyderabad']);
    await expect(city).toHaveValue('pune');
    await city.press('Enter');

    await expectChips(admin, ['Bengaluru, India', 'Pune', 'Hyderabad']);
    await expect(admin.getByTestId('opp-locations-hint')).toHaveText('Already added');
    await expect(city).toHaveValue('');
    await expect(admin.getByTestId('opp-preview-location')).toHaveText(
      'Bengaluru · Pune · +1 · Hybrid',
    );
  });

  test('2. remove and re-add a chip', async () => {
    const pune = chips(admin).filter({ hasText: /^Pune/ });
    await pune.getByTestId('opp-location-chip-remove').click();
    await expectChips(admin, ['Bengaluru, India', 'Hyderabad']);
    await expect(admin.getByTestId('opp-preview-location')).toHaveText(
      'Bengaluru · Hyderabad · Hybrid',
    );
    const city = admin.getByTestId('opp-location-city-input');
    await fillStable(city, 'Pune');
    await city.press('Enter');
    await expectChips(admin, ['Bengaluru, India', 'Hyderabad', 'Pune']);
  });

  test('3. Remote hides the chips; back to Hybrid restores them', async () => {
    await setMode(admin, 'remote');
    await expect(admin.getByTestId('opp-locations')).toHaveCount(0);
    await expect(admin.getByTestId('opp-preview-location')).toHaveText('Remote');
    await setMode(admin, 'hybrid');
    await expectChips(admin, ['Bengaluru, India', 'Hyderabad', 'Pune']);
  });

  test('4. typed-but-unadded city is committed on Publish', async () => {
    await typeInto(admin.getByTestId('opp-location-city-input'), 'Chennai');
    const posted = admin.waitForResponse(
      (r) =>
        r.request().method() === 'POST' &&
        new URL(r.url()).pathname === '/api/admin/opportunities',
    );
    const publish = admin.getByTestId('opp-publish');
    await waitForHydration(publish);
    await publish.click();
    const res = await posted;
    expect(res.status(), `publish → ${res.status()}: ${await res.text()}`).toBe(200);
    const opp = (await res.json()).data.opportunity;
    multiId = opp.id;
    createdIds.push(multiId);
    expect(opp.status).toBe('open');
    expect(opp.locations).toEqual([
      { city: 'Bengaluru', country: 'India' },
      { city: 'Hyderabad', country: null },
      { city: 'Pune', country: null },
      { city: 'Chennai', country: null },
    ]);
    expect(opp.city).toBe('Bengaluru');
  });

  test('5. public card and listing show every location; nothing internal leaks', async ({
    browser,
  }) => {
    const { ctx, page } = await publicPage(browser, 'public-5');
    try {
      await gotoBoardNewest(page);
      const c = card(page, TITLE);
      await expect(c).toHaveCount(1);
      const loc = c.getByTestId('opportunity-location');
      await expect(loc).toHaveText('Bengaluru · Hyderabad · +2 · Hybrid');
      await expect(loc).toHaveAttribute('title', 'Bengaluru, Hyderabad, Pune, Chennai');
      for (const html of [await page.content()]) {
        expect(html).not.toContain('ZZ-INTERNAL');
        expect(html).not.toContain('locations_json');
      }
      await expectListing(
        page,
        multiId,
        TITLE,
        'Bengaluru, India · Hyderabad · Pune · Chennai · Hybrid',
      );
      const html = await page.content();
      expect(html).not.toContain('ZZ-INTERNAL');
      expect(html).not.toContain('locations_json');
    } finally {
      await ctx.close();
    }
  });

  test('6. format vectors on card and listing', async ({ browser }) => {
    const vectors: Array<{ title: string; body: Record<string, unknown>; card: string; detail: string }> = [
      {
        title: `Legacy Pune ${RUN}`,
        body: { location_mode: 'onsite', city: 'Pune' },
        card: 'Pune · Onsite',
        detail: 'Pune · Onsite',
      },
      {
        title: `Two cities ${RUN}`,
        body: {
          location_mode: 'hybrid',
          locations: [
            { city: 'Bengaluru', country: null },
            { city: 'Pune', country: null },
          ],
        },
        card: 'Bengaluru · Pune · Hybrid',
        detail: 'Bengaluru · Pune · Hybrid',
      },
      {
        title: `Five cities ${RUN}`,
        body: {
          location_mode: 'onsite',
          locations: ['Delhi', 'Noida', 'Gurugram', 'Jaipur', 'Agra'].map((city) => ({
            city,
            country: null,
          })),
        },
        card: 'Delhi · Noida · +3 · Onsite',
        detail: 'Delhi · Noida · Gurugram · Jaipur · Agra · Onsite',
      },
      {
        title: `Remote only ${RUN}`,
        body: { location_mode: 'remote' },
        card: 'Remote',
        detail: 'Remote',
      },
    ];
    const ids: number[] = [];
    for (const v of vectors) ids.push(await publishViaApi(v.title, v.body));
    legacyId = ids[0];

    const { ctx, page } = await publicPage(browser, 'public-6');
    try {
      await gotoBoardNewest(page);
      for (const v of vectors) {
        const c = card(page, v.title);
        await expect(c, `card ${v.title} on page 1 (newest)`).toHaveCount(1);
        await expect(c.getByTestId('opportunity-location')).toHaveText(v.card);
      }
      for (const [i, v] of vectors.entries()) await expectListing(page, ids[i], v.title, v.detail);
    } finally {
      await ctx.close();
    }
  });

  test('7. errors: no city on Onsite, 10-chip cap, 81-char city', async () => {
    const title = `Errors ${RUN}`;
    await openNewEditor(admin);
    await fillRequired(admin, title);
    await setMode(admin, 'onsite');
    await expect(chips(admin)).toHaveCount(0);

    const save = admin.getByTestId('opp-save-draft');
    await waitForHydration(save);
    await save.click();
    await expect(admin.getByTestId('opp-locations-error')).toContainText('add at least one city');
    await expect(admin.getByTestId('opp-title-input')).toHaveValue(title);
    await expect(admin.getByTestId('opp-location-select')).toHaveValue('onsite');

    const city = admin.getByTestId('opp-location-city-input');
    await city.fill('x'.repeat(81));
    await city.press('Enter');
    await expect(admin.getByTestId('opp-locations-error')).toHaveText(
      'City must be 80 characters or fewer',
    );
    await expect(chips(admin)).toHaveCount(0);

    const ten = Array.from({ length: 10 }, (_, i) => `City${'abcdefghij'[i]}`);
    await city.fill(ten.join(', '));
    await city.press('Enter');
    await expect(chips(admin)).toHaveCount(10);
    await expect(city).toBeDisabled();
    await expect(admin.getByTestId('opp-locations-hint')).toHaveText('Up to 10 locations');
  });

  test('8. a legacy single-city listing opens as one chip', async () => {
    expect(legacyId).toBeGreaterThan(0);
    await admin.goto(`${ADMIN_OPPS_URL}edit/?id=${legacyId}`);
    await expect(admin.getByTestId('opp-title-input')).toHaveValue(`Legacy Pune ${RUN}`, {
      timeout: 15_000,
    });
    await expectChips(admin, ['Pune']);
    expect(errors, errors.join('\n')).toEqual([]);
  });
});
