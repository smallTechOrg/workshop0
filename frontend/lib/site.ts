/**
 * Public origin and head-metadata helpers for the indexable static pages
 * (api.md §Phase 13b): the landing page `/`, the board `/app/opportunities/`
 * and the trainer directory `/app/network/directory/`.
 *
 * The export is static, so the public origin is a build-time constant: it is
 * the production domain that `WORKSHOP0_BASE_URL` names on the server (the
 * sitemap uses the same URLs). Server-rendered listing and trainer pages build
 * their own head on the server and never use these helpers.
 */

import type { Metadata } from "next";

export const SITE_URL = "https://workshop0.smalltech.in";
export const SITE_NAME = "Workshop0";
export const PUBLISHER_NAME = "smallTech";
export const PUBLISHER_URL = "https://smalltech.in";

/** Absolute public URL for a path that starts with `/`. */
export function absoluteUrl(path: string): string {
  return `${SITE_URL}${path}`;
}

/**
 * Title, description, canonical, Open Graph and Twitter card for one public
 * page. There is no `og:image`: no share-sized image asset exists (the
 * smallTech logo is 121×128, below the preview minimums), so the card is
 * `summary`.
 */
export function publicPageMetadata(page: {
  title: string;
  description: string;
  path: string;
}): Metadata {
  const url = absoluteUrl(page.path);
  return {
    title: page.title,
    description: page.description,
    alternates: { canonical: url },
    openGraph: {
      type: "website",
      siteName: SITE_NAME,
      locale: "en_IN",
      title: page.title,
      description: page.description,
      url,
    },
    twitter: {
      card: "summary",
      title: page.title,
      description: page.description,
    },
  };
}

/** JSON for a `<script type="application/ld+json">`: no `<`, `>` or `&` survive. */
export function jsonLdScript(data: unknown): string {
  return JSON.stringify(data)
    .replace(/</g, "\\u003c")
    .replace(/>/g, "\\u003e")
    .replace(/&/g, "\\u0026");
}
