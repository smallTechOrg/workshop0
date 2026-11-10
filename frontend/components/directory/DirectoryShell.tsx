export function DirectoryShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col overflow-x-clip">
      <header className="border-b border-stone-200/80 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3.5 sm:px-6">
          <a href="/" className="flex items-center gap-2 font-semibold tracking-tight text-stone-900">
            <span aria-hidden="true">⛵</span>
            Workshop0
          </a>
          <nav className="flex gap-4 text-sm font-medium text-stone-600">
            <a href="/app/opportunities/" className="hover:text-stone-900">Opportunities</a>
            <a href="/trainers" className="hover:text-stone-900">Trainers</a>
          </nav>
        </div>
      </header>
      <div className="flex-1">{children}</div>
      <footer className="border-t border-stone-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-6 text-sm text-stone-500 sm:px-6">
          Trainers from the smallTech network.{" "}
          <a href="/network" className="underline underline-offset-4">Join the network</a>
        </div>
      </footer>
    </div>
  );
}
