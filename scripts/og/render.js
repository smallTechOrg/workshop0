#!/usr/bin/env node
/**
 * Renders the Open Graph / Twitter share images (api.md §Phase 13b → Share
 * images) from scripts/og/template.html into frontend/public/og/<variant>.png,
 * 1200×630, deviceScaleFactor 1.
 *
 * Run from the repo root:  node scripts/og/render.js
 * Needs Playwright with Chromium on the Node path and the Inter font installed
 * system-wide (the script fails if Inter is not available).
 */
const path = require("node:path");
const fs = require("node:fs");
const { chromium } = require("playwright");

const VARIANTS = ["landing", "opportunities", "directory", "default"];
const TEMPLATE = path.join(__dirname, "template.html");
const OUT_DIR = path.join(__dirname, "..", "..", "frontend", "public", "og");

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({
      viewport: { width: 1200, height: 630 },
      deviceScaleFactor: 1,
    });
    for (const variant of VARIANTS) {
      await page.goto(`file://${TEMPLATE}#${variant}`);
      await page.reload(); // the hash alone does not re-run the script
      await page.evaluate(() => document.fonts.ready);
      const hasInter = await page.evaluate(() => document.fonts.check('700 68px "Inter"'));
      const logoOk = await page.evaluate(() => {
        const img = document.querySelector(".brand img");
        return img.complete && img.naturalWidth > 0;
      });
      if (!hasInter) throw new Error("Inter font not available");
      if (!logoOk) throw new Error("smalltech logo failed to load");
      const out = path.join(OUT_DIR, `${variant}.png`);
      await page.screenshot({ path: out, type: "png" });
      console.log(`${out} ${fs.statSync(out).size} bytes`);
    }
  } finally {
    await browser.close();
  }
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
