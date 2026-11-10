import * as fs from 'node:fs';
import { test, expect, type APIRequestContext, type BrowserContext, type Page } from '@playwright/test';
import { ORIGIN, adminKey, waitForHydration } from './helpers';

/**
 * Phase 13 — saved searches, instant alerts, unsubscribe and the weekly digest
 * (roadmap.md §Phase 13 slice V1, api.md §Phase 13 C17).
 *
 * Instances (the gate starts them, one shared database):
 *   - ORIGIN (BASE_URL)        SMTP -> fake sink, WORKSHOP0_CRON_KEY set
 *   - FAIL_ORIGIN (:8013)      SMTP -> a closed port (every send fails)
 *   - UNCONF_ORIGIN (:8014)    SMTP unset and cron key unset
 * SMTP_DUMP_FILE: JSON-lines dump of the sink (`{to, subject, text, html}`); the
 * message-content assertions run only when it is set.
 * Self-seeding; presence-only assertions (other specs publish to the same DB).
 */
const RUN = `ad${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const FAIL_ORIGIN = (process.env.FAIL_ORIGIN || 'http://localhost:8013').replace(/\/+$/, '');
const UNCONF_ORIGIN = (process.env.UNCONF_ORIGIN || 'http://localhost:8014').replace(/\/+$/, '');
const BASE_URL = (process.env.WORKSHOP0_BASE_URL || ORIGIN).replace(/\/+$/, '');
const DUMP = process.env.SMTP_DUMP_FILE;
const CRON_KEY = process.env.WORKSHOP0_CRON_KEY || 'ci-cron-key-0123456789';

const TRAINER_EMAIL = `alert-trainer-${RUN}@example.test`;
const CITY = `AlertCity${RUN}`;
const CITY2 = `AlertTwo${RUN}`;
const PARTNER_PUBLIC = `Public Partner ${RUN}`;
const PARTNER_INTERNAL = `Internal Secret Co ${RUN}`;
const HEADERS = { 'X-Requested-With': 'workshop0' };

const data = (b: any) => (b && typeof b === 'object' && 'data' in b ? b.data : b);
const title = (n: string) => `Alert ${n} ${RUN}`;

let main: APIRequestContext;
let failing: APIRequestContext;
let unconf: APIRequestContext;
let trainerCtx: BrowserContext;
let topic: { id: number; slug: string };
const ids: Array<{ api: APIRequestContext; id: number }> = [];
let firstId = 0;
let firstSlug = '';

async function adminApi(playwright: any, origin: string): Promise<APIRequestContext> {
  return playwright.request.newContext({ baseURL: origin, extraHTTPHeaders: { 'X-Admin-Key': adminKey() } });
}

async function completeIssuer(page: Page, email: string): Promise<void> {
  await expect(page.getByTestId('fake-oidc-email')).toBeVisible({ timeout: 15_000 });
  await page.getByTestId('fake-oidc-email').fill(email);
  await Promise.all([
    page.waitForURL((u) => u.origin === ORIGIN && !u.pathname.startsWith('/authorize'), { timeout: 30_000 }),
    page.getByTestId('fake-oidc-signin').click(),
  ]);
}

async function publish(api: APIRequestContext, name: string): Promise<{ id: number; slug: string; status: string }> {
  const res = await api.post('/api/admin/opportunities', {
    data: {
      title: title(name),
      type: 'workshop',
      summary: `Alert fixture (${RUN}).`,
      description_md: 'A hands-on workshop.',
      topic_ids: [topic.id],
      location_mode: 'onsite',
      locations: [
        { city: CITY, country: null },
        { city: CITY2, country: null },
      ],
      compensation_min: 8000,
      compensation_max: 12000,
      compensation_currency: 'INR',
      compensation_unit: 'day',
      partner_display_name: PARTNER_PUBLIC,
      partner_internal_name: PARTNER_INTERNAL,
      deadline: new Date(Date.now() + 10 * 86_400_000).toISOString().replace(/\.\d{3}Z$/, 'Z'),
      status: 'open',
    },
  });
  expect(res.status(), await res.text()).toBe(200);
  const opp = data(await res.json()).opportunity;
  ids.push({ api, id: opp.id });
  return opp;
}

async function alertRows(api: APIRequestContext, name: string, template = 'network.alert'): Promise<any[]> {
  const items = data(await (await api.get('/api/admin/outbox')).json()).items as Array<any>;
  return items.filter(
    (r) => r.to === TRAINER_EMAIL && r.template === template && (name ? String(r.subject).includes(title(name)) : true),
  );
}

function dumpMessages(name: string): any[] {
  if (!DUMP || !fs.existsSync(DUMP)) return [];
  return fs
    .readFileSync(DUMP, 'utf8')
    .split('\n')
    .filter((l) => l.includes(TRAINER_EMAIL) && l.includes(title(name)))
    .map((l) => JSON.parse(l));
}

async function openAdmin(page: Page, origin: string, path: string, testId: string): Promise<void> {
  await page.goto(`${origin}/app/admin/`);
  const key = page.getByTestId('admin-key-input');
  await expect
    .poll(() => key.evaluate((el) => Object.keys(el).some((k) => k.startsWith('__reactProps'))), { timeout: 30_000 })
    .toBe(true);
  await key.fill(adminKey());
  await page.getByTestId('admin-key-submit').click();
  await expect(page.getByTestId('new-workshop-button')).toBeVisible({ timeout: 15_000 });
  await page.goto(`${origin}/app/admin/${path}`);
  await expect(page.getByTestId(testId).first()).toBeVisible({ timeout: 20_000 });
}

test.describe.serial('Phase 13 — alerts, unsubscribe and weekly digest', () => {
  test.beforeAll(async ({ playwright, browser }) => {
    test.setTimeout(120_000);
    main = await adminApi(playwright, ORIGIN);
    failing = await adminApi(playwright, FAIL_ORIGIN);
    unconf = await adminApi(playwright, UNCONF_ORIGIN);
    const topics = data(await (await main.get('/api/admin/topics')).json()).topics as Array<{ id: number; slug: string }>;
    topic = topics.find((t) => t.slug === 'generative-ai') ?? topics[0];

    trainerCtx = await browser.newContext();
    const page = await trainerCtx.newPage();
    await page.goto(`${ORIGIN}/api/auth/google/start?next=${encodeURIComponent('/app/network/')}`);
    await completeIssuer(page, TRAINER_EMAIL);
    const create = await trainerCtx.request.post(`${ORIGIN}/api/me/profile`, {
      headers: HEADERS,
      data: {
        headline: `Alert trainer ${RUN}`,
        bio_md: `Seeded by alerts-digest.spec.ts (${RUN}).`,
        city: CITY,
        remote_ok: true,
        topics: [{ slug: topic.slug, level: 'advanced' }],
        consent: true,
      },
    });
    expect(create.status(), await create.text()).toBe(200);
    await page.close();
  });

  test.afterAll(async () => {
    for (const { api, id } of ids) await api.patch(`/api/admin/opportunities/${id}`, { data: { status: 'closed' } }).catch(() => undefined);
    await main?.dispose();
    await failing?.dispose();
    await unconf?.dispose();
    await trainerCtx?.close();
  });

  test('trainer saves a board search (topic) and a city search', async () => {
    const page = await trainerCtx.newPage();
    await page.goto(`${ORIGIN}/app/opportunities/?topic=${topic.slug}`);
    const save = page.getByTestId('save-search-button');
    await expect(save).toBeVisible({ timeout: 20_000 });
    await waitForHydration(save);
    await expect(save).toBeEnabled();
    await save.click();
    await expect(page.getByTestId('save-search-saved')).toBeVisible({ timeout: 15_000 });

    // The city search: the Saved searches page has no create form, so use the API
    // (the page is then asserted to list both).
    const res = await trainerCtx.request.post(`${ORIGIN}/api/me/searches`, {
      headers: HEADERS,
      data: { name: `City ${RUN}`, criteria: { types: [], topic_slugs: [], location_modes: [], cities: [CITY] }, alerts_enabled: true },
    });
    expect(res.status(), await res.text()).toBe(200);

    await page.goto(`${ORIGIN}/app/network/searches/`);
    await expect(page.getByTestId('searches-list')).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('search-row')).toHaveCount(2);
    await expect(page.getByTestId('search-row').filter({ hasText: `City ${RUN}` })).toHaveCount(1);
    await page.close();
  });

  test('publishing a matching listing sends one alert with the public partner, pay, cities and links', async () => {
    const opp = await publish(main, 'one');
    firstId = opp.id;
    firstSlug = opp.slug;
    await expect.poll(async () => (await alertRows(main, 'one'))[0]?.status, { timeout: 30_000 }).toBe('sent');
    expect(await alertRows(main, 'one')).toHaveLength(1); // two matching searches, one email

    if (DUMP) {
      await expect.poll(() => dumpMessages('one').length, { timeout: 20_000 }).toBeGreaterThan(0);
      const text: string = dumpMessages('one')[0].text;
      expect(text).toContain(PARTNER_PUBLIC);
      expect(text).not.toContain(PARTNER_INTERNAL);
      expect(text).toContain('per day');
      expect(text).toMatch(/8,?000/);
      expect(text).toContain(CITY);
      expect(text).toContain(CITY2);
      expect(text).toContain(`${BASE_URL}/opportunities/${firstSlug}`);
      expect(text).toContain(`${BASE_URL}/api/email/unsubscribe?t=`);
    }
  });

  test('unsubscribe link: GET only confirms (no change), the Unsubscribe click turns alerts off, digest stays on', async ({ playwright, browser }) => {
    const link = DUMP
      ? (dumpMessages('one')[0].text.match(/https?:\/\/[^\s"'<>]*\/api\/email\/unsubscribe\?t=[^\s"'<>]+/) ?? [])[0]
      : undefined;
    expect(DUMP ? link : 'n/a', 'unsubscribe link in the delivered message').toBeTruthy();
    if (link) {
      const u = new URL(link);
      const anon = await playwright.request.newContext({ baseURL: ORIGIN });
      const res = await anon.get(`${u.pathname}${u.search}`, { maxRedirects: 0 });
      expect(res.status()).toBe(303);
      expect(res.headers()['location']).toContain('/app/network/unsubscribed/?confirm=alerts');
      await anon.dispose();
      // A prefetching mail scanner would stop here: nothing changed yet.
      const before = data(await (await trainerCtx.request.get(`${ORIGIN}/api/me/email-prefs`)).json());
      expect(before).toMatchObject({ alerts: true, digest: true });

      const ctx = await browser.newContext();
      const page = await ctx.newPage();
      await page.goto(`${ORIGIN}${u.pathname}${u.search}`);
      await expect(page.getByTestId('unsubscribe-question')).toContainText('new-opportunity alerts');
      await page.getByTestId('unsubscribe-confirm').click();
      await expect(page.getByTestId('unsubscribed-message')).toContainText("You're unsubscribed from new-opportunity alerts");
      await ctx.close();
    }
    const prefs = data(await (await trainerCtx.request.get(`${ORIGIN}/api/me/email-prefs`)).json());
    if (link) expect(prefs).toMatchObject({ alerts: false, digest: true });
  });

  test('after unsubscribing, close/reopen and a second matching listing send no new alerts', async () => {
    const before = (await alertRows(main, '')).length;
    expect((await main.patch(`/api/admin/opportunities/${firstId}`, { data: { status: 'closed' } })).ok()).toBeTruthy();
    expect((await main.patch(`/api/admin/opportunities/${firstId}`, { data: { status: 'open' } })).ok()).toBeTruthy();
    await publish(main, 'two');
    await new Promise((r) => setTimeout(r, 3_000));
    expect(await alertRows(main, 'two')).toHaveLength(0);
    expect(await alertRows(main, 'one')).toHaveLength(1);
    expect((await alertRows(main, '')).length).toBe(before);
  });

  test('failing SMTP: publish still succeeds, the alert row ends failed after 3 attempts', async () => {
    const res = await trainerCtx.request.patch(`${ORIGIN}/api/me/email-prefs`, { headers: HEADERS, data: { alerts: true } });
    expect(res.ok(), await res.text()).toBeTruthy();
    const opp = await publish(failing, 'fail');
    expect(opp.status).toBe('open');
    await expect.poll(async () => (await alertRows(failing, 'fail'))[0]?.status, { timeout: 60_000 }).toBe('failed');
    expect((await alertRows(failing, 'fail'))[0].attempts).toBe(3);
  });

  test('SMTP unset: the alert row is recorded and the Outbox page labels it not sent', async ({ browser }) => {
    await publish(unconf, 'unconf');
    await expect.poll(async () => (await alertRows(unconf, 'unconf'))[0]?.status, { timeout: 30_000 }).toBe('recorded');
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await openAdmin(page, UNCONF_ORIGIN, 'outbox/', 'outbox-row');
    const row = page.getByTestId('outbox-row').filter({ hasText: title('unconf') }).filter({ hasText: TRAINER_EMAIL });
    await expect(row).toHaveCount(1);
    await expect(row).toHaveAttribute('data-status', 'recorded');
    await expect(row).toContainText('Not sent');
    await ctx.close();
  });

  test('weekly digest: 401 without the key, enqueues once with it, idempotent, 404 when unconfigured', async ({ playwright }) => {
    const anon = await playwright.request.newContext({ baseURL: ORIGIN });
    expect((await anon.post('/api/cron/weekly-digest')).status()).toBe(401);
    expect((await anon.post('/api/cron/weekly-digest', { headers: { 'X-Cron-Key': 'wrong-key' } })).status()).toBe(401);

    const ok = await anon.post('/api/cron/weekly-digest', { headers: { 'X-Cron-Key': CRON_KEY } });
    expect(ok.status(), await ok.text()).toBe(200);
    const body = data(await ok.json());
    expect(body.enqueued).toBeGreaterThanOrEqual(1);
    await expect.poll(async () => (await alertRows(main, '', 'network.digest'))[0]?.status, { timeout: 30_000 }).toBe('sent');

    const again = await anon.post('/api/cron/weekly-digest', { headers: { 'X-Cron-Key': CRON_KEY } });
    expect(again.status()).toBe(200);
    expect(data(await again.json()).enqueued).toBe(0);
    await anon.dispose();

    const off = await playwright.request.newContext({ baseURL: UNCONF_ORIGIN });
    expect((await off.post('/api/cron/weekly-digest')).status()).toBe(404);
    expect((await off.post('/api/cron/weekly-digest', { headers: { 'X-Cron-Key': CRON_KEY } })).status()).toBe(404);
    await off.dispose();
  });
});
