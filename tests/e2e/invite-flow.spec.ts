import {
  test,
  expect,
  type Browser,
  type BrowserContext,
  type Locator,
  type Page,
} from '@playwright/test';
import { ADMIN_BASE, APP_BASE, ORIGIN, waitForHydration } from './helpers';

/**
 * Phase 11d — invite flow fixes (roadmap.md §Phase 11d slice E1, api.md
 * §Invite acceptance + §Phase 11d, capabilities.md §C11/§C13).
 *
 * (a) A trainer signs in through the local OIDC issuer, creates a profile by
 *     hand (no CV), then an admin creates an invite for that email. Opening
 *     `/invite/<token>` in the SAME signed-in context shows the invite card (no
 *     redirect to My profile) → **Use my invite** → Verified → Go to My profile
 *     shows the badge; the admin panel lists the invite as Accepted.
 * (b) A second account opening that accepted invite → `invite_used`.
 * (c) An invite revoked from the admin panel → row reads Revoked with no link →
 *     signing in through the link as the invited email → `invite_revoked`.
 * (d) Creating the same email twice → `invite-reused`, same URL; the panel
 *     says "created", never "sent".
 *
 * Self-seeding and run-suffixed (the e2e DB is never reset). Sign-in helpers
 * are private to this spec (helpers.ts is read-only).
 */

const RUN = `i${Date.now().toString(36)}${Math.floor(Math.random() * 1e4).toString(36)}`;
const ADMIN_EMAIL = 'admin@example.test';
const TRAINER_EMAIL = `t-${RUN}@example.test`;
const OTHER_EMAIL = `other-${RUN}@example.test`;
const REVOKED_EMAIL = `revoked-${RUN}@example.test`;
const REUSE_EMAIL = `reuse-${RUN}@example.test`;
const HEADLINE = `E2E invite-flow trainer ${RUN}`;
const POOL_URL = `${ADMIN_BASE}/network/`;

let adminCtx: BrowserContext;
let admin: Page;
let trainerCtx: BrowserContext;
let trainer: Page;
let acceptedToken = '';
const pageErrors: string[] = [];

// ------------------------------------------------------- private helpers

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

async function continueWithGoogle(
  page: Page,
  email: string,
  testId: 'google-signin' | 'admin-google-signin' = 'google-signin',
): Promise<void> {
  const google = page.getByTestId(testId);
  await waitForHydration(google);
  await google.click();
  await completeIssuer(page, email);
}

function tokenOf(url: string): string {
  return new URL(url).pathname.split('/').pop()!;
}

function invitesPanel(page: Page): Locator {
  return page.getByRole('region', { name: 'Invites' });
}

function inviteRow(page: Page, email: string): Locator {
  return page.getByTestId('invite-row').filter({ hasText: email });
}

/** Create an invite on the admin Invites panel; return the shown URL. */
async function createInvite(page: Page, email: string): Promise<string> {
  if (!/\/app\/admin\/network\/?(\?.*)?$/.test(page.url())) await page.goto(POOL_URL);
  const panel = invitesPanel(page);
  const emailInput = panel.getByLabel('Email', { exact: true });
  await waitForHydration(emailInput);
  await emailInput.fill(email);
  await expect(emailInput).toHaveValue(email);
  await panel.getByRole('button', { name: 'Create invite' }).click();
  const created = panel.getByTestId('invite-created');
  await expect(created).toContainText(email);
  const url = ((await created.getByTestId('invite-url').textContent()) ?? '').trim();
  expect(url).toMatch(/\/invite\/[A-Za-z0-9_-]+$/);
  return url;
}

/** Open an invite in a brand-new browser context and sign in as `email`. */
async function openInviteFresh(
  browser: Browser,
  token: string,
  email: string,
): Promise<{ ctx: BrowserContext; page: Page }> {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(`${ORIGIN}/invite/${token}`);
  await expect(page).toHaveURL(new RegExp(`invite=${token}`));
  await continueWithGoogle(page, email);
  return { ctx, page };
}

// ---------------------------------------------------------------- journey

test.describe.configure({ mode: 'serial' });

test.describe('invite flow fixes (Phase 11d)', () => {
  test.beforeAll(async ({ browser }) => {
    test.setTimeout(120_000);
    adminCtx = await browser.newContext();
    admin = await adminCtx.newPage();
    admin.on('pageerror', (e) => pageErrors.push(`admin: ${e.message}`));
    await admin.goto(`${ADMIN_BASE}/`);
    await expect(admin.getByTestId('admin-key-input')).toBeVisible({ timeout: 20_000 });
    await continueWithGoogle(admin, ADMIN_EMAIL, 'admin-google-signin');
    await expect(admin.getByTestId('new-workshop-button')).toBeVisible({ timeout: 20_000 });
    await admin.goto(POOL_URL);
    await expect(invitesPanel(admin)).toBeVisible({ timeout: 20_000 });

    trainerCtx = await browser.newContext();
    trainer = await trainerCtx.newPage();
    trainer.on('pageerror', (e) => pageErrors.push(`trainer: ${e.message}`));
  });

  test.afterAll(async () => {
    await trainerCtx?.close();
    await adminCtx?.close();
  });

  test('(a) signed-in trainer WITH a profile → Use my invite → Verified', async () => {
    test.setTimeout(150_000);
    // Sign in and create a profile by hand (no CV).
    await trainer.goto(`${APP_BASE}/network/join/`);
    await continueWithGoogle(trainer, TRAINER_EMAIL);
    await trainer.waitForURL(/\/app\/network\/join\//);
    const skip = trainer.getByTestId('skip-cv');
    await waitForHydration(skip);
    await skip.click();
    const headline = trainer.getByTestId('profile-headline');
    await expect(headline).toBeVisible();
    await headline.fill(HEADLINE);
    const firstTopic = trainer.locator('[data-testid^="topic-option-"]').first();
    await expect(firstTopic).toBeVisible({ timeout: 15_000 });
    await firstTopic.click();
    await expect(trainer.locator('[data-testid^="selected-topic-"]').first()).toBeVisible();
    await trainer.getByTestId('profile-consent').check();
    await trainer.getByTestId('profile-submit').click();
    await trainer.waitForURL(/\/app\/network\/me\//);
    await expect(trainer.getByTestId('profile-headline-text')).toHaveText(HEADLINE);
    await expect(trainer.getByTestId('verified-badge')).toHaveCount(0);

    // Admin invites that email.
    const url = await createInvite(admin, TRAINER_EMAIL);
    acceptedToken = tokenOf(url);

    // Same signed-in context opens the link → invite card, no redirect.
    await trainer.goto(`${ORIGIN}/invite/${acceptedToken}`);
    await expect(trainer).toHaveURL(new RegExp(`/app/network/join/.*invite=${acceptedToken}`));
    const card = trainer.getByTestId('invite-card');
    await expect(card).toBeVisible({ timeout: 20_000 });
    await expect(card).toContainText(TRAINER_EMAIL);
    await expect(trainer).toHaveURL(/\/app\/network\/join\//);
    const use = trainer.getByTestId('invite-use');
    await waitForHydration(use);
    await use.click();
    await expect(trainer.getByTestId('invite-verified')).toBeVisible({ timeout: 20_000 });
    await expect(trainer.getByTestId('invite-card')).toHaveCount(0);

    const goProfile = trainer.getByTestId('invite-go-profile');
    await goProfile.click();
    await trainer.waitForURL(/\/app\/network\/me\//);
    await expect(trainer.getByTestId('verified-badge')).toBeVisible({ timeout: 20_000 });

    // Server truth: profile verified, invite accepted in the admin panel.
    const prof = await trainerCtx.request.get(`${ORIGIN}/api/me/profile`);
    expect(prof.ok()).toBe(true);
    expect((await prof.json()).data.profile.verified).toBe(true);
    await admin.reload();
    await expect(inviteRow(admin, TRAINER_EMAIL)).toContainText('Accepted', { timeout: 20_000 });
    await expect(inviteRow(admin, TRAINER_EMAIL).getByTestId('invite-revoke')).toHaveCount(0);
  });

  test('(b) another account opening the accepted invite → invite_used', async ({ browser }) => {
    expect(acceptedToken, 'scenario (a) produced a token').not.toBe('');
    const other = await openInviteFresh(browser, acceptedToken, OTHER_EMAIL);
    try {
      await expect(other.page).toHaveURL(/\/app\/signin\/.*error=invite_used/);
      const err = other.page.getByTestId('signin-error');
      await expect(err).toHaveAttribute('data-code', 'invite_used');
      await expect(err).toContainText('This invite has already been used.');
      const me = await other.ctx.request.get(`${ORIGIN}/api/auth/me`);
      expect((await me.json()).data.user, 'no session for a refused invite').toBeNull();
    } finally {
      await other.ctx.close();
    }
  });

  test('(c) revoked from the panel → Revoked, no link → invite_revoked', async ({ browser }) => {
    const url = await createInvite(admin, REVOKED_EMAIL);
    const token = tokenOf(url);
    const row = inviteRow(admin, REVOKED_EMAIL);
    await expect(row).toContainText('Pending', { timeout: 20_000 });
    const revoke = row.getByTestId('invite-revoke');
    await waitForHydration(revoke);
    await revoke.click();
    await row.getByTestId('invite-revoke-confirm').click();
    await expect(row).toContainText('Revoked', { timeout: 20_000 });
    await expect(row.getByTestId('invite-revoke')).toHaveCount(0);
    await expect(row.getByRole('button', { name: /Copy invite link/ })).toHaveCount(0);
    await expect(invitesPanel(admin).getByTestId('invite-created')).toHaveCount(0);
    // Survives a reload (server state, not local UI state).
    await admin.reload();
    await expect(inviteRow(admin, REVOKED_EMAIL)).toContainText('Revoked', { timeout: 20_000 });

    const invitee = await openInviteFresh(browser, token, REVOKED_EMAIL);
    try {
      await expect(invitee.page).toHaveURL(/\/app\/signin\/.*error=invite_revoked/);
      const err = invitee.page.getByTestId('signin-error');
      await expect(err).toHaveAttribute('data-code', 'invite_revoked');
      await expect(err).toContainText('This invite has been withdrawn — ask smallTech for a new one.');
      const me = await invitee.ctx.request.get(`${ORIGIN}/api/auth/me`);
      expect((await me.json()).data.user).toBeNull();
    } finally {
      await invitee.ctx.close();
    }
  });

  test('(d) same email twice → reused notice, same link; "created" copy, never "sent"', async () => {
    await admin.goto(POOL_URL);
    const first = await createInvite(admin, REUSE_EMAIL);
    await expect(invitesPanel(admin).getByTestId('invite-reused')).toHaveCount(0);
    const second = await createInvite(admin, REUSE_EMAIL);
    await expect(invitesPanel(admin).getByTestId('invite-reused')).toBeVisible();
    expect(second).toBe(first);
    // One actionable row for the email, not two.
    await expect(inviteRow(admin, REUSE_EMAIL)).toHaveCount(1, { timeout: 20_000 });
    await expect(inviteRow(admin, REUSE_EMAIL)).toContainText(/created .* · expires /);
    const text = (await invitesPanel(admin).getByTestId('invite-list').innerText()) ?? '';
    expect(text).toContain('created');
    expect(text).not.toMatch(/\bsent\b/);
  });

  test('no uncaught page errors', async () => {
    expect(pageErrors).toEqual([]);
  });
});
