import { test, expect, type APIRequestContext, type BrowserContext, type Page } from '@playwright/test';
import { ORIGIN, adminKey, signInAdmin, waitForHydration } from './helpers';

/**
 * Phase 12 — Suggested trainers (real Anthropic call on the server) -> Invite to
 * apply -> the trainer sees an Invited badge in Matched for you
 * (roadmap.md §Phase 12 slice D1, api.md §Phase 12 C15). Self-seeding, private helpers.
 */
const RUN = `mt${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const TRAINER_EMAIL = `match-trainer-${RUN}@example.test`;
const TITLE = `Matching ${RUN}`;
const NETWORK_HEADERS = { 'X-Requested-With': 'workshop0' };

let admin: APIRequestContext;
let trainerCtx: BrowserContext;
let opportunityId = 0;

const data = (b: any) => (b && typeof b === 'object' && 'data' in b ? b.data : b);

async function completeIssuer(page: Page, email: string): Promise<void> {
  await expect(page.getByTestId('fake-oidc-email')).toBeVisible({ timeout: 15_000 });
  await page.getByTestId('fake-oidc-email').fill(email);
  await Promise.all([
    page.waitForURL((u) => u.origin === ORIGIN && !u.pathname.startsWith('/authorize'), { timeout: 30_000 }),
    page.getByTestId('fake-oidc-signin').click(),
  ]);
}

test.describe.serial('Phase 12 — matching and invite to apply', () => {
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
        summary: `Matching fixture (${RUN}).`,
        description_md: 'A hands-on workshop for engineers.',
        topic_ids: [topic.id],
        location_mode: 'remote',
        deadline: new Date(Date.now() + 10 * 86_400_000).toISOString().replace(/\.\d{3}Z$/, 'Z'),
        status: 'open',
      },
    });
    expect(res.ok(), await res.text()).toBeTruthy();
    opportunityId = data(await res.json()).opportunity.id;

    trainerCtx = await browser.newContext();
    const page = await trainerCtx.newPage();
    await page.goto(`${ORIGIN}/api/auth/google/start?next=${encodeURIComponent('/app/network/')}`);
    await completeIssuer(page, TRAINER_EMAIL);
    const create = await trainerCtx.request.post(`${ORIGIN}/api/me/profile`, {
      headers: NETWORK_HEADERS,
      data: {
        headline: `Match trainer ${RUN}`,
        bio_md: `Seeded by matching.spec.ts (${RUN}). Runs GenAI workshops.`,
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

  test('admin runs Suggested trainers, invites the trainer; trainer sees Invited', async ({ browser }) => {
    test.setTimeout(180_000);
    const adminCtx = await browser.newContext();
    const page = await adminCtx.newPage();
    await signInAdmin(page);
    await page.goto(`${ORIGIN}/app/admin/opportunities/pipeline/?id=${opportunityId}`);
    const panel = page.getByTestId('suggested-trainers');
    await expect(panel).toBeVisible({ timeout: 20_000 });
    await waitForHydration(panel.getByTestId('suggest-run'));
    await panel.getByTestId('suggest-run').click();

    // Real Anthropic call: wait for the list and the run cost.
    await expect(panel.getByTestId('suggest-list')).toBeVisible({ timeout: 120_000 });
    await expect(panel.getByTestId('suggest-cost')).toContainText('$');
    const row = panel.getByTestId('suggest-row').filter({ hasText: `Match trainer ${RUN}` });
    await expect(row).toHaveCount(1);
    await expect(row.getByTestId('suggest-reason')).not.toBeEmpty();
    await row.getByRole('button', { name: /^Invite .* to apply$/ }).click();
    await expect(row.getByText('Invited', { exact: true })).toBeVisible();

    // Trainer: Matched for you shows the Invited badge.
    const t = await trainerCtx.newPage();
    await t.goto(`${ORIGIN}/app/network/matches/`);
    const match = t.getByTestId('match-row').filter({ hasText: TITLE });
    await expect(match).toHaveCount(1, { timeout: 20_000 });
    await expect(match).toContainText('Invited');
    await t.close();
    await adminCtx.close();
  });

  test('error path: inviting a profile that does not exist is refused', async () => {
    const res = await admin.post(`/api/admin/opportunities/${opportunityId}/invites`, { data: { profile_ids: [] } });
    expect(res.status()).toBeGreaterThanOrEqual(400);
    expect(res.status()).toBeLessThan(500);
  });
});
