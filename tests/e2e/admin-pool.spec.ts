import * as fs from 'node:fs';
import * as path from 'node:path';
import {
  test,
  expect,
  type Browser,
  type BrowserContext,
  type Download,
  type Locator,
  type Page,
} from '@playwright/test';
import { ADMIN_BASE, APP_BASE, ORIGIN, waitForHydration } from './helpers';

/**
 * Phase 11 — Admin trainer pool (roadmap.md §Phase 11 "e2e (S13 / S14)"
 * *admin-pool*, capabilities.md C11 + C13, api.md §Phase 11).
 *
 * Journey: an allow-listed admin signs in through the local OIDC issuer
 * (`tests/support/fake_oidc.py`, the server's `WORKSHOP0_OIDC_ISSUER`) and gets
 * Admin Home WITHOUT the access key → Trainer network → finds the trainer this
 * spec seeded in `beforeAll` → opens it → downloads the CV → verifies (badge) →
 * adds a tag and a note → exports CSV → creates an invite and opens the copied
 * `/invite/<token>` link in a fresh browser as the invited email (onboarding
 * shows Verified) → a second invite opened with a different email shows the
 * mismatch message. The admin-side labelled stubs each show their pill.
 *
 * Self-seeding: `beforeAll` signs a fresh trainer in through the issuer, uploads
 * `tests/fixtures/cv/genai_trainer.pdf` and creates the profile over the API
 * (the browser context's cookie + `X-Requested-With: workshop0`). Nothing here
 * depends on another spec's data. The e2e DB is never reset, so every
 * identifier carries RUN. Waits are polling assertions — no fixed sleeps.
 */

const RUN = `r${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;

const ADMIN_EMAIL = 'admin@example.test';
const TRAINER_EMAIL = `pool-trainer-${RUN}@example.test`;
const INVITEE_EMAIL = `invitee-${RUN}@example.test`;
const INVITEE2_EMAIL = `invitee2-${RUN}@example.test`;
const WRONG_EMAIL = `wrong-${RUN}@example.test`;

const HEADLINE = `E2E pool GenAI trainer ${RUN}`;
const TAG = `e2e-tag-${RUN}`;
const NOTE = `E2E private note ${RUN}: strong on RAG evals.`;

const CV_FIXTURE = path.resolve(__dirname, '..', 'fixtures', 'cv', 'genai_trainer.pdf');
const NETWORK_HEADERS = { 'X-Requested-With': 'workshop0' };

const POOL_URL = `${ADMIN_BASE}/network/`;

let trainerCtx: BrowserContext;
let trainerId = 0;

/** Unwrap the `{data, error}` success envelope (api.md §Conventions). */
function data<T = any>(body: any): T {
  return (body && typeof body === 'object' && 'data' in body ? body.data : body) as T;
}

/**
 * Complete the local issuer's authorize page as `email`. The page carries one
 * email field and auto-approves on submit (tests/support/fake_oidc.py); the
 * app's callback then 303s back to `next`. Private to this spec by design
 * (roadmap S13/S14: helpers.ts is read-only this phase).
 */
async function completeIssuer(page: Page, email: string): Promise<void> {
  const emailField = page.getByTestId('fake-oidc-email');
  await expect(emailField).toBeVisible({ timeout: 15_000 });
  await emailField.fill(email);
  await Promise.all([
    page.waitForURL((u) => u.origin === ORIGIN && u.pathname.startsWith('/app/'), {
      timeout: 30_000,
    }),
    page.getByTestId('fake-oidc-signin').click(),
  ]);
}

/** Click a visible "Continue with Google" button, then complete the issuer. */
async function continueWithGoogle(page: Page, email: string): Promise<void> {
  const google = page.getByRole('button', { name: 'Continue with Google' })
    .or(page.getByRole('link', { name: 'Continue with Google' }))
    .first();
  await waitForHydration(google);
  await google.click();
  await completeIssuer(page, email);
}

/** Direct sign-in via the start endpoint (seeding only — not the UI under test). */
async function signInDirect(page: Page, email: string, next: string): Promise<void> {
  await page.goto(`${ORIGIN}/api/auth/google/start?next=${encodeURIComponent(next)}`);
  await completeIssuer(page, email);
}

async function freshContext(browser: Browser): Promise<BrowserContext> {
  return browser.newContext({ acceptDownloads: true });
}

/** A labelled stub: an element carrying `label` that also holds a stub pill. */
function stubWithLabel(page: Page, label: string | RegExp): Locator {
  return page
    .locator('[aria-disabled="true"]')
    .filter({ hasText: label })
    .filter({ has: page.getByTestId('stub-badge') })
    .first();
}

async function saveDownload(dl: Download): Promise<string> {
  const target = path.join(test.info().outputDir, dl.suggestedFilename());
  await dl.saveAs(target);
  return target;
}

test.describe.configure({ mode: 'serial' });

test.beforeAll(async ({ browser }) => {
  test.setTimeout(180_000);
  expect(fs.existsSync(CV_FIXTURE), `missing CV fixture ${CV_FIXTURE}`).toBe(true);

  // 1. A brand-new trainer signs in through the issuer.
  trainerCtx = await freshContext(browser);
  const page = await trainerCtx.newPage();
  await signInDirect(page, TRAINER_EMAIL, '/app/network/');
  const me = await trainerCtx.request.get(`${ORIGIN}/api/auth/me`);
  expect(me.ok()).toBe(true);
  const meUser = data<{ user: { email: string; has_profile: boolean } | null }>(await me.json()).user;
  expect(meUser?.email).toBe(TRAINER_EMAIL);
  expect(meUser?.has_profile).toBe(false);

  // 2. Upload the real CV fixture (multipart `file`).
  const upload = await trainerCtx.request.post(`${ORIGIN}/api/me/cv`, {
    headers: NETWORK_HEADERS,
    multipart: {
      file: {
        name: 'genai_trainer.pdf',
        mimeType: 'application/pdf',
        buffer: fs.readFileSync(CV_FIXTURE),
      },
    },
  });
  expect(upload.status(), await upload.text()).toBe(200);

  // 3. Let the background drafter settle (real Anthropic call on the server) so
  //    the CV row is final before the profile exists. Any terminal status is fine.
  await expect
    .poll(
      async () => {
        const r = await trainerCtx.request.get(`${ORIGIN}/api/me/cv/draft`);
        if (!r.ok()) return `http-${r.status()}`;
        return data<{ draft_status: string }>(await r.json()).draft_status;
      },
      { timeout: 90_000, intervals: [1_500] },
    )
    .not.toBe('pending');

  // 4. Create the profile with a curated topic and the required consent.
  const topicsRes = await trainerCtx.request.get(`${ORIGIN}/api/public/topics`);
  expect(topicsRes.ok()).toBe(true);
  const topicsBody = data<any>(await topicsRes.json());
  const topics: Array<{ slug: string; active?: boolean }> = Array.isArray(topicsBody)
    ? topicsBody
    : topicsBody.topics ?? topicsBody.items ?? [];
  const topic = topics.find((t) => t.active !== false) ?? topics[0];
  expect(topic, 'no curated topics on the server').toBeTruthy();

  const create = await trainerCtx.request.post(`${ORIGIN}/api/me/profile`, {
    headers: NETWORK_HEADERS,
    data: {
      headline: HEADLINE,
      bio_md: `Seeded by admin-pool.spec.ts (${RUN}). Builds GenAI workshops for product teams.`,
      city: 'Bengaluru',
      remote_ok: true,
      topics: [{ slug: topic.slug, level: 'advanced' }],
      consent: true,
    },
  });
  expect(create.status(), await create.text()).toBe(200);
  const profile = await trainerCtx.request.get(`${ORIGIN}/api/me/profile`);
  expect(profile.ok()).toBe(true);
  const own = data<{ profile: { id: number; headline: string } }>(await profile.json()).profile;
  expect(own.headline).toBe(HEADLINE);
  trainerId = own.id;
  await page.close();
});

test.afterAll(async () => {
  await trainerCtx?.close();
});

test('admin signs in with Google, curates the pool and invites a trainer', async ({ browser }) => {
  test.setTimeout(240_000);
  const adminCtx = await freshContext(browser);
  const admin = await adminCtx.newPage();
  const consoleErrors: string[] = [];
  admin.on('pageerror', (e) => consoleErrors.push(e.message));

  // --- Admin Home via the issuer, never typing the key -----------------------
  await admin.goto(`${ADMIN_BASE}/`);
  await expect(admin.getByTestId('admin-key-input')).toBeVisible({ timeout: 20_000 });
  await continueWithGoogle(admin, ADMIN_EMAIL);
  await expect(admin).toHaveURL(/\/app\/admin\/?(\?.*)?$/);
  await expect(admin.getByTestId('new-workshop-button')).toBeVisible({ timeout: 20_000 });
  await expect(admin.getByTestId('admin-key-input')).toHaveCount(0);
  const storedKey = await admin.evaluate(() => window.localStorage.getItem('workshop0_admin_key'));
  expect(storedKey ?? '').toBe('');

  // --- Trainer network (real nav, no stub pill) --------------------------------
  const nav = admin.getByTestId('nav-trainer-network');
  await expect(nav).toHaveText('Trainer network');
  await expect(nav.getByTestId('stub-badge')).toHaveCount(0);
  await waitForHydration(nav);
  await nav.click();
  await expect(admin).toHaveURL(/\/app\/admin\/network\/?(\?.*)?$/);
  await expect(admin.getByText('Network AI spend')).toBeVisible();

  // Admin-side labelled stubs on the pool page (C13): matching filters, Email invite.
  await expect(stubWithLabel(admin, /level|budget|availability|matching/i)).toBeVisible();
  await expect(stubWithLabel(admin, /Email invite/i)).toBeVisible();

  // --- The seeded trainer is listed (search narrows to this run) -------------
  const search = admin.getByRole('searchbox').or(admin.getByPlaceholder(/search/i)).first();
  await waitForHydration(search);
  await search.fill(RUN);
  const row = admin.getByTestId('pool-row').filter({ hasText: HEADLINE });
  await expect(row).toBeVisible({ timeout: 15_000 });
  await expect(row).toContainText(TRAINER_EMAIL);

  // --- Open → trainer detail --------------------------------------------------
  await row.getByRole('link').first().click();
  await expect(admin).toHaveURL(new RegExp(`/app/admin/network/trainer/\\?id=${trainerId}`));
  await expect(admin.getByText(HEADLINE).first()).toBeVisible();

  // Download CV → a real .pdf download event with the original bytes' magic.
  const cvBtn = admin
    .getByRole('button', { name: 'Download CV' })
    .or(admin.getByRole('link', { name: 'Download CV' }))
    .first();
  await waitForHydration(cvBtn);
  const [cvDl] = await Promise.all([admin.waitForEvent('download'), cvBtn.click()]);
  expect(cvDl.suggestedFilename().toLowerCase()).toMatch(/\.pdf$/);
  const cvPath = await saveDownload(cvDl);
  expect(fs.readFileSync(cvPath).subarray(0, 5).toString('latin1')).toBe('%PDF-');

  // Verify → badge, and the action flips to Unverify.
  await admin.getByRole('button', { name: 'Verify', exact: true }).click();
  await expect(admin.getByRole('button', { name: 'Unverify' })).toBeVisible();
  await expect(admin.getByTestId('verified-badge').first()).toBeVisible();

  // Tag.
  const tagInput = admin.getByLabel(/tag/i).or(admin.getByPlaceholder(/tag/i)).first();
  await waitForHydration(tagInput);
  await tagInput.fill(TAG);
  await tagInput.press('Enter');
  await expect(admin.getByText(TAG).first()).toBeVisible();

  // Private note (append-only, author shown).
  const noteInput = admin.getByLabel(/note/i).or(admin.getByPlaceholder(/note/i)).first();
  await noteInput.fill(NOTE);
  await admin.getByRole('button', { name: /add note/i }).click();
  await expect(admin.getByText(NOTE)).toBeVisible();
  await expect(admin.getByText(ADMIN_EMAIL).first()).toBeVisible();

  // Server truth: verified, tag and note persisted.
  const detail = await adminCtx.request.get(`${ORIGIN}/api/admin/network/trainers/${trainerId}`);
  expect(detail.ok()).toBe(true);
  const detailJson = JSON.stringify(await detail.json());
  expect(detailJson).toContain(TAG);
  expect(detailJson).toContain(NOTE);

  // --- Back to the pool: badge + tag in the row, Export CSV ------------------
  await admin.goto(POOL_URL);
  const search2 = admin.getByRole('searchbox').or(admin.getByPlaceholder(/search/i)).first();
  await waitForHydration(search2);
  await search2.fill(RUN);
  const row2 = admin.getByTestId('pool-row').filter({ hasText: HEADLINE });
  await expect(row2).toBeVisible();
  await expect(row2).toContainText(TAG);
  await expect(row2.getByTestId('verified-badge')).toBeVisible();

  const csvBtn = admin
    .getByRole('button', { name: 'Export CSV' })
    .or(admin.getByRole('link', { name: 'Export CSV' }))
    .first();
  const [csvDl] = await Promise.all([admin.waitForEvent('download'), csvBtn.click()]);
  expect(csvDl.suggestedFilename()).toMatch(/^workshop0-trainers-\d{8}\.csv$/);
  const csv = fs.readFileSync(await saveDownload(csvDl), 'utf8');
  expect(csv).toContain(TRAINER_EMAIL);

  // --- Invite → fresh browser as the invited email → Verified ---------------
  const inviteUrl = await createInvite(admin, INVITEE_EMAIL);
  const invitee = await openInviteAs(browser, inviteUrl, INVITEE_EMAIL);
  await expect(invitee.page).toHaveURL(/\/app\/network\/join\//);
  await expect(invitee.page.getByText('Verified', { exact: true }).first()).toBeVisible({
    timeout: 20_000,
  });
  await invitee.ctx.close();

  // --- Second invite opened with a different email → mismatch --------------
  const inviteUrl2 = await createInvite(admin, INVITEE2_EMAIL);
  const wrong = await openInviteAs(browser, inviteUrl2, WRONG_EMAIL);
  await expect(wrong.page).toHaveURL(/error=invite_email_mismatch/);
  await expect(wrong.page.getByText(/This invite was sent to/)).toBeVisible();
  await expect(wrong.page.getByText(/sign in with that Google account/)).toBeVisible();
  const wrongMe = data<{ user: unknown }>(
    await (await wrong.ctx.request.get(`${ORIGIN}/api/auth/me`)).json(),
  );
  expect(wrongMe.user).toBeNull();
  await wrong.ctx.close();

  // Invite list shows the accepted one.
  await admin.reload();
  await expect(admin.getByText(INVITEE_EMAIL).first()).toBeVisible();

  // --- Opportunities page: Trainer pool nav is real; Phase-12 stubs pill ----
  await admin.goto(`${ADMIN_BASE}/opportunities/`);
  const poolNav = admin.getByTestId('nav-trainer-pool');
  await expect(poolNav).toBeVisible({ timeout: 20_000 });
  await expect(poolNav).toHaveAttribute('href', /\/admin\/network\/?$/);
  await expect(stubWithLabel(admin, 'Outbox')).toBeVisible();

  expect(consoleErrors, consoleErrors.join('\n')).toEqual([]);
  await adminCtx.close();
});

test('the seeded trainer sees the My profile stubs and the Verified badge', async () => {
  const page = await trainerCtx.newPage();
  await page.goto(`${APP_BASE}/network/me/`);
  await expect(page.getByText(HEADLINE).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('Verified', { exact: true }).first()).toBeVisible();
  for (const label of ['My applications', 'Matched for you', /Saved searches/, /Public directory/]) {
    await expect(stubWithLabel(page, label)).toBeVisible();
  }
  await page.close();
});

/** Create an invite on the pool page's Invites panel and return its copyable URL. */
async function createInvite(admin: Page, email: string): Promise<string> {
  if (!/\/app\/admin\/network\/?(\?.*)?$/.test(admin.url())) await admin.goto(POOL_URL);
  const panel = admin
    .getByRole('region', { name: /invite/i })
    .or(admin.locator('section', { has: admin.getByRole('heading', { name: /invites?/i }) }))
    .first();
  const emailInput = panel.getByLabel(/email/i).or(panel.getByPlaceholder(/email/i)).first();
  await waitForHydration(emailInput);
  await emailInput.fill(email);
  await panel.getByRole('button', { name: /create invite/i }).click();
  let url = '';
  await expect
    .poll(
      async () => {
        const text = await panel.innerText();
        const m = text.match(/https?:\/\/\S+?\/invite\/[A-Za-z0-9_-]+/);
        url = m ? m[0] : '';
        return url;
      },
      { timeout: 15_000 },
    )
    .not.toBe('');
  return url;
}

/** Open an invite link in a brand-new browser and sign in as `email`. */
async function openInviteAs(
  browser: Browser,
  inviteUrl: string,
  email: string,
): Promise<{ ctx: BrowserContext; page: Page }> {
  const ctx = await freshContext(browser);
  const page = await ctx.newPage();
  // Same-origin by construction; the invite URL's host is the server's base URL.
  const token = new URL(inviteUrl).pathname.split('/').pop()!;
  await page.goto(`${ORIGIN}/invite/${token}`);
  await expect(page).toHaveURL(new RegExp(`invite=${token}`));
  await continueWithGoogle(page, email);
  return { ctx, page };
}
