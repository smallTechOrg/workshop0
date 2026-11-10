import {
  test,
  expect,
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import { APP_BASE, ORIGIN, adminKey, waitForHydration } from './helpers';

/**
 * Phase 13 — public trainer directory (roadmap.md §Phase 13 e2e plan, V2;
 * api.md §Phase 13 "Public directory" + "Server-rendered trainer pages").
 *
 * Trainer A reaches 60 % (headline, bio >= 80 chars, 3 topics, location, link,
 * one past-work item) and carries sentinel values in rate / admin note / tag.
 * Trainer B has headline + 1 topic (20 %). Both switch **Public directory
 * profile** on in My profile; only A is listed. Public surfaces are probed
 * unauthenticated and must never expose a sentinel, an email or numeric ids.
 * Self-seeding with a per-run suffix; asserts only on its own rows.
 */

const RUN = `d${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;
const EMAIL_A = `dir-a-${RUN}@example.test`;
const EMAIL_B = `dir-b-${RUN}@example.test`;
const HEADLINE_A = `Directory trainer A ${RUN}`;
const HEADLINE_B = `Directory trainer B ${RUN}`;
const NOTE_SENTINEL = `NOTESENTINEL${RUN}`;
const TAG_SENTINEL = `tagsentinel-${RUN}`;
const RATE_MIN = 7777;
const RATE_MAX = 8888;
const NETWORK_HEADERS = { 'X-Requested-With': 'workshop0' };

const CARD_KEYS = [
  'avatar_url', 'display_name', 'headline', 'city', 'links', 'public_url',
  'remote_ok', 'slug', 'topics', 'verified',
].sort();
const DETAIL_KEYS = [...CARD_KEYS, 'bio_md', 'past_work'].sort();

let ctxA: BrowserContext;
let ctxB: BrowserContext;
let pageA: Page;
let pageB: Page;
let admin: APIRequestContext;
let idA = 0;
let idB = 0;
let slugA = '';
let slugB = '';
let topicSlugs: string[] = [];
let topicOnlyA: { slug: string; name: string };

function data<T = any>(body: any): T {
  return (body && typeof body === 'object' && 'data' in body ? body.data : body) as T;
}

async function signInDirect(page: Page, email: string, next: string): Promise<void> {
  await page.goto(`${ORIGIN}/api/auth/google/start?next=${encodeURIComponent(next)}`);
  const field = page.getByTestId('fake-oidc-email');
  await expect(field).toBeVisible({ timeout: 15_000 });
  await field.fill(email);
  await Promise.all([
    page.waitForURL((u) => u.origin === ORIGIN && u.pathname.startsWith('/app/'), { timeout: 30_000 }),
    page.getByTestId('fake-oidc-signin').click(),
  ]);
}

async function newTrainer(browser: Browser, email: string) {
  const ctx = await browser.newContext();
  ctx.setDefaultTimeout(15_000);
  ctx.setDefaultNavigationTimeout(30_000);
  const page = await ctx.newPage();
  await signInDirect(page, email, '/app/network/');
  return { ctx, page };
}

async function ownProfile(ctx: BrowserContext) {
  const res = await ctx.request.get(`${ORIGIN}/api/me/profile`);
  expect(res.ok()).toBeTruthy();
  return data(await res.json()).profile;
}

/** Click the My profile directory toggle and wait for the status to settle. */
async function toggleDirectory(page: Page, status: RegExp): Promise<void> {
  await page.goto(`${APP_BASE}/network/me/`);
  const toggle = page.getByTestId('directory-toggle');
  await waitForHydration(toggle);
  await toggle.click();
  await expect(page.getByTestId('directory-status')).toHaveText(status);
}

/** Unauthenticated GET (no cookies), no redirects followed. */
async function anon(path: string) {
  return admin.get(`${ORIGIN}${path}`, { maxRedirects: 0, headers: { 'X-Admin-Key': '' } });
}

async function anonText(path: string) {
  const res = await anon(path);
  return { status: res.status(), text: await res.text() };
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser, playwright }) => {
  test.setTimeout(120_000);
  admin = await playwright.request.newContext({
    baseURL: ORIGIN,
    extraHTTPHeaders: { 'X-Admin-Key': adminKey() },
  });
  const topicsRes = await admin.get('/api/public/topics');
  expect(topicsRes.ok()).toBeTruthy();
  const raw = data(await topicsRes.json());
  const topics: Array<{ slug: string; name: string; active?: boolean }> = (
    Array.isArray(raw) ? raw : raw.topics
  ).filter((t: any) => t.active !== false);
  expect(topics.length, 'at least 4 curated topics').toBeGreaterThanOrEqual(4);
  topicSlugs = topics.map((t) => t.slug);
  topicOnlyA = topics[0];

  ({ ctx: ctxA, page: pageA } = await newTrainer(browser, EMAIL_A));
  ({ ctx: ctxB, page: pageB } = await newTrainer(browser, EMAIL_B));

  const a = await ctxA.request.post(`${ORIGIN}/api/me/profile`, {
    headers: NETWORK_HEADERS,
    data: {
      headline: HEADLINE_A,
      bio_md: `Trainer A (${RUN}) teaches hands-on generative AI engineering workshops for product teams, with labs and code reviews.`,
      city: 'Pune',
      remote_ok: true,
      linkedin_url: `https://www.linkedin.com/in/dir-a-${RUN}`,
      topics: [
        { slug: topics[0].slug, level: 'expert' },
        { slug: topics[1].slug, level: 'advanced' },
        { slug: topics[2].slug, level: 'advanced' },
      ],
      past_work: [{ title: `Workshop for Acme ${RUN}`, kind: 'workshop', org: 'Acme', year: 2024 }],
      rate_min: RATE_MIN,
      rate_max: RATE_MAX,
      rate_currency: 'INR',
      rate_unit: 'day',
      pro_bono: false,
      consent: true,
    },
  });
  expect(a.status(), await a.text()).toBe(200);
  const pa = await ownProfile(ctxA);
  idA = pa.id;

  const b = await ctxB.request.post(`${ORIGIN}/api/me/profile`, {
    headers: NETWORK_HEADERS,
    data: { headline: HEADLINE_B, topics: [{ slug: topics[3].slug, level: 'advanced' }], consent: true },
  });
  expect(b.status(), await b.text()).toBe(200);
  idB = (await ownProfile(ctxB)).id;

  // Admin-only sentinels: a note and a tag on A.
  const note = await admin.post(`/api/admin/network/trainers/${idA}/notes`, { data: { body: NOTE_SENTINEL } });
  expect(note.ok(), await note.text()).toBeTruthy();
  const tags = await admin.put(`/api/admin/network/trainers/${idA}/tags`, { data: { tags: [TAG_SENTINEL] } });
  expect(tags.ok(), await tags.text()).toBeTruthy();
});

test.afterAll(async () => {
  await ctxA?.close();
  await ctxB?.close();
  await admin?.dispose();
});

test('both trainers switch Public directory profile on; A is Listed, B is told to reach 60 %', async () => {
  await toggleDirectory(pageA, /^Listed$/);
  const dirA = (await ownProfile(ctxA)).directory;
  expect(dirA.listed).toBe(true);
  expect(dirA.path).toMatch(/^\/trainers\/[a-z0-9-]+$/);
  slugA = dirA.path.replace('/trainers/', '');
  await expect(pageA.getByTestId('directory-link')).toHaveAttribute('href', dirA.path);

  await toggleDirectory(pageB, /Complete your profile to 60%/);
  const dirB = (await ownProfile(ctxB)).directory;
  expect(dirB.listed).toBe(false);
  await expect(pageB.getByTestId('directory-link')).toHaveCount(0);
  slugB = dirB.path ? dirB.path.replace('/trainers/', '') : '';
});

test('anonymous /trainers/{A} is a 200 server-rendered page with SEO and no private data', async () => {
  const { status, text } = await anonText(`/trainers/${slugA}`);
  expect(status).toBe(200);
  expect(text).toMatch(/<title>[^<]*Directory trainer A[^<]*<\/title>/);
  expect(text).toMatch(/<link[^>]+rel="canonical"[^>]+href="[^"]*\/trainers\/[^"]+"/);
  const ld = text.match(/<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/);
  expect(ld, 'JSON-LD block').not.toBeNull();
  const json = JSON.parse(ld![1]);
  expect(json['@type']).toBe('Person');
  for (const secret of [NOTE_SENTINEL, TAG_SENTINEL, String(RATE_MIN), String(RATE_MAX), EMAIL_A, 'example.test']) {
    expect(text, `HTML must not contain ${secret}`).not.toContain(secret);
  }
  const block = text.split('<!--w0-seo-->')[1]?.split('<!--/w0-seo-->')[0] ?? '';
  expect(block.length).toBeGreaterThan(0);
  expect(block).not.toContain(`"${idA}"`);
  expect(block).not.toMatch(/user_id|profile_id/);
});

test('public JSON exposes exactly the allow-listed keys and no sentinel', async () => {
  const detailRes = await anon(`/api/public/trainers/${slugA}`);
  expect(detailRes.status()).toBe(200);
  const detailText = await detailRes.text();
  const detail = data(JSON.parse(detailText));
  expect(Object.keys(detail).sort()).toEqual(DETAIL_KEYS);
  expect(detail.slug).toBe(slugA);
  expect(detail.headline).toBe(HEADLINE_A);

  // Find A in the paginated list.
  let card: any = null;
  let listText = '';
  for (let page = 1; page <= 50 && !card; page++) {
    const res = await anon(`/api/public/trainers?page=${page}`);
    expect(res.status()).toBe(200);
    const t = await res.text();
    const body = data(JSON.parse(t));
    const found = body.items.find((i: any) => i.slug === slugA);
    if (found) {
      card = found;
      listText = t;
    }
    if (page * body.page_size >= body.total) break;
  }
  expect(card, 'A is in the public list').not.toBeNull();
  expect(Object.keys(card).sort()).toEqual(CARD_KEYS);
  for (const text of [detailText, listText]) {
    for (const secret of [NOTE_SENTINEL, TAG_SENTINEL, EMAIL_A, String(RATE_MIN), String(RATE_MAX)]) {
      expect(text).not.toContain(secret);
    }
    expect(text).not.toMatch(/"(id|user_id|profile_id|email|rate_min|pro_bono|tags|notes)"/);
  }
});

test('directory page shows A and not B; topic filter narrows to A', async ({ page }) => {
  // Locate A's page in the (shared, paginated) directory through the API.
  let pageNo = 1;
  for (; pageNo <= 50; pageNo++) {
    const body = data(await (await anon(`/api/public/trainers?page=${pageNo}`)).json());
    if (body.items.some((i: any) => i.slug === slugA)) break;
  }
  await page.goto(`${APP_BASE}/network/directory/${pageNo > 1 ? `?page=${pageNo}` : ''}`);
  await expect(page.getByTestId('directory-grid')).toBeVisible();
  const cardA = page.getByTestId('trainer-card').filter({ has: page.locator(`a[href$="/trainers/${slugA}"]`) });
  await expect(cardA).toHaveCount(1);
  await expect(cardA).toContainText(HEADLINE_A);
  await expect(page.getByTestId('trainer-card').filter({ hasText: HEADLINE_B })).toHaveCount(0);

  // Topic filter: A's first topic is held by A, not by B.
  const filtered = data(await (await anon(`/api/public/trainers?topic=${topicOnlyA.slug}`)).json());
  expect(filtered.items.some((i: any) => i.slug === slugA)).toBe(true);
  expect(filtered.items.some((i: any) => i.headline === HEADLINE_B)).toBe(false);
  await page.goto(`${APP_BASE}/network/directory/?topic=${topicOnlyA.slug}`);
  await expect(page.getByTestId('directory-topic-filter')).toHaveValue(topicOnlyA.slug);
  await expect(page.getByTestId('trainer-card').filter({ hasText: HEADLINE_B })).toHaveCount(0);
  await expect(page.getByTestId('trainer-card').filter({ hasText: HEADLINE_A })).toHaveCount(1);
});

test('B is not listed anywhere: every route returns 404 (HTML with noindex)', async () => {
  const keys = [slugB, String(idB)].filter(Boolean);
  for (const key of keys) {
    const api = await anon(`/api/public/trainers/${key}`);
    expect(api.status(), `api ${key}`).toBe(404);
  }
  expect((await anon(`/api/public/trainers/${idA}`)).status(), 'numeric id of a listed trainer').toBe(404);
  for (const key of keys) {
    const { status, text } = await anonText(`/trainers/${key}`);
    expect(status, `page ${key}`).toBe(404);
    expect(text).toMatch(/<meta\s+name="robots"\s+content="noindex"/);
    expect(text).not.toContain(HEADLINE_B);
  }
  const { status, text } = await anonText('/sitemap.xml');
  expect(status).toBe(200);
  expect(text).toContain(`/trainers/${slugA}<`);
  if (slugB) expect(text).not.toContain(`/trainers/${slugB}<`);
  expect(text).not.toContain(`/trainers/${idA}<`);
});

test('admin verifies A and the verified badge shows on the trainer page', async ({ page }) => {
  const res = await admin.post(`/api/admin/network/trainers/${idA}/verify`);
  expect(res.ok(), await res.text()).toBeTruthy();
  expect(data(JSON.parse(await (await anon(`/api/public/trainers/${slugA}`)).text())).verified).toBe(true);

  await page.goto(`${ORIGIN}/trainers/${slugA}`);
  const trainerPage = page.getByTestId('trainer-page');
  await expect(trainerPage).toBeVisible();
  await expect(trainerPage).toContainText(HEADLINE_A);
  await expect(page.getByTestId('verified-badge').first()).toBeVisible();
  await expect(page.locator('body')).not.toContainText(NOTE_SENTINEL);
  await expect(page.locator('body')).not.toContainText(String(RATE_MIN));
});

test('A switches to private: page 404s and leaves the sitemap; switching back restores the same slug', async () => {
  await toggleDirectory(pageA, /^Private/);
  expect((await anon(`/api/public/trainers/${slugA}`)).status()).toBe(404);
  const gone = await anonText(`/trainers/${slugA}`);
  expect(gone.status).toBe(404);
  expect(gone.text).toMatch(/<meta\s+name="robots"\s+content="noindex"/);
  expect((await anonText('/sitemap.xml')).text).not.toContain(`/trainers/${slugA}<`);

  await toggleDirectory(pageA, /^Listed$/);
  const dir = (await ownProfile(ctxA)).directory;
  expect(dir.path).toBe(`/trainers/${slugA}`);
  expect((await anonText(`/trainers/${slugA}`)).status).toBe(200);
  expect((await anonText('/sitemap.xml')).text).toContain(`/trainers/${slugA}<`);
});
