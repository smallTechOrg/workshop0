import AccountMenu from "@/components/network/AccountMenu";

/**
 * Chrome for the trainer-network pages owned by the sign-in slice (sign-in,
 * network home): brand, Opportunities link and the account menu. Outbound
 * links are plain `<a href>` because `/` is served outside the /app basePath.
 */
export function NetworkShell({
  children,
  showAccount = true,
}: {
  children: React.ReactNode;
  showAccount?: boolean;
}) {
  return (
    <div className="flex min-h-screen flex-col overflow-x-clip bg-stone-50">
      <header className="border-b border-stone-200/80 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <a
            href="/"
            className="flex items-center gap-2 font-semibold tracking-tight text-stone-900"
          >
            <span aria-hidden="true">⛵</span>
            Workshop0
          </a>
          <nav className="flex items-center gap-4">
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
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-5 text-sm text-stone-500 sm:px-6">
          <p>The smallTech trainer network.</p>
          <a href="/" className="underline underline-offset-4 hover:text-stone-800">
            About Workshop0
          </a>
        </div>
      </footer>
    </div>
  );
}
