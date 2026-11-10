import {
  test,
  expect,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import { APP_BASE, ORIGIN, adminKey, signInAdmin, waitForHydration, fillStable } from './helpers';

/**
 * Phase 13 — workshop tie-in (roadmap.md §Phase 13 e2e plan, V3; api.md
 * §Workshop tie-in). Admin links a trainer to a workshop through the
 * Facilitators picker and through Link as facilitator on a Selected applicant;
 * the trainer's My Workshop0 workshops card shows it; removal empties it while
 * the admin token keeps working; a signed-out participant sees Join our network.
 * Self-seeding with a per-run suffix; asserts only on its own rows.
 */

const RUN = `t${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;
const EMAIL = `tiein-${RUN}@example.test`;
const WS1_NAME = `Tiein WS One ${RUN}`;
const WS2_NAME = `Tiein WS Two ${RUN}`;
const LISTING_TITLE = `Tiein co-facilitation ${RUN}`;
const NETWORK_HEADERS = { 'X-Requested-With': 'workshop0' };

let admin: APIRequestContext;
let ctx: BrowserContext;
let profileId = 0;
let ws1: any;
let ws2: any;
let opportunityId = 0;

function data<T = any>(body: any): T {
  return (body && typeof body === 'object' && 'data' in body ? body.data : body) as T;
}

async function createWorkshop(name: string) {
  const res = await admin.post('/api/admin/workshops', {
    data: {
      name,
      milestones: [
        { title: 'Milestone one', content_md: 'first', minutes: 5 },
        { title: 'Milestone two', content_md: 'second', minutes: 5 },
      ],
    },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  return data(await res.json()).workshop;
}

async function myWorkshops(): Promise<any[]> {
  const res = await ctx.request.get(`${ORIGIN}/api/me/workshops`);
  expect(res.ok(), await res.text()).toBeTruthy();
  return data(await res.json()).workshops;
}

async function facilitators(workshopId: number): Promise<any[]> {
  const res = await admin.get(`/api/admin/workshops/${workshopId}/facilitators`);
  expect(res.ok(), await res.text()).toBeTruthy();
  return data(await res.json()).facilitators;
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser, playwright }) => {
  test.setTimeout(120_000);
  admin = await playwright.request.newContext({
    baseURL: ORIGIN,
    extraHTTPHeaders: { 'X-Admin-Key': adminKey() },
  });
  ws1 = await createWorkshop(WS1_NAME);
  ws2 = await createWorkshop(WS2_NAME);

  const topics = data(await (await admin.get('/api/admin/topics')).json()).topics as Array<{ id: number; slug: string }>;
  const topic = topics.find((t) => t.slug === 'generative-ai') ?? topics[0];

  ctx = await browser.newContext();
  ctx.setDefaultTimeout(15_000);
  ctx.setDefaultNavigationTimeout(30_000);
  const page = await ctx.newPage();
  await page.goto(`${ORIGIN}/api/auth/google/start?next=${encodeURIComponent('/app/network/')}`);
  const field = page.getByTestId('fake-oidc-email');
  await expect(field).toBeVisible({ timeout: 15_000 });
  await field.fill(EMAIL);
  await Promise.all([
    page.waitForURL((u) => u.origin === ORIGIN && u.pathname.startsWith('/app/'), { timeout: 30_000 }),
    page.getByTestId('fake-oidc-signin').click(),
  ]);
  const create = await ctx.request.post(`${ORIGIN}/api/me/profile`, {
    headers: NETWORK_HEADERS,
    data: {
      headline: `Tiein trainer ${RUN}`,
      topics: [{ slug: topic.slug, level: 'advanced' }],
      consent: true,
    },
  });
  expect(create.status(), await create.text()).toBe(200);
  const prof = await ctx.request.get(`${ORIGIN}/api/me/profile`);
  profileId = data(await prof.json()).profile.id;
  await page.close();

  const opp = await admin.post('/api/admin/opportunities', {
    data: {
      title: LISTING_TITLE,
      type: 'cofacilitation',
      summary: `Tie-in fixture (${RUN}).`,
      description_md: 'Co-facilitate a workshop.',
      topic_ids: [topic.id],
      location_mode: 'remote',
      deadline: new Date(Date.now() + 10 * 86_400_000).toISOString().replace(/\.\d{3}Z$/, 'Z'),
      status: 'open',
    },
  });
  expect(opp.ok(), await opp.text()).toBeTruthy();
  opportunityId = data(await opp.json()).opportunity.id;
});

test.afterAll(async () => {
  if (admin && opportunityId) await admin.patch(`/api/admin/opportunities/${opportunityId}`, { data: { status: 'closed' } });
  await admin?.dispose();
  await ctx?.close();
});

test('before any link the trainer card is empty', async () => {
  const page = await ctx.newPage();
  await page.goto(`${APP_BASE}/network/me/`);
  await expect(page.getByTestId('my-workshops')).toBeVisible();
  await expect(page.getByTestId('workshop-row').filter({ hasText: WS1_NAME })).toHaveCount(0);
  expect((await myWorkshops()).some((w) => w.name === WS1_NAME)).toBe(false);
  await page.close();
});

test('admin adds the trainer as co through the Facilitators picker on the workshop card', async ({ browser }) => {
  test.setTimeout(90_000);
  const adminCtx = await browser.newContext();
  const page = await adminCtx.newPage();
  await signInAdmin(page);
  const card = page.getByTestId('workshop-card').filter({ hasText: WS1_NAME }).first();
  await expect(card).toBeVisible({ timeout: 20_000 });
  const button = card.getByTestId('facilitators-button');
  await waitForHydration(button);
  await button.click();
  const picker = page.getByTestId('facilitators-picker');
  await expect(picker).toBeVisible();
  await expect(page.getByTestId('facilitators-empty')).toBeVisible();
  await fillStable(page.getByTestId('facilitators-search'), EMAIL);
  await page.getByTestId('facilitators-search-button').click();
  const result = page.getByTestId('facilitators-result').filter({ hasText: EMAIL });
  await expect(result).toHaveCount(1);
  await result.getByRole('button', { name: 'Add' }).click();
  await expect(page.getByTestId('facilitator-row')).toHaveCount(1);
  await page.getByTestId('facilitators-save').click();
  await expect(picker).toBeHidden({ timeout: 15_000 });

  const list = await facilitators(ws1.id);
  expect(list).toHaveLength(1);
  expect(list[0].profile_id).toBe(profileId);
  expect(list[0].role).toBe('co');
  await adminCtx.close();
});

test("trainer's My Workshop0 workshops shows the workshop, role and a working dashboard link", async () => {
  const page = await ctx.newPage();
  await page.goto(`${APP_BASE}/network/me/`);
  const row = page.getByTestId('workshop-row').filter({ hasText: WS1_NAME });
  await expect(row).toHaveCount(1, { timeout: 20_000 });
  await expect(row).toContainText('co');
  const link = row.getByTestId('workshop-dashboard-link');
  await expect(link).toHaveAttribute('href', new RegExp(`/f/${ws1.admin_token}$`));
  await link.click();
  await expect(page.getByTestId('dashboard-page')).toBeVisible({ timeout: 20_000 });
  await page.close();
});

test('Link as facilitator on a Selected applicant of a cofacilitation listing', async ({ browser }) => {
  test.setTimeout(120_000);
  // Trainer applies (API), admin selects (API), then links through the pipeline UI.
  const apply = await ctx.request.post(`${ORIGIN}/api/me/applications`, {
    headers: NETWORK_HEADERS,
    data: { opportunity_id: opportunityId, note: `Tie-in ${RUN}` },
  });
  expect(apply.ok(), await apply.text()).toBeTruthy();
  const apps = await admin.get(`/api/admin/opportunities/${opportunityId}/applications`);
  expect(apps.ok(), await apps.text()).toBeTruthy();
  const rows = (data(await apps.json()).items ?? data(await apps.json()).applications) as Array<any>;
  const mine = rows.find((r) => r.trainer?.email === EMAIL);
  expect(mine, 'application row').toBeTruthy();
  const sel = await admin.post(`/api/admin/opportunities/${opportunityId}/applications/status`, {
    data: { application_ids: [mine.id], status: 'selected', notify: false },
  });
  expect(sel.ok(), await sel.text()).toBeTruthy();

  const adminCtx = await browser.newContext();
  const page = await adminCtx.newPage();
  await signInAdmin(page);
  await page.goto(`${ORIGIN}/app/admin/opportunities/pipeline/?id=${opportunityId}`);
  await expect(page.getByTestId('pipeline-board')).toBeVisible({ timeout: 20_000 });
  const row = page.getByTestId('pipeline-group-selected').getByTestId('pipeline-row').filter({ hasText: EMAIL });
  await expect(row).toHaveCount(1);
  const linkBtn = row.getByTestId('link-facilitator-button');
  await waitForHydration(linkBtn);
  await linkBtn.click();
  // The listing has no workshop, so the button asks which workshop first.
  await page.getByTestId('link-facilitator-workshop').selectOption({ label: WS2_NAME });
  await page.getByTestId('link-facilitator-confirm').click();
  await expect(row.getByTestId('link-facilitator-done')).toBeVisible({ timeout: 15_000 });

  const list = await facilitators(ws2.id);
  expect(list.map((f) => [f.profile_id, f.role])).toEqual([[profileId, 'co']]);
  const names = (await myWorkshops()).map((w) => w.name);
  expect(names).toEqual(expect.arrayContaining([WS1_NAME, WS2_NAME]));
  await adminCtx.close();
});

test('admin removes the links: card empties, /api/me/workshops is [], admin token still works', async () => {
  for (const ws of [ws1, ws2]) {
    const res = await admin.put(`/api/admin/workshops/${ws.id}/facilitators`, { data: { facilitators: [] } });
    expect(res.ok(), await res.text()).toBeTruthy();
    expect(await facilitators(ws.id)).toEqual([]);
  }
  expect(await myWorkshops()).toEqual([]);

  const page = await ctx.newPage();
  await page.goto(`${APP_BASE}/network/me/`);
  await expect(page.getByTestId('workshops-empty')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId('workshop-row')).toHaveCount(0);

  // The workshop's admin token is untouched.
  const wsRes = await admin.get(`/api/f/${ws1.admin_token}/workshop`);
  expect(wsRes.ok(), await wsRes.text()).toBeTruthy();
  await page.goto(`${APP_BASE}/f/?t=${encodeURIComponent(ws1.admin_token)}`);
  await expect(page.getByTestId('dashboard-page')).toBeVisible({ timeout: 20_000 });
  await page.close();
});

test('signed-out participant sees Join our network, joins, completes everything, card shows again', async ({ browser }) => {
  test.setTimeout(90_000);
  const anonCtx = await browser.newContext();
  const page: Page = await anonCtx.newPage();
  await page.goto(`${ORIGIN}/j/${ws1.join_slug}`);
  const card = page.getByTestId('join-network-card');
  await expect(card).toBeVisible({ timeout: 20_000 });
  await expect(card.getByRole('link', { name: 'Join our network' })).toHaveAttribute('href', '/network');

  await fillStable(page.getByTestId('join-name-input'), `Tiein Participant ${RUN}`);
  await page.getByTestId('join-submit').click();
  await page.waitForURL((u) => u.pathname.startsWith('/app/p/'), { timeout: 30_000 });
  await expect(page.getByTestId('tracker-page')).toBeVisible({ timeout: 20_000 });

  // Participant token from the URL; complete every milestone through the API.
  const token = new URL(page.url()).searchParams.get('t');
  expect(token).toBeTruthy();
  const state = data(await (await anonCtx.request.get(`${ORIGIN}/api/p/${token}/state?v=-1`)).json());
  expect(state.milestones.length).toBe(2);
  for (const m of state.milestones) {
    const done = await anonCtx.request.post(`${ORIGIN}/api/p/${token}/milestones/${m.id}/complete`, { data: {} });
    expect(done.ok(), await done.text()).toBeTruthy();
  }
  await page.reload();
  await expect(page.getByTestId('join-network-card')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByTestId('join-network-card').getByRole('link', { name: 'Join our network' })).toHaveAttribute('href', '/network');
  // No sign-in was needed: never bounced to the OIDC issuer.
  expect(new URL(page.url()).origin).toBe(ORIGIN);
  await anonCtx.close();
});
