/** Listing-page apply helpers (Phase 12). */
import { signInPageUrl } from "@/lib/networkAuth";

/** Sign-in link that returns the trainer to this listing's slug URL. */
export function signInToApplyHref(slug: string): string {
  // safeNext only allows /app/ paths, so return via the static listing view.
  return signInPageUrl(`/app/opportunities/view/?slug=${encodeURIComponent(slug)}`);
}
