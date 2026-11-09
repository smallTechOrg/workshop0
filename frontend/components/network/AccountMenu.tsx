"use client";

/**
 * Signed-in account menu for network pages (spec/capabilities.md C11):
 * avatar + name, "My profile", "Sign out" (plus "Admin console" for an
 * allowlisted admin). Signed out → a "Sign in" link back to this page.
 * Loading → a small placeholder; a failed check → a quiet retry link.
 *
 * Default export, no props — imported by other network slices' pages.
 */

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/format";
import { Avatar } from "@/components/network/auth/Avatar";
import { signInPageUrl, signOut, useCurrentUser } from "@/lib/networkAuth";

function currentAppPath(): string {
  if (typeof window === "undefined") return "/app/network/";
  return `${window.location.pathname}${window.location.search}`;
}

export default function AccountMenu() {
  const { user, loading, error, refresh } = useCurrentUser();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function handleSignOut() {
    setSigningOut(true);
    setSignOutError(null);
    try {
      await signOut();
      window.location.assign("/app/signin/?signed_out=1");
    } catch {
      setSignOutError("Couldn't sign you out — try again.");
      setSigningOut(false);
    }
  }

  if (loading && !user) {
    return (
      <span
        data-testid="account-menu-loading"
        aria-label="Checking sign-in"
        className="inline-block size-8 animate-pulse rounded-full bg-stone-200"
      />
    );
  }

  if (error && !user) {
    return (
      <button
        type="button"
        onClick={() => void refresh()}
        className="text-sm font-medium text-stone-500 underline underline-offset-4 hover:text-stone-800"
        title={error}
      >
        Retry sign-in check
      </button>
    );
  }

  if (!user) {
    return (
      <a
        data-testid="account-signin"
        href={signInPageUrl(currentAppPath())}
        className="rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-sm font-medium text-stone-800 shadow-sm hover:bg-stone-50"
      >
        Sign in
      </a>
    );
  }

  const name = user.display_name?.trim() || user.email;

  return (
    <div ref={rootRef} className="relative" data-testid="account-menu">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-full py-0.5 pr-2 pl-0.5 text-sm font-medium text-stone-700 hover:bg-stone-100 focus-visible:outline-2 focus-visible:outline-brand-600"
      >
        <Avatar user={user} />
        <span className="hidden max-w-[10rem] truncate sm:inline">{name}</span>
        <svg aria-hidden="true" viewBox="0 0 20 20" fill="currentColor" className="size-4 text-stone-400">
          <path
            fillRule="evenodd"
            d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06Z"
            clipRule="evenodd"
          />
        </svg>
        <span className="sr-only">Account menu</span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-30 mt-2 w-64 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-lg"
        >
          <div className="flex items-center gap-3 border-b border-stone-100 px-4 py-3">
            <Avatar user={user} className="size-10" />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-stone-900">{name}</p>
              <p className="truncate text-xs text-stone-500">{user.email}</p>
            </div>
          </div>
          <div className="py-1">
            <a
              role="menuitem"
              href={user.has_profile ? "/app/network/me/" : "/app/network/join/"}
              className="block px-4 py-2 text-sm text-stone-700 hover:bg-stone-50"
            >
              My profile
            </a>
            {user.is_admin && (
              <a
                role="menuitem"
                href="/app/admin/"
                className="block px-4 py-2 text-sm text-stone-700 hover:bg-stone-50"
              >
                Admin console
              </a>
            )}
            <button
              role="menuitem"
              type="button"
              disabled={signingOut}
              onClick={() => void handleSignOut()}
              className={cn(
                "block w-full px-4 py-2 text-left text-sm text-stone-700 hover:bg-stone-50",
                signingOut && "cursor-wait opacity-60",
              )}
            >
              {signingOut ? "Signing out…" : "Sign out"}
            </button>
            {signOutError && (
              <p role="alert" className="px-4 pb-2 text-xs text-red-600">
                {signOutError}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
