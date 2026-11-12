"use client";

/**
 * Google Analytics for the PUBLIC landing page only (spec/capabilities.md C5).
 *
 * Loads the shared smallTech script (`public/st-analytics.js`, copied unchanged
 * from the smallTech site set; never edit it here). That script already limits
 * itself to the production hostname and skips every `/app/...` path, so the
 * signed-in and token-bearing screens are never measured. This island adds
 * the guards the shared script cannot know about:
 *
 * - only at `/` (the landing page's one URL);
 * - not when the query string carries anything but campaign parameters, so an
 *   unexpected `?token=...` is never sent as the page location;
 * - not when the visitor arrived from another page of this site, because the
 *   browser would report that page's full URL (which can carry a join code,
 *   invite or dashboard token) to GA as the referrer.
 *
 * Render it ONLY on pages that are public, logged-out and free of codes or
 * tokens in the URL. Never put it in the root layout.
 */

import Script from "next/script";
import { useEffect, useState } from "react";

const CAMPAIGN_PARAM = /^(utm_[a-z_]+|gclid|gbraid|wbraid|fbclid|msclkid)$/;

function isSafeToMeasure(): boolean {
  if (window.location.pathname !== "/") return false;
  for (const key of new URLSearchParams(window.location.search).keys()) {
    if (!CAMPAIGN_PARAM.test(key)) return false;
  }
  if (document.referrer) {
    try {
      const ref = new URL(document.referrer);
      if (ref.origin === window.location.origin && (ref.pathname !== "/" || ref.search)) {
        return false;
      }
    } catch {
      return false;
    }
  }
  return true;
}

export function Analytics() {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    setEnabled(isSafeToMeasure());
  }, []);

  // `next/script` does not add the `/app` basePath to `src`.
  return enabled ? <Script src="/app/st-analytics.js" strategy="afterInteractive" /> : null;
}
