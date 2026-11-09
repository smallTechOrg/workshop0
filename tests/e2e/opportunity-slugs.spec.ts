import { test, expect, type APIRequestContext, type Browser, type BrowserContext, type Page } from '@playwright/test';
import { ADMIN_BASE, APP_BASE, ORIGIN, adminKey, signInAdmin, waitForHydration } from './helpers';

/**
 * Phase 11e — Opportunity slugs & SEO (roadmap.md §Phase 11e "e2e journey (E3)",
 * api.md §Phase 11e). Runs against the live single-origin app on :8001.
 *
 * A hybrid listing is published via the admin API; a stranger opens it from
 * the board and lands on `/opportunities/{slug}`; legacy id URLs end on the
 * slug URL; the raw (no-JS) HTML carries the SEO head + JobPosting JSON-LD and
 * nothing internal; the slug survives a rename; closing it adds noindex and
 * drops it from the sitemap; a draft's slug is a 404 that leaks nothing.
 *
 * The e2e DB is shared across runs — every name carries RUN (lower-case
 * alphanumerics, so it survives slugification unchanged).
 */

const RUN = `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const TITLE = `Slug Test ${RUN} Zürich`;
const RENAMED = `Renamed ${RUN}`;
const INTERNAL_NOTE = `ZZ-INTERNAL-${RUN}`;
const SENTINEL_PARTNER = `ZZ-SENTINEL-PARTNER-${RUN}`;
const DRAFT_TITLE = `ZZ-DRAFT-${RUN}`;
const SLUG_RE = new RegExp(`^slug-test-${RUN}-zurich-bengaluru-[0-9a-f]{4,6}$`);

let api: APIRequestContext;
let opportunityId = 0;
let slug = '';
let publicUrl = '';
let draftSlug = '';
let draftId = 0;
let partnerId = 0;
const errors: string[] = [];

function isoDaysFromNow(days: number): string {
  return new Date(Date.now() + days * 86_400_000).toISOString().replace(/\.\d{3}Z$/, 'Z');
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

async function topicId(slugName: string): Promise<number> {
  const res = await api.get('/api/admin/topics');
  expect(res.ok(), `GET /api/admin/topics → ${res.status()}`).toBeTruthy();
  const t = ((await res.json()).data.topics as Array<{ id: number; slug: string }>).find((x) => x.slug === slugName);
  expect(t, `seeded topic ${slugName} must exist`).toBeTruthy();
  return t!.id;
}

async function rawHtml(request: APIRequestContext, path: string): Promise<{ status: number; html: string }> {
  const res = await request.get(`${ORIGIN}${path}`, { maxRedirects: 0 });
  return { status: res.status(), html: await res.text() };
}

function ldJsonBlocks(html: string): string[] {
  return [...html.matchAll(/<script[^>]*type="application\/ld\+json"[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
}

test.describe.serial('Phase 11e — Opportunity slugs & SEO, end to end', () => {
  test.beforeAll(async ({ playwright }) => {
    api = await playwright.request.newContext({
      baseURL: ORIGIN,
      extraHTTPHeaders: { 'X-Admin-Key': adminKey() },
    });
  });

  test.afterAll(async () => {
    if (api) {
      if (opportunityId) await api.patch(`/api/admin/opportunities/${opportunityId}`, { data: { status: 'closed' } });
      if (partnerId) await api.patch(`/api/admin/partners/${partnerId}`, { data: { active: false } });
      await api.dispose();
    }
    expect(errors, 'no page errors / no admin key sent by public contexts').toEqual([]);
  });

  test('1. seed — published hybrid listing gets a readable slug and slug public_url', async () => {
    const pRes = await api.post('/api/admin/partners', {
      data: { internal_name: SENTINEL_PARTNER, display_name: 'A Bengaluru fintech', notes: null },
    });
    expect(pRes.ok(), `POST /api/admin/partners → ${pRes.status()}: ${await pRes.text()}`).toBeTruthy();
    partnerId = (await pRes.json()).data.partner.id;

    const res = await api.post('/api/admin/opportunities', {
      data: {
        title: TITLE,
        type: 'workshop',
        summary: `Slug fixture (${RUN}).`,
        description_md: 'A hands-on **GenAI** workshop.',
        topic_ids: [await topicId('generative-ai')],
        location_mode: 'hybrid',
        locations: [{ city: 'Bengaluru', country: null }],
        deadline: isoDaysFromNow(10),
        partner_id: partnerId,
        internal_notes: INTERNAL_NOTE,
        status: 'open',
      },
    });
    expect(res.ok(), `POST /api/admin/opportunities → ${res.status()}: ${await res.text()}`).toBeTruthy();
    const opp = (await res.json()).data.opportunity;
    opportunityId = opp.id;
    slug = opp.slug;
    publicUrl = opp.public_url;
    expect(slug).toMatch(SLUG_RE);
    expect(publicUrl.endsWith(`/opportunities/${slug}`)).toBeTruthy();
  });

  test('2. card → slug URL, and back to the filtered board', async ({ browser }) => {
    const { ctx, page } = await publicPage(browser, 'card');
    try {
      await page.goto(`${APP_BASE}/opportunities/?sort=deadline&type=workshop`);
      const card = page.getByTestId('opportunity-card').filter({ hasText: TITLE });
      await expect(card).toHaveCount(1);
      await waitForHydration(card);
      await card.getByRole('link').first().click();
      await expect(page.getByTestId('opportunity-title')).toHaveText(TITLE, { timeout: 15_000 });
      expect(new URL(page.url()).pathname).toBe(`/opportunities/${slug}`);

      await page.getByRole('link', { name: /All opportunities/ }).first().click();
      await expect(page.getByTestId('board-page')).toBeVisible();
      const back = new URL(page.url());
      expect(back.pathname).toBe('/app/opportunities/');
      expect(back.searchParams.get('sort')).toBe('deadline');
      expect(back.searchParams.get('type')).toBe('workshop');
    } finally {
      await ctx.close();
    }
  });

  test('3. legacy id URLs end on the slug URL', async ({ browser }) => {
    const { ctx, page } = await publicPage(browser, 'legacy');
    try {
      for (const legacy of [`${ORIGIN}/opportunities/${opportunityId}`, `${APP_BASE}/opportunities/view/?id=${opportunityId}`]) {
        await page.goto(legacy);
        await expect.poll(() => new URL(page.url()).pathname, { message: legacy }).toBe(`/opportunities/${slug}`);
        await expect(page.getByTestId('opportunity-title')).toHaveText(TITLE);
      }
    } finally {
      await ctx.close();
    }
  });

  test('4. raw HTML carries the SEO head + JobPosting and nothing internal', async ({ request, browser }) => {
    const { status, html } = await rawHtml(request, `/opportunities/${slug}`);
    expect(status).toBe(200);
    expect(html).toContain(`<title>${TITLE} — Workshop0</title>`);
    expect(html).toContain(`rel="canonical" href="${publicUrl}"`);
    expect(html).toContain('og:title');
    const blocks = ldJsonBlocks(html);
    expect(blocks).toHaveLength(1);
    const ld = JSON.parse(blocks[0]);
    expect(ld['@type']).toBe('JobPosting');
    expect(ld.jobLocation[0].address.addressLocality).toBe('Bengaluru');
    expect(html).not.toContain('ZZ-INTERNAL');
    expect(html).not.toContain(SENTINEL_PARTNER);

    const { ctx, page } = await publicPage(browser, 'rendered');
    try {
      await page.goto(`${ORIGIN}/opportunities/${slug}`);
      await expect(page.getByTestId('opportunity-title')).toHaveText(TITLE);
      const content = await page.content();
      expect(content).not.toContain('ZZ-INTERNAL');
      expect(content).not.toContain(SENTINEL_PARTNER);
    } finally {
      await ctx.close();
    }
  });

  test('5. the slug is stable across a rename', async ({ request }) => {
    const res = await api.patch(`/api/admin/opportunities/${opportunityId}`, { data: { title: RENAMED } });
    expect(res.ok(), `PATCH → ${res.status()}`).toBeTruthy();
    expect((await res.json()).data.opportunity.slug).toBe(slug);
    const { status, html } = await rawHtml(request, `/opportunities/${slug}`);
    expect(status).toBe(200);
    expect(html).toContain(`<title>${RENAMED} — Workshop0</title>`);
  });

  test('6. admin editor public link is the slug URL', async ({ browser }) => {
    const ctx = await browser.newContext();
    try {
      const page = await ctx.newPage();
      await signInAdmin(page);
      await page.goto(`${ADMIN_BASE}/opportunities/edit/?id=${opportunityId}`);
      const link = page.getByTestId('opp-public-link');
      await expect(link).toBeVisible({ timeout: 15_000 });
      expect((await link.innerText()).trim().endsWith(`/opportunities/${slug}`)).toBeTruthy();
      expect((await link.getAttribute('href'))!.endsWith(`/opportunities/${slug}`)).toBeTruthy();
    } finally {
      await ctx.close();
    }
  });

  test('9a. sitemap lists the open listing; robots disallows private paths', async ({ request }) => {
    const sm = await request.get(`${ORIGIN}/sitemap.xml`);
    expect(sm.ok()).toBeTruthy();
    expect(await sm.text()).toContain(`<loc>${publicUrl}</loc>`);
    const robots = await (await request.get(`${ORIGIN}/robots.txt`)).text();
    for (const line of ['Disallow: /admin', 'Disallow: /api/', 'Disallow: /network/me']) {
      expect(robots.split('\n').map((l) => l.trim())).toContain(line);
    }
  });

  test('7. closed — noindex, no JSON-LD, closed banner; gone from the sitemap', async ({ request, browser }) => {
    const res = await api.patch(`/api/admin/opportunities/${opportunityId}`, { data: { status: 'closed' } });
    expect(res.ok(), `PATCH closed → ${res.status()}`).toBeTruthy();
    const { status, html } = await rawHtml(request, `/opportunities/${slug}`);
    expect(status).toBe(200);
    expect(html).toContain('noindex');
    expect(html).not.toContain('application/ld+json');

    const { ctx, page } = await publicPage(browser, 'closed');
    try {
      await page.goto(`${ORIGIN}/opportunities/${slug}`);
      await expect(page.getByText('Applications for this opportunity have closed.')).toBeVisible();
    } finally {
      await ctx.close();
    }

    const sm = await (await request.get(`${ORIGIN}/sitemap.xml`)).text();
    expect(sm).not.toContain(`/opportunities/${slug}<`);
  });

  test('8. a draft slug is a 404 that leaks nothing', async ({ request, browser }) => {
    const res = await api.post('/api/admin/opportunities', {
      data: {
        title: DRAFT_TITLE,
        type: 'workshop',
        summary: `Draft fixture (${RUN}).`,
        description_md: 'Draft.',
        topic_ids: [await topicId('python')],
        location_mode: 'remote',
        deadline: isoDaysFromNow(10),
        status: 'draft',
      },
    });
    expect(res.ok(), `POST draft → ${res.status()}`).toBeTruthy();
    const opp = (await res.json()).data.opportunity;
    draftId = opp.id;
    draftSlug = opp.slug;
    expect(draftSlug).toBeTruthy();

    const { status, html } = await rawHtml(request, `/opportunities/${draftSlug}`);
    expect(status).toBe(404);
    expect(html).not.toContain('ZZ-DRAFT');

    const { ctx, page } = await publicPage(browser, 'draft');
    try {
      await page.goto(`${ORIGIN}/opportunities/${draftSlug}`);
      await expect(page.getByTestId('opportunity-not-found')).toBeVisible();
      expect(await page.content()).not.toContain('ZZ-DRAFT');
    } finally {
      await ctx.close();
    }
    const sm = await (await request.get(`${ORIGIN}/sitemap.xml`)).text();
    expect(sm).not.toContain('ZZ-DRAFT');
    expect(draftId).toBeGreaterThan(0);
  });
});
