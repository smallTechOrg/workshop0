import AccountMenu from "@/components/network/AccountMenu";

/**
 * Page chrome for every trainer-network page: brand header (Opportunities link +
 * account menu) and a quiet footer. Mirrors the board's BoardShell so the network
 * feels like one product. Outbound links are plain `<a href>` because `/` is
 * served outside the /app basePath.
 *
 * `variant="entry"` is the wider sign-in / network-home chrome (footer links to
 * About Workshop0); the default `"app"` is the narrower onboarding / My profile
 * chrome (footer links to opportunities). `showAccount={false}` hides the
 * account menu (the sign-in page).
 */
export function NetworkShell({
  children,
  showAccount = true,
  variant = "app",
}: {
  children: React.ReactNode;
  showAccount?: boolean;
  variant?: "app" | "entry";
}) {
  const entry = variant === "entry";
  const width = entry ? "max-w-5xl" : "max-w-4xl";
  return (
    <div className="flex min-h-screen flex-col overflow-x-clip bg-stone-50">
      <header className="border-b border-stone-200/80 bg-white/80 backdrop-blur">
        <div
          className={`mx-auto flex ${width} items-center justify-between gap-3 px-4 ${entry ? "py-3" : "py-3.5"} sm:px-6`}
        >
          <a
            href="/"
            className="flex items-center gap-2 font-semibold tracking-tight text-stone-900"
          >
            <span aria-hidden="true">⛵</span>
            Workshop0
          </a>
          <nav aria-label="Network" className="flex items-center gap-4">
            <a
              href="/app/opportunities/"
              className="text-sm font-medium text-stone-600 hover:text-stone-900"
            >
              Opportunities
            </a>
            {showAccount && <AccountMenu />}
          </nav>
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-stone-200 bg-white">
        <div
          className={`mx-auto flex ${width} flex-wrap items-center justify-between gap-3 px-4 ${entry ? "py-5" : "py-6"} text-sm text-stone-500 sm:px-6`}
        >
          <p>The smallTech trainer network.</p>
          {entry ? (
            <a href="/" className="underline underline-offset-4 hover:text-stone-800">
              About Workshop0
            </a>
          ) : (
            <a
              href="/app/opportunities/"
              className="underline underline-offset-4 hover:text-stone-800"
            >
              Browse opportunities
            </a>
          )}
        </div>
      </footer>
    </div>
  );
}
