import * as fs from 'node:fs';
import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { ORIGIN, adminKey } from './helpers';

/**
 * Phase 12 — Email outbox (roadmap.md §Phase 12 slice D1, api.md §Phase 12 C16).
 *
 * Three app instances share one database (the gate starts them):
 *   - ORIGIN (BASE_URL)          SMTP -> fake sink (tests/support/fake_smtp.py)
 *   - FAIL_ORIGIN  (:8013)       SMTP -> a closed port (every send fails)
 *   - UNCONF_ORIGIN (:8014)      SMTP not configured
 * Optional SMTP_DUMP_FILE: JSON-lines dump of the sink's captured mail (written by a
 * wrapper around tests/support/fake_smtp.py); when set, the invite link in the
 * delivered message is asserted to start with WORKSHOP0_BASE_URL.
 * Self-seeding over the admin API; private helpers.
 */
const RUN = `ob${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
const FAIL_ORIGIN = (process.env.FAIL_ORIGIN || 'http://localhost:8013').replace(/\/+$/, '');
const UNCONF_ORIGIN = (process.env.UNCONF_ORIGIN || 'http://localhost:8014').replace(/\/+$/, '');
const BASE_URL = (process.env.WORKSHOP0_BASE_URL || ORIGIN).replace(/\/+$/, '');
const DUMP = process.env.SMTP_DUMP_FILE;

const data = (b: any) => (b && typeof b === 'object' && 'data' in b ? b.data : b);

async function adminApi(playwright: any, origin: string): Promise<APIRequestContext> {
  return playwright.request.newContext({ baseURL: origin, extraHTTPHeaders: { 'X-Admin-Key': adminKey() } });
}

async function createInvite(api: APIRequestContext, email: string): Promise<number> {
  const res = await api.post('/api/admin/network/invites', { data: { email, name: `Outbox ${RUN}` } });
  expect(res.ok(), await res.text()).toBeTruthy();
  return data(await res.json()).invite.id;
}

async function outboxRow(api: APIRequestContext, to: string): Promise<any | undefined> {
  const items = data(await (await api.get('/api/admin/outbox')).json()).items as Array<any>;
  return items.find((r) => r.to === to && r.template === 'network.invite');
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

test.describe.serial('Phase 12 — email outbox', () => {
  let main: APIRequestContext;
  let failing: APIRequestContext;
  let unconf: APIRequestContext;

  test.beforeAll(async ({ playwright }) => {
    main = await adminApi(playwright, ORIGIN);
    failing = await adminApi(playwright, FAIL_ORIGIN);
    unconf = await adminApi(playwright, UNCONF_ORIGIN);
  });
  test.afterAll(async () => {
    await main?.dispose();
    await failing?.dispose();
    await unconf?.dispose();
  });

  test('Email invite click -> outbox row sent in the fake SMTP sink, link on WORKSHOP0_BASE_URL', async ({ browser }) => {
    const email = `invitee-sent-${RUN}@example.test`;
    const inviteId = await createInvite(main, email);
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await openAdmin(page, ORIGIN, 'network/', 'invite-list');
    const row = page.getByTestId('invite-row').filter({ hasText: email });
    await expect(row).toHaveCount(1);
    await row.getByTestId('invite-email').click();
    await page.getByRole('button', { name: 'Send email' }).click();
    await expect(row.getByTestId('invite-email-result')).toBeVisible();

    await expect.poll(async () => (await outboxRow(main, email))?.status, { timeout: 30_000 }).toBe('sent');

    if (DUMP) {
      await expect
        .poll(() => fs.readFileSync(DUMP, 'utf8').split('\n').filter((l) => l.includes(email)).length, { timeout: 20_000 })
        .toBeGreaterThan(0);
      const msg = JSON.parse(fs.readFileSync(DUMP, 'utf8').split('\n').filter((l) => l.includes(email))[0]);
      const links: string[] = msg.body.match(/https?:\/\/[^\s"'<>]+/g) ?? [];
      expect(links.length).toBeGreaterThan(0);
      for (const l of links) expect(l.startsWith(BASE_URL), `link ${l}`).toBe(true);
      expect(links.some((l) => l.includes('/invite/'))).toBe(true);
      expect(msg.body).not.toContain('<img');
    }

    // Second click is idempotent: still exactly one row for this recipient.
    const again = await main.post(`/api/admin/network/invites/${inviteId}/email`);
    expect(again.ok(), await again.text()).toBeTruthy();
    const items = data(await (await main.get('/api/admin/outbox')).json()).items as Array<any>;
    expect(items.filter((r) => r.to === email && r.template === 'network.invite')).toHaveLength(1);
    await ctx.close();
  });

  test('failed SMTP -> row failed, Retry in the Outbox re-queues and delivers', async ({ browser }) => {
    const email = `invitee-failed-${RUN}@example.test`;
    const inviteId = await createInvite(main, email);
    // The failing instance (closed SMTP port) processes the row: 3 attempts, then failed.
    const send = await failing.post(`/api/admin/network/invites/${inviteId}/email`);
    expect(send.ok(), await send.text()).toBeTruthy();
    await expect.poll(async () => (await outboxRow(failing, email))?.status, { timeout: 30_000 }).toBe('failed');
    expect((await outboxRow(failing, email)).attempts).toBe(3);

    // The working instance shows it Failed with Retry; Retry re-queues and the sink accepts it.
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await openAdmin(page, ORIGIN, 'outbox/', 'outbox-row');
    const row = page.getByTestId('outbox-row').filter({ hasText: email });
    await expect(row).toHaveCount(1);
    await expect(row).toHaveAttribute('data-status', 'failed');
    await row.getByTestId('outbox-retry').click();
    await expect(page.getByTestId('outbox-row').filter({ hasText: email })).toHaveAttribute('data-status', 'sent', {
      timeout: 30_000,
    });
    await ctx.close();
  });

  test('unconfigured SMTP -> banner and the row is labelled not sent', async ({ browser }) => {
    const email = `invitee-unconf-${RUN}@example.test`;
    const inviteId = await createInvite(unconf, email);
    const send = await unconf.post(`/api/admin/network/invites/${inviteId}/email`);
    expect(send.ok(), await send.text()).toBeTruthy();
    expect(data(await send.json()).outbox.status).toMatch(/queued|recorded/);

    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await openAdmin(page, UNCONF_ORIGIN, 'outbox/', 'outbox-banner');
    await expect(page.getByTestId('outbox-banner')).toContainText("Email sending isn't configured");
    const row = page.getByTestId('outbox-row').filter({ hasText: email });
    await expect(row).toHaveCount(1);
    await expect(row).toHaveAttribute('data-status', 'recorded');
    await expect(row).toContainText('Not sent');
    await expect(row.getByTestId('outbox-retry')).toHaveCount(0);
    await ctx.close();
  });
});
