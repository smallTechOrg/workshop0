import { test, expect, type APIRequestContext, type BrowserContext, type Page } from '@playwright/test';
import { ORIGIN, adminKey, signInAdmin, waitForHydration } from './helpers';

/**
 * Phase 12 — Apply -> bulk move (with email) -> status visible to the trainer
 * (roadmap.md §Phase 12 slice D1, api.md §Phase 12 C14/C16).
 *
 * Self-seeding over the API (fresh trainer via the fake OIDC issuer, fresh open
 * listing via the admin API); every identifier carries RUN. Helpers are private.
 */
const RUN = `ap${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const TRAINER_EMAIL = `apply-trainer-${RUN}@example.test`;
const TITLE = `Apply Pipeline ${RUN}`;
const NOTE = `Happy to run this (${RUN}).`;
const NETWORK_HEADERS = { 'X-Requested-With': 'workshop0' };

let admin: APIRequestContext;
let trainerCtx: BrowserContext;
let opportunityId = 0;
let slug = '';

const data = (b: any) => (b && typeof b === 'object' && 'data' in b ? b.data : b);

async function completeIssuer(page: Page, email: string): Promise<void> {
  await expect(page.getByTestId('fake-oidc-email')).toBeVisible({ timeout: 15_000 });
  await page.getByTestId('fake-oidc-email').fill(email);
  await Promise.all([
    page.waitForURL((u) => u.origin === ORIGIN && !u.pathname.startsWith('/authorize'), { timeout: 30_000 }),
    page.getByTestId('fake-oidc-signin').click(),
  ]);
}

test.describe.serial('Phase 12 — apply and applicant pipeline', () => {
  test.beforeAll(async ({ playwright, browser }) => {
    test.setTimeout(120_000);
    admin = await playwright.request.newContext({
      baseURL: ORIGIN,
      extraHTTPHeaders: { 'X-Admin-Key': adminKey() },
    });
    const topics = data(await (await admin.get('/api/admin/topics')).json()).topics as Array<{ id: number; slug: string }>;
    const topic = topics.find((t) => t.slug === 'generative-ai') ?? topics[0];
    const res = await admin.post('/api/admin/opportunities', {
      data: {
        title: TITLE,
        type: 'workshop',
        summary: `Apply fixture (${RUN}).`,
        description_md: 'A hands-on workshop.',
        topic_ids: [topic.id],
        location_mode: 'remote',
        deadline: new Date(Date.now() + 10 * 86_400_000).toISOString().replace(/\.\d{3}Z$/, 'Z'),
        status: 'open',
      },
    });
    expect(res.ok(), await res.text()).toBeTruthy();
    const opp = data(await res.json()).opportunity;
    opportunityId = opp.id;
    slug = opp.slug;

    trainerCtx = await browser.newContext();
    const page = await trainerCtx.newPage();
    await page.goto(`${ORIGIN}/api/auth/google/start?next=${encodeURIComponent('/app/network/')}`);
    await completeIssuer(page, TRAINER_EMAIL);
    const create = await trainerCtx.request.post(`${ORIGIN}/api/me/profile`, {
      headers: NETWORK_HEADERS,
      data: {
        headline: `Apply trainer ${RUN}`,
        bio_md: `Seeded by apply-pipeline.spec.ts (${RUN}).`,
        city: 'Bengaluru',
        remote_ok: true,
        topics: [{ slug: topic.slug, level: 'advanced' }],
        consent: true,
      },
    });
    expect(create.status(), await create.text()).toBe(200);
    await page.close();
  });

  test.afterAll(async () => {
    if (admin && opportunityId) await admin.patch(`/api/admin/opportunities/${opportunityId}`, { data: { status: 'closed' } });
    await admin?.dispose();
    await trainerCtx?.close();
  });

  test('trainer applies with a note on the listing and sees Applied', async () => {
    const page = await trainerCtx.newPage();
    await page.goto(`${ORIGIN}/opportunities/${slug}`);
    await expect(page.getByTestId('opportunity-title')).toHaveText(TITLE, { timeout: 20_000 });
    const form = page.getByTestId('apply-form');
    await expect(form).toBeVisible({ timeout: 20_000 });
    await waitForHydration(form);
    await page.locator('#apply-note').fill(NOTE);
    await page.getByTestId('apply-submit').click();
    await expect(page.getByTestId('apply-status')).toHaveText(/applied/i);
    await page.close();
  });

  test('admin selects the applicant, moves to Shortlisted with email, trainer sees it', async ({ browser }) => {
    test.setTimeout(120_000);
    const adminCtx = await browser.newContext();
    const page = await adminCtx.newPage();
    await signInAdmin(page);
    await page.goto(`${ORIGIN}/app/admin/opportunities/pipeline/?id=${opportunityId}`);
    await expect(page.getByTestId('pipeline-board')).toBeVisible({ timeout: 20_000 });
    const row = page.getByTestId('pipeline-group-applied').getByTestId('pipeline-row').filter({ hasText: TRAINER_EMAIL });
    await expect(row).toHaveCount(1);
    await expect(row).toContainText(NOTE);
    await waitForHydration(row);
    await row.getByRole('checkbox').check();
    await expect(page.getByTestId('pipeline-selected-count')).toHaveText('1 selected');
    await page.getByTestId('pipeline-move-select').selectOption('shortlisted');
    await expect(page.getByTestId('pipeline-notify')).toBeChecked();
    await page.getByTestId('pipeline-move-button').click();
    await expect(
      page.getByTestId('pipeline-group-shortlisted').getByTestId('pipeline-row').filter({ hasText: TRAINER_EMAIL }),
    ).toHaveCount(1);

    // One status email for the trainer (API view of the outbox; delivered or recorded, never lost).
    await expect
      .poll(
        async () => {
          const items = data(await (await admin.get('/api/admin/outbox')).json()).items as Array<any>;
          return items.filter((r) => r.to === TRAINER_EMAIL && r.template === 'application.status_changed').length;
        },
        { timeout: 20_000 },
      )
      .toBe(1);

    // Trainer's view.
    const t = await trainerCtx.newPage();
    await t.goto(`${ORIGIN}/app/network/applications/`);
    const app = t.getByTestId('app-row').filter({ hasText: TITLE });
    await expect(app).toHaveCount(1, { timeout: 20_000 });
    await expect(app).toContainText(/shortlisted/i);
    await t.goto(`${ORIGIN}/opportunities/${slug}`);
    await expect(t.getByTestId('apply-status')).toHaveText(/shortlisted/i, { timeout: 20_000 });
    await t.close();
    await adminCtx.close();
  });

  test('error path: applying twice is refused (already_applied)', async () => {
    const res = await trainerCtx.request.post(`${ORIGIN}/api/me/applications`, {
      headers: NETWORK_HEADERS,
      data: { opportunity_id: opportunityId, note: 'again' },
    });
    expect(res.status()).toBe(409);
    expect(JSON.stringify(await res.json())).toContain('already_applied');
  });
});
