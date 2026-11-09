import AccountMenu from "@/components/network/AccountMenu";

/**
 * Page chrome for the trainer-network pages (onboarding, My profile): brand
 * header with the account menu, and a quiet footer. Mirrors the board's
 * BoardShell so the network feels like one product.
 */
export function NetworkShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col overflow-x-clip bg-stone-50">
      <header className="border-b border-stone-200/80 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-3.5 sm:px-6">
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
            <AccountMenu />
          </nav>
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-stone-200 bg-white">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-sm text-stone-500 sm:px-6">
          <p>The smallTech trainer network.</p>
          <a href="/app/opportunities/" className="underline underline-offset-4 hover:text-stone-800">
            Browse opportunities
          </a>
        </div>
      </footer>
    </div>
  );
}
