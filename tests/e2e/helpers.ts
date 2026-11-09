import * as fs from 'node:fs';
import * as path from 'node:path';
import { expect, type Locator, type Page } from '@playwright/test';

/**
 * Single origin (architecture.md §Process model). Defaults to the local uvicorn
 * worker on :8001; set `BASE_URL` to target a deployed origin instead.
 */
export const ORIGIN = (process.env.BASE_URL || 'http://localhost:8001').replace(/\/+$/, '');
/** Canonical app base — the built Next.js export mounted by FastAPI. */
export const APP_BASE = `${ORIGIN}/app`;
/**
 * Admin console base. Phase 6 moved the admin console off `/app/` (which now
 * serves the public landing page) to `/app/admin/`, pretty URL `/admin`
 * (architecture.md §Public landing page & routing).
 */
export const ADMIN_BASE = `${APP_BASE}/admin`;
/** Public marketing landing page — served at the origin root (200 HTML). */
export const LANDING_URL = `${ORIGIN}/`;
/** Public keyless create flow. */
export const CREATE_URL = `${APP_BASE}/create/`;

let cachedAdminKey: string | null = null;

/**
 * Resolve WORKSHOP0_ADMIN_KEY: process.env first, else parse the repo-root
 * `.env` file (simple line parse — no dotenv dependency). The value is only
 * ever typed into the admin-key field; it is never logged or asserted on.
 */
export function adminKey(): string {
  if (cachedAdminKey) return cachedAdminKey;

  const fromEnv = process.env.WORKSHOP0_ADMIN_KEY;
  if (fromEnv && fromEnv.trim()) {
    cachedAdminKey = fromEnv.trim();
    return cachedAdminKey;
  }

  const envPath = path.resolve(__dirname, '..', '..', '.env');
  let raw: string;
  try {
    raw = fs.readFileSync(envPath, 'utf8');
  } catch {
    throw new Error(
      'WORKSHOP0_ADMIN_KEY is not set in the environment and the repo-root .env file is not readable. ' +
        'Run `cp .env.example .env` and set WORKSHOP0_ADMIN_KEY before the e2e gate.',
    );
  }

  for (const line of raw.split(/\r?\n/)) {
    const match = line.match(/^\s*(?:export\s+)?WORKSHOP0_ADMIN_KEY\s*=\s*(.*)$/);
    if (!match) continue;
    let value = match[1].trim();
    if (
      (value.startsWith('"') && value.endsWith('"') && value.length >= 2) ||
      (value.startsWith("'") && value.endsWith("'") && value.length >= 2)
    ) {
      value = value.slice(1, -1);
    }
    if (value) {
      cachedAdminKey = value;
      return cachedAdminKey;
    }
  }

  throw new Error(
    'WORKSHOP0_ADMIN_KEY is missing/empty in both the environment and the repo-root .env file.',
  );
}

/**
 * Pull the first absolute pretty URL of a given kind (/j/, /p/ or /f/) out of
 * an element's visible text (link elements may also contain copy-button text).
 */
export function extractUrl(text: string, kind: '/j/' | '/p/' | '/f/'): string {
  const escaped = kind.replace(/\//g, '\\/');
  const re = new RegExp(`https?:\\/\\/\\S+${escaped}[A-Za-z0-9_-]+`);
  const match = text.match(re);
  if (!match) {
    throw new Error(`Expected a full ${kind} URL in element text, got: ${JSON.stringify(text)}`);
  }
  return match[0];
}

/** A milestone row for the shared composer (capabilities.md C6). */
export interface ComposedMilestone {
  title: string;
  content: string;
}

/**
 * Drive the PUBLIC create flow (`/app/create/`, no access key at any point):
 * fill the shared composer with `name` + `milestones`, then the final email
 * step, submit, and return the two links revealed on the success screen.
 *
 * The page must already be on the create page (`create-page` visible) — the
 * caller decides how it got there (landing CTA or direct navigation), which is
 * itself part of what the specs assert.
 */
export async function composePublicWorkshop(
  page: Page,
  opts: { name: string; milestones: ComposedMilestone[]; email: string },
): Promise<{ dashboardUrl: string; joinUrl: string }> {
  await fillComposer(page, opts.name, opts.milestones);
  await submitPublicCreate(page, opts.email);

  const success = page.getByTestId('create-success');
  await expect(success).toBeVisible({ timeout: 15_000 });
  const dashboardUrl = extractUrl(
    await success.getByTestId('success-dashboard-link').innerText(),
    '/f/',
  );
  const joinUrl = extractUrl(await success.getByTestId('success-join-link').innerText(), '/j/');
  return { dashboardUrl, joinUrl };
}

/** Fill the shared milestone composer (same component as the admin console). */
export async function fillComposer(
  page: Page,
  name: string,
  milestones: ComposedMilestone[],
): Promise<void> {
  const composer = page.getByTestId('composer');
  await expect(composer).toBeVisible();

  // Wait until React has attached to the input (hydration done) BEFORE typing,
  // otherwise hydration resets the value; then verify (retry) the typed value.
  const nameInput = page.getByTestId('workshop-name-input');
  await nameInput.waitFor({ state: 'visible' });
  await expect
    .poll(
      () => nameInput.evaluate((el) => Object.keys(el).some((k) => k.startsWith('__reactProps'))),
      { timeout: 30_000 },
    )
    .toBe(true);
  await expect(async () => {
    await nameInput.fill(name);
    await expect(nameInput).toHaveValue(name, { timeout: 1_000 });
  }).toPass({ timeout: 15_000 });

  const titleInputs = page.getByTestId('milestone-title-input');
  // A click before React hydrates is silently lost, so retry: click, then wait
  // briefly for the row count to grow; repeat until the target count is reached.
  const addButton = page.getByTestId('add-milestone-button');
  await expect(addButton).toBeVisible();
  const deadline = Date.now() + 30_000;
  while ((await titleInputs.count()) < milestones.length) {
    if (Date.now() > deadline) break;
    const before = await titleInputs.count();
    await addButton.click();
    await expect
      .poll(async () => titleInputs.count(), { timeout: 1_500 })
      .toBeGreaterThan(before)
      .catch(() => undefined);
  }
  await expect(titleInputs).toHaveCount(milestones.length);

  const contentInputs = page.getByTestId('milestone-content-input');
  for (const [i, m] of milestones.entries()) {
    await titleInputs.nth(i).fill(m.title);
    await expect(titleInputs.nth(i)).toHaveValue(m.title);
    await contentInputs.nth(i).fill(m.content);
    await expect(contentInputs.nth(i)).toHaveValue(m.content);
  }
}

/**
 * Complete the final step of the public create flow: reveal the email field
 * (the composer may present it behind a "next/continue" step — capabilities.md
 * C6 "the last step before anything is created"), type `email`, submit.
 */
export async function submitPublicCreate(page: Page, email: string): Promise<void> {
  const emailInput = page.getByTestId('creator-email-input');
  for (let i = 0; i < 3 && !(await emailInput.isVisible().catch(() => false)); i += 1) {
    const next = page.getByRole('button', { name: /next|continue/i }).first();
    if (!(await next.isVisible().catch(() => false))) break;
    await next.click();
  }
  await expect(emailInput).toBeVisible();
  await emailInput.fill(email);
  await expect(emailInput).toHaveValue(email);
  await page.getByTestId('create-submit').click();
}

/** Sign in at the relocated admin console (`/app/admin/`) with the real key. */
export async function signInAdmin(page: Page): Promise<void> {
  await page.goto(`${ADMIN_BASE}/`);
  const keyInput = page.getByTestId('admin-key-input');
  await expect
    .poll(() => keyInput.evaluate((el) => Object.keys(el).some((k) => k.startsWith('__reactProps'))), {
      timeout: 30_000,
    })
    .toBe(true);
  await keyInput.fill(adminKey());
  await page.getByTestId('admin-key-submit').click();
  await expect(page.getByTestId('new-workshop-button')).toBeVisible({ timeout: 15_000 });
}

/** The admin all-workshops card for a given workshop name. */
export function adminWorkshopCard(page: Page, name: string): Locator {
  return page.getByTestId('workshop-card').filter({ hasText: name }).first();
}

/**
 * Wait until React has attached its props to the element (hydration done) —
 * a click/keystroke delivered before hydration on a static export is lost.
 * Phase 10 addition (opportunity-board.spec.ts); existing helpers unchanged.
 */
export async function waitForHydration(locator: Locator): Promise<void> {
  await locator.first().waitFor({ state: 'visible' });
  await expect
    .poll(
      () =>
        locator
          .first()
          .evaluate((el) => Object.keys(el).some((k) => k.startsWith('__reactProps'))),
      { timeout: 30_000 },
    )
    .toBe(true);
}

/** Fill an input after hydration and retry until the controlled value sticks. */
export async function fillStable(locator: Locator, value: string): Promise<void> {
  await waitForHydration(locator);
  await expect(async () => {
    await locator.fill(value);
    await expect(locator).toHaveValue(value, { timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
}
