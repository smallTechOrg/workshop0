import * as path from 'node:path';
import {
  test,
  expect,
  type APIRequestContext,
  type BrowserContext,
  type Page,
} from '@playwright/test';
import { APP_BASE, ORIGIN, adminKey, waitForHydration } from './helpers';

/**
 * Phase 11 — network onboarding (roadmap.md §Phase 11 "e2e (S13)",
 * capabilities.md C11 + C12, api.md §Phase 11).
 *
 * A stranger on the public board clicks **Join our network** → the sign-in
 * page → **Continue with Google** → the LOCAL fake OIDC issuer
 * (tests/support/fake_oidc.py, the server's WORKSHOP0_OIDC_ISSUER) → types
 * `trainer-<run>@example.test` → back on onboarding → uploads the committed
 * GenAI-trainer PDF → "Reading your CV…" → the review screen is pre-filled by
 * the REAL Anthropic drafter (the server's .env) with "From your CV — please
 * check" chips and curated topics → consent → **Create my profile** → My
 * profile (completeness meter + nudges + labelled stubs) → sign out → sign in
 * again → the same profile → **Delete my account** → confirmation → signing in
 * again lands on onboarding with a fresh account.
 *
 * One browser context for the whole journey (the session cookie is the state).
 * `ctx.request` shares that cookie jar, so API cross-checks see exactly what
 * the browser sees. The e2e DB is never reset: every identity carries RUN.
 */

const RUN = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const EMAIL = `trainer-${RUN}@example.test`;
const CV_PDF = path.resolve(__dirname, '..', 'fixtures', 'cv', 'genai_trainer.pdf');

const BOARD_URL = `${APP_BASE}/opportunities/`;
const STUB_PILL = 'Coming in a later phase';
/** Real Anthropic drafting through a BackgroundTask; the UI polls ≤60 s. */
const DRAFT_TIMEOUT = 90_000;

const errors: string[] = [];

let ctx: BrowserContext;
let page: Page;
let profileId = 0;
let firstUserId = 0;
let headline = '';
let listingId = 0;

// ------------------------------------------------- private sign-in helper
// (roadmap S13: private to this spec — tests/e2e/helpers.ts is read-only.)

/**
 * From a page showing the sign-in surface: click **Continue with Google**,
 * complete the fake issuer's authorize page as `email`, and wait until the
 * callback has bounced the browser back onto the app (`/app/…`, not signin).
 */
async function signInWithFakeIssuer(p: Page, email: string): Promise<void> {
  const google = p.getByRole('link', { name: 'Continue with Google' });
  await waitForHydration(google);
  await google.click();
  // The authorize page lives on the issuer's origin, not the app's.
  await p.waitForURL((u) => u.origin !== ORIGIN, { timeout: 30_000 });
  // tests/support/README.md §Playwright: the authorize page.
  const emailField = p.getByTestId('fake-oidc-email');
  await expect(emailField).toBeVisible();
  await emailField.fill(email);
  await p.getByTestId('fake-oidc-signin').click();
  await p.waitForURL(
    (u) => u.origin === ORIGIN && u.pathname.startsWith('/app/') && !u.pathname.startsWith('/app/signin'),
    { timeout: 30_000 },
  );
}

/** Open the sign-in page directly (as a returning trainer would). */
async function gotoSignIn(p: Page): Promise<void> {
  await p.goto(`${APP_BASE}/signin/?next=${encodeURIComponent('/app/network/')}`);
}

async function authMe(): Promise<{ id: number; email: string; has_profile: boolean } | null> {
  const res = await ctx.request.get(`${ORIGIN}/api/auth/me`);
  expect(res.status(), 'GET /api/auth/me never 401s').toBe(200);
  return (await res.json()).data.user;
}

// ---------------------------------------------------------------- journey

test.describe.configure({ mode: 'serial' });

test.describe('network onboarding — sign in, CV-drafted profile, delete', () => {
  test.beforeAll(async ({ browser, playwright }) => {
    // A real open listing so the listing page's "Sign in to apply" stub is
    // asserted deterministically (the board is otherwise data-dependent).
    const api: APIRequestContext = await playwright.request.newContext({
      baseURL: ORIGIN,
      extraHTTPHeaders: { 'X-Admin-Key': adminKey() },
    });
    try {
      const topicsRes = await api.get('/api/admin/topics');
      expect(topicsRes.ok(), `GET /api/admin/topics → ${topicsRes.status()}`).toBeTruthy();
      const topics = (await topicsRes.json()).data.topics as Array<{ id: number; slug: string }>;
      expect(topics.length, 'curated topics are seeded').toBeGreaterThan(0);
      const res = await api.post('/api/admin/opportunities', {
        data: {
          title: `E2E Network onboarding ${RUN}`,
          type: 'workshop',
          summary: `Listing for the onboarding journey (${RUN}).`,
          description_md: 'Fixture listing.',
          topic_ids: [topics[0].id],
          location_mode: 'remote',
          deadline: new Date(Date.now() + 14 * 86_400_000).toISOString().replace(/\.\d{3}Z$/, 'Z'),
          status: 'open',
        },
      });
      expect(res.ok(), `POST /api/admin/opportunities → ${res.status()}`).toBeTruthy();
      listingId = (await res.json()).data.opportunity.id as number;
    } finally {
      await api.dispose();
    }

    ctx = await browser.newContext();
    ctx.setDefaultTimeout(15_000);
    ctx.setDefaultNavigationTimeout(30_000);
    page = await ctx.newPage();
    page.on('pageerror', (err) => errors.push(String(err)));
  });

  test.afterAll(async ({ playwright }) => {
    // Close the fixture listing so it doesn't linger on the shared board.
    if (listingId) {
      const api = await playwright.request.newContext({
        baseURL: ORIGIN,
        extraHTTPHeaders: { 'X-Admin-Key': adminKey() },
      });
      await api.patch(`/api/admin/opportunities/${listingId}`, { data: { status: "closed" } }).catch(() => undefined);
      await api.dispose();
    }
    await ctx?.close();
  });

  test('board: Join our network is real; Sign in to apply stays a labelled stub', async () => {
    await page.goto(`${ORIGIN}/opportunities/${listingId}`);
    const applyStub = page.getByTestId('apply-stub');
    await expect(applyStub).toBeVisible();
    await expect(applyStub).toContainText('Sign in to apply');
    await expect(applyStub).toContainText(STUB_PILL);

    await page.goto(BOARD_URL);
    await expect(page.getByTestId('board-page')).toBeVisible();
    // The old stub wrapper is gone; the CTA is a real, clickable control.
    await expect(page.getByTestId('join-network-stub')).toHaveCount(0);
    const join = page.getByTestId('join-network-cta');
    await expect(join).toHaveAccessibleName('Join our network');
    await waitForHydration(join);
    await expect(join).not.toContainText(STUB_PILL);
    await join.click();
    await page.waitForURL(/\/app\/signin\//);
    expect(new URL(page.url()).searchParams.get('next')).toBe('/app/network/join/');
    await expect(page.getByRole('link', { name: 'Continue with Google' })).toBeVisible();
  });

  test('first sign-in through the local issuer lands on onboarding', async () => {
    expect(await authMe()).toBeNull();
    await signInWithFakeIssuer(page, EMAIL);
    await page.waitForURL(/\/app\/network\/join\//);
    const me = await authMe();
    expect(me, 'signed in').not.toBeNull();
    expect(me!.email).toBe(EMAIL);
    expect(me!.has_profile).toBe(false);
    firstUserId = me!.id;
    await expect(page.getByText("We can't read LinkedIn links directly")).toBeVisible();
  });

  test('upload the CV → Reading your CV… → pre-filled review with chips and curated topics', async () => {
    test.setTimeout(DRAFT_TIMEOUT + 60_000);
    const fileInput = page.locator('input[type="file"]').first();
    await waitForHydration(page.getByRole('tab', { name: /upload cv/i }));
    await fileInput.setInputFiles(CV_PDF);
    // Some UIs upload on select; others need an explicit submit.
    const submit = page.getByRole('button', { name: /upload|read my cv|continue/i }).first();
    if (await submit.isVisible().catch(() => false)) await submit.click();

    await expect(page.getByText('Reading your CV…')).toBeVisible({ timeout: 15_000 });

    const chips = page.getByText('From your CV — please check');
    await expect(chips.first()).toBeVisible({ timeout: DRAFT_TIMEOUT });
    expect(await chips.count()).toBeGreaterThanOrEqual(1);
    await expect(page.getByText('Reading your CV…')).toHaveCount(0);
    // A real draft, not the "couldn't pre-fill" empty state.
    await expect(page.getByText("We couldn't pre-fill from your CV")).toHaveCount(0);

    // The server's draft: ready, non-empty headline, ≥1 curated topic.
    const draftRes = await ctx.request.get(`${ORIGIN}/api/me/cv/draft`);
    expect(draftRes.ok()).toBeTruthy();
    const draft = (await draftRes.json()).data;
    expect(draft.draft_status).toBe('ready');
    expect(String(draft.draft.headline).trim().length).toBeGreaterThan(2);
    expect(draft.draft.topics.length).toBeGreaterThanOrEqual(1);
    expect(draft.autofilled_fields).toContain('topics');

    // The headline field shows the drafted value.
    headline = String(draft.draft.headline);
    await expect(page.getByLabel(/headline/i).first()).toHaveValue(headline);

    // Curated topics are shown by their curated names on the review screen.
    const topicsRes = await ctx.request.get(`${ORIGIN}/api/public/topics`);
    expect(topicsRes.ok()).toBeTruthy();
    const curated = (await topicsRes.json()).data.topics as Array<{ slug: string; name: string }>;
    const bySlug = new Map(curated.map((t) => [t.slug, t.name]));
    for (const t of draft.draft.topics as Array<{ slug: string; level: string }>) {
      expect(bySlug.has(t.slug), `drafted topic ${t.slug} is curated`).toBe(true);
      expect(['intermediate', 'advanced', 'expert']).toContain(t.level);
    }
    const firstTopicName = bySlug.get(draft.draft.topics[0].slug)!;
    await expect(page.getByTestId('review-topics').getByText(firstTopicName).first()).toBeVisible();
  });

  test('consent → Create my profile → My profile shows completeness, nudges and stubs', async () => {
    const create = page.getByRole('button', { name: 'Create my profile' });
    const consent = page.getByRole('checkbox', { name: /smallTech may share my profile/i });
    await waitForHydration(consent);
    await consent.check();
    await expect(consent).toBeChecked();
    await create.click();

    await page.waitForURL(/\/app\/network\/me\//);
    const res = await ctx.request.get(`${ORIGIN}/api/me/profile`);
    expect(res.ok()).toBeTruthy();
    const body = (await res.json()).data;
    profileId = body.profile.id;
    expect(body.profile.headline).toBe(headline);
    const pct = body.completeness.pct as number;
    expect(pct).toBeGreaterThan(0);

    const meter = page.getByTestId('completeness-meter');
    await expect(meter).toBeVisible();
    await expect(meter).toContainText(`${pct}%`);
    if (body.completeness.missing.length > 0) {
      await expect(page.getByTestId('completeness-nudges')).toBeVisible();
    }
    await expect(page.getByText(headline).first()).toBeVisible();

    for (const label of [
      'My applications',
      'Matched for you',
      'Saved searches',
      'Public directory profile',
    ]) {
      const stub = page.locator('[aria-disabled="true"]').filter({ hasText: label }).first();
      await expect(stub, `${label} is a labelled stub`).toBeVisible();
      await expect(stub).toContainText(STUB_PILL);
    }
    expect((await authMe())!.has_profile).toBe(true);
  });

  test('sign out → sign in again → the same profile', async () => {
    const menuButton = page.getByTestId('account-menu').getByRole('button', { expanded: false });
    await waitForHydration(menuButton);
    await menuButton.click();
    await page.getByRole('menuitem', { name: 'Sign out' }).click();
    await page.waitForURL(/\/app\/signin\/\?signed_out=1/);
    await expect(page.getByTestId('signin-signed-out')).toBeVisible();
    expect(await authMe()).toBeNull();

    await gotoSignIn(page);
    await signInWithFakeIssuer(page, EMAIL);
    await page.waitForURL(/\/app\/network\/me\//);
    const me = await authMe();
    expect(me!.id, 'second sign-in reuses the account').toBe(firstUserId);
    expect(me!.has_profile).toBe(true);
    const res = await ctx.request.get(`${ORIGIN}/api/me/profile`);
    expect((await res.json()).data.profile.id).toBe(profileId);
    await expect(page.getByText(headline).first()).toBeVisible();
  });

  test('Delete my account → confirmation → signing in again starts fresh onboarding', async () => {
    await page.getByRole('button', { name: 'Delete my account' }).first().click();
    const confirmInput = page.getByLabel(/email/i).last();
    await expect(confirmInput).toBeVisible();
    await confirmInput.fill(EMAIL);
    await page
      .getByRole('dialog')
      .getByRole('button', { name: /delete/i })
      .or(page.getByRole('button', { name: /^delete( my account)?( permanently)?$/i }).last())
      .first()
      .click();
    await expect(page.getByText(/account (has been|was) deleted|your account is deleted/i).first()).toBeVisible();
    await expect.poll(authMe, { timeout: 15_000 }).toBeNull();

    await gotoSignIn(page);
    await signInWithFakeIssuer(page, EMAIL);
    await page.waitForURL(/\/app\/network\/join\//);
    const me = await authMe();
    expect(me!.email).toBe(EMAIL);
    expect(me!.has_profile).toBe(false);
    expect(me!.id, 'deletion removed the old user; this is a new account').not.toBe(firstUserId);
    const profileRes = await ctx.request.get(`${ORIGIN}/api/me/profile`);
    expect(profileRes.status()).toBe(404);
  });

  test('no uncaught page errors on the journey', async () => {
    expect(errors).toEqual([]);
  });
});
