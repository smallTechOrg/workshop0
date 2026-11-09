import { cn } from "@/lib/format";
import { signInPageUrl } from "@/lib/networkAuth";

/** Where the board's CTA lands: sign-in, then onboarding (spec/capabilities.md C12). */
export const JOIN_NETWORK_HREF = signInPageUrl("/app/network/join/");

/**
 * The real "Join our network" call to action (Phase 11 — replaces the
 * labelled stub). `variant="header"` is the board header button;
 * `variant="card"` is the listing page's side card.
 */
export function JoinNetworkCta({
  variant = "header",
  className,
}: {
  variant?: "header" | "card";
  className?: string;
}) {
  const link = (
    <a
      href={JOIN_NETWORK_HREF}
      data-testid="join-network-cta"
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg bg-brand-600 px-4 py-2 font-medium text-white shadow-sm transition-colors hover:bg-brand-700 active:bg-brand-800",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600",
        variant === "card" && "w-full text-sm",
      )}
    >
      Join our network
      <span aria-hidden="true">→</span>
    </a>
  );

  if (variant === "card") {
    return (
      <div className={cn("rounded-xl border border-brand-200 bg-brand-50/60 p-4", className)}>
        <h3 className="text-sm font-semibold text-stone-900">Trainer? Join our network</h3>
        <p className="mt-1 mb-3 text-sm text-stone-600">
          Sign in with Google, drop your CV and get matched to opportunities like this.
        </p>
        {link}
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col items-start gap-1.5", className)}>
      {link}
      <p className="text-xs text-stone-500">Sign in with Google and drop your CV — about two minutes.</p>
    </div>
  );
}
