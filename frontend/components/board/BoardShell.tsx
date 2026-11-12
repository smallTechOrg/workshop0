/**
 * Page chrome shared by the public board and listing pages: a slim brand
 * header and footer. Outbound links are plain `<a href>` (the landing page is
 * served from `/`, outside the /app basePath).
 *
 * Both pages are public and measured (`<Analytics />`). Any link added to them
 * that leads outside the landing page, the board and the listing pages must be
 * a plain `<a href>`, so the analytics tag never follows a visitor there.
 */
import { Analytics } from "@/components/ui/Analytics";

export function BoardShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col overflow-x-clip">
      <Analytics />
      <header className="border-b border-stone-200/80 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3.5 sm:px-6">
          <a
            href="/"
            className="flex items-center gap-2 font-semibold tracking-tight text-stone-900"
          >
            <span aria-hidden="true">⛵</span>
            Workshop0
          </a>
          <a
            href="/app/opportunities/"
            className="text-sm font-medium text-stone-600 hover:text-stone-900"
          >
            Opportunities
          </a>
        </div>
      </header>
      <div className="flex-1">{children}</div>
      <footer className="border-t border-stone-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-sm text-stone-500 sm:px-6">
          <p>Opportunities from the smallTech partner network.</p>
          <a href="/" className="underline underline-offset-4 hover:text-stone-800">
            About Workshop0
          </a>
        </div>
      </footer>
    </div>
  );
}
