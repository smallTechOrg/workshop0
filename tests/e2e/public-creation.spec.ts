import {
  test,
  expect,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import {
  APP_BASE,
  LANDING_URL,
  ORIGIN,
  adminKey,
  adminWorkshopCard,
  extractUrl,
  fillComposer,
  signInAdmin,
  submitPublicCreate,
} from './helpers';

/**
 * Phase 6 core journey (roadmap.md §Phase 6 "How the user tests it") — a
 * stranger, in a browser that NEVER sends an access key:
 *
 *   land on / → click the CTA → compose a 3-milestone workshop with a markdown
 *   list and a fenced code block → a bad email is rejected inline and creates
 *   NOTHING → a valid email reveals the dashboard + join links → Priya joins in
 *   a second browser and completes a milestone → she appears live on the
 *   creator's own dashboard within one poll → the creator has FULL facilitator
 *   parity (broadcast, pause, audit — nothing locked) → and the admin, at
 *   /admin, sees that same workshop in the full list with a Public origin badge
 *   and the creator email that was typed.
 *
 * Every run creates a FRESH workshop (timestamped name); live-update waits are
 * polling assertions sized to one poll cycle (dashboard 2 s), never sleeps.
 */

const WORKSHOP_NAME = `E2E Public Creation ${Date.now()}`;
const CREATOR_EMAIL = `e2e.public.${Date.now()}@example.com`;
const BAD_EMAIL = 'no-at.example.com';

const M1_TITLE = 'Set up your environment';
const M2_TITLE = 'Call the health endpoint';
const M3_TITLE = 'Ship it';

const M1_CONTENT = [
  'Before you start, check off the basics:',
  '',
  '- A terminal you can type in',
  '- Python 3.12 installed',
  '- Ten minutes of quiet',
].join('\n');
const M2_CONTENT = ['Run this and confirm it says ok:', '', '```bash', 'curl -s /api/health', '```'].join(
  '\n',
);
const M3_CONTENT = 'Push your branch and open a pull request.';

const BROADCAST_MD = '**Five minutes left** — wrap up your current milestone.';

let creatorCtx: BrowserContext;
let priyaCtx: BrowserContext;
let adminCtx: BrowserContext;
let creator: Page;
let priya: Page;
let admin: Page;

let dashboardUrl = '';
let joinUrl = '';

const uncaughtErrors: Array<{ page: string; message: string }> = [];

/** Every request this browser context makes must be keyless (no X-Admin-Key). */
function forbidAdminKey(ctx: BrowserContext, label: string): void {
  ctx.on('request', (req) => {
    const headers = req.headers();
    if (headers['x-admin-key'] !== undefined) {
      uncaughtErrors.push({
        page: label,
        message: `sent an X-Admin-Key header to ${req.url()} — this journey must be keyless`,
      });
    }
  });
}

/** Does the admin all-workshops list hold a workshop with this exact name? */
async function adminSeesWorkshop(request: APIRequestContext, name: string): Promise<boolean> {
  const res = await request.get(`${ORIGIN}/api/admin/workshops`, {
    headers: { 'X-Admin-Key': adminKey() },
  });
  expect(res.ok(), 'GET /api/admin/workshops must succeed').toBeTruthy();
  const body = await res.json();
  const rows: Array<{ name: string }> = body.data.workshops;
  return rows.some((w) => w.name === name);
}

test.describe.serial('Phase 6 — keyless public creation, end to end', () => {
  test.beforeAll(async ({ browser }) => {
    const mk = async (label: string, keyless: boolean) => {
      const ctx = await browser.newContext({ baseURL: APP_BASE });
      ctx.setDefaultTimeout(15_000);
      ctx.setDefaultNavigationTimeout(30_000);
      if (keyless) forbidAdminKey(ctx, label);
      const page = await ctx.newPage();
      page.on('pageerror', (err) => uncaughtErrors.push({ page: label, message: String(err) }));
      return { ctx, page };
    };
    ({ ctx: creatorCtx, page: creator } = await mk('creator', true));
    ({ ctx: priyaCtx, page: priya } = await mk('priya', true));
    ({ ctx: adminCtx, page: admin } = await mk('admin', false));
  });

  test.afterAll(async () => {
    await Promise.all([creatorCtx, priyaCtx, adminCtx].filter(Boolean).map((ctx) => ctx.close()));
  });

  test('a stranger reaches the composer from the landing toolkit CTA and composes 3 milestones', async () => {
    await creator.goto(LANDING_URL);
    await expect(creator.getByTestId('landing-hero')).toBeVisible();

    await creator.getByTestId('landing-workshop-cta').click();
    await expect(creator.getByTestId('create-page')).toBeVisible({ timeout: 15_000 });
    expect(new URL(creator.url()).pathname).toBe('/app/create/');
    // No key gate anywhere on the public create flow.
    await expect(creator.getByTestId('admin-key-input')).toHaveCount(0);

    await fillComposer(creator, WORKSHOP_NAME, [
      { title: M1_TITLE, content: M1_CONTENT },
      { title: M2_TITLE, content: M2_CONTENT },
      { title: M3_TITLE, content: M3_CONTENT },
    ]);
  });

  test('an invalid email is rejected inline and creates nothing', async ({ request }) => {
    const attempted = creator
      .waitForResponse(
        (r) => r.url().includes('/api/public/workshops') && r.request().method() === 'POST',
        { timeout: 8000 },
      )
      .catch(() => null);

    await submitPublicCreate(creator, BAD_EMAIL);

    // If the client did call the API, it must have been rejected 422
    // validation_error (api.md §POST /api/public/workshops).
    const res = await attempted;
    if (res) {
      expect(res.status()).toBe(422);
      const body = await res.json();
      expect(body.error.code).toBe('validation_error');
    }

    // Inline field error, no success reveal.
    await expect(creator.getByTestId('email-error')).toBeVisible();
    await expect(creator.getByTestId('create-success')).toHaveCount(0);

    // The composed workshop is preserved (C6 §Errors: "never lost").
    await expect(creator.getByTestId('workshop-name-input')).toHaveValue(WORKSHOP_NAME);

    // And nothing was persisted — the admin list does not know this workshop.
    expect(
      await adminSeesWorkshop(request, WORKSHOP_NAME),
      'a rejected email must create zero rows',
    ).toBe(false);
  });

  test('a valid email creates the workshop and reveals the dashboard + join links', async () => {
    const created = creator.waitForResponse(
      (r) => r.url().includes('/api/public/workshops') && r.request().method() === 'POST',
    );
    await submitPublicCreate(creator, CREATOR_EMAIL);
    const res = await created;
    expect(res.ok(), 'POST /api/public/workshops must succeed').toBeTruthy();
    const workshop = (await res.json()).data.workshop;
    expect(workshop.created_via).toBe('public');
    expect(workshop.creator_email).toBe(CREATOR_EMAIL);

    const success = creator.getByTestId('create-success');
    await expect(success).toBeVisible({ timeout: 15_000 });
    // The "this link is the only key" warning is load-bearing (C6 §Success screen).
    await expect(success).toContainText(/only key|save it/i);

    dashboardUrl = extractUrl(await success.getByTestId('success-dashboard-link').innerText(), '/f/');
    joinUrl = extractUrl(await success.getByTestId('success-join-link').innerText(), '/j/');
    expect(dashboardUrl).toMatch(/\/f\/[A-Za-z0-9_-]{20,}$/);
    expect(joinUrl).toMatch(/\/j\/[A-Za-z0-9_-]{6,}$/);
    await expect(success.getByTestId('success-copy-dashboard')).toBeVisible();
  });

  test('Priya joins from a second browser and completes a milestone', async () => {
    await priya.goto(joinUrl);
    await expect(priya).toHaveURL(/\/app\/join\/\?s=[A-Za-z0-9_-]+/);
    await expect(priya.getByText(WORKSHOP_NAME).first()).toBeVisible();

    await priya.getByTestId('join-name-input').fill('Priya');
    const joined = priya.waitForResponse(
      (r) => /\/api\/join\/[^/?]+$/.test(r.url().split('?')[0]) && r.request().method() === 'POST',
    );
    await priya.getByTestId('join-submit').click();
    expect((await joined).ok(), 'POST /api/join/{slug} must succeed').toBeTruthy();

    await expect(priya.getByTestId('tracker-page')).toBeVisible({ timeout: 15_000 });
    const items = priya.getByTestId('milestone-item');
    await expect(items).toHaveCount(3);

    // The composed markdown reached the participant RENDERED, not raw.
    await expect(items.first().locator('li').first()).toContainText('A terminal you can type in');
    await expect(items.first()).not.toContainText('```');

    const completed = priya.waitForResponse(
      (r) =>
        /\/milestones\/\d+\/complete$/.test(r.url().split('?')[0]) && r.request().method() === 'POST',
    );
    await items.first().getByTestId('milestone-toggle').click();
    expect((await completed).ok(), 'complete endpoint must succeed').toBeTruthy();
  });

  test("Priya and her progress appear on the creator's dashboard within one poll", async () => {
    await creator.goto(dashboardUrl);
    await expect(creator).toHaveURL(/\/app\/f\/\?t=[A-Za-z0-9_-]+/);
    const dashboard = creator.getByTestId('dashboard-page');
    await expect(dashboard).toBeVisible();
    await expect(dashboard).toContainText(WORKSHOP_NAME);
    await expect(creator.getByTestId('milestone-stat')).toHaveCount(3);

    const priyaRow = creator.getByTestId('participant-row').filter({ hasText: 'Priya' }).first();
    await expect(priyaRow).toBeVisible({ timeout: 15_000 });
    await expect(priyaRow.getByTestId('participant-progress')).toContainText(/\b1\b|33/, {
      timeout: 15_000,
    });
    await expect(creator.getByTestId('milestone-stat').first()).toContainText(/\b1\b|100/, {
      timeout: 15_000,
    });

    // The creator email is never shown on a facilitator surface (C7).
    await expect(dashboard).not.toContainText(CREATOR_EMAIL);
  });

  test('facilitator parity on a public-created workshop: broadcast, pause and audit all work', async () => {
    // Broadcast — reaches Priya's tracker rendered.
    await creator.getByTestId('broadcast-button').click();
    await creator.getByTestId('broadcast-textarea').fill(BROADCAST_MD);
    const sent = creator.waitForResponse(
      (r) =>
        /\/api\/f\/[^/]+\/broadcast$/.test(r.url().split('?')[0]) && r.request().method() === 'POST',
    );
    await creator.getByTestId('broadcast-submit').click();
    expect((await sent).ok(), 'POST …/broadcast must succeed for a public creator').toBeTruthy();

    const banner = priya.getByTestId('broadcast-banner');
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toContainText('Five minutes left');
    await expect(banner).not.toContainText('**Five');

    // Pause — locks Priya's completion toggle; resume unlocks it.
    const paused = creator.waitForResponse(
      (r) => /\/api\/f\/[^/]+\/pause$/.test(r.url().split('?')[0]) && r.request().method() === 'POST',
    );
    await creator.getByTestId('pause-button').click();
    expect((await paused).ok(), 'POST …/pause must succeed for a public creator').toBeTruthy();
    await expect(priya.getByTestId('paused-banner')).toBeVisible({ timeout: 15_000 });

    const resumed = creator.waitForResponse(
      (r) => /\/api\/f\/[^/]+\/pause$/.test(r.url().split('?')[0]) && r.request().method() === 'POST',
    );
    await creator.getByTestId('pause-button').click();
    expect((await resumed).ok(), 'POST …/pause (resume) must succeed').toBeTruthy();
    await expect(priya.getByTestId('paused-banner')).toHaveCount(0, { timeout: 15_000 });

    // Audit — the full trail is available, with this journey's actions in it.
    await creator.getByTestId('audit-tab').click();
    const rows = creator.getByTestId('audit-row');
    await expect(rows.first()).toBeVisible();
    await expect(rows.filter({ hasText: /broadcast/i }).first()).toBeVisible();
    await expect(rows.filter({ hasText: /pause/i }).first()).toBeVisible();

    // Nothing is a reduced tier: the parity controls themselves are REAL —
    // enabled, not aria-disabled, and carrying no "later phase" stub badge.
    // (The dashboard legitimately renders by-design labelled stubs for genuinely
    // later-phase features — End workshop, AI help-desk, the stubbed stat card —
    // identically for admin- and public-created workshops; core-loop.spec.ts
    // requires them to be present. Parity is about the controls below.)
    for (const id of ['broadcast-button', 'pause-button', 'audit-tab'] as const) {
      const control = creator.getByTestId(id);
      await expect(control, `${id} must be present for a public creator`).toBeVisible();
      await expect(control, `${id} must be enabled for a public creator`).toBeEnabled();
      await expect(control).not.toHaveAttribute('aria-disabled', 'true');
      await expect(
        control.getByTestId('stub-badge'),
        `${id} must not be a labelled stub for a public creator`,
      ).toHaveCount(0);
    }
  });

  test('the admin sees the workshop in the full list with a Public badge and the creator email', async () => {
    await signInAdmin(admin);
    // Reached via the pretty /admin URL too.
    await admin.goto(`${ORIGIN}/admin`);
    expect(new URL(admin.url()).pathname).toBe('/app/admin/');

    const card = adminWorkshopCard(admin, WORKSHOP_NAME);
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card.getByTestId('workshop-origin-badge')).toContainText(/public/i);
    await expect(card.getByTestId('workshop-creator-email')).toContainText(CREATOR_EMAIL);
  });

  test('the creating browser never sent an access key, and no page threw', async () => {
    const detail = uncaughtErrors.map((e) => `[${e.page}] ${e.message}`).join('\n');
    expect(uncaughtErrors, detail || 'clean').toEqual([]);
  });
});
