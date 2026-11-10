import { test, expect, type Page } from '@playwright/test';
import { APP_BASE, ADMIN_BASE, signInAdmin } from './helpers';

/**
 * Phase 13 — no-stub sweep (roadmap.md §Phase 13 e2e plan, V4).
 * Trainer-network and admin network/opportunity pages carry zero
 * `stub-badge`. Out of scope: admin Home and facilitator/participant
 * workshop pages (their Phase 2-4 stubs are by design).
 */

const TRAINER_PATHS = [
  '/network/',
  '/network/me/',
  '/network/applications/',
  '/network/matches/',
  '/network/searches/',
  '/network/directory/',
  '/network/unsubscribed/',
  '/opportunities/',
  '/opportunities/view/?slug=no-such-listing',
];

const ADMIN_PATHS = [
  '/network/',
  '/network/trainer/?id=0',
  '/opportunities/',
  '/opportunities/edit/',
  '/opportunities/pipeline/?id=0',
  '/outbox/',
  '/partners/',
  '/topics/',
];

async function expectNoStubs(page: Page, url: string): Promise<void> {
  await page.goto(url);
  await expect(page.locator('main, body').first()).toBeVisible();
  await page.waitForLoadState('networkidle');
  await expect(page.getByTestId('stub-badge'), `${url} has no stub badge`).toHaveCount(0);
}

test.describe('trainer pages have no stub badges', () => {
  for (const path of TRAINER_PATHS) {
    test(path, async ({ page }) => {
      await expectNoStubs(page, `${APP_BASE}${path}`);
    });
  }
});

test.describe('admin network pages have no stub badges', () => {
  test('all admin network/opportunity pages', async ({ page }) => {
    await signInAdmin(page);
    for (const path of ADMIN_PATHS) {
      await expectNoStubs(page, `${ADMIN_BASE}${path}`);
    }
  });
});
