"use client";

/**
 * Google Analytics for the PUBLIC pages only (spec/capabilities.md C5, C10):
 * the landing page `/`, the opportunity board `/app/opportunities/` and the
 * listing pages `/opportunities/<slug>` (plus the legacy listing alias
 * `/app/opportunities/view/`).
 *
 * Loads the shared smallTech script (`public/st-analytics.js`, copied unchanged
 * from the smallTech site set; never edit it here). That script limits itself
 * to the production hostname and to the same public paths. This island adds
 * the guards the shared script cannot know about. The script is not loaded:
 *
 * - on any other path;
 * - when the query string carries a parameter this page does not define
 *   (campaign parameters are always allowed), so an unexpected `?token=...`
 *   is never sent as the page location;
 * - when the visitor arrived from a page of this site that is not one of the
 *   public pages above, because the browser would report that page's full URL
 *   (which can carry a join code, invite or dashboard token) as the referrer.
 *
 * Once loaded, GA also reports client-side (history) navigations. So on the
 * pages that render this, every link to a page NOT listed above must be a
 * plain `<a href>` (a full page load), never `next/link` or the router.
 *
 * Render it ONLY on pages that are public and free of codes, tokens and
 * personal identifiers in the URL. Never put it in the root layout.
 */

import Script from "next/script";
import { useEffect, useState } from "react";

const CAMPAIGN_PARAM = /^(utm_[a-z_]+|gclid|gbraid|wbraid|fbclid|msclkid)$/;

/** Public pages and the (non-sensitive) query parameters each one defines. */
const PUBLIC_PAGES: { path: RegExp; params: string[] }[] = [
  { path: /^\/$/, params: [] },
  { path: /^\/app\/opportunities\/?$/, params: ["type", "topic", "sort", "page"] },
  { path: /^\/app\/opportunities\/view\/?$/, params: ["id", "slug", "from"] },
  { path: /^\/opportunities\/[A-Za-z0-9-]{1,80}\/?$/, params: ["from"] },
];

function isPublicUrl(url: URL | Location): boolean {
  const page = PUBLIC_PAGES.find((p) => p.path.test(url.pathname));
  if (!page) return false;
  for (const key of new URLSearchParams(url.search).keys()) {
    if (!page.params.includes(key) && !CAMPAIGN_PARAM.test(key)) return false;
  }
  return true;
}

function isSafeToMeasure(): boolean {
  if (!isPublicUrl(window.location)) return false;
  if (!document.referrer) return true;
  try {
    const ref = new URL(document.referrer);
    return ref.origin !== window.location.origin || isPublicUrl(ref);
  } catch {
    return false;
  }
}

export function Analytics() {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    setEnabled(isSafeToMeasure());
  }, []);

  // `next/script` does not add the `/app` basePath to `src`.
  return enabled ? <Script src="/app/st-analytics.js" strategy="afterInteractive" /> : null;
}
